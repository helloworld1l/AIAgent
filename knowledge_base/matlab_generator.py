"""
MATLAB .m file generation engine driven by local knowledge entries.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from knowledge_base.matlab_model_data import get_model_catalog
from knowledge_base.matlab_smoke_tester import MatlabSyntaxSmokeTester
from knowledge_base.matlab_static_validator import MatlabStaticValidator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEF_CPP_PATH = PROJECT_ROOT / "def.cpp"
_CPP_ENUM_CACHE: Dict[str, Tuple[int, Dict[str, int]]] = {}


def load_cpp_enum_values(path: str | Path | None = None) -> Dict[str, int]:
    enum_path = Path(path) if path is not None else DEFAULT_DEF_CPP_PATH
    if not enum_path.exists() or not enum_path.is_file():
        return {}

    cache_key = str(enum_path.resolve())
    try:
        modified_at = int(enum_path.stat().st_mtime_ns)
    except OSError:
        modified_at = -1

    cached = _CPP_ENUM_CACHE.get(cache_key)
    if cached and cached[0] == modified_at:
        return dict(cached[1])

    values = _parse_cpp_enum_values(_read_text_file(enum_path))
    _CPP_ENUM_CACHE[cache_key] = (modified_at, dict(values))
    return values


def _read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _parse_cpp_enum_values(text: str) -> Dict[str, int]:
    if not text:
        return {}

    sanitized = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    values: Dict[str, int] = {}

    for match in re.finditer(r"enum(?:\s+class)?\s+\w+\s*\{(?P<body>.*?)\}\s*;", sanitized, flags=re.DOTALL):
        body = re.sub(r"//.*", "", match.group("body"))
        current_value = -1
        for raw_item in body.split(","):
            item = raw_item.strip()
            if not item:
                continue

            name, has_assignment, expr = item.partition("=")
            enum_name = name.strip()
            if not re.fullmatch(r"[A-Za-z_]\w*", enum_name):
                continue

            if has_assignment:
                parsed_value = _parse_cpp_int_value(expr.strip())
                if parsed_value is None:
                    continue
                current_value = parsed_value
            else:
                current_value += 1

            values[enum_name] = current_value

    return values


def _parse_cpp_int_value(expr: str) -> Optional[int]:
    normalized = re.sub(r"\b([0-9A-Fa-fxX]+)[uUlL]+\b", r"\1", expr.strip())
    if not re.fullmatch(r"[-+]?(?:0[xX][0-9A-Fa-f]+|\d+)", normalized):
        return None
    try:
        return int(normalized, 0)
    except Exception:
        return None


class MatlabModelGenerator:
    def __init__(self):
        self.catalog = get_model_catalog()
        self.static_validator = MatlabStaticValidator()
        self.smoke_tester = MatlabSyntaxSmokeTester()
        self.templates: Dict[str, Callable[[Dict[str, Any]], str]] = {
            "transfer_function_step": self._tpl_transfer_function_step,
            "state_space_response": self._tpl_state_space_response,
            "pid_simulink_loop": self._tpl_pid_simulink_loop,
            "mass_spring_damper_ode": self._tpl_mass_spring_damper_ode,
            "kalman_tracking": self._tpl_kalman_tracking,
            "arx_identification": self._tpl_arx_identification,
            "mpc_control": self._tpl_mpc_control,
            "fft_lowpass_filter": self._tpl_fft_lowpass_filter,
            "battery_rc_model": self._tpl_battery_rc_model,
            "pv_iv_curve": self._tpl_pv_iv_curve,
            "robot_2dof_kinematics": self._tpl_robot_2dof_kinematics,
            "rocket_launch_1d": self._tpl_rocket_launch_1d,
            "missile_flight_2d": self._tpl_missile_flight_2d,
            "satellite_orbit_2body": self._tpl_satellite_orbit_2body,
            "torpedo_underwater_launch_1d": self._tpl_torpedo_underwater_launch_1d,
            "radar_target_tracking_2d": self._tpl_radar_target_tracking_2d,
            "lanchester_battle_attrition": self._tpl_lanchester_battle_attrition,
        }

    def retrieve_knowledge(self, description: str, top_k: int = 5) -> List[Dict[str, Any]]:
        scored: List[Tuple[int, Dict[str, Any]]] = []
        text = description.lower()
        for item in self.catalog:
            score = 0
            for keyword in item.get("keywords", []):
                if keyword.lower() in text:
                    score += 3
            for example in item.get("examples", []):
                overlap = _token_overlap(text, example.lower())
                score += overlap
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored:
            scored = [(0, self.catalog[0])]

        result = []
        for score, item in scored[:top_k]:
            result.append(
                {
                    "score": score,
                    "model_id": item["model_id"],
                    "name": item["name"],
                    "category": item["category"],
                    "template_family": item.get("template_family", ""),
                    "domain_tags": item.get("domain_tags", []),
                    "description": item["description"],
                    "keywords": item.get("keywords", []),
                }
            )
        return result

    def generate_m_file(
        self,
        description: str,
        output_dir: str = "generated_models",
        file_name: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        match = self._pick_model(description, model_id)
        if match is None:
            return {"status": "error", "message": "No model template matched."}

        chosen = match
        params = self._infer_params(description, chosen)
        code = self.render_script(chosen["model_id"], params)
        static_validation = self.static_validator.validate_script(code)
        if not static_validation.get("valid", False):
            return {
                "status": "error",
                "message": "static validation failed: " + "; ".join(static_validation.get("errors", [])),
                "model_id": chosen["model_id"],
                "model_name": chosen["name"],
                "category": chosen["category"],
                "script": code,
                "params": params,
                "static_validation": static_validation,
                "knowledge_matches": self.retrieve_knowledge(description, top_k=3),
            }
        safe_name, file_path = self.save_script(
            code=code,
            model_id=chosen["model_id"],
            output_dir=output_dir,
            file_name=file_name,
        )
        smoke_validation = self.smoke_tester.validate_file(file_path)
        if smoke_validation.get("status") == "failed":
            smoke_errors = smoke_validation.get("errors", [])
            smoke_message = "; ".join(smoke_errors) if smoke_errors else smoke_validation.get(
                "message", "MATLAB/Octave syntax smoke failed"
            )
            return {
                "status": "error",
                "message": "smoke validation failed: " + smoke_message,
                "model_id": chosen["model_id"],
                "model_name": chosen["name"],
                "category": chosen["category"],
                "file_name": safe_name,
                "file_path": file_path,
                "script": code,
                "params": params,
                "static_validation": static_validation,
                "smoke_validation": smoke_validation,
                "knowledge_matches": self.retrieve_knowledge(description, top_k=3),
            }

        return {
            "status": "success",
            "model_id": chosen["model_id"],
            "model_name": chosen["name"],
            "category": chosen["category"],
            "file_name": safe_name,
            "file_path": file_path,
            "script": code,
            "params": params,
            "static_validation": static_validation,
            "smoke_validation": smoke_validation,
            "knowledge_matches": self.retrieve_knowledge(description, top_k=3),
        }

    def render_script(self, model_id: str, params: Dict[str, Any]) -> str:
        template = self.templates.get(model_id)
        if template is None:
            raise ValueError(f"No template function for {model_id}")
        return template(params)

    @staticmethod
    def _resolve_builtin_enum_value(enum_name: str, fallback: int) -> int:
        values = load_cpp_enum_values()
        try:
            return int(values.get(enum_name, fallback))
        except Exception:
            return int(fallback)

    def _render_builtin_msg_simu_helper(self) -> str:
        enum_values = load_cpp_enum_values()
        if not enum_values:
            enum_values = {
                "SM_INITIALIZE": 10102,
                "SM_CONTINUE": 10103,
                "SM_STOP": 10106,
                "SM_OUTPUT": 10124,
            }

        lines = [
            "function mode_codes = local_builtin_msg_simu()",
            "    persistent cached_mode_codes;",
            "    if isempty(cached_mode_codes)",
            "        cached_mode_codes = struct();",
        ]
        for enum_name, enum_value in enum_values.items():
            lines.append(f"        cached_mode_codes.{enum_name} = {int(enum_value)};")
        lines.extend(
            [
                "    end",
                "    mode_codes = cached_mode_codes;",
                "end",
            ]
        )
        return "\n".join(lines)

    def get_default_params(self, model_id: str) -> Dict[str, Any]:
        for item in self.catalog:
            if item.get("model_id") == model_id:
                return dict(item.get("default_params", {}))
        return {}

    def save_script(
        self,
        code: str,
        model_id: str,
        output_dir: str = "generated_models",
        file_name: Optional[str] = None,
    ) -> Tuple[str, str]:
        os.makedirs(output_dir, exist_ok=True)
        if not file_name:
            inferred_function_name = _infer_matlab_primary_function_name(code)
            if inferred_function_name:
                file_name = f"{inferred_function_name}.m"
            else:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_name = f"{model_id}_{ts}.m"
        elif not file_name.endswith(".m"):
            file_name = f"{file_name}.m"
        safe_name = _sanitize_filename(file_name)
        file_path = os.path.abspath(os.path.join(output_dir, safe_name))
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)
        return safe_name, file_path

    def _pick_model(self, description: str, model_id: Optional[str]) -> Optional[Dict[str, Any]]:
        if model_id:
            for item in self.catalog:
                if item["model_id"] == model_id:
                    return item
        ranked = self.retrieve_knowledge(description, top_k=1)
        if not ranked:
            return None
        match_id = ranked[0]["model_id"]
        for item in self.catalog:
            if item["model_id"] == match_id:
                return item
        return None

    def _infer_params(self, description: str, item: Dict[str, Any]) -> Dict[str, Any]:
        params = dict(item.get("default_params", {}))
        text = description.lower()

        stop_time = _extract_number(text, ["stop time", "仿真", "模拟", "运行"])
        if stop_time is not None and "stop_time" in params:
            params["stop_time"] = stop_time

        if "kp" in params:
            kp = _extract_named_number(text, ["kp", "比例"])
            if kp is not None:
                params["kp"] = kp
        if "ki" in params:
            ki = _extract_named_number(text, ["ki", "积分"])
            if ki is not None:
                params["ki"] = ki
        if "kd" in params:
            kd = _extract_named_number(text, ["kd", "微分"])
            if kd is not None:
                params["kd"] = kd

        for key in (
            "m",
            "c",
            "k",
            "dt",
            "steps",
            "fs",
            "cutoff_hz",
            "na",
            "nb",
            "nk",
            "ts",
            "mass0",
            "fuel_mass",
            "burn_rate",
            "thrust",
            "drag_coeff",
            "area",
            "air_density",
            "g",
            "launch_angle_deg",
            "init_speed",
            "burn_time",
            "mu",
            "earth_radius",
            "altitude0",
            "v0",
            "mass",
            "water_density",
            "displaced_volume",
            "x0",
            "y0",
            "target_speed_x",
            "target_speed_y",
            "process_noise",
            "measurement_noise",
            "red0",
            "blue0",
            "alpha",
            "beta",
        ):
            if key in params:
                val = _extract_named_number(text, [key])
                if val is not None:
                    params[key] = int(val) if isinstance(params[key], int) else val

        vector_matches = re.findall(r"\[[0-9\.\-\s;\,]+\]", description)
        if "numerator" in params and vector_matches:
            params["numerator"] = vector_matches[0]
        if "denominator" in params and len(vector_matches) > 1:
            params["denominator"] = vector_matches[1]

        if "sample" in text or "采样" in text:
            sample_time = _extract_number(text, ["sample", "sampling", "采样"])
            if sample_time is not None and "ts" in params:
                params["ts"] = sample_time

        alias_groups = {
            "missile_flight_2d": {
                "mass0": ["mass0", "initial mass", "\u521d\u59cb\u8d28\u91cf", "\u603b\u8d28\u91cf"],
                "thrust": ["thrust", "\u63a8\u529b"],
                "drag_coeff": ["drag_coeff", "drag coefficient", "\u963b\u529b\u7cfb\u6570", "cd"],
                "area": ["area", "frontal area", "\u8fce\u98ce\u9762\u79ef", "\u622a\u9762\u79ef"],
                "air_density": ["air_density", "\u7a7a\u6c14\u5bc6\u5ea6", "rho"],
                "g": ["g", "gravity", "\u91cd\u529b\u52a0\u901f\u5ea6"],
                "launch_angle_deg": ["launch_angle_deg", "launch angle", "\u53d1\u5c04\u89d2", "\u89d2\u5ea6"],
                "init_speed": ["init_speed", "initial speed", "\u521d\u901f\u5ea6", "\u521d\u59cb\u901f\u5ea6"],
                "burn_time": ["burn_time", "burn time", "\u71c3\u70e7\u65f6\u95f4", "\u63a8\u529b\u65f6\u95f4"],
                "dt": ["dt", "\u6b65\u957f", "\u65f6\u95f4\u6b65\u957f"],
            },
            "satellite_orbit_2body": {
                "mu": ["mu", "gravitational parameter", "\u5f15\u529b\u53c2\u6570"],
                "earth_radius": ["earth_radius", "earth radius", "\u5730\u7403\u534a\u5f84"],
                "altitude0": ["altitude0", "altitude", "\u521d\u59cb\u9ad8\u5ea6", "\u8f68\u9053\u9ad8\u5ea6"],
                "v0": ["v0", "orbital speed", "initial speed", "\u8f68\u9053\u901f\u5ea6", "\u521d\u59cb\u901f\u5ea6"],
                "dt": ["dt", "\u6b65\u957f", "\u65f6\u95f4\u6b65\u957f"],
            },
            "torpedo_underwater_launch_1d": {
                "mass": ["mass", "\u8d28\u91cf"],
                "thrust": ["thrust", "\u63a8\u529b"],
                "drag_coeff": ["drag_coeff", "drag coefficient", "\u963b\u529b\u7cfb\u6570", "cd"],
                "area": ["area", "cross section", "\u6a2a\u622a\u9762\u79ef", "\u622a\u9762\u79ef"],
                "water_density": ["water_density", "water density", "\u6c34\u5bc6\u5ea6", "rho"],
                "displaced_volume": ["displaced_volume", "displaced volume", "\u6392\u6c34\u4f53\u79ef", "\u6392\u5f00\u4f53\u79ef"],
                "g": ["g", "gravity", "\u91cd\u529b\u52a0\u901f\u5ea6"],
                "dt": ["dt", "\u6b65\u957f", "\u65f6\u95f4\u6b65\u957f"],
            },
            "radar_target_tracking_2d": {
                "dt": ["dt", "\u6b65\u957f", "\u65f6\u95f4\u6b65\u957f"],
                "steps": ["steps", "\u6b65\u6570"],
                "process_noise": ["process_noise", "\u8fc7\u7a0b\u566a\u58f0"],
                "measurement_noise": ["measurement_noise", "measurement std", "\u6d4b\u91cf\u566a\u58f0"],
                "x0": ["x0", "\u521d\u59cbx", "\u521d\u59cb\u6a2a\u5411\u4f4d\u7f6e"],
                "y0": ["y0", "\u521d\u59cby", "\u521d\u59cb\u7eb5\u5411\u4f4d\u7f6e"],
                "target_speed_x": ["target_speed_x", "vx", "\u76ee\u6807x\u901f\u5ea6", "\u76ee\u6807\u6a2a\u5411\u901f\u5ea6"],
                "target_speed_y": ["target_speed_y", "vy", "\u76ee\u6807y\u901f\u5ea6", "\u76ee\u6807\u7eb5\u5411\u901f\u5ea6"],
            },
            "lanchester_battle_attrition": {
                "red0": ["red0", "red force", "\u7ea2\u65b9\u5175\u529b", "\u7ea2\u65b9\u521d\u59cb\u5175\u529b"],
                "blue0": ["blue0", "blue force", "\u84dd\u65b9\u5175\u529b", "\u84dd\u65b9\u521d\u59cb\u5175\u529b"],
                "alpha": ["alpha", "\u84dd\u65b9\u6740\u4f24\u7cfb\u6570", "blue firepower"],
                "beta": ["beta", "\u7ea2\u65b9\u6740\u4f24\u7cfb\u6570", "red firepower"],
                "dt": ["dt", "\u6b65\u957f", "\u65f6\u95f4\u6b65\u957f"],
            },
        }
        model_aliases = alias_groups.get(str(item.get("model_id", "")), {})
        for key, aliases in model_aliases.items():
            for alias in aliases:
                val = _extract_named_number(description, [alias])
                if val is not None:
                    params[key] = int(val) if isinstance(params.get(key), int) else val
                    break

        return params

    def has_template(self, model_id: str) -> bool:
        return str(model_id or "").strip() in self.templates

    def _render_standard_model_function(
        self,
        function_name: str,
        parameter_lines: List[str],
        state_dim_expr: str,
        output_dim_expr: str,
        input_dim_expr: str,
        default_x_expr: str,
        default_u_expr: str,
        shared_logic: str = "",
        y_logic: str = "",
        f_logic: str = "",
        init_extra: str = "",
        cont_extra: str = "",
        out_extra: str = "",
        exit_body: str = "",
    ) -> str:
        parameter_block = _indent_block("\n".join(line for line in parameter_lines if str(line).strip()), 4)
        init_body = _indent_block(_join_matlab_blocks(shared_logic, y_logic, f_logic, init_extra), 12)
        cont_body = _indent_block(_join_matlab_blocks(shared_logic, y_logic, f_logic, cont_extra), 12)
        out_body = _indent_block(_join_matlab_blocks(shared_logic, y_logic, out_extra), 12)
        exit_block = _indent_block(exit_body, 12)
        builtin_helper = _indent_block(self._render_builtin_msg_simu_helper(), 0)

        lines = [
            f"function [y, f] = {function_name}(mode, time, Ts, x, u)",
            "    mode_codes = local_builtin_msg_simu();",
            "    INIT = mode_codes.SM_INITIALIZE;",
            "    CONT = mode_codes.SM_CONTINUE;",
            "    OUT  = mode_codes.SM_OUTPUT;",
            "    EXIT = mode_codes.SM_STOP;",
            "",
        ]
        if parameter_block:
            lines.append(parameter_block)
            lines.append("")
        lines.extend(
            [
                f"    state_dim = max(0, {state_dim_expr});",
                f"    output_dim = max(0, {output_dim_expr});",
                f"    input_dim = max(0, {input_dim_expr});",
                "",
                "    if nargin < 4 || isempty(x)",
                f"        x = {default_x_expr};",
                "    else",
                "        x = x(:);",
                "    end",
                "    if state_dim == 0",
                "        x = zeros(0, 1);",
                "    elseif numel(x) < state_dim",
                "        x = [x; zeros(state_dim - numel(x), 1)];",
                "    elseif numel(x) > state_dim",
                "        x = x(1:state_dim);",
                "    end",
                "",
                "    if nargin < 5 || isempty(u)",
                f"        u = {default_u_expr};",
                "    else",
                "        u = u(:);",
                "    end",
                "    if input_dim == 0",
                "        u = zeros(0, 1);",
                "    elseif numel(u) < input_dim",
                "        u = [u; zeros(input_dim - numel(u), 1)];",
                "    elseif numel(u) > input_dim",
                "        u = u(1:input_dim);",
                "    end",
                "",
                "    switch mode",
                "        case INIT",
                "            y = zeros(output_dim, 1);",
                "            f = zeros(state_dim, 1);",
            ]
        )
        if init_body:
            lines.append(init_body)
        lines.extend(
            [
                "",
                "        case CONT",
                "            y = zeros(output_dim, 1);",
                "            f = zeros(state_dim, 1);",
            ]
        )
        if cont_body:
            lines.append(cont_body)
        lines.extend(
            [
                "",
                "        case OUT",
                "            y = zeros(output_dim, 1);",
                "            f = zeros(state_dim, 1);",
            ]
        )
        if out_body:
            lines.append(out_body)
        lines.extend(
            [
                "",
                "        case EXIT",
                "            y = zeros(output_dim, 1);",
                "            f = zeros(state_dim, 1);",
            ]
        )
        if exit_block:
            lines.append(exit_block)
        lines.extend(
            [
                "",
                "        otherwise",
                "            error('Invalid mode');",
                "    end",
                "end",
                "",
                builtin_helper,
            ]
        )
        return "\n".join(lines)

    def _tpl_transfer_function_step(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="transfer_function_step",
            parameter_lines=[
                f"num = {p['numerator']};",
                f"den = {p['denominator']};",
                "[A, B, C, D] = tf2ss(num, den);",
            ],
            state_dim_expr="size(A, 1)",
            output_dim_expr="size(C, 1)",
            input_dim_expr="1",
            default_x_expr="zeros(state_dim, 1)",
            default_u_expr="1",
            shared_logic="""
