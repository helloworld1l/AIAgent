from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from config.settings import settings
from knowledge_base.web_evidence_retriever import WebEvidenceRetriever


class _MatchValue:
    def __init__(self, *, value: object) -> None:
        self.value = value


class _FieldCondition:
    def __init__(self, *, key: str, match: object) -> None:
        self.key = key
        self.match = match


class _Filter:
    def __init__(self, *, must: list[object]) -> None:
        self.must = must


class WebEvidenceRetrieverTest(unittest.TestCase):
    def test_retrieve_filters_by_session_id(self) -> None:
        with patch.object(settings, "WEB_RESEARCH_QDRANT_ENABLED", True, create=True), patch.object(
            settings,
            "WEB_RESEARCH_QDRANT_SCOPE",
            "session",
            create=True,
        ):
            retriever = WebEvidenceRetriever()

        retriever._ensure_backend = Mock(return_value=True)
        retriever.embedding_model = Mock()
        retriever.embedding_model.encode.return_value = [[0.1, 0.2]]
        retriever._qdrant_models = SimpleNamespace(
            MatchValue=_MatchValue,
            FieldCondition=_FieldCondition,
            Filter=_Filter,
        )
        retriever._search_points = Mock(return_value=[])

        retriever.retrieve(query="rocket thrust", session_id="session-1")

        query_filter = retriever._search_points.call_args.kwargs["query_filter"]
        session_conditions = [item for item in query_filter.must if getattr(item, "key", "") == "session_id"]
        self.assertEqual(len(session_conditions), 1)
        self.assertEqual(session_conditions[0].match.value, "session-1")

    def test_payload_to_doc_returns_agent_compatible_shape(self) -> None:
        retriever = WebEvidenceRetriever()
        doc = retriever._payload_to_doc(
            point_id=42,
            score=0.91234,
            payload={
                "title": "Rocket equation overview",
                "url": "https://example.com/rocket",
                "domain": "example.com",
                "saved_path": "generated_research/session-1/source.md",
                "session_id": "session-1",
                "scope": "session",
                "chunk_index": 1,
                "content_hash": "abc123",
                "text": "The rocket equation links mass ratio with achievable delta-v.",
            },
        )

        self.assertEqual(doc["id"], "web_qdrant_42")
        self.assertEqual(doc["payload"]["source"], "web_research_qdrant")
        self.assertEqual(doc["payload"]["url"], "https://example.com/rocket")
        self.assertIn("web_source:", doc["text"])

    def test_retrieve_skips_expired_points(self) -> None:
        with patch.object(settings, "WEB_RESEARCH_QDRANT_ENABLED", True, create=True):
            retriever = WebEvidenceRetriever()

        retriever._ensure_backend = Mock(return_value=True)
        retriever.embedding_model = Mock()
        retriever.embedding_model.encode.return_value = [[0.1, 0.2]]
        retriever._qdrant_models = SimpleNamespace(
            MatchValue=_MatchValue,
            FieldCondition=_FieldCondition,
            Filter=_Filter,
        )
        now_dt = datetime.now(timezone.utc)
        retriever._search_points = Mock(
            return_value=[
                SimpleNamespace(
                    id=1,
                    score=0.9,
                    payload={
                        "title": "Expired source",
                        "url": "https://example.com/expired",
                        "expires_at": (now_dt - timedelta(days=1)).isoformat(),
                        "text": "expired",
                    },
                ),
                SimpleNamespace(
                    id=2,
                    score=0.8,
                    payload={
                        "title": "Fresh source",
                        "url": "https://example.com/fresh",
                        "expires_at": (now_dt + timedelta(days=1)).isoformat(),
                        "text": "fresh",
                    },
                ),
            ]
        )

        docs = retriever.retrieve(query="rocket thrust", session_id="session-1")

        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["id"], "web_qdrant_2")


if __name__ == "__main__":
    unittest.main()
