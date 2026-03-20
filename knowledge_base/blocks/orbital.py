"""Orbital MATLAB block rules and registrations."""

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
    "orbital_dynamics": ["two_body_gravity_planar"],
    "relative_orbit": ["cw_relative_dynamics"],
    "orbit_transfer": ["impulsive_delta_v", "two_body_gravity_planar"],
}

FRAGMENT_FLAG_RULES: Dict[str, List[tuple[str, str]]] = {
    "orbital_dynamics": [("use_gravity", "two_body_gravity_planar")],
    "relative_orbit": [("use_cw", "cw_relative_dynamics")],
    "orbit_transfer": [
        ("use_impulse", "impulsive_delta_v"),
        ("use_gravity", "two_body_gravity_planar"),
    ],
}

PARAMETER_DECLARATION_RULES: Dict[str, List[tuple[str, str, str | None]]] = {
    "orbital_dynamics": [
        ("mu", "mu", None),
        ("Re", "earth_radius", None),
        ("altitude0", "altitude0", None),
        ("v0", "v0", None),
        ("dt", "dt", None),
        ("T", "stop_time", None),
    ],
    "relative_orbit": [
        ("n", "mean_motion", None),
        ("x0", "x0", None),
        ("y0", "y0", None),
        ("vx0", "vx0", None),
        ("vy0", "vy0", None),
        ("dt", "dt", None),
        ("T", "stop_time", None),
    ],
    "orbit_transfer": [
        ("mu", "mu", None),
        ("Re", "earth_radius", None),
        ("altitude0", "altitude0", None),
        ("v0", "v0", None),
        ("transfer_dv", "transfer_dv", None),
        ("transfer_burn_time", "transfer_burn_time", None),
        ("dt", "dt", None),
        ("T", "stop_time", None),
    ],
}

