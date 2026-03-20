"""Integration test for generating a MATLAB model and compiling it into a DLL."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from agents.tools import DynamicLibraryBuildTool
from knowledge_base.matlab_generator import MatlabModelGenerator
from tools.mcp_local_build.server import LocalBuildMCPServer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_DLL_PROFILES = ["windows_msvc_dll", "windows_gcc_dll"]


def _dump(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


class GeneratedModelDllBuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.name != "nt":
            raise unittest.SkipTest("DLL build validation only runs on Windows.")

        server = LocalBuildMCPServer()
        probe = server.call_tool(
            "probe_toolchains",
            {"profiles": WINDOWS_DLL_PROFILES, "require_matlab": True},
        )["structuredContent"]
        cls.toolchain_probe = probe
        cls.available_profile = next(
            (
                str(item.get("profile") or item.get("resolved_profile") or "").strip()
                for item in probe.get("profiles", [])
                if item.get("available")
            ),
            "",
        )
        if not cls.available_profile:
            raise unittest.SkipTest(
                "No Windows DLL toolchain with MATLAB is available for integration validation:\n"
                + _dump(probe)
            )

    def test_generate_model_then_build_dll(self) -> None:
        generator = MatlabModelGenerator()
        model_id = "rocket_launch_1d"
        entry_function = "rocket_launch_1d"
        params = generator.get_default_params(model_id)
        matlab_code = generator.render_script(model_id, params)
        static_validation = generator.static_validator.validate_script(matlab_code)

        self.assertTrue(
            static_validation.get("valid"),
            msg="Generated MATLAB model failed static validation:\n" + _dump(static_validation),
        )

        run_id = uuid4().hex[:8]
        output_dir = PROJECT_ROOT / "generated_models" / f"generated_model_dll_test_{run_id}"
        build_root = PROJECT_ROOT / "generated_builds" / f"generated_model_dll_test_{run_id}"
        matlab_prefdir = build_root / ".matlab_pref"

        output_dir.mkdir(parents=True, exist_ok=True)
        build_root.mkdir(parents=True, exist_ok=True)
        matlab_prefdir.mkdir(parents=True, exist_ok=True)

        file_name, file_path = generator.save_script(
            code=matlab_code,
            model_id=model_id,
            output_dir=str(output_dir),
        )

        self.assertEqual(file_name, f"{entry_function}.m")
        self.assertTrue(Path(file_path).exists(), msg=f"Generated MATLAB file not found: {file_path}")

        env_overrides = {
            "LOCAL_BUILD_MCP_DRY_RUN": "0",
            "LOCAL_BUILD_ROOT": str(build_root),
            "MATLAB_PREFDIR": str(matlab_prefdir),
            "MCP_BUILD_TIMEOUT_MATLAB_SEC": os.getenv("MCP_BUILD_TIMEOUT_MATLAB_SEC", "1200"),
            "MCP_BUILD_TIMEOUT_CONFIGURE_SEC": os.getenv("MCP_BUILD_TIMEOUT_CONFIGURE_SEC", "300"),
            "MCP_BUILD_TIMEOUT_BUILD_SEC": os.getenv("MCP_BUILD_TIMEOUT_BUILD_SEC", "1200"),
        }

        entry_args_schema = [
            {"name": "mode", "type": "double_scalar"},
            {"name": "time", "type": "double_scalar"},
            {"name": "Ts", "type": "double_scalar"},
            {"name": "x", "type": "double_vector", "shape": [3, 1]},
            {"name": "u", "type": "double_vector", "shape": [2, 1]},
        ]

        with patch.dict(os.environ, env_overrides, clear=False):
            build_tool = DynamicLibraryBuildTool()
            response = json.loads(
                build_tool._run(
                    matlab_file=file_path,
                    entry_function=entry_function,
                    entry_args_schema=entry_args_schema,
                    project_name="generated_model_dll_test",
                    artifact_name="rocket_launch_1d_dll_test",
                    profile=self.available_profile,
                    build_type="Release",
                    target_lang="C",
                    matlab_codegen_mode="matlab_coder",
                    generate_report=False,
                    require_matlab=True,
                )
            )

            self.assertEqual(
                response.get("status"),
                "success",
                msg="Dynamic library build pipeline failed:\n" + _dump(response),
            )
            self.assertFalse(response.get("planned_pipeline"), msg=_dump(response))
            self.assertTrue(response.get("job_id"), msg=_dump(response))

            job_result = response.get("job_result", {})
            self.assertEqual(
                job_result.get("status"),
                "succeeded",
                msg="Build job did not finish successfully:\n" + _dump(response),
            )

            artifact_paths = [Path(item) for item in job_result.get("artifact_paths", [])]
            dll_paths = [path for path in artifact_paths if path.suffix.lower() == ".dll"]

            self.assertTrue(artifact_paths, msg="No build artifacts were collected:\n" + _dump(response))
            self.assertTrue(dll_paths, msg="No DLL artifact was produced:\n" + _dump(response))
            for dll_path in dll_paths:
                self.assertTrue(dll_path.exists(), msg=f"DLL artifact missing on disk: {dll_path}")
                self.assertGreater(dll_path.stat().st_size, 0, msg=f"DLL artifact is empty: {dll_path}")

            pipeline_tools = [step.get("tool_name") for step in response.get("pipeline_steps", [])]
            self.assertEqual(
                pipeline_tools,
                [
                    "probe_toolchains",
                    "create_build_job",
                    "materialize_inputs",
                    "matlab_generate_cpp",
                    "cmake_configure",
                    "cmake_build_dynamic",
                    "inspect_artifacts",
                ],
                msg="Unexpected build pipeline steps:\n" + _dump(response),
            )


if __name__ == "__main__":
    unittest.main()
