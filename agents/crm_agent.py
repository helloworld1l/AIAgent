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

from agents.dll_build_support import (
    extract_build_preferences,
    inspect_matlab_entrypoint,
    mentions_dynamic_library,
    references_previous_artifact,
    requests_dynamic_library_build,
)
from agents.session_store import build_session_store
from agents.structured_generation_ir import StructuredGenerationIR
from agents.tools import DynamicLibraryBuildTool, MatlabFileGeneratorTool, list_supported_models
from agents.matlab_codegen import MatlabCodeGenerator
from agents.model_spec_builder import ModelSpecBuilder
from agents.model_spec_validator import ModelSpecValidator
from agents.task_planner import RAGTaskPlanner
from config.settings import settings
from knowledge_base.rag_retriever import MatlabRAGRetriever

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PENDING_GENERATION_IR_STATE = "pending_generation_ir"
PENDING_GENERATION_MATCH_STATE = "pending_generation_match"
LAST_GENERATION_RESULT_STATE = "last_generation_result"

CLARIFY_STAGE_OBJECT = "object"
CLARIFY_STAGE_FAMILY = "family"
CLARIFY_STAGE_SLOT = "slot"

OBJECT_CLARIFY_REASONS = {
    "military_equipment_needs_object",
    "battlefield_situation_needs_object",
    "out_of_scope",
}

FAMILY_CONFIRM_MARKERS = {
    "确认",
    "就这个",
    "就用这个",
    "按这个",
    "按这个来",
    "用这个",
    "可以",
    "继续",
    "开始",
    "生成",
    "yes",
    "ok",
    "okay",
}


