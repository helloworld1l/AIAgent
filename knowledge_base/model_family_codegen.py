"""Composable MATLAB code generation via model families and equation fragments."""

from __future__ import annotations

from typing import Any, Dict, List

from knowledge_base.blocks import (
    BLOCK_LIBRARY,
    DEFAULT_RENDER_RULE,
    FAMILY_RENDER_RULES,
    FRAGMENT_FLAG_RULES,
    FRAGMENT_RENDER_ORDER,
    PARAMETER_DECLARATION_RULES,
    _family_block_id,
)
from knowledge_base.matlab_generator import MatlabModelGenerator
from knowledge_base.model_planner import ModelPlanner
from knowledge_base.matlab_model_data import get_model_catalog
from knowledge_base.matlab_static_validator import MatlabStaticValidator


FRAGMENT_LIBRARY: Dict[str, Dict[str, str]] = {
    "constant_thrust": {
        "description": "constant thrust term",
        "equation": "F_thrust = T",
    },
    "mass_depletion": {
        "description": "linear mass depletion during burn",
        "equation": "m(t) = m0 - burn_rate * t",
    },
    "quadratic_drag_air": {
        "description": "quadratic aerodynamic drag",
        "equation": "F_drag = 0.5 * rho_air * Cd * A * v * abs(v)",
    },
    "quadratic_drag_water": {
        "description": "quadratic hydrodynamic drag",
        "equation": "F_drag = 0.5 * rho_water * Cd * A * v * abs(v)",
    },
    "gravity_scalar": {
        "description": "scalar gravity term",
        "equation": "F_gravity = m * g",
    },
    "buoyancy_scalar": {
        "description": "buoyancy term",
        "equation": "F_buoyancy = rho * g * V_disp",
    },
    "constant_thrust_vector": {
        "description": "constant thrust projected to body axis",
        "equation": "F_thrust = T * [cos(theta), sin(theta)]",
    },
    "quadratic_drag_planar": {
        "description": "planar quadratic drag",
        "equation": "F_drag = 0.5 * rho * Cd * A * ||v||^2 * v/||v||",
    },
    "gravity_planar": {
        "description": "planar gravity",
        "equation": "a_g = [0, -g]",
    },
    "two_body_gravity_planar": {
        "description": "planar two-body gravity",
        "equation": "a = -mu * r / ||r||^3",
    },
    "cv_state_transition": {
        "description": "constant-velocity state transition",
        "equation": "x_k = F x_{k-1} + w_k",
    },
    "noisy_measurement": {
        "description": "noisy Cartesian measurement model",
        "equation": "z_k = H x_k + v_k",
    },
    "kalman_filter_update": {
        "description": "Kalman prediction and update",
        "equation": "x^+ = x^- + K(z - Hx^-)",
    },
    "lanchester_square_law": {
        "description": "Lanchester square-law attrition",
        "equation": "dR/dt = -alpha * B, dB/dt = -beta * R",
    },
    "pitch_program": {
        "description": "time-varying pitch program",
        "equation": "gamma_cmd = gamma0 + schedule(t)",
    },
    "atmosphere_density_decay": {
        "description": "exponential atmosphere density model",
        "equation": "rho(h) = rho0 * exp(-h / H)",
    },
    "lift_to_drag_planar": {
        "description": "lift generated from drag proxy",
        "equation": "L = (L/D) * D",
    },
    "heating_rate_proxy": {
        "description": "reentry heating proxy",
        "equation": "q_dot ? sqrt(rho) * V^3",
    },
    "thrust_drag_balance": {
        "description": "thrust and drag balance for aircraft point mass",
        "equation": "m Vdot = T - D - m g sin(gamma)",
    },
    "lift_balance": {
        "description": "lift balance for flight-path evolution",
        "equation": "m V gamma_dot = L - m g cos(gamma)",
    },
    "bank_turn_rate": {
        "description": "bank-angle driven heading rate",
        "equation": "psi_dot = g tan(phi) / V",
    },
    "constant_speed_target": {
        "description": "constant-speed target motion",
        "equation": "r_t(k+1) = r_t(k) + V_t * dt",
    },
    "closing_velocity": {
        "description": "line-of-sight and closing velocity calculation",
        "equation": "V_c = V_m - dot(V_t, r_hat)",
    },
    "proportional_navigation": {
        "description": "proportional navigation guidance",
        "equation": "psi_dot = N * lambda_dot",
    },
    "depth_restoring_force": {
        "description": "depth-hold guidance law",
        "equation": "theta_cmd = atan(k_d * depth_error / V)",
    },
    "ballast_control": {
        "description": "ballast-force depth control",
        "equation": "F_ballast = k_b * depth_error",
    },
    "cw_relative_dynamics": {
        "description": "Clohessy-Wiltshire relative dynamics",
        "equation": "xddot - 2n ydot - 3n^2 x = 0, yddot + 2n xdot = 0",
    },
    "impulsive_delta_v": {
        "description": "impulsive velocity increment",
        "equation": "v^+ = v^- + Delta v",
    },
    "multi_sensor_measurement": {
        "description": "multi-sensor Cartesian measurements",
        "equation": "z_r = Hx + v_r, z_e = Hx + v_e",
    },
    "track_fusion_update": {
        "description": "sequential track-to-track fusion update",
        "equation": "x^+ = fuse(z_r, z_e)",
    },
    "bearing_measurement": {
        "description": "bearing-only measurement model",
        "equation": "theta = atan2(y - y_s, x - x_s)",
    },
    "ekf_linearization": {
        "description": "EKF linearization around predicted state",
        "equation": "K = P H^T (H P H^T + R)^-1",
    },
    "sensor_coverage_decay": {
        "description": "coverage decay in battlefield sensing",
        "equation": "coverage_dot = -lambda * coverage",
    },
    "information_fusion": {
        "description": "information-fusion increment",
        "equation": "awareness = alpha * coverage + beta * feed",
    },
    "threat_score_accumulation": {
        "description": "accumulated threat score growth",
        "equation": "threat_dot = f(proximity, intent, asset)",
    },
    "intent_weighting": {
        "description": "intent weighting factor",
        "equation": "intent_factor = w_i * intent",
    },
    "salvo_exchange": {
        "description": "salvo and interceptor exchange",
        "equation": "engaged = min(raid, interceptors)",
    },
    "intercept_leakage": {
        "description": "intercept leakage computation",
        "equation": "leakers = engaged - kills",
    },
}


FAMILY_LIBRARY: Dict[str, Dict[str, Any]] = {
    "launch_dynamics": {
        "domain": "aerospace",
        "family_tier": "trunk",
        "governing_form": "ode",
        "solver": "discrete_euler",
        "state_variables": ["h", "v", "a", "m"],
    },
    "trajectory_ode": {
        "domain": "aerospace",
        "family_tier": "trunk",
        "governing_form": "ode",
        "solver": "discrete_euler",
        "state_variables": ["x", "y", "vx", "vy", "ax", "ay"],
    },
    "powered_ascent": {
        "domain": "aerospace",
        "parent_family": "trajectory_ode",
        "family_tier": "extended",
        "governing_form": "ode",
        "solver": "discrete_euler",
        "state_variables": ["x", "y", "vx", "vy", "mass"],
    },
    "reentry_dynamics": {
        "domain": "aerospace",
        "parent_family": "trajectory_ode",
        "family_tier": "extended",
        "governing_form": "ode",
        "solver": "discrete_euler",
        "state_variables": ["x", "y", "vx", "vy", "heat_load"],
    },
    "aircraft_point_mass": {
        "domain": "aerospace",
        "family_tier": "extended",
        "governing_form": "ode",
        "solver": "discrete_euler",
        "state_variables": ["x", "y", "v", "gamma", "heading"],
    },
    "interceptor_guidance": {
        "domain": "aerospace",
        "family_tier": "extended",
        "governing_form": "difference_equation",
        "solver": "guidance_loop",
        "state_variables": ["missile_x", "missile_y", "target_x", "target_y", "miss_distance"],
    },
    "underwater_launch": {
        "domain": "underwater",
        "family_tier": "trunk",
        "governing_form": "ode",
        "solver": "discrete_euler",
        "state_variables": ["s", "v", "a"],
    },
    "underwater_cruise": {
        "domain": "underwater",
        "parent_family": "underwater_launch",
        "family_tier": "extended",
        "governing_form": "ode",
        "solver": "discrete_euler",
        "state_variables": ["range", "depth", "speed", "pitch"],
    },
    "submarine_depth_control": {
        "domain": "underwater",
        "family_tier": "extended",
        "governing_form": "ode",
        "solver": "discrete_euler",
        "state_variables": ["depth", "w", "a"],
    },
    "orbital_dynamics": {
        "domain": "orbital",
        "family_tier": "trunk",
        "governing_form": "ode",
        "solver": "discrete_euler",
        "state_variables": ["x", "y", "vx", "vy"],
    },
    "relative_orbit": {
        "domain": "orbital",
        "parent_family": "orbital_dynamics",
        "family_tier": "extended",
        "governing_form": "ode",
        "solver": "discrete_euler",
        "state_variables": ["x", "y", "vx", "vy"],
    },
    "orbit_transfer": {
        "domain": "orbital",
        "parent_family": "orbital_dynamics",
        "family_tier": "extended",
        "governing_form": "ode",
        "solver": "impulsive_burn_plus_euler",
        "state_variables": ["x", "y", "vx", "vy", "specific_energy"],
    },
    "tracking_estimation": {
        "domain": "tracking",
        "family_tier": "trunk",
        "governing_form": "difference_equation",
        "solver": "kalman_loop",
        "state_variables": ["x", "y", "vx", "vy"],
    },
    "sensor_fusion_tracking": {
        "domain": "tracking",
        "parent_family": "tracking_estimation",
        "family_tier": "extended",
        "governing_form": "difference_equation",
        "solver": "sequential_fusion_loop",
        "state_variables": ["x", "y", "vx", "vy"],
    },
    "bearing_only_tracking": {
        "domain": "tracking",
        "parent_family": "tracking_estimation",
        "family_tier": "extended",
        "governing_form": "difference_equation",
        "solver": "ekf_loop",
        "state_variables": ["x", "y", "vx", "vy"],
    },
    "combat_attrition": {
        "domain": "battlefield",
        "family_tier": "trunk",
        "governing_form": "ode",
        "solver": "discrete_euler",
        "state_variables": ["red", "blue"],
    },
    "battlefield_awareness": {
        "domain": "battlefield",
        "family_tier": "extended",
        "governing_form": "difference_equation",
        "solver": "discrete_euler",
        "state_variables": ["coverage", "feed", "awareness"],
    },
    "threat_assessment": {
        "domain": "battlefield",
        "family_tier": "extended",
        "governing_form": "difference_equation",
        "solver": "discrete_euler",
        "state_variables": ["proximity", "intent", "threat_score"],
    },
    "salvo_engagement": {
        "domain": "battlefield",
        "family_tier": "extended",
        "governing_form": "difference_equation",
        "solver": "discrete_euler",
        "state_variables": ["red_salvo", "blue_inventory", "intercepted", "leakers"],
    },
}


