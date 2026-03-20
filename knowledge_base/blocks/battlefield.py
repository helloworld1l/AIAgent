"""Battlefield-situation MATLAB block rules and registrations."""

from __future__ import annotations

from typing import Dict, List

from .common import (
    BlockRenderer,
    RenderRuleToken,
    _family_block_id,
    _join_lines,
    _make_fragment_flag_renderer,
    _make_parameter_renderer,
    _register_block,
    _register_text_block,
    _standard_family_rule,
)

BLOCK_LIBRARY: Dict[str, BlockRenderer] = {}

FRAGMENT_RENDER_ORDER: Dict[str, List[str]] = {
    "combat_attrition": ["lanchester_square_law"],
    "battlefield_awareness": ["sensor_coverage_decay", "information_fusion"],
    "threat_assessment": ["intent_weighting", "threat_score_accumulation"],
    "salvo_engagement": ["salvo_exchange", "intercept_leakage"],
}

FRAGMENT_FLAG_RULES: Dict[str, List[tuple[str, str]]] = {
    "combat_attrition": [("use_attrition", "lanchester_square_law")],
    "battlefield_awareness": [
        ("use_coverage_decay", "sensor_coverage_decay"),
        ("use_information_fusion", "information_fusion"),
    ],
    "threat_assessment": [
        ("use_intent_weighting", "intent_weighting"),
        ("use_threat_accumulation", "threat_score_accumulation"),
    ],
    "salvo_engagement": [
        ("use_salvo_exchange", "salvo_exchange"),
        ("use_intercept_leakage", "intercept_leakage"),
    ],
}

PARAMETER_DECLARATION_RULES: Dict[str, List[tuple[str, str, str | None]]] = {
    "combat_attrition": [
        ("red0", "red0", None),
        ("blue0", "blue0", None),
        ("alpha", "alpha", None),
        ("beta", "beta", None),
        ("dt", "dt", None),
        ("T", "stop_time", None),
    ],
    "battlefield_awareness": [
        ("coverage0", "coverage0", None),
        ("feed0", "feed0", None),
        ("decay_rate", "decay_rate", None),
        ("fusion_gain", "fusion_gain", None),
        ("dt", "dt", None),
        ("T", "stop_time", None),
    ],
    "threat_assessment": [
        ("proximity0", "proximity0", None),
        ("closing_rate", "closing_rate", None),
        ("intent_weight", "intent_weight", None),
        ("asset_value", "asset_value", None),
        ("lethality_weight", "lethality_weight", None),
        ("dt", "dt", None),
        ("T", "stop_time", None),
    ],
    "salvo_engagement": [
        ("red_salvo0", "red_salvo0", None),
        ("blue_interceptors0", "blue_interceptors0", None),
        ("raid_size", "raid_size", None),
        ("p_kill", "p_kill", None),
        ("interceptor_regen", "interceptor_regen", None),
        ("dt", "dt", None),
        ("T", "stop_time", None),
    ],
}

FAMILY_RENDER_RULES: Dict[str, List[RenderRuleToken]] = {
    "combat_attrition": _standard_family_rule(
        "combat_attrition",
        setup_blocks=["time_grid", "state_arrays"],
        post_fragment_update_blocks=["state"],
        include_postprocess=False,
    ),
    "battlefield_awareness": _standard_family_rule(
        "battlefield_awareness",
        setup_blocks=["time_grid", "state_arrays", "initial_conditions"],
        post_fragment_update_blocks=["state"],
    ),
    "threat_assessment": _standard_family_rule(
        "threat_assessment",
        setup_blocks=["time_grid", "state_arrays", "initial_conditions"],
        post_fragment_update_blocks=["state"],
    ),
    "salvo_engagement": _standard_family_rule(
        "salvo_engagement",
        setup_blocks=["time_grid", "state_arrays", "initial_conditions"],
        post_fragment_update_blocks=["state"],
    ),
}

for family_name, flag_rules in FRAGMENT_FLAG_RULES.items():
    _register_block(
        BLOCK_LIBRARY,
        _family_block_id("setup", family_name, "fragment_flags"),
        _make_fragment_flag_renderer(family_name, flag_rules),
    )

for family_name, declaration_rules in PARAMETER_DECLARATION_RULES.items():
    _register_block(
        BLOCK_LIBRARY,
        _family_block_id("declare", family_name, "parameters"),
        _make_parameter_renderer(declaration_rules),
    )

