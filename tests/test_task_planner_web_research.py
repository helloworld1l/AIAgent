"""Regression tests for web research planning flags."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from agents.task_planner import RAGTaskPlanner


class TaskPlannerWebResearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = RAGTaskPlanner()

    def test_plan_marks_explicit_web_research_request(self) -> None:
        with patch.object(RAGTaskPlanner, "_llm_plan", return_value=(None, "")):
            plan = self.planner.plan(
                query="联网搜索火箭上升段空气阻力经验参数后生成 MATLAB 模型",
                retrieved_docs=[],
                recent_history=[],
            )

        self.assertTrue(plan["wants_web_research"])
        self.assertEqual(plan["task_type"], "matlab_generation")

    def test_plan_keeps_web_research_disabled_without_explicit_marker(self) -> None:
        with patch.object(RAGTaskPlanner, "_llm_plan", return_value=(None, "")):
            plan = self.planner.plan(
                query="生成一维火箭 MATLAB 模型，质量 1kg，仿真 10 秒",
                retrieved_docs=[],
                recent_history=[],
            )

        self.assertFalse(plan["wants_web_research"])


if __name__ == "__main__":
    unittest.main()

