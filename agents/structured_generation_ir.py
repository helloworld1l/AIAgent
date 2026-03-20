"""Structured generation IR orchestrator built on three clear layers.

Layers:
1) family-level schema registry
2) family-aware slot extractor
3) clarify policy for slot collection
"""

from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from typing import Any, Dict, List

from agents.open_model_ir_builder import OpenModelIRBuilder
from agents.open_model_ir_compat import OpenModelIRCompatAdapter
from agents.open_model_ir_schema import OPEN_MODEL_IR_VERSION
from agents.open_model_ir_validator import OpenModelIRValidator
from agents.structured_generation import (
    COMMON_SLOT_METADATA,
    FAMILY_SCHEMA_BLUEPRINTS,
    FamilyClarifyPolicy,
    FamilySchemaRegistry,
    FamilySlotExtractor,
    SLOT_SCHEMAS,
)
from knowledge_base.model_family_codegen import (
    FAMILY_LIBRARY,
    FAMILY_PARAMETER_DEFAULTS,
    FRAGMENT_LIBRARY,
    MatlabFamilyAssembler,
)
from knowledge_base.rag_retriever import MatlabRAGRetriever

logger = logging.getLogger(__name__)

TRACE_CLARIFY_STAGE_OBJECT = "object"
TRACE_CLARIFY_STAGE_FAMILY = "family"
TRACE_CLARIFY_STAGE_SLOT = "slot"
TRACE_CLARIFY_STAGE_READY = "ready"
TRACE_OBJECT_REASONS = {
    "military_equipment_needs_object",
    "battlefield_situation_needs_object",
    "out_of_scope",
}

NO_DRAG_MARKERS = ["不考虑阻力", "无阻力", "忽略阻力", "没阻力", "no drag"]
NO_GRAVITY_MARKERS = ["不考虑重力", "无重力", "忽略重力", "没重力", "no gravity"]
NO_BUOYANCY_MARKERS = ["不考虑浮力", "无浮力", "忽略浮力", "没浮力", "no buoyancy"]
NO_THRUST_MARKERS = ["不考虑推力", "无推力", "忽略推力", "没推力", "关机", "no thrust"]
NO_MEASUREMENT_NOISE_MARKERS = ["不考虑测量噪声", "无测量噪声", "noise-free measurement"]
NO_FILTER_UPDATE_MARKERS = ["不用kalman", "不使用kalman", "不做滤波", "no kalman", "关闭滤波更新"]
ENABLE_MASS_DEPLETION_MARKERS = ["质量递减", "燃料消耗", "考虑燃耗", "mass depletion", "fuel burn"]

DRAG_FRAGMENTS = {"quadratic_drag_air", "quadratic_drag_water", "quadratic_drag_planar"}
GRAVITY_FRAGMENTS = {"gravity_scalar", "gravity_planar", "two_body_gravity_planar"}
BUOYANCY_FRAGMENTS = {"buoyancy_scalar"}
THRUST_FRAGMENTS = {"constant_thrust", "constant_thrust_vector"}
MEASUREMENT_FRAGMENTS = {"noisy_measurement", "multi_sensor_measurement", "bearing_measurement"}
FILTER_FRAGMENTS = {"kalman_filter_update", "track_fusion_update", "ekf_linearization"}