step_val = u(1);
if time < 0
    step_val = 0;
end
response = C * x + D * step_val;
response = response(:);
""",
            y_logic="""
y = response;
""",
            f_logic="""
f = A * x + B * step_val;
""",
        )

    def _tpl_state_space_response(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="state_space_response",
            parameter_lines=[
                f"A = {p['A']};",
                f"B = {p['B']};",
                f"C = {p['C']};",
                f"D = {p['D']};",
            ],
            state_dim_expr="size(A, 1)",
            output_dim_expr="size(C, 1)",
            input_dim_expr="size(B, 2)",
            default_x_expr="zeros(state_dim, 1)",
            default_u_expr="ones(input_dim, 1)",
            shared_logic="""
response = C * x + D * u;
response = response(:);
""",
            y_logic="""
y = response;
""",
            f_logic="""
f = A * x + B * u;
""",
        )

    def _tpl_pid_simulink_loop(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="pid_simulink_loop",
            parameter_lines=[
                f"kp = {p['kp']};",
                f"ki = {p['ki']};",
                f"kd = {p['kd']};",
                f"num = {p['numerator']};",
                f"den = {p['denominator']};",
                "[A, B, C, D] = tf2ss(num, den);",
                "plant_state_dim = size(A, 1);",
            ],
            state_dim_expr="plant_state_dim + 2",
            output_dim_expr="2",
            input_dim_expr="1",
            default_x_expr="zeros(state_dim, 1)",
            default_u_expr="1",
            shared_logic="""
