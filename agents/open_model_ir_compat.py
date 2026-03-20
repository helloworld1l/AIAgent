"""Compatibility adapter between OpenModelIR and legacy ModelSpec/codegen flows."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from agents.open_model_ir_builder import OpenModelIRBuilder
from agents.open_model_ir_schema import OpenModelIR
from knowledge_base.model_family_codegen import MatlabFamilyAssembler


class OpenModelIRCompatAdapter:
    def __init__(
        self,
        assembler: MatlabFamilyAssembler | None = None,
        builder: OpenModelIRBuilder | None = None,
    ):
        self.assembler = assembler or MatlabFamilyAssembler()
        self.builder = builder or OpenModelIRBuilder()
        self.default_model_by_family: Dict[str, Dict[str, Any]] = {}
        for item in self.assembler.catalog:
            family = str(item.get("template_family", "")).strip()
            if family and family not in self.default_model_by_family:
                self.default_model_by_family[family] = dict(item)

    @staticmethod
    def looks_like_open_model_ir(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        required_sections = {"task", "domain", "entities", "physics", "simulation", "outputs", "codegen", "trace"}
        return required_sections.issubset(payload.keys())

    def normalize(self, payload: Dict[str, Any] | OpenModelIR) -> Dict[str, Any]:
        model = self.builder.build_model(payload)
        return model.model_dump(mode="python", exclude_none=True)

    def to_model_spec(self, payload: Dict[str, Any] | OpenModelIR) -> Dict[str, Any]:
        generation_ir = self.normalize(payload)
        family = self._resolve_family(generation_ir)
        original_model_id = str(generation_ir.get("model_id", "")).strip()
        compatible_model_id, compat_model_source = self._resolve_compatible_model_id(
            original_model_id=original_model_id,
            family=family,
        )

        params: Dict[str, Any] = {}
        params.update(self.default_model_by_family.get(family, {}).get("default_params", {}))
        params.update(self.assembler.model_by_id.get(compatible_model_id, {}).get("default_params", {}))
        defaults = generation_ir.get("defaults", {})
        if isinstance(defaults, dict):
            params.update(defaults)
        params.update(self._extract_parameter_values(generation_ir.get("physics", {}).get("parameters", {})))
        params.update(self._flatten_collected_slots(generation_ir.get("slot_collection", {}).get("collected_slots", {})))

        simulation_ir = generation_ir.get("simulation", {}) if isinstance(generation_ir, dict) else {}
        stop_time = params.get("stop_time")
        if stop_time is None and isinstance(simulation_ir, dict):
            stop_time = simulation_ir.get("stop_time")
        if stop_time is None:
            stop_time = 10
        simulation_plan: Dict[str, Any] = {"stop_time": stop_time}
        if isinstance(simulation_ir, dict):
            for key in ("solver", "time_step_hint", "sample_count"):
                if key in simulation_ir:
                    simulation_plan[key] = simulation_ir[key]

        outputs_ir = generation_ir.get("outputs", {}) if isinstance(generation_ir, dict) else {}
        required_outputs = list(generation_ir.get("required_outputs", []))
        if not required_outputs and isinstance(outputs_ir, dict):
            required_outputs = list(outputs_ir.get("artifacts", [])) or list(outputs_ir.get("signals", []))
        if not required_outputs:
            required_outputs = ["plot"]

        spec: Dict[str, Any] = {
            "task_goal": str(generation_ir.get("task_goal") or generation_ir.get("task", {}).get("goal", "")).strip(),
            "model_id": compatible_model_id,
            "assumptions": list(generation_ir.get("assumptions", [])),
            "parameters": params,
            "simulation_plan": simulation_plan,
            "required_outputs": required_outputs,
            "missing_info": list(generation_ir.get("missing_info", [])),
            "_build_source": "open_model_ir_compat",
            "_generation_ir": generation_ir,
        }
        if family:
            spec["_template_family"] = family
        if original_model_id and original_model_id != compatible_model_id:
            spec["_original_model_id"] = original_model_id
        if compat_model_source:
            spec["_compat_model_id_source"] = compat_model_source
        equation_fragments = generation_ir.get("codegen", {}).get("equation_fragments", [])
        if equation_fragments:
            spec["_equation_fragments"] = list(equation_fragments)
        return spec

    def to_assembly_plan(
        self,
        payload: Dict[str, Any] | OpenModelIR,
        spec: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        generation_ir = self.normalize(payload)
        compatible_spec = self.to_model_spec(generation_ir)
        if isinstance(spec, dict):
            compatible_spec.update(spec)
            compatible_spec["_generation_ir"] = generation_ir
        return self.assembler.plan_from_ir(generation_ir, spec=compatible_spec)

    def _resolve_compatible_model_id(self, original_model_id: str, family: str) -> Tuple[str, str]:
        if original_model_id and original_model_id in self.assembler.model_by_id:
            return original_model_id, "original_model_id"
        family_default = self.default_model_by_family.get(family, {})
        family_model_id = str(family_default.get("model_id", "")).strip()
        if family_model_id:
            return family_model_id, "family_default"
        if original_model_id:
            return original_model_id, "passthrough"
        return "transfer_function_step", "global_default"

    @staticmethod
    def _resolve_family(generation_ir: Dict[str, Any]) -> str:
        candidates = [
            generation_ir.get("schema_family", ""),
            generation_ir.get("codegen", {}).get("template_family", "") if isinstance(generation_ir.get("codegen", {}), dict) else "",
            generation_ir.get("domain", {}).get("model_family", "") if isinstance(generation_ir.get("domain", {}), dict) else "",
        ]
        for candidate in candidates:
            normalized = str(candidate or "").strip()
            if normalized:
                return normalized
        return ""

    @staticmethod
    def _flatten_collected_slots(collected_slots: Any) -> Dict[str, Any]:
        if not isinstance(collected_slots, dict):
            return {}
        flattened: Dict[str, Any] = {}
        for key, item in collected_slots.items():
            if not str(key or "").strip() or not isinstance(item, dict):
                continue
            if item.get("value") is not None:
                flattened[str(key).strip()] = item.get("value")
        return flattened

    @staticmethod
    def _extract_parameter_values(parameters: Any) -> Dict[str, Any]:
        if isinstance(parameters, dict):
            return dict(parameters)

        extracted: Dict[str, Any] = {}
        if not isinstance(parameters, list):
            return extracted
        for item in parameters:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if name and item.get("value") is not None:
                extracted[name] = item.get("value")
        return extracted


__all__ = ["OpenModelIRCompatAdapter"]
