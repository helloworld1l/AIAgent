"""
Backward-compatible agent entry.
Project goal is now MATLAB model generation (.m file output).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from agents.tools import MatlabFileGeneratorTool, MatlabKnowledgeRetrieverTool, list_supported_models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CRMAgent:
    """
Compatibility class name preserved for existing imports.
Behavior: parse model description -> generate MATLAB .m file.
    """

    def __init__(self):
        self.knowledge_tool = MatlabKnowledgeRetrieverTool()
        self.generation_tool = MatlabFileGeneratorTool()
        logger.info("MATLAB model generation agent initialized.")

    def process_query(
        self,
        question: str,
        user_id: str = "default",
        session_id: str = "default",
    ) -> Dict[str, Any]:
        del user_id, session_id
        text = (question or "").strip()
        if not text:
            return self._error("请输入模型描述，例如：构建一个PID闭环控制模型。")

        if self._is_greeting(text):
            return self._greeting()

        if self._is_model_list_request(text):
            payload = json.loads(list_supported_models())
            model_lines = [f"- {m['model_id']}: {m['name']}" for m in payload.get("models", [])]
            return {
                "message": "当前支持的 MATLAB 模型模板如下：\n" + "\n".join(model_lines),
                "data": {
                    "query_type": "model_catalog",
                    "models": payload.get("models", []),
                },
            }

        generated = json.loads(self.generation_tool._run(description=text))
        if generated.get("status") != "success":
            return self._error(generated.get("message", "生成失败"))

        knowledge = json.loads(self.knowledge_tool._run(text))
        matches = knowledge.get("matches", [])

        message = (
            f"已生成 MATLAB 模型脚本：`{generated['file_name']}`\n"
            f"模型类型：{generated['model_name']} ({generated['model_id']})\n"
            f"保存路径：{generated['file_path']}"
        )

        return {
            "message": message,
            "data": {
                "query_type": "matlab_generation",
                "model_id": generated.get("model_id"),
                "model_name": generated.get("model_name"),
                "category": generated.get("category"),
                "generated_file": generated.get("file_name"),
                "generated_file_path": generated.get("file_path"),
                "script": generated.get("script"),
                "parsed_params": generated.get("params", {}),
                "knowledge_matches": matches,
            },
        }

    def test_query(self, test_cases: List[str] | None = None):
        if test_cases is None:
            test_cases = [
                "构建一个传递函数阶跃响应模型，分母是[1 3 2]",
                "生成PID闭环Simulink模型，kp=1.8, ki=0.9, kd=0.05",
                "做一个质量弹簧阻尼系统仿真，m=2,c=0.3,k=15",
                "构建卡尔曼滤波跟踪模型",
            ]
        print("Testing MATLAB generation agent")
        print("=" * 60)
        for i, query in enumerate(test_cases, 1):
            result = self.process_query(query)
            print(f"\n[{i}] {query}")
            print(result.get("message", ""))
            print("-" * 60)

    def interactive_mode(self):
        print("=" * 60)
        print("MATLAB model generation agent")
        print("Input description and I will generate a .m file.")
        print("Type 'exit' to quit.")
        print("=" * 60)

        while True:
            user_input = input("\n请输入模型描述: ").strip()
            if user_input.lower() in {"exit", "quit", "q", "退出"}:
                print("Bye.")
                break
            result = self.process_query(user_input)
            print(result.get("message", ""))

    def _is_greeting(self, text: str) -> bool:
        lower = text.lower()
        return any(token in lower for token in ["你好", "您好", "hello", "hi"])

    def _is_model_list_request(self, text: str) -> bool:
        markers = ["支持", "模型列表", "有哪些模型", "list models", "template list", "可用模型"]
        lower = text.lower()
        return any(marker in text or marker in lower for marker in markers)

    def _greeting(self) -> Dict[str, Any]:
        return {
            "message": (
                "你好！我可以根据你的描述生成 MATLAB .m 文件。"
                "例如：'构建PID闭环控制的Simulink模型，kp=1.5, ki=0.8, kd=0.02'。"
            ),
            "data": {"query_type": "greeting"},
        }

    def _error(self, msg: str) -> Dict[str, Any]:
        return {"message": f"抱歉，{msg}", "data": {"query_type": "error"}}


def main():
    agent = CRMAgent()
    agent.interactive_mode()


if __name__ == "__main__":
    main()