plant_state = x(1:plant_state_dim);
int_error = x(plant_state_dim + 1);
prev_error = x(plant_state_dim + 2);
reference = u(1);
sample_time = max(Ts, 1e-6);
open_loop_output = C * plant_state;
open_loop_output = open_loop_output(:);
error_val = reference - open_loop_output(1);
error_dot = (error_val - prev_error) / sample_time;
control_val = kp * error_val + ki * int_error + kd * error_dot;
plant_output = C * plant_state + D * control_val;
plant_output = plant_output(:);
""",
            y_logic="""
y(1) = plant_output(1);
y(2) = control_val;
""",
            f_logic="""
f(1:plant_state_dim) = A * plant_state + B * control_val;
f(plant_state_dim + 1) = error_val;
f(plant_state_dim + 2) = error_dot;
""",
        )

    def _tpl_mass_spring_damper_ode(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="mass_spring_damper_ode",
            parameter_lines=[
                f"m = {p['m']};",
                f"c = {p['c']};",
                f"k = {p['k']};",
            ],
            state_dim_expr="2",
            output_dim_expr="2",
            input_dim_expr="1",
            default_x_expr=f"{p['x0']}",
            default_u_expr="0",
            shared_logic="""
position = x(1);
velocity = x(2);
force = u(1);
""",
            y_logic="""
