"""MATLAB/Octave syntax smoke testing for generated .m files."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


_RUNNER_UNAVAILABLE_CACHE: Dict[str, str] = {}


def _env_flag(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "")).strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _escape_matlab_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace("'", "''")


class MatlabSyntaxSmokeTester:
    def __init__(self) -> None:
        self.timeout_seconds = max(5, int(os.getenv("MATLAB_SMOKE_TIMEOUT_SEC", "45")))
        self.require_runner = _env_flag("MATLAB_SMOKE_REQUIRED", default=False)
        self.preferred_runner = str(os.getenv("MATLAB_SMOKE_PREFERRED", "matlab")).strip().lower()
        self.explicit_runner = str(os.getenv("MATLAB_SMOKE_RUNNER", "")).strip()

    def validate_file(self, file_path: str) -> Dict[str, Any]:
        raw_file_path = str(file_path or "").strip()
        if not raw_file_path:
            return {
                "status": "failed",
                "valid": False,
                "message": "smoke target path is empty",
                "errors": ["smoke target path is empty"],
                "warnings": [],
                "issues": [],
                "file_path": raw_file_path,
            }

        target_path = Path(raw_file_path).expanduser().resolve()
        if not target_path.exists() or not target_path.is_file():
            return {
                "status": "failed",
                "valid": False,
                "message": f"smoke target does not exist: {target_path}",
                "errors": [f"smoke target does not exist: {target_path}"],
                "warnings": [],
                "issues": [],
                "file_path": str(target_path),
            }

        runner = self._detect_runner()
        if runner is None:
            message = "MATLAB/Octave runner not found; smoke test skipped"
            status = "failed" if self.require_runner else "skipped"
            return {
                "status": status,
                "valid": False if self.require_runner else None,
                "message": message,
                "errors": [message] if self.require_runner else [],
                "warnings": [] if self.require_runner else [message],
                "issues": [],
                "file_path": str(target_path),
            }

        cached_unavailable = _RUNNER_UNAVAILABLE_CACHE.get(runner["path"])
        if cached_unavailable and not self.require_runner:
            return self._build_skipped_result(
                message=cached_unavailable,
                runner=runner,
                target_path=target_path,
                mode="cached_unavailable",
            )

        if runner["kind"] == "matlab":
            return self._run_matlab_checkcode(target_path, runner)
        return self._run_octave_source(target_path, runner)

    def _detect_runner(self) -> Optional[Dict[str, str]]:
        if self.explicit_runner:
            explicit_path = Path(self.explicit_runner).expanduser()
            if explicit_path.exists():
                kind = "octave" if "octave" in explicit_path.name.lower() else "matlab"
                return {"kind": kind, "path": str(explicit_path.resolve())}
            resolved = shutil.which(self.explicit_runner)
            if resolved:
                kind = "octave" if "octave" in Path(resolved).name.lower() else "matlab"
                return {"kind": kind, "path": resolved}

        runner_order = ["matlab", "octave"] if self.preferred_runner != "octave" else ["octave", "matlab"]
        for runner_kind in runner_order:
            if runner_kind == "matlab":
                matlab_path = self._find_matlab_executable()
                if matlab_path:
                    return {"kind": "matlab", "path": matlab_path}
            else:
                octave_path = self._find_octave_executable()
                if octave_path:
                    return {"kind": "octave", "path": octave_path}
        return None

    def _find_matlab_executable(self) -> Optional[str]:
        candidates = [
            os.getenv("MATLAB_EXE", ""),
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
    def _find_octave_executable() -> Optional[str]:
        for name in ("octave-cli", "octave-cli.exe", "octave", "octave.exe"):
            resolved = shutil.which(name)
            if resolved:
                return resolved
        return None

    def _run_matlab_checkcode(self, target_path: Path, runner: Dict[str, str]) -> Dict[str, Any]:
        runner_script = None
        try:
            runner_script = self._write_matlab_runner_script(target_path)
            command = [runner["path"], "-batch", f"run('{_escape_matlab_path(runner_script)}')"]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            message = f"MATLAB syntax smoke timed out after {self.timeout_seconds}s"
            self._mark_runner_unavailable(runner, message)
            if not self.require_runner:
                return self._build_skipped_result(
                    message=message,
                    runner=runner,
                    target_path=target_path,
                    mode="checkcode",
                )
            return {
                "status": "failed",
                "valid": False,
                "message": message,
                "errors": [message],
                "warnings": [],
                "issues": [],
                "runner": "matlab",
                "runner_path": runner["path"],
                "mode": "checkcode",
                "file_path": str(target_path),
            }
        finally:
            if runner_script and runner_script.exists():
                runner_script.unlink(missing_ok=True)

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        issues = self._parse_matlab_issue_lines(stdout + "\n" + stderr)

        if completed.returncode == 0:
            return {
                "status": "passed",
                "valid": True,
                "message": "MATLAB syntax smoke passed",
                "errors": [],
                "warnings": [],
                "issues": [],
                "runner": "matlab",
                "runner_path": runner["path"],
                "mode": "checkcode",
                "returncode": completed.returncode,
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "file_path": str(target_path),
            }

        errors = [
            f"{issue['id']} at line {issue['line']}: {issue['message']}"
            for issue in issues
        ]
        if not errors:
            raw_output = "\n".join(part for part in [stdout.strip(), stderr.strip()] if part).strip()
            if self._is_runner_environment_error(raw_output):
                message = raw_output or "MATLAB runner startup failed; smoke test skipped"
                self._mark_runner_unavailable(runner, message)
                if not self.require_runner:
                    return self._build_skipped_result(
                        message=message,
                        runner=runner,
                        target_path=target_path,
                        mode="checkcode",
                        stdout=stdout,
                        stderr=stderr,
                    )
            errors = [raw_output or "MATLAB syntax smoke failed"]
        return {
            "status": "failed",
            "valid": False,
            "message": errors[0],
            "errors": errors,
            "warnings": [],
            "issues": issues,
            "runner": "matlab",
            "runner_path": runner["path"],
            "mode": "checkcode",
            "returncode": completed.returncode,
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "file_path": str(target_path),
        }

    def _write_matlab_runner_script(self, target_path: Path) -> Path:
        target_literal = _escape_matlab_path(target_path)
        script_body = f"""target = '{target_literal}';
