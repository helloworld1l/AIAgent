from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from config.settings import settings
from tools.mcp_web_research.qdrant_indexer import WebResearchQdrantIndexer


class WebResearchQdrantIndexerTest(unittest.TestCase):
    def test_index_sources_returns_disabled_when_feature_off(self) -> None:
        with patch.object(settings, "WEB_RESEARCH_QDRANT_ENABLED", False, create=True):
            indexer = WebResearchQdrantIndexer()
            result = indexer.index_sources(query="rocket", session_id="session-1", fetched_sources=[])

        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["points_upserted"], 0)

    def test_build_point_id_is_stable_for_same_url_and_chunk(self) -> None:
        indexer = WebResearchQdrantIndexer()
        point_id_1 = indexer._build_point_id(
            url="https://example.com/a",
            content_hash="abc123",
            chunk_index=1,
        )
        point_id_2 = indexer._build_point_id(
            url="https://example.com/a",
            content_hash="abc123",
            chunk_index=1,
        )

        self.assertEqual(point_id_1, point_id_2)

    def test_index_sources_builds_expected_payload_fields(self) -> None:
        with patch.object(settings, "WEB_RESEARCH_QDRANT_ENABLED", True, create=True), patch.object(
            settings,
            "WEB_RESEARCH_QDRANT_MAX_CHUNK_CHARS",
            1000,
            create=True,
        ), patch.object(settings, "WEB_RESEARCH_QDRANT_CHUNK_OVERLAP", 120, create=True):
            indexer = WebResearchQdrantIndexer()

        indexer._ensure_backend = Mock(return_value=True)
        indexer.ensure_collection = Mock()
        indexer.cleanup_expired = Mock(return_value=0)
        indexer.client = Mock()
        indexer.embedding_model = Mock()
        indexer.embedding_model.encode.return_value = [[0.1, 0.2, 0.3]]
        indexer._qdrant_models = SimpleNamespace(PointStruct=lambda **kwargs: kwargs)

        result = indexer.index_sources(
            query="rocket thrust",
            session_id="session-1",
            fetched_sources=[
                {
                    "status": "success",
                    "title": "Rocket equation overview",
                    "url": "https://example.com/rocket",
                    "domain": "example.com",
                    "saved_path": "generated_research/session-1/source.md",
                    "text": "The rocket equation links mass ratio with achievable delta-v.",
                }
            ],
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["points_upserted"], 1)
        payload = indexer.client.upsert.call_args.kwargs["points"][0]["payload"]
        for key in (
            "source",
            "scope",
            "session_id",
            "query",
            "url",
            "saved_path",
            "chunk_index",
            "chunk_count",
            "content_hash",
            "fetched_at",
            "expires_at",
            "text",
        ):
            self.assertIn(key, payload)


if __name__ == "__main__":
    unittest.main()
