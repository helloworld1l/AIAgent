"""
MATLAB .m file generation engine driven by local knowledge entries.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from knowledge_base.matlab_model_data import get_model_catalog


class MatlabModelGenerator:
    def __init__(self):
        self.catalog = get_model_catalog()
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
        template = self.templates.get(chosen["model_id"])
        if template is None:
            return {"status": "error", "message": f"No template function for {chosen['model_id']}"}

        code = template(params)
        os.makedirs(output_dir, exist_ok=True)

        if not file_name:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"{chosen['model_id']}_{ts}.m"
        elif not file_name.endswith(".m"):
            file_name = f"{file_name}.m"

        safe_name = _sanitize_filename(file_name)
        file_path = os.path.abspath(os.path.join(output_dir, safe_name))
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

        return {
            "status": "success",
            "model_id": chosen["model_id"],
            "model_name": chosen["name"],
            "category": chosen["category"],
            "file_name": safe_name,
            "file_path": file_path,
            "script": code,
            "params": params,
            "knowledge_matches": self.retrieve_knowledge(description, top_k=3),
        }

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

        for key in ("m", "c", "k", "dt", "steps", "fs", "cutoff_hz", "na", "nb", "nk", "ts"):
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

        return params

    def _tpl_transfer_function_step(self, p: Dict[str, Any]) -> str:
        return f"""%% Auto-generated MATLAB model: Transfer Function Step Response
clear; clc; close all;

num = {p['numerator']};
den = {p['denominator']};
sys = tf(num, den);

figure('Name', 'Step Response');
step(sys, {p['stop_time']});
grid on;
title('Transfer Function Step Response');

info = stepinfo(sys);
disp(info);
"""

    def _tpl_state_space_response(self, p: Dict[str, Any]) -> str:
        return f"""%% Auto-generated MATLAB model: State Space Simulation
clear; clc; close all;

A = {p['A']};
B = {p['B']};
C = {p['C']};
D = {p['D']};
sys = ss(A, B, C, D);

t = linspace(0, {p['stop_time']}, 1000)';
u = ones(size(t));
y = lsim(sys, u, t);

figure('Name', 'State Space Output');
plot(t, y, 'LineWidth', 1.5);
xlabel('Time (s)');
ylabel('Output');
title('State Space Simulation');
grid on;
"""

    def _tpl_pid_simulink_loop(self, p: Dict[str, Any]) -> str:
        return f"""%% Auto-generated MATLAB model: PID closed-loop Simulink
clear; clc; close all;

modelName = 'auto_pid_loop_model';
if bdIsLoaded(modelName)
    close_system(modelName, 0);
end
new_system(modelName);
open_system(modelName);

add_block('simulink/Sources/Step', [modelName '/Step'], ...
    'Position', [30 80 60 110]);
add_block('simulink/Math Operations/Sum', [modelName '/Sum'], ...
    'Inputs', '+-', 'Position', [100 78 120 112]);
add_block('simulink/Continuous/PID Controller', [modelName '/PID'], ...
    'P', '{p['kp']}', 'I', '{p['ki']}', 'D', '{p['kd']}', ...
    'Position', [170 70 250 120]);
add_block('simulink/Continuous/Transfer Fcn', [modelName '/Plant'], ...
    'Numerator', '{p['numerator']}', 'Denominator', '{p['denominator']}', ...
    'Position', [300 75 380 115]);
add_block('simulink/Sinks/Scope', [modelName '/Scope'], ...
    'Position', [450 80 480 110]);

add_line(modelName, 'Step/1', 'Sum/1');
add_line(modelName, 'Sum/1', 'PID/1');
add_line(modelName, 'PID/1', 'Plant/1');
add_line(modelName, 'Plant/1', 'Scope/1');
add_line(modelName, 'Plant/1', 'Sum/2');

set_param(modelName, 'StopTime', '{p['stop_time']}');
sim(modelName);
save_system(modelName, [modelName '.slx']);
"""

    def _tpl_mass_spring_damper_ode(self, p: Dict[str, Any]) -> str:
        return f"""%% Auto-generated MATLAB model: Mass-Spring-Damper
clear; clc; close all;