class CRMAgent:
    """Compatibility class name kept for existing imports."""

    def __init__(self, history_size: int | None = None):
        self.retriever = MatlabRAGRetriever()
        self.task_planner = RAGTaskPlanner()
        self.spec_builder = ModelSpecBuilder(self.retriever)
        self.spec_validator = ModelSpecValidator(self.retriever)
        self.structured_ir = StructuredGenerationIR(self.retriever)
        self.codegen = MatlabCodeGenerator()
        self.generation_tool = MatlabFileGeneratorTool()
        self.dynamic_library_build_tool = DynamicLibraryBuildTool()
        self.history_size = max(1, int(history_size or settings.SESSION_HISTORY_SIZE))
        self.chat_history_window = max(1, int(settings.CHAT_HISTORY_WINDOW))
        self.fallback_history_window = max(1, int(settings.FALLBACK_HISTORY_WINDOW))
        self.session_store = build_session_store(history_size=self.history_size)
        self.system_prompt = (
            "你是一个专业、简洁、实用的中文 AI 助手。"
            "你可以进行普通对话，并在用户需要时辅助 MATLAB 建模与 DLL 构建。"
            "回答要准确、结构清晰、避免空话。"
            "如果用户表述不清，先给出可执行的澄清建议。"
            "请直接输出结论，不要输出冗长思考过程。"
        )
        logger.info(
            "Conversational AI assistant initialized. session_store=%s, history_size=%s",
            self.session_store.backend_name,
            self.history_size,
        )
        self._log_retrieval_startup_check()

    def _log_retrieval_startup_check(self) -> None:
        retrieval_health = self.retriever.get_retrieval_health()
        if retrieval_health.get("hybrid_effective"):
            logger.info(
                "Hybrid retrieval startup check passed. backend=%s, effective_weights=(bm25=%s, vector=%s)",
                retrieval_health.get("active_vector_backend", "none"),
                retrieval_health.get("effective_bm25_weight", 1.0),
                retrieval_health.get("effective_vector_weight", 0.0),
            )
            return

        logger.error(
            "HYBRID RETRIEVAL STARTUP CHECK FAILED: hybrid is inactive; configured_backend=%s, active_backend=%s, error=%s, effective_weights=(bm25=%s, vector=%s)",
            retrieval_health.get("configured_vector_backend", "auto"),
            retrieval_health.get("active_vector_backend", "none"),
            retrieval_health.get("vector_error", ""),
            retrieval_health.get("effective_bm25_weight", 1.0),
            retrieval_health.get("effective_vector_weight", 0.0),
        )

    def build_dynamic_library(
        self,
        matlab_file: str,
        entry_function: str,
        entry_args_schema: List[Dict[str, Any]] | str | None = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return json.loads(
            self.dynamic_library_build_tool._run(
                matlab_file=matlab_file,
                entry_function=entry_function,
                entry_args_schema=entry_args_schema,
                **kwargs,
            )
        )

    def _get_last_generation_result(self, session_id: str) -> Dict[str, Any] | None:
        return self.session_store.get_state(session_id, LAST_GENERATION_RESULT_STATE)

    def _set_last_generation_result(self, session_id: str, value: Dict[str, Any]) -> None:
        self.session_store.set_state(session_id, LAST_GENERATION_RESULT_STATE, value)

    def _build_generated_dynamic_library(
        self,
        text: str,
        generated: Dict[str, Any],
        model_spec: Dict[str, Any],
    ) -> Dict[str, Any]:
        generated_file_path = str(generated.get("file_path", "")).strip()
        if not generated_file_path:
            return {
                "status": "error",
                "message": "Generated MATLAB file path is missing.",
                "artifact_paths": [],
                "build_result": {},
                "entry_function": "",
                "entry_args_schema": [],
            }

        entry_info = inspect_matlab_entrypoint(generated_file_path)
        build_preferences = extract_build_preferences(text)
        if entry_info.get("status") != "success":
            return {
                "status": str(entry_info.get("status", "skipped") or "skipped"),
                "message": str(entry_info.get("message", "DLL build skipped.")).strip() or "DLL build skipped.",
                "artifact_paths": [],
                "build_result": {},
                "entry_function": str(entry_info.get("entry_function", "")).strip(),
                "entry_args_schema": list(entry_info.get("entry_args_schema", [])),
                "preferences": build_preferences,
            }

        build_kwargs: Dict[str, Any] = {
            "matlab_file": generated_file_path,
            "entry_function": str(entry_info.get("entry_function", "")).strip(),
            "entry_args_schema": list(entry_info.get("entry_args_schema", [])),
            "project_name": str(generated.get("model_id", "") or model_spec.get("model_id", "") or "generated_model").strip(),
            "artifact_name": str(generated.get("model_id", "") or model_spec.get("model_id", "") or "generated_model")
            .strip()
            .replace("-", "_")
            + "_dll",
            "build_type": build_preferences.get("build_type", "Release"),
            "target_lang": build_preferences.get("target_lang", "C"),
            "generate_report": bool(build_preferences.get("generate_report", False)),
            "require_matlab": True,
        }
        if build_preferences.get("profile"):
            build_kwargs["profile"] = build_preferences["profile"]

        build_result = self.build_dynamic_library(**build_kwargs)
        job_result = build_result.get("job_result", {}) if isinstance(build_result.get("job_result", {}), dict) else {}
        artifact_paths = [str(item) for item in job_result.get("artifact_paths", []) if str(item).strip()]

        return {
            "status": str(build_result.get("status", "error") or "error"),
            "message": str(build_result.get("message", "")).strip(),
            "artifact_paths": artifact_paths,
            "build_result": build_result,
            "entry_function": build_kwargs["entry_function"],
            "entry_args_schema": build_kwargs["entry_args_schema"],
            "preferences": build_preferences,
        }

    def _handle_dynamic_library_followup(
        self,
        text: str,
        session_id: str,
        last_generation_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        generated = {
            "file_path": last_generation_result.get("generated_file_path", ""),
            "model_id": last_generation_result.get("model_id", ""),
            "model_name": last_generation_result.get("model_name", ""),
        }
        model_spec = last_generation_result.get("model_spec", {}) if isinstance(last_generation_result.get("model_spec", {}), dict) else {}
        dll_result = self._build_generated_dynamic_library(text=text, generated=generated, model_spec=model_spec)

        response = (
            f"已尝试将最近生成的 MATLAB 文件编译为 DLL：{generated.get('file_path', '')}"
            if generated.get("file_path")
            else "已尝试将最近生成的 MATLAB 文件编译为 DLL。"
        )
        if dll_result.get("status") == "success":
            if dll_result.get("artifact_paths"):
                response += "\n产物：" + "\n".join(dll_result.get("artifact_paths", []))
            else:
                response += "\nDLL 构建已完成。"
        elif dll_result.get("message"):
            response += f"\n结果：{dll_result.get('message', '')}"

        self._append_history(session_id, "user", text)
        self._append_history(session_id, "assistant", response)
        return {
            "message": response,
            "data": {
                "query_type": "dynamic_library_build",
                "session_id": session_id,
                "session_store_backend": self.session_store.backend_name,
                "model_id": last_generation_result.get("model_id", ""),
                "model_name": last_generation_result.get("model_name", ""),
                "generated_file_path": last_generation_result.get("generated_file_path", ""),
                "dll_build_status": dll_result.get("status", "error"),
                "dll_artifact_paths": dll_result.get("artifact_paths", []),
                "dll_entry_function": dll_result.get("entry_function", ""),
                "dll_entry_args_schema": dll_result.get("entry_args_schema", []),
                "dll_build": dll_result.get("build_result", {}),
            },
        }

    @staticmethod
    def _normalize_trace_list(values: Any) -> List[str]:
        if isinstance(values, (list, tuple, set)):
            return [str(item).strip() for item in values if str(item).strip()]
        if str(values or "").strip():
            return [str(values).strip()]
        return []

    def _build_generation_trace(
        self,
        event: str,
        session_id: str = "",
        match_assessment: Dict[str, Any] | None = None,
        generation_ir: Dict[str, Any] | None = None,
        clarify_stage: str = "",
        final_generated: bool | None = None,
    ) -> Dict[str, Any]:
        assessment = match_assessment or {}
        ir = generation_ir or {}
        assessment_trace = assessment.get("trace", {}) if isinstance(assessment.get("trace", {}), dict) else {}
        ir_trace = ir.get("trace", {}) if isinstance(ir.get("trace", {}), dict) else {}
        slot_collection = ir.get("slot_collection", {}) if isinstance(ir.get("slot_collection", {}), dict) else {}
        query_domains = self._normalize_trace_list(
            ir.get("query_domains", [])
            or assessment.get("query_domains", [])
            or ir_trace.get("query_domains", [])
            or assessment_trace.get("query_domains", [])
        )
        top_family = str(
            ir.get("schema_family", "")
            or assessment.get("top_family", "")
            or ir_trace.get("top_family", "")
            or assessment_trace.get("top_family", "")
            or ""
        ).strip()
        family_top_share_raw = assessment.get(
            "family_top_share",
            ir_trace.get("family_top_share", assessment_trace.get("family_top_share", 0.0)),
        )
        reject_reasons = self._normalize_trace_list(
            assessment.get("reject_reasons", [])
            or ir_trace.get("reject_reasons", [])
            or assessment_trace.get("reject_reasons", [])
        )
        missing_slots = self._normalize_trace_list(
            slot_collection.get("missing_slots", [])
            or ir.get("missing_info", [])
            or ir_trace.get("missing_slots", [])
            or assessment_trace.get("missing_slots", [])
        )
        stage = str(
            clarify_stage
            or ir.get("clarify_stage", "")
            or assessment.get("clarify_stage", "")
            or ir_trace.get("clarify_stage", "")
            or assessment_trace.get("clarify_stage", "")
            or ""
        ).strip().lower()
        if not stage:
            if ir:
                stage = CLARIFY_STAGE_SLOT if missing_slots else "ready"
            elif assessment:
                stage = self._resolve_clarify_stage(match_assessment=assessment)
            else:
                stage = "ready"
        should_generate = assessment.get("should_generate")
        if should_generate is None and ir:
            should_generate = not bool(missing_slots)
        return {
            "source": "crm_agent",
            "event": str(event or "generation_round").strip(),
            "session_id": str(session_id or "").strip(),
            "query_domains": query_domains,
            "top_family": top_family,
            "family_top_share": round(float(family_top_share_raw or 0.0), 4),
            "reject_reasons": reject_reasons,
            "clarify_stage": stage,
            "missing_slots": missing_slots,
            "should_generate": None if should_generate is None else bool(should_generate),
            "final_generated": final_generated,
        }

    def _log_generation_trace(self, trace: Dict[str, Any]) -> None:
        logger.info("generation_trace=%s", json.dumps(trace, ensure_ascii=False, sort_keys=True))

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
                "message": "当前支持的 MATLAB 模型：\n" + "\n".join(model_lines),
                "data": {"query_type": "model_catalog", "models": payload.get("models", [])},
            }

        pending_generation_ir_state = self._get_pending_generation_ir(session_id)
        pending_generation_ir = self._normalize_pending_generation_ir(
            pending_generation_ir_state
        )
        pending_generation_ir_request_dynamic_library = (
            self._extract_pending_generation_ir_request_dynamic_library(
                pending_generation_ir_state
            )
        )
        if pending_generation_ir:
            if self.structured_ir.wants_cancel(text):
                trace = self._build_generation_trace(
                    event="cancel_slot_clarify",
                    session_id=session_id,
                    generation_ir=pending_generation_ir,
                    clarify_stage=CLARIFY_STAGE_SLOT,
                    final_generated=False,
                )
                self._log_generation_trace(trace)
                self._clear_pending_generation_ir(session_id)
                self._clear_pending_generation_match(session_id)
                response = "已取消上一轮结构化参数收集。"
                self._append_history(session_id, "user", text)
                self._append_history(session_id, "assistant", response)
                return {
                    "message": response,
                    "data": {
                        "query_type": "matlab_generation_clarify_cancelled",
                        "session_id": session_id,
                        "session_store_backend": self.session_store.backend_name,
                        "generation_trace": trace,
                    },
                }
            if self.structured_ir.looks_like_slot_reply(text, pending_generation_ir):
                return self._resume_pending_generation_ir(
                    text,
                    session_id,
                    pending_generation_ir,
                    request_dynamic_library=pending_generation_ir_request_dynamic_library,
                )
            if self._is_generation_intent(text):
                self._clear_pending_generation_ir(session_id)
                self._clear_pending_generation_match(session_id)

        pending_generation_match = self._normalize_pending_generation_match(
            self._get_pending_generation_match(session_id)
        )
        if pending_generation_match and not pending_generation_ir:
            if self.structured_ir.wants_cancel(text):
                trace = self._build_generation_trace(
                    event="cancel_match_clarify",
                    session_id=session_id,
                    match_assessment=pending_generation_match.get("match_assessment", {}),
                    clarify_stage=self._get_match_clarify_stage(pending_generation_match),
                    final_generated=False,
                )
                self._log_generation_trace(trace)
                self._clear_pending_generation_match(session_id)
                response = "已取消上一轮建模对象澄清。"
                self._append_history(session_id, "user", text)
                self._append_history(session_id, "assistant", response)
                return {
                    "message": response,
                    "data": {
                        "query_type": "matlab_generation_match_cancelled",
                        "session_id": session_id,
                        "session_store_backend": self.session_store.backend_name,
                        "generation_trace": trace,
                    },
                }
            if self._looks_like_generation_match_reply(text, pending_generation_match):
                return self._resume_pending_generation_match(text, session_id, pending_generation_match)
            if self._is_generation_intent(text):
                self._clear_pending_generation_match(session_id)
                self._clear_pending_generation_ir(session_id)

        last_generation_result = self._get_last_generation_result(session_id)
        if (
            last_generation_result
            and requests_dynamic_library_build(text)
            and (references_previous_artifact(text) or not self._is_generation_intent(text))
        ):
            return self._handle_dynamic_library_followup(text, session_id, last_generation_result)

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
        request_dynamic_library = bool(planner.get("wants_dynamic_library", False)) or mentions_dynamic_library(text)

        if task_type in {"matlab_generation", "matlab_generation_dll"} and confidence >= 0.45 and (has_action or confidence >= 0.78):
            match_assessment = self.retriever.assess_generation_match(text, retrieved_docs)
            if not match_assessment.get("should_generate", True):
                return self._handle_generation_clarify(
                    text=text,
                    session_id=session_id,
                    retrieved_docs=retrieved_docs,
                    planner=planner,
                    match_assessment=match_assessment,
                    request_dynamic_library=request_dynamic_library,
                )

            generation_ir = self.structured_ir.begin_collection(text, match_assessment)
            if generation_ir:
                if self.structured_ir.should_clarify(generation_ir):
                    return self._handle_generation_clarify(
                        text=text,
                        session_id=session_id,
                        retrieved_docs=retrieved_docs,
                        planner=planner,
                        match_assessment=match_assessment,
                        generation_ir=generation_ir,
                        clarify_stage=CLARIFY_STAGE_SLOT,
                        request_dynamic_library=request_dynamic_library,
                    )
                return self._handle_generation_intent(
                    text,
                    session_id=session_id,
                    retrieved_docs=retrieved_docs,
                    planner=planner,
                    match_assessment=match_assessment,
                    prefilled_spec=self.structured_ir.to_model_spec(generation_ir),
                    generation_ir=generation_ir,
                    request_dynamic_library=request_dynamic_library,
                )

            return self._handle_generation_intent(
                text,
                session_id=session_id,
                retrieved_docs=retrieved_docs,
                planner=planner,
                match_assessment=match_assessment,
                request_dynamic_library=request_dynamic_library,
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

    def _handle_generation_clarify(
        self,
        text: str,
        session_id: str,
        retrieved_docs: List[Dict[str, Any]],
        planner: Dict[str, Any],
        match_assessment: Dict[str, Any],
        generation_ir: Dict[str, Any] | None = None,
        clarify_stage: str = "",
        request_dynamic_library: bool = False,
    ) -> Dict[str, Any]:
        stage = self._resolve_clarify_stage(
            match_assessment=match_assessment,
            generation_ir=generation_ir,
            preferred_stage=clarify_stage,
        )
        response_generation_ir = generation_ir or {}
        if stage == CLARIFY_STAGE_SLOT and generation_ir:
            staged_generation_ir = dict(generation_ir)
            staged_generation_ir["clarify_stage"] = CLARIFY_STAGE_SLOT
            response = self.structured_ir.build_clarify_message(staged_generation_ir)
            self._set_pending_generation_ir(
                session_id,
                staged_generation_ir,
                request_dynamic_library=request_dynamic_library,
            )
            self._clear_pending_generation_match(session_id)
            response_generation_ir = staged_generation_ir
        else:
            out_of_scope_clarify = self._is_out_of_scope_clarify(match_assessment)
            self._clear_pending_generation_ir(session_id)
            response = self._build_match_clarify_message(match_assessment, stage)
            if out_of_scope_clarify:
                self._clear_pending_generation_match(session_id)
            else:
                self._set_pending_generation_match(
                    session_id,
                    {
                        "original_query": text,
                        "match_assessment": match_assessment,
                        "clarify_stage": stage,
                        "request_dynamic_library": bool(request_dynamic_library),
                    },
                )
        trace = self._build_generation_trace(
            event="handle_generation_clarify",
            session_id=session_id,
            match_assessment=match_assessment,
            generation_ir=response_generation_ir,
            clarify_stage=stage,
            final_generated=False,
        )
        self._log_generation_trace(trace)
        self._append_history(session_id, "user", text)
        self._append_history(session_id, "assistant", response)
        return {
            "message": response,
            "data": {
                "query_type": "matlab_generation_clarify",
                "clarify_stage": stage,
                "session_id": session_id,
                "session_store_backend": self.session_store.backend_name,
                "planner": planner,
                "generation_match": match_assessment,
                "generation_ir": response_generation_ir,
                "request_dynamic_library": bool(request_dynamic_library),
                "generation_trace": trace,
                "retrieved_knowledge": retrieved_docs[:5],
            },
        }

    def _handle_generation_intent(
        self,
        text: str,
        session_id: str,
        retrieved_docs: List[Dict[str, Any]],
        planner: Dict[str, Any],
        match_assessment: Dict[str, Any] | None = None,
        prefilled_spec: Dict[str, Any] | None = None,
        generation_ir: Dict[str, Any] | None = None,
        request_dynamic_library: bool = False,
    ) -> Dict[str, Any]:
        if prefilled_spec is not None:
            spec_result = {
                "spec": prefilled_spec,
                "used_llm": False,
                "llm_error": "",
            }
        else:
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
            normalized_spec = raw_spec
            if prefilled_spec is None:
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
                        "\u8bf7\u8865\u5145\u66f4\u660e\u786e\u7684\u53c2\u6570\u540e\u91cd\u8bd5\u3002\n"
                        "\u4f8b\u5982\uff1a\u751f\u6210\u72b6\u6001\u7a7a\u95f4\u6a21\u578b\uff0cA=[0 1;-2 -3], B=[0;1], C=[1 0], D=0, \u4eff\u771f10\u79d2"
                    )
                    message = "\u6a21\u578b\u89c4\u683c\u6821\u9a8c\u5931\u8d25\uff1a\n" + "\n".join(f"- {e}" for e in errors)
                    if schema_errors:
                        message += "\n\nSchema \u9519\u8bef\uff1a\n" + "\n".join(f"- {e}" for e in schema_errors)
                    if warnings:
                        message += "\n\n\u5df2\u8bc6\u522b\u5230\u7684\u98ce\u9669\u63d0\u793a\uff1a\n" + "\n".join(f"- {w}" for w in warnings)
                    if heuristic_validation.get("errors"):
                        message += "\n\n\u542f\u53d1\u5f0f\u4fee\u590d\u540e\u4ecd\u5931\u8d25\uff1a\n" + "\n".join(
                            f"- {e}" for e in heuristic_validation.get("errors", [])
                        )
                    message += f"\n\n{suggestion}"
                    generation_trace = self._build_generation_trace(
                        event="validation_failed",
                        session_id=session_id,
                        match_assessment=match_assessment or {},
                        generation_ir=generation_ir or {},
                        clarify_stage="ready",
                        final_generated=False,
                    )
                    self._log_generation_trace(generation_trace)
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
                            "generation_match": match_assessment or {},
                            "generation_ir": generation_ir or {},
                            "generation_trace": generation_trace,
                        },
                    }
            else:
                errors = validation.get("errors", [])
                warnings = validation.get("warnings", [])
                schema_errors = schema_validation.get("errors", [])
                message = "\u7ed3\u6784\u5316\u69fd\u4f4d\u53c2\u6570\u4ecd\u672a\u901a\u8fc7\u6821\u9a8c\uff1a\n" + "\n".join(f"- {e}" for e in errors)
                if schema_errors:
                    message += "\n\nSchema \u9519\u8bef\uff1a\n" + "\n".join(f"- {e}" for e in schema_errors)
                if warnings:
                    message += "\n\n\u98ce\u9669\u63d0\u793a\uff1a\n" + "\n".join(f"- {w}" for w in warnings)
                message += "\n\n\u4f60\u53ef\u4ee5\u76f4\u63a5\u7ee7\u7eed\u4fee\u6539\u4e0a\u4e00\u8f6e\u69fd\u4f4d\u53c2\u6570\u3002"
                generation_trace = self._build_generation_trace(
                    event="validation_failed",
                    session_id=session_id,
                    match_assessment=match_assessment or {},
                    generation_ir=generation_ir or {},
                    clarify_stage="ready",
                    final_generated=False,
                )
                self._log_generation_trace(generation_trace)
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
                        "generation_match": match_assessment or {},
                        "generation_ir": generation_ir or {},
                        "generation_trace": generation_trace,
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
            legacy = json.loads(self.generation_tool._run(description=text))
            if legacy.get("status") == "success":
                generated = legacy
                used_legacy_fallback = True
            else:
                message = (
                    f"抱歉，RAG 生成失败({generated.get('message', 'unknown')})，"
                    f"模板兜底生成也失败({legacy.get('message', 'unknown')})"
                )
                generation_trace = self._build_generation_trace(
                    event="generation_failed",
                    session_id=session_id,
                    match_assessment=match_assessment or {},
                    generation_ir=generation_ir or {},
                    clarify_stage="ready",
                    final_generated=False,
                )
                self._log_generation_trace(generation_trace)
                return {
                    "message": message,
                    "data": {
                        "query_type": "matlab_generation_failed",
                        "session_id": session_id,
                        "session_store_backend": self.session_store.backend_name,
                        "generation_match": match_assessment or {},
                        "generation_ir": generation_ir or {},
                        "generation_trace": generation_trace,
                        "retrieved_knowledge": retrieved_docs[:5],
                    },
                }

        if generation_ir:
            self._clear_pending_generation_ir(session_id)
        self._clear_pending_generation_match(session_id)

        last_generation_result = {
            "model_id": generated.get("model_id"),
            "model_name": generated.get("model_name", normalized_spec.get("model_id", "")),
            "generated_file": generated.get("file_name"),
            "generated_file_path": generated.get("file_path"),
            "model_spec": normalized_spec,
            "generator_strategy": generated.get("generator_strategy", ""),
        }
        self._set_last_generation_result(session_id, last_generation_result)

        dll_result: Dict[str, Any] = {}
        if request_dynamic_library:
            dll_result = self._build_generated_dynamic_library(
                text=text,
                generated=generated,
                model_spec=normalized_spec,
            )

        model_id = generated.get("model_id", normalized_spec.get("model_id", "unknown"))
        model_name = generated.get("model_name", model_id)
        response = (
            f"\u5df2\u4e3a\u4f60\u751f\u6210 `.m` \u6587\u4ef6\uff1a{generated['file_name']}\n"
            f"\u6a21\u578b\uff1a{model_name} ({model_id})\n"
            f"\u8def\u5f84\uff1a{generated['file_path']}\n"
            "\u8be5\u7ed3\u679c\u7531 RAG \u68c0\u7d22\u4e0e\u89c4\u683c\u63a8\u5bfc\u5f97\u5230\u3002"
        )
        smoke_validation = generated.get("smoke_validation", {})
        smoke_status = str(smoke_validation.get("status", "")).strip().lower()
        if smoke_status == "passed":
            runner_label = str(smoke_validation.get("runner", "MATLAB/Octave")).strip() or "MATLAB/Octave"
            response += f"\n\u5df2\u901a\u8fc7 {runner_label} \u8bed\u6cd5\u70df\u6d4b\u3002"
        elif smoke_status == "skipped":
            smoke_message = smoke_validation.get("message", "MATLAB/Octave \u8bed\u6cd5\u70df\u6d4b\u672a\u6267\u884c")
            response += f"\n\u6ce8\u610f\uff1a{smoke_message}\u3002"
        if generation_ir:
            response += "\n\u6ce8\u610f\uff1a\u672c\u6b21\u751f\u6210\u524d\u5df2\u5b8c\u6210\u7ed3\u6784\u5316\u69fd\u4f4d\u6536\u96c6\u3002"
        if used_legacy_fallback:
            response += "\n\u6ce8\u610f\uff1a\u672c\u6b21\u4f7f\u7528\u4e86\u6a21\u677f\u515c\u5e95\u751f\u6210\u3002"
        if auto_repaired_by_llm:
            response += "\n\u6ce8\u610f\uff1aModelSpec \u7ecf\u81ea\u52a8\u4fee\u590d\u540e\u901a\u8fc7\u6821\u9a8c\u3002"
        if auto_recovered_by_heuristic:
            response += "\n\u6ce8\u610f\uff1aLLM \u89c4\u683c\u6821\u9a8c\u5931\u8d25\uff0c\u5df2\u81ea\u52a8\u4f7f\u7528\u542f\u53d1\u5f0f\u89c4\u683c\u4fee\u590d\u3002"
        if request_dynamic_library:
            if dll_result.get("status") == "success":
                if dll_result.get("artifact_paths"):
                    response += "\n已自动完成 DLL 构建：\n" + "\n".join(dll_result.get("artifact_paths", []))
                else:
                    response += "\n已自动触发 DLL 构建。"
            else:
                response += "\nDLL 构建结果：" + (
                    str(dll_result.get("message", "")).strip() or str(dll_result.get("status", "skipped"))
                )

        generation_trace = self._build_generation_trace(
            event="generation_succeeded",
            session_id=session_id,
            match_assessment=match_assessment or {},
            generation_ir=generation_ir or {},
            clarify_stage="ready",
            final_generated=True,
        )
        self._log_generation_trace(generation_trace)

        self._append_history(session_id, "user", text)
        self._append_history(session_id, "assistant", response)

        return {
            "message": response,
            "data": {
                "query_type": "matlab_generation_dll" if request_dynamic_library else "matlab_generation",
                "session_id": session_id,
                "session_store_backend": self.session_store.backend_name,
                "model_id": generated.get("model_id"),
                "model_name": model_name,
                "generated_file": generated.get("file_name"),
                "generated_file_path": generated.get("file_path"),
                "request_dynamic_library": bool(request_dynamic_library),
                "dll_build_status": dll_result.get("status", "") if request_dynamic_library else "",
                "dll_artifact_paths": dll_result.get("artifact_paths", []) if request_dynamic_library else [],
                "dll_entry_function": dll_result.get("entry_function", "") if request_dynamic_library else "",
                "dll_entry_args_schema": dll_result.get("entry_args_schema", []) if request_dynamic_library else [],
                "dll_build": dll_result.get("build_result", {}) if request_dynamic_library else {},
                "script": generated.get("script"),
                "static_validation": generated.get("static_validation"),
                "smoke_validation": generated.get("smoke_validation"),
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
                "generation_match": match_assessment or {},
                "generation_ir": generation_ir or {},
                "generation_trace": generation_trace,
            },
        }

    def _resume_pending_generation_match(
        self,
        text: str,
        session_id: str,
        pending_generation_match: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalized_pending_match = self._normalize_pending_generation_match(pending_generation_match)
        request_dynamic_library = bool(normalized_pending_match.get("request_dynamic_library", False))
        original_query = str(normalized_pending_match.get("original_query", "")).strip()
        clarified_reply = self._materialize_match_reply(text, normalized_pending_match)
        combined_query = f"{original_query} {clarified_reply}".strip() if original_query else clarified_reply
        self._clear_pending_generation_match(session_id)
        retrieved_docs = self.retriever.retrieve(combined_query, top_k=10)
        planner = {
            "task_type": "matlab_generation_dll" if request_dynamic_library else "matlab_generation",
            "confidence": 1.0,
            "source": "generation_match_clarify_resume",
            "wants_dynamic_library": request_dynamic_library,
        }
        match_assessment = self.retriever.assess_generation_match(combined_query, retrieved_docs)
        if not match_assessment.get("should_generate", True):
            return self._handle_generation_clarify(
                text=combined_query,
                session_id=session_id,
                retrieved_docs=retrieved_docs,
                planner=planner,
                match_assessment=match_assessment,
                clarify_stage=self._resolve_clarify_stage(match_assessment=match_assessment),
                request_dynamic_library=request_dynamic_library,
            )

        generation_ir = self.structured_ir.begin_collection(combined_query, match_assessment)
        if generation_ir and self.structured_ir.should_clarify(generation_ir):
            return self._handle_generation_clarify(
                text=combined_query,
                session_id=session_id,
                retrieved_docs=retrieved_docs,
                planner=planner,
                match_assessment=match_assessment,
                generation_ir=generation_ir,
                clarify_stage=CLARIFY_STAGE_SLOT,
                request_dynamic_library=request_dynamic_library,
            )
        return self._handle_generation_intent(
            text=combined_query,
            session_id=session_id,
            retrieved_docs=retrieved_docs,
            planner=planner,
            match_assessment=match_assessment,
            prefilled_spec=self.structured_ir.to_model_spec(generation_ir) if generation_ir else None,
            generation_ir=generation_ir,
            request_dynamic_library=request_dynamic_library,
        )

    def _resume_pending_generation_ir(
        self,
        text: str,
        session_id: str,
        pending_generation_ir: Dict[str, Any],
        request_dynamic_library: bool = False,
    ) -> Dict[str, Any]:
        normalized_pending_ir = self._normalize_pending_generation_ir(pending_generation_ir)
        request_dynamic_library = bool(
            request_dynamic_library
            or self._extract_pending_generation_ir_request_dynamic_library(pending_generation_ir)
        )
        updated_ir = self.structured_ir.continue_collection(normalized_pending_ir, text)
        combined_query = f"{updated_ir.get('task_goal', '')} {text}".strip()
        retrieved_docs = self.retriever.retrieve(combined_query, top_k=10)
        planner = {
            "task_type": "matlab_generation_dll" if request_dynamic_library else "matlab_generation",
            "confidence": 1.0,
            "source": "structured_generation_ir_resume",
            "wants_dynamic_library": request_dynamic_library,
        }
        match_assessment = self.retriever.assess_generation_match(
            str(updated_ir.get("task_goal", "")),
            retrieved_docs,
        )
        if self.structured_ir.should_clarify(updated_ir):
            return self._handle_generation_clarify(
                text=text,
                session_id=session_id,
                retrieved_docs=retrieved_docs,
                planner=planner,
                match_assessment=match_assessment,
                generation_ir=updated_ir,
                clarify_stage=CLARIFY_STAGE_SLOT,
                request_dynamic_library=request_dynamic_library,
            )
        return self._handle_generation_intent(
            text=combined_query,
            session_id=session_id,
            retrieved_docs=retrieved_docs,
            planner=planner,
            match_assessment=match_assessment,
            prefilled_spec=self.structured_ir.to_model_spec(updated_ir),
            generation_ir=updated_ir,
            request_dynamic_library=request_dynamic_library,
        )

    def _looks_like_generation_match_reply(self, text: str, pending_generation_match: Dict[str, Any]) -> bool:
        stage = self._get_match_clarify_stage(pending_generation_match)
        if stage == CLARIFY_STAGE_OBJECT:
            return bool((text or "").strip())
        lowered = text.lower()
        if "template_family=" in lowered or "model_id=" in lowered:
            return True
        if stage == CLARIFY_STAGE_FAMILY and self._looks_like_family_confirmation(text):
            return True
        if self.retriever._detect_query_domains(text):
            return True
        match_assessment = pending_generation_match.get("match_assessment", {})
        candidate_tokens: List[str] = []
        for item in match_assessment.get("family_candidates", [])[:3]:
            normalized = str(item.get("family", "") or "").strip().lower()
            if normalized:
                candidate_tokens.append(normalized)
        for item in match_assessment.get("top_candidates", [])[:3]:
            for token in [item.get("model_id", ""), item.get("template_family", "")]:
                normalized = str(token or "").strip().lower()
                if normalized:
                    candidate_tokens.append(normalized)
        top_family = str(match_assessment.get("top_family", "")).strip().lower()
        if top_family:
            candidate_tokens.append(top_family)
        return any(token in lowered for token in candidate_tokens)

    def _get_pending_generation_match(self, session_id: str) -> Dict[str, Any] | None:
        return self.session_store.get_state(session_id, PENDING_GENERATION_MATCH_STATE)

    def _set_pending_generation_match(self, session_id: str, value: Dict[str, Any]) -> None:
        self.session_store.set_state(session_id, PENDING_GENERATION_MATCH_STATE, value)

    def _clear_pending_generation_match(self, session_id: str) -> None:
        self.session_store.clear_state(session_id, PENDING_GENERATION_MATCH_STATE)

    def _get_pending_generation_ir(self, session_id: str) -> Dict[str, Any] | None:
        return self.session_store.get_state(session_id, PENDING_GENERATION_IR_STATE)

    def _set_pending_generation_ir(
        self,
        session_id: str,
        generation_ir: Dict[str, Any],
        request_dynamic_library: bool = False,
    ) -> None:
        self.session_store.set_state(
            session_id,
            PENDING_GENERATION_IR_STATE,
            {
                "generation_ir": dict(generation_ir),
                "request_dynamic_library": bool(request_dynamic_library),
            },
        )

    def _clear_pending_generation_ir(self, session_id: str) -> None:
        self.session_store.clear_state(session_id, PENDING_GENERATION_IR_STATE)

    def _normalize_pending_generation_match(
        self,
        pending_generation_match: Dict[str, Any] | None,
    ) -> Dict[str, Any] | None:
        if not pending_generation_match:
            return None
        normalized = dict(pending_generation_match)
        normalized["clarify_stage"] = self._get_match_clarify_stage(normalized)
        return normalized

    def _normalize_pending_generation_ir(
        self,
        pending_generation_ir: Dict[str, Any] | None,
    ) -> Dict[str, Any] | None:
        if not pending_generation_ir:
            return None
        generation_ir = pending_generation_ir.get("generation_ir")
        if isinstance(generation_ir, dict):
            normalized = dict(generation_ir)
        else:
            normalized = dict(pending_generation_ir)
        normalized.pop("generation_ir", None)
        normalized.pop("request_dynamic_library", None)
        normalized["clarify_stage"] = CLARIFY_STAGE_SLOT
        return normalized

    def _extract_pending_generation_ir_request_dynamic_library(
        self,
        pending_generation_ir: Dict[str, Any] | None,
    ) -> bool:
        if not pending_generation_ir:
            return False
        return bool(pending_generation_ir.get("request_dynamic_library", False))

    def _resolve_clarify_stage(
        self,
        match_assessment: Dict[str, Any] | None = None,
        generation_ir: Dict[str, Any] | None = None,
        preferred_stage: str = "",
    ) -> str:
        assessment = match_assessment or {}
        stage = str(preferred_stage or assessment.get("clarify_stage", "") or "").strip().lower()
        if stage in {CLARIFY_STAGE_OBJECT, CLARIFY_STAGE_FAMILY, CLARIFY_STAGE_SLOT}:
            return stage
        if generation_ir:
            return CLARIFY_STAGE_SLOT
        reject_reasons = [str(item).strip() for item in assessment.get("reject_reasons", []) if str(item).strip()]
        if not reject_reasons:
            reason = str(assessment.get("reason", "")).strip()
            if reason:
                reject_reasons = [reason]
        if any(reason.endswith("_needs_object") or reason in OBJECT_CLARIFY_REASONS for reason in reject_reasons):
            return CLARIFY_STAGE_OBJECT
        if assessment.get("top_family") or assessment.get("family_candidates"):
            return CLARIFY_STAGE_FAMILY
        return CLARIFY_STAGE_OBJECT

    def _get_match_clarify_stage(self, pending_generation_match: Dict[str, Any]) -> str:
        return self._resolve_clarify_stage(
            match_assessment=pending_generation_match.get("match_assessment", {}),
            preferred_stage=str(pending_generation_match.get("clarify_stage", "")),
        )

    def _looks_like_family_confirmation(self, text: str) -> bool:
        lowered = (text or "").lower()
        return any(marker in lowered for marker in FAMILY_CONFIRM_MARKERS)

    def _materialize_match_reply(self, text: str, pending_generation_match: Dict[str, Any]) -> str:
        if self._get_match_clarify_stage(pending_generation_match) != CLARIFY_STAGE_FAMILY:
            return text
        manual_selection = self.retriever._extract_manual_generation_selection(text)
        if any(str(value or "").strip() for value in manual_selection.values()):
            return text
        lowered = (text or "").lower()
        match_assessment = pending_generation_match.get("match_assessment", {})
        for item in match_assessment.get("top_candidates", [])[:3]:
            model_id = str(item.get("model_id", "") or "").strip()
            if model_id and model_id.lower() in lowered:
                return f"{text} model_id={model_id}".strip()
        family_tokens: List[str] = []
        top_family = str(match_assessment.get("top_family", "") or "").strip()
        if top_family:
            family_tokens.append(top_family)
        for item in match_assessment.get("family_candidates", [])[:3]:
            family = str(item.get("family", "") or "").strip()
            if family:
                family_tokens.append(family)
        for item in match_assessment.get("top_candidates", [])[:3]:
            family = str(item.get("template_family", "") or "").strip()
            if family:
                family_tokens.append(family)
        for family in dict.fromkeys(family_tokens):
            if family.lower() in lowered:
                return f"{text} template_family={family}".strip()
        if self._looks_like_family_confirmation(text) and top_family:
            return f"{text} template_family={top_family}".strip()
        return text

    def _build_match_clarify_message(self, match_assessment: Dict[str, Any], stage: str) -> str:
        out_of_scope_message = self._build_out_of_scope_clarify_message(match_assessment)
        if out_of_scope_message:
            return out_of_scope_message
        if stage == CLARIFY_STAGE_OBJECT:
            return self._build_object_clarify_message(match_assessment)
        return self._build_family_clarify_message(match_assessment)

    def _is_out_of_scope_clarify(self, match_assessment: Dict[str, Any]) -> bool:
        reject_reasons = self._normalize_trace_list(match_assessment.get("reject_reasons", []))
        if "out_of_scope" not in reject_reasons:
            return False
        guardrail = match_assessment.get("guardrail", {})
        if not isinstance(guardrail, dict):
            return False
        suggestions = self._normalize_trace_list(guardrail.get("suggestions", []))
        return bool(suggestions)

    def _build_out_of_scope_clarify_message(self, match_assessment: Dict[str, Any]) -> str:
        if not self._is_out_of_scope_clarify(match_assessment):
            return ""

        guardrail = match_assessment.get("guardrail", {})
        suggestions = self._normalize_trace_list(guardrail.get("suggestions", []))
        if not suggestions:
            suggestions = self._normalize_trace_list(match_assessment.get("suggestions", []))

        message_lines: List[str] = []
        if not suggestions or all("不在" not in item and "支持域" not in item for item in suggestions[:1]):
            message_lines.append("当前请求不在当前支持域内，暂不进入 MATLAB 建模生成。")

        for item in suggestions[:4]:
            if item and item not in message_lines:
                message_lines.append(item)

        if not message_lines:
            message_lines = [
                "当前请求不在当前支持域内，暂不进入 MATLAB 建模生成。",
                "如果你希望继续，请改写为支持域内的具体对象 + 场景/介质 + 关键参数。",
            ]
        return "\n".join(message_lines)

    def _family_choice_label(self, family: str) -> str:
        normalized = str(family or "").strip()
        if not normalized:
            return ""
        schema = self.structured_ir.schema_registry.get_schema(normalized)
        return str(schema.get("display_name", "") or normalized).strip()

    def _build_minimal_object_scene_question(self, match_assessment: Dict[str, Any]) -> str:
        guardrail = match_assessment.get("guardrail", {})
        matched_groups = guardrail.get("matched_groups", []) if isinstance(guardrail, dict) else []
        group_labels: List[str] = []
        for item in matched_groups[:3]:
            label = str(item.get("label", "") or "").strip()
            if label and label not in group_labels:
                group_labels.append(label)
        if group_labels:
            return f"你要建模的对象/场景更接近 {' / '.join(group_labels)} 中的哪一个？"

        family_labels: List[str] = []
        top_family = str(match_assessment.get("top_family", "") or "").strip()
        top_label = self._family_choice_label(top_family)
        if top_label:
            family_labels.append(top_label)
        for item in match_assessment.get("family_candidates", [])[:3]:
            label = self._family_choice_label(str(item.get("family", "") or item.get("template_family", "")))
            if label and label not in family_labels:
                family_labels.append(label)
        if family_labels:
            return f"你要的是哪种对象/场景：{' / '.join(family_labels[:3])}？"

        query_domains = [str(item).strip() for item in match_assessment.get("query_domains", []) if str(item).strip()]
        if "military_equipment" in query_domains:
            return "你要建模的是哪类对象/场景？例如导弹飞行、鱼雷水下发射或雷达目标跟踪。"
        if "battlefield_situation" in query_domains:
            return "你要建模的是哪类场景？例如态势感知、威胁评估、兵力消耗或拦截交战。"
        if "aerospace" in query_domains:
            return "你要建模的是哪类场景？例如火箭上升、轨道传播还是再入飞行？"
        return "你要建模的对象或场景具体是什么？"

    def _build_object_clarify_message(self, match_assessment: Dict[str, Any]) -> str:
        return self._build_minimal_object_scene_question(match_assessment)

    def _build_family_clarify_message(self, match_assessment: Dict[str, Any]) -> str:
        return self._build_minimal_object_scene_question(match_assessment)

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
            "我现在无法连接到本地 LLM 服务（Ollama），但仍可帮你做结构化任务。"
            "你可以直接说：\n"
            "1) `生成一个 PID 闭环模型，kp=1.5, ki=0.8, kd=0.02`\n"
            "2) `列出支持的 MATLAB 模型`"
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
            "浠ヤ笅鏄绱㈠埌鐨勭浉鍏崇煡璇嗚瘉鎹紝璇蜂紭鍏堜緷鎹繖浜涜瘉鎹綔绛旓細",
            f"璺敱寤鸿: task_type={planner.get('task_type','')}, confidence={planner.get('confidence',0)}",
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
        action_words = [
            "build",
            "generate",
            "create",
            "design",
            "implement",
            "simulate",
            "compile",
            "export",
            "package",
            "生成",
            "构建",
            "建立",
            "创建",
            "设计",
            "实现",
            "仿真",
            "建模",
            "编译",
            "导出",
            "打包",
            "做个",
        ]
        return any(action in lowered for action in action_words)

    def _is_generation_intent(self, text: str) -> bool:
        lowered = text.lower()
        keywords = [
            ".m",
            "matlab",
            "simulink",
            "model",
            "transfer function",
            "state space",
            "pid",
            "kalman",
            "mpc",
            "ode45",
            "rocket",
            "missile",
            "torpedo",
            "submarine",
            "satellite",
            "orbit",
            "radar",
            "tracking",
            "battlefield",
            "模型",
            "传递函数",
            "状态空间",
            "火箭",
            "导弹",
            "鱼雷",
            "潜艇",
            "卫星",
            "轨道",
            "雷达",
            "跟踪",
            "战场",
        ]
        return (any(keyword in lowered for keyword in keywords) or mentions_dynamic_library(text)) and self._has_generation_action(text)

    def _error(self, msg: str) -> Dict[str, Any]:
        return {"message": f"抱歉，{msg}", "data": {"query_type": "error"}}

    def test_query(self, test_cases: List[str] | None = None):
        if test_cases is None:
            test_cases = [
                "你好，介绍下你能做什么？",
                "生成一个 PID 闭环控制的 Simulink 模型，kp=1.8, ki=0.9, kd=0.05",
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
        print("AI 对话助手（支持 MATLAB 模型生成与 DLL 构建）")
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

