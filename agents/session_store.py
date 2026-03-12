from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from typing import Deque, Dict, List, Protocol

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


class InMemorySessionStore:
    backend_name = "memory"

    def __init__(self, history_size: int):
        self.history_size = max(1, int(history_size))
        self._session_histories: Dict[str, Deque[Dict[str, str]]] = defaultdict(
            lambda: deque(maxlen=self.history_size)
        )

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        return list(self._session_histories[session_id])

    def append(self, session_id: str, role: str, content: str) -> None:
        self._session_histories[session_id].append({"role": role, "content": content})

    def clear(self, session_id: str) -> None:
        self._session_histories[session_id].clear()

    def count(self, session_id: str) -> int:
        return len(self._session_histories[session_id])


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
        values = self._client.lrange(self._key(session_id), 0, -1)
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
        key = self._key(session_id)
        pipe = self._client.pipeline()
        pipe.rpush(key, payload)
        pipe.ltrim(key, -self.history_size, -1)
        if self.ttl_sec > 0:
            pipe.expire(key, self.ttl_sec)
        pipe.execute()

    def clear(self, session_id: str) -> None:
        self._client.delete(self._key(session_id))

    def count(self, session_id: str) -> int:
        return int(self._client.llen(self._key(session_id)))

    def _key(self, session_id: str) -> str:
        return f"{self.key_prefix}:{session_id}"


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
