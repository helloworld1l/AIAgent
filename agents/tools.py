"""
Tool adapters for MATLAB knowledge retrieval, .m generation, and dynamic library build orchestration.
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import ensure_runtime_env_defaults
from knowledge_base.matlab_generator import MatlabModelGenerator
from knowledge_base.matlab_model_data import get_model_catalog
from tools.mcp_local_build.server import LocalBuildMCPServer
from tools.mcp_web_research.server import WebResearchMCPServer


class MatlabKnowledgeRetrieverTool:
    name = "matlab_knowledge_retriever"
    description = "Retrieve relevant MATLAB model knowledge entries by natural language description."

    def __init__(self):
        self.generator = MatlabModelGenerator()

    def _run(self, query: str) -> str:
        if not query or not query.strip():
            return json.dumps({"status": "error", "message": "Query is empty."}, ensure_ascii=False)
        matches = self.generator.retrieve_knowledge(query, top_k=5)
        return json.dumps(
            {
                "status": "success",
                "query": query,
                "matches": matches,
            },
            ensure_ascii=False,
            indent=2,
        )


class MatlabFileGeneratorTool:
    name = "matlab_file_generator"
    description = "Generate and save a MATLAB .m script from model description."

    def __init__(self):
        self.generator = MatlabModelGenerator()

    def _run(
        self,
        description: str,
        output_dir: str = "generated_models",
        file_name: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> str:
        result = self.generator.generate_m_file(
            description=description,
            output_dir=output_dir,
            file_name=file_name,
            model_id=model_id,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)


class WebResearchTool:
    name = "web_research"
    description = (
        "Search the public web for modeling evidence, fetch top pages, persist a local bundle, "
        "and return normalized research docs for downstream MATLAB generation."
    )

    def __init__(self):
        self.server = WebResearchMCPServer()

    def _run(
        self,
        query: str,
        session_id: str = "default",
        max_results: int = 5,
        max_fetch: int = 3,
        allowed_domains: Any = None,
        bundle_name: Optional[str] = None,
    ) -> str:
        payload = self.server.call_tool(
            "research_query",
            {
                "query": str(query or "").strip(),
                "session_id": str(session_id or "default").strip() or "default",
                "max_results": int(max_results),
                "max_fetch": int(max_fetch),
                "allowed_domains": self._normalize_string_list(allowed_domains),
                "bundle_name": str(bundle_name or "").strip(),
            },
        )
        return json.dumps(payload.get("structuredContent", {}), ensure_ascii=False, indent=2)

    @staticmethod
    def _normalize_string_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [segment.strip() for segment in re.split(r"[,;\n]", value) if segment.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("allowed_domains must be a list or a delimited string")


class DynamicLibraryBuildTool:
    name = "dynamic_library_build"
    description = (
        "Build a dynamic library (DLL) from a MATLAB function .m file via the local MCP build pipeline. "
        "It orchestrates toolchain probe, build job creation, input materialization, MATLAB codegen, "
        "CMake configure/build, and artifact collection."
    )

    def __init__(self):
        ensure_runtime_env_defaults()
        self.server = LocalBuildMCPServer()
        self.default_profiles = ["windows_msvc_dll", "windows_gcc_dll", "linux_gcc_shared"]
        self.default_profile = str(os.getenv("MCP_BUILD_DEFAULT_PROFILE", "")).strip()

    def _run(
        self,
        matlab_file: str,
        entry_function: str,
        entry_args_schema: Any = None,
        project_name: Optional[str] = None,
        artifact_name: Optional[str] = None,
        profile: Optional[str] = None,
        build_type: str = "Release",
        target_lang: str = "C++",
        matlab_codegen_mode: str = "matlab_coder",
        generate_report: bool = True,
        generator: str = "",
        platform: str = "",
        extra_defines: Any = None,
        config: Optional[str] = None,
        require_matlab: bool = True,
        probe_profiles: Any = None,
    ) -> str:
        job_id = ""
        pipeline_steps: List[Dict[str, Any]] = []

        try:
            normalized_matlab_file = self._normalize_non_empty_string(matlab_file, "matlab_file")
            normalized_entry_function = self._normalize_non_empty_string(entry_function, "entry_function")
            normalized_entry_args = self._normalize_entry_args_schema(entry_args_schema)
            normalized_probe_profiles = self._normalize_profiles(probe_profiles)
            normalized_extra_defines = self._normalize_extra_defines(extra_defines)

            matlab_path = Path(normalized_matlab_file)
            default_project_name = self._slugify(project_name or matlab_path.stem or normalized_entry_function, fallback="matlab_build_job")
            default_artifact_name = self._slugify(artifact_name or f"{default_project_name}_dll", fallback="matlab_dynamic_lib")

            probe_payload = self._call_tool(
                "probe_toolchains",
                {
                    "profiles": normalized_probe_profiles,
                    "require_matlab": bool(require_matlab),
                },
            )
            pipeline_steps.append(probe_payload)
            probe_result = probe_payload.get("result", {})

            selected_profile, profile_source = self._select_profile(probe_result, profile)
            if not selected_profile:
                return json.dumps(
                    {
                        "status": "error",
                        "message": "No available build profile found. Check toolchain probe results.",
                        "probe": probe_result,
                        "requested_profile": profile or "",
                    },
                    ensure_ascii=False,
                    indent=2,
                )

            requested_profile = str(profile or "").strip()
            if requested_profile and not self._is_profile_available(probe_result, requested_profile):
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Requested profile '{requested_profile}' is unavailable.",
                        "requested_profile": requested_profile,
                        "probe": probe_result,
                    },
                    ensure_ascii=False,
                    indent=2,
                )

            create_payload = self._call_tool(
                "create_build_job",
                {
                    "project_name": default_project_name,
                    "profile": selected_profile,
                    "build_type": build_type,
                    "artifact_name": default_artifact_name,
                },
            )
            pipeline_steps.append(create_payload)
            create_result = create_payload.get("result", {})
            job_id = str(create_result.get("job_id", "")).strip()

            materialize_payload = self._call_tool(
                "materialize_inputs",
                {
                    "job_id": job_id,
                    "matlab_file": normalized_matlab_file,
                    "entry_function": normalized_entry_function,
                    "entry_args_schema": normalized_entry_args,
                },
            )
            pipeline_steps.append(materialize_payload)

            codegen_payload = self._call_tool(
                "matlab_generate_cpp",
                {
                    "job_id": job_id,
                    "target_lang": target_lang,
                    "matlab_codegen_mode": matlab_codegen_mode,
                    "generate_report": bool(generate_report),
                },
            )
            pipeline_steps.append(codegen_payload)

            planned_pipeline = any(
                str(step.get("result", {}).get("status", "")).strip().lower() == "planned" for step in pipeline_steps
            )
            failed_pipeline = any(
                bool(step.get("is_error"))
                or str(step.get("result", {}).get("status", "")).strip().lower() == "failed"
                for step in pipeline_steps
            )

            if not planned_pipeline and not failed_pipeline:
                configure_payload = self._call_tool(
                    "cmake_configure",
                    {
                        "job_id": job_id,
                        "generator": generator,
                        "platform": platform,
                        "build_type": build_type,
                        "extra_defines": normalized_extra_defines,
                    },
                )
                pipeline_steps.append(configure_payload)

                planned_pipeline = any(
                    str(step.get("result", {}).get("status", "")).strip().lower() == "planned"
                    for step in pipeline_steps
                )
                failed_pipeline = any(
                    bool(step.get("is_error"))
                    or str(step.get("result", {}).get("status", "")).strip().lower() == "failed"
                    for step in pipeline_steps
                )

            if not planned_pipeline and not failed_pipeline:
                build_payload = self._call_tool(
                    "cmake_build_dynamic",
                    {
                        "job_id": job_id,
                        "target": default_artifact_name,
                        "config": config or build_type,
                    },
                )
                pipeline_steps.append(build_payload)

                planned_pipeline = any(
                    str(step.get("result", {}).get("status", "")).strip().lower() == "planned"
                    for step in pipeline_steps
                )
                failed_pipeline = any(
                    bool(step.get("is_error"))
                    or str(step.get("result", {}).get("status", "")).strip().lower() == "failed"
                    for step in pipeline_steps
                )

            if not planned_pipeline and not failed_pipeline:
                inspect_payload = self._call_tool("inspect_artifacts", {"job_id": job_id})
                pipeline_steps.append(inspect_payload)

            job_status = self._safe_tool_call("get_job_status", {"job_id": job_id}) if job_id else {}
            job_result = self._safe_tool_call("get_job_result", {"job_id": job_id}) if job_id else {}

            next_action_hint = str(job_result.get("next_action_hint", "")).strip()
            if not next_action_hint:
                for step in pipeline_steps:
                    candidate = str(step.get("result", {}).get("next_action_hint", "")).strip()
                    if candidate:
                        next_action_hint = candidate
                        break

            response = {
                "status": self._derive_overall_status(pipeline_steps, job_status, job_result),
                "job_id": job_id,
                "selected_profile": selected_profile,
                "profile_source": profile_source,
                "project_name": default_project_name,
                "artifact_name": default_artifact_name,
                "workspace": create_result.get("workspace", ""),
                "artifacts_dir": create_result.get("artifacts_dir", ""),
                "matlab_file": normalized_matlab_file,
                "entry_function": normalized_entry_function,
                "entry_args_schema": normalized_entry_args,
                "planned_pipeline": planned_pipeline,
                "pipeline_steps": pipeline_steps,
                "probe": probe_result,
                "job_status": job_status,
                "job_result": job_result,
            }
            message = self._derive_response_message(pipeline_steps, job_status, job_result)
            if message:
                response["message"] = message
            if next_action_hint:
                response["next_action_hint"] = next_action_hint
            return json.dumps(response, ensure_ascii=False, indent=2)
        except Exception as exc:
            failure_payload: Dict[str, Any] = {
                "status": "error",
                "message": str(exc),
                "job_id": job_id,
                "pipeline_steps": pipeline_steps,
            }
            if job_id:
                job_status = self._safe_tool_call("get_job_status", {"job_id": job_id})
                job_result = self._safe_tool_call("get_job_result", {"job_id": job_id})
                if job_status:
                    failure_payload["job_status"] = job_status
                if job_result:
                    failure_payload["job_result"] = job_result
            return json.dumps(failure_payload, ensure_ascii=False, indent=2)

    def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        response = self.server.call_tool(tool_name, arguments)
        return {
            "tool_name": tool_name,
            "arguments": arguments,
            "result": response.get("structuredContent", {}),
            "is_error": bool(response.get("isError", False)),
        }

    def _safe_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.server.call_tool(tool_name, arguments).get("structuredContent", {})
        except Exception:
            return {}

    def _select_profile(self, probe_result: Dict[str, Any], requested_profile: Optional[str]) -> tuple[str, str]:
        normalized_requested = str(requested_profile or "").strip()
        if normalized_requested:
            return normalized_requested, "argument"

        recommended = str(probe_result.get("recommended_profile", "")).strip()
        if recommended:
            return recommended, "probe_recommended"

        if self.default_profile and self._is_profile_available(probe_result, self.default_profile):
            return self.default_profile, "env_default"

        for item in probe_result.get("profiles", []):
            candidate = str(item.get("profile", "")).strip()
            if candidate and item.get("available"):
                return candidate, "first_available"
        return "", ""

    @staticmethod
    def _is_profile_available(probe_result: Dict[str, Any], profile: str) -> bool:
        normalized_profile = str(profile or "").strip()
        for item in probe_result.get("profiles", []):
            if str(item.get("profile", "")).strip() == normalized_profile:
                return bool(item.get("available"))
        return False

    @staticmethod
    def _derive_overall_status(
        pipeline_steps: List[Dict[str, Any]], job_status: Dict[str, Any], job_result: Dict[str, Any]
    ) -> str:
        for step in pipeline_steps:
            result = step.get("result", {})
            if step.get("is_error") or str(result.get("status", "")).strip().lower() == "failed":
                return "failed"

        result_status = str(job_result.get("status", "")).strip().lower()
        manifest_status = str(job_status.get("status", "")).strip().lower()
        if result_status == "succeeded" or manifest_status == "succeeded":
            return "success"
        if any(str(step.get("result", {}).get("status", "")).strip().lower() == "planned" for step in pipeline_steps):
            return "planned"
        if result_status == "failed" or manifest_status == "failed":
            return "failed"
        if result_status or manifest_status:
            return result_status or manifest_status
        return "ok"

    @staticmethod
    def _derive_response_message(
        pipeline_steps: List[Dict[str, Any]], job_status: Dict[str, Any], job_result: Dict[str, Any]
    ) -> str:
        for step in pipeline_steps:
            result = step.get("result", {}) if isinstance(step.get("result", {}), dict) else {}
            status = str(result.get("status", "")).strip().lower()
            if step.get("is_error") or status == "failed":
                message = str(result.get("message", "")).strip()
                if message:
                    return message

        result_error = str(job_result.get("error_summary", "")).strip()
        if result_error:
            return result_error

        status_error = str(job_status.get("error_summary", "")).strip()
        if status_error:
            return status_error

        return ""

    def _normalize_profiles(self, value: Any) -> List[str]:
        normalized = self._normalize_string_list(value)
        return normalized or list(self.default_profiles)

    @staticmethod
    def _normalize_non_empty_string(value: Any, field_name: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{field_name} is required")
        return text

    def _normalize_entry_args_schema(self, value: Any) -> List[Dict[str, Any]]:
        raw_items = self._parse_structured_value(value, default=[])
        if raw_items is None:
            raw_items = []
        if not isinstance(raw_items, list):
            raise ValueError("entry_args_schema must be a list or a JSON/Python-literal list string")

        normalized: List[Dict[str, Any]] = []
        for index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                raise ValueError(f"entry_args_schema[{index}] must be an object")

            name = str(item.get("name", "")).strip()
            arg_type = str(item.get("type", "")).strip()
            if not name or not arg_type:
                raise ValueError(f"entry_args_schema[{index}] requires non-empty name and type")

            normalized_item: Dict[str, Any] = {"name": name, "type": arg_type}
            shape = item.get("shape")
            if shape not in (None, ""):
                if not isinstance(shape, (list, tuple)):
                    raise ValueError(f"entry_args_schema[{index}].shape must be a list of non-negative integers")
                normalized_shape = [int(dim) for dim in shape]
                if any(dim < 0 for dim in normalized_shape):
                    raise ValueError(f"entry_args_schema[{index}].shape must contain non-negative integers")
                normalized_item["shape"] = normalized_shape
            normalized.append(normalized_item)
        return normalized

    def _normalize_extra_defines(self, value: Any) -> Dict[str, Any]:
        raw = self._parse_structured_value(value, default={})
        if raw is None:
            return {}
        if isinstance(raw, dict):
            return {str(key).strip(): self._coerce_scalar(val) for key, val in raw.items() if str(key).strip()}
        if isinstance(raw, str):
            pairs = [segment.strip() for segment in re.split(r"[,;\n]", raw) if segment.strip()]
            defines: Dict[str, Any] = {}
            for pair in pairs:
                if "=" in pair:
                    key, raw_value = pair.split("=", 1)
                    key = key.strip()
                    if key:
                        defines[key] = self._coerce_scalar(raw_value.strip())
                else:
                    defines[pair] = True
            return defines
        raise ValueError("extra_defines must be an object or a JSON/Python-literal object string")

    def _normalize_string_list(self, value: Any) -> List[str]:
        parsed = self._parse_structured_value(value, default=[])
        if parsed is None:
            return []
        if isinstance(parsed, str):
            items = [segment.strip() for segment in re.split(r"[,;\n]", parsed) if segment.strip()]
            return items
        if isinstance(parsed, (list, tuple, set)):
            return [str(item).strip() for item in parsed if str(item).strip()]
        raise ValueError("probe_profiles must be a list or a delimited string")

    @staticmethod
    def _parse_structured_value(value: Any, default: Any = None) -> Any:
        if value is None:
            return default
        if isinstance(value, (dict, list, tuple, set)):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return default
            if stripped[0] in "[{(":
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    try:
                        return ast.literal_eval(stripped)
                    except (ValueError, SyntaxError):
                        return value
            return value
        return value

    @staticmethod
    def _coerce_scalar(value: Any) -> Any:
        if isinstance(value, (bool, int, float)):
            return value
        text = str(value).strip()
        if not text:
            return ""
        lowered = text.lower()
        if lowered in {"true", "yes", "on"}:
            return True
        if lowered in {"false", "no", "off"}:
            return False
        try:
            return int(text)
        except ValueError:
            pass
        try:
            return float(text)
        except ValueError:
            pass
        return text

    @staticmethod
    def _slugify(value: str, fallback: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip())
        normalized = normalized.strip("_-")
        return normalized or fallback


def list_supported_models() -> str:
    catalog = get_model_catalog()
    items = [
        {
            "model_id": m["model_id"],
            "name": m["name"],
            "category": m["category"],
            "template_family": m.get("template_family", ""),
            "domain_tags": m.get("domain_tags", []),
            "equation_fragments": m.get("equation_fragments", []),
            "description": m["description"],
            "examples": m.get("examples", []),
        }
        for m in catalog
    ]
    return json.dumps({"status": "success", "models": items, "count": len(items)}, ensure_ascii=False, indent=2)

