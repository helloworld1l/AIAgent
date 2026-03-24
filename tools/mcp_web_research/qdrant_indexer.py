"""Incrementally index fetched web research evidence into Qdrant."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Sequence
from urllib.parse import urlparse

from config.settings import settings

logger = logging.getLogger(__name__)


class WebResearchQdrantIndexer:
    def __init__(self) -> None:
        self.enabled = bool(getattr(settings, "WEB_RESEARCH_QDRANT_ENABLED", False))
        self.collection = str(
            getattr(settings, "WEB_RESEARCH_QDRANT_COLLECTION", "web_research_evidence")
            or "web_research_evidence"
        ).strip() or "web_research_evidence"
        self.scope = str(getattr(settings, "WEB_RESEARCH_QDRANT_SCOPE", "session") or "session").strip() or "session"
        self.retention_days = max(0, int(getattr(settings, "WEB_RESEARCH_QDRANT_RETENTION_DAYS", 7)))
        self.max_chunk_chars = max(200, int(getattr(settings, "WEB_RESEARCH_QDRANT_MAX_CHUNK_CHARS", 1000)))
        self.chunk_overlap = max(0, int(getattr(settings, "WEB_RESEARCH_QDRANT_CHUNK_OVERLAP", 120)))
        self.cleanup_on_write = bool(getattr(settings, "WEB_RESEARCH_QDRANT_CLEANUP_ON_WRITE", True))
        self.host = str(getattr(settings, "QDRANT_HOST", "localhost") or "localhost")
        self.port = int(getattr(settings, "QDRANT_PORT", 6333))

        self.client = None
        self.embedding_model = None
        self.embedding_dim: int | None = None
        self._qdrant_models = None
        self._backend_initialized = False
        self._backend_error = ""

    def default_result(
        self,
        *,
        status: str = "disabled",
        scope: str | None = None,
        sources_total: int = 0,
        sources_indexed: int = 0,
        points_upserted: int = 0,
        cleanup_deleted: int = 0,
        error: str = "",
    ) -> Dict[str, object]:
        return {
            "enabled": bool(self.enabled),
            "status": status,
            "collection": self.collection,
            "scope": str(scope or self.scope or "session"),
            "sources_total": int(sources_total),
            "sources_indexed": int(sources_indexed),
            "points_upserted": int(points_upserted),
            "cleanup_deleted": int(cleanup_deleted),
            "error": str(error or ""),
        }

    def index_sources(
        self,
        *,
        query: str,
        session_id: str,
        fetched_sources: list[dict[str, object]],
        scope: str | None = None,
    ) -> dict[str, object]:
        resolved_scope = str(scope or self.scope or "session").strip() or "session"
        source_items = [item for item in fetched_sources if isinstance(item, dict)]
        sources_total = len(source_items)
        if not self.enabled:
            return self.default_result(status="disabled", scope=resolved_scope, sources_total=sources_total)
        if not self._ensure_backend():
            return self.default_result(
                status="failed",
                scope=resolved_scope,
                sources_total=sources_total,
                error=self._backend_error,
            )

        sources_indexed = 0
        points_upserted = 0
        cleanup_deleted = 0
        try:
            self.ensure_collection()

            prepared_points: List[tuple[int, str, Dict[str, object]]] = []
            now_dt = datetime.now(timezone.utc).replace(microsecond=0)
            fetched_at = now_dt.isoformat()
            expires_at = (now_dt + timedelta(days=self.retention_days)).isoformat()

            for source_item in source_items:
                if str(source_item.get("status", "")).strip() != "success":
                    continue
                extracted_text = self._extract_indexable_text(source_item)
                normalized_text = self._normalize_text(extracted_text)
                if not normalized_text:
                    continue
                chunks = self._chunk_text(normalized_text)
                if not chunks:
                    continue
                sources_indexed += 1
                content_hash = hashlib.sha1(normalized_text.encode("utf-8")).hexdigest()
                for chunk_index, chunk_text in enumerate(chunks, start=1):
                    point_id = self._build_point_id(
                        url=str(source_item.get("url", "") or ""),
                        content_hash=content_hash,
                        chunk_index=chunk_index,
                    )
                    payload = self._build_payload(
                        query=query,
                        session_id=session_id,
                        scope=resolved_scope,
                        source_item=source_item,
                        text=chunk_text,
                        chunk_index=chunk_index,
                        chunk_count=len(chunks),
                        fetched_at=fetched_at,
                        expires_at=expires_at,
                        content_hash=content_hash,
                    )
                    prepared_points.append((point_id, chunk_text, payload))

            if prepared_points:
                vectors = self._encode_texts([item[1] for item in prepared_points])
                points = []
                assert self._qdrant_models is not None
                assert self.client is not None
                for (point_id, _, payload), vector in zip(prepared_points, vectors):
                    points.append(
                        self._qdrant_models.PointStruct(
                            id=point_id,
                            vector=vector,
                            payload=payload,
                        )
                    )
                self.client.upsert(collection_name=self.collection, points=points)
                points_upserted = len(points)

            if self.cleanup_on_write:
                cleanup_deleted = self.cleanup_expired(now_iso=now_dt.isoformat())

            return self.default_result(
                status="success",
                scope=resolved_scope,
                sources_total=sources_total,
                sources_indexed=sources_indexed,
                points_upserted=points_upserted,
                cleanup_deleted=cleanup_deleted,
            )
        except Exception as exc:
            logger.warning("Web research Qdrant indexing failed: %s", exc)
            return self.default_result(
                status="failed",
                scope=resolved_scope,
                sources_total=sources_total,
                sources_indexed=sources_indexed,
                points_upserted=points_upserted,
                cleanup_deleted=cleanup_deleted,
                error=str(exc),
            )

    def cleanup_expired(self, *, now_iso: str | None = None) -> int:
        if not self.enabled or not self._ensure_backend():
            return 0
        now_dt = self._parse_iso_datetime(now_iso) or datetime.now(timezone.utc)
        expired_ids: List[object] = []
        next_offset = None
        while True:
            points, next_offset = self._scroll_points(limit=256, offset=next_offset)
            if not points:
                break
            for point in points:
                payload = getattr(point, "payload", {}) or {}
                if not isinstance(payload, dict):
                    continue
                if self._is_expired(payload.get("expires_at"), now_dt):
                    expired_ids.append(getattr(point, "id", None))
            if next_offset is None:
                break
        return self._delete_points(expired_ids)

    def ensure_collection(self) -> None:
        if not self._ensure_backend():
            raise RuntimeError(self._backend_error or "web research qdrant backend unavailable")
        assert self.client is not None
        assert self.embedding_dim is not None
        assert self._qdrant_models is not None
        try:
            self.client.get_collection(self.collection)
            return
        except Exception:
            pass
        self.client.create_collection(
            collection_name=self.collection,
            vectors_config=self._qdrant_models.VectorParams(
                size=self.embedding_dim,
                distance=self._qdrant_models.Distance.COSINE,
            ),
        )

    def _ensure_backend(self) -> bool:
        if not self.enabled:
            return False
        if self._backend_initialized:
            return bool(self.client is not None and self.embedding_model is not None and self.embedding_dim)
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
            self.embedding_dim = int(self.embedding_model.get_sentence_embedding_dimension())
            self._qdrant_models = qdrant_models
            self._backend_error = ""
            return True
        except Exception as exc:
            self._backend_error = str(exc)
            logger.warning("Web research Qdrant backend unavailable: %s", exc)
            self.client = None
            self.embedding_model = None
            self.embedding_dim = None
            self._qdrant_models = None
            return False

    def _chunk_text(self, text: str) -> list[str]:
        normalized = self._normalize_text(text)
        if not normalized:
            return []

        paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", normalized) if part.strip()]
        if not paragraphs:
            return [normalized[: self.max_chunk_chars]]

        chunks: List[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > self.max_chunk_chars:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(self._split_long_text(paragraph))
                continue

            candidate = f"{current}\n\n{paragraph}" if current else paragraph
            if len(candidate) <= self.max_chunk_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = paragraph

        if current:
            chunks.append(current)
        return chunks

    def _normalize_text(self, text: str) -> str:
        value = str(text or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
        cleaned_lines = []
        for line in value.split("\n"):
            stripped = line.strip().lstrip("\ufeff")
            if stripped.startswith("#"):
                stripped = stripped.lstrip("#").strip()
            cleaned_lines.append(stripped)
        normalized = "\n".join(cleaned_lines)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        normalized = re.sub(r"[ \t]{2,}", " ", normalized)
        return normalized.strip()

    def _build_point_id(self, *, url: str, content_hash: str, chunk_index: int) -> int:
        digest = hashlib.sha1(f"{url}\n{content_hash}\n{chunk_index}".encode("utf-8")).digest()
        return int.from_bytes(digest[-8:], byteorder="big", signed=False)

    def _build_payload(
        self,
        *,
        query: str,
        session_id: str,
        scope: str,
        source_item: dict[str, object],
        text: str,
        chunk_index: int,
        chunk_count: int,
        fetched_at: str,
        expires_at: str,
        content_hash: str,
    ) -> dict[str, object]:
        url = str(source_item.get("url", "") or "").strip()
        domain = str(source_item.get("domain", "") or "").strip() or urlparse(url).netloc
        title = str(source_item.get("title", "") or "").strip() or url
        return {
            "source": "web_research",
            "scope": scope,
            "session_id": str(session_id or "").strip(),
            "query": str(query or "").strip(),
            "title": title,
            "url": url,
            "domain": domain,
            "saved_path": str(source_item.get("saved_path", "") or "").strip(),
            "chunk_index": int(chunk_index),
            "chunk_count": int(chunk_count),
            "content_hash": content_hash,
            "fetched_at": fetched_at,
            "expires_at": expires_at,
            "text": text,
        }

    def _extract_indexable_text(self, source_item: dict[str, object]) -> str:
        text = str(source_item.get("text", "") or "").strip()
        if text:
            return text
        return str(source_item.get("excerpt", "") or "").strip()

    def _encode_texts(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        assert self.embedding_model is not None
        try:
            encoded = self.embedding_model.encode(list(texts), normalize_embeddings=True)
        except TypeError:
            encoded = self.embedding_model.encode(list(texts))

        vectors: List[List[float]] = []
        for item in encoded:
            raw = item.tolist() if hasattr(item, "tolist") else item
            vectors.append([float(value) for value in raw])
        return vectors

    def _split_long_text(self, text: str) -> List[str]:
        parts: List[str] = []
        start = 0
        safe_overlap = max(0, min(self.chunk_overlap, self.max_chunk_chars // 2))
        while start < len(text):
            end = min(len(text), start + self.max_chunk_chars)
            chunk = text[start:end].strip()
            if chunk:
                parts.append(chunk)
            if end >= len(text):
                break
            start = max(start + 1, end - safe_overlap)
        return parts

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

    def _scroll_points(self, *, limit: int, offset: object = None) -> tuple[list[object], object]:
        assert self.client is not None
        response = self.client.scroll(
            collection_name=self.collection,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if isinstance(response, tuple) and len(response) == 2:
            return list(response[0] or []), response[1]
        points = getattr(response, "points", None)
        if points is not None:
            return list(points or []), getattr(response, "next_page_offset", None)
        return list(response or []), None

    def _delete_points(self, point_ids: Iterable[object]) -> int:
        assert self.client is not None
        assert self._qdrant_models is not None
        normalized_ids = [point_id for point_id in dict.fromkeys(point_ids) if point_id is not None]
        if not normalized_ids:
            return 0
        try:
            self.client.delete(
                collection_name=self.collection,
                points_selector=self._qdrant_models.PointIdsList(points=normalized_ids),
            )
            return len(normalized_ids)
        except Exception:
            try:
                self.client.delete(collection_name=self.collection, points_selector=normalized_ids)
                return len(normalized_ids)
            except Exception as exc:
                logger.warning("Web research Qdrant cleanup failed: %s", exc)
                return 0
