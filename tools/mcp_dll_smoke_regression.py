"""One-command regression runner for the local MCP DLL smoke flow."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from tools.mcp_local_build.server import LocalBuildMCPServer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SMOKE_FILE = PROJECT_ROOT / "tools" / "mcp_local_build" / "smoke_assets" / "dll_smoke.m"
DEFAULT_PREFDIR = PROJECT_ROOT / ".matlab_pref_mcp_smoke"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the MCP DLL smoke regression end-to-end.")
    parser.add_argument("--profile", default="windows_msvc_dll", help="Build profile to probe and use.")
    parser.add_argument("--build-type", default="Release", help="CMake build type.")
    parser.add_argument("--target-lang", default="C", choices=["C", "C++"], help="MATLAB Coder target language.")
    parser.add_argument("--matlab-file", default=str(DEFAULT_SMOKE_FILE), help="MATLAB smoke source file.")
    parser.add_argument("--entry-function", default="dll_smoke", help="Smoke entry function name.")
    parser.add_argument("--artifact-name", default="dll_smoke", help="Generated DLL target name.")
    parser.add_argument("--project-name", default="dll_smoke_regression", help="Logical project name used for job creation.")
    parser.add_argument(
        "--matlab-prefdir",
        default=str(DEFAULT_PREFDIR),
        help="Isolated MATLAB_PREFDIR used for the regression; use --use-user-prefdir to disable.",
    )
    parser.add_argument(
        "--use-user-prefdir",
        action="store_true",
        help="Use the current user MATLAB preference directory instead of an isolated regression prefdir.",
    )
    parser.add_argument("--generate-report", action="store_true", help="Enable MATLAB Coder HTML report generation.")
    parser.add_argument("--json-only", action="store_true", help="Only print the final JSON summary.")
    return parser.parse_args()


def configure_environment(args: argparse.Namespace) -> str:
    os.environ["LOCAL_BUILD_MCP_DRY_RUN"] = "0"
    os.environ.setdefault("MCP_BUILD_TIMEOUT_MATLAB_SEC", "1200")
    os.environ.setdefault("MCP_BUILD_TIMEOUT_CONFIGURE_SEC", "300")
    os.environ.setdefault("MCP_BUILD_TIMEOUT_BUILD_SEC", "1200")

    if args.use_user_prefdir:
        os.environ.pop("MATLAB_PREFDIR", None)
        return ""

    prefdir = Path(args.matlab_prefdir).resolve()
    prefdir.mkdir(parents=True, exist_ok=True)
    os.environ["MATLAB_PREFDIR"] = str(prefdir)
    return str(prefdir)


def call_tool(
    server: LocalBuildMCPServer,
    tool_name: str,
    arguments: Dict[str, Any],
    steps: List[Dict[str, Any]],
    *,
    json_only: bool,
) -> Dict[str, Any]:
    payload = server.call_tool(tool_name, arguments)["structuredContent"]
    steps.append({"tool": tool_name, "arguments": arguments, "result": payload})

    if not json_only:
        status = str(payload.get("status", "ok"))
        marker = "ok" if status in {"ok", "succeeded", "created", "running"} else status
        print(f"[{marker}] {tool_name}")
        if payload.get("message"):
            print(f"  {payload['message']}")
        if payload.get("job_id"):
            print(f"  job_id={payload['job_id']}")
    return payload


def main() -> int:
    args = parse_args()
    prefdir = configure_environment(args)

    matlab_file = Path(args.matlab_file).resolve()
    if not matlab_file.exists():
        raise FileNotFoundError(f"MATLAB smoke file not found: {matlab_file}")

    server = LocalBuildMCPServer()
    steps: List[Dict[str, Any]] = []

    probe = call_tool(
        server,
        "probe_toolchains",
        {"profiles": [args.profile], "require_matlab": True},
        steps,
        json_only=args.json_only,
    )
    profile_result = next((item for item in probe.get("profiles", []) if item.get("resolved_profile") == args.profile or item.get("profile") == args.profile), {})
    if not profile_result.get("available"):
        summary = {
            "status": "failed",
            "reason": "toolchain_unavailable",
            "profile": args.profile,
            "probe": probe,
            "steps": steps,
            "matlab_prefdir": prefdir,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    created = call_tool(
        server,
        "create_build_job",
        {
            "project_name": args.project_name,
            "profile": args.profile,
            "build_type": args.build_type,
            "artifact_name": args.artifact_name,
        },
        steps,
        json_only=args.json_only,
    )
    job_id = str(created["job_id"])

    pipeline = [
        (
            "materialize_inputs",
            {
                "job_id": job_id,
                "matlab_file": str(matlab_file),
                "entry_function": args.entry_function,
                "entry_args_schema": [{"name": "x", "type": "double_scalar"}],
            },
        ),
        (
            "matlab_generate_cpp",
            {
                "job_id": job_id,
                "target_lang": args.target_lang,
                "matlab_codegen_mode": "matlab_coder",
                "generate_report": bool(args.generate_report),
            },
        ),
        (
            "cmake_configure",
            {
                "job_id": job_id,
                "build_type": args.build_type,
            },
        ),
        (
            "cmake_build_dynamic",
            {
                "job_id": job_id,
                "config": args.build_type,
            },
        ),
        (
            "inspect_artifacts",
            {
                "job_id": job_id,
            },
        ),
    ]

    failure: Dict[str, Any] | None = None
    for tool_name, arguments in pipeline:
        result = call_tool(server, tool_name, arguments, steps, json_only=args.json_only)
        if str(result.get("status", "")).lower() == "failed":
            failure = {"tool": tool_name, "result": result}
            break

    job_result = call_tool(server, "get_job_result", {"job_id": job_id}, steps, json_only=args.json_only)

    artifact_paths = list(job_result.get("artifact_paths", []))
    succeeded = str(job_result.get("status", "")).lower() == "succeeded" and bool(artifact_paths)
    summary = {
        "status": "succeeded" if succeeded else "failed",
        "job_id": job_id,
        "workspace": str(created.get("workspace", "")),
        "artifacts_dir": str(created.get("artifacts_dir", "")),
        "artifact_paths": artifact_paths,
        "header_paths": list(job_result.get("header_paths", [])),
        "logs": dict(job_result.get("logs", {})),
        "matlab_prefdir": prefdir,
        "matlab_file": str(matlab_file),
        "profile": args.profile,
        "failure": failure or {},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
