"""Regression tests for explicit web research in normal chat mode."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from agents.crm_agent import CRMAgent


class ChatWebResearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = CRMAgent.__new__(CRMAgent)
        self.agent.session_store = Mock()
        self.agent.session_store.backend_name = "memory"
        self.agent.session_store.get_state.return_value = None
        self.agent.session_store.get_history.return_value = []
        self.agent.session_store.count.return_value = 2

        self.agent.retriever = Mock()
        self.agent.retriever.retrieve.return_value = [{"id": "kb-1", "title": "local"}]

        self.agent.task_planner = Mock()
        self.agent.task_planner.plan.return_value = {
            "task_type": "chat",
            "confidence": 0.64,
            "wants_dynamic_library": False,
            "wants_web_research": False,
        }

        self.agent._has_generation_action = Mock(return_value=False)
        self.agent._is_generation_intent = Mock(return_value=False)
        self.agent._handle_dynamic_library_followup = Mock()
        self.agent._generate_chat_reply = Mock(return_value=("已结合联网结果回答。", False, ""))
        self.agent._perform_web_research = Mock(
            return_value={
                "status": "success",
                "bundle_dir": "generated_research/session-1",
                "summary_path": "generated_research/session-1/summary.md",
                "brief_path": "generated_research/session-1/brief.md",
                "sources": ["https://example.com/a", "https://example.com/b"],
                "docs": [{"id": "web-1", "title": "web"}],
            }
        )
        self.agent._retrieve_persisted_web_evidence = Mock(return_value=[])

    def test_chat_explicit_web_research_merges_research_docs(self) -> None:
        result = self.agent.chat(
            message="请给我最新的火箭推力参数概览",
            session_id="session-1",
            request_web_research=True,
        )

        self.agent._perform_web_research.assert_called_once_with(
            text="请给我最新的火箭推力参数概览",
            session_id="session-1",
        )

        retrieved_docs = self.agent._generate_chat_reply.call_args.kwargs["retrieved_docs"]
        self.assertEqual(retrieved_docs[0]["id"], "web-1")
        self.assertEqual(retrieved_docs[1]["id"], "kb-1")

        self.assertTrue(result["data"]["request_web_research"])
        self.assertEqual(result["data"]["web_research_status"], "success")
        self.assertEqual(result["data"]["web_research_bundle_dir"], "generated_research/session-1")
        self.assertEqual(result["data"]["web_research_summary_path"], "generated_research/session-1/summary.md")
        self.assertEqual(result["data"]["web_research_brief_path"], "generated_research/session-1/brief.md")
        self.assertEqual(
            result["data"]["web_research_sources"],
            ["https://example.com/a", "https://example.com/b"],
        )
        self.assertEqual(result["data"]["persisted_web_evidence_count"], 0)
        self.assertEqual(result["data"]["web_research_qdrant_index"], {})
        self.assertEqual(result["data"]["retrieved_knowledge"][0]["id"], "web-1")
        self.assertEqual(result["data"]["planner"]["wants_web_research"], True)

    def test_chat_explicit_web_research_merges_current_then_persisted_then_kb(self) -> None:
        self.agent._perform_web_research.return_value = {
            "status": "success",
            "bundle_dir": "generated_research/session-1",
            "summary_path": "generated_research/session-1/summary.md",
            "brief_path": "generated_research/session-1/brief.md",
            "sources": ["https://example.com/a"],
            "docs": [{"id": "web-now", "payload": {"url": "https://example.com/a"}}],
            "qdrant_index": {"status": "success", "points_upserted": 2},
        }
        self.agent._retrieve_persisted_web_evidence.return_value = [
            {"id": "web-old", "payload": {"url": "https://example.com/old"}}
        ]
        self.agent.retriever.retrieve.return_value = [{"id": "kb-1", "payload": {}}]

        result = self.agent.chat(
            message="请给我最新的火箭推力参数概览",
            session_id="session-1",
            request_web_research=True,
        )

        retrieved_docs = self.agent._generate_chat_reply.call_args.kwargs["retrieved_docs"]
        self.assertEqual([item["id"] for item in retrieved_docs[:3]], ["web-now", "web-old", "kb-1"])
        self.assertEqual(result["data"]["persisted_web_evidence_count"], 1)
        self.assertEqual(result["data"]["web_research_qdrant_index"]["status"], "success")


if __name__ == "__main__":
    unittest.main()
