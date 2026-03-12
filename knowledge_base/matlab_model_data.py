"""
Knowledge entries for MATLAB/Simulink model generation.
"""

from __future__ import annotations

from typing import Dict, List


MATLAB_MODEL_KNOWLEDGE: List[Dict] = [
    {
        "model_id": "transfer_function_step",
        "name": "Transfer Function Step Response",
        "category": "control",
        "keywords": ["transfer function", "tf", "step", "传递函数", "阶跃响应", "控制系统"],
        "description": "Create a transfer function model and run step response.",
        "default_params": {
            "numerator": "[1]",
            "denominator": "[1 3 2]",
            "stop_time": 10,
        },
        "examples": [
            "构建一个二阶传递函数并画阶跃响应",
            "build tf step response with denominator [1 3 2]",
        ],
    },
    {
        "model_id": "state_space_response",
        "name": "State Space Simulation",
        "category": "control",
        "keywords": ["state space", "ss", "状态空间", "lsim", "状态变量"],
        "description": "Build a state-space model and simulate output with lsim.",
        "default_params": {
            "A": "[0 1; -2 -3]",
            "B": "[0; 1]",
            "C": "[1 0]",
            "D": "0",
            "stop_time": 10,
        },
        "examples": [
            "生成状态空间模型仿真代码",
            "simulate state space system with lsim",
        ],
    },
    {
        "model_id": "pid_simulink_loop",
        "name": "PID Closed Loop in Simulink",
        "category": "simulink_control",
        "keywords": ["pid", "simulink", "闭环", "控制器", "调参", "直流电机"],
        "description": "Create a Simulink closed-loop model with PID and transfer function plant.",
        "default_params": {
            "kp": 1.2,
            "ki": 0.8,
            "kd": 0.02,
            "numerator": "[1]",
            "denominator": "[0.5 1]",
            "stop_time": 20,
        },
        "examples": [
            "构建PID闭环控制的Simulink模型",
            "build a simulink pid loop for dc motor",
        ],
    },
    {
        "model_id": "mass_spring_damper_ode",
        "name": "Mass-Spring-Damper ODE Model",
        "category": "physical_modeling",
        "keywords": ["mass spring damper", "ode45", "质量弹簧阻尼", "机械系统", "二阶系统"],
        "description": "Build and simulate a mass-spring-damper model using ode45.",
        "default_params": {
            "m": 1.0,
            "c": 0.5,
            "k": 20.0,
            "x0": "[0; 0]",
            "stop_time": 15,
        },
        "examples": [
            "生成质量弹簧阻尼系统仿真代码",
            "simulate mass spring damper with ode45",
        ],
    },
    {
        "model_id": "kalman_tracking",
        "name": "Kalman Filter Tracking",
        "category": "estimation",
        "keywords": ["kalman", "滤波", "状态估计", "跟踪", "观测噪声"],
        "description": "Create a 1D constant velocity tracking example with Kalman filter.",
        "default_params": {
            "dt": 0.1,
            "steps": 200,
            "process_noise": 0.01,
            "measurement_noise": 0.1,
        },
        "examples": [
            "构建卡尔曼滤波跟踪模型",
            "build kalman filter tracking script",
        ],
    },
    {
        "model_id": "arx_identification",
        "name": "ARX System Identification",
        "category": "identification",
        "keywords": ["arx", "system identification", "辨识", "输入输出建模", "iddata"],
        "description": "Generate ARX identification pipeline from synthetic data.",
        "default_params": {
            "na": 2,
            "nb": 2,
            "nk": 1,
            "samples": 500,
        },
        "examples": [
            "生成ARX系统辨识模型",
            "identify system with arx model",
        ],
    },
    {
        "model_id": "mpc_control",
        "name": "Model Predictive Control Demo",
        "category": "advanced_control",
        "keywords": ["mpc", "predictive control", "模型预测控制", "约束控制"],
        "description": "Create an MPC controller for a simple plant with constraints.",
        "default_params": {
            "ts": 0.1,
            "prediction_horizon": 20,
            "control_horizon": 5,
            "stop_time": 30,
        },
        "examples": [
            "构建MPC控制模型",
            "build model predictive control demo in matlab",
        ],
    },
    {
        "model_id": "fft_lowpass_filter",
        "name": "FFT-based Signal Filter",
        "category": "signal_processing",
        "keywords": ["fft", "signal", "滤波", "低通", "频域"],
        "description": "Generate noisy signal and apply FFT low-pass filtering.",
        "default_params": {
            "fs": 1000,
            "duration": 2.0,
            "cutoff_hz": 40,
        },
        "examples": [
            "生成FFT低通滤波模型",
            "build frequency domain low-pass filtering script",
        ],
    },
    {
        "model_id": "battery_rc_model",
        "name": "Battery 1-RC Equivalent Model",
        "category": "energy",
        "keywords": ["battery", "rc model", "电池", "等效电路", "soc"],
        "description": "Build a simple battery equivalent circuit simulation (1-RC model).",
        "default_params": {
            "capacity_ah": 2.3,
            "r0": 0.03,
            "r1": 0.015,
            "c1": 2400,
            "stop_time": 2000,
        },
        "examples": [
            "构建电池一阶RC等效模型",
            "simulate battery rc equivalent circuit in matlab",
        ],
    },
    {
        "model_id": "pv_iv_curve",
        "name": "PV I-V Curve Model",
        "category": "energy",
        "keywords": ["pv", "solar", "光伏", "i-v", "组件模型"],
        "description": "Build a photovoltaic module I-V and P-V curve script.",
        "default_params": {
            "isc": 8.2,
            "voc": 37.5,
            "n_cells": 60,
            "temperature": 25,
        },
        "examples": [
            "生成光伏组件IV曲线模型",
            "build solar pv iv curve matlab model",
        ],
    },
    {
        "model_id": "robot_2dof_kinematics",
        "name": "2-DOF Robot Kinematics",
        "category": "robotics",
        "keywords": ["robot", "2dof", "kinematics", "机器人", "逆解", "机械臂"],
        "description": "Build forward/inverse kinematics demo for 2-link planar robot.",
        "default_params": {
            "l1": 0.6,
            "l2": 0.4,
            "x_target": 0.7,
            "y_target": 0.2,
        },
        "examples": [
            "构建二自由度机械臂运动学模型",
            "build 2dof robot kinematics matlab script",
        ],
    },
    {
        "model_id": "rocket_launch_1d",
        "name": "1D Rocket Launch Dynamics",
        "category": "aerospace",
        "keywords": [
            "rocket",
            "launch",
            "fire",
            "火箭",
            "发射",
            "弹道",
            "推进",
            "空气阻力",
            "航天",
        ],
        "description": "Simulate 1D vertical rocket launch with thrust, drag, gravity and fuel consumption.",
        "default_params": {
            "mass0": 500.0,
            "fuel_mass": 180.0,
            "burn_rate": 2.5,
            "thrust": 16000.0,
            "drag_coeff": 0.55,
            "area": 0.8,
            "air_density": 1.225,
            "g": 9.81,
            "dt": 0.05,
            "stop_time": 120.0,
        },
        "examples": [
            "生成一个火箭发射模型",
            "构建一维火箭垂直发射仿真，考虑推力和阻力",
            "build rocket launch dynamics model in matlab",
        ],
    },
]


def get_model_catalog() -> List[Dict]:
    return MATLAB_MODEL_KNOWLEDGE
