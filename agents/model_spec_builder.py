"""
Build and repair ModelSpec from user query + retrieved RAG evidence.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

import requests

from agents.model_spec_schema import MODEL_SPEC_JSON_SCHEMA
from config.settings import settings
from knowledge_base.rag_retriever import MatlabRAGRetriever


class ModelSpecBuilder:
    def __init__(self, retriever: MatlabRAGRetriever):
        self.retriever = retriever
        self._schema_json = json.dumps(MODEL_SPEC_JSON_SCHEMA, ensure_ascii=False)

    def build_spec(self, query: str, retrieved_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        candidates = self.retriever.infer_candidate_models(retrieved_docs, top_k=3)
        primary_model_id = candidates[0]["model_id"] if candidates else "transfer_function_step"

        llm_spec, llm_error = self._build_with_llm(query, retrieved_docs, candidates)
        if llm_spec is not None:
            filled_spec = self._fill_spec_defaults(
                spec=llm_spec,
                query=query,
                fallback_model_id=primary_model_id,
            )
            filled_spec["_build_source"] = "llm_rag"
            filled_spec["_candidate_models"] = candidates
            return {"spec": filled_spec, "used_llm": True, "llm_error": ""}

        heuristic = self._build_heuristic(query, primary_model_id)
        heuristic["_build_source"] = "heuristic_rag"
        heuristic["_candidate_models"] = candidates
        return {"spec": heuristic, "used_llm": False, "llm_error": llm_error}

    def build_heuristic_spec(self, query: str, retrieved_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        candidates = self.retriever.infer_candidate_models(retrieved_docs, top_k=3)
        primary_model_id = candidates[0]["model_id"] if candidates else "transfer_function_step"
        heuristic = self._build_heuristic(query, primary_model_id)
        heuristic["_build_source"] = "heuristic_rag_forced"
        heuristic["_candidate_models"] = candidates
        return heuristic

    def repair_spec_with_llm(
        self,
        query: str,
        invalid_spec: Dict[str, Any],
        schema_errors: List[str],
        validation_errors: List[str],
        retrieved_docs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        candidates = self.retriever.infer_candidate_models(retrieved_docs, top_k=3)
        evidence_lines = self._format_evidence_lines(retrieved_docs)
        candidate_lines = [f"{c['model_id']} ({c['name']})" for c in candidates] or ["transfer_function_step"]

        system_prompt = (
            "你是MATLAB建模规格修复器。"
            "你的任务是修复不合法的ModelSpec。"
            "只输出JSON对象，不要markdown，不要解释。"
        )
        user_prompt = (
            f"用户需求: {query}\n"
            f"候选模型: {', '.join(candidate_lines)}\n"
            f"检索证据:\n{evidence_lines}\n\n"
            f"当前不合法的ModelSpec:\n{json.dumps(invalid_spec, ensure_ascii=False)}\n\n"
            "Schema错误:\n"
            + "\n".join(f"- {e}" for e in schema_errors[:12])
            + "\n语义校验错误:\n"
            + "\n".join(f"- {e}" for e in validation_errors[:12])
            + "\n\n请输出修复后的完整JSON，必须满足以下JSON Schema：\n"
            + self._schema_json
        )

        repaired, error = self._call_ollama_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            num_predict=max(220, min(420, int(settings.OLLAMA_NUM_PREDICT) * 3)),
            temperature=0.1,
        )
        if repaired is None:
            return {"spec": None, "error": error}

        filled = self._fill_spec_defaults(
            spec=repaired,
            query=query,
            fallback_model_id=(candidates[0]["model_id"] if candidates else "transfer_function_step"),
        )
        filled["_build_source"] = "llm_repair"
        filled["_repair_error_count"] = len(schema_errors) + len(validation_errors)
        return {"spec": filled, "error": ""}

    def _build_with_llm(
        self,
        query: str,
        retrieved_docs: List[Dict[str, Any]],
        candidates: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any] | None, str]:
        evidence_lines = self._format_evidence_lines(retrieved_docs)
        candidate_lines = [f"{c['model_id']} ({c['name']})" for c in candidates] or ["transfer_function_step"]
        system_prompt = (
            "你是MATLAB建模规划器。"
            "请根据用户需求和检索证据输出ModelSpec。"
            "只输出JSON对象，不要markdown，不要额外文本。"
        )
        user_prompt = (
            f"用户需求: {query}\n"
            f"候选模型: {', '.join(candidate_lines)}\n"
            f"证据:\n{evidence_lines}\n\n"
            "输出必须严格满足以下JSON Schema：\n"
            + self._schema_json
            + "\n\n补充要求："
            "1) model_id优先从候选模型中选择；"
            "2) 不能确定的参数写入 missing_info；"
            "3) stop_time 必须>0。"
        )

        return self._call_ollama_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            num_predict=max(200, min(360, int(settings.OLLAMA_NUM_PREDICT) * 2)),
            temperature=0.2,
        )

    def _format_evidence_lines(self, retrieved_docs: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for idx, item in enumerate(retrieved_docs[:8], 1):
            payload = item.get("payload", {})
            model_id = payload.get("model_id", "")
            short = item.get("text", "")[:220]
            lines.append(f"[{idx}] model={model_id}; score={item.get('score', 0)}; text={short}")
        return "\n".join(lines)

    def _call_ollama_json(
        self,
        system_prompt: str,
        user_prompt: str,
        num_predict: int,
        temperature: float,
    ) -> Tuple[Dict[str, Any] | None, str]:
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
                "top_p": 0.8,
                "num_predict": num_predict,
            },
        }

        try:
            resp = requests.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json=payload,
                timeout=(10, settings.OLLAMA_TIMEOUT_SEC),
            )
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "").strip()
            if not content:
                return None, "empty_llm_content"
            parsed = _extract_json_obj(content)
            if parsed is None:
                return None, "llm_json_parse_failed"
            return parsed, ""
        except Exception as exc:
            return None, str(exc)

    def _fill_spec_defaults(
        self,
        spec: Dict[str, Any],
        query: str,
        fallback_model_id: str,
    ) -> Dict[str, Any]:
        result = dict(spec) if isinstance(spec, dict) else {}
        model_id = str(result.get("model_id", "")).strip() or fallback_model_id
        defaults = self.retriever.get_model_defaults(model_id)

        result.setdefault("task_goal", query)
        result["model_id"] = model_id
        result.setdefault("assumptions", [])
        result.setdefault("parameters", {})
        result.setdefault("required_outputs", ["plot"])
        result.setdefault("missing_info", [])

        if not isinstance(result["parameters"], dict):
            result["parameters"] = {}
        merged = dict(defaults)
        merged.update(result["parameters"])
        result["parameters"] = merged

        simulation_plan = result.get("simulation_plan", {})
        if not isinstance(simulation_plan, dict):
            simulation_plan = {}
        stop_time = simulation_plan.get("stop_time", merged.get("stop_time", 10))
        try:
            stop_time = float(stop_time)
        except Exception:
            stop_time = float(merged.get("stop_time", 10))
        if stop_time <= 0:
            stop_time = float(merged.get("stop_time", 10) or 10)
        simulation_plan["stop_time"] = stop_time
        result["simulation_plan"] = simulation_plan
        result["parameters"]["stop_time"] = stop_time
        return result

    def _build_heuristic(self, query: str, model_id: str) -> Dict[str, Any]:
        defaults = self.retriever.get_model_defaults(model_id)
        params = dict(defaults)
        text = query

        numeric_keys = (
            "kp",
            "ki",
            "kd",
            "m",
            "c",
            "k",
            "dt",
            "ts",
            "na",
            "nb",
            "nk",
            "samples",
            "steps",
            "mass0",
            "fuel_mass",
            "burn_rate",
            "thrust",
            "drag_coeff",
            "area",
            "air_density",
            "g",
            "launch_angle_deg",
            "init_speed",
            "burn_time",
            "mu",
            "earth_radius",
            "altitude0",
            "v0",
            "mass",
            "water_density",
            "displaced_volume",
            "x0",
            "y0",
            "target_speed_x",
            "target_speed_y",
            "process_noise",
            "measurement_noise",
            "red0",
            "blue0",
            "alpha",
            "beta",
        )
        for key in numeric_keys:
            found = _extract_named_number(text, key)
            if found is not None:
                params[key] = found

        stop_time = _extract_stop_time(text)
        if stop_time is not None:
            params["stop_time"] = stop_time

        vectors = re.findall(r"\[[0-9\.\-\s;\,]+\]", text)
        if model_id == "transfer_function_step":
            if len(vectors) >= 1:
                params["numerator"] = vectors[0]
            if len(vectors) >= 2:
                params["denominator"] = vectors[1]
        elif model_id == "state_space_response":
            if len(vectors) >= 1:
                params["A"] = vectors[0]
            if len(vectors) >= 2:
                params["B"] = vectors[1]
            if len(vectors) >= 3:
                params["C"] = vectors[2]
            if len(vectors) >= 4:
                params["D"] = vectors[3]
        else:
            alias_map: Dict[str, List[str]] = {}
            if model_id == "rocket_launch_1d":
                alias_map = {
                    "mass0": ["mass0", "initial mass", "\u521d\u59cb\u8d28\u91cf", "\u603b\u8d28\u91cf"],
                    "fuel_mass": ["fuel_mass", "fuel mass", "\u71c3\u6599\u8d28\u91cf", "\u63a8\u8fdb\u5242\u8d28\u91cf"],
                    "burn_rate": ["burn_rate", "burn rate", "\u71c3\u70e7\u901f\u7387", "\u6d88\u8017\u901f\u7387"],
                    "thrust": ["thrust", "\u63a8\u529b"],
                    "drag_coeff": ["drag_coeff", "drag coefficient", "\u963b\u529b\u7cfb\u6570", "cd"],
                    "area": ["area", "frontal area", "\u8fce\u98ce\u9762\u79ef", "\u622a\u9762\u79ef"],
                    "air_density": ["air_density", "air density", "\u7a7a\u6c14\u5bc6\u5ea6", "rho"],
                    "g": ["g", "gravity", "\u91cd\u529b\u52a0\u901f\u5ea6"],
                    "dt": ["dt", "\u6b65\u957f", "\u65f6\u95f4\u6b65\u957f"],
                }
            elif model_id == "missile_flight_2d":
                alias_map = {
                    "mass0": ["mass0", "initial mass", "\u521d\u59cb\u8d28\u91cf", "\u603b\u8d28\u91cf"],
                    "thrust": ["thrust", "\u63a8\u529b"],
                    "drag_coeff": ["drag_coeff", "drag coefficient", "\u963b\u529b\u7cfb\u6570", "cd"],
                    "area": ["area", "frontal area", "\u8fce\u98ce\u9762\u79ef", "\u622a\u9762\u79ef"],
                    "air_density": ["air_density", "air density", "\u7a7a\u6c14\u5bc6\u5ea6", "rho"],
                    "launch_angle_deg": ["launch_angle_deg", "launch angle", "\u53d1\u5c04\u89d2", "\u89d2\u5ea6"],
                    "init_speed": ["init_speed", "initial speed", "\u521d\u901f\u5ea6", "\u521d\u59cb\u901f\u5ea6"],
                    "burn_time": ["burn_time", "burn time", "\u71c3\u70e7\u65f6\u95f4", "\u63a8\u529b\u65f6\u95f4"],
                    "dt": ["dt", "\u6b65\u957f", "\u65f6\u95f4\u6b65\u957f"],
                }
            elif model_id == "satellite_orbit_2body":
                alias_map = {
                    "mu": ["mu", "gravitational parameter", "\u5f15\u529b\u53c2\u6570"],
                    "earth_radius": ["earth_radius", "earth radius", "\u5730\u7403\u534a\u5f84"],
                    "altitude0": ["altitude0", "altitude", "\u8f68\u9053\u9ad8\u5ea6", "\u521d\u59cb\u9ad8\u5ea6"],
                    "v0": ["v0", "orbital speed", "initial speed", "\u8f68\u9053\u901f\u5ea6", "\u521d\u59cb\u901f\u5ea6"],
                    "dt": ["dt", "\u6b65\u957f", "\u65f6\u95f4\u6b65\u957f"],
                }
            elif model_id == "torpedo_underwater_launch_1d":
                alias_map = {
                    "mass": ["mass", "\u8d28\u91cf"],
                    "thrust": ["thrust", "\u63a8\u529b"],
                    "drag_coeff": ["drag_coeff", "drag coefficient", "\u963b\u529b\u7cfb\u6570", "cd"],
                    "area": ["area", "cross section", "\u622a\u9762\u79ef", "\u6a2a\u622a\u9762\u79ef"],
                    "water_density": ["water_density", "water density", "\u6c34\u5bc6\u5ea6", "rho"],
                    "displaced_volume": ["displaced_volume", "displaced volume", "\u6392\u6c34\u4f53\u79ef", "\u6392\u5f00\u4f53\u79ef"],
                    "dt": ["dt", "\u6b65\u957f", "\u65f6\u95f4\u6b65\u957f"],
                }
            elif model_id == "radar_target_tracking_2d":
                alias_map = {
                    "dt": ["dt", "\u6b65\u957f", "\u65f6\u95f4\u6b65\u957f"],
                    "steps": ["steps", "\u6b65\u6570"],
                    "process_noise": ["process_noise", "\u8fc7\u7a0b\u566a\u58f0"],
                    "measurement_noise": ["measurement_noise", "measurement std", "\u6d4b\u91cf\u566a\u58f0"],
                    "x0": ["x0", "\u521d\u59cbx", "\u521d\u59cb\u6a2a\u5411\u4f4d\u7f6e"],
                    "y0": ["y0", "\u521d\u59cby", "\u521d\u59cb\u7eb5\u5411\u4f4d\u7f6e"],
                    "target_speed_x": ["target_speed_x", "vx", "\u76ee\u6807x\u901f\u5ea6", "\u76ee\u6807\u6a2a\u5411\u901f\u5ea6"],
                    "target_speed_y": ["target_speed_y", "vy", "\u76ee\u6807y\u901f\u5ea6", "\u76ee\u6807\u7eb5\u5411\u901f\u5ea6"],
                }
            elif model_id == "lanchester_battle_attrition":
                alias_map = {
                    "red0": ["red0", "red force", "\u7ea2\u65b9\u5175\u529b", "\u7ea2\u65b9\u521d\u59cb\u5175\u529b"],
                    "blue0": ["blue0", "blue force", "\u84dd\u65b9\u5175\u529b", "\u84dd\u65b9\u521d\u59cb\u5175\u529b"],
                    "alpha": ["alpha", "blue firepower", "\u84dd\u65b9\u6740\u4f24\u7cfb\u6570"],
                    "beta": ["beta", "red firepower", "\u7ea2\u65b9\u6740\u4f24\u7cfb\u6570"],
                    "dt": ["dt", "\u6b65\u957f", "\u65f6\u95f4\u6b65\u957f"],
                }

            for key, aliases in alias_map.items():
                for alias in aliases:
                    value = _extract_named_number(text, alias)
                    if value is not None:
                        params[key] = value
                        break

        return {
            "task_goal": query,
            "model_id": model_id,
            "assumptions": ["\u4f7f\u7528\u9ed8\u8ba4\u53c2\u6570\u8865\u5168\u672a\u660e\u786e\u6307\u5b9a\u9879"],
            "parameters": params,
            "simulation_plan": {
                "stop_time": params.get("stop_time", defaults.get("stop_time", 10))
            },
            "required_outputs": ["plot"],
            "missing_info": [],
        }


def _extract_json_obj(text: str) -> Dict[str, Any] | None:
    try:
        return json.loads(text)
    except Exception:
        pass

    code_match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if code_match:
        try:
            return json.loads(code_match.group(1))
        except Exception:
            pass

    brace_match = re.search(r"(\{.*\})", text, re.DOTALL)
    if brace_match:
        candidate = brace_match.group(1)
        try:
            return json.loads(candidate)
        except Exception:
            return None
    return None


def _extract_named_number(text: str, key: str) -> float | None:
    pattern = rf"{re.escape(key)}\s*[=:：]?\s*(-?\d+(?:\.\d+)?)"
    matched = re.search(pattern, text, re.IGNORECASE)
    if matched:
        return float(matched.group(1))
    return None


def _extract_stop_time(text: str) -> float | None:
    patterns = [
        r"(?:仿真|模拟|运行)\s*(\d+(?:\.\d+)?)\s*秒",
        r"stop[_\s-]?time\s*[=:：]?\s*(\d+(?:\.\d+)?)",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return None

