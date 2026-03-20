"""Artifact inspection helpers for local build MCP jobs."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

from tools.mcp_local_build.job_manager import BuildJobManager


class ArtifactInspector:
    def __init__(self, job_manager: BuildJobManager) -> None:
        self.job_manager = job_manager

    def inspect_artifacts(self, job_id: str) -> Dict[str, Any]:
        paths = self.job_manager.ensure_job_exists(job_id)
        manifest = self.job_manager.load_manifest(job_id)
        artifact_name = str(manifest.get("artifact_name", "")).strip()
        libraries = self._collect_libraries(paths.build_dir, artifact_name)
        copied_libraries = self._copy_libraries_to_artifacts(libraries, paths.artifacts_dir)
        headers = self._collect_headers(paths)

        result = self.job_manager.load_result(job_id)
        logs = dict(result.get("logs", {}))
        if copied_libraries:
            self.job_manager.append_step(
                job_id,
                "inspect_artifacts",
                "completed",
                {"artifact_paths": [str(path) for path in copied_libraries], "header_count": len(headers)},
            )
            self.job_manager.set_job_success(
                job_id,
                artifact_paths=[str(path) for path in copied_libraries],
                header_paths=[str(path) for path in headers],
                logs=logs,
            )
            return {
                "status": "ok",
                "job_id": job_id,
                "artifact_paths": [str(path) for path in copied_libraries],
                "header_paths": [str(path) for path in headers],
            }

        self.job_manager.append_step(job_id, "inspect_artifacts", "failed", {"artifact_name": artifact_name})
        self.job_manager.set_job_error(
            job_id,
            "artifact_missing",
            f"No dynamic library found for artifact '{artifact_name}'",
            extra={"header_paths": [str(path) for path in headers], "logs": logs},
        )
        return {
            "status": "failed",
            "error_type": "artifact_missing",
            "message": f"No dynamic library found for artifact '{artifact_name}'",
            "header_paths": [str(path) for path in headers],
        }

    def get_job_result(self, job_id: str) -> Dict[str, Any]:
        self.job_manager.ensure_job_exists(job_id)
        return self.job_manager.load_result(job_id)

    @staticmethod
    def _collect_libraries(build_dir: Path, artifact_name: str) -> List[Path]:
        if not build_dir.exists():
            return []
        matches: List[Path] = []
        for pattern in ("*.dll", "*.so", "*.dylib", "*.lib", "*.a"):
            for path in build_dir.rglob(pattern):
                if ArtifactInspector._matches_artifact_name(path, artifact_name):
                    matches.append(path)
        return sorted(set(matches))

    @staticmethod
    def _matches_artifact_name(path: Path, artifact_name: str) -> bool:
        if not artifact_name:
            return True
        normalized_name = path.name.lower()
        normalized_artifact = artifact_name.lower()
        candidates = {normalized_artifact, f"lib{normalized_artifact}"}
        return any(normalized_name == candidate or normalized_name.startswith(f"{candidate}.") for candidate in candidates)

    @staticmethod
    def _copy_libraries_to_artifacts(libraries: List[Path], artifacts_dir: Path) -> List[Path]:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        copied: List[Path] = []
        for library in libraries:
            destination = artifacts_dir / library.name
            if library.resolve() != destination.resolve():
                shutil.copy2(library, destination)
            copied.append(destination)
        return copied

    @staticmethod
    def _collect_headers(paths) -> List[Path]:
        headers: List[Path] = []
        for root in (paths.src_dir, paths.matlab_dir / "codegen"):
            if not root.exists():
                continue
            headers.extend(root.rglob("*.h"))
            headers.extend(root.rglob("*.hpp"))
        return sorted(set(headers))
