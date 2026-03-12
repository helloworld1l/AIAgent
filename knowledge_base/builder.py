"""
Build knowledge base artifacts for MATLAB model generation.

Outputs:
1) Local JSON document index (always).
2) Optional Qdrant vector index (if dependencies and service are available).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from config.settings import settings
from knowledge_base.document_loader import DEFAULT_DOCS_DIR, load_file_documents
from knowledge_base.matlab_model_data import get_model_catalog

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class KnowledgeBaseBuilder:
    def __init__(self, enable_qdrant: bool = False):
        self.catalog = get_model_catalog()
        self.docs_dir = DEFAULT_DOCS_DIR
        self.local_index_path = os.path.join(
            os.path.dirname(__file__), "matlab_knowledge_index.json"
        )
        self.qdrant_enabled = False
        self.qdrant_requested = enable_qdrant
        self.client = None
        self.embedding_model = None
        self.embedding_dim = None
        self._qdrant_models = None

        if enable_qdrant:
            self._initialize_qdrant()

    def _initialize_qdrant(self) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qdrant_models

            self._ensure_hf_cached_download_compat()
            from sentence_transformers import SentenceTransformer

            self.client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
            self.embedding_model = SentenceTransformer(
                settings.EMBEDDING_MODEL,
                device=settings.EMBEDDING_DEVICE,
            )
            self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
            self._qdrant_models = qdrant_models
            self.qdrant_enabled = True
        except Exception as exc:
            logger.warning("Qdrant mode disabled: %s", exc)
            self.qdrant_enabled = False

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
            # Typical HF URL:
            # https://huggingface.co/<repo_id>/resolve/<revision>/<file_path>
            match = re.match(r"^(?P<repo>.+?)/resolve/(?P<rev>[^/]+)/(?P<file>.+)$", parsed.path.lstrip("/"))
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

            # Fallback for non-HF URL.
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
        logger.info("Patched huggingface_hub.cached_download compatibility shim.")

    def prepare_documents(self) -> List[Dict[str, Any]]:
        documents: List[Dict[str, Any]] = []
        for idx, item in enumerate(self.catalog):
            base = (
                f"model_id: {item['model_id']}; name: {item['name']}; category: {item['category']}; "
                f"description: {item['description']}; keywords: {', '.join(item.get('keywords', []))}"
            )
            documents.append(
                {
                    "id": idx * 10,
                    "text": base,
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
                documents.append(
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

        file_documents = load_file_documents(self.docs_dir)
        if file_documents:
            logger.info(
                "Loaded external document chunks: count=%s, docs_dir=%s",
                len(file_documents),
                self.docs_dir,
            )
            documents.extend(file_documents)
        return documents

    def build_local_index(self, documents: List[Dict[str, Any]]) -> str:
        with open(self.local_index_path, "w", encoding="utf-8") as f:
            json.dump(documents, f, ensure_ascii=False, indent=2)
        logger.info("Local knowledge index written: %s", self.local_index_path)
        return self.local_index_path

    def build_qdrant_index(self, documents: List[Dict[str, Any]]) -> int:
        if not self.qdrant_enabled:
            return 0

        assert self.client is not None
        assert self.embedding_model is not None
        assert self.embedding_dim is not None
        assert self._qdrant_models is not None

        collection = settings.QDRANT_COLLECTION
        try:
            self.client.delete_collection(collection)
        except Exception:
            pass

        self.client.create_collection(
            collection_name=collection,
            vectors_config=self._qdrant_models.VectorParams(
                size=self.embedding_dim,
                distance=self._qdrant_models.Distance.COSINE,
            ),
        )

        points = []
        for doc in documents:
            vector = self.embedding_model.encode(doc["text"]).tolist()
            points.append(
                self._qdrant_models.PointStruct(
                    id=doc["id"],
                    vector=vector,
                    payload={
                        "text": doc["text"],
                        **doc["payload"],
                    },
                )
            )

        self.client.upsert(collection_name=collection, points=points)
        logger.info("Qdrant index built. points=%s", len(points))
        return len(points)

    def build_knowledge_base(self) -> Dict[str, Any]:
        docs = self.prepare_documents()
        local_path = self.build_local_index(docs)
        qdrant_points = self.build_qdrant_index(docs)
        return {
            "documents": len(docs),
            "local_index": local_path,
            "qdrant_points": qdrant_points,
            "qdrant_enabled": self.qdrant_enabled,
            "qdrant_requested": self.qdrant_requested,
        }


def main(with_qdrant: bool = False):
    builder = KnowledgeBaseBuilder(enable_qdrant=with_qdrant)
    result = builder.build_knowledge_base()
    print(
        f"Knowledge base build finished. docs={result['documents']}, "
        f"qdrant_points={result['qdrant_points']}, "
        f"qdrant_enabled={result['qdrant_enabled']}, "
        f"local_index={result['local_index']}"
    )


if __name__ == "__main__":
    main()
