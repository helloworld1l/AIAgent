"""Toolchain detection helpers for the local build MCP server."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_DYNAMIC_PROFILES = ["windows_msvc_dll", "windows_gcc_dll", "linux_gcc_shared"]

PROFILE_ALIASES = {
    "windows_msvc_static": "windows_msvc_dll",
    "windows_gcc_static": "windows_gcc_dll",
    "linux_gcc_static": "linux_gcc_shared",
}


def normalize_profile_name(profile: str) -> str:
    return PROFILE_ALIASES.get(str(profile or "").strip(), str(profile or "").strip())


class ToolchainProbe:
    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[2]

    def probe(self, profiles: List[str], require_matlab: bool = True) -> Dict[str, Any]:
        snapshot = self.snapshot()
        profile_results = [self._probe_profile(profile, snapshot, require_matlab=require_matlab) for profile in profiles]
        missing = sorted({item for result in profile_results for item in result.get("missing", [])})
        recommended_profile = self._pick_recommended_profile(profile_results)
        return {
            "os": platform.platform(),
            "profiles": profile_results,
            "recommended_profile": recommended_profile,
            "missing": missing,
            "snapshot": snapshot,
        }

    def snapshot(self) -> Dict[str, Any]:
        matlab_exe = self._find_matlab_executable()
        cmake_exe = self._find_executable([os.getenv("CMAKE_EXE", "").strip(), "cmake", "cmake.exe"])
        vswhere_exe = self._find_vswhere_executable()
        visual_studio = self._detect_visual_studio(vswhere_exe)
        gcc_exe = self._find_executable(["gcc", "gcc.exe"])
        gpp_exe = self._find_executable(["g++", "g++.exe"])
        ar_exe = self._find_executable(["ar", "ar.exe"])

        return {
            "matlab": {
                "available": bool(matlab_exe),
                "path": matlab_exe or "",
            },
            "cmake": {
                "available": bool(cmake_exe),
                "path": cmake_exe or "",
                "version": self._read_version(cmake_exe, [cmake_exe, "--version"]) if cmake_exe else "",
            },
            "visual_studio": visual_studio,
            "gcc": {
                "available": bool(gcc_exe),
                "path": gcc_exe or "",
                "version": self._read_version(gcc_exe, [gcc_exe, "--version"]) if gcc_exe else "",
            },
            "gxx": {
                "available": bool(gpp_exe),
                "path": gpp_exe or "",
                "version": self._read_version(gpp_exe, [gpp_exe, "--version"]) if gpp_exe else "",
            },
            "ar": {
                "available": bool(ar_exe),
                "path": ar_exe or "",
            },
        }

    def _probe_profile(self, profile: str, snapshot: Dict[str, Any], require_matlab: bool) -> Dict[str, Any]:
        normalized_profile = normalize_profile_name(profile)
        missing: List[str] = []
        if require_matlab and not snapshot["matlab"]["available"]:
            missing.append("matlab")
        if not snapshot["cmake"]["available"]:
            missing.append("cmake")

        if normalized_profile == "windows_msvc_dll":
            if os.name != "nt":
                missing.append("windows")
            if not snapshot["visual_studio"]["available"]:
                missing.append("visual_studio")
        elif normalized_profile == "windows_gcc_dll":
            if os.name != "nt":
                missing.append("windows")
            if not snapshot["gcc"]["available"]:
                missing.append("gcc")
            if not snapshot["gxx"]["available"]:
                missing.append("g++")
        elif normalized_profile == "linux_gcc_shared":
            if os.name == "nt":
                missing.append("linux")
            if not snapshot["gcc"]["available"]:
                missing.append("gcc")
            if not snapshot["gxx"]["available"]:
                missing.append("g++")
        else:
            missing.append("unknown_profile")

        return {
            "profile": profile,
            "resolved_profile": normalized_profile,
            "available": not missing,
            "missing": missing,
        }

    @staticmethod
    def _pick_recommended_profile(profile_results: List[Dict[str, Any]]) -> str:
        for preferred in DEFAULT_DYNAMIC_PROFILES:
            for result in profile_results:
                resolved = normalize_profile_name(str(result.get("resolved_profile") or result.get("profile") or ""))
                if resolved == preferred and result.get("available"):
                    return str(result.get("profile") or preferred)
        return ""

    @staticmethod
    def _find_executable(candidates: List[str]) -> str | None:
        for candidate in candidates:
            if not candidate:
                continue
            candidate_path = Path(candidate).expanduser()
            if candidate_path.exists():
                return str(candidate_path.resolve())
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
        return None

    def _find_matlab_executable(self) -> str | None:
        candidates = [
            os.getenv("MATLAB_EXE", "").strip(),
            shutil.which("matlab"),
            shutil.which("matlab.exe"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return str(Path(candidate).resolve())

        for root in (Path("C:/Program Files/MATLAB"), Path("D:/Program Files/MATLAB")):
            if not root.exists():
                continue
            discovered = sorted(root.glob("*/bin/matlab.exe"), reverse=True)
            if discovered:
                return str(discovered[0].resolve())
        return None

    @staticmethod
    def _find_vswhere_executable() -> str | None:
        candidates = [
            os.getenv("VSWWHERE_EXE", "").strip(),
            r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe",
            r"C:\Program Files\Microsoft Visual Studio\Installer\vswhere.exe",
        ]
        return ToolchainProbe._find_executable(candidates)

    def _detect_visual_studio(self, vswhere_exe: str | None) -> Dict[str, Any]:
        cl_exe = self._find_executable(["cl.exe"])
        link_exe = self._find_executable(["link.exe"])
        lib_exe = self._find_executable(["lib.exe"])
        if cl_exe and link_exe:
            return {
                "available": True,
                "installation_path": "",
                "cl_path": cl_exe,
                "link_path": link_exe,
                "lib_path": lib_exe,
                "msbuild_path": self._find_executable(["MSBuild.exe"]),
                "vswhere_path": vswhere_exe or "",
            }

        if not vswhere_exe:
            return {
                "available": False,
                "installation_path": "",
                "cl_path": "",
                "link_path": "",
                "lib_path": "",
                "msbuild_path": "",
                "vswhere_path": "",
            }

        try:
            completed = subprocess.run(
                [
                    vswhere_exe,
                    "-latest",
                    "-products",
                    "*",
                    "-requires",
                    "Microsoft.Component.MSBuild",
                    "-property",
                    "installationPath",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            installation_path = (completed.stdout or "").strip()
        except Exception:
            installation_path = ""

        if not installation_path:
            return {
                "available": False,
                "installation_path": "",
                "cl_path": "",
                "link_path": "",
                "lib_path": "",
                "msbuild_path": "",
                "vswhere_path": vswhere_exe,
            }

        installation_root = Path(installation_path)
        cl_candidates = sorted(installation_root.glob("VC/Tools/MSVC/*/bin/Hostx64/x64/cl.exe"), reverse=True)
        link_candidates = sorted(installation_root.glob("VC/Tools/MSVC/*/bin/Hostx64/x64/link.exe"), reverse=True)
        lib_candidates = sorted(installation_root.glob("VC/Tools/MSVC/*/bin/Hostx64/x64/lib.exe"), reverse=True)
        msbuild_candidates = sorted(installation_root.glob("MSBuild/Current/Bin/MSBuild.exe"), reverse=True)

        return {
            "available": bool(cl_candidates and link_candidates),
            "installation_path": str(installation_root),
            "cl_path": str(cl_candidates[0]) if cl_candidates else "",
            "link_path": str(link_candidates[0]) if link_candidates else "",
            "lib_path": str(lib_candidates[0]) if lib_candidates else "",
            "msbuild_path": str(msbuild_candidates[0]) if msbuild_candidates else "",
            "vswhere_path": vswhere_exe,
        }

    @staticmethod
    def _read_version(executable: str | None, command: List[str]) -> str:
        if not executable:
            return ""
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=5)
            output = (completed.stdout or completed.stderr or "").strip().splitlines()
            return output[0].strip() if output else ""
        except Exception:
            return ""
