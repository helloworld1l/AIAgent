"""Regression tests for pending generation IR state handling."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from agents.crm_agent import CLARIFY_STAGE_SLOT, PENDING_GENERATION_IR_STATE, CRMAgent


class PendingGenerationIRStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = CRMAgent.__new__(CRMAgent)

    def test_normalize_pending_generation_ir_removes_runtime_flag(self) -> None:
        state = {
            "generation_ir": {
                "task_goal": "生成一维火箭模型",
                "status": "needs_clarify",
            },
            "request_dynamic_library": True,
        }

        normalized = self.agent._normalize_pending_generation_ir(state)

        self.assertEqual(normalized["task_goal"], "生成一维火箭模型")
        self.assertEqual(normalized["clarify_stage"], CLARIFY_STAGE_SLOT)
        self.assertNotIn("request_dynamic_library", normalized)
        self.assertTrue(
            self.agent._extract_pending_generation_ir_request_dynamic_library(state)
        )

        legacy_state = {
            "task_goal": "生成一维火箭模型",
            "request_dynamic_library": True,
        }
        normalized_legacy = self.agent._normalize_pending_generation_ir(legacy_state)
        self.assertNotIn("request_dynamic_library", normalized_legacy)

    def test_set_pending_generation_ir_stores_runtime_flag_outside_ir(self) -> None:
        self.agent.session_store = Mock()
        generation_ir = {
            "task_goal": "生成一维火箭模型",
            "clarify_stage": CLARIFY_STAGE_SLOT,
        }

        self.agent._set_pending_generation_ir(
            "session-1",
            generation_ir,
            request_dynamic_library=True,
        )

        self.agent.session_store.set_state.assert_called_once_with(
            "session-1",
            PENDING_GENERATION_IR_STATE,
            {
                "generation_ir": generation_ir,
                "request_dynamic_library": True,
            },
        )

    def test_resume_pending_generation_ir_keeps_runtime_flag_outside_ir(self) -> None:
        self.agent.structured_ir = Mock()
        self.agent.retriever = Mock()
        self.agent._handle_generation_intent = Mock(
            return_value={"message": "ok", "data": {"request_dynamic_library": True}}
        )
        self.agent._handle_generation_clarify = Mock()

        updated_ir = {
            "task_goal": "生成一维火箭模型",
            "missing_info": [],
        }
        self.agent.structured_ir.continue_collection.return_value = updated_ir
        self.agent.structured_ir.should_clarify.return_value = False
        self.agent.structured_ir.to_model_spec.return_value = {"model_id": "rocket_launch_1d"}
        self.agent.retriever.retrieve.return_value = []
        self.agent.retriever.assess_generation_match.return_value = {"top_family": "rocket"}

        pending_state = {
            "generation_ir": {
                "task_goal": "生成一维火箭模型",
                "clarify_stage": CLARIFY_STAGE_SLOT,
            },
            "request_dynamic_library": True,
        }

        self.agent._resume_pending_generation_ir(
            "补充参数：质量=1kg",
            "session-1",
            pending_state,
        )

        continued_ir = self.agent.structured_ir.continue_collection.call_args.args[0]
        normalized_for_codegen = self.agent.structured_ir.to_model_spec.call_args.args[0]
        _, handle_kwargs = self.agent._handle_generation_intent.call_args

        self.assertNotIn("request_dynamic_library", continued_ir)
        self.assertNotIn("request_dynamic_library", normalized_for_codegen)
        self.assertEqual(handle_kwargs["generation_ir"], updated_ir)
        self.assertTrue(handle_kwargs["request_dynamic_library"])


if __name__ == "__main__":
    unittest.main()
