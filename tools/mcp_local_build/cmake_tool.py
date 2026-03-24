"""CMake configure/build scaffolding for dynamic library generation."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from string import Template
from typing import Any, Dict, List

from tools.mcp_local_build.job_manager import BuildJobManager
from tools.mcp_local_build.process_utils import run_command
from tools.mcp_local_build.toolchains import ToolchainProbe, normalize_profile_name


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


class CMakeTool:
    def __init__(self, job_manager: BuildJobManager, toolchains: ToolchainProbe) -> None:
        self.job_manager = job_manager
        self.toolchains = toolchains
        self.templates_dir = Path(__file__).resolve().parent / "templates"
        self.dry_run = _env_flag("LOCAL_BUILD_MCP_DRY_RUN", default=True)
        self.configure_timeout = max(30, int(os.getenv("MCP_BUILD_TIMEOUT_CONFIGURE_SEC", "120")))
        self.build_timeout = max(30, int(os.getenv("MCP_BUILD_TIMEOUT_BUILD_SEC", "600")))

    def cmake_configure(
        self,
        job_id: str,
        generator: str = "",
        platform: str = "",
        build_type: str = "Release",
        extra_defines: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        paths = self.job_manager.ensure_job_exists(job_id)
        manifest = self.job_manager.load_manifest(job_id)
        snapshot = manifest.get("toolchain_snapshot") or self.toolchains.snapshot()
        self.job_manager.update_manifest(job_id, {"toolchain_snapshot": snapshot})

        cmake_path = snapshot.get("cmake", {}).get("path", "")
        if not cmake_path:
            self.job_manager.set_job_error(job_id, "toolchain_missing", "CMake executable not found")
            return {
                "status": "failed",
                "error_type": "toolchain_missing",
                "message": "CMake executable not found",
            }

        selected_generator, selected_platform = self._select_generator(
            profile=str(manifest.get("profile", "")),
            requested_generator=generator,
            requested_platform=platform,
        )
        source_files = self._collect_codegen_sources(paths)
        wrapper_files = self._ensure_wrapper_files(paths, manifest)

        if not source_files and not self.dry_run:
            self.job_manager.set_job_error(
                job_id,
                "cmake_configure_failed",
                "No generated C/C++ files found under matlab/codegen; run matlab_generate_cpp first",
            )
            return {
                "status": "failed",
                "error_type": "cmake_configure_failed",
                "message": "No generated C/C++ files found under matlab/codegen; run matlab_generate_cpp first",
            }

        cmakelists_path = paths.src_dir / "CMakeLists.txt"
        include_dirs = self._collect_include_dirs(paths, source_files, snapshot)

        cmakelists_path.write_text(
            self._render_cmakelists(
                project_name=str(manifest.get("project_name", "mcp_build_job")),
                artifact_name=str(manifest.get("artifact_name", "mcp_dynamic_lib")),
                source_files=source_files + wrapper_files,
                include_dirs=include_dirs,
                cpp_standard=17,
                compile_definitions=extra_defines or {},
            ),
            encoding="utf-8",
        )

        configure_log = paths.logs_dir / "cmake_configure.log"
        command = [cmake_path, "-S", str(paths.src_dir), "-B", str(paths.build_dir)]
        if selected_generator:
            command.extend(["-G", selected_generator])
        if selected_platform and selected_generator.lower().startswith("visual studio"):
            command.extend(["-A", selected_platform])
        command.extend([f"-DCMAKE_BUILD_TYPE={build_type}", "-DBUILD_SHARED_LIBS=ON"])
        for key, value in (extra_defines or {}).items():
            command.append(f"-D{key}={value}")

        detail = {
            "generator": selected_generator,
            "platform": selected_platform,
            "build_type": build_type,
            "dry_run": self.dry_run,
            "command": command,
            "cmakelists_path": str(cmakelists_path),
        }

        if self.dry_run:
            configure_log.write_text("DRY RUN\n" + " ".join(command), encoding="utf-8-sig")
            self.job_manager.append_step(job_id, "cmake_configure", "planned", detail)
            result = self.job_manager.load_result(job_id)
            result.update(
                {
                    "status": "running",
                    "logs": {**result.get("logs", {}), "configure": str(configure_log)},
                    "next_action_hint": "Disable LOCAL_BUILD_MCP_DRY_RUN to execute CMake configure.",
                }
            )
            self.job_manager.write_result(job_id, result)
            return {
                "status": "planned",
                "job_id": job_id,
                "command": command,
                "cmakelists_path": str(cmakelists_path),
            }

        completed = run_command(command, timeout=self.configure_timeout)
        configure_log.write_text((completed.stdout or "") + "\n" + (completed.stderr or ""), encoding="utf-8-sig")
        if completed.returncode != 0:
            error_message = (completed.stderr or completed.stdout or "CMake configure failed").strip()
            self.job_manager.append_step(job_id, "cmake_configure", "failed", detail)
            self.job_manager.set_job_error(
                job_id,
                "cmake_configure_failed",
                error_message,
                extra={"logs": {"configure": str(configure_log)}},
            )
            return {
                "status": "failed",
                "error_type": "cmake_configure_failed",
                "message": error_message,
                "logs": {"configure": str(configure_log)},
            }

        self.job_manager.append_step(job_id, "cmake_configure", "completed", detail)
        result = self.job_manager.load_result(job_id)
        result.update({"status": "running", "logs": {**result.get("logs", {}), "configure": str(configure_log)}})
        self.job_manager.write_result(job_id, result)
        return {
            "status": "ok",
            "job_id": job_id,
            "configure_log": str(configure_log),
            "cmakelists_path": str(cmakelists_path),
        }

    def cmake_build_dynamic(self, job_id: str, target: str = "", config: str = "Release") -> Dict[str, Any]:
        paths = self.job_manager.ensure_job_exists(job_id)
        manifest = self.job_manager.load_manifest(job_id)
        snapshot = manifest.get("toolchain_snapshot") or self.toolchains.snapshot()
        cmake_path = snapshot.get("cmake", {}).get("path", "")
        if not cmake_path:
            self.job_manager.set_job_error(job_id, "toolchain_missing", "CMake executable not found")
            return {
                "status": "failed",
                "error_type": "toolchain_missing",
                "message": "CMake executable not found",
            }

        selected_target = target or str(manifest.get("artifact_name", "")).strip()
        build_log = paths.logs_dir / "cmake_build.log"
        command = [cmake_path, "--build", str(paths.build_dir), "--config", config]
        if selected_target:
            command.extend(["--target", selected_target])

        detail = {
            "target": selected_target,
            "config": config,
            "dry_run": self.dry_run,
            "command": command,
        }

        if self.dry_run:
            build_log.write_text("DRY RUN\n" + " ".join(command), encoding="utf-8-sig")
            self.job_manager.append_step(job_id, "cmake_build_dynamic", "planned", detail)
            result = self.job_manager.load_result(job_id)
            result.update(
                {
                    "status": "running",
                    "logs": {**result.get("logs", {}), "build": str(build_log)},
                    "next_action_hint": "Disable LOCAL_BUILD_MCP_DRY_RUN to execute CMake build.",
                }
            )
            self.job_manager.write_result(job_id, result)
            return {
                "status": "planned",
                "job_id": job_id,
                "command": command,
            }

        completed = run_command(command, timeout=self.build_timeout)
        build_log.write_text((completed.stdout or "") + "\n" + (completed.stderr or ""), encoding="utf-8-sig")
        if completed.returncode != 0:
            error_message = (completed.stderr or completed.stdout or "CMake build failed").strip()
            self.job_manager.append_step(job_id, "cmake_build_dynamic", "failed", detail)
            self.job_manager.set_job_error(
                job_id,
                "compile_failed",
                error_message,
                extra={"logs": {"build": str(build_log)}},
            )
            return {
                "status": "failed",
                "error_type": "compile_failed",
                "message": error_message,
                "logs": {"build": str(build_log)},
            }

        self.job_manager.append_step(job_id, "cmake_build_dynamic", "completed", detail)
        result = self.job_manager.load_result(job_id)
        result.update({"status": "running", "logs": {**result.get("logs", {}), "build": str(build_log)}})
        self.job_manager.write_result(job_id, result)
        return {
            "status": "ok",
            "job_id": job_id,
            "build_log": str(build_log),
        }

    def cmake_build_static(self, job_id: str, target: str = "", config: str = "Release") -> Dict[str, Any]:
        return self.cmake_build_dynamic(job_id=job_id, target=target, config=config)

    def _select_generator(self, profile: str, requested_generator: str, requested_platform: str) -> tuple[str, str]:
        normalized_profile = normalize_profile_name(profile)
        if requested_generator:
            return requested_generator, requested_platform
        if normalized_profile == "windows_msvc_dll":
            return "Visual Studio 17 2022", requested_platform or "x64"
        if normalized_profile == "windows_gcc_dll":
            ninja = shutil.which("ninja") or shutil.which("ninja.exe")
            return ("Ninja", "") if ninja else ("MinGW Makefiles", "")
        return "Ninja", ""

    @staticmethod
    def _collect_codegen_sources(paths) -> List[Path]:
        codegen_dir = paths.matlab_dir / "codegen"
        if not codegen_dir.exists():
            return []
        source_files: List[Path] = []
        excluded_dirs = {"examples", "interface", "html"}
        for pattern in ("*.c", "*.cc", "*.cpp", "*.cxx"):
            for path in codegen_dir.rglob(pattern):
                normalized_parts = {part.lower() for part in path.parts}
                if excluded_dirs & normalized_parts:
                    continue
                source_files.append(path)
        return sorted(set(source_files))

    @staticmethod
    def _collect_include_dirs(paths, source_files: List[Path], snapshot: Dict[str, Any]) -> List[Path]:
        include_dirs = {paths.src_dir}
        include_dirs.update(path.parent for path in source_files)

        matlab_exe = str(snapshot.get("matlab", {}).get("path", "")).strip()
        if matlab_exe:
            matlab_root = Path(matlab_exe).resolve().parent.parent
            include_dirs.add(matlab_root / "extern" / "include")

        return sorted(include_dirs)

    def _ensure_wrapper_files(self, paths, manifest: Dict[str, Any]) -> List[Path]:
        header_path = paths.src_dir / "wrapper.h"
        source_path = paths.src_dir / "wrapper.cpp"
        artifact_name = str(manifest.get("artifact_name", "mcp_dynamic_lib")).strip() or "mcp_dynamic_lib"
        project_name = str(manifest.get("project_name", "mcp_build_job")).strip() or "mcp_build_job"

        header_path.write_text(
            "#pragma once\n"
            "const char* local_build_mcp_project_name();\n"
            "const char* local_build_mcp_artifact_name();\n",
            encoding="utf-8",
        )
        source_path.write_text(
            "#include \"wrapper.h\"\n\n"
            f"const char* local_build_mcp_project_name() {{ return \"{project_name}\"; }}\n"
            f"const char* local_build_mcp_artifact_name() {{ return \"{artifact_name}\"; }}\n",
            encoding="utf-8",
        )
        return [source_path]

    def _render_cmakelists(
        self,
        project_name: str,
        artifact_name: str,
        source_files: List[Path],
        include_dirs: List[Path],
        cpp_standard: int,
        compile_definitions: Dict[str, Any],
    ) -> str:
        template = Template((self.templates_dir / "CMakeLists.static.txt").read_text(encoding="utf-8"))
        source_lines = "\n".join(f'    "{self._cmake_path(path)}"' for path in source_files) or '    "wrapper.cpp"'
        include_lines = "\n".join(f'    "{self._cmake_path(path)}"' for path in include_dirs)
        if compile_definitions:
            definition_values = " ".join(f"{key}={value}" for key, value in compile_definitions.items())
            compile_block = f"target_compile_definitions({artifact_name} PRIVATE {definition_values})"
        else:
            compile_block = ""
        return template.substitute(
            project_name=project_name,
            artifact_name=artifact_name,
            source_lines=source_lines,
            include_lines=include_lines,
            cpp_standard=str(cpp_standard),
            compile_definitions_block=compile_block,
        )

    @staticmethod
    def _cmake_path(path: Path) -> str:
        return str(path).replace("\\", "/")
