"""Tracking MATLAB block rules and registrations."""

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
    "tracking_estimation": ["cv_state_transition", "noisy_measurement", "kalman_filter_update"],
    "sensor_fusion_tracking": ["cv_state_transition", "multi_sensor_measurement", "track_fusion_update"],
    "bearing_only_tracking": ["cv_state_transition", "bearing_measurement", "ekf_linearization"],
}

FRAGMENT_FLAG_RULES: Dict[str, List[tuple[str, str]]] = {
    "tracking_estimation": [
        ("use_cv", "cv_state_transition"),
        ("use_measurement_noise", "noisy_measurement"),
        ("use_kalman", "kalman_filter_update"),
    ],
    "sensor_fusion_tracking": [
        ("use_cv", "cv_state_transition"),
        ("use_multi_sensor", "multi_sensor_measurement"),
        ("use_fusion", "track_fusion_update"),
    ],
    "bearing_only_tracking": [
        ("use_cv", "cv_state_transition"),
        ("use_bearing", "bearing_measurement"),
        ("use_ekf", "ekf_linearization"),
    ],
}

PARAMETER_DECLARATION_RULES: Dict[str, List[tuple[str, str, str | None]]] = {
    "tracking_estimation": [
        ("dt", "dt", None),
        ("steps", "steps", "int"),
        ("process_noise", "process_noise", None),
        ("measurement_noise", "measurement_noise", None),
        ("x0", "x0", None),
        ("y0", "y0", None),
        ("vx0", "target_speed_x", None),
        ("vy0", "target_speed_y", None),
    ],
    "sensor_fusion_tracking": [
        ("dt", "dt", None),
        ("steps", "steps", "int"),
        ("process_noise", "process_noise", None),
        ("radar_noise", "radar_noise", None),
        ("eo_noise", "eo_noise", None),
        ("x0", "x0", None),
        ("y0", "y0", None),
        ("vx0", "target_speed_x", None),
        ("vy0", "target_speed_y", None),
    ],
    "bearing_only_tracking": [
        ("dt", "dt", None),
        ("steps", "steps", "int"),
        ("process_noise", "process_noise", None),
        ("bearing_noise", "bearing_noise", None),
        ("sensor_x", "sensor_x", None),
        ("sensor_y", "sensor_y", None),
        ("x0", "x0", None),
        ("y0", "y0", None),
        ("vx0", "target_speed_x", None),
        ("vy0", "target_speed_y", None),
    ],
}

