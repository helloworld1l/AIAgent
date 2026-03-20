"""Golden regression report for generation matching.

Release profile uses 30-50 curated golden cases and stricter gates.
Run this script after any knowledge-base, threshold, or alias change.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.structured_generation_ir import StructuredGenerationIR
from knowledge_base.rag_retriever import MatlabRAGRetriever


RELEASE_PROFILE = "release"
RELEASE_GOLDEN_CASE_RANGE = (30, 50)


def _case(
    name: str,
    query: str,
    reason: str,
    should_generate: bool,
    reject_reasons: List[str],
    query_domains: List[str],
    enters_clarify: bool,
    top_family: str = "",
    forbid_launch_dynamics: bool | None = None,
    track_core_family: bool = False,
    track_missing_critical_clarify: bool = False,
    track_object_guard: bool = False,
    track_family_clarify: bool = False,
) -> Dict[str, Any]:
    resolved_forbid_launch_dynamics = forbid_launch_dynamics
    if resolved_forbid_launch_dynamics is None:
        resolved_forbid_launch_dynamics = bool(top_family) and top_family != "launch_dynamics"

    case: Dict[str, Any] = {
        "name": name,
        "query": query,
        "reason": reason,
        "should_generate": should_generate,
        "reject_reasons": list(reject_reasons),
        "query_domains": list(query_domains),
        "enters_clarify": enters_clarify,
        "forbid_launch_dynamics": bool(resolved_forbid_launch_dynamics),
        "track_core_family": track_core_family,
        "track_missing_critical_clarify": track_missing_critical_clarify,
        "track_object_guard": track_object_guard,
        "track_family_clarify": track_family_clarify,
    }
    if top_family:
        case["top_family"] = top_family
    return case


def _matched_case(name: str, query: str, query_domains: List[str], top_family: str) -> Dict[str, Any]:
    return _case(
        name=name,
        query=query,
        reason="matched",
        should_generate=True,
        reject_reasons=[],
        query_domains=query_domains,
        enters_clarify=True,
        top_family=top_family,
        track_core_family=True,
        track_missing_critical_clarify=True,
    )


def _family_clarify_case(
    name: str,
    query: str,
    reason: str,
    reject_reasons: List[str],
    query_domains: List[str],
    top_family: str,
) -> Dict[str, Any]:
    return _case(
        name=name,
        query=query,
        reason=reason,
        should_generate=False,
        reject_reasons=reject_reasons,
        query_domains=query_domains,
        enters_clarify=True,
        top_family=top_family,
        track_family_clarify=True,
    )


def _object_guard_case(
    name: str,
    query: str,
    reason: str,
    query_domains: List[str],
) -> Dict[str, Any]:
    return _case(
        name=name,
        query=query,
        reason=reason,
        should_generate=False,
        reject_reasons=[reason],
        query_domains=query_domains,
        enters_clarify=True,
        forbid_launch_dynamics=True,
        track_object_guard=True,
    )


def _out_of_scope_case(name: str, query: str) -> Dict[str, Any]:
    return _case(
        name=name,
        query=query,
        reason="out_of_scope",
        should_generate=False,
        reject_reasons=["out_of_scope"],
        query_domains=[],
        enters_clarify=True,
        forbid_launch_dynamics=True,
        track_object_guard=True,
    )


CASES: List[Dict[str, Any]] = [
    _matched_case("rocket_short", "构建一个火箭垂直发射模型", ["aerospace"], "launch_dynamics"),
    _matched_case("rocket_full", "构建一个火箭垂直发射模型，考虑燃料消耗和空气阻力", ["aerospace"], "launch_dynamics"),
    _matched_case("launch_pitch", "构建一个垂直升空火箭模型，分析推力和高度变化", ["aerospace"], "launch_dynamics"),
    _matched_case("launch_upward", "构建一个火箭垂直上升模型", [], "launch_dynamics"),
    _matched_case("launch_drag_sim", "生成一个火箭垂直发射仿真，考虑推力和空气阻力", ["aerospace"], "launch_dynamics"),
    _matched_case("launch_speed_height", "做一个火箭上升仿真，输出速度和高度", [], "launch_dynamics"),
    _family_clarify_case(
        "launch_vehicle_ambiguous",
        "构建一个运载火箭升空模型，考虑推力和质量变化",
        "ambiguous_family",
        ["ambiguous_family"],
        ["aerospace"],
        "launch_dynamics",
    ),
    _family_clarify_case(
        "launch_vertical_family",
        "生成一个垂直发射动力学脚本，分析速度和高度",
        "family_needs_confirmation",
        ["family_needs_confirmation"],
        ["aerospace"],
        "launch_dynamics",
    ),
    _matched_case(
        "traj_missile_matched",
        "构建一个导弹二维弹道模型，给定发射角和初速度",
        ["missile"],
        "trajectory_ode",
    ),
    _matched_case(
        "traj_range",
        "构建一个导弹射程分析模型，给定初速度和发射角",
        ["missile"],
        "trajectory_ode",
    ),
    _matched_case(
        "traj_explicit",
        "构建一个导弹弹道飞行模型，给定初速度和发射角",
        ["missile"],
        "trajectory_ode",
    ),
    _family_clarify_case(
        "missile_needs_family_clarify",
        "构建一个导弹拦截模型",
        "family_needs_confirmation",
        ["family_needs_confirmation"],
        ["missile"],
        "trajectory_ode",
    ),
    _family_clarify_case(
        "traj_planar_family_confirm",
        "生成一个平面弹道轨迹仿真，考虑重力和阻力",
        "family_needs_confirmation",
        ["family_needs_confirmation"],
        ["missile"],
        "trajectory_ode",
    ),
    _family_clarify_case(
        "traj_shell_family_confirm",
        "构建一个炮弹抛射轨迹模型，输出射程与弹道高度",
        "family_needs_confirmation",
        ["family_needs_confirmation"],
        ["missile"],
        "trajectory_ode",
    ),
    _matched_case("orbit_short", "构建一个卫星二体轨道模型", ["space"], "orbital_dynamics"),
    _matched_case(
        "orbit_leo",
        "做一个近地卫星轨道传播仿真，输出轨道半径变化",
        ["space"],
        "orbital_dynamics",
    ),
    _matched_case(
        "orbit_gravity",
        "生成一个轨道动力学模型，考虑地球引力参数",
        ["space"],
        "orbital_dynamics",
    ),
    _matched_case(
        "orbit_period",
        "构建一个卫星绕地运行模型，分析轨道周期",
        ["space"],
        "orbital_dynamics",
    ),
    _matched_case(
        "orbit_init",
        "生成一个二体轨道仿真，给定初始位置和速度",
        ["space"],
        "orbital_dynamics",
    ),
    _matched_case("orbit_propagation", "构建一个卫星轨道传播模型", ["space"], "orbital_dynamics"),
    _matched_case("tracking_short", "构建一个雷达目标跟踪模型", ["radar_tracking"], "tracking_estimation"),
    _matched_case(
        "tracking_kalman",
        "做一个单目标卡尔曼滤波跟踪仿真，考虑量测噪声",
        ["radar_tracking"],
        "tracking_estimation",
    ),
    _matched_case(
        "tracking_process_noise",
        "生成一个目标航迹估计模型，加入过程噪声和观测误差",
        ["radar_tracking"],
        "tracking_estimation",
    ),
    _matched_case(
        "tracking_state",
        "构建一个二维目标状态估计模型，使用卡尔曼滤波",
        ["radar_tracking"],
        "tracking_estimation",
    ),
    _matched_case(
        "tracking_posvel",
        "做一个单目标跟踪脚本，输出位置速度估计",
        ["radar_tracking"],
        "tracking_estimation",
    ),
    _matched_case("tracking_track_estimation", "生成一个雷达航迹估计模型", ["radar_tracking"], "tracking_estimation"),
    _matched_case("attrition_short", "构建一个红蓝对抗兵力消耗模型", ["battlefield"], "combat_attrition"),
    _matched_case("attrition_curve", "生成一个兵力消耗仿真，分析战损曲线", ["battlefield"], "combat_attrition"),
    _matched_case(
        "attrition_battlefield",
        "生成一个战场兵力消耗脚本，输出战损曲线",
        ["battlefield"],
        "combat_attrition",
    ),
    _matched_case("combat_redblue", "生成一个红蓝兵力消耗模型", ["battlefield"], "combat_attrition"),
    _matched_case("combat_battlefield", "构建一个战场对抗模型，分析兵力消耗", ["battlefield"], "combat_attrition"),
    _family_clarify_case(
        "attrition_lanchester",
        "做一个兰彻斯特战损仿真，分析红蓝兵力剩余",
        "low_confidence",
        ["low_confidence", "ambiguous_family"],
        ["battlefield"],
        "combat_attrition",
    ),
    _family_clarify_case(
        "attrition_script_family_confirm",
        "生成一个战场对抗消耗脚本，给定杀伤率系数",
        "family_needs_confirmation",
        ["family_needs_confirmation", "low_confidence"],
        ["battlefield"],
        "combat_attrition",
    ),
    _family_clarify_case(
        "attrition_evolution",
        "构建一个红蓝双方战损演化模型",
        "family_needs_confirmation",
        ["family_needs_confirmation", "low_confidence"],
        ["battlefield"],
        "combat_attrition",
    ),
    _family_clarify_case(
        "battlefield_cover_fusion_family_confirm",
        "做一个战场覆盖与情报融合仿真",
        "family_needs_confirmation",
        ["family_needs_confirmation", "low_confidence"],
        ["battlefield"],
        "combat_attrition",
    ),
    _family_clarify_case(
        "awareness_coverage_family_confirm",
        "构建一个战场覆盖度与情报供给模型",
        "family_needs_confirmation",
        ["family_needs_confirmation", "low_confidence"],
        ["battlefield"],
        "battlefield_awareness",
    ),
    _object_guard_case(
        "battlefield_parent_guard",
        "构建一个战场态势感知模型",
        "battlefield_situation_needs_object",
        ["battlefield_situation", "battlefield"],
    ),
    _object_guard_case(
        "awareness_warning_guard",
        "做一个预警图景融合模型，分析态势感知水平",
        "battlefield_situation_needs_object",
        ["battlefield_situation", "radar_tracking"],
    ),
    _object_guard_case(
        "military_parent_guard",
        "构建一个军工装备建模系统，用于武器平台评估",
        "military_equipment_needs_object",
        ["military_equipment"],
    ),
    _object_guard_case(
        "military_system_guard",
        "生成一个武器平台评估系统模型",
        "military_equipment_needs_object",
        ["military_equipment"],
    ),
    _out_of_scope_case("finance_out_of_scope", "构建一个高频交易回测系统"),
    _out_of_scope_case("medical_out_of_scope", "生成一个医疗诊断预测模型"),
    _out_of_scope_case("ecommerce_out_of_scope", "构建一个电商推荐模型"),
    _out_of_scope_case("legal_out_of_scope", "生成一个合同风险评分模型"),
    _out_of_scope_case("ad_out_of_scope", "构建一个广告点击率预测模型"),
]


METRIC_THRESHOLDS = {
    "core_family_hit_rate": 0.96,
    "out_of_scope_false_generate_rate": 0.00,
    "missing_critical_clarify_first_rate": 1.00,
    "object_guard_clarify_rate": 1.00,
    "family_clarify_reject_rate": 1.00,
}


def _format_query(query: str) -> str:
    return query.encode("unicode_escape").decode("ascii")


def _normalize_str_list(values: Any) -> List[str]:
    return [str(item) for item in list(values or [])]


def _format_rate(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "n/a (0/0)"
    return f"{(numerator / denominator) * 100:.1f}% ({numerator}/{denominator})"


def _format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _display_family(family: Any) -> str:
    value = str(family or "").strip()
    return value or "<none>"


def _is_out_of_scope_case(case: Dict[str, Any]) -> bool:
    if str(case.get("reason", "")).strip() == "out_of_scope":
        return True
    return "out_of_scope" in _normalize_str_list(case.get("reject_reasons", []))


def _resolve_actual_clarify_stage(result: Dict[str, Any], generation_ir: Dict[str, Any]) -> str:
    if generation_ir:
        trace = generation_ir.get("trace", {}) if isinstance(generation_ir.get("trace", {}), dict) else {}
        stage = str(trace.get("clarify_stage", "")).strip().lower()
        if stage:
            return stage
        slot_collection = (
            generation_ir.get("slot_collection", {})
            if isinstance(generation_ir.get("slot_collection", {}), dict)
            else {}
        )
        missing_slots = _normalize_str_list(slot_collection.get("missing_slots", []))
        return "slot" if missing_slots else "ready"

    stage = str(result.get("clarify_stage", "")).strip().lower()
    if stage:
        return stage

    reject_reasons = _normalize_str_list(result.get("reject_reasons", []))
    if not reject_reasons:
        reason = str(result.get("reason", "")).strip()
        if reason and reason != "matched":
            reject_reasons = [reason]
    if not reject_reasons:
        return "ready"
    if any(reason.endswith("_needs_object") or reason == "out_of_scope" for reason in reject_reasons):
        return "object"
    return "family"


def _validate_release_configuration() -> List[str]:
    errors: List[str] = []
    case_count = len(CASES)
    minimum_cases, maximum_cases = RELEASE_GOLDEN_CASE_RANGE
    if case_count < minimum_cases or case_count > maximum_cases:
        errors.append(
            f"release profile requires {minimum_cases}-{maximum_cases} golden cases, got {case_count}"
        )

    metric_case_selectors = {
        "core_family_hit_rate": "track_core_family",
        "missing_critical_clarify_first_rate": "track_missing_critical_clarify",
        "object_guard_clarify_rate": "track_object_guard",
        "family_clarify_reject_rate": "track_family_clarify",
    }
    for label, selector in metric_case_selectors.items():
        selected_count = sum(1 for case in CASES if bool(case.get(selector, False)))
        if selected_count <= 0:
            errors.append(f"{label} has no golden cases configured")

    out_of_scope_case_count = sum(1 for case in CASES if _is_out_of_scope_case(case))
    if out_of_scope_case_count <= 0:
        errors.append("out_of_scope_false_generate_rate has no golden cases configured")

    return errors


def _print_family_confusion_matrix(records: List[Dict[str, Any]]) -> None:
    family_records = [record for record in records if str(record.get("expected_family", "")).strip()]
    print("\nFamily confusion matrix (expected x actual):")
    if not family_records:
        print("- no family-labeled cases")
        return

    matrix: Dict[str, Dict[str, int]] = defaultdict(dict)
    row_labels = sorted({str(record["expected_family"]).strip() for record in family_records})
    col_labels = sorted(
        {
            _display_family(record.get("expected_family"))
            for record in family_records
        }
        | {
            _display_family(record.get("actual_family"))
            for record in family_records
        }
    )

    for row_label in row_labels:
        matrix[row_label] = {col_label: 0 for col_label in col_labels}

    for record in family_records:
        expected_family = str(record["expected_family"]).strip()
        actual_family = _display_family(record.get("actual_family"))
        matrix[expected_family][actual_family] += 1

    row_header = "expected \\ actual"
    row_width = max(len(row_header), *(len(label) for label in row_labels))
    col_widths = {
        label: max(len(label), len(str(max(matrix[row][label] for row in row_labels))))
        for label in col_labels
    }

    header = f"{row_header:<{row_width}} | " + " | ".join(
        f"{label:<{col_widths[label]}}" for label in col_labels
    )
    separator = "-" * len(header)
    print(header)
    print(separator)
    for row_label in row_labels:
        row = f"{row_label:<{row_width}} | " + " | ".join(
            f"{matrix[row_label][col_label]:<{col_widths[col_label]}}"
            for col_label in col_labels
        )
        print(row)


def _build_metric_results(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    core_family_records = [record for record in records if record.get("track_core_family", False)]
    core_family_hits = sum(
        1
        for record in core_family_records
        if str(record.get("actual_family", "")).strip() == str(record.get("expected_family", "")).strip()
    )
    core_family_misses = [
        str(record.get("name", ""))
        for record in core_family_records
        if str(record.get("actual_family", "")).strip() != str(record.get("expected_family", "")).strip()
    ]

    out_of_scope_records = [record for record in records if record.get("expected_out_of_scope", False)]
    out_of_scope_false_generates = sum(
        1 for record in out_of_scope_records if record.get("actual_should_generate", False)
    )
    out_of_scope_false_generate_cases = [
        str(record.get("name", ""))
        for record in out_of_scope_records
        if record.get("actual_should_generate", False)
    ]

    clarify_records = [record for record in records if record.get("track_missing_critical_clarify", False)]
    clarify_hits = sum(
        1
        for record in clarify_records
        if record.get("actual_clarify_stage") == "slot"
        and record.get("actual_enters_clarify", False)
        and bool(record.get("actual_missing_critical_slots", []))
    )
    clarify_misses = [
        str(record.get("name", ""))
        for record in clarify_records
        if not (
            record.get("actual_clarify_stage") == "slot"
            and record.get("actual_enters_clarify", False)
            and bool(record.get("actual_missing_critical_slots", []))
        )
    ]

    object_guard_records = [record for record in records if record.get("track_object_guard", False)]
    object_guard_hits = sum(
        1
        for record in object_guard_records
        if not record.get("actual_should_generate", False)
        and record.get("actual_enters_clarify", False)
        and record.get("actual_clarify_stage") == "object"
    )
    object_guard_misses = [
        str(record.get("name", ""))
        for record in object_guard_records
        if not (
            not record.get("actual_should_generate", False)
            and record.get("actual_enters_clarify", False)
            and record.get("actual_clarify_stage") == "object"
        )
    ]

    family_clarify_records = [record for record in records if record.get("track_family_clarify", False)]
    family_clarify_hits = sum(
        1
        for record in family_clarify_records
        if not record.get("actual_should_generate", False)
        and record.get("actual_enters_clarify", False)
        and record.get("actual_clarify_stage") == "family"
    )
    family_clarify_misses = [
        str(record.get("name", ""))
        for record in family_clarify_records
        if not (
            not record.get("actual_should_generate", False)
            and record.get("actual_enters_clarify", False)
            and record.get("actual_clarify_stage") == "family"
        )
    ]

    return [
        {
            "key": "core_family_hit_rate",
            "label": "core family hit rate",
            "numerator": core_family_hits,
            "denominator": len(core_family_records),
            "threshold": METRIC_THRESHOLDS["core_family_hit_rate"],
            "direction": "min",
            "failed_cases": core_family_misses,
        },
        {
            "key": "out_of_scope_false_generate_rate",
            "label": "out-of-scope false generate rate",
            "numerator": out_of_scope_false_generates,
            "denominator": len(out_of_scope_records),
            "threshold": METRIC_THRESHOLDS["out_of_scope_false_generate_rate"],
            "direction": "max",
            "failed_cases": out_of_scope_false_generate_cases,
        },
        {
            "key": "missing_critical_clarify_first_rate",
            "label": "missing-critical-slot clarify-first rate",
            "numerator": clarify_hits,
            "denominator": len(clarify_records),
            "threshold": METRIC_THRESHOLDS["missing_critical_clarify_first_rate"],
            "direction": "min",
            "failed_cases": clarify_misses,
        },
        {
            "key": "object_guard_clarify_rate",
            "label": "object-guard clarify rate",
            "numerator": object_guard_hits,
            "denominator": len(object_guard_records),
            "threshold": METRIC_THRESHOLDS["object_guard_clarify_rate"],
            "direction": "min",
            "failed_cases": object_guard_misses,
        },
        {
            "key": "family_clarify_reject_rate",
            "label": "family-clarify reject rate",
            "numerator": family_clarify_hits,
            "denominator": len(family_clarify_records),
            "threshold": METRIC_THRESHOLDS["family_clarify_reject_rate"],
            "direction": "min",
            "failed_cases": family_clarify_misses,
        },
    ]


def _collect_metric_gate_failures(metric_results: List[Dict[str, Any]]) -> List[str]:
    failures: List[str] = []
    for metric in metric_results:
        numerator = int(metric["numerator"])
        denominator = int(metric["denominator"])
        threshold = float(metric["threshold"])
        direction = str(metric["direction"])
        label = str(metric["label"])
        failed_cases = [str(name) for name in metric.get("failed_cases", [])]

        if denominator <= 0:
            failures.append(
                f"{label}: no golden cases configured for this gate"
            )
            continue

        actual_rate = numerator / denominator
        passes_gate = actual_rate >= threshold if direction == "min" else actual_rate <= threshold
        if passes_gate:
            continue

        comparator = ">=" if direction == "min" else "<="
        failed_case_text = ", ".join(failed_cases) if failed_cases else "<none>"
        failures.append(
            f"{label}: got {_format_rate(numerator, denominator)}, gate {comparator} {_format_percent(threshold)}, "
            f"failed_cases={failed_case_text}"
        )
    return failures


def _print_summary(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    total_cases = len(records)
    passed_cases = sum(1 for record in records if not record.get("case_failures"))
    metric_results = _build_metric_results(records)
    minimum_cases, maximum_cases = RELEASE_GOLDEN_CASE_RANGE

    print(f"\nGolden {RELEASE_PROFILE} report:")
    print(f"- case coverage: {total_cases} (release gate: {minimum_cases}-{maximum_cases})")
    print(f"- pass rate: {_format_rate(passed_cases, total_cases)}")
    for metric in metric_results:
        comparator = ">=" if str(metric["direction"]) == "min" else "<="
        gate_status = "PASS" if not _collect_metric_gate_failures([metric]) else "FAIL"
        print(
            f"- {metric['label']}: {_format_rate(int(metric['numerator']), int(metric['denominator']))} "
            f"(gate {comparator} {_format_percent(float(metric['threshold']))}, {gate_status})"
        )
    _print_family_confusion_matrix(records)
    print(
        "\nRun policy: rerun `powershell -ExecutionPolicy Bypass -File tools\\verify_golden.ps1` "
        "after any knowledge-base, threshold, or alias change."
    )
    return metric_results


def main() -> int:
    retriever = MatlabRAGRetriever()
    structured_ir = StructuredGenerationIR(retriever)
    failures: List[str] = []
    records: List[Dict[str, Any]] = []
    metric_config_failures = _validate_release_configuration()

    for case in CASES:
        query = str(case["query"])
        docs = retriever.retrieve(query, top_k=10)
        result = retriever.assess_generation_match(query, docs)
        case_failures: List[str] = []

        actual_reason = str(result.get("reason", ""))
        expected_reason = str(case["reason"])
        actual_should_generate = bool(result.get("should_generate", False))
        expected_should_generate = bool(case.get("should_generate", False))
        actual_reject_reasons = _normalize_str_list(result.get("reject_reasons", []))
        expected_reject_reasons = _normalize_str_list(case.get("reject_reasons", []))
        actual_query_domains = _normalize_str_list(result.get("query_domains", []))
        expected_query_domains = _normalize_str_list(case.get("query_domains", []))
        actual_family = str(result.get("top_family", ""))
        expected_family = str(case.get("top_family", ""))
        top_candidate = dict(result.get("top_candidate") or {})
        top_candidate_family = str(top_candidate.get("template_family", "")).strip()

        generation_ir = {}
        actual_enters_clarify = not actual_should_generate
        if actual_should_generate:
            generation_ir = structured_ir.begin_collection(query, result)
            actual_enters_clarify = bool(generation_ir) and structured_ir.should_clarify(generation_ir)
        expected_enters_clarify = bool(case.get("enters_clarify", False))
        slot_collection = generation_ir.get("slot_collection", {}) if isinstance(generation_ir.get("slot_collection", {}), dict) else {}
        actual_missing_critical_slots = _normalize_str_list(slot_collection.get("missing_critical_slots", []))
        actual_clarify_stage = _resolve_actual_clarify_stage(result, generation_ir)

        generation_family = str(generation_ir.get("schema_family", "")).strip()
        actual_hits_launch_dynamics = any(
            family == "launch_dynamics"
            for family in [actual_family, top_candidate_family, generation_family]
            if family
        )
        forbid_launch_dynamics = bool(case.get("forbid_launch_dynamics", False))

        if actual_reason != expected_reason:
            case_failures.append(
                f"reason expected={expected_reason}, got={actual_reason}"
            )
        if actual_should_generate != expected_should_generate:
            case_failures.append(
                f"should_generate expected={expected_should_generate}, got={actual_should_generate}"
            )
        if actual_reject_reasons != expected_reject_reasons:
            case_failures.append(
                f"reject_reasons expected={expected_reject_reasons}, got={actual_reject_reasons}"
            )
        if actual_query_domains != expected_query_domains:
            case_failures.append(
                f"query_domains expected={expected_query_domains}, got={actual_query_domains}"
            )
        if expected_family and actual_family != expected_family:
            case_failures.append(
                f"top_family expected={expected_family}, got={actual_family}"
            )
        if actual_enters_clarify != expected_enters_clarify:
            case_failures.append(
                f"enters_clarify expected={expected_enters_clarify}, got={actual_enters_clarify}"
            )
        if forbid_launch_dynamics and actual_hits_launch_dynamics:
            case_failures.append(
                "unexpectedly fell into launch_dynamics"
            )

        records.append(
            {
                "name": str(case["name"]),
                "case_failures": list(case_failures),
                "expected_reason": expected_reason,
                "actual_reason": actual_reason,
                "expected_should_generate": expected_should_generate,
                "actual_should_generate": actual_should_generate,
                "expected_family": expected_family,
                "actual_family": actual_family,
                "expected_enters_clarify": expected_enters_clarify,
                "actual_enters_clarify": actual_enters_clarify,
                "actual_clarify_stage": actual_clarify_stage,
                "actual_missing_critical_slots": actual_missing_critical_slots,
                "expected_out_of_scope": _is_out_of_scope_case(case),
                "track_core_family": bool(case.get("track_core_family", False)),
                "track_missing_critical_clarify": bool(case.get("track_missing_critical_clarify", False)),
                "track_object_guard": bool(case.get("track_object_guard", False)),
                "track_family_clarify": bool(case.get("track_family_clarify", False)),
            }
        )

        if case_failures:
            failures.append(
                f"{case['name']}: {'; '.join(case_failures)}, query={_format_query(query)}"
            )
            continue

        print(
            f"PASS {case['name']}: reason={actual_reason}, generate={actual_should_generate}, "
            f"clarify={actual_enters_clarify}, stage={actual_clarify_stage}, family={actual_family or '-'}"
        )

    metric_results = _print_summary(records)
    metric_gate_failures = _collect_metric_gate_failures(metric_results)

    if metric_config_failures:
        print("\nGolden metric configuration failed:", file=sys.stderr)
        for item in metric_config_failures:
            print(f"- {item}", file=sys.stderr)

    if metric_gate_failures:
        print("\nGolden metric gate failed:", file=sys.stderr)
        for item in metric_gate_failures:
            print(f"- {item}", file=sys.stderr)

    if failures:
        print("\nGolden regression failed:", file=sys.stderr)
        for item in failures:
            print(f"- {item}", file=sys.stderr)

    if metric_config_failures or metric_gate_failures or failures:
        return 1

    print(f"\nAll {len(CASES)} golden cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
