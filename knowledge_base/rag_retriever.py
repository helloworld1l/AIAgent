"""
Hybrid RAG retriever for MATLAB modeling knowledge.

Pipeline:
1) BM25 lexical recall
2) Vector recall (Qdrant preferred, local embedding fallback)
3) Rule-based rerank and score fusion
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import requests

from config.settings import settings
from knowledge_base.document_loader import DEFAULT_DOCS_DIR, load_file_documents
from knowledge_base.matlab_model_data import get_model_catalog

logger = logging.getLogger(__name__)


class MatlabRAGRetriever:
    def __init__(self, index_path: str | None = None):
        self.index_path = index_path or os.path.join(
            os.path.dirname(__file__), "matlab_knowledge_index.json"
        )
        self.docs_dir = DEFAULT_DOCS_DIR
        self.catalog = get_model_catalog()
        self.model_by_id = {item["model_id"]: item for item in self.catalog}
        self._model_aliases = self._build_model_aliases()
        self.documents = self._load_documents()
        self._ensure_unique_doc_ids()
        self._doc_by_id = {int(d["id"]): d for d in self.documents}

        # BM25 index
        self._doc_tokens: List[List[str]] = []
        self._doc_term_freq: List[Dict[str, int]] = []
        self._doc_len: List[int] = []
        self._doc_freq: Dict[str, int] = {}
        self._avgdl = 0.0
        self._build_bm25_index()

        # Vector backend (lazy init)
        self._vector_initialized = False
        self._vector_ready = False
        self._vector_backend = "none"
        self._vector_error = ""
        self._embedding_model = None
        self._qdrant_client = None
        self._doc_embeddings: List[List[float]] | None = None

    def _load_documents(self) -> List[Dict[str, Any]]:
        catalog_docs = self._build_catalog_documents()
        file_docs = load_file_documents(self.docs_dir)

        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    docs = json.load(f)
                if isinstance(docs, list) and docs:
                    persisted_docs = [
                        doc
                        for doc in docs
                        if str(doc.get("payload", {}).get("type", "")).lower() != "document"
                    ]
                    return self._merge_documents(persisted_docs, file_docs, catalog_docs)
            except Exception:
                pass

        return self._merge_documents(file_docs, catalog_docs)

    def _build_model_aliases(self) -> Dict[str, List[str]]:
        aliases: Dict[str, List[str]] = {}
        for item in self.catalog:
            model_id = str(item.get("model_id", "")).strip()
            if not model_id:
                continue
            values = {model_id.lower(), str(item.get("name", "")).lower()}
            for kw in item.get("keywords", []):
                kw_text = str(kw).strip().lower()
                if kw_text:
                    values.add(kw_text)
            aliases[model_id] = sorted(v for v in values if len(v) >= 2)
        return aliases

    def _ensure_unique_doc_ids(self) -> None:
        seen: set[int] = set()
        for idx, doc in enumerate(self.documents):
            raw_id = doc.get("id")
            try:
                doc_id = int(raw_id)
            except Exception:
                doc_id = idx
            while doc_id in seen:
                doc_id += 100000
            seen.add(doc_id)
            doc["id"] = doc_id

    def _build_catalog_documents(self) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        for idx, item in enumerate(self.catalog):
            docs.append(
                {
                    "id": idx * 10,
                    "text": (
                        f"model_id: {item['model_id']}; name: {item['name']}; category: {item['category']}; "
                        f"description: {item['description']}; keywords: {', '.join(item.get('keywords', []))}"
                    ),
                    "payload": {
                        "type": "model",
                        "model_id": item["model_id"],
                        "name": item["name"],
                        "category": item["category"],
                        "description": item["description"],
                        "keywords": item.get("keywords", []),
                        "default_params": item.get("default_params", {}),
                    },
                }
            )
            for e_idx, example in enumerate(item.get("examples", []), start=1):
                docs.append(
                    {
                        "id": idx * 10 + e_idx,
                        "text": f"example: {example} -> model {item['model_id']}",
                        "payload": {
                            "type": "example",
                            "model_id": item["model_id"],
                            "example": example,
                        },
                    }
                )
        return docs

    def _merge_documents(self, *doc_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen_keys = set()

        def add_doc(doc: Dict[str, Any]) -> None:
            payload = doc.get("payload", {})
            key = (
                payload.get("type", ""),
                payload.get("model_id", ""),
                str(payload.get("example", "")),
                str(payload.get("description", "")),
                str(payload.get("source_file", "")),
                str(payload.get("chunk_index", "")),
                doc.get("text", ""),
            )
            if key in seen_keys:
                return
            seen_keys.add(key)
            merged.append(doc)

        for docs in doc_groups:
            for doc in docs:
                add_doc(doc)
        return merged

    def _build_bm25_index(self) -> None:
        doc_freq: Dict[str, int] = defaultdict(int)
        lengths: List[int] = []
        tokens_store: List[List[str]] = []
        tf_store: List[Dict[str, int]] = []

        for doc in self.documents:
            tokens = [t.lower() for t in _extract_terms(doc.get("text", ""))]
            if not tokens:
                tokens = ["__empty__"]
            tf = Counter(tokens)
            tokens_store.append(tokens)
            tf_store.append(dict(tf))
            lengths.append(len(tokens))
            for term in tf.keys():
                doc_freq[term] += 1

        self._doc_tokens = tokens_store
        self._doc_term_freq = tf_store
        self._doc_len = lengths
        self._doc_freq = dict(doc_freq)
        self._avgdl = (sum(lengths) / len(lengths)) if lengths else 1.0

    def _bm25_scores(self, query_terms: List[str]) -> Dict[int, float]:
        if not query_terms:
            return {}
        n_docs = len(self.documents)
        if n_docs == 0:
            return {}

        k1 = 1.5
        b = 0.75
        scores: Dict[int, float] = defaultdict(float)
        avgdl = self._avgdl or 1.0

        for term in [t.lower() for t in query_terms]:
            df = self._doc_freq.get(term, 0)
            if df == 0:
                continue
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            for idx, doc in enumerate(self.documents):
                tf = self._doc_term_freq[idx].get(term, 0)
                if tf <= 0:
                    continue
                dl = self._doc_len[idx]
                denom = tf + k1 * (1.0 - b + b * dl / avgdl)
                value = idf * (tf * (k1 + 1.0)) / max(1e-9, denom)
                scores[int(doc["id"])] += value

        return dict(scores)

    def _ensure_vector_backend(self) -> bool:
        if self._vector_initialized:
            return self._vector_ready
        self._vector_initialized = True

        backend = str(getattr(settings, "RETRIEVAL_VECTOR_BACKEND", "auto")).strip().lower()
        if backend in {"off", "none", "disable", "disabled"}:
            self._vector_backend = "none"
            self._vector_ready = False
            self._vector_error = "vector_backend_disabled"
            return False

        try:
            self._ensure_hf_cached_download_compat()
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            self._vector_backend = "none"
            self._vector_ready = False
            self._vector_error = f"embedding_init_failed: {exc}"
            logger.warning("Vector retrieval disabled: %s", self._vector_error)
            return False

        try:
            self._embedding_model = SentenceTransformer(
                settings.EMBEDDING_MODEL,
                device=settings.EMBEDDING_DEVICE,
            )
        except Exception as exc:
            self._vector_backend = "none"
            self._vector_ready = False
            self._vector_error = f"embedding_model_load_failed: {exc}"
            logger.warning("Vector retrieval disabled: %s", self._vector_error)
            return False

        if backend in {"auto", "qdrant"}:
            try:
                from qdrant_client import QdrantClient

                client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT, timeout=3)
                try:
                    client.get_collection(settings.QDRANT_COLLECTION)
                except Exception as get_exc:
                    # Some qdrant-client versions may fail to parse newer server response.
                    if not self._qdrant_collection_exists_http():
                        raise get_exc
                    logger.warning(
                        "Qdrant client/server schema mismatch detected, use REST compatibility mode: %s",
                        get_exc,
                    )
                    self._vector_error = f"qdrant_client_compat_mode: {get_exc}"
                self._qdrant_client = client
                self._vector_backend = "qdrant"
                self._vector_ready = True
                logger.info(
                    "Hybrid retriever vector backend enabled: qdrant(%s:%s/%s)",
                    settings.QDRANT_HOST,
                    settings.QDRANT_PORT,
                    settings.QDRANT_COLLECTION,
                )
                return True
            except Exception as exc:
                self._vector_error = f"qdrant_unavailable: {exc}"
                if backend == "qdrant":
                    self._vector_backend = "none"
                    self._vector_ready = False
                    logger.warning("Vector backend=qdrant required but unavailable: %s", exc)
                    return False

        # Local vector fallback
        try:
            self._prepare_local_doc_embeddings()
            self._vector_backend = "local"
            self._vector_ready = True
            logger.info("Hybrid retriever vector backend enabled: local")
            return True
        except Exception as exc:
            self._vector_backend = "none"
            self._vector_ready = False
            self._vector_error = f"local_vector_prepare_failed: {exc}"
            logger.warning("Vector retrieval disabled: %s", self._vector_error)
            return False

    def _prepare_local_doc_embeddings(self) -> None:
        if self._embedding_model is None:
            raise RuntimeError("embedding model is not initialized")
        if self._doc_embeddings is not None:
            return
        texts = [doc.get("text", "") for doc in self.documents]
        vectors = self._embedding_model.encode(texts, normalize_embeddings=True)
        self._doc_embeddings = [list(map(float, v)) for v in vectors]

    @staticmethod
    def _ensure_hf_cached_download_compat() -> None:
        """
        Compatibility shim:
        sentence-transformers<2.3 imports `cached_download` from huggingface_hub,
        but newer huggingface_hub removed this symbol.
        """
        try:
            import huggingface_hub  # type: ignore
        except Exception:
            return

        if hasattr(huggingface_hub, "cached_download"):
            return

        try:
            from huggingface_hub import hf_hub_download  # type: ignore
        except Exception:
            return

        def cached_download(
            url: str,
            cache_dir: str | None = None,
            force_filename: str | None = None,
            use_auth_token: str | None = None,
            token: str | None = None,
            local_files_only: bool = False,
            proxies: Dict[str, str] | None = None,
            **_: Any,
        ) -> str:
            target_cache = cache_dir or str(Path.home() / ".cache" / "huggingface" / "hub")
            os.makedirs(target_cache, exist_ok=True)

            parsed = urlparse(url)
            match = re.match(
                r"^(?P<repo>.+?)/resolve/(?P<rev>[^/]+)/(?P<file>.+)$",
                parsed.path.lstrip("/"),
            )
            if match:
                repo_id = match.group("repo")
                revision = match.group("rev")
                filename = match.group("file")
                downloaded = hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    revision=revision,
                    cache_dir=target_cache,
                    token=token or use_auth_token,
                    local_files_only=local_files_only,
                )
                if force_filename:
                    forced_path = os.path.join(target_cache, force_filename)
                    if not os.path.exists(forced_path):
                        with open(downloaded, "rb") as src, open(forced_path, "wb") as dst:
                            dst.write(src.read())
                    return forced_path
                return downloaded

            file_name = force_filename or os.path.basename(parsed.path) or "download.bin"
            local_path = os.path.join(target_cache, file_name)
            if os.path.exists(local_path):
                return local_path
            if local_files_only:
                raise FileNotFoundError(f"local_files_only=True and file not found: {local_path}")

            import requests

            headers = {}
            auth_token = token or use_auth_token
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"
            with requests.get(url, stream=True, timeout=120, proxies=proxies, headers=headers) as resp:
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            return local_path

        setattr(huggingface_hub, "cached_download", cached_download)

    def _vector_scores(self, query: str, top_n: int) -> Tuple[Dict[int, float], str]:
        if not self._ensure_vector_backend():
            return {}, "none"

        assert self._embedding_model is not None
        query_vec_raw = self._embedding_model.encode([query], normalize_embeddings=True)[0]
        query_vec = list(map(float, query_vec_raw))

        if self._vector_backend == "qdrant" and self._qdrant_client is not None:
            try:
                raw = self._vector_search_qdrant(query_vec, top_n)
                return _normalize_score_map(raw), "qdrant"
            except Exception as exc:
                self._vector_error = f"qdrant_search_failed: {exc}"
                logger.warning("Qdrant search failed, fallback local vector: %s", exc)
                self._prepare_local_doc_embeddings()
                raw = self._vector_search_local(query_vec, top_n)
                return _normalize_score_map(raw), "local"

        self._prepare_local_doc_embeddings()
        raw = self._vector_search_local(query_vec, top_n)
        return _normalize_score_map(raw), "local"

    def _vector_search_qdrant(self, query_vec: List[float], top_n: int) -> Dict[int, float]:
        assert self._qdrant_client is not None
        hits = None
        try:
            hits = self._qdrant_client.search(
                collection_name=settings.QDRANT_COLLECTION,
                query_vector=query_vec,
                limit=top_n,
                with_payload=True,
            )
        except Exception:
            try:
                points = self._qdrant_client.query_points(
                    collection_name=settings.QDRANT_COLLECTION,
                    query=query_vec,
                    limit=top_n,
                    with_payload=True,
                )
                hits = getattr(points, "points", points)
            except Exception:
                return self._vector_search_qdrant_http(query_vec, top_n)

        raw_scores: Dict[int, float] = {}
        for hit in hits or []:
            point_id = getattr(hit, "id", None)
            doc_id = _safe_to_int(point_id)
            if doc_id is None:
                payload = getattr(hit, "payload", {}) or {}
                doc_id = _safe_to_int(payload.get("id"))
            if doc_id is None or doc_id not in self._doc_by_id:
                continue
            raw_scores[doc_id] = float(getattr(hit, "score", 0.0))
        return raw_scores

    def _vector_search_qdrant_http(self, query_vec: List[float], top_n: int) -> Dict[int, float]:
        base_url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
        collection = settings.QDRANT_COLLECTION
        payload = {"vector": query_vec, "limit": top_n, "with_payload": True}
        endpoints = [
            f"{base_url}/collections/{collection}/points/search",
            f"{base_url}/collections/{collection}/points/query",
        ]

        last_error = ""
        for endpoint in endpoints:
            body = payload if endpoint.endswith("/search") else {
                "query": query_vec,
                "limit": top_n,
                "with_payload": True,
            }
            try:
                resp = requests.post(endpoint, json=body, timeout=8)
                if resp.status_code == 404:
                    last_error = f"404:{endpoint}"
                    continue
                resp.raise_for_status()
                data = resp.json()
                result = data.get("result", [])
                if isinstance(result, dict) and "points" in result:
                    result = result.get("points", [])
                raw_scores: Dict[int, float] = {}
                for hit in result or []:
                    doc_id = _safe_to_int(hit.get("id"))
                    if doc_id is None:
                        payload_obj = hit.get("payload", {}) or {}
                        doc_id = _safe_to_int(payload_obj.get("id"))
                    if doc_id is None or doc_id not in self._doc_by_id:
                        continue
                    raw_scores[doc_id] = float(hit.get("score", 0.0))
                return raw_scores
            except Exception as exc:
                last_error = str(exc)
                continue

        raise RuntimeError(f"qdrant_rest_search_failed: {last_error}")

    def _qdrant_collection_exists_http(self) -> bool:
        url = (
            f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
            f"/collections/{settings.QDRANT_COLLECTION}"
        )
        try:
            resp = requests.get(url, timeout=4)
            if resp.status_code == 200:
                return True
            return False
        except Exception:
            return False

    def _vector_search_local(self, query_vec: List[float], top_n: int) -> Dict[int, float]:
        if self._doc_embeddings is None:
            return {}
        scored: List[Tuple[int, float]] = []
        for idx, vec in enumerate(self._doc_embeddings):
            score = sum(float(a) * float(b) for a, b in zip(query_vec, vec))
            doc_id = int(self.documents[idx]["id"])
            scored.append((doc_id, float(score)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return dict(scored[:top_n])

    def retrieve(self, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
        text = (query or "").strip()
        if not text:
            return []
        query_terms = _extract_terms(text)
        if not query_terms:
            return self._fallback_docs(top_k)

        candidate_multiplier = max(2, int(getattr(settings, "RETRIEVAL_CANDIDATE_MULTIPLIER", 4)))
        candidate_k = max(top_k, top_k * candidate_multiplier)

        bm25_raw = self._bm25_scores(query_terms)
        bm25_norm = _normalize_score_map(bm25_raw)

        vector_norm, vector_backend = self._vector_scores(text, top_n=candidate_k)
        vector_enabled = bool(vector_norm)

        candidate_ids = set(_top_keys(bm25_norm, candidate_k))
        candidate_ids.update(_top_keys(vector_norm, candidate_k))
        if not candidate_ids:
            return self._fallback_docs(top_k)

        bm25_weight = float(getattr(settings, "RETRIEVAL_BM25_WEIGHT", 0.55))
        vector_weight = float(getattr(settings, "RETRIEVAL_VECTOR_WEIGHT", 0.45))
        if not vector_enabled:
            bm25_weight = 1.0
            vector_weight = 0.0
        total_w = max(1e-9, bm25_weight + vector_weight)
        bm25_weight /= total_w
        vector_weight /= total_w
        rerank_blend = min(0.9, max(0.0, float(getattr(settings, "RETRIEVAL_RERANK_BLEND", 0.35))))

        ranked: List[Dict[str, Any]] = []
        for doc_id in candidate_ids:
            doc = self._doc_by_id.get(doc_id)
            if not doc:
                continue
            bm25_s = bm25_norm.get(doc_id, 0.0)
            vec_s = vector_norm.get(doc_id, 0.0)
            fused = bm25_weight * bm25_s + vector_weight * vec_s
            rerank = self._rerank_score(text, query_terms, doc)
            final_norm = (1.0 - rerank_blend) * fused + rerank_blend * rerank
            final_score = final_norm * 20.0
            ranked.append(
                {
                    "score": round(final_score, 4),
                    "id": doc_id,
                    "text": doc.get("text", ""),
                    "payload": doc.get("payload", {}),
                    "score_detail": {
                        "bm25": round(bm25_s, 5),
                        "vector": round(vec_s, 5),
                        "fused": round(fused, 5),
                        "rerank": round(rerank, 5),
                        "backend": vector_backend,
                    },
                }
            )

        ranked.sort(key=lambda x: x["score"], reverse=True)
        if not ranked:
            return self._fallback_docs(top_k)
        return ranked[:top_k]

    def _fallback_docs(self, top_k: int) -> List[Dict[str, Any]]:
        fallback = self.documents[:top_k]
        return [
            {
                "score": 0.0,
                "id": item.get("id"),
                "text": item.get("text", ""),
                "payload": item.get("payload", {}),
                "score_detail": {
                    "bm25": 0.0,
                    "vector": 0.0,
                    "fused": 0.0,
                    "rerank": 0.0,
                    "backend": self._vector_backend,
                },
            }
            for item in fallback
        ]

    def _rerank_score(self, query: str, query_terms: List[str], doc: Dict[str, Any]) -> float:
        query_lower = query.lower()
        doc_text = doc.get("text", "")
        doc_lower = doc_text.lower()
        payload = doc.get("payload", {})

        # lexical overlap
        doc_terms = set(t.lower() for t in _extract_terms(doc_text))
        q_terms = [t.lower() for t in query_terms]
        overlap = 0.0
        if q_terms and doc_terms:
            overlap = len([t for t in set(q_terms) if t in doc_terms]) / max(1, len(set(q_terms)))

        # exact matches
        model_id = str(payload.get("model_id", "")).lower()
        model_match = 1.0 if model_id and model_id in query_lower else 0.0
        keyword_hit = 0.0
        for kw in payload.get("keywords", []):
            if str(kw).lower() in query_lower:
                keyword_hit += 1.0
        keyword_hit = min(1.0, keyword_hit / 3.0)

        alias_hit = 0.0
        raw_model_id = str(payload.get("model_id", ""))
        if raw_model_id:
            alias_list = self._model_aliases.get(raw_model_id, [])
            hits = 0
            for alias in alias_list:
                if alias in query_lower:
                    hits += 1
            alias_hit = min(1.0, hits / 2.0)

        example_bonus = 0.1 if payload.get("type") == "example" else 0.0
        phrase_bonus = 0.2 if query_lower in doc_lower else 0.0

        score = (
            0.3 * overlap
            + 0.2 * model_match
            + 0.25 * keyword_hit
            + 0.25 * alias_hit
            + phrase_bonus
            + example_bonus
        )
        return min(1.0, max(0.0, score))

    def infer_candidate_models(self, retrieved_docs: List[Dict[str, Any]], top_k: int = 3) -> List[Dict[str, Any]]:
        score_map: Dict[str, float] = defaultdict(float)
        for item in retrieved_docs:
            payload = item.get("payload", {})
            model_id = payload.get("model_id")
            if not model_id:
                continue
            score_map[model_id] += float(item.get("score", 0))

        if not score_map:
            return []

        ranked = sorted(score_map.items(), key=lambda x: x[1], reverse=True)[:top_k]
        results: List[Dict[str, Any]] = []
        for model_id, score in ranked:
            model = self.model_by_id.get(model_id, {})
            results.append(
                {
                    "model_id": model_id,
                    "score": round(score, 4),
                    "name": model.get("name", model_id),
                    "category": model.get("category", ""),
                    "description": model.get("description", ""),
                }
            )
        return results

    def get_model_defaults(self, model_id: str) -> Dict[str, Any]:
        return dict(self.model_by_id.get(model_id, {}).get("default_params", {}))

    def list_supported_models(self) -> List[Dict[str, Any]]:
        return self.catalog


def _extract_terms(text: str) -> List[str]:
    terms = re.findall(r"[A-Za-z_]+|[\u4e00-\u9fff]{1,4}|\d+(?:\.\d+)?", text)
    dedup: List[str] = []
    seen = set()
    for t in terms:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            dedup.append(t)
    return dedup


def _normalize_score_map(scores: Dict[int, float]) -> Dict[int, float]:
    if not scores:
        return {}
    values = list(scores.values())
    min_v = min(values)
    max_v = max(values)
    if abs(max_v - min_v) < 1e-12:
        return {k: 1.0 for k in scores}
    return {k: (v - min_v) / (max_v - min_v) for k, v in scores.items()}


def _top_keys(score_map: Dict[int, float], top_n: int) -> List[int]:
    return [k for k, _ in sorted(score_map.items(), key=lambda x: x[1], reverse=True)[:top_n]]


def _safe_to_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None
