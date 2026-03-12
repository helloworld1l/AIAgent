"""
Shared JSON Schema for ModelSpec.
"""

from __future__ import annotations

from typing import Any, Dict

MODEL_SPEC_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": [
        "task_goal",
        "model_id",
        "assumptions",
        "parameters",
        "simulation_plan",
        "required_outputs",
        "missing_info",
    ],
    "properties": {
        "task_goal": {"type": "string", "minLength": 1},
        "model_id": {"type": "string", "pattern": r"^[A-Za-z0-9_]+$"},
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "parameters": {
            "type": "object",
            "additionalProperties": {
                "anyOf": [
                    {"type": "number"},
                    {"type": "string"},
                    {"type": "integer"},
                    {
                        "type": "array",
                        "items": {
                            "anyOf": [
                                {"type": "number"},
                                {"type": "string"},
                                {"type": "integer"},
                            ]
                        },
                    },
                ]
            },
        },
        "simulation_plan": {
            "type": "object",
            "required": ["stop_time"],
            "properties": {
                "stop_time": {"type": "number", "exclusiveMinimum": 0},
            },
            "additionalProperties": True,
        },
        "required_outputs": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "missing_info": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    # allow internal metadata fields like _build_source
    "patternProperties": {
        "^_": {},
    },
    "additionalProperties": False,
}

