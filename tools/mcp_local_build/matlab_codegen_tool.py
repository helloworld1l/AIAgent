"""MATLAB input materialization and code generation scaffolding."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from string import Template
from typing import Any, Dict, List

from tools.mcp_local_build.job_manager import BuildJobManager
from tools.mcp_local_build.process_utils import run_command
from tools.mcp_local_build.toolchains import ToolchainProbe


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


class MatlabCodegenTool:
    def __init__(self, job_manager: BuildJobManager, toolchains: ToolchainProbe) -> None:
        self.job_manager = job_manager
        self.toolchains = toolchains
        self.project_root = Path(__file__).resolve().parents[2]
        self.templates_dir = Path(__file__).resolve().parent / "templates"
        self.dry_run = _env_flag("LOCAL_BUILD_MCP_DRY_RUN", default=True)
        self.timeout_seconds = max(30, int(os.getenv("MCP_BUILD_TIMEOUT_MATLAB_SEC", "1200")))

    def materialize_inputs(
        self,
        job_id: str,
        matlab_file: str,
        entry_function: str,
        entry_args_schema: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        paths = self.job_manager.ensure_job_exists(job_id)
        matlab_source = self._resolve_allowed_input(matlab_file)
        if not matlab_source.exists() or not matlab_source.is_file():
            raise FileNotFoundError(f"MATLAB file not found: {matlab_source}")

        copied_source = paths.inputs_dir / matlab_source.name
        shutil.copy2(matlab_source, copied_source)

        request_payload = {
            "entry_function": entry_function,
            "entry_args_schema": entry_args_schema,
            "original_matlab_file": str(matlab_source),
            "copied_matlab_file": str(copied_source),
        }
        request_path = paths.inputs_dir / "build_request.json"
        request_path.write_text(json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        manifest = self.job_manager.update_manifest(
            job_id,
            {
                "status": "running",
                "input_manifest": request_payload,
                "source_model": str(copied_source),
            },
        )
        self.job_manager.append_step(
            job_id,
            step="materialize_inputs",
            status="completed",
            detail={
                "source_model": str(copied_source),
                "request_path": str(request_path),
            },
        )
        return {
            "status": "ok",
            "job_id": job_id,
            "workspace": str(paths.root),
            "source_model": str(copied_source),
            "request_path": str(request_path),
            "manifest_updated": manifest.get("updated_at", ""),
        }

    def matlab_generate_cpp(
        self,
        job_id: str,
        target_lang: str = "C++",
        matlab_codegen_mode: str = "matlab_coder",
        generate_report: bool = True,
    ) -> Dict[str, Any]:
        paths = self.job_manager.ensure_job_exists(job_id)
        manifest = self.job_manager.load_manifest(job_id)
        input_manifest = manifest.get("input_manifest", {})
        entry_function = str(input_manifest.get("entry_function", "")).strip()
        entry_args_schema = list(input_manifest.get("entry_args_schema", []))
        if not entry_function:
            raise ValueError("entry_function is missing; run materialize_inputs first")

        snapshot = self.toolchains.snapshot()
        self.job_manager.update_manifest(job_id, {"toolchain_snapshot": snapshot})
        matlab_path = snapshot.get("matlab", {}).get("path", "")
        if not matlab_path:
            self.job_manager.set_job_error(job_id, "toolchain_missing", "MATLAB executable not found")
            return {
                "status": "failed",
                "error_type": "toolchain_missing",
                "message": "MATLAB executable not found",
            }

        codegen_dir = paths.matlab_dir / "codegen"
        codegen_dir.mkdir(parents=True, exist_ok=True)
        runner_script = paths.matlab_dir / "matlab_codegen_runner.m"
        runner_script.write_text(
            self._render_runner_template(
                entry_function=entry_function,
                entry_args_schema=entry_args_schema,
                target_lang=target_lang,
                generate_report=generate_report,
                inputs_dir=paths.inputs_dir,
                work_dir=paths.matlab_dir,
            ),
            encoding="utf-8",
        )

        stdout_path = paths.matlab_dir / "matlab_stdout.log"
        stderr_path = paths.matlab_dir / "matlab_stderr.log"
        command = [matlab_path, "-batch", f"run('{self._escape_matlab_path(runner_script)}')"]
        command_path = paths.matlab_dir / "matlab_command.json"
        command_path.write_text(json.dumps({"command": command}, ensure_ascii=False, indent=2), encoding="utf-8")

        default_runtime_prefdir = (self.project_root / ".matlab_pref_for_build").resolve()
        configured_prefdir = str(os.getenv("MATLAB_PREFDIR", "")).strip()
        configured_prefdir_path = Path(configured_prefdir).expanduser().resolve() if configured_prefdir else None
        if configured_prefdir_path is not None and configured_prefdir_path != default_runtime_prefdir:
            matlab_prefdir = configured_prefdir_path
        else:
            matlab_prefdir = paths.root / ".matlab_pref"
        matlab_prefdir.mkdir(parents=True, exist_ok=True)
        command_env = dict(os.environ)
        command_env["MATLAB_PREFDIR"] = str(matlab_prefdir)

        detail = {
            "runner_script": str(runner_script),
            "target_lang": target_lang,
            "matlab_codegen_mode": matlab_codegen_mode,
            "generate_report": generate_report,
            "dry_run": self.dry_run,
            "matlab_prefdir": str(matlab_prefdir),
            "command": command,
            "codegen_dir": str(codegen_dir),
        }

        if self.dry_run:
            self.job_manager.append_step(job_id, "matlab_generate_cpp", "planned", detail)
            result = self.job_manager.load_result(job_id)
            result.update(
                {
                    "status": "running",
                    "logs": {**result.get("logs", {}), "matlab_command": str(command_path)},
                    "next_action_hint": "Disable LOCAL_BUILD_MCP_DRY_RUN to execute MATLAB code generation.",
                }
            )
            self.job_manager.write_result(job_id, result)
            return {
                "status": "planned",
                "job_id": job_id,
                "command": command,
                "runner_script": str(runner_script),
                "codegen_dir": str(codegen_dir),
            }

        completed = run_command(command, timeout=self.timeout_seconds, env=command_env)

        stdout_path.write_text(completed.stdout or "", encoding="utf-8-sig")
        stderr_path.write_text(completed.stderr or "", encoding="utf-8-sig")

        log_payload = {
            "matlab_stdout": str(stdout_path),
            "matlab_stderr": str(stderr_path),
            "matlab_command": str(command_path),
        }
        if completed.returncode != 0:
            error_message = (completed.stderr or completed.stdout or "MATLAB code generation failed").strip()
            self.job_manager.append_step(job_id, "matlab_generate_cpp", "failed", detail)
            self.job_manager.set_job_error(
                job_id,
                "matlab_codegen_failed",
                error_message,
                extra={"logs": log_payload},
            )
            return {
                "status": "failed",
                "error_type": "matlab_codegen_failed",
                "message": error_message,
                "logs": log_payload,
            }

        self.job_manager.append_step(job_id, "matlab_generate_cpp", "completed", detail)
        result = self.job_manager.load_result(job_id)
        result.update(
            {
                "status": "running",
                "logs": {**result.get("logs", {}), **log_payload},
                "codegen_dir": str(codegen_dir),
            }
        )
        self.job_manager.write_result(job_id, result)
        return {
            "status": "ok",
            "job_id": job_id,
            "codegen_dir": str(codegen_dir),
            "logs": log_payload,
        }

    def _resolve_allowed_input(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = (self.project_root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        allowed_roots = [self.project_root.resolve(), (self.project_root / "generated_models").resolve()]
        if not any(self._is_relative_to(candidate, root) for root in allowed_roots):
            raise ValueError(f"input path is outside allowed roots: {candidate}")
        return candidate

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _render_runner_template(
        self,
        entry_function: str,
        entry_args_schema: List[Dict[str, Any]],
        target_lang: str,
        generate_report: bool,
        inputs_dir: Path,
        work_dir: Path,
    ) -> str:
        template = Template((self.templates_dir / "matlab_codegen_runner.m.txt").read_text(encoding="utf-8"))
        args_literal = ", ".join(self._build_matlab_arg_literals(entry_args_schema))
        return template.substitute(
            entry_function=entry_function,
            target_lang=target_lang,
            generate_report="true" if generate_report else "false",
            args_literal=args_literal,
            inputs_dir=self._escape_matlab_path(inputs_dir),
            work_dir=self._escape_matlab_path(work_dir),
        )

    def _build_matlab_arg_literals(self, entry_args_schema: List[Dict[str, Any]]) -> List[str]:
        literals: List[str] = []
        for item in entry_args_schema:
            arg_type = str(item.get("type", "")).strip().lower()
            shape = list(item.get("shape", []))
            if arg_type in {"double_scalar", "scalar", "double"}:
                literals.append("1.0")
            elif arg_type in {"int_scalar", "int32_scalar"}:
                literals.append("int32(1)")
            elif arg_type in {"logical", "bool", "boolean"}:
                literals.append("false")
            elif arg_type in {"double_vector", "vector", "double_matrix", "matrix"}:
                rows = shape[0] if len(shape) >= 1 else 1
                cols = shape[1] if len(shape) >= 2 else 1
                literals.append(f"zeros({rows},{cols})")
            else:
                literals.append("coder.typeof(0)")
        return literals

    @staticmethod
    def _escape_matlab_path(path: Path) -> str:
        return str(path).replace("\\", "/").replace("'", "''")