FAMILY_RENDER_RULES: Dict[str, List[RenderRuleToken]] = {
    "tracking_estimation": _standard_family_rule(
        "tracking_estimation",
        include_rng=True,
        pre_setup_fragments=["cv_state_transition", "noisy_measurement"],
        setup_blocks=["arrays", "initial_conditions"],
        pre_fragment_update_blocks=["truth", "measurement"],
        post_fragment_update_blocks=[],
    ),
    "sensor_fusion_tracking": _standard_family_rule(
        "sensor_fusion_tracking",
        include_rng=True,
        pre_setup_fragments=["cv_state_transition", "multi_sensor_measurement"],
        setup_blocks=["arrays", "initial_conditions"],
        pre_fragment_update_blocks=["truth", "measurement"],
        post_fragment_update_blocks=[],
    ),
    "bearing_only_tracking": _standard_family_rule(
        "bearing_only_tracking",
        include_rng=True,
        pre_setup_fragments=["cv_state_transition", "bearing_measurement"],
        setup_blocks=["arrays", "initial_conditions"],
        pre_fragment_update_blocks=["truth", "measurement"],
        post_fragment_update_blocks=[],
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
    _family_block_id("setup", "tracking_estimation", "arrays"): _join_lines([
        "truth = zeros(4, steps);",
        "meas = zeros(2, steps);",
        "est = zeros(4, steps);",
        "P = diag([100, 100, 25, 25]);",
    ]),
    _family_block_id("setup", "tracking_estimation", "initial_conditions"): _join_lines([
        "truth(:,1) = [x0; y0; vx0; vy0];",
        "est(:,1) = truth(:,1);",
        "if use_measurement_noise",
        "    meas(:,1) = H * truth(:,1) + measurement_noise * randn(2,1);",
        "else",
        "    meas(:,1) = H * truth(:,1);",
        "end",
    ]),
    _family_block_id("setup", "sensor_fusion_tracking", "arrays"): _join_lines([
        "truth = zeros(4, steps);",
        "radar_meas = zeros(2, steps);",
        "eo_meas = zeros(2, steps);",
        "est = zeros(4, steps);",
        "P = diag([100, 100, 25, 25]);",
    ]),
    _family_block_id("setup", "sensor_fusion_tracking", "initial_conditions"): _join_lines([
        "truth(:,1) = [x0; y0; vx0; vy0];",
        "est(:,1) = truth(:,1);",
        "radar_meas(:,1) = H * truth(:,1) + radar_noise * randn(2,1);",
        "eo_meas(:,1) = H * truth(:,1) + eo_noise * randn(2,1);",
    ]),
    _family_block_id("setup", "bearing_only_tracking", "arrays"): _join_lines([
        "truth = zeros(4, steps);",
        "bearing = zeros(1, steps);",
        "est = zeros(4, steps);",
        "P = diag([200, 200, 50, 50]);",
    ]),
    _family_block_id("setup", "bearing_only_tracking", "initial_conditions"): _join_lines([
        "truth(:,1) = [x0; y0; vx0; vy0];",
        "est(:,1) = [x0 + 200; y0 - 150; vx0; vy0];",
        "bearing(1) = atan2(truth(2,1) - sensor_y, truth(1,1) - sensor_x);",
    ]),
    _family_block_id("solver", "tracking_estimation", "loop_begin"): "for k = 2:steps",
    _family_block_id("solver", "tracking_estimation", "loop_end"): "end",
    _family_block_id("solver", "sensor_fusion_tracking", "loop_begin"): "for k = 2:steps",
    _family_block_id("solver", "sensor_fusion_tracking", "loop_end"): "end",
    _family_block_id("solver", "bearing_only_tracking", "loop_begin"): "for k = 2:steps",
    _family_block_id("solver", "bearing_only_tracking", "loop_end"): "end",
    _family_block_id("fragment", "tracking_estimation", "cv_state_transition"): _join_lines([
        "if use_cv",
        "    F = [1 0 dt 0; 0 1 0 dt; 0 0 1 0; 0 0 0 1];",
        "    Q = process_noise * [dt^4/4 0 dt^3/2 0; 0 dt^4/4 0 dt^3/2; dt^3/2 0 dt^2 0; 0 dt^3/2 0 dt^2];",
        "else",
        "    F = eye(4);",
        "    Q = zeros(4);",
        "end",
    ]),
    _family_block_id("fragment", "tracking_estimation", "noisy_measurement"): _join_lines([
        "H = [1 0 0 0; 0 1 0 0];",
        "if use_measurement_noise",
        "    R = (measurement_noise^2) * eye(2);",
        "else",
        "    R = 1e-9 * eye(2);",
        "end",
    ]),
    _family_block_id("fragment", "tracking_estimation", "kalman_filter_update"): _join_lines([
        "    pred = F * est(:,k-1);",
        "    if use_kalman",
        "        Pp = F * P * F' + Q;",
        "        K = Pp * H' / (H * Pp * H' + R);",
        "        est(:,k) = pred + K * (meas(:,k) - H * pred);",
        "        P = (eye(4) - K * H) * Pp;",
        "    else",
        "        est(:,k) = pred;",
        "        P = F * P * F' + Q;",
        "    end",
    ]),
    _family_block_id("fragment", "sensor_fusion_tracking", "cv_state_transition"): _join_lines([
        "if use_cv",
        "    F = [1 0 dt 0; 0 1 0 dt; 0 0 1 0; 0 0 0 1];",
        "    Q = process_noise * [dt^4/4 0 dt^3/2 0; 0 dt^4/4 0 dt^3/2; dt^3/2 0 dt^2 0; 0 dt^3/2 0 dt^2];",
        "else",
        "    F = eye(4);",
        "    Q = zeros(4);",
        "end",
    ]),
    _family_block_id("fragment", "sensor_fusion_tracking", "multi_sensor_measurement"): _join_lines([
        "H = [1 0 0 0; 0 1 0 0];",
        "if use_multi_sensor",
        "    R_radar = (radar_noise^2) * eye(2);",
        "    R_eo = (eo_noise^2) * eye(2);",
        "else",
        "    R_radar = 1e-9 * eye(2);",
        "    R_eo = 1e-9 * eye(2);",
        "end",
    ]),
    _family_block_id("fragment", "sensor_fusion_tracking", "track_fusion_update"): _join_lines([
        "    pred = F * est(:,k-1);",
        "    Pp = F * P * F' + Q;",
        "    if use_fusion",
        "        K_r = Pp * H' / (H * Pp * H' + R_radar);",
        "        est_r = pred + K_r * (radar_meas(:,k) - H * pred);",
        "        P_r = (eye(4) - K_r * H) * Pp;",
        "        K_e = P_r * H' / (H * P_r * H' + R_eo);",
        "        est(:,k) = est_r + K_e * (eo_meas(:,k) - H * est_r);",
        "        P = (eye(4) - K_e * H) * P_r;",
        "    else",
        "        est(:,k) = pred;",
        "        P = Pp;",
        "    end",
    ]),
    _family_block_id("fragment", "bearing_only_tracking", "cv_state_transition"): _join_lines([
        "if use_cv",
        "    F = [1 0 dt 0; 0 1 0 dt; 0 0 1 0; 0 0 0 1];",
        "    Q = process_noise * [dt^4/4 0 dt^3/2 0; 0 dt^4/4 0 dt^3/2; dt^3/2 0 dt^2 0; 0 dt^3/2 0 dt^2];",
        "else",
        "    F = eye(4);",
        "    Q = zeros(4);",
        "end",
    ]),
    _family_block_id("fragment", "bearing_only_tracking", "bearing_measurement"): _join_lines([
        "if use_bearing",
        "    R = bearing_noise^2;",
        "else",
        "    R = 1e-9;",
        "end",
    ]),
    _family_block_id("fragment", "bearing_only_tracking", "ekf_linearization"): _join_lines([
        "    pred = F * est(:,k-1);",
        "    Pp = F * P * F' + Q;",
        "    dx = pred(1) - sensor_x;",
        "    dy = pred(2) - sensor_y;",
        "    q = max(dx^2 + dy^2, 1e-6);",
        "    h = atan2(dy, dx);",
        "    H_b = [-dy / q, dx / q, 0, 0];",
        "    innovation = bearing(k) - h;",
        "    if innovation > pi",
        "        innovation = innovation - 2 * pi;",
        "    elseif innovation < -pi",
        "        innovation = innovation + 2 * pi;",
        "    end",
        "    if use_ekf",
        "        K = Pp * H_b' / (H_b * Pp * H_b' + R);",
        "        est(:,k) = pred + K * innovation;",
        "        P = (eye(4) - K * H_b) * Pp;",
        "    else",
        "        est(:,k) = pred;",
        "        P = Pp;",
        "    end",
    ]),
    _family_block_id("update", "tracking_estimation", "truth"): _join_lines([
        "    if use_cv",
        "        process_w = chol(Q + 1e-9 * eye(4), 'lower') * randn(4,1);",
        "    else",
        "        process_w = zeros(4,1);",
        "    end",
        "    truth(:,k) = F * truth(:,k-1) + process_w;",
    ]),
    _family_block_id("update", "tracking_estimation", "measurement"): _join_lines([
        "    if use_measurement_noise",
        "        meas(:,k) = H * truth(:,k) + measurement_noise * randn(2,1);",
        "    else",
        "        meas(:,k) = H * truth(:,k);",
        "    end",
    ]),
    _family_block_id("update", "sensor_fusion_tracking", "truth"): _join_lines([
        "    process_w = chol(Q + 1e-9 * eye(4), 'lower') * randn(4,1);",
        "    truth(:,k) = F * truth(:,k-1) + process_w;",
    ]),
    _family_block_id("update", "sensor_fusion_tracking", "measurement"): _join_lines([
        "    radar_meas(:,k) = H * truth(:,k) + radar_noise * randn(2,1);",
        "    eo_meas(:,k) = H * truth(:,k) + eo_noise * randn(2,1);",
    ]),
    _family_block_id("update", "bearing_only_tracking", "truth"): _join_lines([
        "    process_w = chol(Q + 1e-9 * eye(4), 'lower') * randn(4,1);",
        "    truth(:,k) = F * truth(:,k-1) + process_w;",
    ]),
    _family_block_id("update", "bearing_only_tracking", "measurement"): _join_lines([
        "    if use_bearing",
        "        bearing(k) = atan2(truth(2,k) - sensor_y, truth(1,k) - sensor_x) + bearing_noise * randn;",
        "    else",
        "        bearing(k) = atan2(truth(2,k) - sensor_y, truth(1,k) - sensor_x);",
        "    end",
    ]),
    _family_block_id("postprocess", "tracking_estimation", "metrics"): _join_lines([
        "time = (0:steps-1) * dt;",
        "pos_err = hypot(est(1,:) - truth(1,:), est(2,:) - truth(2,:));",
    ]),
    _family_block_id("postprocess", "sensor_fusion_tracking", "metrics"): _join_lines([
        "time = (0:steps-1) * dt;",
        "pos_err = hypot(est(1,:) - truth(1,:), est(2,:) - truth(2,:));",
    ]),
    _family_block_id("postprocess", "bearing_only_tracking", "metrics"): _join_lines([
        "time = (0:steps-1) * dt;",
        "pos_err = hypot(est(1,:) - truth(1,:), est(2,:) - truth(2,:));",
    ]),
    _family_block_id("output", "tracking_estimation", "plots"): _join_lines([
        "figure('Name', 'Tracking Estimation 2D');",
        "subplot(1,2,1); plot(truth(1,:), truth(2,:), 'k-', 'LineWidth', 1.8); hold on; plot(meas(1,:), meas(2,:), 'r.', 'MarkerSize', 8); plot(est(1,:), est(2,:), 'b--', 'LineWidth', 1.6); grid on; axis equal; xlabel('X (m)'); ylabel('Y (m)'); title('IR-Block Tracking'); legend('True', 'Measured', 'Estimated');",
        "subplot(1,2,2); plot(time, pos_err, 'LineWidth', 1.6); grid on; xlabel('Time (s)'); ylabel('Position Error (m)'); title('Tracking Error');",
    ]),
    _family_block_id("output", "sensor_fusion_tracking", "plots"): _join_lines([
        "figure('Name', 'Sensor Fusion Tracking');",
        "subplot(1,2,1); plot(truth(1,:), truth(2,:), 'k-', 'LineWidth', 1.8); hold on; plot(radar_meas(1,:), radar_meas(2,:), 'r.'); plot(eo_meas(1,:), eo_meas(2,:), 'g.'); plot(est(1,:), est(2,:), 'b--', 'LineWidth', 1.6); grid on; axis equal; xlabel('X (m)'); ylabel('Y (m)'); title('Fusion Tracking'); legend('True', 'Radar', 'EO', 'Fused');",
        "subplot(1,2,2); plot(time, pos_err, 'LineWidth', 1.6); grid on; xlabel('Time (s)'); ylabel('Position Error (m)'); title('Fusion Error');",
    ]),
    _family_block_id("output", "bearing_only_tracking", "plots"): _join_lines([
        "figure('Name', 'Bearing-only Tracking');",
        "subplot(1,2,1); plot(truth(1,:), truth(2,:), 'k-', 'LineWidth', 1.8); hold on; plot(est(1,:), est(2,:), 'b--', 'LineWidth', 1.6); plot(sensor_x, sensor_y, 'ro', 'MarkerFaceColor', 'r'); grid on; axis equal; xlabel('X (m)'); ylabel('Y (m)'); title('Bearing-only EKF'); legend('True', 'Estimated', 'Sensor');",
        "subplot(1,2,2); yyaxis left; plot(time, pos_err, 'LineWidth', 1.6); ylabel('Position Error (m)'); yyaxis right; plot(time, bearing, '--', 'LineWidth', 1.2); ylabel('Bearing (rad)'); grid on; xlabel('Time (s)'); title('Error and Bearing');",
    ]),
}

for block_id, text in STATIC_BLOCKS.items():
    _register_text_block(BLOCK_LIBRARY, block_id, text)