STATIC_BLOCKS = {
    _family_block_id("setup", "combat_attrition", "time_grid"): _join_lines(["t = 0:dt:T;", "N = numel(t);"]),
    _family_block_id("setup", "combat_attrition", "state_arrays"): _join_lines(["red = zeros(N,1);", "blue = zeros(N,1);", "red(1) = red0;", "blue(1) = blue0;"]),
    _family_block_id("setup", "battlefield_awareness", "time_grid"): _join_lines(["t = 0:dt:T;", "N = numel(t);"]),
    _family_block_id("setup", "battlefield_awareness", "state_arrays"): _join_lines(["coverage = zeros(N,1);", "feed = zeros(N,1);", "awareness = zeros(N,1);"]),
    _family_block_id("setup", "battlefield_awareness", "initial_conditions"): _join_lines(["coverage(1) = coverage0;", "feed(1) = feed0;", "awareness(1) = 0.65 * coverage0 + 0.35 * feed0;"]),
    _family_block_id("setup", "threat_assessment", "time_grid"): _join_lines(["t = 0:dt:T;", "N = numel(t);"]),
    _family_block_id("setup", "threat_assessment", "state_arrays"): _join_lines(["proximity = zeros(N,1);", "intent = zeros(N,1);", "threat_score = zeros(N,1);"]),
    _family_block_id("setup", "threat_assessment", "initial_conditions"): _join_lines(["proximity(1) = proximity0;", "intent(1) = 0.5;", "threat_score(1) = 0.0;"]),
    _family_block_id("setup", "salvo_engagement", "time_grid"): _join_lines(["t = 0:dt:T;", "N = numel(t);"]),
    _family_block_id("setup", "salvo_engagement", "state_arrays"): _join_lines(["red_salvo = zeros(N,1);", "blue_inventory = zeros(N,1);", "intercepted = zeros(N,1);", "leakers = zeros(N,1);"]),
    _family_block_id("setup", "salvo_engagement", "initial_conditions"): _join_lines(["red_salvo(1) = red_salvo0;", "blue_inventory(1) = blue_interceptors0;"]),
    _family_block_id("solver", "combat_attrition", "loop_begin"): "for k = 2:N",
    _family_block_id("solver", "combat_attrition", "loop_end"): "end",
    _family_block_id("solver", "battlefield_awareness", "loop_begin"): "for k = 2:N",
    _family_block_id("solver", "battlefield_awareness", "loop_end"): "end",
    _family_block_id("solver", "threat_assessment", "loop_begin"): "for k = 2:N",
    _family_block_id("solver", "threat_assessment", "loop_end"): "end",
    _family_block_id("solver", "salvo_engagement", "loop_begin"): "for k = 2:N",
    _family_block_id("solver", "salvo_engagement", "loop_end"): "end",
    _family_block_id("fragment", "combat_attrition", "lanchester_square_law"): _join_lines([
        "    if use_attrition",
        "        d_red = -alpha * blue(k-1);",
        "        d_blue = -beta * red(k-1);",
        "    else",
        "        d_red = 0;",
        "        d_blue = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "battlefield_awareness", "sensor_coverage_decay"): _join_lines([
        "    if use_coverage_decay",
        "        coverage_loss = decay_rate * coverage(k-1);",
        "    else",
        "        coverage_loss = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "battlefield_awareness", "information_fusion"): _join_lines([
        "    if use_information_fusion",
        "        feed(k) = feed0 + 0.20 * sin(0.15 * t(k-1));",
        "        fusion_input = fusion_gain * feed(k);",
        "    else",
        "        feed(k) = feed(k-1);",
        "        fusion_input = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "threat_assessment", "intent_weighting"): _join_lines([
        "    if use_intent_weighting",
        "        intent_factor = 0.5 + 0.5 * sin(0.2 * t(k-1));",
        "    else",
        "        intent_factor = 0.5;",
        "    end",
    ]),
    _family_block_id("fragment", "threat_assessment", "threat_score_accumulation"): _join_lines([
        "    if use_threat_accumulation",
        "        proximity_term = lethality_weight / max(proximity(k-1), 1.0);",
        "        score_increment = proximity_term + intent_weight * intent_factor + 0.4 * asset_value;",
        "    else",
        "        score_increment = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "salvo_engagement", "salvo_exchange"): _join_lines([
        "    if use_salvo_exchange",
        "        engaged = min(red_salvo(k-1), blue_inventory(k-1));",
        "        intercept_step = engaged * p_kill * dt;",
        "    else",
        "        engaged = 0;",
        "        intercept_step = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "salvo_engagement", "intercept_leakage"): _join_lines([
        "    if use_intercept_leakage",
        "        leak_step = max(0, engaged * dt - intercept_step);",
        "    else",
        "        leak_step = 0;",
        "    end",
    ]),
    _family_block_id("update", "combat_attrition", "state"): _join_lines([
        "    red(k) = max(0, red(k-1) + d_red * dt);",
        "    blue(k) = max(0, blue(k-1) + d_blue * dt);",
        "    if red(k) <= 0 || blue(k) <= 0",
        "        red(k+1:end) = red(k); blue(k+1:end) = blue(k);",
        "        break;",
        "    end",
    ]),
    _family_block_id("update", "battlefield_awareness", "state"): _join_lines([
        "    coverage(k) = max(0, min(1, coverage(k-1) + (fusion_input - coverage_loss) * dt));",
        "    if feed(k) == 0",
        "        feed(k) = feed(k-1);",
        "    end",
        "    awareness(k) = min(1, 0.65 * coverage(k) + 0.35 * feed(k));",
    ]),
    _family_block_id("update", "threat_assessment", "state"): _join_lines([
        "    proximity(k) = max(1, proximity(k-1) - closing_rate * dt);",
        "    intent(k) = intent_factor;",
        "    threat_score(k) = min(10, threat_score(k-1) + score_increment * dt);",
    ]),
    _family_block_id("update", "salvo_engagement", "state"): _join_lines([
        "    red_salvo(k) = max(0, red_salvo(k-1) - engaged * dt);",
        "    blue_inventory(k) = max(0, blue_inventory(k-1) - engaged * dt + interceptor_regen * dt);",
        "    intercepted(k) = intercepted(k-1) + intercept_step;",
        "    leakers(k) = leakers(k-1) + leak_step + max(0, raid_size * dt - engaged * dt);",
    ]),
    _family_block_id("postprocess", "battlefield_awareness", "metrics"): _join_lines([
        "fprintf('Final awareness score: %.3f\\n', awareness(end));",
        "fprintf('Coverage floor: %.3f\\n', min(coverage));",
    ]),
    _family_block_id("postprocess", "threat_assessment", "metrics"): _join_lines([
        "fprintf('Threat score peak: %.3f\\n', max(threat_score));",
        "fprintf('Final proximity proxy: %.3f\\n', proximity(end));",
    ]),
    _family_block_id("postprocess", "salvo_engagement", "metrics"): _join_lines([
        "fprintf('Total intercepted: %.2f\\n', intercepted(end));",
        "fprintf('Total leakers: %.2f\\n', leakers(end));",
    ]),
    _family_block_id("output", "combat_attrition", "plots"): _join_lines([
        "figure('Name', 'Combat Attrition');",
        "subplot(1,2,1); plot(t, red, 'r', 'LineWidth', 1.8); hold on; plot(t, blue, 'b', 'LineWidth', 1.8); grid on; xlabel('Time'); ylabel('Force Level'); title('IR-Block Attrition'); legend('Red', 'Blue');",
        "subplot(1,2,2); plot(red, blue, 'k', 'LineWidth', 1.8); grid on; xlabel('Red Force'); ylabel('Blue Force'); title('Phase Portrait');",
    ]),
    _family_block_id("output", "battlefield_awareness", "plots"): _join_lines([
        "figure('Name', 'Battlefield Awareness');",
        "subplot(3,1,1); plot(t, coverage, 'LineWidth', 1.6); grid on; ylabel('Coverage'); title('Awareness Build-up');",
        "subplot(3,1,2); plot(t, feed, 'LineWidth', 1.6); grid on; ylabel('External Feed');",
        "subplot(3,1,3); plot(t, awareness, 'LineWidth', 1.6); grid on; ylabel('Awareness'); xlabel('Time (s)');",
    ]),
    _family_block_id("output", "threat_assessment", "plots"): _join_lines([
        "figure('Name', 'Threat Assessment');",
        "subplot(3,1,1); plot(t, proximity, 'LineWidth', 1.6); grid on; ylabel('Proximity Proxy'); title('Threat Build-up');",
        "subplot(3,1,2); plot(t, intent, 'LineWidth', 1.6); grid on; ylabel('Intent');",
        "subplot(3,1,3); plot(t, threat_score, 'LineWidth', 1.6); grid on; ylabel('Threat Score'); xlabel('Time (s)');",
    ]),
    _family_block_id("output", "salvo_engagement", "plots"): _join_lines([
        "figure('Name', 'Salvo Engagement');",
        "subplot(2,2,1); plot(t, red_salvo, 'r', 'LineWidth', 1.6); hold on; plot(t, blue_inventory, 'b', 'LineWidth', 1.6); grid on; xlabel('Time (s)'); ylabel('Inventory'); legend('Raid', 'Interceptors');",
        "subplot(2,2,2); plot(t, intercepted, 'LineWidth', 1.6); grid on; xlabel('Time (s)'); ylabel('Intercepted');",
        "subplot(2,2,3); plot(t, leakers, 'LineWidth', 1.6); grid on; xlabel('Time (s)'); ylabel('Leakers');",
        "subplot(2,2,4); plot(intercepted, leakers, 'k', 'LineWidth', 1.6); grid on; xlabel('Intercepted'); ylabel('Leakers'); title('Outcome Tradeoff');",
    ]),
}

for block_id, text in STATIC_BLOCKS.items():
    _register_text_block(BLOCK_LIBRARY, block_id, text)
