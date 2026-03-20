"""Helpers for running subprocesses with robust output decoding."""

from __future__ import annotations

import locale
import subprocess
from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CapturedProcess:
    returncode: int
    stdout: str
    stderr: str


def run_command(
    command: Sequence[str],
    *,
    timeout: int,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
) -> CapturedProcess:
    completed = subprocess.run(
        list(command),
        capture_output=True,
        text=False,
        timeout=timeout,
        cwd=cwd,
        env=dict(env) if env is not None else None,
    )
    return CapturedProcess(
        returncode=completed.returncode,
        stdout=_decode_output(completed.stdout),
        stderr=_decode_output(completed.stderr),
    )


def _decode_output(payload: bytes | None) -> str:
    if not payload:
        return ""

    preferred = locale.getpreferredencoding(False) or "utf-8"
    encodings = []
    for encoding in ("utf-8", "utf-8-sig", preferred, "gbk", "mbcs"):
        if encoding and encoding not in encodings:
            encodings.append(encoding)

    for encoding in encodings:
        try:
            return payload.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue

    try:
        return payload.decode(preferred, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")
