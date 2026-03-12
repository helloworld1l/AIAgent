"""
ModelSpec JSON Schema validator + semantic validator + auto repair loop.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Callable, Dict, List, Tuple

from agents.model_spec_schema import MODEL_SPEC_JSON_SCHEMA
from knowledge_base.rag_retriever import MatlabRAGRetriever

try:
    from jsonschema import Draft202012Validator  # type: ignore
except Exception:
    Draft202012Validator = None  # type: ignore


class ModelSpecValidator:
    def __init__(self, retriever: MatlabRAGRetriever):
        self.retriever = retriever
        self.model_map = {m["model_id"]: m for m in retriever.list_supported_models()}
        self.schema_validator = (
            Draft202012Validator(MODEL_SPEC_JSON_SCHEMA)
            if Draft202012Validator is not None
            else None
        )

    def validate_with_auto_repair(
        self,
        initial_spec: Dict[str, Any],
        query: str,
        retrieved_docs: List[Dict[str, Any]],
        repair_fn: Callable[..., Dict[str, Any]] | None = None,
        max_repair_rounds: int = 2,
    ) -> Dict[str, Any]:
        current_spec: Dict[str, Any] = copy.deepcopy(initial_spec) if isinstance(initial_spec, dict) else {}
        trace: List[Dict[str, Any]] = []
        rounds = max(0, int(max_repair_rounds))

        for round_idx in range(rounds + 1):
            schema_result = self.validate_schema(current_spec)
            semantic_result = self.validate(current_spec, retrieved_docs)
            is_valid = schema_result["valid"] and semantic_result["valid"]

            trace.append(
                {
                    "round": round_idx,
                    "schema_valid": schema_result["valid"],
                    "semantic_valid": semantic_result["valid"],
                    "schema_errors": schema_result["errors"],
                    "semantic_errors": semantic_result["errors"],
                    "semantic_warnings": semantic_result["warnings"],
                    "spec_source": str(current_spec.get("_build_source", "")),
                }
            )

            if is_valid:
                return {
                    "valid": True,
                    "normalized_spec": semantic_result["normalized_spec"],
                    "schema_validation": schema_result,
                    "semantic_validation": semantic_result,
                    "repair_used": round_idx > 0,
                    "repair_trace": trace,
                }

            if round_idx >= rounds or repair_fn is None:
                break

            repaired = repair_fn(
                query=query,
                invalid_spec=current_spec,
                schema_errors=schema_result["errors"],
                validation_errors=semantic_result["errors"],
                retrieved_docs=retrieved_docs,
            )
            repaired_spec = repaired.get("spec") if isinstance(repaired, dict) else None
            repair_error = repaired.get("error", "unknown_repair_error") if isinstance(repaired, dict) else "unknown_repair_error"

            if not isinstance(repaired_spec, dict):
                trace[-1]["repair_status"] = "failed"
                trace[-1]["repair_error"] = repair_error
                break
            if repaired_spec == current_spec:
                trace[-1]["repair_status"] = "failed"
                trace[-1]["repair_error"] = "repair_no_change"
                break

            trace[-1]["repair_status"] = "applied"
            trace[-1]["repair_source"] = repaired_spec.get("_build_source", "llm_repair")
            current_spec = repaired_spec

        final_schema = self.validate_schema(current_spec)
        final_semantic = self.validate(current_spec, retrieved_docs)
        return {
            "valid": False,
            "normalized_spec": final_semantic["normalized_spec"],
            "schema_validation": final_schema,
            "semantic_validation": final_semantic,
            "repair_used": any(item.get("repair_status") == "applied" for item in trace),
            "repair_trace": trace,
        }

    def validate_schema(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(spec, dict):
            return {"valid": False, "errors": ["ModelSpec 必须是对象(JSON object)"]}

        if self.schema_validator is not None:
            errors = sorted(self.schema_validator.iter_errors(spec), key=lambda e: list(e.path))
            if not errors:
                return {"valid": True, "errors": []}
            messages: List[str] = []
            for err in errors[:20]:
                path = ".".join(str(x) for x in err.absolute_path) or "$"
                messages.append(f"{path}: {err.message}")
            return {"valid": False, "errors": messages}

        # Minimal fallback schema checks when jsonschema is not installed.
        required = MODEL_SPEC_JSON_SCHEMA.get("required", [])
        missing = [f for f in required if f not in spec]
        if missing:
            return {"valid": False, "errors": [f"缺少必填字段: {', '.join(missing)}"]}
        if not isinstance(spec.get("task_goal"), str) or not spec.get("task_goal", "").strip():
            return {"valid": False, "errors": ["task_goal 必须是非空字符串"]}
        if not isinstance(spec.get("model_id"), str) or not re.fullmatch(r"[A-Za-z0-9_]+", spec.get("model_id", "")):
            return {"valid": False, "errors": ["model_id 格式非法"]}
        if not isinstance(spec.get("parameters"), dict):
            return {"valid": False, "errors": ["parameters 必须是对象"]}
        sim = spec.get("simulation_plan")
        stop_time = _to_float(sim.get("stop_time")) if isinstance(sim, dict) else None
        if not isinstance(sim, dict) or stop_time is None or stop_time <= 0:
            return {"valid": False, "errors": ["simulation_plan.stop_time 必须是正数"]}
        return {"valid": True, "errors": []}

    def validate(self, spec: Dict[str, Any], retrieved_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []
        normalized = copy.deepcopy(spec)

        model_id = str(normalized.get("model_id", "")).strip()
        if not model_id:
            inferred = self.retriever.infer_candidate_models(retrieved_docs, top_k=1)
            if inferred:
                model_id = inferred[0]["model_id"]
                warnings.append(f"未提供model_id，已推断为 {model_id}")
            else:
                model_id = "transfer_function_step"
                warnings.append("未提供model_id，已使用默认 transfer_function_step")
        normalized["model_id"] = model_id

        if model_id not in self.model_map:
            errors.append(f"不支持的 model_id: {model_id}")
            return {
                "valid": False,
                "errors": errors,
                "warnings": warnings,
                "normalized_spec": normalized,
            }

        defaults = dict(self.model_map[model_id].get("default_params", {}))
        params = normalized.get("parameters", {})
        if not isinstance(params, dict):
            params = {}
        merged_params = dict(defaults)
        merged_params.update(params)

        if "simulation_plan" not in normalized or not isinstance(normalized["simulation_plan"], dict):
            normalized["simulation_plan"] = {}
        if "stop_time" in merged_params and "stop_time" not in normalized["simulation_plan"]:
            normalized["simulation_plan"]["stop_time"] = merged_params["stop_time"]
        elif "stop_time" not in normalized["simulation_plan"]:
            normalized["simulation_plan"]["stop_time"] = 10

        stop_time = _to_float(normalized["simulation_plan"].get("stop_time"))
        if stop_time is None or stop_time <= 0:
            warnings.append("stop_time 非法，已重置为 10")
            stop_time = 10.0
        normalized["simulation_plan"]["stop_time"] = stop_time
        merged_params["stop_time"] = stop_time

        # convert numeric-like strings
        for key, val in list(merged_params.items()):
            if isinstance(val, str):
                num = _to_float(val)
                if num is not None and _is_simple_number_str(val):
                    merged_params[key] = num

        if model_id == "transfer_function_step":
            for key in ("numerator", "denominator"):
                if key not in merged_params:
                    errors.append(f"缺少参数: {key}")
                elif not _looks_like_vector(str(merged_params[key])):
                    errors.append(f"{key} 格式应类似 [1 3 2]")

        if model_id == "state_space_response":
            for key in ("A", "B", "C", "D"):
                if key not in merged_params:
                    errors.append(f"缺少参数: {key}")
            if not errors:
                dims_ok, dim_err = _validate_state_space_dims(
                    str(merged_params["A"]),
                    str(merged_params["B"]),
                    str(merged_params["C"]),
                    str(merged_params["D"]),
                )
                if not dims_ok:
                    errors.append(dim_err)

        if model_id == "pid_simulink_loop":
            for key in ("kp", "ki", "kd"):
                value = _to_float(merged_params.get(key))
                if value is None:
                    errors.append(f"参数 {key} 需要数值")
                else:
                    merged_params[key] = value
            for key in ("numerator", "denominator"):
                if key not in merged_params:
                    errors.append(f"缺少参数: {key}")

        if model_id == "rocket_launch_1d":
            required_numeric = (
                "mass0",
                "fuel_mass",
                "burn_rate",
                "thrust",
                "drag_coeff",
                "area",
                "air_density",
                "g",
                "dt",
            )
            for key in required_numeric:
                value = _to_float(merged_params.get(key))
                if value is None:
                    errors.append(f"参数 {key} 需要数值")
                    continue
                merged_params[key] = value
                if value <= 0:
                    errors.append(f"参数 {key} 必须大于0")

            fuel_mass = _to_float(merged_params.get("fuel_mass"))
            mass0 = _to_float(merged_params.get("mass0"))
            if fuel_mass is not None and mass0 is not None and fuel_mass >= mass0:
                warnings.append("fuel_mass 不应大于或等于 mass0，已建议用户调整")

        normalized.setdefault("assumptions", [])
        normalized.setdefault("required_outputs", ["plot"])
        normalized.setdefault("missing_info", [])
        normalized["parameters"] = merged_params

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "normalized_spec": normalized,
        }


def _to_float(value: Any) -> float | None:
    try:
        if isinstance(value, bool):
            return None
        return float(value)
    except Exception:
        return None


def _is_simple_number_str(text: str) -> bool:
    return bool(re.fullmatch(r"\s*-?\d+(?:\.\d+)?\s*", text))


def _looks_like_vector(text: str) -> bool:
    return bool(re.fullmatch(r"\[\s*[-0-9\.\s;,\+eE]+\s*\]", text))


def _parse_matrix(text: str) -> List[List[float]] | None:
    if not _looks_like_vector(text):
        return None
    inner = text.strip()[1:-1].strip()
    if not inner:
        return []
    rows = [r.strip() for r in inner.split(";")]
    parsed: List[List[float]] = []
    for row in rows:
        if not row:
            continue
        parts = [p for p in re.split(r"[\s,]+", row) if p]
        row_vals: List[float] = []
        for p in parts:
            try:
                row_vals.append(float(p))
            except Exception:
                return None
        parsed.append(row_vals)
    if not parsed:
        return None
    row_len = len(parsed[0])
    if any(len(r) != row_len for r in parsed):
        return None
    return parsed


def _validate_state_space_dims(A: str, B: str, C: str, D: str) -> Tuple[bool, str]:
    mat_a = _parse_matrix(A)
    mat_b = _parse_matrix(B)
    mat_c = _parse_matrix(C)
    mat_d = _parse_matrix(D)
    if None in (mat_a, mat_b, mat_c, mat_d):
        return False, "状态空间矩阵格式非法，请使用如 [0 1; -2 -3]"

    assert mat_a is not None
    assert mat_b is not None
    assert mat_c is not None
    assert mat_d is not None
    n = len(mat_a)
    if len(mat_a[0]) != n:
        return False, "A 必须是方阵"
    if len(mat_b) != n:
        return False, "B 的行数必须与 A 的维度一致"
    if len(mat_c[0]) != n:
        return False, "C 的列数必须与 A 的维度一致"
    m = len(mat_b[0])
    p = len(mat_c)
    if len(mat_d) != p or len(mat_d[0]) != m:
        return False, "D 的维度必须是 p×m（p=输出数, m=输入数）"
    return True, ""
