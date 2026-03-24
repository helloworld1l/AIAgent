from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from agents.dll_build_support import (
    extract_build_preferences,
    inspect_matlab_entrypoint,
    mentions_dynamic_library,
    references_previous_artifact,
    requests_dynamic_library_build,
)
from agents.tools import DynamicLibraryBuildTool


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_TMP_ROOT = PROJECT_ROOT / "tmp_test_codegen"


class DllBuildSupportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        TEST_TMP_ROOT.mkdir(parents=True, exist_ok=True)

    def test_dynamic_library_intent_detection(self) -> None:
        self.assertTrue(mentions_dynamic_library("帮我生成 DLL"))
        self.assertTrue(requests_dynamic_library_build("请把刚才那个模型编译成 DLL"))
        self.assertTrue(references_previous_artifact("把刚才那个编译成 DLL"))
        self.assertFalse(requests_dynamic_library_build("DLL 是什么"))

    def test_extract_build_preferences(self) -> None:
        preferences = extract_build_preferences("请用 C++ Debug 模式生成 msvc DLL")
        self.assertEqual(preferences["target_lang"], "C++")
        self.assertEqual(preferences["build_type"], "Debug")
        self.assertEqual(preferences["profile"], "windows_msvc_dll")
        self.assertFalse(preferences["generate_report"])

    def test_inspect_standard_matlab_entrypoint(self) -> None:
        matlab_source = """
function [y, f] = rocket_launch_1d(mode, time, Ts, x, u)
    state_dim = max(0, 3);
    input_dim = max(0, 2);
    y = zeros(2, 1);
    f = zeros(state_dim, 1);
end
""".strip()

        matlab_file = TEST_TMP_ROOT / f"rocket_launch_1d_{uuid4().hex[:8]}.m"
        try:
            matlab_file.write_text(matlab_source, encoding="utf-8")
            result = inspect_matlab_entrypoint(matlab_file)
        finally:
            matlab_file.unlink(missing_ok=True)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["entry_function"], "rocket_launch_1d")
        self.assertEqual(
            result["entry_args_schema"],
            [
                {"name": "mode", "type": "double_scalar"},
                {"name": "time", "type": "double_scalar"},
                {"name": "Ts", "type": "double_scalar"},
                {"name": "x", "type": "double_vector", "shape": [3, 1]},
                {"name": "u", "type": "double_vector", "shape": [2, 1]},
            ],
        )

    def test_inspect_script_returns_skipped(self) -> None:
        matlab_source = """
clear; clc;
disp('hello');
""".strip()

        matlab_file = TEST_TMP_ROOT / f"demo_script_{uuid4().hex[:8]}.m"
        try:
            matlab_file.write_text(matlab_source, encoding="utf-8")
            result = inspect_matlab_entrypoint(matlab_file)
        finally:
            matlab_file.unlink(missing_ok=True)

        self.assertEqual(result["status"], "skipped")
        self.assertFalse(result["is_function"])

    def test_inspect_allows_zero_length_input_vector(self) -> None:
        matlab_source = """
function [y, f] = satellite_orbit_2body(mode, time, Ts, x, u)
    state_dim = max(0, 4);
    input_dim = max(0, 0);
    y = zeros(3, 1);
    f = zeros(state_dim, 1);
end
""".strip()

        matlab_file = TEST_TMP_ROOT / f"satellite_orbit_2body_{uuid4().hex[:8]}.m"
        try:
            matlab_file.write_text(matlab_source, encoding="utf-8")
            result = inspect_matlab_entrypoint(matlab_file)
        finally:
            matlab_file.unlink(missing_ok=True)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["entry_function"], "satellite_orbit_2body")
        self.assertEqual(
            result["entry_args_schema"],
            [
                {"name": "mode", "type": "double_scalar"},
                {"name": "time", "type": "double_scalar"},
                {"name": "Ts", "type": "double_scalar"},
                {"name": "x", "type": "double_vector", "shape": [4, 1]},
                {"name": "u", "type": "double_vector", "shape": [0, 1]},
            ],
        )

    def test_dynamic_library_tool_accepts_zero_in_shape(self) -> None:
        tool = DynamicLibraryBuildTool()
        normalized = tool._normalize_entry_args_schema(
            [
                {"name": "x", "type": "double_vector", "shape": [4, 1]},
                {"name": "u", "type": "double_vector", "shape": [0, 1]},
            ]
        )

        self.assertEqual(
            normalized,
            [
                {"name": "x", "type": "double_vector", "shape": [4, 1]},
                {"name": "u", "type": "double_vector", "shape": [0, 1]},
            ],
        )


if __name__ == "__main__":
    unittest.main()