FAMILY_PARAMETER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "launch_dynamics": {
        "mass0": 500.0,
        "fuel_mass": 180.0,
        "burn_rate": 2.5,
        "thrust": 16000.0,
        "drag_coeff": 0.55,
        "area": 0.8,
        "air_density": 1.225,
        "g": 9.81,
        "dt": 0.05,
        "stop_time": 60.0,
    },
    "trajectory_ode": {
        "mass0": 120.0,
        "thrust": 9500.0,
        "drag_coeff": 0.32,
        "area": 0.08,
        "air_density": 1.225,
        "g": 9.81,
        "launch_angle_deg": 45.0,
        "init_speed": 160.0,
        "burn_time": 12.0,
        "dt": 0.05,
        "stop_time": 40.0,
    },
    "powered_ascent": {
        "mass0": 850.0,
        "fuel_mass": 320.0,
        "burn_rate": 4.0,
        "thrust": 35000.0,
        "drag_coeff": 0.38,
        "area": 0.65,
        "air_density": 1.225,
        "g": 9.81,
        "init_speed": 80.0,
        "init_flight_path_deg": 88.0,
        "pitch_start_deg": 88.0,
        "pitch_end_deg": 25.0,
        "pitch_ramp_time": 45.0,
        "dt": 0.05,
        "stop_time": 120.0,
    },
    "reentry_dynamics": {
        "mass0": 1200.0,
        "drag_coeff": 0.90,
        "area": 1.4,
        "air_density_ref": 1.225,
        "scale_height": 8500.0,
        "lift_to_drag": 0.25,
        "g": 9.81,
        "init_altitude": 120000.0,
        "init_speed": 7200.0,
        "entry_angle_deg": 6.0,
        "dt": 0.05,
        "stop_time": 350.0,
    },
    "aircraft_point_mass": {
        "mass": 18000.0,
        "thrust": 120000.0,
        "drag_coeff": 0.045,
        "area": 30.0,
        "wing_area": 32.0,
        "air_density": 1.225,
        "lift_coeff": 0.70,
        "g": 9.81,
        "bank_angle_deg": 18.0,
        "climb_cmd_deg": 6.0,
        "init_speed": 230.0,
        "init_altitude": 1500.0,
        "dt": 0.1,
        "stop_time": 240.0,
    },
    "interceptor_guidance": {
        "missile_speed": 550.0,
        "target_speed": 260.0,
        "target_heading_deg": 20.0,
        "nav_gain": 4.0,
        "init_range": 18000.0,
        "init_los_deg": 30.0,
        "dt": 0.05,
        "stop_time": 80.0,
    },
    "underwater_launch": {
        "mass": 180.0,
        "thrust": 3200.0,
        "drag_coeff": 0.35,
        "area": 0.045,
        "water_density": 1000.0,
        "displaced_volume": 0.16,
        "g": 9.81,
        "dt": 0.02,
        "stop_time": 25.0,
    },
    "underwater_cruise": {
        "mass": 220.0,
        "thrust": 2400.0,
        "drag_coeff": 0.28,
        "area": 0.05,
        "water_density": 1000.0,
        "displaced_volume": 0.21,
        "g": 9.81,
        "target_depth": 25.0,
        "depth_gain": 0.08,
        "init_depth": 8.0,
        "init_speed": 12.0,
        "dt": 0.05,
        "stop_time": 180.0,
    },
    "submarine_depth_control": {
        "mass": 8500.0,
        "drag_coeff": 0.85,
        "area": 7.5,
        "water_density": 1025.0,
        "displaced_volume": 8.1,
        "g": 9.81,
        "target_depth": 120.0,
        "ballast_gain": 1800.0,
        "dt": 0.1,
        "stop_time": 300.0,
    },
    "orbital_dynamics": {
        "mu": 3.986e14,
        "earth_radius": 6.371e6,
        "altitude0": 4.0e5,
        "v0": 7670.0,
        "dt": 1.0,
        "stop_time": 5400.0,
    },
    "relative_orbit": {
        "mean_motion": 0.00113,
        "x0": 120.0,
        "y0": -40.0,
        "vx0": 0.0,
        "vy0": -0.05,
        "dt": 1.0,
        "stop_time": 7200.0,
    },
    "orbit_transfer": {
        "mu": 3.986e14,
        "earth_radius": 6.371e6,
        "altitude0": 2.0e5,
        "v0": 7780.0,
        "transfer_dv": 120.0,
        "transfer_burn_time": 600.0,
        "dt": 1.0,
        "stop_time": 7200.0,
    },
    "tracking_estimation": {
        "dt": 1.0,
        "steps": 120,
        "process_noise": 1.0,
        "measurement_noise": 15.0,
        "x0": 0.0,
        "y0": 0.0,
        "target_speed_x": 120.0,
        "target_speed_y": 35.0,
    },
    "sensor_fusion_tracking": {
        "dt": 1.0,
        "steps": 120,
        "process_noise": 1.0,
        "radar_noise": 20.0,
        "eo_noise": 8.0,
        "x0": 0.0,
        "y0": 0.0,
        "target_speed_x": 150.0,
        "target_speed_y": 25.0,
    },
    "bearing_only_tracking": {
        "dt": 1.0,
        "steps": 120,
        "process_noise": 1.0,
        "bearing_noise": 0.5,
        "sensor_x": 0.0,
        "sensor_y": 0.0,
        "x0": 1200.0,
        "y0": 1800.0,
        "target_speed_x": -35.0,
        "target_speed_y": 45.0,
    },
    "combat_attrition": {
        "red0": 120.0,
        "blue0": 100.0,
        "alpha": 0.018,
        "beta": 0.015,
        "dt": 0.1,
        "stop_time": 120.0,
    },
    "battlefield_awareness": {
        "coverage0": 0.72,
        "feed0": 0.55,
        "decay_rate": 0.045,
        "fusion_gain": 0.35,
        "dt": 0.2,
        "stop_time": 120.0,
    },
    "threat_assessment": {
        "proximity0": 60.0,
        "closing_rate": 0.45,
        "intent_weight": 0.60,
        "asset_value": 0.90,
        "lethality_weight": 0.75,
        "dt": 0.2,
        "stop_time": 80.0,
    },
    "salvo_engagement": {
        "red_salvo0": 24.0,
        "blue_interceptors0": 36.0,
        "raid_size": 0.18,
        "p_kill": 0.72,
        "interceptor_regen": 0.05,
        "dt": 0.5,
        "stop_time": 60.0,
    },
}