class StructuredGenerationIR:
    def __init__(self, retriever: MatlabRAGRetriever):
        self.retriever = retriever
        self.assembler = MatlabFamilyAssembler()
        self.schema_registry = FamilySchemaRegistry(retriever.model_by_id)
        self.slot_extractor = FamilySlotExtractor(self.schema_registry)
        self.clarify_policy = FamilyClarifyPolicy(self.schema_registry, self.slot_extractor)
        self.ir_builder = OpenModelIRBuilder()
        self.compat_adapter = OpenModelIRCompatAdapter(assembler=self.assembler, builder=self.ir_builder)
        self.ir_validator = OpenModelIRValidator(
            supported_families=FAMILY_LIBRARY.keys(),
            fragment_library=FRAGMENT_LIBRARY,
            builder=self.ir_builder,
        )

    def supports(self, model_or_family: str) -> bool:
        family = self._resolve_family(model_or_family=model_or_family)
        return self.schema_registry.supports_family(family)

    def begin_collection(self, query: str, match_assessment: Dict[str, Any]) -> Dict[str, Any]:
        candidate = dict(match_assessment.get("top_candidate") or {})
        model_id = str(candidate.get("model_id", "")).strip()
        family = self._resolve_family(
            model_id=model_id,
            family_hint=str(candidate.get("template_family", "")).strip() or str(match_assessment.get("top_family", "")).strip(),
        )
        if not self._can_begin_collection(query, match_assessment, family=family):
            self._log_generation_trace(
                self._build_generation_trace(
                    event="begin_collection_skipped",
                    match_assessment=match_assessment,
                )
            )
            return {}
        extracted = self.extract_slots(query, family)
        defaults = self._get_defaults(model_id, family)
        model_name = str(candidate.get("name") or self._family_display_name(family))
        generation_ir = self._build_ir(
            query=query,
            model_id=model_id,
            family=family,
            model_name=model_name,
            query_domains=match_assessment.get("query_domains", []),
            extracted=extracted,
            defaults=defaults,
            source="query",
            match_assessment=match_assessment,
        )
        self._log_generation_trace(
            self._build_generation_trace(
                event="begin_collection",
                match_assessment=match_assessment,
                generation_ir=generation_ir,
            )
        )
        return generation_ir

    def can_begin_collection(self, query: str, match_assessment: Dict[str, Any]) -> bool:
        candidate = dict(match_assessment.get("top_candidate") or {})
        model_id = str(candidate.get("model_id", "")).strip()
        family = self._resolve_family(
            model_id=model_id,
            family_hint=str(candidate.get("template_family", "")).strip() or str(match_assessment.get("top_family", "")).strip(),
        )
        return self._can_begin_collection(query, match_assessment, family=family)

    def continue_collection(self, pending_ir: Dict[str, Any], reply: str) -> Dict[str, Any]:
        family = self._resolve_generation_family(pending_ir)
        if not self.schema_registry.supports_family(family):
            return {}
        merged = deepcopy(pending_ir)
        slot_update = self.clarify_policy.apply_reply(merged, reply, family)
        slot_collection = slot_update["slot_collection"]
        defaults = dict(merged.get("defaults", {}))
        filled_values = slot_update["filled_values"]
        unresolved_slots = slot_update["unresolved_slots"]
        merged["slot_collection"] = slot_collection

        physics = dict(merged.get("physics", {}))
        current_fragments = list(physics.get("equation_fragments", [])) or self._base_fragments(family, str(merged.get("model_id", "")))
        updated_fragments = self._adjust_fragments_from_text(family, current_fragments, reply)
        physics["equation_fragments"] = updated_fragments
        physics["state_equations"] = self._state_equations_for_family(family, updated_fragments)
        physics["parameters"] = self._physics_parameters(family, {**defaults, **filled_values})
        merged["physics"] = physics

        codegen = dict(merged.get("codegen", {}))
        codegen["template_family"] = family
        codegen["equation_fragments"] = updated_fragments
        merged["codegen"] = codegen

        simulation = dict(merged.get("simulation", {}))
        simulation.update(self._build_simulation_ir(family, {**defaults, **filled_values}))
        merged["simulation"] = simulation
        merged["status"] = slot_collection["status"]
        merged["missing_info"] = unresolved_slots
        merged["schema_family"] = family
        merged["trace"] = self._build_generation_trace(
            event="continue_collection",
            generation_ir=merged,
        )
        self._log_generation_trace(merged["trace"])
        return self._finalize_open_model_ir(merged)

    def should_clarify(self, generation_ir: Dict[str, Any]) -> bool:
        return self.clarify_policy.should_clarify(generation_ir)

    def build_clarify_message(self, generation_ir: Dict[str, Any]) -> str:
        family = self._resolve_generation_family(generation_ir)
        return self.clarify_policy.build_clarify_message(generation_ir, family=family)

    def build_reply_template(self, family: str, missing_slots: List[str], defaults: Dict[str, Any] | None = None) -> str:
        return self.clarify_policy.build_reply_template(family, missing_slots, defaults)

    def to_model_spec(self, generation_ir: Dict[str, Any]) -> Dict[str, Any]:
        return self.compat_adapter.to_model_spec(generation_ir)

    def wants_defaults(self, text: str) -> bool:
        return self.clarify_policy.wants_defaults(text)

    def wants_cancel(self, text: str) -> bool:
        return self.clarify_policy.wants_cancel(text)

    def looks_like_slot_reply(self, text: str, generation_ir: Dict[str, Any]) -> bool:
        family = self._resolve_generation_family(generation_ir)
        return self.clarify_policy.looks_like_slot_reply(text, generation_ir, family=family)

    def extract_slots(self, text: str, family: str, preferred_slots: List[str] | None = None) -> Dict[str, float | int]:
        return self.slot_extractor.extract_slots(text, family, preferred_slots)

    def _build_ir(
        self,
        query: str,
        model_id: str,
        family: str,
        model_name: str,
        query_domains: List[str],
        extracted: Dict[str, float | int],
        defaults: Dict[str, Any],
        source: str,
        match_assessment: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        schema = self.schema_registry.get_schema(family)
        model_meta = self.retriever.model_by_id.get(model_id, {})
        collected_slots = {key: {"value": value, "source": source} for key, value in extracted.items()}
        slot_summary = self.schema_registry.summarize_slot_collection(family, collected_slots, defaults=defaults)
        filled_parameters = {**defaults, **extracted}
        fragments = self._adjust_fragments_from_text(family, self._base_fragments(family, model_id), query)
        simulation_ir = self._build_simulation_ir(family, filled_parameters)
        generation_ir = {
            "ir_version": OPEN_MODEL_IR_VERSION,
            "status": slot_summary["status"],
            "task_goal": query,
            "model_id": model_id,
            "model_name": model_name,
            "schema_family": family,
            "task": {
                "goal": query,
                "request_type": "model_generation",
                "language": "zh-CN",
                "confidence": 0.84 if slot_summary["status"] == "ready" else 0.70,
            },
            "domain": self._build_domain_ir(model_meta, query_domains, schema, family),
            "entities": self._build_entities_ir(family),
            "physics": self._build_physics_ir(family, defaults, extracted, fragments),
            "events": [],
            "constraints": [],
            "simulation": simulation_ir,
            "outputs": self._build_outputs_ir(family, schema),
            "codegen": self._build_codegen_ir(family, fragments),
            "query_domains": list(query_domains),
            "defaults": dict(defaults),
            "assumptions": list(schema.get("assumptions", [])),
            "required_outputs": list(schema.get("required_outputs", ["plot"])),
            "slot_collection": {
                "schema_family": family,
                "identify_slots": slot_summary["identify_slots"],
                "critical_slots": slot_summary["critical_slots"],
                "defaultable_slots": slot_summary["defaultable_slots"],
                "required_slots": slot_summary["required_slots"],
                "recommended_slots": slot_summary["recommended_slots"],
                "collected_slots": collected_slots,
                "filled_parameters": filled_parameters,
                "missing_slots": slot_summary["active_missing_slots"],
                "missing_critical_slots": slot_summary["missing_critical_slots"],
                "missing_defaultable_slots": slot_summary["missing_defaultable_slots"],
                "unresolved_slots": slot_summary["unresolved_slots"],
                "collection_stage": slot_summary["collection_stage"],
                "status": slot_summary["status"],
                "scene": schema.get("scene", ""),
            },
            "missing_info": slot_summary["unresolved_slots"],
        }
        generation_ir["trace"] = self._build_generation_trace(
            event="build_ir",
            match_assessment=match_assessment,
            generation_ir=generation_ir,
        )
        generation_ir["trace"]["model_family"] = family
        generation_ir["trace"]["domain_tags"] = list(model_meta.get("domain_tags", []))
        generation_ir["trace"]["equation_fragments"] = list(fragments)
        return self._finalize_open_model_ir(generation_ir)

    def _finalize_open_model_ir(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        validation = self.ir_validator.validate(payload)
        if not validation.get("valid", False):
            raise ValueError("; ".join(validation.get("errors", [])) or "invalid open model ir")
        return self.ir_builder.build(validation.get("normalized_ir", payload))

    @staticmethod
    def _normalize_trace_list(values: Any) -> List[str]:
        if isinstance(values, (list, tuple, set)):
            return [str(item).strip() for item in values if str(item).strip()]
        if str(values or "").strip():
            return [str(values).strip()]
        return []

    def _resolve_trace_clarify_stage(
        self,
        match_assessment: Dict[str, Any] | None = None,
        generation_ir: Dict[str, Any] | None = None,
    ) -> str:
        if generation_ir:
            slot_collection = generation_ir.get("slot_collection", {})
            missing_slots = self._normalize_trace_list(
                slot_collection.get("missing_slots", []) if isinstance(slot_collection, dict) else generation_ir.get("missing_info", [])
            )
            if missing_slots:
                return TRACE_CLARIFY_STAGE_SLOT
            return TRACE_CLARIFY_STAGE_READY
        assessment = match_assessment or {}
        stage = str(assessment.get("clarify_stage", "") or "").strip().lower()
        if stage in {
            TRACE_CLARIFY_STAGE_OBJECT,
            TRACE_CLARIFY_STAGE_FAMILY,
            TRACE_CLARIFY_STAGE_SLOT,
            TRACE_CLARIFY_STAGE_READY,
        }:
            return stage
        reject_reasons = self._normalize_trace_list(assessment.get("reject_reasons", []))
        if not reject_reasons:
            reason = str(assessment.get("reason", "") or "").strip()
            if reason and reason != "matched":
                reject_reasons = [reason]
        if not reject_reasons:
            return TRACE_CLARIFY_STAGE_READY
        if any(reason.endswith("_needs_object") or reason in TRACE_OBJECT_REASONS for reason in reject_reasons):
            return TRACE_CLARIFY_STAGE_OBJECT
        return TRACE_CLARIFY_STAGE_FAMILY

    def _build_generation_trace(
        self,
        event: str,
        match_assessment: Dict[str, Any] | None = None,
        generation_ir: Dict[str, Any] | None = None,
        final_generated: bool | None = None,
    ) -> Dict[str, Any]:
        assessment = match_assessment or {}
        ir = generation_ir or {}
        previous_trace = ir.get("trace", {}) if isinstance(ir, dict) and isinstance(ir.get("trace", {}), dict) else {}
        slot_collection = ir.get("slot_collection", {}) if isinstance(ir.get("slot_collection", {}), dict) else {}
        query_domains = self._normalize_trace_list(
            ir.get("query_domains", [])
            or assessment.get("query_domains", [])
            or previous_trace.get("query_domains", [])
        )
        top_family = str(
            ir.get("schema_family", "")
            or assessment.get("top_family", "")
            or previous_trace.get("top_family", "")
            or ""
        ).strip()
        family_top_share_raw = assessment.get("family_top_share", previous_trace.get("family_top_share", 0.0))
        reject_reasons = self._normalize_trace_list(
            assessment.get("reject_reasons", []) or previous_trace.get("reject_reasons", [])
        )
        missing_slots = self._normalize_trace_list(
            slot_collection.get("missing_slots", []) or ir.get("missing_info", []) or previous_trace.get("missing_slots", [])
        )
        trace = {
            "source": "structured_generation_ir",
            "event": str(event or "structured_generation_ir").strip(),
            "query_domains": query_domains,
            "top_family": top_family,
            "family_top_share": round(float(family_top_share_raw or 0.0), 4),
            "reject_reasons": reject_reasons,
            "clarify_stage": self._resolve_trace_clarify_stage(match_assessment=assessment, generation_ir=ir),
            "missing_slots": missing_slots,
            "final_generated": final_generated,
        }
        model_family = str(ir.get("schema_family", "") or previous_trace.get("model_family", "") or top_family).strip()
        if model_family:
            trace["model_family"] = model_family
        domain = ir.get("domain", {}) if isinstance(ir.get("domain", {}), dict) else {}
        domain_tags = domain.get("domain_tags", []) or previous_trace.get("domain_tags", [])
        if domain_tags:
            trace["domain_tags"] = list(domain_tags)
        codegen = ir.get("codegen", {}) if isinstance(ir.get("codegen", {}), dict) else {}
        physics = ir.get("physics", {}) if isinstance(ir.get("physics", {}), dict) else {}
        equation_fragments = (
            codegen.get("equation_fragments", [])
            or physics.get("equation_fragments", [])
            or previous_trace.get("equation_fragments", [])
        )
        if equation_fragments:
            trace["equation_fragments"] = list(equation_fragments)
        return trace

    def _log_generation_trace(self, trace: Dict[str, Any]) -> None:
        logger.info("generation_trace=%s", json.dumps(trace, ensure_ascii=False, sort_keys=True))

    def _build_domain_ir(self, model_meta: Dict[str, Any], query_domains: List[str], schema: Dict[str, Any], family: str) -> Dict[str, Any]:
        family_meta = FAMILY_LIBRARY.get(family, {})
        family_domain = str(family_meta.get("domain", "generic") or "generic")
        domain_tags = list(model_meta.get("domain_tags", []))
        if family_domain and family_domain not in domain_tags:
            domain_tags.insert(0, family_domain)
        if family not in domain_tags:
            domain_tags.append(family)
        primary = query_domains[0] if query_domains else family_domain
        secondary = query_domains[1:] if len(query_domains) > 1 else [tag for tag in domain_tags[:4] if tag != primary]
        return {
            "primary": primary,
            "secondary": secondary,
            "scene": schema.get("scene", ""),
            "model_family": family,
            "fidelity": "family_fragment_composable",
            "coordinate_system": self._coordinate_system_for_family(family),
            "domain_tags": domain_tags,
        }

    def _build_entities_ir(self, family: str) -> List[Dict[str, Any]]:
        family_meta = FAMILY_LIBRARY.get(family, {})
        states = list(family_meta.get("state_variables", []))
        domain = str(family_meta.get("domain", "generic"))
        if domain in {"tracking", "battlefield"}:
            return [{"id": family, "type": domain, "role": "scenario", "states": states}]
        return [{"id": family, "type": "system", "role": "main_model", "states": states}]

    def _build_physics_ir(self, family: str, defaults: Dict[str, Any], extracted: Dict[str, Any], fragments: List[str]) -> Dict[str, Any]:
        family_meta = FAMILY_LIBRARY.get(family, {})
        merged = {**defaults, **extracted}
        return {
            "governing_form": family_meta.get("governing_form", "ode"),
            "state_variables": list(family_meta.get("state_variables", [])),
            "equation_fragments": list(fragments),
            "state_equations": self._state_equations_for_family(family, fragments),
            "forces": self._build_physics_components(fragments),
            "parameters": self._physics_parameters(family, merged),
            "initial_conditions": {},
        }

    def _build_simulation_ir(self, family: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        family_meta = FAMILY_LIBRARY.get(family, {})
        dt = parameters.get("dt", parameters.get("ts", 0.1))
        stop_time = parameters.get("stop_time", 10)
        sample_count = parameters.get("steps")
        if sample_count is None:
            sample_count = int(max(50, stop_time / max(dt, 1e-6)))
        return {
            "solver": family_meta.get("solver", "discrete_euler"),
            "stop_time": stop_time,
            "time_step_hint": dt,
            "sample_count": int(sample_count),
        }

    def _build_outputs_ir(self, family: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "signals": list(FAMILY_LIBRARY.get(family, {}).get("state_variables", [])),
            "artifacts": list(schema.get("required_outputs", ["plot"])),
        }

    def _build_codegen_ir(self, family: str, fragments: List[str]) -> Dict[str, Any]:
        return {
            "strategy": "ir_composable_renderer",
            "template_family": family,
            "equation_fragments": list(fragments),
            "target": "matlab_script",
        }

    def _build_physics_components(self, fragments: List[str]) -> List[Dict[str, Any]]:
        components: List[Dict[str, Any]] = []
        for fragment_id in fragments:
            fragment_meta = FRAGMENT_LIBRARY.get(fragment_id, {})
            components.append(
                {
                    "name": fragment_id,
                    "type": fragment_id,
                    "expression": str(fragment_meta.get("equation", "") or ""),
                    "description": str(fragment_meta.get("description", "") or ""),
                }
            )
        return components

    def _state_equations_for_family(self, family: str, fragments: List[str]) -> List[str]:
        return self.assembler._default_state_equations(family, fragments)

    def _adjust_fragments_from_text(self, family: str, fragments: List[str], text: str) -> List[str]:
        allowed = set(self._allowed_fragments(family))
        result = list(dict.fromkeys(fragment for fragment in fragments if fragment in allowed))
        lowered = (text or "").lower()
        if any(marker in lowered for marker in NO_DRAG_MARKERS) or self._negates_concept(lowered, "阻力"):
            result = [fragment for fragment in result if fragment not in DRAG_FRAGMENTS]
        if any(marker in lowered for marker in NO_GRAVITY_MARKERS) or self._negates_concept(lowered, "重力"):
            result = [fragment for fragment in result if fragment not in GRAVITY_FRAGMENTS]
        if any(marker in lowered for marker in NO_BUOYANCY_MARKERS) or self._negates_concept(lowered, "浮力"):
            result = [fragment for fragment in result if fragment not in BUOYANCY_FRAGMENTS]
        if any(marker in lowered for marker in NO_THRUST_MARKERS) or self._negates_concept(lowered, "推力"):
            result = [fragment for fragment in result if fragment not in THRUST_FRAGMENTS]
        if any(marker in lowered for marker in NO_MEASUREMENT_NOISE_MARKERS) or self._negates_concept(lowered, "噪声"):
            result = [fragment for fragment in result if fragment not in MEASUREMENT_FRAGMENTS]
        if any(marker in lowered for marker in NO_FILTER_UPDATE_MARKERS):
            result = [fragment for fragment in result if fragment not in FILTER_FRAGMENTS]
        if any(marker in lowered for marker in ENABLE_MASS_DEPLETION_MARKERS):
            if "mass_depletion" in allowed and "mass_depletion" not in result:
                result.append("mass_depletion")
        return [fragment for fragment in result if fragment in allowed]

    def _base_fragments(self, family: str, model_id: str) -> List[str]:
        model_meta = self.retriever.model_by_id.get(model_id, {})
        return list(model_meta.get("equation_fragments", [])) or self.assembler._default_fragments_for_family(family)

    def _allowed_fragments(self, family: str) -> List[str]:
        return list(self.assembler._default_fragments_for_family(family))

    def _get_defaults(self, model_id: str, family: str) -> Dict[str, Any]:
        defaults = dict(FAMILY_PARAMETER_DEFAULTS.get(family, {}))
        defaults.update(self.retriever.model_by_id.get(model_id, {}).get("default_params", {}))
        return defaults

    def _physics_parameters(self, family: str, merged: Dict[str, Any]) -> List[Dict[str, Any]]:
        schema = self.schema_registry.get_schema(family)
        slot_defs = schema.get("slot_defs", {})
        critical_slots = set(self.schema_registry.critical_slots(family))
        return [
            {
                "name": key,
                "label": slot_def.get("label", key),
                "unit": slot_def.get("unit", ""),
                "value": merged.get(key),
                "required": key in critical_slots,
                "collection_roles": list(slot_def.get("collection_roles", [])),
            }
            for key, slot_def in slot_defs.items()
        ]

    def _resolve_family(self, model_or_family: str = "", model_id: str = "", family_hint: str = "") -> str:
        return self.schema_registry.resolve_family(
            model_or_family=model_or_family,
            model_id=model_id,
            family_hint=family_hint,
            model_lookup=self.retriever.model_by_id,
        )

    def _can_begin_collection(self, query: str, match_assessment: Dict[str, Any], family: str = "") -> bool:
        resolved_family = family or self._resolve_family(
            family_hint=str(match_assessment.get("top_family", "") or "").strip(),
        )
        if not self.schema_registry.supports_family(resolved_family):
            return False
        if self._has_manual_family_lock(query):
            return True
        if not bool(match_assessment.get("should_generate", False)):
            return False
        reject_reasons = self._normalized_reject_reasons(match_assessment)
        return not any(self._blocks_ir_collection(reason) for reason in reject_reasons)

    def _normalized_reject_reasons(self, match_assessment: Dict[str, Any]) -> List[str]:
        reject_reasons = [
            str(item).strip()
            for item in match_assessment.get("reject_reasons", [])
            if str(item).strip()
        ]
        if reject_reasons:
            return reject_reasons
        reason = str(match_assessment.get("reason", "")).strip()
        if reason and reason != "matched":
            return [reason]
        return []

    def _has_manual_family_lock(self, query: str) -> bool:
        manual_selection = self.retriever._extract_manual_generation_selection(query)
        return any(str(value or "").strip() for value in manual_selection.values())

    @staticmethod
    def _blocks_ir_collection(reason: str) -> bool:
        normalized = str(reason or "").strip()
        if not normalized:
            return False
        if normalized.endswith("_needs_object"):
            return True
        return normalized in {
            "family_needs_confirmation",
            "domain_conflict",
            "ambiguous_family",
            "ambiguous_candidate",
            "low_confidence",
            "no_candidate",
            "out_of_scope",
        }

    def _resolve_generation_family(self, generation_ir: Dict[str, Any]) -> str:
        return self.schema_registry.resolve_generation_family(generation_ir, model_lookup=self.retriever.model_by_id)

    def _family_display_name(self, family: str) -> str:
        return self.schema_registry.display_name(family)

    @staticmethod
    def _negates_concept(text: str, concept: str) -> bool:
        prefixes = ["不", "不要", "不考虑", "无", "忽略", "没有", "no"]
        for prefix in prefixes:
            pattern = rf"{re.escape(prefix)}.{{0,4}}{re.escape(concept)}"
            if re.search(pattern, text):
                return True
        return False

    @staticmethod
    def _coordinate_system_for_family(family: str) -> str:
        family_meta = FAMILY_LIBRARY.get(family, {})
        return f"{family_meta.get('domain', 'generic')}_{family_meta.get('governing_form', 'model')}"


__all__ = [
    "COMMON_SLOT_METADATA",
    "FAMILY_SCHEMA_BLUEPRINTS",
    "SLOT_SCHEMAS",
    "StructuredGenerationIR",
]
