"""Mocked end-to-end tests for the chat API."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

import api.server as server


EXPECTED_TOP_LEVEL_KEYS = {"success", "message", "data"}
EXPECTED_MATLAB_DLL_DATA_KEYS = {
    "query_type",
    "session_id",
    "session_store_backend",
    "model_id",
    "model_name",
    "generated_file",
    "generated_file_path",
    "request_dynamic_library",
    "dll_build_status",
    "dll_artifact_paths",
    "dll_entry_function",
    "dll_entry_args_schema",
    "dll_build",
    "script",
    "static_validation",
    "smoke_validation",
    "parsed_params",
    "model_spec",
    "spec_build_source",
    "spec_used_llm",
    "spec_llm_error",
    "validation",
    "schema_validation",
    "repair_trace",
    "retrieved_knowledge",
    "used_legacy_fallback",
    "auto_repaired_by_llm",
    "auto_recovered_by_heuristic",
    "planner",
    "generation_match",
    "generation_ir",
    "generation_trace",
}


def _mock_matlab_generation_dll_result() -> dict:
    return {
        "message": "已生成 MATLAB 脚本并完成 DLL 构建。",
        "data": {
            "query_type": "matlab_generation_dll",
            "session_id": "session-e2e",
            "session_store_backend": "memory",
            "model_id": "rocket_launch_1d",
            "model_name": "一维火箭发射模型",
            "generated_file": "rocket_launch_1d.m",
            "generated_file_path": "generated_models/rocket_launch_1d.m",
            "request_dynamic_library": True,
            "dll_build_status": "success",
            "dll_artifact_paths": ["generated_builds/rocket_launch_1d.dll"],
            "dll_entry_function": "rocket_launch_1d",
            "dll_entry_args_schema": [
                {"name": "mode", "type": "double_scalar"},
                {"name": "time", "type": "double_scalar"},
            ],
            "dll_build": {"status": "success", "job_id": "job-e2e"},
            "script": "function y = rocket_launch_1d(mode, time)",
            "static_validation": {"valid": True, "issues": []},
            "smoke_validation": {"valid": True, "output": "ok"},
            "parsed_params": {"thrust": 10.0},
            "model_spec": {
                "model_name": "一维火箭发射模型",
                "parameters": {"thrust": 10.0},
            },
            "spec_build_source": "llm",
            "spec_used_llm": True,
            "spec_llm_error": "",
            "validation": {"valid": True},
            "schema_validation": {"valid": True},
            "repair_trace": [],
            "retrieved_knowledge": [{"id": "doc-1", "score": 0.92}],
            "used_legacy_fallback": False,
            "auto_repaired_by_llm": False,
            "auto_recovered_by_heuristic": False,
            "planner": {"task_type": "matlab_generation_dll", "confidence": 0.98},
            "generation_match": {"top_family": "rocket", "should_generate": True},
            "generation_ir": {"intent": "generate", "domain": "matlab"},
            "generation_trace": {"event": "generation_succeeded", "source": "crm_agent"},
        },
    }


class ChatApiE2ETest(unittest.TestCase):
    def test_api_chat_returns_matlab_generation_dll_payload_shape(self) -> None:
        mocked_result = _mock_matlab_generation_dll_result()
        mocked_agent = Mock()
        mocked_agent.chat.return_value = mocked_result

        with patch.object(server, "_ensure_agent", return_value=mocked_agent):
            with TestClient(server.app) as client:
                response = client.post(
                    "/api/chat",
                    json={
                        "message": "请生成一维火箭模型并编译成 DLL",
                        "user_id": "user-e2e",
                        "session_id": "session-e2e",
                    },
                )

        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertSetEqual(set(body.keys()), EXPECTED_TOP_LEVEL_KEYS)
        self.assertTrue(body["success"])
        self.assertEqual(body["message"], mocked_result["message"])

        data = body["data"]
        self.assertSetEqual(set(data.keys()), EXPECTED_MATLAB_DLL_DATA_KEYS)
        self.assertEqual(data["query_type"], "matlab_generation_dll")
        self.assertTrue(data["request_dynamic_library"])
        self.assertEqual(data["dll_build_status"], "success")
        self.assertIsInstance(data["dll_artifact_paths"], list)
        self.assertIsInstance(data["dll_entry_args_schema"], list)
        self.assertIsInstance(data["dll_build"], dict)
        self.assertIsInstance(data["model_spec"], dict)
        self.assertIsInstance(data["generation_trace"], dict)
        self.assertEqual(data, mocked_result["data"])

        mocked_agent.chat.assert_called_once_with(
            message="请生成一维火箭模型并编译成 DLL",
            user_id="user-e2e",
            session_id="session-e2e",
            request_web_research=False,
        )

    def test_api_chat_forwards_explicit_web_research_flag(self) -> None:
        mocked_result = _mock_matlab_generation_dll_result()
        mocked_agent = Mock()
        mocked_agent.chat.return_value = mocked_result

        with patch.object(server, "_ensure_agent", return_value=mocked_agent):
            with TestClient(server.app) as client:
                response = client.post(
                    "/api/chat",
                    json={
                        "message": "联网查询最新火箭参数",
                        "user_id": "user-e2e",
                        "session_id": "session-e2e",
                        "request_web_research": True,
                    },
                )

        self.assertEqual(response.status_code, 200)
        mocked_agent.chat.assert_called_once_with(
            message="联网查询最新火箭参数",
            user_id="user-e2e",
            session_id="session-e2e",
            request_web_research=True,
        )


if __name__ == "__main__":
    unittest.main()