exit_code = 0;
try
    issues = checkcode(target, '-id');
    blocking_count = 0;
    for k = 1:numel(issues)
        issue = issues(k);
        if is_blocking_issue(issue.id, issue.message)
            blocking_count = blocking_count + 1;
            clean_message = regexprep(char(issue.message), '[\\r\\n]+', ' ');
            clean_message = strrep(clean_message, '|', '/');
            fprintf('MATLAB_SMOKE_ISSUE|%s|%d|%s\\n', char(issue.id), double(issue.line), clean_message);
        end
    end
    if blocking_count == 0
        fprintf('MATLAB_SMOKE_OK\\n');
    else
        exit_code = 1;
    end
catch ME
    exit_code = 1;
    report = regexprep(getReport(ME, 'extended', 'hyperlinks', 'off'), '[\\r\\n]+', ' ');
    report = strrep(report, '|', '/');
    fprintf('MATLAB_SMOKE_FATAL|%s\\n', report);
end
exit(exit_code);

function flag = is_blocking_issue(issue_id, issue_message)
    id_text = upper(char(issue_id));
    message_text = char(issue_message);
    if startsWith(id_text, 'ENDCT')
        flag = true;
        return;
    end
    syntax_ids = {{'SYNER', 'NOPAR', 'NOBRA'}};
    if any(strcmp(id_text, syntax_ids))
        flag = true;
        return;
    end
    flag = ~isempty(regexpi(message_text, 'syntax|parse error|missing\\s+end|unexpected\\s+end|missing\\s+\\)|missing\\s+\\]|解析错误|语法|缺少一个 END|缺少结束|无效', 'once'));
