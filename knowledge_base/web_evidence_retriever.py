"""Retrieve persisted web research evidence from the dedicated Qdrant collection."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Sequence

from config.settings import settings

logger = logging.getLogger(__name__)


class WebEvidenceRetriever:
    def __init__(self) -> None:
        self.enabled = bool(getattr(settings, "WEB_RESEARCH_QDRANT_ENABLED", False))
        self.collection = str(
            getattr(settings, "WEB_RESEARCH_QDRANT_COLLECTION", "web_research_evidence")
            or "web_research_evidence"
        ).strip() or "web_research_evidence"
        self.scope = str(getattr(settings, "WEB_RESEARCH_QDRANT_SCOPE", "session") or "session").strip() or "session"
        self.top_k_default = max(1, int(getattr(settings, "WEB_RESEARCH_QDRANT_TOP_K", 6)))
        self.host = str(getattr(settings, "QDRANT_HOST", "localhost") or "localhost")
        self.port = int(getattr(settings, "QDRANT_PORT", 6333))

        self.client = None
        self.embedding_model = None
        self._qdrant_models = None
        self._backend_initialized = False
        self._backend_error = ""

    def retrieve(
        self,
        *,
        query: str,
        session_id: str,
        top_k: int | None = None,
    ) -> list[dict[str, object]]:
        query_text = str(query or "").strip()
        if not query_text or not self.enabled or not self._ensure_backend():
            return []

        effective_top_k = max(1, int(top_k or self.top_k_default))
        fetch_limit = max(effective_top_k * 4, effective_top_k)
        query_filter = self._build_filter(session_id=session_id)
        hits = self._search_points(
            query_vec=self._encode_query(query_text),
            limit=fetch_limit,
            query_filter=query_filter,
        )

        now_dt = datetime.now(timezone.utc)
        docs: List[Dict[str, object]] = []
        seen_urls: set[str] = set()
        for hit in hits:
            payload = getattr(hit, "payload", {}) or {}
            if not isinstance(payload, dict):
                continue
            if self._is_expired(payload.get("expires_at"), now_dt):
                continue
            url = str(payload.get("url", "") or "").strip()
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            docs.append(
                self._payload_to_doc(
                    point_id=getattr(hit, "id", None),
                    score=float(getattr(hit, "score", 0.0) or 0.0),
                    payload=payload,
                )
            )
            if len(docs) >= effective_top_k:
                break
        return docs

    def _ensure_backend(self) -> bool:
        if not self.enabled:
            return False
        if self._backend_initialized:
            return bool(self.client is not None and self.embedding_model is not None)
        self._backend_initialized = True
        try:
            from knowledge_base.builder import KnowledgeBaseBuilder
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qdrant_models

            KnowledgeBaseBuilder._ensure_hf_cached_download_compat()

            from sentence_transformers import SentenceTransformer

            self.client = QdrantClient(host=self.host, port=self.port)
            self.embedding_model = SentenceTransformer(
                settings.EMBEDDING_MODEL,
                device=settings.EMBEDDING_DEVICE,
            )
            self._qdrant_models = qdrant_models
            self._backend_error = ""
            return True
        except Exception as exc:
            self._backend_error = str(exc)
            logger.warning("Web evidence retriever backend unavailable: %s", exc)
            self.client = None
            self.embedding_model = None
            self._qdrant_models = None
            return False

    def _build_filter(self, *, session_id: str):
        if self._qdrant_models is None:
            return None
        must = [
            self._qdrant_models.FieldCondition(
                key="source",
                match=self._qdrant_models.MatchValue(value="web_research"),
            )
        ]
        if self.scope == "session":
            must.append(
                self._qdrant_models.FieldCondition(
                    key="scope",
                    match=self._qdrant_models.MatchValue(value="session"),
                )
            )
            must.append(
                self._qdrant_models.FieldCondition(
                    key="session_id",
                    match=self._qdrant_models.MatchValue(value=str(session_id or "")),
                )
            )
        elif self.scope == "global":
            must.append(
                self._qdrant_models.FieldCondition(
                    key="scope",
                    match=self._qdrant_models.MatchValue(value="global"),
                )
            )
        return self._qdrant_models.Filter(must=must)

    def _payload_to_doc(self, *, point_id: object, score: float, payload: dict[str, object]) -> dict[str, object]:
        title = str(payload.get("title", "") or payload.get("url", "")).strip()
        url = str(payload.get("url", "") or "").strip()
        text = str(payload.get("text", "") or "").strip()
        return {
            "id": f"web_qdrant_{point_id}",
            "score": round(float(score), 4),
            "text": f"web_source: {title}; url: {url}; content: {text[:1800]}",
            "payload": {
                "source": "web_research_qdrant",
                "model_id": "",
                "template_family": "",
                "title": title,
                "url": url,
                "domain": str(payload.get("domain", "") or "").strip(),
                "saved_path": str(payload.get("saved_path", "") or "").strip(),
                "session_id": str(payload.get("session_id", "") or "").strip(),
                "scope": str(payload.get("scope", "") or "").strip(),
                "collection": self.collection,
                "chunk_index": int(payload.get("chunk_index", 0) or 0),
                "content_hash": str(payload.get("content_hash", "") or "").strip(),
            },
        }

    def _encode_query(self, text: str) -> List[float]:
        assert self.embedding_model is not None
        try:
            encoded = self.embedding_model.encode([text], normalize_embeddings=True)[0]
        except TypeError:
            encoded = self.embedding_model.encode([text])[0]
        raw = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        return [float(value) for value in raw]

    def _search_points(self, *, query_vec: Sequence[float], limit: int, query_filter: object) -> List[object]:
        assert self.client is not None
        try:
            return list(
                self.client.search(
                    collection_name=self.collection,
                    query_vector=list(query_vec),
                    limit=limit,
                    with_payload=True,
                    query_filter=query_filter,
                )
                or []
            )
        except TypeError:
            try:
                return list(
                    self.client.search(
                        collection_name=self.collection,
                        query_vector=list(query_vec),
                        limit=limit,
                        with_payload=True,
                        filter=query_filter,
                    )
                    or []
                )
            except Exception:
                pass
        except Exception:
            pass

        try:
            points = self.client.query_points(
                collection_name=self.collection,
                query=list(query_vec),
                limit=limit,
                with_payload=True,
                query_filter=query_filter,
            )
        except TypeError:
            points = self.client.query_points(
                collection_name=self.collection,
                query=list(query_vec),
                limit=limit,
                with_payload=True,
                filter=query_filter,
            )
        return list(getattr(points, "points", points) or [])

    def _parse_iso_datetime(self, value: object) -> datetime | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _is_expired(self, expires_at: object, now_dt: datetime) -> bool:
        expiry_dt = self._parse_iso_datetime(expires_at)
        if expiry_dt is None:
            return False
        return expiry_dt < now_dt