FAMILY_RENDER_RULES: Dict[str, List[RenderRuleToken]] = {
    "orbital_dynamics": _standard_family_rule(
        "orbital_dynamics",
        setup_blocks=["time_grid", "state_arrays", "initial_conditions"],
        post_fragment_update_blocks=["state"],
    ),
    "relative_orbit": _standard_family_rule(
        "relative_orbit",
        setup_blocks=["time_grid", "state_arrays", "initial_conditions"],
        post_fragment_update_blocks=["state"],
    ),
    "orbit_transfer": _standard_family_rule(
        "orbit_transfer",
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
    _family_block_id("setup", "orbital_dynamics", "time_grid"): _join_lines(["t = 0:dt:T;", "N = numel(t);"]),
    _family_block_id("setup", "orbital_dynamics", "state_arrays"): _join_lines(["x = zeros(N,1);", "y = zeros(N,1);", "vx = zeros(N,1);", "vy = zeros(N,1);"]),
    _family_block_id("setup", "orbital_dynamics", "initial_conditions"): _join_lines(["x(1) = Re + altitude0;", "vy(1) = v0;"]),
    _family_block_id("setup", "relative_orbit", "time_grid"): _join_lines(["t = 0:dt:T;", "N = numel(t);"]),
    _family_block_id("setup", "relative_orbit", "state_arrays"): _join_lines(["x = zeros(N,1);", "y = zeros(N,1);", "vx = zeros(N,1);", "vy = zeros(N,1);"]),
    _family_block_id("setup", "relative_orbit", "initial_conditions"): _join_lines(["x(1) = x0;", "y(1) = y0;", "vx(1) = vx0;", "vy(1) = vy0;"]),
    _family_block_id("setup", "orbit_transfer", "time_grid"): _join_lines(["t = 0:dt:T;", "N = numel(t);"]),
    _family_block_id("setup", "orbit_transfer", "state_arrays"): _join_lines(["x = zeros(N,1);", "y = zeros(N,1);", "vx = zeros(N,1);", "vy = zeros(N,1);", "specific_energy = zeros(N,1);"]),
    _family_block_id("setup", "orbit_transfer", "initial_conditions"): _join_lines(["x(1) = Re + altitude0;", "vy(1) = v0;", "specific_energy(1) = -mu / (2 * x(1));"]),
    _family_block_id("solver", "orbital_dynamics", "loop_begin"): _join_lines(["for k = 2:N", "    r = max(hypot(x(k-1), y(k-1)), 1e-9);"]),
    _family_block_id("solver", "orbital_dynamics", "loop_end"): "end",
    _family_block_id("solver", "relative_orbit", "loop_begin"): "for k = 2:N",
    _family_block_id("solver", "relative_orbit", "loop_end"): "end",
    _family_block_id("solver", "orbit_transfer", "loop_begin"): _join_lines(["for k = 2:N", "    r = max(hypot(x(k-1), y(k-1)), 1e-9);"]),
    _family_block_id("solver", "orbit_transfer", "loop_end"): "end",
    _family_block_id("fragment", "orbital_dynamics", "two_body_gravity_planar"): _join_lines([
        "    if use_gravity",
        "        ax = -mu * x(k-1) / r^3;",
        "        ay = -mu * y(k-1) / r^3;",
        "    else",
        "        ax = 0;",
        "        ay = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "relative_orbit", "cw_relative_dynamics"): _join_lines([
        "    if use_cw",
        "        ax = 3 * n^2 * x(k-1) + 2 * n * vy(k-1);",
        "        ay = -2 * n * vx(k-1);",
        "    else",
        "        ax = 0;",
        "        ay = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "orbit_transfer", "impulsive_delta_v"): _join_lines([
        "    if use_impulse && abs(t(k-1) - transfer_burn_time) <= dt / 2",
        "        impulse_dv = transfer_dv;",
        "    else",
        "        impulse_dv = 0;",
        "    end",
    ]),
    _family_block_id("fragment", "orbit_transfer", "two_body_gravity_planar"): _join_lines([
        "    if use_gravity",
        "        ax = -mu * x(k-1) / r^3;",
        "        ay = -mu * y(k-1) / r^3;",
        "    else",
        "        ax = 0;",
        "        ay = 0;",
        "    end",
    ]),
    _family_block_id("update", "orbital_dynamics", "state"): _join_lines([
        "    vx(k) = vx(k-1) + ax * dt;",
        "    vy(k) = vy(k-1) + ay * dt;",
        "    x(k) = x(k-1) + vx(k) * dt;",
        "    y(k) = y(k-1) + vy(k) * dt;",
    ]),
    _family_block_id("update", "relative_orbit", "state"): _join_lines([
        "    vx(k) = vx(k-1) + ax * dt;",
        "    vy(k) = vy(k-1) + ay * dt;",
        "    x(k) = x(k-1) + vx(k) * dt;",
        "    y(k) = y(k-1) + vy(k) * dt;",
    ]),
    _family_block_id("update", "orbit_transfer", "state"): _join_lines([
        "    vmag = max(hypot(vx(k-1), vy(k-1)), 1e-9);",
        "    dv_vec = impulse_dv * [vx(k-1); vy(k-1)] / vmag;",
        "    vx(k) = vx(k-1) + ax * dt + dv_vec(1);",
        "    vy(k) = vy(k-1) + ay * dt + dv_vec(2);",
        "    x(k) = x(k-1) + vx(k) * dt;",
        "    y(k) = y(k-1) + vy(k) * dt;",
        "    specific_energy(k) = 0.5 * (vx(k)^2 + vy(k)^2) - mu / max(hypot(x(k), y(k)), 1e-9);",
    ]),
    _family_block_id("postprocess", "orbital_dynamics", "metrics"): _join_lines([
        "radius = hypot(x, y);",
        "altitude = radius - Re;",
        "theta = linspace(0, 2*pi, 400);",
    ]),
    _family_block_id("postprocess", "relative_orbit", "metrics"): _join_lines([
        "rel_range = hypot(x, y);",
        "fprintf('Minimum relative distance: %.2f m\\n', min(rel_range));",
    ]),
    _family_block_id("postprocess", "orbit_transfer", "metrics"): _join_lines([
        "radius = hypot(x, y);",
        "altitude = radius - Re;",
        "theta = linspace(0, 2*pi, 400);",
        "fprintf('Specific orbital energy final: %.2f J/kg\\n', specific_energy(end));",
    ]),
    _family_block_id("output", "orbital_dynamics", "plots"): _join_lines([
        "figure('Name', 'Orbital Dynamics 2D');",
        "subplot(1,2,1); fill(Re*cos(theta), Re*sin(theta), [0.7 0.85 1.0], 'EdgeColor', 'none'); hold on; plot(x, y, 'r', 'LineWidth', 1.6); axis equal; grid on; xlabel('X (m)'); ylabel('Y (m)'); title('IR-Block Orbit');",
        "subplot(1,2,2); plot(t, altitude / 1e3, 'LineWidth', 1.6); grid on; xlabel('Time (s)'); ylabel('Altitude (km)'); title('Altitude Evolution');",
    ]),
    _family_block_id("output", "relative_orbit", "plots"): _join_lines([
        "figure('Name', 'Relative Orbit');",
        "subplot(1,2,1); plot(x, y, 'LineWidth', 1.8); grid on; axis equal; xlabel('Radial (m)'); ylabel('Along-track (m)'); title('CW Relative Motion');",
        "subplot(1,2,2); plot(t, hypot(x, y), 'LineWidth', 1.6); grid on; xlabel('Time (s)'); ylabel('Relative Distance (m)'); title('Relative Range');",
    ]),
    _family_block_id("output", "orbit_transfer", "plots"): _join_lines([
        "figure('Name', 'Orbit Transfer');",
        "subplot(2,2,1); fill(Re*cos(theta), Re*sin(theta), [0.7 0.85 1.0], 'EdgeColor', 'none'); hold on; plot(x, y, 'm', 'LineWidth', 1.6); axis equal; grid on; xlabel('X (m)'); ylabel('Y (m)'); title('Transfer Trajectory');",
        "subplot(2,2,2); plot(t, altitude / 1e3, 'LineWidth', 1.6); grid on; xlabel('Time (s)'); ylabel('Altitude (km)');",
        "subplot(2,2,3); plot(t, specific_energy, 'LineWidth', 1.6); grid on; xlabel('Time (s)'); ylabel('Specific Energy (J/kg)');",
        "subplot(2,2,4); plot(t, hypot(vx, vy), 'LineWidth', 1.6); grid on; xlabel('Time (s)'); ylabel('Speed (m/s)');",
    ]),
}

for block_id, text in STATIC_BLOCKS.items():
    _register_text_block(BLOCK_LIBRARY, block_id, text)
