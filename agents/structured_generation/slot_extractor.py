"""Family-aware slot extraction layer for structured generation."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Sequence, Tuple

from .schema_registry import FamilySchemaRegistry


NUMBER_PATTERN = r"(?<![a-zA-Z_])-?\d+(?:\.\d+)?(?:e[+-]?\d+)?"
UNIT_ALIASES = {
    "km/s": ["km/s", "公里/秒", "千米/秒", "公里每秒", "千米每秒"],
    "m/s": ["m/s", "米/秒", "米每秒", "meter/s", "meters/s", "mps"],
    "km/h": ["km/h", "公里/小时", "千米/小时", "公里每小时", "千米每小时"],
    "rad/s": ["rad/s", "弧度/秒", "弧度每秒"],
    "deg/s": ["deg/s", "°/s", "度/秒", "度每秒"],
    "kg/m^3": ["kg/m^3", "kg/m3", "千克/立方米", "公斤/立方米"],
    "g/cm^3": ["g/cm^3", "g/cm3", "克/立方厘米"],
    "m^3": ["m^3", "m3", "m³", "立方米"],
    "m^2": ["m^2", "m2", "m²", "平方米"],
    "km": ["km", "公里", "千米"],
    "m": ["m", "米"],
    "kg": ["kg", "公斤", "千克"],
    "g": ["g", "克"],
    "t": ["t", "吨"],
    "min": ["min", "mins", "minute", "minutes", "分钟", "分"],
    "h": ["h", "hr", "hrs", "hour", "hours", "小时"],
    "deg": ["deg", "degree", "degrees", "°", "度"],
    "rad": ["rad", "radian", "radians", "弧度"],
    "s": ["s", "sec", "secs", "second", "seconds", "秒", "秒钟"],
}
UNIT_PATTERN = "|".join(
    re.escape(alias)
    for alias in sorted(
        {item.lower() for values in UNIT_ALIASES.values() for item in values},
        key=len,
        reverse=True,
    )
)
NUMBER_WITH_OPTIONAL_UNIT_PATTERN = (
    rf"(?P<number>{NUMBER_PATTERN})(?:\s*(?P<unit>{UNIT_PATTERN}))?"
)
SPECIAL_SLOT_ALIASES = {
    "altitude0": ["altitude", "高度", "轨道高度", "初始高度", "轨道初始高度"],
    "init_altitude": ["altitude", "高度", "初始高度", "飞行高度"],
    "vx0": ["vx", "v_x", "初始横向速度", "初始x方向速度", "x方向初速度"],
    "vy0": ["vy", "v_y", "初始纵向速度", "初始y方向速度", "y方向初速度"],
    "target_speed_x": [
        "vx",
        "v_x",
        "目标vx",
        "目标横向速度",
        "目标x方向速度",
        "target x speed",
        "target x velocity",
        "lateral speed",
        "lateral velocity",
    ],
    "target_speed_y": [
        "vy",
        "v_y",
        "目标vy",
        "目标纵向速度",
        "目标y方向速度",
        "target y speed",
        "target y velocity",
        "vertical speed",
        "vertical velocity",
    ],
}
PAIR_SLOT_GROUPS = [
    ("target_speed_x", "target_speed_y"),
    ("vx0", "vy0"),
    ("x0", "y0"),
]


class FamilySlotExtractor:
    """Extract numeric slot values from free-form user text using family schema."""

    def __init__(self, schema_registry: FamilySchemaRegistry):
        self.schema_registry = schema_registry

    def extract_slots(
        self,
        text: str,
        family: str,
        preferred_slots: List[str] | None = None,
    ) -> Dict[str, float | int]:
        return self.extract_slot_details(text, family, preferred_slots=preferred_slots)["values"]

    def extract_slot_details(
        self,
        text: str,
        family: str,
        preferred_slots: List[str] | None = None,
    ) -> Dict[str, Any]:
        lowered = self._normalize_text(text)
        slot_defs = self.schema_registry.get_slot_defs(family)
        extracted: Dict[str, float | int] = {}
        matched_spans: List[Tuple[int, int]] = []
        ordered_keys = list(preferred_slots or [])
        ordered_keys.extend(key for key in slot_defs.keys() if key not in ordered_keys)

        pair_values = self._extract_paired_slots(lowered, slot_defs, ordered_keys)
        for key, payload in pair_values.items():
            value = payload["value"]
            extracted[key] = int(value) if key in {"steps"} else value
            matched_spans.append(payload["span"])

        for key in ordered_keys:
            if key in extracted:
                continue
            slot_def = slot_defs.get(key, {})
            matched = self._extract_named_number(lowered, key, slot_def)
            if matched is None:
                continue
            value, span = matched
            extracted[key] = int(value) if key in {"steps"} else value
            matched_spans.append(span)

        stop_time = self._extract_stop_time(lowered)
        if stop_time is not None and "stop_time" in slot_defs and "stop_time" not in extracted:
            extracted["stop_time"] = stop_time[0]
            matched_spans.append(stop_time[1])

        return {
            "values": extracted,
            "matched_spans": matched_spans,
            "normalized_text": lowered,
        }

    @staticmethod
    def flatten_collected(collected_slots: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        return {
            key: value.get("value")
            for key, value in collected_slots.items()
            if isinstance(value, dict) and "value" in value
        }

    def extract_positional_values(
        self,
        text: str,
        family: str,
        slot_keys: Sequence[str],
        exclude_spans: Sequence[Tuple[int, int]] | None = None,
    ) -> Dict[str, float | int]:
        lowered = self._normalize_text(text)
        slot_defs = self.schema_registry.get_slot_defs(family)
        candidates = self._extract_number_candidates(lowered, exclude_spans=exclude_spans)
        extracted: Dict[str, float | int] = {}
        candidate_index = 0
        for key in slot_keys:
            if candidate_index >= len(candidates):
                break
            slot_def = slot_defs.get(key, {})
            candidate = candidates[candidate_index]
            candidate_index += 1
            value = self._convert_value(
                candidate["value"],
                candidate.get("unit", ""),
                str(slot_def.get("unit", "") or ""),
            )
            extracted[key] = int(value) if key in {"steps"} else value
        return extracted

    @staticmethod
    def extract_positional_numbers(text: str) -> List[float]:
        lowered = FamilySlotExtractor._normalize_text(text)
        return [
            float(matched.group("number"))
            for matched in re.finditer(NUMBER_WITH_OPTIONAL_UNIT_PATTERN, lowered)
        ]

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = str(text or "").lower()
        translation_table = str.maketrans(
            {
                "：": ":",
                "，": ",",
                "；": ";",
                "。": ".",
                "（": "(",
                "）": ")",
                "【": "[",
                "】": "]",
                "＝": "=",
                "／": "/",
                "、": ",",
            }
        )
        normalized = normalized.translate(translation_table)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    def _extract_named_number(self, text: str, slot_key: str, slot_def: Dict[str, Any]) -> Tuple[float, Tuple[int, int]] | None:
        expected_unit = str(slot_def.get("unit", "") or "")
        for alias_text in self._slot_alias_variants(slot_key, slot_def):
            token = self._alias_pattern(alias_text)
            patterns = [
                rf"{token}\s*(?:=|:|为|是|取|设为|设成)?\s*{NUMBER_WITH_OPTIONAL_UNIT_PATTERN}",
                rf"{token}[^\d\-]{{0,8}}{NUMBER_WITH_OPTIONAL_UNIT_PATTERN}",
                rf"{NUMBER_WITH_OPTIONAL_UNIT_PATTERN}\s*(?:的)?\s*{token}",
            ]
            for pattern in patterns:
                matched = re.search(pattern, text)
                if not matched:
                    continue
                value = self._convert_value(
                    float(matched.group("number")),
                    matched.group("unit") or "",
                    expected_unit,
                )
                return value, matched.span()
        return None

    def _extract_paired_slots(
        self,
        text: str,
        slot_defs: Dict[str, Dict[str, Any]],
        ordered_keys: Sequence[str],
    ) -> Dict[str, Dict[str, Any]]:
        extracted: Dict[str, Dict[str, Any]] = {}
        ordered_set = set(ordered_keys)
        for left_key, right_key in PAIR_SLOT_GROUPS:
            if left_key not in ordered_set or right_key not in ordered_set:
                continue
            left_def = slot_defs.get(left_key)
            right_def = slot_defs.get(right_key)
            if not left_def or not right_def:
                continue
            pair_match = self._extract_slot_pair(text, left_key, left_def, right_key, right_def)
            if pair_match is None:
                continue
            left_value, right_value, span = pair_match
            extracted[left_key] = {"value": left_value, "span": span}
            extracted[right_key] = {"value": right_value, "span": span}
        return extracted

    def _extract_slot_pair(
        self,
        text: str,
        left_key: str,
        left_def: Dict[str, Any],
        right_key: str,
        right_def: Dict[str, Any],
    ) -> Tuple[float, float, Tuple[int, int]] | None:
        separators = r"(?:/|,|，|、|和|与|and)"
        for left_alias in self._slot_alias_variants(left_key, left_def):
            for right_alias in self._slot_alias_variants(right_key, right_def):
                left_token = self._alias_pattern(left_alias)
                right_token = self._alias_pattern(right_alias)
                patterns = [
                    (
                        rf"{left_token}\s*/\s*{right_token}\s*(?:=|:|为|是|分别为)?\s*"
                        rf"(?P<n1>{NUMBER_PATTERN})(?:\s*(?P<u1>{UNIT_PATTERN}))?\s*{separators}\s*"
                        rf"(?P<n2>{NUMBER_PATTERN})(?:\s*(?P<u2>{UNIT_PATTERN}))?"
                    ),
                    (
                        rf"{left_token}\s*(?:和|与|and)\s*{right_token}\s*(?:=|:|为|是|分别为)?\s*"
                        rf"(?P<n1>{NUMBER_PATTERN})(?:\s*(?P<u1>{UNIT_PATTERN}))?\s*{separators}\s*"
                        rf"(?P<n2>{NUMBER_PATTERN})(?:\s*(?P<u2>{UNIT_PATTERN}))?"
                    ),
                ]
                for pattern in patterns:
                    matched = re.search(pattern, text)
                    if not matched:
                        continue
                    unit_1 = matched.group("u1") or matched.group("u2") or ""
                    unit_2 = matched.group("u2") or matched.group("u1") or ""
                    left_value = self._convert_value(float(matched.group("n1")), unit_1, str(left_def.get("unit", "") or ""))
                    right_value = self._convert_value(float(matched.group("n2")), unit_2, str(right_def.get("unit", "") or ""))
                    return left_value, right_value, matched.span()
        return None

    @staticmethod
    def _extract_number_candidates(
        text: str,
        exclude_spans: Sequence[Tuple[int, int]] | None = None,
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for matched in re.finditer(NUMBER_WITH_OPTIONAL_UNIT_PATTERN, text):
            span = matched.span()
            if FamilySlotExtractor._span_overlaps(span, exclude_spans or []):
                continue
            candidates.append(
                {
                    "value": float(matched.group("number")),
                    "unit": matched.group("unit") or "",
                    "span": span,
                }
            )
        return candidates

    @staticmethod
    def _span_overlaps(span: Tuple[int, int], spans: Sequence[Tuple[int, int]]) -> bool:
        start, end = span
        for other_start, other_end in spans:
            if start < other_end and other_start < end:
                return True
        return False

    @staticmethod
    def _alias_pattern(alias_text: str) -> str:
        token = re.escape(alias_text)
        if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", alias_text):
            return rf"(?<![a-zA-Z0-9_]){token}(?![a-zA-Z0-9_])"
        return token

    @staticmethod
    def _slot_alias_variants(slot_key: str, slot_def: Dict[str, Any]) -> List[str]:
        aliases = list(slot_def.get("aliases", []))
        aliases.extend(SPECIAL_SLOT_ALIASES.get(slot_key, []))
        deduped: List[str] = []
        seen = set()
        for alias in aliases:
            value = str(alias or "").strip().lower()
            if not value:
                continue
            variants = {value, value.replace("_", " "), value.replace(" ", "")}
            for item in variants:
                item = item.strip()
                if not item or item in seen:
                    continue
                seen.add(item)
                deduped.append(item)
        return sorted(deduped, key=len, reverse=True)

    @staticmethod
    def _normalize_unit(unit_text: str) -> str:
        normalized = str(unit_text or "").strip().lower().replace(" ", "")
        if not normalized:
            return ""
        for canonical, aliases in UNIT_ALIASES.items():
            if normalized == canonical:
                return canonical
            for alias in aliases:
                if normalized == alias.lower().replace(" ", ""):
                    return canonical
        return normalized

    @staticmethod
    def _convert_value(value: float, unit_text: str, expected_unit: str) -> float:
        normalized_unit = FamilySlotExtractor._normalize_unit(unit_text)
        normalized_expected = FamilySlotExtractor._normalize_unit(expected_unit)
        if not normalized_unit or not normalized_expected or normalized_unit == normalized_expected:
            return value

        conversions = {
            "m": {"m": 1.0, "km": 1000.0},
            "m/s": {"m/s": 1.0, "km/s": 1000.0, "km/h": 1000.0 / 3600.0},
            "s": {"s": 1.0, "min": 60.0, "h": 3600.0},
            "deg": {"deg": 1.0, "rad": 180.0 / math.pi},
            "rad/s": {"rad/s": 1.0, "deg/s": math.pi / 180.0},
            "kg": {"kg": 1.0, "g": 0.001, "t": 1000.0},
            "m^2": {"m^2": 1.0},
            "m^3": {"m^3": 1.0},
            "kg/m^3": {"kg/m^3": 1.0, "g/cm^3": 1000.0},
        }
        factor = conversions.get(normalized_expected, {}).get(normalized_unit)
        if factor is None:
            return value
        return value * factor

    @staticmethod
    def _extract_stop_time(text: str) -> Tuple[float, Tuple[int, int]] | None:
        patterns = [
            rf"(?:仿真|模拟|运行)\s*(?P<number>{NUMBER_PATTERN})(?:\s*(?P<unit>{UNIT_PATTERN}))?",
            rf"stop[_\s-]?time\s*(?:=|:)?\s*(?P<number>{NUMBER_PATTERN})(?:\s*(?P<unit>{UNIT_PATTERN}))?",
        ]
        for pattern in patterns:
            matched = re.search(pattern, text)
            if not matched:
                continue
            value = FamilySlotExtractor._convert_value(float(matched.group("number")), matched.group("unit") or "", "s")
            return value, matched.span()
        return None


__all__ = ["FamilySlotExtractor"]