y(1) = position;
y(2) = velocity;
""",
            f_logic="""
f(1) = velocity;
f(2) = (force - c * velocity - k * position) / m;
""",
        )

    def _tpl_kalman_tracking(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="kalman_tracking",
            parameter_lines=[
                f"dt = {p['dt']};",
                f"process_noise = {p['process_noise']};",
                f"measurement_noise = {p['measurement_noise']};",
            ],
            state_dim_expr="4",
            output_dim_expr="3",
            input_dim_expr="1",
            default_x_expr="[0; 1; 0; 1]",
            default_u_expr="x(1)",
            shared_logic="""
sample_time = max(Ts, dt);
if sample_time <= 0
    sample_time = dt;
end
true_pos = x(1);
true_vel = x(2);
est_pos = x(3);
est_vel = x(4);
measurement = u(1);
alpha = min(max(process_noise / max(process_noise + measurement_noise, 1e-6), 0.05), 0.95);
beta = min(max(alpha / max(sample_time, 1e-6), 0.01), 2.0);
pred_pos = est_pos + est_vel * sample_time;
pred_vel = est_vel;
innovation = measurement - pred_pos;
next_est_pos = pred_pos + alpha * innovation;
next_est_vel = pred_vel + beta * innovation;
""",
            y_logic="""
