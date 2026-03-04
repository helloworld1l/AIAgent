"""
Conversational AI assistant agent.

Features:
- Multi-turn chat with in-memory session history.
- Ollama-based response generation.
- Tool trigger: generate MATLAB .m file when user intent is model generation.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Tuple

import requests

from agents.tools import MatlabFileGeneratorTool, list_supported_models
from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CRMAgent:
    """Compatibility class name kept for existing imports."""

    def __init__(self, history_size: int = 20):
        self.generation_tool = MatlabFileGeneratorTool()
        self.history_size = history_size
        self.session_histories: Dict[str, Deque[Dict[str, str]]] = defaultdict(
            lambda: deque(maxlen=self.history_size)
        )
        self.system_prompt = (
            "你是一个专业、简洁、实用的中文AI助手。"
            "你可以进行普通对话，并在用户需要时辅助MATLAB建模。"
            "回答要准确、结构清晰、避免空话。"
            "若用户表达不清，先给出可执行的澄清建议。"
            "请直接输出结论，不要输出冗长思考过程。"
        )
        logger.info("Conversational AI assistant initialized.")

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
            self.session_histories[session_id].clear()
            return {
                "message": "会话已重置，你可以开始新的对话。",
                "data": {"query_type": "session_reset", "session_id": session_id},
            }

        if normalized in {"/models", "模型列表", "可用模型", "支持的模型"}:
            payload = json.loads(list_supported_models())
            model_lines = [f"- {m['model_id']}: {m['name']}" for m in payload.get("models", [])]
            return {
                "message": "当前支持的MATLAB模板：\n" + "\n".join(model_lines),
                "data": {"query_type": "model_catalog", "models": payload.get("models", [])},
            }

        if self._is_generation_intent(text):
            return self._handle_generation_intent(text, session_id=session_id)

        assistant_reply, used_fallback, fallback_reason = self._generate_chat_reply(text, session_id=session_id)
        self._append_history(session_id, "user", text)
        self._append_history(session_id, "assistant", assistant_reply)

        return {
            "message": assistant_reply,
            "data": {
                "query_type": "chat",
                "session_id": session_id,
                "history_turns": len(self.session_histories[session_id]),
                "used_fallback": used_fallback,
                "fallback_reason": fallback_reason,
            },
        }

    def _handle_generation_intent(self, text: str, session_id: str) -> Dict[str, Any]:
        generated = json.loads(self.generation_tool._run(description=text))
        if generated.get("status") != "success":
            return self._error(generated.get("message", "生成失败"))

        response = (
            f"已为你生成 `.m` 文件：{generated['file_name']}\n"
            f"模型：{generated['model_name']} ({generated['model_id']})\n"
            f"路径：{generated['file_path']}\n"
            "如果你要，我可以继续帮你解释代码结构或按参数再改一版。"
        )

        self._append_history(session_id, "user", text)
        self._append_history(session_id, "assistant", response)

        return {
            "message": response,
            "data": {
                "query_type": "matlab_generation",
                "session_id": session_id,
                "model_id": generated.get("model_id"),
                "model_name": generated.get("model_name"),
                "generated_file": generated.get("file_name"),
                "generated_file_path": generated.get("file_path"),
                "script": generated.get("script"),
                "parsed_params": generated.get("params", {}),
            },
        }

    def _generate_chat_reply(self, message: str, session_id: str) -> Tuple[str, bool, str]:
        messages: List[Dict[str, str]] = [{"role": "system", "content": self.system_prompt}]
        # Keep context focused and reduce model latency.
        messages.extend(list(self.session_histories[session_id])[-8:])
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
                + list(self.session_histories[session_id])[-4:]
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
        recent = list(self.session_histories[session_id])[-4:]
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
        self.session_histories[session_id].append({"role": role, "content": content})

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
            "mpc",
            "ode45",
            "机械臂",
            "光伏",
            "电池",
        ]
        action_words = ["生成", "构建", "建立", "写", "创建", "build", "generate"]
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
