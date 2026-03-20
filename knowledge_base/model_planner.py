"""Plan block assembly from validated Open Model IR."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Mapping, Sequence

from agents.open_model_ir_validator import OpenModelIRValidator
from knowledge_base.assembly_plan import AssemblyPlan
from knowledge_base.blocks import (
    BLOCK_LIBRARY,
    DEFAULT_RENDER_RULE,
    FAMILY_RENDER_RULES,
    FRAGMENT_RENDER_ORDER,
    _family_block_id,
)


class ModelPlanner:
    def __init__(
        self,
        catalog: Sequence[Dict[str, Any]],
        family_library: Mapping[str, Dict[str, Any]],
        fragment_library: Mapping[str, Dict[str, Any]],
        family_parameter_defaults: Mapping[str, Dict[str, Any]],
        default_fragments_resolver: Callable[[str], List[str]],
        default_state_equations_resolver: Callable[[str, List[str]], List[str]],
        model_id_resolver: Callable[[str, List[str]], str],
    ):
        self.catalog = [dict(item) for item in catalog]
        self.model_by_id = {str(item.get("model_id", "")).strip(): dict(item) for item in self.catalog}
        self.default_model_by_family: Dict[str, Dict[str, Any]] = {}
        for item in self.catalog:
            family = str(item.get("template_family", "")).strip()
            if family and family not in self.default_model_by_family:
                self.default_model_by_family[family] = dict(item)

        self.family_library = family_library
        self.fragment_library = fragment_library
        self.family_parameter_defaults = family_parameter_defaults
        self.default_fragments_resolver = default_fragments_resolver
        self.default_state_equations_resolver = default_state_equations_resolver
        self.model_id_resolver = model_id_resolver
        self.ir_validator = OpenModelIRValidator(
            supported_families=FAMILY_RENDER_RULES.keys(),
            fragment_library=fragment_library,
            allow_fragment_drafts=True,
        )

    def supports_family(self, family: str) -> bool:
        return str(family or "").strip() in FAMILY_RENDER_RULES

    def supports_ir(self, generation_ir: Dict[str, Any]) -> bool:
        family = self._resolve_family_from_payload(generation_ir)
        return self.supports_family(family)

    def plan_from_ir(self, generation_ir: Dict[str, Any], spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
        validation = self.ir_validator.validate(generation_ir)
        if not validation.get("valid", False):
            return {
                "status": "error",
                "message": "invalid open model ir: " + "; ".join(validation.get("errors", [])),
                "ir_validation": validation,
            }

        normalized_ir = dict(validation.get("normalized_ir", {}))
        if normalized_ir.get("missing_info", []):
            return {
                "status": "error",
                "message": "open model ir is incomplete: " + ", ".join(normalized_ir.get("missing_info", [])),
                "ir_validation": validation,
            }

        spec = spec if isinstance(spec, dict) else {}
        model_id = str(spec.get("model_id") or normalized_ir.get("model_id", "")).strip()
        model_meta = self.model_by_id.get(model_id, {})
        family = self._resolve_family(normalized_ir, spec, model_meta)
        if not self.supports_family(family):
            return {
                "status": "error",
                "message": f"unsupported or missing template family: {family}",
                "ir_validation": validation,
            }

        family_meta = self.family_library.get(family, {})
        physics_ir = normalized_ir.get("physics", {}) if isinstance(normalized_ir, dict) else {}
        simulation_ir = normalized_ir.get("simulation", {}) if isinstance(normalized_ir, dict) else {}
        outputs_ir = normalized_ir.get("outputs", {}) if isinstance(normalized_ir, dict) else {}
        fragment_plan = self._resolve_fragment_plan(family, normalized_ir, model_meta)
        fragments = list(fragment_plan.get("reused_fragments", []))
        fragment_defs = list(fragment_plan.get("fragment_defs", []))
        state_equations = list(physics_ir.get("state_equations", [])) or self.default_state_equations_resolver(family, fragments)
        parameters = self._resolve_parameters(family, normalized_ir, spec, model_meta)
        render_blocks = self._build_render_blocks(family, fragments, outputs_ir)
        block_groups = self._build_block_groups(render_blocks)
        assumptions = list(normalized_ir.get("assumptions", spec.get("assumptions", [])))
        if fragment_plan.get("draft_fragment_defs"):
            assumptions.append("draft equation fragments are preserved as comment_only placeholders until native render blocks are registered")

        plan = AssemblyPlan.model_validate(
            {
                "model_id": model_id or self.model_id_resolver(family, fragments),
                "model_name": str(normalized_ir.get("model_name") or model_meta.get("name") or family),
                "template_family": family,
                "governing_form": str(physics_ir.get("governing_form", family_meta.get("governing_form", "ode"))),
                "solver": str(simulation_ir.get("solver", family_meta.get("solver", "discrete_euler"))),
                "state_variables": list(physics_ir.get("state_variables", [])) or list(family_meta.get("state_variables", [])),
                "equation_fragments": list(fragments),
                "fragment_defs": fragment_defs,
                "state_equations": state_equations,
                "parameters": parameters,
                "entities": list(normalized_ir.get("entities", [])),
                "outputs": self._resolve_outputs(outputs_ir, normalized_ir),
                "task_goal": str(normalized_ir.get("task_goal", spec.get("task_goal", ""))),
                "ir_version": str(normalized_ir.get("ir_version", "")),
                "codegen_strategy": str(normalized_ir.get("codegen", {}).get("strategy", "ir_composable_renderer")),
                "block_groups": block_groups,
                "render_blocks": render_blocks,
                "domain": dict(normalized_ir.get("domain", {})),
                "assumptions": assumptions,
            }
        )
        return {
            "status": "success",
            "plan": plan.model_dump(mode="python", exclude_none=True),
            "ir_validation": validation,
        }

    def _resolve_family_from_payload(self, generation_ir: Dict[str, Any]) -> str:
        if not isinstance(generation_ir, dict):
            return ""
        candidates = [
            generation_ir.get("schema_family", ""),
            generation_ir.get("codegen", {}).get("template_family", "") if isinstance(generation_ir.get("codegen", {}), dict) else "",
            generation_ir.get("domain", {}).get("model_family", "") if isinstance(generation_ir.get("domain", {}), dict) else "",
        ]
        for candidate in candidates:
            family = str(candidate or "").strip()
            if family:
                return family
        return ""

    def _resolve_family(
        self,
        generation_ir: Dict[str, Any],
        spec: Dict[str, Any],
        model_meta: Dict[str, Any],
    ) -> str:
        codegen_ir = generation_ir.get("codegen", {}) if isinstance(generation_ir, dict) else {}
        domain_ir = generation_ir.get("domain", {}) if isinstance(generation_ir, dict) else {}
        candidates = [
            codegen_ir.get("template_family"),
            domain_ir.get("model_family"),
            generation_ir.get("schema_family") if isinstance(generation_ir, dict) else "",
            spec.get("template_family") if isinstance(spec, dict) else "",
            model_meta.get("template_family", ""),
        ]
        for candidate in candidates:
            family = str(candidate or "").strip()
            if family:
                return family
        return ""

    def _resolve_fragment_plan(
        self,
        family: str,
        generation_ir: Dict[str, Any],
        model_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        codegen_ir = generation_ir.get("codegen", {}) if isinstance(generation_ir, dict) else {}
        physics_ir = generation_ir.get("physics", {}) if isinstance(generation_ir, dict) else {}
        raw_fragments = self._normalize_fragment_tokens(
            list(codegen_ir.get("equation_fragments", []))
            or list(physics_ir.get("equation_fragments", []))
            or list(model_meta.get("equation_fragments", []))
            or list(self.default_model_by_family.get(family, {}).get("equation_fragments", []))
            or self.default_fragments_resolver(family)
        )
        reused_fragments: List[str] = []
        fragment_defs: List[Dict[str, Any]] = []
        draft_fragment_defs: List[Dict[str, Any]] = []
        seen_reused: set[str] = set()
        seen_defs: set[str] = set()

        def add_library_fragment(fragment_id: str, origin: str) -> None:
            normalized = str(fragment_id or "").strip()
            if not normalized or normalized in seen_reused:
                return
            if not self._can_render_fragment(family, normalized):
                fragment_meta = self.fragment_library.get(normalized, {})
                add_draft_fragment(
                    fragment_id=normalized,
                    description=str(fragment_meta.get("description", "") or f"cross-family fragment: {normalized}"),
                    equation=str(fragment_meta.get("equation", "") or ""),
                    origin=origin,
                )
                return
            seen_reused.add(normalized)
            reused_fragments.append(normalized)
            if normalized in seen_defs:
                return
            seen_defs.add(normalized)
            fragment_meta = self.fragment_library.get(normalized, {})
            fragment_defs.append(
                {
                    "fragment_id": normalized,
                    "description": str(fragment_meta.get("description", "") or ""),
                    "equation": str(fragment_meta.get("equation", "") or ""),
                    "source": "library",
                    "render_mode": "native",
                    "origin": origin,
                }
            )

        def add_draft_fragment(fragment_id: str, description: str = "", equation: str = "", origin: str = "") -> None:
            normalized = self._normalize_fragment_id(fragment_id)
            if not normalized:
                normalized = f"{family}_draft_fragment_{len(draft_fragment_defs) + 1}"
            if normalized in self.fragment_library and self._can_render_fragment(family, normalized):
                add_library_fragment(normalized, origin)
                return
            if normalized in seen_defs:
                return
            seen_defs.add(normalized)
            draft_payload = {
                "fragment_id": normalized,
                "description": str(description or f"draft fragment inferred from {origin or 'open_model_ir'}"),
                "equation": str(equation or ""),
                "source": "draft",
                "render_mode": "comment_only",
                "origin": origin,
            }
            fragment_defs.append(draft_payload)
            draft_fragment_defs.append(draft_payload)

        for fragment_id in raw_fragments:
            if fragment_id in self.fragment_library:
                add_library_fragment(fragment_id, "equation_fragments")
            else:
                matched_component = self._find_component_seed(physics_ir, fragment_id)
                add_draft_fragment(
                    fragment_id=fragment_id,
                    description=matched_component.get("description", "") if matched_component else f"draft fragment requested by open_model_ir: {fragment_id}",
                    equation=matched_component.get("equation", "") if matched_component else "",
                    origin="equation_fragments",
                )

        physics_components = self._physics_components(physics_ir)
        for component_index, component in enumerate(physics_components, start=1):
            matched_fragment = self._match_component_to_fragment(family, component)
            if matched_fragment:
                add_library_fragment(matched_fragment, f"physics.forces:{component_index}")
                continue
            add_draft_fragment(
                fragment_id=self._component_fragment_id(family, component, component_index),
                description=str(component.get("description", "") or component.get("name", "") or component.get("type", "") or f"draft force component {component_index}"),
                equation=str(component.get("expression", "") or ""),
                origin=f"physics.forces:{component_index}",
            )

        state_equations = [str(item).strip() for item in physics_ir.get("state_equations", []) if str(item).strip()]
        if state_equations and not physics_components and not fragment_defs:
            for equation_index, equation in enumerate(state_equations, start=1):
                add_draft_fragment(
                    fragment_id=f"{family}_state_equation_{equation_index}",
                    description=f"draft fragment synthesized from physics.state_equations[{equation_index - 1}]",
                    equation=equation,
                    origin=f"physics.state_equations:{equation_index - 1}",
                )

        return {
            "reused_fragments": reused_fragments,
            "fragment_defs": fragment_defs,
            "draft_fragment_defs": draft_fragment_defs,
        }

    @staticmethod
    def _normalize_fragment_tokens(values: List[Any]) -> List[str]:
        result: List[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

    @staticmethod
    def _normalize_fragment_id(value: Any) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "").strip().lower())
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        return normalized

    def _can_render_fragment(self, family: str, fragment_id: str) -> bool:
        return _family_block_id("fragment", family, fragment_id) in BLOCK_LIBRARY

    @staticmethod
    def _physics_components(physics_ir: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(physics_ir, dict):
            return []
        forces = physics_ir.get("forces", [])
        if not isinstance(forces, list):
            return []
        return [dict(item) for item in forces if isinstance(item, dict)]

    def _find_component_seed(self, physics_ir: Dict[str, Any], fragment_id: str) -> Dict[str, str]:
        normalized_target = self._normalize_fragment_id(fragment_id)
        for component in self._physics_components(physics_ir):
            candidates = [component.get("type", ""), component.get("name", "")]
            for candidate in candidates:
                if self._normalize_fragment_id(candidate) == normalized_target:
                    return {
                        "description": str(component.get("description", "") or component.get("name", "") or component.get("type", "") or ""),
                        "equation": str(component.get("expression", "") or ""),
                    }
        return {}

    def _match_component_to_fragment(self, family: str, component: Dict[str, Any]) -> str:
        for candidate in (component.get("type", ""), component.get("name", "")):
            fragment_id = str(candidate or "").strip()
            if fragment_id in self.fragment_library and self._can_render_fragment(family, fragment_id):
                return fragment_id

        expression = str(component.get("expression", "") or "").strip()
        if not expression:
            return ""
        for fragment_id, fragment_meta in self.fragment_library.items():
            if expression == str(fragment_meta.get("equation", "") or "").strip() and self._can_render_fragment(family, fragment_id):
                return fragment_id
        return ""

    def _component_fragment_id(self, family: str, component: Dict[str, Any], index: int) -> str:
        for candidate in (component.get("type", ""), component.get("name", "")):
            normalized = self._normalize_fragment_id(candidate)
            if normalized:
                return normalized
        return f"{family}_draft_fragment_{index}"

    def _resolve_parameters(
        self,
        family: str,
        generation_ir: Dict[str, Any],
        spec: Dict[str, Any],
        model_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        params = dict(self.family_parameter_defaults.get(family, {}))
        params.update(self.default_model_by_family.get(family, {}).get("default_params", {}))
        params.update(model_meta.get("default_params", {}))
        if isinstance(spec, dict):
            params.update(spec.get("parameters", {}))

        physics_ir = generation_ir.get("physics", {}) if isinstance(generation_ir, dict) else {}
        physics_params = physics_ir.get("parameters", {}) if isinstance(physics_ir, dict) else {}
        if isinstance(physics_params, dict):
            params.update(physics_params)
        elif isinstance(physics_params, list):
            for item in physics_params:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if name and item.get("value") is not None:
                    params[name] = item.get("value")

        simulation_ir = generation_ir.get("simulation", {}) if isinstance(generation_ir, dict) else {}
        if isinstance(simulation_ir, dict):
            if "stop_time" in simulation_ir:
                params["stop_time"] = simulation_ir["stop_time"]
            if "time_step_hint" in simulation_ir:
                params.setdefault("dt", simulation_ir["time_step_hint"])
            if "sample_count" in simulation_ir:
                params.setdefault("steps", simulation_ir["sample_count"])

        if "steps" in params:
            try:
                params["steps"] = int(float(params["steps"]))
            except Exception:
                pass
        return params

    @staticmethod
    def _resolve_outputs(outputs_ir: Dict[str, Any], generation_ir: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = []
        if isinstance(outputs_ir, dict):
            artifacts = list(outputs_ir.get("artifacts", []))
        if not artifacts:
            artifacts = list(generation_ir.get("required_outputs", ["plot"]))
        signals = list(outputs_ir.get("signals", [])) if isinstance(outputs_ir, dict) else []
        return {
            "artifacts": artifacts,
            "signals": signals,
        }

    def _build_render_blocks(self, family: str, fragments: List[str], outputs_ir: Dict[str, Any]) -> List[str]:
        del outputs_ir
        rule = FAMILY_RENDER_RULES.get(family, DEFAULT_RENDER_RULE)
        ordered_fragments = list(FRAGMENT_RENDER_ORDER.get(family, []))
        ordered_fragments.extend(fragment for fragment in fragments if fragment not in ordered_fragments)

        render_blocks: List[str] = []
        consumed_fragments: set[str] = set()
        for token in rule:
            if isinstance(token, str):
                render_blocks.append(token)
                continue
            if not isinstance(token, dict) or token.get("kind") != "fragments":
                continue

            fragment_names = list(token.get("names", []))
            if token.get("include_remaining"):
                fragment_names.extend(
                    fragment for fragment in ordered_fragments if fragment not in fragment_names
                )

            for fragment in fragment_names:
                if fragment in consumed_fragments:
                    continue
                render_blocks.append(_family_block_id("fragment", family, fragment))
                consumed_fragments.add(fragment)
        return render_blocks

    def _build_block_groups(self, render_blocks: List[str]) -> List[Dict[str, Any]]:
        groups: List[Dict[str, Any]] = []
        current_stage = ""
        current_blocks: List[str] = []

        def flush() -> None:
            if not current_blocks:
                return
            stage = current_stage if current_stage in {"setup", "declare", "solver", "fragment", "update", "output"} else "custom"
            groups.append(
                {
                    "group_id": f"{stage}_{len(groups) + 1}",
                    "stage": stage,
                    "block_ids": list(current_blocks),
                    "loop_scoped": stage in {"fragment", "update"},
                    "required": True,
                    "description": f"{stage} blocks",
                }
            )

        for block_id in render_blocks:
            stage = str(block_id).split(":", 1)[0].strip() or "custom"
            if current_blocks and stage != current_stage:
                flush()
                current_blocks = []
            current_stage = stage
            current_blocks.append(block_id)
        flush()
        return groups


__all__ = ["ModelPlanner"]
