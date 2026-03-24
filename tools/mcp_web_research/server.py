"""Minimal stdio MCP server skeleton for web research workflows."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Callable, Dict

if __package__ in {None, ""}:
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[2]))

from tools.mcp_web_research.research_tool import WebResearchToolchain
from tools.mcp_web_research.schemas import SchemaValidationError, list_tools, validate_tool_args

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebResearchMCPServer:
    def __init__(self) -> None:
        self.research_toolchain = WebResearchToolchain()
        self.tool_handlers: Dict[str, Callable[..., Dict[str, Any]]] = {
            "research_query": self.research_toolchain.research_query,
        }

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
            "isError": bool(payload.get("status") in {"failed", "error"}),
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
                    "serverInfo": {"name": "web-research-mcp", "version": "0.1.0"},
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
    parser = argparse.ArgumentParser(description="Local MCP server for web research query workflows")
    parser.add_argument("--print-tools", action="store_true", help="Print tool definitions as JSON and exit")
    args = parser.parse_args()

    server = WebResearchMCPServer()
    if args.print_tools:
        print(json.dumps(server.list_tools(), ensure_ascii=False, indent=2))
        return
    server.serve_stdio()


if __name__ == "__main__":
    main()
