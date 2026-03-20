"""Semantic validator for Open Model IR payloads."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Sequence

from pydantic import ValidationError

from agents.open_model_ir_builder import OpenModelIRBuilder
from agents.open_model_ir_schema import OpenModelIR


class OpenModelIRValidator:
    def __init__(
        self,
        supported_families: Iterable[str] | None = None,
        fragment_library: Mapping[str, Any] | None = None,
        builder: OpenModelIRBuilder | None = None,
        allow_fragment_drafts: bool = False,
    ):
        self.supported_families = {
            str(item).strip()
            for item in (supported_families or [])
            if str(item).strip()
        }
        self.fragment_library = fragment_library or {}
        self.builder = builder or OpenModelIRBuilder()
        self.allow_fragment_drafts = bool(allow_fragment_drafts)

    def validate(self, payload: Dict[str, Any] | OpenModelIR) -> Dict[str, Any]:
        try:
            model = self.builder.build_model(payload)
        except ValidationError as exc:
            return {
                "valid": False,
                "errors": self._format_schema_errors(exc),
                "warnings": [],
                "normalized_ir": {},
                "family": "",
            }
        except Exception as exc:
            return {
                "valid": False,
                "errors": [str(exc)],
                "warnings": [],
                "normalized_ir": {},
                "family": "",
            }

        errors: list[str] = []
        warnings: list[str] = []
        family_candidates = self._family_candidates(model)
        family = family_candidates[0] if family_candidates else ""

        if len(family_candidates) > 1:
            errors.append("inconsistent family fields: " + ", ".join(family_candidates))

        if model.task.request_type == "model_generation" and not family:
            errors.append("missing model family for model_generation request")

        if self.supported_families and family and family not in self.supported_families:
            errors.append(f"unsupported model family: {family}")

        physics_fragments = self._normalize_strings(model.physics.equation_fragments)
        codegen_fragments = self._normalize_strings(model.codegen.equation_fragments)
        combined_fragments = physics_fragments or codegen_fragments

        if len(physics_fragments) != len(set(physics_fragments)):
            warnings.append("physics.equation_fragments contain duplicates")
        if len(codegen_fragments) != len(set(codegen_fragments)):
            warnings.append("codegen.equation_fragments contain duplicates")
        if physics_fragments and codegen_fragments and physics_fragments != codegen_fragments:
            warnings.append("physics/codegen equation_fragments differ")

        if self.fragment_library:
            unknown_fragments = [fragment for fragment in combined_fragments if fragment not in self.fragment_library]
            if unknown_fragments:
                message = "unknown equation fragments: " + ", ".join(unknown_fragments)
                if self.allow_fragment_drafts:
                    warnings.append(message + " (treated as draft candidates)")
                else:
                    errors.append(message)

        if model.status == "ready" and model.missing_info:
            errors.append("status=ready conflicts with missing_info")

        if model.task_goal and model.task.goal and model.task_goal != model.task.goal:
            warnings.append("task_goal differs from task.goal")

        if not model.outputs.artifacts and not model.outputs.signals:
            warnings.append("outputs are empty")

        if model.simulation.time_step_hint and model.simulation.stop_time:
            if model.simulation.time_step_hint > model.simulation.stop_time:
                warnings.append("simulation.time_step_hint is greater than stop_time")

        normalized_ir = model.model_dump(mode="python", exclude_none=True)
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "normalized_ir": normalized_ir,
            "family": family,
        }

    def validate_or_raise(self, payload: Dict[str, Any] | OpenModelIR) -> OpenModelIR:
        result = self.validate(payload)
        if not result.get("valid", False):
            raise ValueError("; ".join(result.get("errors", [])) or "invalid open model ir")
        return self.builder.build_model(result["normalized_ir"])

    @staticmethod
    def _family_candidates(model: OpenModelIR) -> list[str]:
        values = [
            model.schema_family,
            model.domain.model_family,
            model.codegen.template_family,
            model.trace.model_family,
            model.slot_collection.schema_family if model.slot_collection else "",
        ]
        result: list[str] = []
        for value in values:
            normalized = str(value or "").strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @staticmethod
    def _normalize_strings(values: Sequence[Any]) -> list[str]:
        result: list[str] = []
        for value in values:
            normalized = str(value or "").strip()
            if normalized:
                result.append(normalized)
        return result

    @staticmethod
    def _format_schema_errors(exc: ValidationError) -> list[str]:
        errors: list[str] = []
        for item in exc.errors():
            location = ".".join(str(part) for part in item.get("loc", [])) or "payload"
            message = str(item.get("msg", "validation error")).strip()
            errors.append(f"{location}: {message}")
        return errors


__all__ = ["OpenModelIRValidator"]
