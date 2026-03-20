"""Clarify policy layer for family-organized slot collection."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from knowledge_base.model_family_codegen import FAMILY_PARAMETER_DEFAULTS

from .schema_registry import FamilySchemaRegistry
from .slot_extractor import FamilySlotExtractor

DEFAULT_MARKERS = ["默认", "按默认", "默认值", "use default", "default"]
CANCEL_MARKERS = ["取消", "算了", "停止", "cancel", "abort"]
CONFIRM_MARKERS = ["继续", "开始", "生成", "就这样", "可以", "确认"]
MAX_CLARIFY_SLOT_QUESTIONS = 3


class FamilyClarifyPolicy:
    """Owns slot-driven clarification behavior and reply interpretation."""

    def __init__(self, schema_registry: FamilySchemaRegistry, slot_extractor: FamilySlotExtractor):
        self.schema_registry = schema_registry
        self.slot_extractor = slot_extractor

    def wants_defaults(self, text: str) -> bool:
        lowered = (text or "").lower()
        return any(marker in lowered for marker in DEFAULT_MARKERS)

    def wants_cancel(self, text: str) -> bool:
        lowered = (text or "").lower()
        return any(marker in lowered for marker in CANCEL_MARKERS)

    def looks_like_slot_reply(self, text: str, generation_ir: Dict[str, Any], family: str = "") -> bool:
        lowered = (text or "").lower()
        if any(marker in lowered for marker in DEFAULT_MARKERS + CONFIRM_MARKERS):
            return True
        if re.search(r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?", lowered):
            return True
        resolved_family = family or self.schema_registry.resolve_generation_family(generation_ir)
        slot_defs = self.schema_registry.get_slot_defs(resolved_family)
        for slot in slot_defs.values():
            for alias in slot.get("aliases", []):
                if str(alias).lower() in lowered:
                    return True
        return False

    def should_clarify(self, generation_ir: Dict[str, Any]) -> bool:
        return bool(generation_ir and generation_ir.get("missing_info", []))

    @staticmethod
    def _limit_slots(slots: List[str], limit: int = MAX_CLARIFY_SLOT_QUESTIONS) -> List[str]:
        return [str(slot).strip() for slot in slots if str(slot).strip()][:limit]

    def _select_slots_for_question(
        self,
        slot_collection: Dict[str, Any],
        defaults: Dict[str, Any] | None = None,
    ) -> List[str]:
        missing_critical_slots = list(slot_collection.get("missing_critical_slots", []))
        if missing_critical_slots:
            return self._limit_slots(missing_critical_slots)

        default_values = defaults or {}
        missing_defaultable_slots = list(slot_collection.get("missing_defaultable_slots", []))
        without_defaults = [slot for slot in missing_defaultable_slots if slot not in default_values]
        with_defaults = [slot for slot in missing_defaultable_slots if slot in default_values]
        return self._limit_slots([*without_defaults, *with_defaults])

    def build_reply_template(
        self,
        family: str,
        missing_slots: List[str],
        defaults: Dict[str, Any] | None = None,
    ) -> str:
        slot_defs = self.schema_registry.get_slot_defs(family)
        default_values = defaults or dict(FAMILY_PARAMETER_DEFAULTS.get(family, {}))
        asked_slots = self._limit_slots(missing_slots)
        parts: List[str] = []
        for key in asked_slots:
            slot_def = slot_defs.get(key, {})
            label = slot_def.get("label", key)
            example_value = default_values.get(key, "...") if slot_def.get("is_defaultable_slot") else "..."
            parts.append(f"{label}={example_value}")
        if parts:
            return "， ".join(parts)

        has_defaultable_reply = any(
            slot_defs.get(key, {}).get("is_defaultable_slot") and key in default_values for key in missing_slots
        )
        return "按默认值继续" if has_defaultable_reply else ""

    def build_clarify_message(self, generation_ir: Dict[str, Any], family: str = "") -> str:
        resolved_family = family or self.schema_registry.resolve_generation_family(generation_ir)
        if not self.schema_registry.supports_family(resolved_family):
            return "请先说明你要建模的对象或场景是什么？"

        schema = self.schema_registry.get_schema(resolved_family)
        model_name = str(
            generation_ir.get(
                "model_name",
                generation_ir.get("model_id", self.schema_registry.display_name(resolved_family)),
            )
        )
        model_id = str(generation_ir.get("model_id", "")).strip()
        slot_collection = generation_ir.get("slot_collection", {})
        missing_critical_slots = list(slot_collection.get("missing_critical_slots", []))
        missing_defaultable_slots = list(slot_collection.get("missing_defaultable_slots", []))
        if not missing_critical_slots and not missing_defaultable_slots:
            return "参数已齐，可以继续生成。"

        collection_stage = str(slot_collection.get("collection_stage", "")).strip() or (
            "critical" if missing_critical_slots else "defaultable" if missing_defaultable_slots else "ready"
        )
        slot_defs = schema.get("slot_defs", {})
        defaults = dict(generation_ir.get("defaults", {}))
        asked_slots = self._select_slots_for_question(slot_collection, defaults)

        def format_missing_line(key: str, allow_default_hint: bool = False) -> str:
            slot_def = slot_defs.get(key, {})
            label = slot_def.get("label", key)
            unit = str(slot_def.get("unit", "") or "").strip()
            unit_text = f" ({unit})" if unit and unit != "-" else ""
            default_hint = defaults.get(key)
            if allow_default_hint and default_hint is not None:
                return f"- {label}{unit_text}，默认值 {default_hint}"
            return f"- {label}{unit_text}"

        example_reply = self.build_reply_template(resolved_family, asked_slots, defaults)
        target_label = (
            f"{model_name} ({model_id})"
            if model_id
            else self.schema_registry.display_name(resolved_family)
        )
        parts = [f"已锁定模型：{target_label}。"]

        if collection_stage == "critical" and asked_slots:
            parts.append(
                "请先补充这 {} 个关键参数：\n{}".format(
                    len(asked_slots),
                    "\n".join(format_missing_line(key) for key in asked_slots),
                )
            )
            if example_reply:
                parts.append("可直接回复：\n" + example_reply)
            parts.append("也可以回复“取消”。")
            return "\n".join(parts)

        defaultable_with_defaults = [key for key in missing_defaultable_slots if key in defaults]
        if asked_slots:
            parts.append(
                "如需自定义，请补充这 {} 个参数：\n{}".format(
                    len(asked_slots),
                    "\n".join(format_missing_line(key, allow_default_hint=True) for key in asked_slots),
                )
            )
            if example_reply:
                parts.append("可直接回复：\n" + example_reply)
        if defaultable_with_defaults:
            parts.append("如无特殊要求，回复“按默认值继续”即可。")
            parts.append("该操作只会补齐有默认值的 `defaultable_slots`。")
        parts.append("也可以回复“取消”。")
        return "\n".join(parts)

    def apply_reply(self, pending_ir: Dict[str, Any], reply: str, family: str) -> Dict[str, Any]:
        slot_collection = dict(pending_ir.get("slot_collection", {}))
        collected_slots = dict(slot_collection.get("collected_slots", {}))
        defaults = dict(pending_ir.get("defaults", {}))
        missing_slots = list(slot_collection.get("missing_slots", []))
        defaultable_missing_slots = list(slot_collection.get("missing_defaultable_slots", []))
        extraction = self.slot_extractor.extract_slot_details(reply, family, preferred_slots=missing_slots)
        extracted = dict(extraction.get("values", {}))
        unresolved_for_positional = [key for key in missing_slots if key not in extracted]
        if unresolved_for_positional:
            positional_values = self.slot_extractor.extract_positional_values(
                reply,
                family,
                unresolved_for_positional[:4],
                exclude_spans=extraction.get("matched_spans", []),
            )
            extracted.update(positional_values)
        for key, value in extracted.items():
            collected_slots[key] = {"value": value, "source": "reply"}

        used_default_fill = False
        if self.wants_defaults(reply):
            for key in defaultable_missing_slots:
                if key in defaults and key not in collected_slots:
                    collected_slots[key] = {"value": defaults[key], "source": "default"}
                    used_default_fill = True

        filled_values = self.slot_extractor.flatten_collected(collected_slots)
        slot_summary = self.schema_registry.summarize_slot_collection(family, collected_slots, defaults=defaults)

        slot_collection["collected_slots"] = collected_slots
        slot_collection["last_user_reply"] = reply
        slot_collection["used_default_fill"] = used_default_fill
        slot_collection["filled_parameters"] = {**defaults, **filled_values}
        slot_collection["identify_slots"] = slot_summary["identify_slots"]
        slot_collection["critical_slots"] = slot_summary["critical_slots"]
        slot_collection["defaultable_slots"] = slot_summary["defaultable_slots"]
        slot_collection["required_slots"] = slot_summary["required_slots"]
        slot_collection["recommended_slots"] = slot_summary["recommended_slots"]
        slot_collection["missing_slots"] = slot_summary["active_missing_slots"]
        slot_collection["missing_critical_slots"] = slot_summary["missing_critical_slots"]
        slot_collection["missing_defaultable_slots"] = slot_summary["missing_defaultable_slots"]
        slot_collection["unresolved_slots"] = slot_summary["unresolved_slots"]
        slot_collection["collection_stage"] = slot_summary["collection_stage"]
        slot_collection["status"] = slot_summary["status"]
        slot_collection["schema_family"] = family
        return {
            "slot_collection": slot_collection,
            "filled_values": filled_values,
            "missing_slots": slot_summary["active_missing_slots"],
            "unresolved_slots": slot_summary["unresolved_slots"],
            "collected_slots": collected_slots,
            "used_default_fill": used_default_fill,
        }


__all__ = ["FamilyClarifyPolicy"]
