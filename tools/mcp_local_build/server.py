"""Minimal stdio MCP server skeleton for local dynamic library builds."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Callable, Dict

if __package__ in {None, ""}:
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[2]))

from tools.mcp_local_build.artifact_tool import ArtifactInspector
from tools.mcp_local_build.cmake_tool import CMakeTool
from tools.mcp_local_build.job_manager import BuildJobManager
from tools.mcp_local_build.matlab_codegen_tool import MatlabCodegenTool
from tools.mcp_local_build.schemas import SchemaValidationError, list_tools, validate_tool_args
from tools.mcp_local_build.toolchains import DEFAULT_DYNAMIC_PROFILES, ToolchainProbe

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LocalBuildMCPServer:
    def __init__(self) -> None:
        self.job_manager = BuildJobManager()
        self.toolchains = ToolchainProbe()
        self.matlab_codegen = MatlabCodegenTool(self.job_manager, self.toolchains)
        self.cmake_tool = CMakeTool(self.job_manager, self.toolchains)
        self.artifact_inspector = ArtifactInspector(self.job_manager)
        self.tool_handlers: Dict[str, Callable[..., Dict[str, Any]]] = {
            "probe_toolchains": self._probe_toolchains,
            "create_build_job": self._create_build_job,
            "materialize_inputs": self.matlab_codegen.materialize_inputs,
            "matlab_generate_cpp": self.matlab_codegen.matlab_generate_cpp,
            "cmake_configure": self.cmake_tool.cmake_configure,
            "cmake_build_dynamic": self.cmake_tool.cmake_build_dynamic,
            "cmake_build_static": self.cmake_tool.cmake_build_static,
            "inspect_artifacts": self.artifact_inspector.inspect_artifacts,
            "get_job_status": self.job_manager.get_job_status,
            "get_job_result": self.artifact_inspector.get_job_result,
        }

    def _probe_toolchains(self, profiles: list[str] | None = None, require_matlab: bool = True) -> Dict[str, Any]:
        requested_profiles = profiles or list(DEFAULT_DYNAMIC_PROFILES)
        return self.toolchains.probe(requested_profiles, require_matlab=require_matlab)

    def _create_build_job(self, project_name: str, profile: str, build_type: str, artifact_name: str) -> Dict[str, Any]:
        return self.job_manager.create_job(project_name, profile, build_type, artifact_name)

    def list_tools(self) -> Dict[str, Any]:
        return {"tools": list_tools()}

    def call_tool(self, tool_name: str, arguments: Dict[str, Any] | None) -> Dict[str, Any]:
        normalized_args = validate_tool_args(tool_name, arguments)
        if tool_name not in self.tool_handlers:
            raise ValueError(f"tool handler not implemented: {tool_name}")
        payload = self.tool_handlers[tool_name](**normalized_args)
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(payload, ensure_ascii=False, indent=2),
                }
            ],
            "structuredContent": payload,
            "isError": bool(payload.get("status") == "failed"),
        }

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any] | None:
        request_id = request.get("id")
        method = request.get("method", "")
        params = request.get("params", {}) or {}

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "serverInfo": {"name": "local-build-mcp", "version": "0.1.0"},
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                },
            }
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": self.list_tools()}
        if method == "tools/call":
            result = self.call_tool(str(params.get("name", "")), params.get("arguments"))
            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Unsupported method: {method}",
            },
        }

    def serve_stdio(self) -> None:
        stdin = sys.stdin.buffer
        stdout = sys.stdout.buffer
        while True:
            request = self._read_message(stdin)
            if request is None:
                break
            try:
                response = self.handle_request(request)
            except (ValueError, FileNotFoundError, SchemaValidationError) as exc:
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {
                        "code": -32000,
                        "message": str(exc),
                    },
                }
            except Exception as exc:
                logger.exception("Unhandled MCP server error")
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {
                        "code": -32603,
                        "message": str(exc),
                    },
                }
            if response is not None:
                self._write_message(stdout, response)

    @staticmethod
    def _read_message(stream) -> Dict[str, Any] | None:
        headers: Dict[str, str] = {}
        while True:
            line = stream.readline()
            if not line:
                return None
            if line in {b"\r\n", b"\n"}:
                break
            decoded = line.decode("utf-8").strip()
            if not decoded or ":" not in decoded:
                continue
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            return None
        body = stream.read(content_length)
        if not body:
            return None
        return json.loads(body.decode("utf-8"))

    @staticmethod
    def _write_message(stream, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        stream.write(header)
        stream.write(body)
        stream.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local MCP server for MATLAB -> dynamic library build jobs")
    parser.add_argument("--print-tools", action="store_true", help="Print tool definitions as JSON and exit")
    args = parser.parse_args()

    server = LocalBuildMCPServer()
    if args.print_tools:
        print(json.dumps(server.list_tools(), ensure_ascii=False, indent=2))
        return
    server.serve_stdio()


if __name__ == "__main__":
    main()