y(1) = measurement;
y(2) = next_est_pos;
y(3) = next_est_vel;
""",
            f_logic="""
f(1) = true_vel;
f(2) = 0;
f(3) = (next_est_pos - est_pos) / sample_time;
f(4) = (next_est_vel - est_vel) / sample_time;
""",
        )

    def _tpl_arx_identification(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="arx_identification",
            parameter_lines=[
                f"na = {int(p['na'])};",
                f"nb = {int(p['nb'])};",
                f"nk = {int(p['nk'])};",
                "a_demo = [1.2; -0.5];",
                "b_demo = [0.4; 0.2];",
            ],
            state_dim_expr="4",
            output_dim_expr="1",
            input_dim_expr="1",
            default_x_expr="zeros(4, 1)",
            default_u_expr="0",
            shared_logic="""
sample_time = max(Ts, 1);
if sample_time <= 0
    sample_time = 1;
end
prev_y1 = x(1);
prev_y2 = x(2);
prev_u1 = x(3);
prev_u2 = x(4);
current_u = u(1);
predicted_y = 0;
if na >= 1
    predicted_y = predicted_y + a_demo(1) * prev_y1;
end
if na >= 2
    predicted_y = predicted_y + a_demo(2) * prev_y2;
end
if nb >= 1
    predicted_y = predicted_y + b_demo(1) * prev_u1;
end
if nb >= 2
    predicted_y = predicted_y + b_demo(2) * prev_u2;
end
next_state = [predicted_y; prev_y1; current_u; prev_u1];
""",
            y_logic="""
y(1) = predicted_y;
""",
            f_logic="""
f = (next_state - x) / sample_time;
""",
        )

    def _tpl_mpc_control(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="mpc_control",
            parameter_lines=[
                f"Ts_default = {p['ts']};",
                f"prediction_horizon = {int(p['prediction_horizon'])};",
                f"control_horizon = {int(p['control_horizon'])};",
                "[A, B, C, D] = tf2ss([1], [1 1 0]);",
                "plant_state_dim = size(A, 1);",
            ],
            state_dim_expr="plant_state_dim + 1",
            output_dim_expr="2",
            input_dim_expr="1",
            default_x_expr="zeros(state_dim, 1)",
            default_u_expr="1",
            shared_logic="""