m = {p['m']};
c = {p['c']};
k = {p['k']};
x0 = {p['x0']};
tspan = [0 {p['stop_time']}];

f = @(t, x) [x(2); -(c/m)*x(2) - (k/m)*x(1)];
[t, x] = ode45(f, tspan, x0);

figure('Name', 'Mass-Spring-Damper');
subplot(2,1,1);
plot(t, x(:,1), 'LineWidth', 1.5); grid on;
ylabel('Displacement (m)');
subplot(2,1,2);
plot(t, x(:,2), 'LineWidth', 1.5); grid on;
xlabel('Time (s)'); ylabel('Velocity (m/s)');
"""

    def _tpl_kalman_tracking(self, p: Dict[str, Any]) -> str:
        return f"""%% Auto-generated MATLAB model: Kalman tracking
clear; clc; close all;
rng(7);

dt = {p['dt']};
N = {int(p['steps'])};
q = {p['process_noise']};
r = {p['measurement_noise']};

F = [1 dt; 0 1];
H = [1 0];
Q = q * [dt^4/4 dt^3/2; dt^3/2 dt^2];
R = r;

x_true = zeros(2, N);
z = zeros(1, N);
x_true(:,1) = [0; 1];
for k = 2:N
    w = mvnrnd([0 0], Q)';
    x_true(:,k) = F * x_true(:,k-1) + w;
end
for k = 1:N
    z(k) = H*x_true(:,k) + sqrt(R)*randn;
end

x_est = zeros(2, N);
P = eye(2);
for k = 2:N
    x_pred = F*x_est(:,k-1);
    P_pred = F*P*F' + Q;
    K = P_pred*H'/(H*P_pred*H' + R);
    x_est(:,k) = x_pred + K*(z(k) - H*x_pred);
    P = (eye(2)-K*H)*P_pred;
end

t = (0:N-1)*dt;
figure('Name', 'Kalman Tracking');
plot(t, x_true(1,:), 'k-', 'LineWidth', 1.5); hold on;
plot(t, z, '.', 'Color', [0.6 0.6 0.6]);
plot(t, x_est(1,:), 'r-', 'LineWidth', 1.5);
legend('True', 'Measurement', 'Estimated');
xlabel('Time (s)'); ylabel('Position'); grid on;
"""

    def _tpl_arx_identification(self, p: Dict[str, Any]) -> str:
        return f"""%% Auto-generated MATLAB model: ARX identification
clear; clc; close all;
rng(1);

N = {int(p['samples'])};
u = randn(N,1);
y = filter([0 0.4 0.2], [1 -1.2 0.5], u) + 0.05*randn(N,1);
data = iddata(y, u, 1);

na = {int(p['na'])};
nb = {int(p['nb'])};
nk = {int(p['nk'])};
model = arx(data, [na nb nk]);
disp(model);

figure('Name', 'ARX compare');
compare(data, model);
grid on;
"""

    def _tpl_mpc_control(self, p: Dict[str, Any]) -> str:
        return f"""%% Auto-generated MATLAB model: MPC demo
clear; clc; close all;

Ts = {p['ts']};
plant = tf(1, [1 1 0]);
plant_d = c2d(ss(plant), Ts);

mpcobj = mpc(plant_d, Ts, {int(p['prediction_horizon'])}, {int(p['control_horizon'])});
mpcobj.MV.Min = -1;
mpcobj.MV.Max = 1;
mpcobj.Weights.OutputVariables = 1;
mpcobj.Weights.ManipulatedVariablesRate = 0.1;

T = {p['stop_time']};
r = ones(T/Ts,1);
sim(mpcobj, length(r), r);
"""

    def _tpl_fft_lowpass_filter(self, p: Dict[str, Any]) -> str:
        return f"""%% Auto-generated MATLAB model: FFT low-pass filter
clear; clc; close all;
rng(2);

fs = {int(p['fs'])};
T = {p['duration']};
t = 0:1/fs:T-1/fs;
s = sin(2*pi*5*t) + 0.6*sin(2*pi*80*t) + 0.2*randn(size(t));

N = length(s);
f = (0:N-1)*(fs/N);
S = fft(s);
cutoff = {p['cutoff_hz']};
mask = (f <= cutoff) | (f >= fs-cutoff);
S_filtered = S .* mask;
s_filtered = real(ifft(S_filtered));

