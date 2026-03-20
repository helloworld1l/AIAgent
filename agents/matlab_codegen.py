"""Generate MATLAB script from validated ModelSpec."""

from __future__ import annotations

from typing import Any, Dict, List

from agents.open_model_ir_compat import OpenModelIRCompatAdapter
from knowledge_base.matlab_generator import MatlabModelGenerator
from knowledge_base.matlab_smoke_tester import MatlabSyntaxSmokeTester
from knowledge_base.model_family_codegen import MatlabFamilyAssembler
from knowledge_base.matlab_static_validator import MatlabStaticValidator


class MatlabCodeGenerator:
    def __init__(self):
        self.generator = MatlabModelGenerator()
        self.family_generator = MatlabFamilyAssembler()
        self.open_model_ir_adapter = OpenModelIRCompatAdapter(assembler=self.family_generator)
        self.static_validator = MatlabStaticValidator()
        self.smoke_tester = MatlabSyntaxSmokeTester()

    def generate_from_open_model_ir(
        self,
        open_model_ir: Dict[str, Any],
        evidence_docs: List[Dict[str, Any]] | None = None,
        output_dir: str = "generated_models",
    ) -> Dict[str, Any]:
        compatible_spec = self.open_model_ir_adapter.to_model_spec(open_model_ir)
        result = self.generate_from_spec(
            spec=compatible_spec,
            evidence_docs=evidence_docs,
            output_dir=output_dir,
        )
        result.setdefault("open_model_ir", compatible_spec.get("_generation_ir", {}))
        return result

    def generate_from_spec(
        self,
        spec: Dict[str, Any],
        evidence_docs: List[Dict[str, Any]] | None = None,
        output_dir: str = "generated_models",
    ) -> Dict[str, Any]:
        if not isinstance(spec, dict):
            return {"status": "error", "message": "spec must be a dict"}
        if self.open_model_ir_adapter.looks_like_open_model_ir(spec):
            return self.generate_from_open_model_ir(
                open_model_ir=spec,
                evidence_docs=evidence_docs,
                output_dir=output_dir,
            )
        generation_ir = spec.get("_generation_ir", {}) if isinstance(spec, dict) else {}
        model_id = self._resolve_output_model_id(spec, generation_ir)
        preferred_template_model_id = self._resolve_template_model_id(str(model_id))
        if preferred_template_model_id:
            model_id = preferred_template_model_id

        params = self.generator.get_default_params(str(model_id))
        params.update(dict(spec.get("parameters", {})))
        simulation_plan = spec.get("simulation_plan", {})
        if isinstance(simulation_plan, dict) and "stop_time" in simulation_plan:
            params["stop_time"] = simulation_plan["stop_time"]

        assembly: Dict[str, Any] = {}
        assembly_plan: Dict[str, Any] = {}
        ir_validation: Dict[str, Any] = {}
        family_static_validation: Dict[str, Any] = {}
        generator_strategy = "template"
        try:
            if preferred_template_model_id:
                core_script = self.generator.render_script(str(model_id), params)
                generator_strategy = "template"
            elif generation_ir and self.family_generator.supports_ir(generation_ir):
                family_result = self.family_generator.render_from_ir(generation_ir, spec=spec)
                if family_result.get("status") == "success":
                    core_script = family_result.get("script", "")
                    assembly = family_result.get("assembly", {})
                    assembly_plan = family_result.get("assembly_plan", {})
                    ir_validation = family_result.get("ir_validation", {})
                    family_static_validation = family_result.get("static_validation", {})
                    model_id = str(assembly.get("model_id", model_id))
                    generator_strategy = "ir_composable_renderer"
                elif family_result.get("error_type") == "static_validation":
                    return {
                        "status": "error",
                        "message": family_result.get("message", "static validation failed"),
                        "assembly": family_result.get("assembly", {}),
                        "assembly_plan": family_result.get("assembly_plan", {}),
                        "ir_validation": family_result.get("ir_validation", {}),
                        "script": family_result.get("script", ""),
                        "static_validation": family_result.get("static_validation", {}),
                        "generator_strategy": "ir_composable_renderer",
                    }
                else:
                    core_script = self.generator.render_script(str(model_id), params)
            elif self.family_generator.supports_spec(spec):
                family_result = self.family_generator.render_from_spec(spec)
                if family_result.get("status") == "success":
                    core_script = family_result.get("script", "")
                    assembly = family_result.get("assembly", {})
                    assembly_plan = family_result.get("assembly_plan", {})
                    ir_validation = family_result.get("ir_validation", {})
                    family_static_validation = family_result.get("static_validation", {})
                    model_id = str(assembly.get("model_id", model_id))
                    generator_strategy = "ir_composable_renderer"
                elif family_result.get("error_type") == "static_validation":
                    return {
                        "status": "error",
                        "message": family_result.get("message", "static validation failed"),
                        "assembly": family_result.get("assembly", {}),
                        "assembly_plan": family_result.get("assembly_plan", {}),
                        "ir_validation": family_result.get("ir_validation", {}),
                        "script": family_result.get("script", ""),
                        "static_validation": family_result.get("static_validation", {}),
                        "generator_strategy": "ir_composable_renderer",
                    }
                else:
                    core_script = self.generator.render_script(str(model_id), params)
            else:
                core_script = self.generator.render_script(str(model_id), params)
        except Exception:
            try:
                core_script = self.generator.render_script(str(model_id), params)
                generator_strategy = "template_fallback"
            except Exception as exc:
                return {"status": "error", "message": f"render failed: {exc}"}

        header = self._build_header(spec, evidence_docs or [], assembly, generator_strategy)
        script = header + "\n" + core_script
        final_script_validation = self.static_validator.validate_script(script, assembly)
        if family_static_validation:
            static_validation = {
                "valid": final_script_validation.get("valid", False) and family_static_validation.get("valid", False),
                "errors": list(family_static_validation.get("errors", [])) + list(final_script_validation.get("errors", [])),
                "warnings": list(family_static_validation.get("warnings", [])) + list(final_script_validation.get("warnings", [])),
                "assembly_validation": family_static_validation.get("assembly_validation", family_static_validation),
                "script_validation": final_script_validation,
            }
        else:
            static_validation = final_script_validation
        if not static_validation.get("valid", False):
            return {
                "status": "error",
                "message": "static validation failed: " + "; ".join(static_validation.get("errors", [])),
                "model_id": model_id,
                "model_name": self._resolve_model_name(str(model_id), assembly),
                "script": script,
                "spec": spec,
                "assembly": assembly,
                "assembly_plan": assembly_plan,
                "ir_validation": ir_validation,
                "generator_strategy": generator_strategy,
                "static_validation": static_validation,
            }

        try:
            file_name, file_path = self.generator.save_script(
                code=script,
                model_id=str(model_id),
                output_dir=output_dir,
            )
        except Exception as exc:
            return {"status": "error", "message": f"save failed: {exc}"}

        smoke_validation = self.smoke_tester.validate_file(file_path)
        if smoke_validation.get("status") == "failed":
            smoke_errors = smoke_validation.get("errors", [])
            smoke_message = "; ".join(smoke_errors) if smoke_errors else smoke_validation.get(
                "message", "MATLAB/Octave syntax smoke failed"
            )
            return {
                "status": "error",
                "message": "smoke validation failed: " + smoke_message,
                "model_id": model_id,
                "model_name": self._resolve_model_name(str(model_id), assembly),
                "file_name": file_name,
                "file_path": file_path,
                "script": script,
                "spec": spec,
                "assembly": assembly,
                "assembly_plan": assembly_plan,
                "ir_validation": ir_validation,
                "generator_strategy": generator_strategy,
                "static_validation": static_validation,
                "smoke_validation": smoke_validation,
            }

        return {
            "status": "success",
            "model_id": model_id,
            "model_name": self._resolve_model_name(str(model_id), assembly),
            "file_name": file_name,
            "file_path": file_path,
            "script": script,
            "spec": spec,
            "assembly": assembly,
            "assembly_plan": assembly_plan,
            "ir_validation": ir_validation,
            "generator_strategy": generator_strategy,
            "static_validation": static_validation,
            "smoke_validation": smoke_validation,
        }


    def _resolve_output_model_id(self, spec: Dict[str, Any], generation_ir: Dict[str, Any]) -> str:
        model_id = str(spec.get("model_id", "")).strip()
        if model_id:
            return model_id
        if isinstance(generation_ir, dict):
            model_id = str(generation_ir.get("model_id", "")).strip()
            if model_id:
                return model_id
            family = str(generation_ir.get("codegen", {}).get("template_family", "")).strip()
            if family:
                return family
            family = str(generation_ir.get("domain", {}).get("model_family", "")).strip()
            if family:
                return family
        return "composed_model"

    def _resolve_template_model_id(self, model_id: str) -> str:
        candidate = str(model_id or "").strip()
        if candidate and self.generator.has_template(candidate):
            return candidate
        return ""

    def _resolve_model_name(self, model_id: str, assembly: Dict[str, Any] | None = None) -> str:
        if assembly and assembly.get("model_name"):
            return str(assembly.get("model_name"))
        for item in self.generator.catalog:
            if item.get("model_id") == model_id:
                return item.get("name", model_id)
        return model_id

    def _build_header(
        self,
        spec: Dict[str, Any],
        evidence_docs: List[Dict[str, Any]],
        assembly: Dict[str, Any],
        generator_strategy: str,
    ) -> str:
        lines = [
            "%% Generated by RAG ModelSpec pipeline",
            f"% task_goal: {spec.get('task_goal', '')}",
            f"% model_id: {spec.get('model_id', '') or assembly.get('model_id', '')}",
            f"% generator_strategy: {generator_strategy}",
        ]
        if assembly:
            lines.append(f"% template_family: {assembly.get('template_family', '')}")
            lines.append(f"% governing_form: {assembly.get('governing_form', '')}")
            lines.append(f"% solver: {assembly.get('solver', '')}")
            lines.append(f"% codegen_strategy: {assembly.get('codegen_strategy', '')}")
            fragments = assembly.get("equation_fragments", [])
            if fragments:
                lines.append("% equation_fragments: " + ", ".join(str(item) for item in fragments))
            render_blocks = assembly.get("render_blocks", [])
            if render_blocks:
                lines.append("% render_blocks: " + ", ".join(str(item) for item in render_blocks))
        assumptions = spec.get("assumptions", [])
        if assumptions:
            lines.append("% assumptions:")
            for item in assumptions[:6]:
                lines.append(f"%   - {item}")
        if evidence_docs:
            lines.append("% evidence:")
            for e in evidence_docs[:5]:
                payload = e.get("payload", {})
                lines.append(
                    f"%   - model={payload.get('model_id', '')}, score={e.get('score', 0)}, id={e.get('id', '')}"
                )
        return "\n".join(lines)