end
"""
        with tempfile.NamedTemporaryFile("w", suffix=".m", delete=False, encoding="utf-8") as handle:
            handle.write(script_body)
            return Path(handle.name)

    @staticmethod
    def _parse_matlab_issue_lines(output: str) -> List[Dict[str, Any]]:
        parsed: List[Dict[str, Any]] = []
        for raw_line in str(output or "").splitlines():
            line = raw_line.strip()
            if line.startswith("MATLAB_SMOKE_ISSUE|"):
                _, issue_id, line_no, message = line.split("|", 3)
                parsed.append(
                    {
                        "id": issue_id.strip(),
                        "line": int(line_no.strip() or "0"),
                        "message": message.strip(),
                    }
                )
            elif line.startswith("MATLAB_SMOKE_FATAL|"):
                _, message = line.split("|", 1)
                parsed.append({"id": "MATLAB_FATAL", "line": 0, "message": message.strip()})
        return parsed

    def _run_octave_source(self, target_path: Path, runner: Dict[str, str]) -> Dict[str, Any]:
        escaped_target = _escape_matlab_path(target_path)
        eval_command = (
            f"try; source('{escaped_target}'); fprintf('OCTAVE_SMOKE_OK\\n'); "
            "catch err; msg = regexprep(err.message, '[\\r\\n]+', ' '); "
            "msg = strrep(msg, '|', '/'); fprintf(2, 'OCTAVE_SMOKE_ERROR|%s\\n', msg); exit(1); end; exit(0);"
        )
        try:
            completed = subprocess.run(
                [runner["path"], "--quiet", "--no-gui", "--eval", eval_command],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "valid": False,
                "message": f"Octave smoke timed out after {self.timeout_seconds}s",
                "errors": [f"Octave smoke timed out after {self.timeout_seconds}s"],
                "warnings": [],
                "issues": [],
                "runner": "octave",
                "runner_path": runner["path"],
                "mode": "source",
                "file_path": str(target_path),
            }

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        if completed.returncode == 0:
            return {
                "status": "passed",
                "valid": True,
                "message": "Octave syntax smoke passed",
                "errors": [],
                "warnings": [],
                "issues": [],
                "runner": "octave",
                "runner_path": runner["path"],
                "mode": "source",
                "returncode": completed.returncode,
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
                "file_path": str(target_path),
            }

        error_lines = [
            line.split("|", 1)[1].strip()
            for line in (stdout + "\n" + stderr).splitlines()
            if line.strip().startswith("OCTAVE_SMOKE_ERROR|")
        ]
        if not error_lines:
            raw_output = "\n".join(part for part in [stdout.strip(), stderr.strip()] if part).strip()
            error_lines = [raw_output or "Octave syntax smoke failed"]
        return {
            "status": "failed",
            "valid": False,
            "message": error_lines[0],
            "errors": error_lines,
            "warnings": [],
            "issues": [{"id": "OCTAVE_ERROR", "line": 0, "message": item} for item in error_lines],
            "runner": "octave",
            "runner_path": runner["path"],
            "mode": "source",
            "returncode": completed.returncode,
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "file_path": str(target_path),
        }

    @staticmethod
    def _is_runner_environment_error(raw_output: str) -> bool:
        output = str(raw_output or "").lower()
        return any(
            token in output
            for token in (
                "fatal startup error",
                "failed to load settings",
                "license checkout failed",
                "licensing error",
                "matlab crash dump",
            )
        )

    @staticmethod
    def _mark_runner_unavailable(runner: Dict[str, str], message: str) -> None:
        path = str(runner.get("path", "")).strip()
        if path:
            _RUNNER_UNAVAILABLE_CACHE[path] = message

    @staticmethod
    def _build_skipped_result(
        message: str,
        runner: Dict[str, str],
        target_path: Path,
        mode: str,
        stdout: str = "",
        stderr: str = "",
    ) -> Dict[str, Any]:
        return {
            "status": "skipped",
            "valid": None,
            "message": message,
            "errors": [],
            "warnings": [message],
            "issues": [],
            "runner": runner.get("kind", "unknown"),
            "runner_path": runner.get("path", ""),
            "mode": mode,
            "stdout": str(stdout or "").strip(),
            "stderr": str(stderr or "").strip(),
            "file_path": str(target_path),
        }
