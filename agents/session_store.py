from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Protocol

from config.settings import settings

logger = logging.getLogger(__name__)


class SessionStore(Protocol):
    backend_name: str

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        ...

    def append(self, session_id: str, role: str, content: str) -> None:
        ...

    def clear(self, session_id: str) -> None:
        ...

    def count(self, session_id: str) -> int:
        ...

    def get_state(self, session_id: str, state_key: str) -> Dict[str, Any] | None:
        ...

    def set_state(self, session_id: str, state_key: str, value: Dict[str, Any]) -> None:
        ...

    def clear_state(self, session_id: str, state_key: str | None = None) -> None:
        ...


class InMemorySessionStore:
    backend_name = "memory"

    def __init__(self, history_size: int):
        self.history_size = max(1, int(history_size))
        self._session_histories: Dict[str, Deque[Dict[str, str]]] = defaultdict(
            lambda: deque(maxlen=self.history_size)
        )
        self._session_states: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        return list(self._session_histories[session_id])

    def append(self, session_id: str, role: str, content: str) -> None:
        self._session_histories[session_id].append({"role": role, "content": content})

    def clear(self, session_id: str) -> None:
        self._session_histories[session_id].clear()
        self._session_states.pop(session_id, None)

    def count(self, session_id: str) -> int:
        return len(self._session_histories[session_id])

    def get_state(self, session_id: str, state_key: str) -> Dict[str, Any] | None:
        value = self._session_states.get(session_id, {}).get(state_key)
        return dict(value) if isinstance(value, dict) else None

    def set_state(self, session_id: str, state_key: str, value: Dict[str, Any]) -> None:
        self._session_states[session_id][state_key] = dict(value)

    def clear_state(self, session_id: str, state_key: str | None = None) -> None:
        if state_key is None:
            self._session_states.pop(session_id, None)
            return
        state_map = self._session_states.get(session_id)
        if not state_map:
            return
        state_map.pop(state_key, None)
        if not state_map:
            self._session_states.pop(session_id, None)


class RedisSessionStore:
    backend_name = "redis"

    def __init__(
        self,
        history_size: int,
        host: str,
        port: int,
        db: int,
        password: str,
        key_prefix: str,
        ttl_sec: int,
    ):
        try:
            import redis
        except ImportError as exc:
            raise RuntimeError("redis package is not installed") from exc

        self.history_size = max(1, int(history_size))
        self.ttl_sec = max(0, int(ttl_sec))
        self.key_prefix = key_prefix.strip() or "rag_crm_agent:session"
        self._client = redis.Redis(
            host=host,
            port=int(port),
            db=int(db),
            password=password or None,
            decode_responses=True,
        )
        self._client.ping()

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        values = self._client.lrange(self._history_key(session_id), 0, -1)
        history: List[Dict[str, str]] = []
        for item in values:
            try:
                parsed = json.loads(item)
            except Exception:
                continue
            role = str(parsed.get("role", "")).strip()
            content = str(parsed.get("content", ""))
            if role and content:
                history.append({"role": role, "content": content})
        return history

    def append(self, session_id: str, role: str, content: str) -> None:
        payload = json.dumps({"role": role, "content": content}, ensure_ascii=False)
        key = self._history_key(session_id)
        pipe = self._client.pipeline()
        pipe.rpush(key, payload)
        pipe.ltrim(key, -self.history_size, -1)
        if self.ttl_sec > 0:
            pipe.expire(key, self.ttl_sec)
        pipe.execute()

    def clear(self, session_id: str) -> None:
        self._client.delete(self._history_key(session_id))
        for key in self._client.scan_iter(match=f"{self._state_prefix(session_id)}*"):
            self._client.delete(key)

    def count(self, session_id: str) -> int:
        return int(self._client.llen(self._history_key(session_id)))

    def get_state(self, session_id: str, state_key: str) -> Dict[str, Any] | None:
        raw = self._client.get(self._state_key(session_id, state_key))
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    def set_state(self, session_id: str, state_key: str, value: Dict[str, Any]) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        key = self._state_key(session_id, state_key)
        if self.ttl_sec > 0:
            self._client.setex(key, self.ttl_sec, payload)
        else:
            self._client.set(key, payload)

    def clear_state(self, session_id: str, state_key: str | None = None) -> None:
        if state_key is None:
            for key in self._client.scan_iter(match=f"{self._state_prefix(session_id)}*"):
                self._client.delete(key)
            return
        self._client.delete(self._state_key(session_id, state_key))

    def _history_key(self, session_id: str) -> str:
        return f"{self.key_prefix}:{session_id}:history"

    def _state_prefix(self, session_id: str) -> str:
        return f"{self.key_prefix}:{session_id}:state:"

    def _state_key(self, session_id: str, state_key: str) -> str:
        return f"{self._state_prefix(session_id)}{state_key}"


def build_session_store(history_size: int) -> SessionStore:
    backend = str(getattr(settings, "SESSION_STORE_BACKEND", "memory")).strip().lower()
    if backend == "redis":
        try:
            store = RedisSessionStore(
                history_size=history_size,
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD,
                key_prefix=settings.REDIS_KEY_PREFIX,
                ttl_sec=settings.SESSION_TTL_SEC,
            )
            logger.info(
                "Session store initialized: redis(%s:%s/%s)",
                settings.REDIS_HOST,
                settings.REDIS_PORT,
                settings.REDIS_DB,
            )
            return store
        except Exception as exc:
            logger.warning("Redis session store unavailable, fallback to memory: %s", exc)

    logger.info("Session store initialized: memory")
    return InMemorySessionStore(history_size=history_size)
