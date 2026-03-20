"""Tool schemas and argument validation for the local build MCP server."""

from __future__ import annotations

from typing import Any, Dict

from tools.mcp_local_build.toolchains import DEFAULT_DYNAMIC_PROFILES

try:
    from jsonschema import validate as _jsonschema_validate
    from jsonschema.exceptions import ValidationError as SchemaValidationError
except ImportError:
    _jsonschema_validate = None

    class SchemaValidationError(ValueError):
        """Fallback schema validation error when jsonschema is unavailable."""

        pass


TOOL_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "probe_toolchains": {
        "description": "Detect MATLAB, CMake, Visual Studio, gcc and recommended build profiles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "profiles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": DEFAULT_DYNAMIC_PROFILES,
                },
                "require_matlab": {"type": "boolean", "default": True},
            },
            "additionalProperties": False,
        },
    },
    "create_build_job": {
        "description": "Create a structured build job workspace under generated_builds/.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_name": {"type": "string", "minLength": 1},
                "profile": {"type": "string", "minLength": 1},
                "build_type": {
                    "type": "string",
                    "enum": ["Debug", "Release", "RelWithDebInfo", "MinSizeRel"],
                },
                "artifact_name": {"type": "string", "minLength": 1},
            },
            "required": ["project_name", "profile", "build_type", "artifact_name"],
            "additionalProperties": False,
        },
    },
    "materialize_inputs": {
        "description": "Copy MATLAB inputs and structured build request into the job workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "minLength": 1},
                "matlab_file": {"type": "string", "minLength": 1},
                "entry_function": {"type": "string", "minLength": 1},
                "entry_args_schema": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "minLength": 1},
                            "type": {"type": "string", "minLength": 1},
                            "shape": {
                                "type": "array",
                                "items": {"type": "integer", "minimum": 1},
                            },
                        },
                        "required": ["name", "type"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["job_id", "matlab_file", "entry_function", "entry_args_schema"],
            "additionalProperties": False,
        },
    },
    "matlab_generate_cpp": {
        "description": "Generate C/C++ sources via MATLAB Coder or compatible local MATLAB tooling.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "minLength": 1},
                "target_lang": {"type": "string", "enum": ["C", "C++"]},
                "matlab_codegen_mode": {"type": "string", "enum": ["matlab_coder", "simulink_coder"]},
                "generate_report": {"type": "boolean"},
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    "cmake_configure": {
        "description": "Render CMakeLists.txt and run the configure phase for a dynamic library / DLL profile.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "minLength": 1},
                "generator": {"type": "string"},
                "platform": {"type": "string"},
                "build_type": {
                    "type": "string",
                    "enum": ["Debug", "Release", "RelWithDebInfo", "MinSizeRel"],
                },
                "extra_defines": {
                    "type": "object",
                    "additionalProperties": {
                        "oneOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}],
                    },
                },
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    "cmake_build_dynamic": {
        "description": "Run the build phase and try to collect the generated dynamic library artifacts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "minLength": 1},
                "target": {"type": "string"},
                "config": {
                    "type": "string",
                    "enum": ["Debug", "Release", "RelWithDebInfo", "MinSizeRel"],
                },
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    "cmake_build_static": {
        "description": "Compatibility alias: build the dynamic library / DLL artifacts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "minLength": 1},
                "target": {"type": "string"},
                "config": {
                    "type": "string",
                    "enum": ["Debug", "Release", "RelWithDebInfo", "MinSizeRel"],
                },
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    "inspect_artifacts": {
        "description": "Inspect generated libraries, headers, logs and materialize result.json.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "minLength": 1},
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    "get_job_status": {
        "description": "Fetch the current manifest-backed job status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "minLength": 1},
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
    "get_job_result": {
        "description": "Return the current result.json payload for a completed or in-flight job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "minLength": 1},
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
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
    normalized = arguments or {}
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

    one_of = schema.get("oneOf")
    if one_of:
        errors = []
        for choice in one_of:
            try:
                _fallback_validate(instance, choice, path)
                return
            except SchemaValidationError as exc:
                errors.append(str(exc))
        raise SchemaValidationError(errors[0] if errors else f"{path} does not match any allowed schema")

    expected_type = schema.get("type")
    if expected_type == "string":
        if not isinstance(instance, str):
            raise SchemaValidationError(f"{path} must be a string")
        min_length = schema.get("minLength")
        if min_length is not None and len(instance) < min_length:
            raise SchemaValidationError(f"{path} must have length >= {min_length}")
    elif expected_type == "boolean":
        if not isinstance(instance, bool):
            raise SchemaValidationError(f"{path} must be a boolean")
    elif expected_type == "integer":
        if not isinstance(instance, int) or isinstance(instance, bool):
            raise SchemaValidationError(f"{path} must be an integer")
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            raise SchemaValidationError(f"{path} must be >= {minimum}")
    elif expected_type == "number":
        if not isinstance(instance, (int, float)) or isinstance(instance, bool):
            raise SchemaValidationError(f"{path} must be a number")

    if "enum" in schema and instance not in schema["enum"]:
        allowed = ", ".join(str(item) for item in schema["enum"])
        raise SchemaValidationError(f"{path} must be one of: {allowed}")