figure('Name', 'FFT filtering');
subplot(2,1,1); plot(t, s); grid on; title('Noisy signal');
subplot(2,1,2); plot(t, s_filtered, 'LineWidth', 1.3); grid on; title('Filtered signal');
"""

    def _tpl_battery_rc_model(self, p: Dict[str, Any]) -> str:
        return f"""%% Auto-generated MATLAB model: Battery 1-RC model
clear; clc; close all;

Q = {p['capacity_ah']} * 3600;   % Coulomb
R0 = {p['r0']};
R1 = {p['r1']};
C1 = {p['c1']};
T = {int(p['stop_time'])};
dt = 1;
t = (0:T)';

I = 1.5 + 0.5*sin(2*pi*t/400);   % discharge current profile
soc = ones(size(t));
v1 = zeros(size(t));
voc = @(z) 3.0 + 1.2*z - 0.1*z.^2;
vt = zeros(size(t));

for k = 2:length(t)
    soc(k) = max(0, soc(k-1) - I(k-1)*dt/Q);
    dv1 = -(1/(R1*C1))*v1(k-1) + I(k-1)/C1;
    v1(k) = v1(k-1) + dt*dv1;
    vt(k) = voc(soc(k)) - I(k)*R0 - v1(k);
end

figure('Name', 'Battery RC model');
subplot(2,1,1); plot(t, soc, 'LineWidth', 1.3); ylabel('SOC'); grid on;
subplot(2,1,2); plot(t, vt, 'LineWidth', 1.3); ylabel('Terminal Voltage (V)'); xlabel('Time (s)'); grid on;
"""

    def _tpl_pv_iv_curve(self, p: Dict[str, Any]) -> str:
        return f"""%% Auto-generated MATLAB model: PV IV/PV curve
clear; clc; close all;

Isc = {p['isc']};
Voc = {p['voc']};
N = 200;
V = linspace(0, Voc, N);

% Simplified empirical I-V equation
I = Isc * (1 - (V./Voc).^1.25);
I(I < 0) = 0;
P = V .* I;

figure('Name', 'PV curves');
subplot(2,1,1); plot(V, I, 'LineWidth', 1.5); grid on; xlabel('Voltage (V)'); ylabel('Current (A)'); title('I-V');
subplot(2,1,2); plot(V, P, 'LineWidth', 1.5); grid on; xlabel('Voltage (V)'); ylabel('Power (W)'); title('P-V');
"""

    def _tpl_robot_2dof_kinematics(self, p: Dict[str, Any]) -> str:
        return f"""%% Auto-generated MATLAB model: 2-DOF robot kinematics
clear; clc; close all;

l1 = {p['l1']};
l2 = {p['l2']};
xt = {p['x_target']};
yt = {p['y_target']};

% Inverse kinematics (elbow-down)
c2 = (xt^2 + yt^2 - l1^2 - l2^2) / (2*l1*l2);
s2 = -sqrt(max(0, 1 - c2^2));
theta2 = atan2(s2, c2);
theta1 = atan2(yt, xt) - atan2(l2*sin(theta2), l1 + l2*cos(theta2));

% Forward kinematics check
x = l1*cos(theta1) + l2*cos(theta1 + theta2);
y = l1*sin(theta1) + l2*sin(theta1 + theta2);

disp(['theta1 = ', num2str(rad2deg(theta1)), ' deg']);
disp(['theta2 = ', num2str(rad2deg(theta2)), ' deg']);
disp(['FK position = (', num2str(x), ', ', num2str(y), ')']);

figure('Name', '2-DOF robot');
plot([0, l1*cos(theta1), x], [0, l1*sin(theta1), y], 'o-', 'LineWidth', 2);
hold on; plot(xt, yt, 'rx', 'MarkerSize', 10, 'LineWidth', 2);
axis equal; grid on; xlabel('X'); ylabel('Y');
title('2-DOF Planar Robot Kinematics');
legend('Robot links', 'Target');
"""


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


def _sanitize_filename(name: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", name)
    if not sanitized.endswith(".m"):
        sanitized = f"{sanitized}.m"
    return sanitized