plant_state = x(1:plant_state_dim);
last_u = x(plant_state_dim + 1);
sample_time = max(Ts, Ts_default);
if sample_time <= 0
    sample_time = Ts_default;
end
reference = u(1);
pred_output = C * plant_state + D * last_u;
pred_output = pred_output(:);
error_val = reference - pred_output(1);
plant_rate = 0;
if plant_state_dim >= 2
    plant_rate = plant_state(2);
end
horizon_gain = max(prediction_horizon, 1) / max(control_horizon, 1);
control_val = horizon_gain * 0.05 * error_val - 0.1 * plant_rate;
control_val = min(max(control_val, -1), 1);
plant_output = C * plant_state + D * control_val;
plant_output = plant_output(:);
""",
            y_logic="""
y(1) = plant_output(1);
y(2) = control_val;
""",
            f_logic="""
f(1:plant_state_dim) = A * plant_state + B * control_val;
f(plant_state_dim + 1) = (control_val - last_u) / sample_time;
""",
        )

    def _tpl_fft_lowpass_filter(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="fft_lowpass_filter",
            parameter_lines=[
                f"fs = {int(p['fs'])};",
                f"cutoff = {p['cutoff_hz']};",
            ],
            state_dim_expr="1",
            output_dim_expr="2",
            input_dim_expr="1",
            default_x_expr="0",
            default_u_expr="sin(2 * pi * 5 * time) + 0.6 * sin(2 * pi * 80 * time)",
            shared_logic="""
sample_time = max(Ts, 1 / fs);
if sample_time <= 0
    sample_time = 1 / fs;
end
signal_in = u(1);
alpha = min(max(2 * pi * cutoff / fs, 0), 1);
filtered = x(1) + alpha * (signal_in - x(1));
""",
            y_logic="""
y(1) = signal_in;
y(2) = filtered;
""",
            f_logic="""
f(1) = (filtered - x(1)) / sample_time;
""",
        )

    def _tpl_battery_rc_model(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="battery_rc_model",
            parameter_lines=[
                f"Q = {p['capacity_ah']} * 3600;",
                f"R0 = {p['r0']};",
                f"R1 = {p['r1']};",
                f"C1 = {p['c1']};",
            ],
            state_dim_expr="2",
            output_dim_expr="2",
            input_dim_expr="1",
            default_x_expr="[1; 0]",
            default_u_expr="1.5",
            shared_logic="""
soc = min(max(x(1), 0), 1);
v1 = x(2);
current = u(1);
voc = 3.0 + 1.2 * soc - 0.1 * soc^2;
terminal_voltage = voc - current * R0 - v1;
""",
            y_logic="""
y(1) = terminal_voltage;
y(2) = soc;
""",
            f_logic="""
f(1) = -current / Q;
f(2) = -(1 / (R1 * C1)) * v1 + current / C1;
""",
        )

    def _tpl_pv_iv_curve(self, p: Dict[str, Any]) -> str:
        default_voltage = float(p['voc']) / 2.0
        return self._render_standard_model_function(
            function_name="pv_iv_curve",
            parameter_lines=[
                f"Isc = {p['isc']};",
                f"Voc = {p['voc']};",
            ],
            state_dim_expr="1",
            output_dim_expr="2",
            input_dim_expr="1",
            default_x_expr=f"{default_voltage}",
            default_u_expr=f"{default_voltage}",
            shared_logic="""
voltage = max(min(u(1), Voc), 0);
current = Isc * (1 - (voltage / max(Voc, 1e-6))^1.25);
current = max(current, 0);
power_val = voltage * current;
""",
            y_logic="""
y(1) = current;
y(2) = power_val;
""",
            f_logic="""
f(1) = 0;
""",
        )

    def _tpl_robot_2dof_kinematics(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="robot_2dof_kinematics",
            parameter_lines=[
                f"l1 = {p['l1']};",
                f"l2 = {p['l2']};",
            ],
            state_dim_expr="2",
            output_dim_expr="4",
            input_dim_expr="2",
            default_x_expr="[0; 0]",
            default_u_expr=f"[{p['x_target']}; {p['y_target']}]",
            shared_logic="""
sample_time = max(Ts, 1e-3);
target_x = u(1);
target_y = u(2);
c2 = (target_x^2 + target_y^2 - l1^2 - l2^2) / (2 * l1 * l2);
c2 = max(min(c2, 1), -1);
s2 = -sqrt(max(0, 1 - c2^2));
theta2_cmd = atan2(s2, c2);
theta1_cmd = atan2(target_y, target_x) - atan2(l2 * sin(theta2_cmd), l1 + l2 * cos(theta2_cmd));
fk_x = l1 * cos(theta1_cmd) + l2 * cos(theta1_cmd + theta2_cmd);
fk_y = l1 * sin(theta1_cmd) + l2 * sin(theta1_cmd + theta2_cmd);
next_state = [theta1_cmd; theta2_cmd];
""",
            y_logic="""
y(1) = theta1_cmd;
y(2) = theta2_cmd;
y(3) = fk_x;
y(4) = fk_y;
""",
            f_logic="""
