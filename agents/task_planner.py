"""
Unified task planner for chat and MATLAB model generation.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List

import requests

from agents.dll_build_support import mentions_dynamic_library
from config.settings import settings


class RAGTaskPlanner:
    def plan(
        self,
        query: str,
        retrieved_docs: List[Dict[str, Any]],
        recent_history: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        wants_web_research = self._wants_web_research(query)
        rule_plan = self._rule_based_plan(query, retrieved_docs)
        llm_plan, llm_error = self._llm_plan(query, retrieved_docs, recent_history)

        if llm_plan is not None:
            task_type = llm_plan.get("task_type", "")
            confidence = _to_float(llm_plan.get("confidence"), default=0.5)
            reason = str(llm_plan.get("reason", "")).strip()
            if task_type in {"matlab_generation", "matlab_generation_dll", "chat", "clarify"}:
                return {
                    "task_type": task_type,
                    "confidence": confidence,
                    "reason": reason or "llm_plan",
                    "source": "llm",
                    "llm_error": "",
                    "rule_fallback": rule_plan,
                    "wants_dynamic_library": bool(llm_plan.get("wants_dynamic_library", False))
                    or task_type == "matlab_generation_dll",
                    "wants_web_research": wants_web_research,
                }

        merged = dict(rule_plan)
        merged["source"] = "rule"
        merged["llm_error"] = llm_error
        merged["wants_web_research"] = wants_web_research
        return merged

    def _wants_web_research(self, query: str) -> bool:
        lowered = str(query or "").lower()
        explicit_markers = [
            "联网",
            "网上",
            "在线",
            "网页",
            "从网上",
            "外部资料",
            "搜索",
            "搜一下",
            "web",
            "internet",
        ]
        if any(marker in lowered for marker in explicit_markers):
            return True
        return bool(re.search(r"查(?:一下)?资料", lowered))

    def _rule_based_plan(self, query: str, retrieved_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        lowered = query.lower()
        generation_actions = [
            "build",
            "generate",
            "create",
            "model",
            "simulate",
            "compile",
            "export",
            "\u751f\u6210",
            "\u6784\u5efa",
            "\u5efa\u7acb",
            "\u521b\u5efa",
            "\u8bbe\u8ba1",
            "\u5b9e\u73b0",
            "\u4eff\u771f",
            "\u5efa\u6a21",
            "\u7f16\u8bd1",
            "\u5bfc\u51fa",
            "\u505a\u4e2a",
        ]
        has_action = any(a in lowered for a in generation_actions)
        model_markers = [
            "matlab",
            ".m",
            "simulink",
            "pid",
            "kalman",
            "mpc",
            "ode45",
            "missile",
            "torpedo",
            "submarine",
            "satellite",
            "orbit",
            "radar",
            "tracking",
            "battlefield",
            "lanchester",
            "\u6a21\u578b",
            "\u4f20\u9012\u51fd\u6570",
            "\u72b6\u6001\u7a7a\u95f4",
            "\u706b\u7bad",
            "\u53d1\u5c04",
            "\u5bfc\u5f39",
            "\u9c7c\u96f7",
            "\u6f5c\u8247",
            "\u6c34\u4e0b",
            "\u536b\u661f",
            "\u8f68\u9053",
            "\u96f7\u8fbe",
            "\u8ddf\u8e2a",
            "\u6218\u573a",
            "\u6001\u52bf",
            "\u7ea2\u84dd\u5bf9\u6297",
            "\u5175\u529b\u6d88\u8017",
        ]
        ask_markers = [
            "\u89e3\u91ca",
            "\u533a\u522b",
            "\u662f\u4ec0\u4e48",
            "\u4e3a\u4ec0\u4e48",
            "\u5982\u4f55",
            "\u600e\u4e48",
            "\u539f\u7406",
            "\u4ecb\u7ecd",
            "\u5bf9\u6bd4",
            "\u542b\u4e49",
            "what is",
            "why",
            "how",
        ]
        wants_dynamic_library = mentions_dynamic_library(query)
        if not has_action and any(m in query for m in ask_markers):
            return {
                "task_type": "chat",
                "confidence": 0.9,
                "reason": "rule_question_without_generation_action",
                "has_generation_action": False,
                "wants_dynamic_library": wants_dynamic_library,
            }

        action_score = 0.4 if has_action else 0.0
        marker_score = 0.4 if any(m in lowered for m in model_markers) else 0.0
        doc_top = float(retrieved_docs[0].get("score", 0.0)) if retrieved_docs else 0.0
        evidence_score = min(0.3, doc_top / 20.0)
        confidence = min(1.0, action_score + marker_score + evidence_score)

        if confidence >= 0.55:
            return {
                "task_type": "matlab_generation_dll" if wants_dynamic_library else "matlab_generation",
                "confidence": confidence,
                "reason": "rule_generation_confident",
                "has_generation_action": has_action,
                "wants_dynamic_library": wants_dynamic_library,
            }
        return {
            "task_type": "chat",
            "confidence": max(0.35, 1.0 - confidence),
            "reason": "rule_chat_default",
            "has_generation_action": has_action,
            "wants_dynamic_library": wants_dynamic_library,
        }

    def _llm_plan(
        self,
        query: str,
        retrieved_docs: List[Dict[str, Any]],
        recent_history: List[Dict[str, str]],
    ) -> tuple[Dict[str, Any] | None, str]:
        evidence_lines: List[str] = []
        for idx, item in enumerate(retrieved_docs[:5], 1):
            payload = item.get("payload", {})
            evidence_lines.append(
                f"[{idx}] model={payload.get('model_id','')}; score={item.get('score', 0)}; text={item.get('text','')[:160]}"
            )

        planner_history_window = max(1, int(settings.PLANNER_HISTORY_WINDOW))
        history_text = "\n".join(
            f"{h.get('role','')}: {h.get('content','')}" for h in recent_history[-planner_history_window:]
        )
        system_prompt = (
            "你是任务路由器。"
            "只输出JSON，不要其他文本。"
            "根据用户输入和证据，判断任务类型：matlab_generation/matlab_generation_dll/chat/clarify。"
        )
        user_prompt = (
            f"用户输入: {query}\n"
            f"最近对话:\n{history_text}\n"
            f"检索证据:\n" + "\n".join(evidence_lines) + "\n\n"
            "输出JSON:\n"
            '{ "task_type": "matlab_generation|matlab_generation_dll|chat|clarify", "confidence": 0.0, "reason": "...", "wants_dynamic_library": false }'
        )

        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.8,
                "num_predict": min(140, max(60, int(settings.OLLAMA_NUM_PREDICT))),
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
                return None, "empty_llm_plan"
            parsed = _extract_json_obj(content)
            if parsed is None:
                return None, "llm_plan_json_parse_failed"
            return parsed, ""
        except Exception as exc:
            return None, str(exc)


def _extract_json_obj(text: str) -> Dict[str, Any] | None:
    try:
        return json.loads(text)
    except Exception:
        pass
    block = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if block:
        try:
            return json.loads(block.group(1))
        except Exception:
            pass
    brace = re.search(r"(\{.*\})", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(1))
        except Exception:
            return None
    return None


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default
