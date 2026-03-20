"""Underwater launch MATLAB block rules and registrations."""

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
    "underwater_launch": ["gravity_scalar", "buoyancy_scalar", "quadratic_drag_water", "constant_thrust"],
    "underwater_cruise": ["gravity_scalar", "buoyancy_scalar", "constant_thrust", "depth_restoring_force", "quadratic_drag_water"],
    "submarine_depth_control": ["gravity_scalar", "buoyancy_scalar", "ballast_control", "quadratic_drag_water"],
}

FRAGMENT_FLAG_RULES: Dict[str, List[tuple[str, str]]] = {
    "underwater_launch": [
        ("use_thrust", "constant_thrust"),
        ("use_drag", "quadratic_drag_water"),
        ("use_gravity", "gravity_scalar"),
        ("use_buoyancy", "buoyancy_scalar"),
    ],
    "underwater_cruise": [
        ("use_thrust", "constant_thrust"),
        ("use_drag", "quadratic_drag_water"),
        ("use_gravity", "gravity_scalar"),
        ("use_buoyancy", "buoyancy_scalar"),
        ("use_depth_guidance", "depth_restoring_force"),
    ],
    "submarine_depth_control": [
        ("use_gravity", "gravity_scalar"),
        ("use_buoyancy", "buoyancy_scalar"),
        ("use_ballast", "ballast_control"),
        ("use_drag", "quadratic_drag_water"),
    ],
}

PARAMETER_DECLARATION_RULES: Dict[str, List[tuple[str, str, str | None]]] = {
    "underwater_launch": [
        ("mass", "mass", None),
        ("thrust", "thrust", None),
        ("Cd", "drag_coeff", None),
        ("A", "area", None),
        ("rho", "water_density", None),
        ("Vd", "displaced_volume", None),
        ("g", "g", None),
        ("dt", "dt", None),
        ("T", "stop_time", None),
    ],
    "underwater_cruise": [
        ("mass", "mass", None),
        ("thrust", "thrust", None),
        ("Cd", "drag_coeff", None),
        ("A", "area", None),
        ("rho", "water_density", None),
        ("Vd", "displaced_volume", None),
        ("g", "g", None),
        ("target_depth", "target_depth", None),
        ("depth_gain", "depth_gain", None),
        ("init_depth", "init_depth", None),
        ("init_speed", "init_speed", None),
        ("dt", "dt", None),
        ("T", "stop_time", None),
    ],
    "submarine_depth_control": [
        ("mass", "mass", None),
        ("Cd", "drag_coeff", None),
        ("A", "area", None),
        ("rho", "water_density", None),
        ("Vd", "displaced_volume", None),
        ("g", "g", None),
        ("target_depth", "target_depth", None),
        ("ballast_gain", "ballast_gain", None),
        ("dt", "dt", None),
        ("T", "stop_time", None),
    ],
}