f = (next_state - x) / sample_time;
""",
        )

    def _tpl_rocket_launch_1d(self, p: Dict[str, Any]) -> str:
        dry_mass = max(float(p["mass0"]) - float(p["fuel_mass"]), 1e-3)
        return self._render_standard_model_function(
            function_name="rocket_launch_1d",
            parameter_lines=[
                f"mass0 = {p['mass0']};",
                f"dry_mass = {dry_mass};",
                f"burn_rate = {p['burn_rate']};",
                f"thrust_default = {p['thrust']};",
                f"Cd = {p['drag_coeff']};",
                f"A = {p['area']};",
                f"rho0 = {p['air_density']};",
                f"g0 = {p['g']};",
            ],
            state_dim_expr="3",
            output_dim_expr="2",
            input_dim_expr="2",
            default_x_expr="[0; 0; mass0]",
            default_u_expr="[thrust_default; 90]",
            shared_logic="""
height = max(x(1), 0);
velocity = x(2);
mass = min(max(x(3), dry_mass), mass0);
thrust_val = max(u(1), 0);
angle_val = max(min(u(2), 90), 0);
angle_rad = angle_val * pi / 180;
rho = rho0 * exp(-height / 8500);
drag = 0.5 * rho * Cd * A * velocity^2;
g_h = g0 * (6371 / (6371 + height / 1000))^2;
if mass > dry_mass && thrust_val > 0
    m_dot = burn_rate;
else
    m_dot = 0;
    thrust_val = 0;
end
thrust_vertical = thrust_val * sin(angle_rad);
drag_vertical = drag * sin(angle_rad) * sign(-velocity);
accel = (thrust_vertical + drag_vertical) / max(mass, 0.1) - g_h;
""",
            y_logic="""
y(1) = height;
y(2) = velocity;
""",
            f_logic="""
f(1) = velocity * sin(angle_rad);
f(2) = accel;
f(3) = -m_dot;
""",
        )


    def _tpl_missile_flight_2d(self, p: Dict[str, Any]) -> str:
        angle_rad = float(p["launch_angle_deg"]) * 3.141592653589793 / 180.0
        return self._render_standard_model_function(
            function_name="missile_flight_2d",
            parameter_lines=[
                f"mass0 = {p['mass0']};",
                f"thrust_default = {p['thrust']};",
                f"Cd = {p['drag_coeff']};",
                f"A = {p['area']};",
                f"rho = {p['air_density']};",
                f"g = {p['g']};",
                f"burn_time = {p['burn_time']};",
            ],
            state_dim_expr="4",
            output_dim_expr="3",
            input_dim_expr="2",
            default_x_expr=f"[0; 0; {p['init_speed']} * cos({angle_rad}); {p['init_speed']} * sin({angle_rad})]",
            default_u_expr=f"[thrust_default; {p['launch_angle_deg']}]",
            shared_logic="""
pos_x = x(1);
pos_y = max(x(2), 0);
vel_x = x(3);
vel_y = x(4);
thrust_val = max(u(1), 0);
launch_angle_deg = max(min(u(2), 90), -10);
theta = launch_angle_deg * pi / 180;
if time > burn_time
    thrust_val = 0;
end
speed = hypot(vel_x, vel_y);
if speed > 1e-8
    drag = 0.5 * rho * Cd * A * speed^2;
    drag_x = drag * vel_x / speed;
    drag_y = drag * vel_y / speed;
else
    drag_x = 0;
    drag_y = 0;
end
ax_val = (thrust_val * cos(theta) - drag_x) / mass0;
ay_val = (thrust_val * sin(theta) - drag_y) / mass0 - g;
if pos_y <= 0 && vel_y < 0 && time > 0
    ay_val = 0;
    vel_y = 0;
end
""",
            y_logic="""
y(1) = pos_x;
y(2) = pos_y;
y(3) = speed;
""",
            f_logic="""
f(1) = vel_x;
f(2) = vel_y;
f(3) = ax_val;
f(4) = ay_val;
""",
        )

    def _tpl_satellite_orbit_2body(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="satellite_orbit_2body",
            parameter_lines=[
                f"mu = {p['mu']};",
                f"Re = {p['earth_radius']};",
            ],
            state_dim_expr="4",
            output_dim_expr="3",
            input_dim_expr="0",
            default_x_expr=f"[{p['earth_radius']} + {p['altitude0']}; 0; 0; {p['v0']}]",
            default_u_expr="zeros(0, 1)",
            shared_logic="""
pos_x = x(1);
pos_y = x(2);
vel_x = x(3);
vel_y = x(4);
radius = max(hypot(pos_x, pos_y), Re);
ax_val = -mu * pos_x / radius^3;
ay_val = -mu * pos_y / radius^3;
altitude = radius - Re;
speed = hypot(vel_x, vel_y);
""",
            y_logic="""
y(1) = pos_x;
y(2) = pos_y;
y(3) = altitude;
""",
            f_logic="""
f(1) = vel_x;
f(2) = vel_y;
f(3) = ax_val;
f(4) = ay_val;
""",
        )

    def _tpl_torpedo_underwater_launch_1d(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="torpedo_underwater_launch_1d",
            parameter_lines=[
                f"mass = {p['mass']};",
                f"thrust_default = {p['thrust']};",
                f"Cd = {p['drag_coeff']};",
                f"A = {p['area']};",
                f"rho = {p['water_density']};",
                f"Vd = {p['displaced_volume']};",
                f"g = {p['g']};",
            ],
            state_dim_expr="2",
            output_dim_expr="2",
            input_dim_expr="1",
            default_x_expr="[0; 0]",
            default_u_expr="thrust_default",
            shared_logic="""
