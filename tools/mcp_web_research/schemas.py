"""Tool schemas and argument validation for the web research MCP server."""

from __future__ import annotations

from typing import Any, Dict

try:
    from jsonschema import validate as _jsonschema_validate
    from jsonschema.exceptions import ValidationError as SchemaValidationError
except ImportError:
    _jsonschema_validate = None

    class SchemaValidationError(ValueError):
        """Fallback schema validation error when jsonschema is unavailable."""

        pass


TOOL_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "research_query": {
        "description": (
            "Search the public web for a modeling query, fetch the top pages, "
            "persist a local research bundle, and return normalized evidence docs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "session_id": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
                "max_fetch": {"type": "integer", "minimum": 1, "maximum": 6},
                "allowed_domains": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                },
                "bundle_name": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    }
}


def list_tools() -> list[Dict[str, Any]]:
    return [
        {
            "name": name,
            "description": payload["description"],
            "inputSchema": payload["inputSchema"],
        }
        for name, payload in TOOL_DEFINITIONS.items()
    ]


def validate_tool_args(tool_name: str, arguments: Dict[str, Any] | None) -> Dict[str, Any]:
    if tool_name not in TOOL_DEFINITIONS:
        raise ValueError(f"unknown tool: {tool_name}")
    normalized = dict(arguments or {})
    schema = TOOL_DEFINITIONS[tool_name]["inputSchema"]
    if _jsonschema_validate is not None:
        _jsonschema_validate(instance=normalized, schema=schema)
    else:
        _fallback_validate(instance=normalized, schema=schema, path=tool_name)
    return normalized


def _fallback_validate(instance: Any, schema: Dict[str, Any], path: str) -> None:
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(instance, dict):
            raise SchemaValidationError(f"{path} must be an object")
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                raise SchemaValidationError(f"{path}.{key} is required")
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}).keys())
            extras = sorted(set(instance.keys()) - allowed)
            if extras:
                raise SchemaValidationError(f"{path} has unsupported fields: {', '.join(extras)}")
        for key, value in instance.items():
            child_schema = schema.get("properties", {}).get(key)
            if child_schema:
                _fallback_validate(value, child_schema, f"{path}.{key}")
        return

    if schema_type == "array":
        if not isinstance(instance, list):
            raise SchemaValidationError(f"{path} must be an array")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(instance):
                _fallback_validate(item, item_schema, f"{path}[{index}]")
        return

    if schema_type == "string":
        if not isinstance(instance, str):
            raise SchemaValidationError(f"{path} must be a string")
        min_length = schema.get("minLength")
        if min_length is not None and len(instance) < int(min_length):
            raise SchemaValidationError(f"{path} must have at least {min_length} characters")
        return

    if schema_type == "integer":
        if not isinstance(instance, int) or isinstance(instance, bool):
            raise SchemaValidationError(f"{path} must be an integer")
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            raise SchemaValidationError(f"{path} must be >= {minimum}")
        maximum = schema.get("maximum")
        if maximum is not None and instance > maximum:
            raise SchemaValidationError(f"{path} must be <= {maximum}")
        return