FAMILY_RENDER_RULES: Dict[str, List[RenderRuleToken]] = {
    "underwater_launch": _standard_family_rule(
        "underwater_launch",
        setup_blocks=["time_grid", "state_arrays"],
        post_setup_fragments=["gravity_scalar", "buoyancy_scalar"],
        post_fragment_update_blocks=["state"],
    ),
    "underwater_cruise": _standard_family_rule(
        "underwater_cruise",
        setup_blocks=["time_grid", "state_arrays", "initial_conditions"],
        post_setup_fragments=["gravity_scalar", "buoyancy_scalar"],
        post_fragment_update_blocks=["state"],
    ),
    "submarine_depth_control": _standard_family_rule(
        "submarine_depth_control",
        setup_blocks=["time_grid", "state_arrays", "initial_conditions"],
        post_setup_fragments=["gravity_scalar", "buoyancy_scalar"],
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
    _family_block_id("setup", "underwater_launch", "time_grid"): _join_lines(["t = 0:dt:T;", "N = numel(t);"]),
    _family_block_id("setup", "underwater_launch", "state_arrays"): _join_lines(["s = zeros(N,1);", "v = zeros(N,1);", "a = zeros(N,1);"]),
    _family_block_id("setup", "underwater_cruise", "time_grid"): _join_lines(["t = 0:dt:T;", "N = numel(t);"]),
    _family_block_id("setup", "underwater_cruise", "state_arrays"): _join_lines([
        "range_pos = zeros(N,1);",
        "depth = zeros(N,1);",
        "speed = zeros(N,1);",
        "accel = zeros(N,1);",
        "pitch_deg = zeros(N,1);",
    ]),
    _family_block_id("setup", "underwater_cruise", "initial_conditions"): _join_lines([
        "depth(1) = init_depth;",
        "speed(1) = init_speed;",
    ]),
    _family_block_id("setup", "submarine_depth_control", "time_grid"): _join_lines(["t = 0:dt:T;", "N = numel(t);"]),
    _family_block_id("setup", "submarine_depth_control", "state_arrays"): _join_lines([
        "depth = zeros(N,1);",
        "w = zeros(N,1);",
        "a = zeros(N,1);",
        "ballast_cmd_hist = zeros(N,1);",
    ]),
    _family_block_id("setup", "submarine_depth_control", "initial_conditions"): "depth(1) = target_depth * 0.35;",
    _family_block_id("solver", "underwater_launch", "loop_begin"): "for k = 2:N",
    _family_block_id("solver", "underwater_launch", "loop_end"): "end",
    _family_block_id("solver", "underwater_cruise", "loop_begin"): "for k = 2:N",
    _family_block_id("solver", "underwater_cruise", "loop_end"): "end",
    _family_block_id("solver", "submarine_depth_control", "loop_begin"): "for k = 2:N",
    _family_block_id("solver", "submarine_depth_control", "loop_end"): "end",
    _family_block_id("fragment", "underwater_launch", "gravity_scalar"): _join_lines([
        "if use_gravity",
        "    weight = mass * g;",
        "else",
        "    weight = 0;",
        "end",
    ]),
    _family_block_id("fragment", "underwater_launch", "buoyancy_scalar"): _join_lines([
        "if use_buoyancy",
        "    buoyancy = rho * g * Vd;",
        "else",
        "    buoyancy = 0;",
        "end",
    ]),
    _family_block_id("fragment", "underwater_launch", "quadratic_drag_water"): _join_lines([
        "    if use_drag",
        "        drag = 0.5 * rho * Cd * A * v(k-1) * abs(v(k-1));",
        "    else",
        "        drag = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "underwater_launch", "constant_thrust"): _join_lines([
        "    if use_thrust",
        "        current_thrust = thrust;",
        "    else",
        "        current_thrust = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "underwater_cruise", "gravity_scalar"): _join_lines([
        "if use_gravity",
        "    weight = mass * g;",
        "else",
        "    weight = 0;",
        "end",
    ]),
    _family_block_id("fragment", "underwater_cruise", "buoyancy_scalar"): _join_lines([
        "if use_buoyancy",
        "    buoyancy = rho * g * Vd;",
        "else",
        "    buoyancy = 0;",
        "end",
    ]),
    _family_block_id("fragment", "underwater_cruise", "constant_thrust"): _join_lines([
        "    if use_thrust",
        "        current_thrust = thrust;",
        "    else",
        "        current_thrust = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "underwater_cruise", "depth_restoring_force"): _join_lines([
        "    if use_depth_guidance",
        "        depth_error = target_depth - depth(k-1);",
        "        pitch_cmd = atan(depth_gain * depth_error / max(speed(k-1), 1e-6));",
        "    else",
        "        pitch_cmd = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "underwater_cruise", "quadratic_drag_water"): _join_lines([
        "    if use_drag",
        "        drag = 0.5 * rho * Cd * A * speed(k-1)^2;",
        "    else",
        "        drag = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "submarine_depth_control", "gravity_scalar"): _join_lines([
        "if use_gravity",
        "    weight = mass * g;",
        "else",
        "    weight = 0;",
        "end",
    ]),
    _family_block_id("fragment", "submarine_depth_control", "buoyancy_scalar"): _join_lines([
        "if use_buoyancy",
        "    buoyancy = rho * g * Vd;",
        "else",
        "    buoyancy = 0;",
        "end",
    ]),
    _family_block_id("fragment", "submarine_depth_control", "ballast_control"): _join_lines([
        "    if use_ballast",
        "        depth_error = target_depth - depth(k-1);",
        "        ballast_force = ballast_gain * depth_error;",
        "    else",
        "        ballast_force = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "submarine_depth_control", "quadratic_drag_water"): _join_lines([
        "    if use_drag",
        "        drag = 0.5 * rho * Cd * A * w(k-1) * abs(w(k-1));",
        "    else",
        "        drag = 0;",
        "    end",
    ]),
    _family_block_id("update", "underwater_launch", "state"): _join_lines([
        "    net_force = current_thrust + buoyancy - weight - drag;",
        "    a(k) = net_force / max(mass, 1e-9);",
        "    v(k) = v(k-1) + a(k) * dt;",
        "    s(k) = max(0, s(k-1) + v(k) * dt);",
    ]),
    _family_block_id("update", "underwater_cruise", "state"): _join_lines([
        "    net_force = current_thrust + buoyancy - weight - drag;",
        "    accel(k) = net_force / max(mass, 1e-9);",
        "    speed(k) = max(0, speed(k-1) + accel(k) * dt);",
        "    depth(k) = max(0, depth(k-1) + speed(k) * sin(pitch_cmd) * dt);",
        "    range_pos(k) = range_pos(k-1) + speed(k) * cos(pitch_cmd) * dt;",
        "    pitch_deg(k) = rad2deg(pitch_cmd);",
    ]),
    _family_block_id("update", "submarine_depth_control", "state"): _join_lines([
        "    net_vertical = buoyancy + ballast_force - weight - drag;",
        "    a(k) = net_vertical / max(mass, 1e-9);",
        "    w(k) = w(k-1) + a(k) * dt;",
        "    depth(k) = max(0, depth(k-1) + w(k) * dt);",
        "    ballast_cmd_hist(k) = ballast_force;",
    ]),
    _family_block_id("postprocess", "underwater_launch", "metrics"): _join_lines([
        "fprintf('Final displacement: %.2f m\\n', s(end));",
        "fprintf('Peak speed: %.2f m/s\\n', max(v));",
    ]),
    _family_block_id("postprocess", "underwater_cruise", "metrics"): _join_lines([
        "fprintf('Cruise range: %.2f m\\n', range_pos(end));",
        "fprintf('Final depth: %.2f m\\n', depth(end));",
    ]),
    _family_block_id("postprocess", "submarine_depth_control", "metrics"): _join_lines([
        "fprintf('Depth tracking error: %.2f m\\n', abs(depth(end) - target_depth));",
        "fprintf('Peak ballast command: %.2f N\\n', max(abs(ballast_cmd_hist)));",
    ]),
    _family_block_id("output", "underwater_launch", "plots"): _join_lines([
        "figure('Name', 'Underwater Launch 1D');",
        "subplot(3,1,1); plot(t, s, 'LineWidth', 1.6); grid on; ylabel('Displacement (m)'); title('IR-Block Underwater Launch');",
        "subplot(3,1,2); plot(t, v, 'LineWidth', 1.6); grid on; ylabel('Velocity (m/s)');",
        "subplot(3,1,3); plot(t, a, 'LineWidth', 1.6); grid on; ylabel('Acceleration (m/s^2)'); xlabel('Time (s)');",
    ]),
    _family_block_id("output", "underwater_cruise", "plots"): _join_lines([
        "figure('Name', 'Underwater Cruise');",
        "subplot(2,2,1); plot(range_pos, depth, 'LineWidth', 1.8); grid on; set(gca, 'YDir', 'reverse'); xlabel('Range (m)'); ylabel('Depth (m)'); title('Cruise Path');",
        "subplot(2,2,2); plot(t, speed, 'LineWidth', 1.6); grid on; xlabel('Time (s)'); ylabel('Speed (m/s)');",
        "subplot(2,2,3); plot(t, depth, 'LineWidth', 1.6); grid on; set(gca, 'YDir', 'reverse'); xlabel('Time (s)'); ylabel('Depth (m)');",
        "subplot(2,2,4); plot(t, pitch_deg, 'LineWidth', 1.6); grid on; xlabel('Time (s)'); ylabel('Pitch (deg)');",
    ]),
    _family_block_id("output", "submarine_depth_control", "plots"): _join_lines([
        "figure('Name', 'Submarine Depth Control');",
        "subplot(3,1,1); plot(t, depth, 'LineWidth', 1.6); hold on; yline(target_depth, '--r'); grid on; set(gca, 'YDir', 'reverse'); ylabel('Depth (m)'); title('Depth Control'); legend('Depth', 'Target');",
        "subplot(3,1,2); plot(t, w, 'LineWidth', 1.6); grid on; ylabel('Vertical Speed (m/s)');",
        "subplot(3,1,3); plot(t, ballast_cmd_hist, 'LineWidth', 1.6); grid on; ylabel('Ballast Force (N)'); xlabel('Time (s)');",
    ]),
}

for block_id, text in STATIC_BLOCKS.items():
    _register_text_block(BLOCK_LIBRARY, block_id, text)