displacement = max(x(1), 0);
velocity = x(2);
thrust_val = u(1);
weight = mass * g;
buoyancy = rho * g * Vd;
drag = 0.5 * rho * Cd * A * velocity * abs(velocity);
accel = (thrust_val + buoyancy - weight - drag) / mass;
""",
            y_logic="""
y(1) = displacement;
y(2) = velocity;
""",
            f_logic="""
f(1) = velocity;
f(2) = accel;
""",
        )

    def _tpl_radar_target_tracking_2d(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="radar_target_tracking_2d",
            parameter_lines=[
                f"dt = {p['dt']};",
                f"process_noise = {p['process_noise']};",
                f"measurement_noise = {p['measurement_noise']};",
            ],
            state_dim_expr="4",
            output_dim_expr="4",
            input_dim_expr="2",
            default_x_expr=f"[{p['x0']}; {p['y0']}; {p['target_speed_x']}; {p['target_speed_y']}]",
            default_u_expr=f"[{p['x0']}; {p['y0']}]",
            shared_logic="""
sample_time = max(Ts, dt);
if sample_time <= 0
    sample_time = dt;
end
est_x = x(1);
est_y = x(2);
est_vx = x(3);
est_vy = x(4);
meas_x = u(1);
meas_y = u(2);
alpha = min(max(process_noise / max(process_noise + measurement_noise, 1e-6), 0.05), 0.95);
beta = min(max(alpha / max(sample_time, 1e-6), 0.01), 2.0);
pred_x = est_x + est_vx * sample_time;
pred_y = est_y + est_vy * sample_time;
innovation_x = meas_x - pred_x;
innovation_y = meas_y - pred_y;
next_x = pred_x + alpha * innovation_x;
next_y = pred_y + alpha * innovation_y;
next_vx = est_vx + beta * innovation_x;
next_vy = est_vy + beta * innovation_y;
next_state = [next_x; next_y; next_vx; next_vy];
""",
            y_logic="""
y(1) = meas_x;
y(2) = meas_y;
y(3) = next_x;
y(4) = next_y;
""",
            f_logic="""
f = (next_state - x) / sample_time;
""",
        )

    def _tpl_lanchester_battle_attrition(self, p: Dict[str, Any]) -> str:
        return self._render_standard_model_function(
            function_name="lanchester_battle_attrition",
            parameter_lines=[
                f"alpha = {p['alpha']};",
                f"beta = {p['beta']};",
            ],
            state_dim_expr="2",
            output_dim_expr="2",
            input_dim_expr="0",
            default_x_expr=f"[{p['red0']}; {p['blue0']}]",
            default_u_expr="zeros(0, 1)",
            shared_logic="""
red_force = max(x(1), 0);
blue_force = max(x(2), 0);
red_dot = -alpha * blue_force;
blue_dot = -beta * red_force;
if red_force <= 0 || blue_force <= 0
    red_dot = 0;
    blue_dot = 0;
end
""",
            y_logic="""
y(1) = red_force;
y(2) = blue_force;
""",
            f_logic="""
f(1) = red_dot;
f(2) = blue_dot;
""",
        )


def _token_overlap(a: str, b: str) -> int:
    tokens = set(re.split(r"[\s,;，。]+", b))
    return sum(1 for t in tokens if t and t in a)


def _extract_number(text: str, keywords: List[str]) -> Optional[float]:
    for keyword in keywords:
        pattern = rf"{re.escape(keyword)}[^\d\-]*(-?\d+(?:\.\d+)?)"
        matched = re.search(pattern, text)
        if matched:
            return float(matched.group(1))
    return None


def _extract_named_number(text: str, names: List[str]) -> Optional[float]:
    patterns = []
    for name in names:
        patterns.extend(
            [
                rf"{re.escape(name)}\s*[=:：]?\s*(-?\d+(?:\.\d+)?)",
                rf"{re.escape(name)}[^\d\-]*(-?\d+(?:\.\d+)?)",
            ]
        )
    for pattern in patterns:
        matched = re.search(pattern, text)
        if matched:
            return float(matched.group(1))
    return None


def _join_matlab_blocks(*blocks: str) -> str:
    normalized: List[str] = []
    for block in blocks:
        text = str(block or "").strip("\n")
        if text.strip():
            normalized.append(text)
    return "\n".join(normalized)


def _indent_block(block: str, spaces: int) -> str:
    text = str(block or "").strip("\n")
    if not text:
        return ""
    prefix = " " * max(0, int(spaces))
    return "\n".join(prefix + line if line else "" for line in text.splitlines())


def _infer_matlab_primary_function_name(code: str) -> str:
    for raw_line in str(code or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("%"):
            continue
        if not line.lower().startswith("function"):
            return ""

        match = re.match(
            r"^function\s+(?:\[[^\]]+\]\s*=\s*|[A-Za-z]\w*\s*=\s*)?([A-Za-z]\w*)\s*\(",
            line,
        )
        if match:
            return match.group(1)

        match = re.match(r"^function\s+([A-Za-z]\w*)\s*$", line)
        if match:
            return match.group(1)
        return ""
    return ""


def _sanitize_filename(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)
    if not sanitized.endswith(".m"):
        sanitized = f"{sanitized}.m"
    return sanitized