class MatlabFamilyAssembler:
    def __init__(self):
        self.catalog = get_model_catalog()
        self.model_by_id = {str(item.get("model_id", "")).strip(): item for item in self.catalog}
        self.default_model_by_family: Dict[str, Dict[str, Any]] = {}
        for item in self.catalog:
            family = str(item.get("template_family", "")).strip()
            if family and family not in self.default_model_by_family:
                self.default_model_by_family[family] = item
        self.static_validator = MatlabStaticValidator()
        self.function_renderer = MatlabModelGenerator()
        self.planner = ModelPlanner(
            catalog=self.catalog,
            family_library=FAMILY_LIBRARY,
            fragment_library=FRAGMENT_LIBRARY,
            family_parameter_defaults=FAMILY_PARAMETER_DEFAULTS,
            default_fragments_resolver=self._default_fragments_for_family,
            default_state_equations_resolver=self._default_state_equations,
            model_id_resolver=self._compose_model_id,
        )

    def supports(self, model_id: str) -> bool:
        model = self.model_by_id.get(model_id, {})
        family = str(model.get("template_family", "")).strip()
        return self.supports_family(family)

    def supports_family(self, family: str) -> bool:
        family_name = str(family or "").strip()
        return family_name in FAMILY_RENDER_RULES

    def supports_ir(self, generation_ir: Dict[str, Any]) -> bool:
        return self.planner.supports_ir(generation_ir)

    def supports_spec(self, spec: Dict[str, Any]) -> bool:
        if not isinstance(spec, dict):
            return False
        generation_ir = spec.get("_generation_ir", {})
        if isinstance(generation_ir, dict) and generation_ir:
            return self.supports_ir(generation_ir)
        model_id = str(spec.get("model_id", "")).strip()
        if model_id:
            return self.supports(model_id)
        return self.supports_family(str(spec.get("template_family", "")))

    def render_from_spec(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(spec, dict):
            return {"status": "error", "message": "spec must be a dict"}
        generation_ir = spec.get("_generation_ir", {})
        if isinstance(generation_ir, dict) and generation_ir:
            return self.render_from_ir(generation_ir, spec=spec)
        plan_result = self.plan_from_spec(spec)
        if plan_result.get("status") == "error":
            return plan_result
        assembly = self._assembly_from_plan(plan_result.get("plan", {}))
        result = self._render_assembly(assembly)
        result.setdefault("assembly_plan", plan_result.get("plan", {}))
        result.setdefault("ir_validation", plan_result.get("ir_validation", {}))
        return result

    def render_from_ir(self, generation_ir: Dict[str, Any], spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not isinstance(generation_ir, dict) or not generation_ir:
            return {"status": "error", "message": "generation_ir is required"}
        plan_result = self.plan_from_ir(generation_ir, spec=spec)
        if plan_result.get("status") == "error":
            return plan_result
        assembly = self._assembly_from_plan(plan_result.get("plan", {}))
        result = self._render_assembly(assembly)
        result.setdefault("assembly_plan", plan_result.get("plan", {}))
        result.setdefault("ir_validation", plan_result.get("ir_validation", {}))
        return result

    def plan_from_spec(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(spec, dict):
            return {"status": "error", "message": "spec must be a dict"}
        model_id = str(spec.get("model_id", "")).strip()
        model = self.model_by_id.get(model_id, {})
        family = str(model.get("template_family", spec.get("template_family", ""))).strip()
        if not family:
            return {"status": "error", "message": "cannot infer template family from spec"}
        legacy_ir = self._spec_to_generation_ir(spec, model)
        return self.plan_from_ir(legacy_ir, spec=spec)

    def plan_from_ir(self, generation_ir: Dict[str, Any], spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not isinstance(generation_ir, dict) or not generation_ir:
            return {"status": "error", "message": "generation_ir is required"}
        return self.planner.plan_from_ir(generation_ir, spec=spec or {})

    @staticmethod
    def _assembly_from_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
        return dict(plan) if isinstance(plan, dict) else {}


    def _render_assembly(self, assembly: Dict[str, Any]) -> Dict[str, Any]:
        family = str(assembly.get("template_family", "")).strip()
        if not self.supports_family(family):
            return {"status": "error", "message": f"unsupported family: {family}"}
        assembly_validation = self.static_validator.validate_assembly(assembly)
        if not assembly_validation.get("valid", False):
            return {
                "status": "error",
                "message": "static assembly validation failed: " + "; ".join(assembly_validation.get("errors", [])),
                "assembly": assembly,
                "static_validation": {
                    "valid": False,
                    "errors": list(assembly_validation.get("errors", [])),
                    "warnings": list(assembly_validation.get("warnings", [])),
                    "assembly_validation": assembly_validation,
                },
                "error_type": "static_validation",
            }
        try:
            script = self._compose_function_from_assembly(assembly)
        except Exception as exc:
            return {"status": "error", "message": f"render assembly failed: {exc}"}
        static_validation = self.static_validator.validate_rendered_output(assembly, script)
        if not static_validation.get("valid", False):
            return {
                "status": "error",
                "message": "static script validation failed: " + "; ".join(static_validation.get("errors", [])),
                "assembly": assembly,
                "script": script,
                "static_validation": static_validation,
                "error_type": "static_validation",
            }
        return {
            "status": "success",
            "script": script,
            "assembly": assembly,
            "static_validation": static_validation,
        }

    def _build_assembly_from_spec(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        plan_result = self.plan_from_spec(spec)
        if plan_result.get("status") == "error":
            return plan_result
        return self._assembly_from_plan(plan_result.get("plan", {}))

    def _spec_to_generation_ir(self, spec: Dict[str, Any], model: Dict[str, Any]) -> Dict[str, Any]:
        model_id = str(spec.get("model_id", model.get("model_id", ""))).strip()
        family = str(model.get("template_family", spec.get("template_family", ""))).strip()
        family_meta = FAMILY_LIBRARY.get(family, {})
        params = dict(FAMILY_PARAMETER_DEFAULTS.get(family, {}))
        params.update(model.get("default_params", {}))
        params.update(spec.get("parameters", {}))
        simulation_plan = spec.get("simulation_plan", {})
        if isinstance(simulation_plan, dict):
            if "stop_time" in simulation_plan:
                params["stop_time"] = simulation_plan["stop_time"]
            if "time_step_hint" in simulation_plan and "dt" not in params:
                params["dt"] = simulation_plan["time_step_hint"]
            if "sample_count" in simulation_plan and "steps" not in params:
                params["steps"] = simulation_plan["sample_count"]
        fragments = list(model.get("equation_fragments", [])) or self._default_fragments_for_family(family)
        return {
            "ir_version": "legacy_spec_adapter",
            "status": "ready",
            "task_goal": spec.get("task_goal", ""),
            "model_id": model_id,
            "model_name": model.get("name", model_id or family),
            "schema_family": family,
            "task": {
                "goal": spec.get("task_goal", model.get("description", "") or model_id or family),
                "request_type": "model_generation",
                "language": "zh-CN",
                "confidence": 1.0,
            },
            "domain": {
                "primary": str((model.get("domain_tags", []) or [family])[0]),
                "secondary": list(model.get("domain_tags", [])[1:4]),
                "model_family": family,
                "scene": model.get("category", ""),
                "domain_tags": list(model.get("domain_tags", [])),
            },
            "entities": [
                {
                    "id": family or model_id or "system",
                    "type": "system",
                    "role": "main_model",
                    "states": list(family_meta.get("state_variables", [])),
                }
            ],
            "physics": {
                "governing_form": family_meta.get("governing_form", "ode"),
                "state_variables": list(family_meta.get("state_variables", [])),
                "equation_fragments": list(fragments),
                "state_equations": self._default_state_equations(family, fragments),
                "parameters": [{"name": key, "value": value} for key, value in params.items()],
            },
            "events": [],
            "constraints": [],
            "simulation": {
                "solver": simulation_plan.get("solver", family_meta.get("solver", "discrete_euler")) if isinstance(simulation_plan, dict) else family_meta.get("solver", "discrete_euler"),
                "stop_time": params.get("stop_time", 10),
                "time_step_hint": params.get("dt", 0.1),
                "sample_count": params.get("steps", max(50, int(params.get("stop_time", 10) / max(params.get("dt", 0.1), 1e-6)))),
            },
            "outputs": {
                "artifacts": list(spec.get("required_outputs", ["plot"])),
                "signals": [],
            },
            "codegen": {
                "strategy": "legacy_spec_adapter",
                "template_family": family,
                "equation_fragments": list(fragments),
                "target": "matlab_script",
            },
            "assumptions": list(spec.get("assumptions", [])),
            "required_outputs": list(spec.get("required_outputs", ["plot"])),
            "trace": {
                "source": "legacy_spec_adapter",
                "event": "spec_to_ir",
                "model_family": family,
                "domain_tags": list(model.get("domain_tags", [])),
                "equation_fragments": list(fragments),
                "final_generated": True,
            },
            "missing_info": [],
        }

    def _build_assembly_from_ir(self, generation_ir: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
        plan_result = self.plan_from_ir(generation_ir, spec=spec)
        if plan_result.get("status") == "error":
            return plan_result
        return self._assembly_from_plan(plan_result.get("plan", {}))

    def _resolve_family(
        self,
        generation_ir: Dict[str, Any],
        spec: Dict[str, Any],
        model_meta: Dict[str, Any],
    ) -> str:
        codegen_ir = generation_ir.get("codegen", {}) if isinstance(generation_ir, dict) else {}
        domain_ir = generation_ir.get("domain", {}) if isinstance(generation_ir, dict) else {}
        candidates = [
            codegen_ir.get("template_family"),
            domain_ir.get("model_family"),
            spec.get("template_family") if isinstance(spec, dict) else "",
            model_meta.get("template_family", ""),
        ]
        for candidate in candidates:
            family = str(candidate or "").strip()
            if family:
                return family
        return ""

    def _resolve_fragments(
        self,
        family: str,
        generation_ir: Dict[str, Any],
        model_meta: Dict[str, Any],
    ) -> List[str]:
        codegen_ir = generation_ir.get("codegen", {}) if isinstance(generation_ir, dict) else {}
        physics_ir = generation_ir.get("physics", {}) if isinstance(generation_ir, dict) else {}
        raw_fragments = (
            list(codegen_ir.get("equation_fragments", []))
            or list(physics_ir.get("equation_fragments", []))
            or list(model_meta.get("equation_fragments", []))
            or list(self.default_model_by_family.get(family, {}).get("equation_fragments", []))
            or self._default_fragments_for_family(family)
        )
        deduped: List[str] = []
        seen = set()
        for fragment in raw_fragments:
            fragment_id = str(fragment).strip()
            if fragment_id and fragment_id in FRAGMENT_LIBRARY and fragment_id not in seen:
                seen.add(fragment_id)
                deduped.append(fragment_id)
        return deduped

    def _resolve_parameters(
        self,
        family: str,
        generation_ir: Dict[str, Any],
        spec: Dict[str, Any],
        model_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        params = dict(FAMILY_PARAMETER_DEFAULTS.get(family, {}))
        params.update(self.default_model_by_family.get(family, {}).get("default_params", {}))
        params.update(model_meta.get("default_params", {}))
        if isinstance(spec, dict):
            params.update(spec.get("parameters", {}))

        physics_ir = generation_ir.get("physics", {}) if isinstance(generation_ir, dict) else {}
        physics_params = physics_ir.get("parameters", {}) if isinstance(physics_ir, dict) else {}
        if isinstance(physics_params, dict):
            params.update(physics_params)
        elif isinstance(physics_params, list):
            for item in physics_params:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                if name and item.get("value") is not None:
                    params[name] = item.get("value")

        simulation_ir = generation_ir.get("simulation", {}) if isinstance(generation_ir, dict) else {}
        if isinstance(simulation_ir, dict):
            if "stop_time" in simulation_ir:
                params["stop_time"] = simulation_ir["stop_time"]
            if "time_step_hint" in simulation_ir:
                params.setdefault("dt", simulation_ir["time_step_hint"])
            if "sample_count" in simulation_ir:
                params.setdefault("steps", simulation_ir["sample_count"])

        if "steps" in params:
            try:
                params["steps"] = int(float(params["steps"]))
            except Exception:
                pass
        return params

    def _resolve_outputs(self, outputs_ir: Dict[str, Any], generation_ir: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = []
        if isinstance(outputs_ir, dict):
            artifacts = list(outputs_ir.get("artifacts", []))
        if not artifacts:
            artifacts = list(generation_ir.get("required_outputs", ["plot"]))
        signals = list(outputs_ir.get("signals", [])) if isinstance(outputs_ir, dict) else []
        return {
            "artifacts": artifacts,
            "signals": signals,
        }


    def _build_render_blocks(self, family: str, fragments: List[str], outputs_ir: Dict[str, Any]) -> List[str]:
        del outputs_ir
        rule = FAMILY_RENDER_RULES.get(family, DEFAULT_RENDER_RULE)
        ordered_fragments = list(FRAGMENT_RENDER_ORDER.get(family, []))
        ordered_fragments.extend(fragment for fragment in fragments if fragment not in ordered_fragments)

        render_blocks: List[str] = []
        consumed_fragments: set[str] = set()
        for token in rule:
            if isinstance(token, str):
                render_blocks.append(token)
                continue
            if not isinstance(token, dict) or token.get("kind") != "fragments":
                continue

            fragment_names = list(token.get("names", []))
            if token.get("include_remaining"):
                fragment_names.extend(
                    fragment for fragment in ordered_fragments if fragment not in fragment_names
                )

            for fragment in fragment_names:
                if fragment in consumed_fragments:
                    continue
                render_blocks.append(_family_block_id("fragment", family, fragment))
                consumed_fragments.add(fragment)
        return render_blocks

    def _default_fragments_for_family(self, family: str) -> List[str]:
        defaults = {
            "launch_dynamics": ["constant_thrust", "mass_depletion", "quadratic_drag_air", "gravity_scalar"],
            "trajectory_ode": ["constant_thrust_vector", "quadratic_drag_planar", "gravity_planar"],
            "powered_ascent": ["mass_depletion", "pitch_program", "constant_thrust_vector", "quadratic_drag_planar", "gravity_planar"],
            "reentry_dynamics": ["atmosphere_density_decay", "gravity_planar", "quadratic_drag_planar", "lift_to_drag_planar", "heating_rate_proxy"],
            "aircraft_point_mass": ["thrust_drag_balance", "lift_balance", "bank_turn_rate"],
            "interceptor_guidance": ["constant_speed_target", "closing_velocity", "proportional_navigation"],
            "underwater_launch": ["constant_thrust", "quadratic_drag_water", "gravity_scalar", "buoyancy_scalar"],
            "underwater_cruise": ["gravity_scalar", "buoyancy_scalar", "constant_thrust", "depth_restoring_force", "quadratic_drag_water"],
            "submarine_depth_control": ["gravity_scalar", "buoyancy_scalar", "ballast_control", "quadratic_drag_water"],
            "orbital_dynamics": ["two_body_gravity_planar"],
            "relative_orbit": ["cw_relative_dynamics"],
            "orbit_transfer": ["impulsive_delta_v", "two_body_gravity_planar"],
            "tracking_estimation": ["cv_state_transition", "noisy_measurement", "kalman_filter_update"],
            "sensor_fusion_tracking": ["cv_state_transition", "multi_sensor_measurement", "track_fusion_update"],
            "bearing_only_tracking": ["cv_state_transition", "bearing_measurement", "ekf_linearization"],
            "combat_attrition": ["lanchester_square_law"],
            "battlefield_awareness": ["sensor_coverage_decay", "information_fusion"],
            "threat_assessment": ["intent_weighting", "threat_score_accumulation"],
            "salvo_engagement": ["salvo_exchange", "intercept_leakage"],
        }
        return list(defaults.get(family, []))


    def _default_state_equations(self, family: str, fragments: List[str]) -> List[str]:
        fragment_set = set(fragments)
        if family == "launch_dynamics":
            force_expr = self._compose_terms(
                positive=["thrust" if "constant_thrust" in fragment_set else "0"],
                negative=[
                    "drag" if "quadratic_drag_air" in fragment_set else "0",
                    "m g" if "gravity_scalar" in fragment_set else "0",
                ],
            )
            equations = ["dh/dt = v", f"m dv/dt = {force_expr}"]
            equations.append("m(t) = m0 - burn_rate * t during burn" if "mass_depletion" in fragment_set else "m(t) = m0")
            return equations
        if family == "trajectory_ode":
            force_expr = self._compose_terms(
                positive=["thrust_vector" if "constant_thrust_vector" in fragment_set else "0"],
                negative=[
                    "drag_vector" if "quadratic_drag_planar" in fragment_set else "0",
                    "gravity_vector" if "gravity_planar" in fragment_set else "0",
                ],
            )
            return ["dx/dt = vx", "dy/dt = vy", f"m dv/dt = {force_expr}"]
        if family == "powered_ascent":
            force_expr = self._compose_terms(
                positive=["thrust_vector" if "constant_thrust_vector" in fragment_set else "0"],
                negative=[
                    "drag_vector" if "quadratic_drag_planar" in fragment_set else "0",
                    "gravity_vector" if "gravity_planar" in fragment_set else "0",
                ],
            )
            equations = ["dx/dt = vx", "dy/dt = vy", f"m dv/dt = {force_expr}"]
            equations.append("gamma_cmd = schedule(t)" if "pitch_program" in fragment_set else "gamma_cmd = atan2(vy, vx)")
            equations.append("m(t) = m0 - burn_rate * t during burn" if "mass_depletion" in fragment_set else "m(t) = m0")
            return equations
        if family == "reentry_dynamics":
            force_expr = self._compose_terms(
                positive=["lift_vector" if "lift_to_drag_planar" in fragment_set else "0"],
                negative=[
                    "drag_vector" if "quadratic_drag_planar" in fragment_set else "0",
                    "gravity_vector" if "gravity_planar" in fragment_set else "0",
                ],
            )
            equations = ["dx/dt = vx", "dy/dt = vy", f"m dv/dt = {force_expr}"]
            equations.append("rho(h) = rho0 * exp(-h/H)" if "atmosphere_density_decay" in fragment_set else "rho(h) = rho0")
            equations.append("q_dot ~ sqrt(rho) * V^3" if "heating_rate_proxy" in fragment_set else "q_dot = 0")
            return equations
        if family == "aircraft_point_mass":
            return [
                "dx/dt = V cos(gamma)",
                "dy/dt = V sin(gamma)",
                "m Vdot = T - D - m g sin(gamma)",
                "m V gamma_dot = L - m g cos(gamma)",
                "psi_dot = g tan(phi) / V" if "bank_turn_rate" in fragment_set else "psi_dot = 0",
            ]
        if family == "interceptor_guidance":
            return [
                "r_t(k+1) = r_t(k) + V_t dt" if "constant_speed_target" in fragment_set else "r_t(k+1) = r_t(k)",
                "lambda_dot = d/dt atan2(y_t - y_m, x_t - x_m)" if "closing_velocity" in fragment_set else "lambda_dot = 0",
                "psi_dot = N * lambda_dot" if "proportional_navigation" in fragment_set else "psi = lambda",
            ]
        if family == "underwater_launch":
            force_expr = self._compose_terms(
                positive=[
                    "thrust" if "constant_thrust" in fragment_set else "0",
                    "buoyancy" if "buoyancy_scalar" in fragment_set else "0",
                ],
                negative=[
                    "drag" if "quadratic_drag_water" in fragment_set else "0",
                    "m g" if "gravity_scalar" in fragment_set else "0",
                ],
            )
            return ["ds/dt = v", f"m dv/dt = {force_expr}"]
        if family == "underwater_cruise":
            force_expr = self._compose_terms(
                positive=[
                    "thrust" if "constant_thrust" in fragment_set else "0",
                    "buoyancy" if "buoyancy_scalar" in fragment_set else "0",
                ],
                negative=[
                    "drag" if "quadratic_drag_water" in fragment_set else "0",
                    "m g" if "gravity_scalar" in fragment_set else "0",
                ],
            )
            equations = ["drange/dt = V cos(theta)", "ddepth/dt = V sin(theta)", f"m dV/dt = {force_expr}"]
            equations.append("theta_cmd = atan(k_d * depth_error / V)" if "depth_restoring_force" in fragment_set else "theta_cmd = 0")
            return equations
        if family == "submarine_depth_control":
            force_expr = self._compose_terms(
                positive=[
                    "buoyancy" if "buoyancy_scalar" in fragment_set else "0",
                    "ballast_force" if "ballast_control" in fragment_set else "0",
                ],
                negative=[
                    "drag" if "quadratic_drag_water" in fragment_set else "0",
                    "m g" if "gravity_scalar" in fragment_set else "0",
                ],
            )
            return ["ddepth/dt = w", f"m dw/dt = {force_expr}"]
        if family == "orbital_dynamics":
            return ["dr/dt = v", "dv/dt = -mu * r / ||r||^3"] if "two_body_gravity_planar" in fragment_set else ["dr/dt = v", "dv/dt = 0"]
        if family == "relative_orbit":
            return [
                "xddot - 2n ydot - 3n^2 x = 0" if "cw_relative_dynamics" in fragment_set else "xddot = 0",
                "yddot + 2n xdot = 0" if "cw_relative_dynamics" in fragment_set else "yddot = 0",
            ]
        if family == "orbit_transfer":
            equations = ["dr/dt = v", "dv/dt = -mu * r / ||r||^3" if "two_body_gravity_planar" in fragment_set else "dv/dt = 0"]
            equations.append("v^+ = v^- + Delta v at burn time" if "impulsive_delta_v" in fragment_set else "Delta v = 0")
            return equations
        if family == "tracking_estimation":
            return [
                "x_k = F x_{k-1} + w_k" if "cv_state_transition" in fragment_set else "x_k = x_{k-1}",
                "z_k = H x_k + v_k" if "noisy_measurement" in fragment_set else "z_k = H x_k",
                "Kalman predict-update loop" if "kalman_filter_update" in fragment_set else "direct propagation",
            ]
        if family == "sensor_fusion_tracking":
            return [
                "x_k = F x_{k-1} + w_k" if "cv_state_transition" in fragment_set else "x_k = x_{k-1}",
                "z_r = H x_k + v_r, z_e = H x_k + v_e" if "multi_sensor_measurement" in fragment_set else "z = H x_k",
                "sequential fusion update" if "track_fusion_update" in fragment_set else "direct propagation",
            ]
        if family == "bearing_only_tracking":
            return [
                "x_k = F x_{k-1} + w_k" if "cv_state_transition" in fragment_set else "x_k = x_{k-1}",
                "theta_k = atan2(y - y_s, x - x_s) + v_k" if "bearing_measurement" in fragment_set else "theta_k = atan2(y - y_s, x - x_s)",
                "EKF linearization update" if "ekf_linearization" in fragment_set else "direct propagation",
            ]
        if family == "combat_attrition":
            return ["dRed/dt = -alpha * Blue", "dBlue/dt = -beta * Red"] if "lanchester_square_law" in fragment_set else ["dRed/dt = 0", "dBlue/dt = 0"]
        if family == "battlefield_awareness":
            return [
                "coverage_dot = -lambda * coverage" if "sensor_coverage_decay" in fragment_set else "coverage_dot = 0",
                "awareness = alpha * coverage + beta * feed" if "information_fusion" in fragment_set else "awareness = coverage",
            ]
        if family == "threat_assessment":
            return [
                "intent_factor = w_i * intent" if "intent_weighting" in fragment_set else "intent_factor = intent",
                "threat_dot = f(proximity, intent, asset)" if "threat_score_accumulation" in fragment_set else "threat_dot = 0",
            ]
        if family == "salvo_engagement":
            return [
                "engaged = min(raid, interceptors)" if "salvo_exchange" in fragment_set else "engaged = 0",
                "leakers = engaged - kills" if "intercept_leakage" in fragment_set else "leakers = 0",
            ]
        return []

    def _assembly_comments(self, assembly: Dict[str, Any]) -> str:
        lines = [
            f"% family: {assembly.get('template_family', '')}",
            f"% governing_form: {assembly.get('governing_form', '')}",
            f"% solver: {assembly.get('solver', '')}",
            f"% codegen_strategy: {assembly.get('codegen_strategy', '')}",
        ]
        for block in assembly.get("render_blocks", []):
            lines.append(f"% render_block: {block}")
        for frag in assembly.get("fragment_defs", []):
            source = frag.get("source", "library")
            render_mode = frag.get("render_mode", "native")
            origin = frag.get("origin", "")
            lines.append(
                f"% fragment: {frag.get('fragment_id', '')} | {source}/{render_mode} | {origin} | {frag.get('description', '')} | {frag.get('equation', '')}"
            )
        for eq in assembly.get("state_equations", []):
            lines.append(f"% equation: {eq}")
        return "\n".join(lines)

    @staticmethod
    def _compose_model_id(family: str, fragments: List[str]) -> str:
        suffix = family or "composed_model"
        if fragments:
            suffix += "_" + "_".join(fragments[:2])
        return suffix

    @staticmethod
    def _compose_terms(positive: List[str], negative: List[str]) -> str:
        positive_terms = [term for term in positive if term and term != "0"]
        negative_terms = [term for term in negative if term and term != "0"]
        if not positive_terms and not negative_terms:
            return "0"
        expression = " + ".join(positive_terms) if positive_terms else "0"
        if negative_terms:
            expression += " - " + " - ".join(negative_terms)
        return expression

    @staticmethod
    def _has_fragment(assembly: Dict[str, Any], fragment_id: str) -> bool:
        return fragment_id in set(assembly.get("equation_fragments", []))

    @staticmethod
    def _matlab_bool(flag: bool) -> str:
        return "true" if flag else "false"

    @staticmethod
    def _matlab_identifier(name: str) -> str:
        normalized = str(name or "").strip().replace("-", "_")
        normalized = __import__("re").sub(r"[^A-Za-z0-9_]", "_", normalized)
        normalized = __import__("re").sub(r"_+", "_", normalized).strip("_")
        if not normalized:
            normalized = "composed_model"
        if not (normalized[0].isalpha() or normalized[0] == "_"):
            normalized = f"m_{normalized}"
        return normalized

    @staticmethod
    def _format_matlab_value(value: Any, cast_mode: str | None = None) -> str:
        if cast_mode == "int":
            return str(int(float(value)))
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, (list, tuple)):
            return "[" + " ".join(MatlabFamilyAssembler._format_matlab_value(item) for item in value) + "]"
        return str(value)

    def _build_interface_declarations(self, family: str, assembly: Dict[str, Any]) -> List[str]:
        params = assembly.get("parameters", {}) if isinstance(assembly.get("parameters", {}), dict) else {}
        lines: List[str] = []
        for flag_name, fragment_id in FRAGMENT_FLAG_RULES.get(family, []):
            lines.append(f"{flag_name} = {self._matlab_bool(self._has_fragment(assembly, fragment_id))};")
        for var_name, param_key, cast_mode in PARAMETER_DECLARATION_RULES.get(family, []):
            if param_key in params:
                lines.append(f"{var_name} = {self._format_matlab_value(params[param_key], cast_mode)};")
        return lines

    @staticmethod
    def _runtime_preamble() -> str:
        return "\n".join([
            "sample_time = Ts;",
            "if nargin < 3 || isempty(Ts) || Ts <= 0",
            "    sample_time = dt;",
            "end",
            "if sample_time <= 0",
            "    sample_time = 1e-3;",
            "end",
            "t = max(time, 0);",
        ])

    def _compose_function_from_assembly(self, assembly: Dict[str, Any]) -> str:
        spec = self._build_standard_function_spec(assembly)
        return self.function_renderer._render_standard_model_function(**spec)

    def _build_standard_function_spec(self, assembly: Dict[str, Any]) -> Dict[str, Any]:
        family = str(assembly.get("template_family", "")).strip()
        function_name = self._matlab_identifier(str(assembly.get("model_id", "") or family or "composed_model"))
        parameter_lines = self._build_interface_declarations(family, assembly)
        preamble = self._runtime_preamble()

        if family == "launch_dynamics":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "3",
                "output_dim_expr": "4",
                "input_dim_expr": "1",
                "default_x_expr": "[0; 0; mass0]",
                "default_u_expr": "thrust",
                "shared_logic": preamble + "\n" + "\n".join([
                    "dry_mass = max(mass0 - fuel_mass, 1e-9);",
                    "h = max(x(1), 0);",
                    "v = x(2);",
                    "m = min(max(x(3), dry_mass), mass0);",
                    "thrust_cmd = thrust;",
                    "if numel(u) >= 1",
                    "    thrust_cmd = max(u(1), 0);",
                    "end",
                    "if ~use_thrust",
                    "    thrust_cmd = 0;",
                    "end",
                    "if use_mass_depletion && m > dry_mass && thrust_cmd > 0",
                    "    mass_dot = -burn_rate;",
                    "else",
                    "    mass_dot = 0;",
                    "    if m <= dry_mass",
                    "        thrust_cmd = 0;",
                    "    end",
                    "end",
                    "drag = 0;",
                    "if use_drag",
                    "    drag = 0.5 * rho * Cd * A * v * abs(v);",
                    "end",
                    "weight = 0;",
                    "if use_gravity",
                    "    weight = m * g;",
                    "end",
                    "a = (thrust_cmd - drag - weight) / max(m, 1e-9);",
                ]),
                "y_logic": "\n".join(["y(1) = h;", "y(2) = v;", "y(3) = a;", "y(4) = m;"]),
                "f_logic": "\n".join(["f(1) = v;", "f(2) = a;", "f(3) = mass_dot;"]),
            }

        if family == "trajectory_ode":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "4",
                "output_dim_expr": "6",
                "input_dim_expr": "2",
                "default_x_expr": "[0; 0; init_speed * cos(launch_angle_deg * pi / 180); init_speed * sin(launch_angle_deg * pi / 180)]",
                "default_u_expr": "[thrust; launch_angle_deg]",
                "shared_logic": preamble + "\n" + "\n".join([
                    "theta = launch_angle_deg * pi / 180;",
                    "if numel(u) >= 2",
                    "    theta = u(2) * pi / 180;",
                    "end",
                    "x_pos = x(1);",
                    "y_pos = max(x(2), 0);",
                    "vx = x(3);",
                    "vy = x(4);",
                    "speed = max(hypot(vx, vy), 1e-9);",
                    "current_thrust = 0;",
                    "if use_thrust && t <= burn_time",
                    "    current_thrust = thrust;",
                    "    if numel(u) >= 1",
                    "        current_thrust = max(u(1), 0);",
                    "    end",
                    "end",
                    "thrust_x = current_thrust * cos(theta);",
                    "thrust_y = current_thrust * sin(theta);",
                    "drag_x = 0;",
                    "drag_y = 0;",
                    "if use_drag && speed > 1e-8",
                    "    drag_mag = 0.5 * rho * Cd * A * speed^2;",
                    "    drag_x = drag_mag * vx / speed;",
                    "    drag_y = drag_mag * vy / speed;",
                    "end",
                    "gravity_y = 0;",
                    "if use_gravity",
                    "    gravity_y = g;",
                    "end",
                    "ax = (thrust_x - drag_x) / max(mass0, 1e-9);",
                    "ay = (thrust_y - drag_y) / max(mass0, 1e-9) - gravity_y;",
                ]),
                "y_logic": "\n".join(["y(1) = x_pos;", "y(2) = y_pos;", "y(3) = vx;", "y(4) = vy;", "y(5) = ax;", "y(6) = ay;"]),
                "f_logic": "\n".join(["f(1) = vx;", "f(2) = vy;", "f(3) = ax;", "f(4) = ay;"]),
            }

        if family == "powered_ascent":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "5",
                "output_dim_expr": "6",
                "input_dim_expr": "2",
                "default_x_expr": "[0; 0; init_speed * cos(init_flight_path_deg * pi / 180); init_speed * sin(init_flight_path_deg * pi / 180); mass0]",
                "default_u_expr": "[1; 0]",
                "shared_logic": preamble + "\n" + "\n".join([
                    "dry_mass = max(mass0 - fuel_mass, 1e-9);",
                    "x_pos = x(1);",
                    "y_pos = max(x(2), 0);",
                    "vx = x(3);",
                    "vy = x(4);",
                    "mass = min(max(x(5), dry_mass), mass0);",
                    "speed = max(hypot(vx, vy), 1e-8);",
                    "if use_pitch_program",
                    "    pitch_ratio = min(max(t / max(pitch_ramp_time, dt), 0), 1);",
                    "    gamma_cmd = (pitch_start_deg + (pitch_end_deg - pitch_start_deg) * pitch_ratio) * pi / 180;",
                    "else",
                    "    gamma_cmd = atan2(vy, max(vx, 1e-9));",
                    "end",
                    "if numel(u) >= 2",
                    "    gamma_cmd = gamma_cmd + u(2) * pi / 180;",
                    "end",
                    "thrust_scale = 1;",
                    "if numel(u) >= 1",
                    "    thrust_scale = max(u(1), 0);",
                    "end",
                    "if use_thrust && mass > dry_mass",
                    "    thrust_vec = thrust * thrust_scale * [cos(gamma_cmd); sin(gamma_cmd)];",
                    "else",
                    "    thrust_vec = [0; 0];",
                    "end",
                    "if use_mass_depletion && mass > dry_mass && use_thrust && thrust_scale > 0",
                    "    mass_dot = -burn_rate;",
                    "else",
                    "    mass_dot = 0;",
                    "end",
                    "drag_vec = [0; 0];",
                    "if use_drag",
                    "    drag_mag = 0.5 * rho * Cd * A * speed^2;",
                    "    drag_vec = drag_mag * [vx; vy] / speed;",
                    "end",
                    "gravity_vec = [0; 0];",
                    "if use_gravity",
                    "    gravity_vec = [0; -mass * g];",
                    "end",
                    "net_force = thrust_vec - drag_vec + gravity_vec;",
                    "ax = net_force(1) / max(mass, 1e-9);",
                    "ay = net_force(2) / max(mass, 1e-9);",
                    "flight_path_deg = atan2(vy, max(vx, 1e-9)) * 180 / pi;",
                ]),
                "y_logic": "\n".join(["y(1) = x_pos;", "y(2) = y_pos;", "y(3) = vx;", "y(4) = vy;", "y(5) = mass;", "y(6) = flight_path_deg;"]),
                "f_logic": "\n".join(["f(1) = vx;", "f(2) = vy;", "f(3) = ax;", "f(4) = ay;", "f(5) = mass_dot;"]),
            }

        if family == "reentry_dynamics":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "5",
                "output_dim_expr": "5",
                "input_dim_expr": "1",
                "default_x_expr": "[0; init_altitude; init_speed * cos(-abs(entry_angle_deg) * pi / 180); init_speed * sin(-abs(entry_angle_deg) * pi / 180); 0]",
                "default_u_expr": "1",
                "shared_logic": preamble + "\n" + "\n".join([
                    "x_pos = x(1);",
                    "y_pos = max(x(2), 0);",
                    "vx = x(3);",
                    "vy = x(4);",
                    "heat_load = max(x(5), 0);",
                    "speed = max(hypot(vx, vy), 1e-8);",
                    "if use_atmosphere",
                    "    rho_local = air_density_ref * exp(-y_pos / max(scale_height, 1e-9));",
                    "else",
                    "    rho_local = air_density_ref;",
                    "end",
                    "drag_mag = 0;",
                    "drag_vec = [0; 0];",
                    "if use_drag",
                    "    drag_mag = 0.5 * rho_local * Cd * A * speed^2;",
                    "    drag_vec = drag_mag * [vx; vy] / speed;",
                    "end",
                    "lift_scale = 1;",
                    "if numel(u) >= 1",
                    "    lift_scale = max(u(1), 0);",
                    "end",
                    "lift_vec = [0; 0];",
                    "if use_lift && speed > 1e-8",
                    "    lift_mag = drag_mag * lift_to_drag * lift_scale;",
                    "    lift_dir = [-vy; vx] / speed;",
                    "    lift_vec = lift_mag * lift_dir;",
                    "end",
                    "gravity_vec = [0; 0];",
                    "if use_gravity",
                    "    gravity_vec = [0; -mass0 * g];",
                    "end",
                    "if use_heating",
                    "    q_dot = 1.83e-4 * sqrt(max(rho_local, 1e-9)) * speed^3;",
                    "else",
                    "    q_dot = 0;",
                    "end",
                    "net_force = lift_vec - drag_vec + gravity_vec;",
                    "ax = net_force(1) / max(mass0, 1e-9);",
                    "ay = net_force(2) / max(mass0, 1e-9);",
                ]),
                "y_logic": "\n".join(["y(1) = x_pos;", "y(2) = y_pos;", "y(3) = vx;", "y(4) = vy;", "y(5) = heat_load;"]),
                "f_logic": "\n".join(["f(1) = vx;", "f(2) = vy;", "f(3) = ax;", "f(4) = ay;", "f(5) = q_dot;"]),
            }

        if family == "aircraft_point_mass":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "5",
                "output_dim_expr": "5",
                "input_dim_expr": "3",
                "default_x_expr": "[0; init_altitude; init_speed; climb_cmd_deg * pi / 180; 0]",
                "default_u_expr": "[thrust; climb_cmd_deg; bank_angle_deg]",
                "shared_logic": preamble + "\n" + "\n".join([
                    "x_pos = x(1);",
                    "y_pos = max(x(2), 0);",
                    "v = max(x(3), 1e-3);",
                    "gamma = x(4);",
                    "heading = x(5);",
                    "rho_local = air_density * exp(-y_pos / 8500);",
                    "drag = 0.5 * rho_local * Cd * A * v^2;",
                    "current_thrust = thrust;",
                    "if numel(u) >= 1",
                    "    current_thrust = max(u(1), 0);",
                    "end",
                    "if ~use_force_balance",
                    "    current_thrust = drag;",
                    "end",
                    "if use_lift",
                    "    lift = 0.5 * rho_local * lift_coeff * wing_area * v^2;",
                    "else",
                    "    lift = mass * g * cos(gamma);",
                    "end",
                    "bank_angle = bank_angle_deg * pi / 180;",
                    "if numel(u) >= 3",
                    "    bank_angle = u(3) * pi / 180;",
                    "end",
                    "heading_rate = 0;",
                    "if use_bank",
                    "    heading_rate = g * tan(bank_angle) / max(v, 1e-6);",
                    "end",
                    "v_dot = (current_thrust - drag) / max(mass, 1e-9) - g * sin(gamma);",
                    "gamma_dot = lift / (max(mass, 1e-9) * max(v, 1e-6)) - g * cos(gamma) / max(v, 1e-6);",
                ]),
                "y_logic": "\n".join(["y(1) = x_pos;", "y(2) = y_pos;", "y(3) = v;", "y(4) = gamma * 180 / pi;", "y(5) = heading * 180 / pi;"]),
                "f_logic": "\n".join(["f(1) = v * cos(gamma) * cos(heading);", "f(2) = v * sin(gamma);", "f(3) = v_dot;", "f(4) = gamma_dot;", "f(5) = heading_rate;"]),
            }

        if family == "interceptor_guidance":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "5",
                "output_dim_expr": "6",
                "input_dim_expr": "2",
                "default_x_expr": "[0; 0; init_range * cos(init_los_deg * pi / 180); init_range * sin(init_los_deg * pi / 180); init_los_deg * pi / 180]",
                "default_u_expr": "[target_speed; target_heading_deg]",
                "shared_logic": preamble + "\n" + "\n".join([
                    "missile_x = x(1);",
                    "missile_y = x(2);",
                    "target_x = x(3);",
                    "target_y = x(4);",
                    "missile_heading = x(5);",
                    "target_speed_cmd = target_speed;",
                    "if numel(u) >= 1",
                    "    target_speed_cmd = max(u(1), 0);",
                    "end",
                    "target_heading = target_heading_deg * pi / 180;",
                    "if numel(u) >= 2",
                    "    target_heading = u(2) * pi / 180;",
                    "end",
                    "if use_target_motion",
                    "    target_vel = target_speed_cmd * [cos(target_heading); sin(target_heading)];",
                    "else",
                    "    target_vel = [0; 0];",
                    "end",
                    "rel_x = target_x - missile_x;",
                    "rel_y = target_y - missile_y;",
                    "range_now = max(hypot(rel_x, rel_y), 1e-6);",
                    "los = atan2(rel_y, rel_x);",
                    "missile_vel = missile_speed * [cos(missile_heading); sin(missile_heading)];",
                    "rel_vel = target_vel - missile_vel;",
                    "los_rate = 0;",
                    "if use_closing_velocity",
                    "    los_rate = (rel_x * rel_vel(2) - rel_y * rel_vel(1)) / max(range_now^2, 1e-6);",
                    "end",
                    "if use_guidance",
                    "    missile_heading_rate = nav_gain * los_rate;",
                    "else",
                    "    missile_heading_rate = (los - missile_heading) / max(sample_time, 1e-6);",
                    "end",
                    "miss_distance = range_now;",
                ]),
                "y_logic": "\n".join(["y(1) = missile_x;", "y(2) = missile_y;", "y(3) = target_x;", "y(4) = target_y;", "y(5) = missile_heading * 180 / pi;", "y(6) = miss_distance;"]),
                "f_logic": "\n".join(["f(1) = missile_speed * cos(missile_heading);", "f(2) = missile_speed * sin(missile_heading);", "f(3) = target_vel(1);", "f(4) = target_vel(2);", "f(5) = missile_heading_rate;"]),
            }

        if family == "underwater_launch":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "2",
                "output_dim_expr": "3",
                "input_dim_expr": "1",
                "default_x_expr": "[0; 0]",
                "default_u_expr": "thrust",
                "shared_logic": preamble + "\n" + "\n".join([
                    "s = max(x(1), 0);",
                    "v = x(2);",
                    "current_thrust = thrust;",
                    "if numel(u) >= 1",
                    "    current_thrust = max(u(1), 0);",
                    "end",
                    "if ~use_thrust",
                    "    current_thrust = 0;",
                    "end",
                    "weight = 0;",
                    "if use_gravity",
                    "    weight = mass * g;",
                    "end",
                    "buoyancy = 0;",
                    "if use_buoyancy",
                    "    buoyancy = rho * g * Vd;",
                    "end",
                    "drag = 0;",
                    "if use_drag",
                    "    drag = 0.5 * rho * Cd * A * v * abs(v);",
                    "end",
                    "a = (current_thrust + buoyancy - weight - drag) / max(mass, 1e-9);",
                ]),
                "y_logic": "\n".join(["y(1) = s;", "y(2) = v;", "y(3) = a;"]),
                "f_logic": "\n".join(["f(1) = v;", "f(2) = a;"]),
            }

        if family == "underwater_cruise":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "4",
                "output_dim_expr": "5",
                "input_dim_expr": "2",
                "default_x_expr": "[0; init_depth; init_speed; 0]",
                "default_u_expr": "[thrust; target_depth]",
                "shared_logic": preamble + "\n" + "\n".join([
                    "range_pos = x(1);",
                    "depth = max(x(2), 0);",
                    "speed = max(x(3), 0);",
                    "pitch = x(4);",
                    "current_thrust = thrust;",
                    "if numel(u) >= 1",
                    "    current_thrust = max(u(1), 0);",
                    "end",
                    "if ~use_thrust",
                    "    current_thrust = 0;",
                    "end",
                    "depth_cmd = target_depth;",
                    "if numel(u) >= 2",
                    "    depth_cmd = u(2);",
                    "end",
                    "if use_depth_guidance",
                    "    depth_error = depth_cmd - depth;",
                    "    pitch_cmd = atan(depth_gain * depth_error / max(speed, 1e-6));",
                    "else",
                    "    pitch_cmd = pitch;",
                    "end",
                    "weight = 0;",
                    "if use_gravity",
                    "    weight = mass * g;",
                    "end",
                    "buoyancy = 0;",
                    "if use_buoyancy",
                    "    buoyancy = rho * g * Vd;",
                    "end",
                    "drag = 0;",
                    "if use_drag",
                    "    drag = 0.5 * rho * Cd * A * speed^2;",
                    "end",
                    "accel = (current_thrust + buoyancy - weight - drag) / max(mass, 1e-9);",
                ]),
                "y_logic": "\n".join(["y(1) = range_pos;", "y(2) = depth;", "y(3) = speed;", "y(4) = pitch_cmd * 180 / pi;", "y(5) = accel;"]),
                "f_logic": "\n".join(["f(1) = speed * cos(pitch_cmd);", "f(2) = speed * sin(pitch_cmd);", "f(3) = accel;", "f(4) = (pitch_cmd - pitch) / max(sample_time, 1e-6);"]),
            }

        if family == "submarine_depth_control":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "2",
                "output_dim_expr": "4",
                "input_dim_expr": "1",
                "default_x_expr": "[target_depth * 0.35; 0]",
                "default_u_expr": "target_depth",
                "shared_logic": preamble + "\n" + "\n".join([
                    "depth = max(x(1), 0);",
                    "w = x(2);",
                    "depth_cmd = target_depth;",
                    "if numel(u) >= 1",
                    "    depth_cmd = u(1);",
                    "end",
                    "weight = 0;",
                    "if use_gravity",
                    "    weight = mass * g;",
                    "end",
                    "buoyancy = 0;",
                    "if use_buoyancy",
                    "    buoyancy = rho * g * Vd;",
                    "end",
                    "if use_ballast",
                    "    depth_error = depth_cmd - depth;",
                    "    ballast_force = ballast_gain * depth_error;",
                    "else",
                    "    ballast_force = 0;",
                    "end",
                    "drag = 0;",
                    "if use_drag",
                    "    drag = 0.5 * rho * Cd * A * w * abs(w);",
                    "end",
                    "a = (buoyancy + ballast_force - weight - drag) / max(mass, 1e-9);",
                ]),
                "y_logic": "\n".join(["y(1) = depth;", "y(2) = w;", "y(3) = a;", "y(4) = ballast_force;"]),
                "f_logic": "\n".join(["f(1) = w;", "f(2) = a;"]),
            }

        if family == "orbital_dynamics":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "4",
                "output_dim_expr": "4",
                "input_dim_expr": "2",
                "default_x_expr": "[Re + altitude0; 0; 0; v0]",
                "default_u_expr": "[0; 0]",
                "shared_logic": preamble + "\n" + "\n".join([
                    "x_pos = x(1);",
                    "y_pos = x(2);",
                    "vx = x(3);",
                    "vy = x(4);",
                    "r = max(hypot(x_pos, y_pos), 1e-9);",
                    "ax = 0;",
                    "ay = 0;",
                    "if use_gravity",
                    "    ax = -mu * x_pos / r^3;",
                    "    ay = -mu * y_pos / r^3;",
                    "end",
                    "if numel(u) >= 2",
                    "    ax = ax + u(1);",
                    "    ay = ay + u(2);",
                    "end",
                ]),
                "y_logic": "\n".join(["y(1) = x_pos;", "y(2) = y_pos;", "y(3) = vx;", "y(4) = vy;"]),
                "f_logic": "\n".join(["f(1) = vx;", "f(2) = vy;", "f(3) = ax;", "f(4) = ay;"]),
            }

        if family == "relative_orbit":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "4",
                "output_dim_expr": "4",
                "input_dim_expr": "2",
                "default_x_expr": "[x0; y0; vx0; vy0]",
                "default_u_expr": "[0; 0]",
                "shared_logic": preamble + "\n" + "\n".join([
                    "x_pos = x(1);",
                    "y_pos = x(2);",
                    "vx = x(3);",
                    "vy = x(4);",
                    "ax = 0;",
                    "ay = 0;",
                    "if use_cw",
                    "    ax = 3 * n^2 * x_pos + 2 * n * vy;",
                    "    ay = -2 * n * vx;",
                    "end",
                    "if numel(u) >= 2",
                    "    ax = ax + u(1);",
                    "    ay = ay + u(2);",
                    "end",
                ]),
                "y_logic": "\n".join(["y(1) = x_pos;", "y(2) = y_pos;", "y(3) = vx;", "y(4) = vy;"]),
                "f_logic": "\n".join(["f(1) = vx;", "f(2) = vy;", "f(3) = ax;", "f(4) = ay;"]),
            }

        if family == "orbit_transfer":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "4",
                "output_dim_expr": "5",
                "input_dim_expr": "1",
                "default_x_expr": "[Re + altitude0; 0; 0; v0]",
                "default_u_expr": "0",
                "shared_logic": preamble + "\n" + "\n".join([
                    "x_pos = x(1);",
                    "y_pos = x(2);",
                    "vx = x(3);",
                    "vy = x(4);",
                    "r = max(hypot(x_pos, y_pos), 1e-9);",
                    "ax = 0;",
                    "ay = 0;",
                    "if use_gravity",
                    "    ax = -mu * x_pos / r^3;",
                    "    ay = -mu * y_pos / r^3;",
                    "end",
                    "impulse_dv = 0;",
                    "if numel(u) >= 1",
                    "    impulse_dv = u(1);",
                    "elseif use_impulse && abs(t - transfer_burn_time) <= sample_time / 2",
                    "    impulse_dv = transfer_dv;",
                    "end",
                    "vmag = max(hypot(vx, vy), 1e-9);",
                    "dv_vec = impulse_dv * [vx; vy] / vmag;",
                    "specific_energy = 0.5 * (vx^2 + vy^2) - mu / r;",
                ]),
                "y_logic": "\n".join(["y(1) = x_pos;", "y(2) = y_pos;", "y(3) = vx;", "y(4) = vy;", "y(5) = specific_energy;"]),
                "f_logic": "\n".join(["f(1) = vx;", "f(2) = vy;", "f(3) = ax + dv_vec(1) / max(sample_time, 1e-6);", "f(4) = ay + dv_vec(2) / max(sample_time, 1e-6);"]),
            }

        if family == "tracking_estimation":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "4",
                "output_dim_expr": "4",
                "input_dim_expr": "2",
                "default_x_expr": "[x0; y0; vx0; vy0]",
                "default_u_expr": "[x0; y0]",
                "shared_logic": preamble + "\n" + "\n".join([
                    "if use_cv",
                    "    F = [1 0 sample_time 0; 0 1 0 sample_time; 0 0 1 0; 0 0 0 1];",
                    "else",
                    "    F = eye(4);",
                    "end",
                    "H = [1 0 0 0; 0 1 0 0];",
                    "pred = F * x;",
                    "z = H * pred;",
                    "if numel(u) >= 2",
                    "    z = u(1:2);",
                    "end",
                    "if use_kalman",
                    "    measurement_var = max(measurement_noise^2, 1e-6);",
                    "    process_var = max(process_noise, 1e-6);",
                    "    gain_pos = process_var / (process_var + measurement_var);",
                    "    gain_vel = min(1, gain_pos / max(sample_time, 1e-6));",
                    "    K = [gain_pos 0; 0 gain_pos; gain_vel 0; 0 gain_vel];",
                    "    next_state = pred + K * (z - H * pred);",
                    "else",
                    "    next_state = pred;",
                    "end",
                ]),
                "y_logic": "y(1:4) = next_state;",
                "f_logic": "f = (next_state - x) / max(sample_time, 1e-6);",
            }

        if family == "sensor_fusion_tracking":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "4",
                "output_dim_expr": "4",
                "input_dim_expr": "4",
                "default_x_expr": "[x0; y0; vx0; vy0]",
                "default_u_expr": "[x0; y0; x0; y0]",
                "shared_logic": preamble + "\n" + "\n".join([
                    "if use_cv",
                    "    F = [1 0 sample_time 0; 0 1 0 sample_time; 0 0 1 0; 0 0 0 1];",
                    "else",
                    "    F = eye(4);",
                    "end",
                    "H = [1 0 0 0; 0 1 0 0];",
                    "pred = F * x;",
                    "z_r = H * pred;",
                    "z_e = H * pred;",
                    "if numel(u) >= 4",
                    "    z_r = u(1:2);",
                    "    z_e = u(3:4);",
                    "end",
                    "if use_fusion",
                    "    radar_var = max(radar_noise^2, 1e-6);",
                    "    eo_var = max(eo_noise^2, 1e-6);",
                    "    process_var = max(process_noise, 1e-6);",
                    "    gain_r = process_var / (process_var + radar_var);",
                    "    gain_e = process_var / (process_var + eo_var);",
                    "    K_r = [gain_r 0; 0 gain_r; min(1, gain_r / max(sample_time, 1e-6)) 0; 0 min(1, gain_r / max(sample_time, 1e-6))];",
                    "    est_r = pred + K_r * (z_r - H * pred);",
                    "    K_e = [gain_e 0; 0 gain_e; min(1, gain_e / max(sample_time, 1e-6)) 0; 0 min(1, gain_e / max(sample_time, 1e-6))];",
                    "    next_state = est_r + K_e * (z_e - H * est_r);",
                    "else",
                    "    next_state = pred;",
                    "end",
                ]),
                "y_logic": "y(1:4) = next_state;",
                "f_logic": "f = (next_state - x) / max(sample_time, 1e-6);",
            }

        if family == "bearing_only_tracking":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "4",
                "output_dim_expr": "5",
                "input_dim_expr": "1",
                "default_x_expr": "[x0 + 200; y0 - 150; vx0; vy0]",
                "default_u_expr": "atan2(y0 - sensor_y, x0 - sensor_x)",
                "shared_logic": preamble + "\n" + "\n".join([
                    "if use_cv",
                    "    F = [1 0 sample_time 0; 0 1 0 sample_time; 0 0 1 0; 0 0 0 1];",
                    "else",
                    "    F = eye(4);",
                    "end",
                    "pred = F * x;",
                    "dx_b = pred(1) - sensor_x;",
                    "dy_b = pred(2) - sensor_y;",
                    "q = max(dx_b^2 + dy_b^2, 1e-6);",
                    "expected_bearing = atan2(dy_b, dx_b);",
                    "z_b = expected_bearing;",
                    "if numel(u) >= 1",
                    "    z_b = u(1);",
                    "end",
                    "innovation = z_b - expected_bearing;",
                    "if innovation > pi",
                    "    innovation = innovation - 2 * pi;",
                    "elseif innovation < -pi",
                    "    innovation = innovation + 2 * pi;",
                    "end",
                    "H_b = [-dy_b / q; dx_b / q; 0; 0];",
                    "if use_ekf",
                    "    gain_scale = max(process_noise, 1e-6) / (max(process_noise, 1e-6) + max(bearing_noise^2, 1e-6));",
                    "    next_state = pred + gain_scale * H_b * innovation;",
                    "else",
                    "    next_state = pred;",
                    "end",
                ]),
                "y_logic": "\n".join(["y(1:4) = next_state;", "y(5) = expected_bearing;"]),
                "f_logic": "f = (next_state - x) / max(sample_time, 1e-6);",
            }

        if family == "combat_attrition":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "2",
                "output_dim_expr": "2",
                "input_dim_expr": "2",
                "default_x_expr": "[red0; blue0]",
                "default_u_expr": "[0; 0]",
                "shared_logic": preamble + "\n" + "\n".join([
                    "red = max(x(1), 0);",
                    "blue = max(x(2), 0);",
                    "red_reinforce = 0;",
                    "blue_reinforce = 0;",
                    "if numel(u) >= 2",
                    "    red_reinforce = u(1);",
                    "    blue_reinforce = u(2);",
                    "end",
                    "if use_attrition",
                    "    d_red = -alpha * blue + red_reinforce;",
                    "    d_blue = -beta * red + blue_reinforce;",
                    "else",
                    "    d_red = red_reinforce;",
                    "    d_blue = blue_reinforce;",
                    "end",
                ]),
                "y_logic": "\n".join(["y(1) = red;", "y(2) = blue;"]),
                "f_logic": "\n".join(["f(1) = d_red;", "f(2) = d_blue;"]),
            }

        if family == "battlefield_awareness":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "3",
                "output_dim_expr": "3",
                "input_dim_expr": "1",
                "default_x_expr": "[coverage0; feed0; 0.65 * coverage0 + 0.35 * feed0]",
                "default_u_expr": "feed0",
                "shared_logic": preamble + "\n" + "\n".join([
                    "coverage = max(0, min(1, x(1)));",
                    "feed = max(0, min(1, x(2)));",
                    "awareness = max(0, min(1, x(3)));",
                    "feed_cmd = feed;",
                    "if use_information_fusion",
                    "    feed_cmd = feed0 + 0.20 * sin(0.15 * t);",
                    "end",
                    "if numel(u) >= 1",
                    "    feed_cmd = u(1);",
                    "end",
                    "feed_cmd = max(0, min(1, feed_cmd));",
                    "if use_coverage_decay",
                    "    coverage_loss = decay_rate * coverage;",
                    "else",
                    "    coverage_loss = 0;",
                    "end",
                    "if use_information_fusion",
                    "    fusion_input = fusion_gain * feed_cmd;",
                    "else",
                    "    fusion_input = 0;",
                    "end",
                    "next_coverage = max(0, min(1, coverage + (fusion_input - coverage_loss) * sample_time));",
                    "next_feed = feed_cmd;",
                    "next_awareness = max(0, min(1, 0.65 * next_coverage + 0.35 * next_feed));",
                    "next_state = [next_coverage; next_feed; next_awareness];",
                ]),
                "y_logic": "y(1:3) = next_state;",
                "f_logic": "f = (next_state - x) / max(sample_time, 1e-6);",
            }

        if family == "threat_assessment":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "3",
                "output_dim_expr": "3",
                "input_dim_expr": "2",
                "default_x_expr": "[proximity0; 0.5; 0]",
                "default_u_expr": "[0.5; asset_value]",
                "shared_logic": preamble + "\n" + "\n".join([
                    "proximity = max(1, x(1));",
                    "intent = x(2);",
                    "threat_score = x(3);",
                    "if use_intent_weighting",
                    "    intent_factor = 0.5 + 0.5 * sin(0.2 * t);",
                    "else",
                    "    intent_factor = 0.5;",
                    "end",
                    "if numel(u) >= 1",
                    "    intent_factor = u(1);",
                    "end",
                    "asset_term = asset_value;",
                    "if numel(u) >= 2",
                    "    asset_term = u(2);",
                    "end",
                    "if use_threat_accumulation",
                    "    proximity_term = lethality_weight / max(proximity, 1.0);",
                    "    score_increment = proximity_term + intent_weight * intent_factor + 0.4 * asset_term;",
                    "else",
                    "    score_increment = 0;",
                    "end",
                    "next_proximity = max(1, proximity - closing_rate * sample_time);",
                    "next_intent = intent_factor;",
                    "next_threat_score = min(10, threat_score + score_increment * sample_time);",
                    "next_state = [next_proximity; next_intent; next_threat_score];",
                ]),
                "y_logic": "y(1:3) = next_state;",
                "f_logic": "f = (next_state - x) / max(sample_time, 1e-6);",
            }

        if family == "salvo_engagement":
            return {
                "function_name": function_name,
                "parameter_lines": parameter_lines,
                "state_dim_expr": "4",
                "output_dim_expr": "4",
                "input_dim_expr": "2",
                "default_x_expr": "[red_salvo0; blue_interceptors0; 0; 0]",
                "default_u_expr": "[raid_size; interceptor_regen]",
                "shared_logic": preamble + "\n" + "\n".join([
                    "red_salvo = max(x(1), 0);",
                    "blue_inventory = max(x(2), 0);",
                    "intercepted = max(x(3), 0);",
                    "leakers = max(x(4), 0);",
                    "raid_inflow = raid_size;",
                    "if numel(u) >= 1",
                    "    raid_inflow = max(u(1), 0);",
                    "end",
                    "regen = interceptor_regen;",
                    "if numel(u) >= 2",
                    "    regen = u(2);",
                    "end",
                    "if use_salvo_exchange",
                    "    engaged = min(red_salvo, blue_inventory);",
                    "    intercept_step = engaged * p_kill * sample_time;",
                    "else",
                    "    engaged = 0;",
                    "    intercept_step = 0;",
                    "end",
                    "if use_intercept_leakage",
                    "    leak_step = max(0, engaged * sample_time - intercept_step);",
                    "else",
                    "    leak_step = 0;",
                    "end",
                    "next_red_salvo = max(0, red_salvo - engaged * sample_time + raid_inflow * sample_time);",
                    "next_blue_inventory = max(0, blue_inventory - engaged * sample_time + regen * sample_time);",
                    "next_intercepted = intercepted + intercept_step;",
                    "next_leakers = leakers + leak_step + max(0, raid_inflow * sample_time - engaged * sample_time);",
                    "next_state = [next_red_salvo; next_blue_inventory; next_intercepted; next_leakers];",
                ]),
                "y_logic": "y(1:4) = next_state;",
                "f_logic": "f = (next_state - x) / max(sample_time, 1e-6);",
            }

        raise ValueError(f"unsupported family interface renderer: {family}")

    @staticmethod
    def _drag_scalar_expr(rho: str, cd: str, area: str, velocity: str) -> str:
        return f"0.5 * {rho} * {cd} * {area} * {velocity} * abs({velocity})"

    @staticmethod
    def _buoyancy_expr(rho: str, gravity: str, displaced_volume: str) -> str:
        return f"{rho} * {gravity} * {displaced_volume}"



    def _compose_script_from_blocks(self, assembly: Dict[str, Any]) -> str:
        parts: List[str] = []
        for block_id in assembly.get("render_blocks", []):
            chunk = self._render_block(block_id, assembly)
            if chunk and chunk.strip():
                parts.append(chunk.rstrip())
        return "\n\n".join(parts)

    def _render_block(self, block_id: str, assembly: Dict[str, Any]) -> str:
        renderer = BLOCK_LIBRARY.get(block_id)
        if renderer is None:
            raise KeyError(f"unregistered render block: {block_id}")
        return renderer(self, assembly)

