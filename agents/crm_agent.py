"""
Conversational AI assistant agent.

Features:
- Multi-turn chat with pluggable session history storage.
- Ollama-based response generation.
- Tool trigger: generate MATLAB .m file when user intent is model generation.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

import requests

from agents.session_store import build_session_store
from agents.tools import MatlabFileGeneratorTool, list_supported_models
from agents.matlab_codegen import MatlabCodeGenerator
from agents.model_spec_builder import ModelSpecBuilder
from agents.model_spec_validator import ModelSpecValidator
from agents.task_planner import RAGTaskPlanner
from config.settings import settings
from knowledge_base.rag_retriever import MatlabRAGRetriever

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CRMAgent:
    """Compatibility class name kept for existing imports."""

    def __init__(self, history_size: int | None = None):
        self.retriever = MatlabRAGRetriever()
        self.task_planner = RAGTaskPlanner()
        self.spec_builder = ModelSpecBuilder(self.retriever)
        self.spec_validator = ModelSpecValidator(self.retriever)
        self.codegen = MatlabCodeGenerator()
        self.generation_tool = MatlabFileGeneratorTool()
        self.history_size = max(1, int(history_size or settings.SESSION_HISTORY_SIZE))
        self.chat_history_window = max(1, int(settings.CHAT_HISTORY_WINDOW))
        self.fallback_history_window = max(1, int(settings.FALLBACK_HISTORY_WINDOW))
        self.session_store = build_session_store(history_size=self.history_size)
        self.system_prompt = (
            "你是一个专业、简洁、实用的中文AI助手。"
            "你可以进行普通对话，并在用户需要时辅助MATLAB建模。"
            "回答要准确、结构清晰、避免空话。"
            "若用户表达不清，先给出可执行的澄清建议。"
            "请直接输出结论，不要输出冗长思考过程。"
        )
        logger.info(
            "Conversational AI assistant initialized. session_store=%s, history_size=%s",
            self.session_store.backend_name,
            self.history_size,
        )

    def process_query(
        self,
        question: str,
        user_id: str = "default",
        session_id: str = "default",
    ) -> Dict[str, Any]:
        return self.chat(question, user_id=user_id, session_id=session_id)

    def chat(
        self,
        message: str,
        user_id: str = "default",
        session_id: str = "default",
    ) -> Dict[str, Any]:
        del user_id
        text = (message or "").strip()
        if not text:
            return self._error("请输入消息。")

        normalized = text.lower()
        if normalized in {"/new", "/reset", "重置会话", "清空会话"}:
            self.session_store.clear(session_id)
            return {
                "message": "会话已重置，你可以开始新的对话。",
                "data": {
                    "query_type": "session_reset",
                    "session_id": session_id,
                    "session_store_backend": self.session_store.backend_name,
                },
            }

        if normalized in {"/models", "模型列表", "可用模型", "支持的模型"}:
            payload = json.loads(list_supported_models())
            model_lines = [f"- {m['model_id']}: {m['name']}" for m in payload.get("models", [])]
            return {
                "message": "当前支持的MATLAB模板：\n" + "\n".join(model_lines),
                "data": {"query_type": "model_catalog", "models": payload.get("models", [])},
            }

        recent_history = self._get_history(session_id)
        retrieved_docs = self.retriever.retrieve(text, top_k=10)
        planner = self.task_planner.plan(
            query=text,
            retrieved_docs=retrieved_docs,
            recent_history=recent_history,
        )
        task_type = planner.get("task_type", "chat")
        confidence = float(planner.get("confidence", 0.0))
        has_action = self._has_generation_action(text)

        if task_type == "matlab_generation" and confidence >= 0.45 and (has_action or confidence >= 0.78):
            return self._handle_generation_intent(
                text,
                session_id=session_id,
                retrieved_docs=retrieved_docs,
                planner=planner,
            )

        assistant_reply, used_fallback, fallback_reason = self._generate_chat_reply(
            text,
            session_id=session_id,
            retrieved_docs=retrieved_docs,
            planner=planner,
        )
        self._append_history(session_id, "user", text)
        self._append_history(session_id, "assistant", assistant_reply)

        return {
            "message": assistant_reply,
            "data": {
                "query_type": "chat",
                "session_id": session_id,
                "history_turns": self.session_store.count(session_id),
                "used_fallback": used_fallback,
                "fallback_reason": fallback_reason,
                "session_store_backend": self.session_store.backend_name,
                "planner": planner,
                "retrieved_knowledge": retrieved_docs[:5],
            },
        }

    def _handle_generation_intent(
        self,
        text: str,
        session_id: str,
        retrieved_docs: List[Dict[str, Any]],
        planner: Dict[str, Any],
    ) -> Dict[str, Any]:
        spec_result = self.spec_builder.build_spec(text, retrieved_docs)
        raw_spec = spec_result.get("spec", {})
        repair_result = self.spec_validator.validate_with_auto_repair(
            initial_spec=raw_spec,
            query=text,
            retrieved_docs=retrieved_docs,
            repair_fn=self.spec_builder.repair_spec_with_llm,
            max_repair_rounds=int(getattr(settings, "MODEL_SPEC_REPAIR_MAX_ROUNDS", 2)),
        )
        validation = repair_result.get("semantic_validation", {})
        schema_validation = repair_result.get("schema_validation", {})
        repair_trace = repair_result.get("repair_trace", [])
        auto_repaired_by_llm = bool(repair_result.get("repair_used", False))
        auto_recovered_by_heuristic = False
        heuristic_validation: Dict[str, Any] = {}

        if not repair_result.get("valid"):
            heuristic_spec = self.spec_builder.build_heuristic_spec(text, retrieved_docs)
            heuristic_repair_result = self.spec_validator.validate_with_auto_repair(
                initial_spec=heuristic_spec,
                query=text,
                retrieved_docs=retrieved_docs,
                repair_fn=self.spec_builder.repair_spec_with_llm,
                max_repair_rounds=1,
            )
            heuristic_validation = heuristic_repair_result.get("semantic_validation", {})
            if heuristic_repair_result.get("valid"):
                validation = heuristic_validation
                schema_validation = heuristic_repair_result.get("schema_validation", {})
                normalized_spec = heuristic_repair_result.get("normalized_spec", heuristic_spec)
                auto_repaired_by_llm = auto_repaired_by_llm or bool(
                    heuristic_repair_result.get("repair_used", False)
                )
                auto_recovered_by_heuristic = True
            else:
                errors = validation.get("errors", [])
                warnings = validation.get("warnings", [])
                schema_errors = schema_validation.get("errors", [])
                suggestion = (
                    "请补充更明确的参数后重试。"
                    "例如：`生成状态空间模型，A=[0 1;-2 -3], B=[0;1], C=[1 0], D=0, 仿真10秒`"
                )
                message = "模型规格校验失败：\n" + "\n".join(f"- {e}" for e in errors)
                if schema_errors:
                    message += "\n\nSchema错误：\n" + "\n".join(f"- {e}" for e in schema_errors)
                if warnings:
                    message += "\n\n已识别到的风险提示：\n" + "\n".join(f"- {w}" for w in warnings)
                if heuristic_validation.get("errors"):
                    message += "\n\n启发式修复后仍失败：\n" + "\n".join(
                        f"- {e}" for e in heuristic_validation.get("errors", [])
                    )
                message += f"\n\n{suggestion}"
                return {
                    "message": message,
                    "data": {
                        "query_type": "matlab_generation_validation_failed",
                        "session_id": session_id,
                        "spec": raw_spec,
                        "validation": validation,
                        "schema_validation": schema_validation,
                        "repair_trace": repair_trace,
                        "heuristic_validation": heuristic_validation,
                        "retrieved_knowledge": retrieved_docs[:5],
                    },
                }
        else:
            normalized_spec = repair_result.get("normalized_spec", raw_spec)
        generated = self.codegen.generate_from_spec(
            spec=normalized_spec,
            evidence_docs=retrieved_docs,
            output_dir="generated_models",
        )
        used_legacy_fallback = False
        if generated.get("status") != "success":
            # fallback to legacy generator path to maximize availability
            legacy = json.loads(self.generation_tool._run(description=text))
            if legacy.get("status") == "success":
                generated = legacy
                used_legacy_fallback = True
            else:
                return self._error(
                    f"RAG生成失败({generated.get('message', 'unknown')})，"
                    f"模板生成也失败({legacy.get('message', 'unknown')})"
                )

        model_id = generated.get("model_id", normalized_spec.get("model_id", "unknown"))
        model_name = generated.get("model_name", model_id)
        response = (
            f"已为你生成 `.m` 文件：{generated['file_name']}\n"
            f"模型：{model_name} ({model_id})\n"
            f"路径：{generated['file_path']}\n"
            "该结果由 RAG 检索与规格推导得到。"
        )
        if used_legacy_fallback:
            response += "\n注意：本次使用了模板兜底生成。"
        if auto_repaired_by_llm:
            response += "\n注意：ModelSpec经过JSON Schema自动修复循环后通过校验。"
        if auto_recovered_by_heuristic:
            response += "\n注意：LLM规格校验失败，已自动使用启发式规格修复。"

        self._append_history(session_id, "user", text)
        self._append_history(session_id, "assistant", response)

        return {
            "message": response,
            "data": {
                "query_type": "matlab_generation",
                "session_id": session_id,
                "session_store_backend": self.session_store.backend_name,
                "model_id": generated.get("model_id"),
                "model_name": model_name,
                "generated_file": generated.get("file_name"),
                "generated_file_path": generated.get("file_path"),
                "script": generated.get("script"),
                "parsed_params": normalized_spec.get("parameters", {}),
                "model_spec": normalized_spec,
                "spec_build_source": normalized_spec.get("_build_source", ""),
                "spec_used_llm": spec_result.get("used_llm", False),
                "spec_llm_error": spec_result.get("llm_error", ""),
                "validation": validation,
                "schema_validation": schema_validation,
                "repair_trace": repair_trace,
                "retrieved_knowledge": retrieved_docs[:5],
                "used_legacy_fallback": used_legacy_fallback,
                "auto_repaired_by_llm": auto_repaired_by_llm,
                "auto_recovered_by_heuristic": auto_recovered_by_heuristic,
                "planner": planner,
            },
        }

    def _generate_chat_reply(
        self,
        message: str,
        session_id: str,
        retrieved_docs: List[Dict[str, Any]],
        planner: Dict[str, Any],
    ) -> Tuple[str, bool, str]:
        messages: List[Dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
        rag_context = self._build_rag_context(retrieved_docs, planner)
        if rag_context:
            messages.append({"role": "system", "content": rag_context})
        # Keep context focused and reduce model latency.
        messages.extend(self._get_history(session_id, limit=self.chat_history_window))
        messages.append({"role": "user", "content": message})
        fallback_reason = ""

        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.4,
                "top_p": 0.9,
                "num_predict": settings.OLLAMA_NUM_PREDICT,
            },
        }

        try:
            content = self._request_ollama(payload, timeout_sec=settings.OLLAMA_TIMEOUT_SEC)
            if content:
                return content, False, fallback_reason
            raise RuntimeError("empty content from /api/chat")
        except requests.Timeout:
            logger.warning("Ollama first attempt timeout, retrying with shorter context/output.")
            fallback_reason = "timeout on /api/chat first attempt"
            retry_payload = {
                "model": settings.OLLAMA_MODEL,
                "messages": [{"role": "system", "content": self.system_prompt}]
                + self._get_history(session_id, limit=self.fallback_history_window)
                + [{"role": "user", "content": message}],
                "stream": False,
                "think": False,
                "options": {
                    "temperature": 0.3,
                    "top_p": 0.8,
                    "num_predict": min(80, int(settings.OLLAMA_NUM_PREDICT)),
                },
            }
            try:
                retry_content = self._request_ollama(
                    retry_payload,
                    timeout_sec=max(120, int(settings.OLLAMA_TIMEOUT_SEC)),
                )
                if retry_content:
                    return retry_content, False, fallback_reason
            except Exception as exc:
                logger.warning("Ollama retry failed: %s", exc)
                fallback_reason = f"{fallback_reason}; retry_failed={exc}"
        except Exception as exc:
            logger.warning("Ollama /api/chat failed, trying /api/generate fallback: %s", exc)
            fallback_reason = f"/api/chat_failed={exc}"
            try:
                generate_reply = self._request_ollama_generate(
                    message=message,
                    session_id=session_id,
                    timeout_sec=max(120, int(settings.OLLAMA_TIMEOUT_SEC)),
                )
                if generate_reply:
                    return generate_reply, False, fallback_reason
                fallback_reason = f"{fallback_reason}; /api/generate empty response"
            except Exception as gen_exc:
                logger.warning("Ollama /api/generate failed: %s", gen_exc)
                fallback_reason = f"{fallback_reason}; /api/generate_failed={gen_exc}"

        fallback = (
            "我现在无法连接到本地LLM服务（Ollama），但仍可帮你做结构化任务。"
            "你可以直接说：\n"
            "1) `生成一个PID闭环模型，kp=1.5, ki=0.8, kd=0.02`\n"
            "2) `列出支持的MATLAB模型`"
        )
        logger.warning("Ollama fallback used. reason=%s", fallback_reason or "unknown")
        return fallback, True, (fallback_reason or "unknown")

    def _request_ollama(self, payload: Dict[str, Any], timeout_sec: int) -> str:
        response = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=(10, timeout_sec),
        )
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "").strip()

    def _request_ollama_generate(self, message: str, session_id: str, timeout_sec: int) -> str:
        recent = self._get_history(session_id, limit=self.fallback_history_window)
        history_text = "\n".join(f"{x['role']}: {x['content']}" for x in recent)
        prompt = (
            f"{self.system_prompt}\n"
            f"以下是最近对话上下文：\n{history_text}\n"
            f"用户问题：{message}\n"
            "请直接给出简洁中文答复。"
        )
        payload = {
            "model": settings.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.3,
                "top_p": 0.8,
                "num_predict": min(96, int(settings.OLLAMA_NUM_PREDICT)),
            },
        }
        response = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=(10, timeout_sec),
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()

    def _append_history(self, session_id: str, role: str, content: str) -> None:
        self.session_store.append(session_id, role, content)

    def _get_history(self, session_id: str, limit: int | None = None) -> List[Dict[str, str]]:
        history = self.session_store.get_history(session_id)
        if limit is None or limit <= 0:
            return history
        return history[-limit:]

    def _build_rag_context(
        self,
        retrieved_docs: List[Dict[str, Any]],
        planner: Dict[str, Any],
    ) -> str:
        if not retrieved_docs:
            return ""
        lines = [
            "以下是检索到的相关知识证据，请优先依据这些证据作答：",
            f"路由建议: task_type={planner.get('task_type','')}, confidence={planner.get('confidence',0)}",
        ]
        for item in retrieved_docs[:4]:
            payload = item.get("payload", {})
            model_id = payload.get("model_id", "")
            score = item.get("score", 0)
            txt = item.get("text", "").replace("\n", " ")
            lines.append(f"- model={model_id}, score={score}: {txt[:180]}")
        return "\n".join(lines)

    def _has_generation_action(self, text: str) -> bool:
        lowered = text.lower()
        action_words = ["生成", "构建", "建立", "写", "创建", "build", "generate", "做个", "设计", "实现", "搭建"]
        return any(a in lowered for a in action_words)

    def _is_generation_intent(self, text: str) -> bool:
        lowered = text.lower()
        keywords = [
            ".m",
            "matlab",
            "simulink",
            "生成模型",
            "建模",
            "控制模型",
            "传递函数",
            "状态空间",
            "pid",
            "kalman",
            "卡尔曼",
            "mpc",
            "ode45",
            "机械臂",
            "光伏",
            "电池",
            "滤波模型",
            "跟踪模型",
        ]
        action_words = ["生成", "构建", "建立", "写", "创建", "build", "generate"]
        action_words.extend(["做", "做个", "设计", "实现", "开发", "搭建"])
        return any(k in lowered for k in keywords) and any(a in lowered for a in action_words)

    def _error(self, msg: str) -> Dict[str, Any]:
        return {"message": f"抱歉，{msg}", "data": {"query_type": "error"}}

    def test_query(self, test_cases: List[str] | None = None):
        if test_cases is None:
            test_cases = [
                "你好，介绍下你能做什么",
                "生成一个PID闭环控制的Simulink模型，kp=1.8, ki=0.9, kd=0.05",
                "如果我想做卡尔曼滤波，应该先准备什么状态方程？",
            ]
        print("Conversational assistant test")
        print("=" * 60)
        for i, query in enumerate(test_cases, 1):
            result = self.chat(query, session_id="test")
            print(f"\n[{i}] {query}")
            print(result.get("message", ""))
            print("-" * 60)

    def interactive_mode(self):
        print("=" * 60)
        print("AI对话助手（支持MATLAB模型生成）")
        print("输入 /new 重置会话，输入 /models 查看支持模型，输入 exit 退出")
        print("=" * 60)
        session_id = "cli_session"
        while True:
            user_input = input("\n你: ").strip()
            if user_input.lower() in {"exit", "quit", "q", "退出"}:
                print("助手: 再见。")
                break
            result = self.chat(user_input, session_id=session_id)
            print(f"\n助手: {result.get('message', '')}")


def main():
    agent = CRMAgent()
    agent.interactive_mode()


if __name__ == "__main__":
    main()
