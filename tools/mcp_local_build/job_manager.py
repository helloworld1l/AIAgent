"""Job workspace management for the local build MCP server."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _slugify(value: str, fallback: str = "build_job") -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", (value or "").strip())
    normalized = normalized.strip("_-")
    return normalized or fallback


@dataclass(frozen=True)
class JobPaths:
    root: Path
    inputs_dir: Path
    matlab_dir: Path
    src_dir: Path
    build_dir: Path
    artifacts_dir: Path
    logs_dir: Path
    manifest_path: Path
    result_path: Path


class BuildJobManager:
    def __init__(self, build_root: str | None = None) -> None:
        self.project_root = Path(__file__).resolve().parents[2]
        configured_root = (build_root or os.getenv("LOCAL_BUILD_ROOT", "generated_builds")).strip()
        root_path = Path(configured_root)
        if not root_path.is_absolute():
            root_path = self.project_root / root_path
        self.build_root = root_path.resolve()
        self.build_root.mkdir(parents=True, exist_ok=True)

    def create_job(
        self,
        project_name: str,
        profile: str,
        build_type: str,
        artifact_name: str,
    ) -> Dict[str, Any]:
        job_id = self._generate_job_id(project_name)
        paths = self.get_job_paths(job_id)
        self._ensure_job_dirs(paths)

        manifest = {
            "job_id": job_id,
            "status": "created",
            "project_name": project_name,
            "artifact_name": artifact_name,
            "profile": profile,
            "build_type": build_type,
            "workspace": str(paths.root),
            "artifacts_dir": str(paths.artifacts_dir),
            "created_at": _utc_now_iso(),
            "updated_at": _utc_now_iso(),
            "steps": [],
            "input_manifest": {},
            "toolchain_snapshot": {},
            "artifacts": [],
            "logs": {},
            "error_summary": "",
        }
        self.write_manifest(job_id, manifest)
        self.write_result(
            job_id,
            {
                "status": "created",
                "artifact_paths": [],
                "header_paths": [],
                "logs": {},
                "error_summary": "",
            },
        )
        return manifest

    def get_job_paths(self, job_id: str) -> JobPaths:
        root = self.build_root / job_id
        return JobPaths(
            root=root,
            inputs_dir=root / "inputs",
            matlab_dir=root / "matlab",
            src_dir=root / "src",
            build_dir=root / "build",
            artifacts_dir=root / "artifacts",
            logs_dir=root / "logs",
            manifest_path=root / "manifest.json",
            result_path=root / "result.json",
        )

    def load_manifest(self, job_id: str) -> Dict[str, Any]:
        return self._read_json(self.get_job_paths(job_id).manifest_path)

    def write_manifest(self, job_id: str, payload: Dict[str, Any]) -> None:
        payload["updated_at"] = _utc_now_iso()
        self._write_json(self.get_job_paths(job_id).manifest_path, payload)

    def update_manifest(self, job_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        manifest = self.load_manifest(job_id)
        manifest.update(updates)
        self.write_manifest(job_id, manifest)
        return manifest

    def append_step(self, job_id: str, step: str, status: str, detail: Dict[str, Any] | None = None) -> Dict[str, Any]:
        manifest = self.load_manifest(job_id)
        steps = list(manifest.get("steps", []))
        steps.append(
            {
                "step": step,
                "status": status,
                "detail": detail or {},
                "timestamp": _utc_now_iso(),
            }
        )
        manifest["steps"] = steps
        self.write_manifest(job_id, manifest)
        return manifest

    def load_result(self, job_id: str) -> Dict[str, Any]:
        return self._read_json(self.get_job_paths(job_id).result_path)

    def write_result(self, job_id: str, payload: Dict[str, Any]) -> None:
        payload["updated_at"] = _utc_now_iso()
        self._write_json(self.get_job_paths(job_id).result_path, payload)

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        manifest = self.load_manifest(job_id)
        result = self.load_result(job_id)
        return {
            "job_id": job_id,
            "status": manifest.get("status", "unknown"),
            "profile": manifest.get("profile", ""),
            "artifact_name": manifest.get("artifact_name", ""),
            "workspace": manifest.get("workspace", ""),
            "updated_at": manifest.get("updated_at", ""),
            "steps": manifest.get("steps", []),
            "error_summary": result.get("error_summary", ""),
        }

    def set_job_error(self, job_id: str, error_type: str, message: str, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
        manifest = self.update_manifest(
            job_id,
            {
                "status": "failed",
                "error_summary": message,
                "error_type": error_type,
            },
        )
        result = self.load_result(job_id)
        result.update(
            {
                "status": "failed",
                "error_type": error_type,
                "error_summary": message,
            }
        )
        if extra:
            result.update(extra)
        self.write_result(job_id, result)
        return {"manifest": manifest, "result": result}

    def set_job_success(self, job_id: str, artifact_paths: list[str], header_paths: list[str], logs: Dict[str, str]) -> Dict[str, Any]:
        manifest = self.update_manifest(
            job_id,
            {
                "status": "succeeded",
                "artifacts": artifact_paths,
                "logs": logs,
                "error_type": "",
                "error_summary": "",
            },
        )
        result = self.load_result(job_id)
        result.update(
            {
                "status": "succeeded",
                "artifact_paths": artifact_paths,
                "header_paths": header_paths,
                "logs": logs,
                "error_type": "",
                "error_summary": "",
            }
        )
        self.write_result(job_id, result)
        return {"manifest": manifest, "result": result}

    def ensure_job_exists(self, job_id: str) -> JobPaths:
        paths = self.get_job_paths(job_id)
        if not paths.manifest_path.exists():
            raise FileNotFoundError(f"unknown build job: {job_id}")
        return paths

    def _generate_job_id(self, project_name: str) -> str:
        prefix = _slugify(project_name, fallback="build_job")
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"{stamp}_{prefix}_{uuid4().hex[:8]}"

    @staticmethod
    def _ensure_job_dirs(paths: JobPaths) -> None:
        for directory in (
            paths.root,
            paths.inputs_dir,
            paths.matlab_dir,
            paths.src_dir,
            paths.build_dir,
            paths.artifacts_dir,
            paths.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
