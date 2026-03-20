"""Family-level schema registry for structured generation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List

from knowledge_base.model_family_codegen import FAMILY_PARAMETER_DEFAULTS

def _slot_meta(label: str, unit: str, aliases: Iterable[str]) -> Dict[str, Any]:
    alias_items = [label, *aliases]
    deduped: List[str] = []
    seen = set()
    for item in alias_items:
        value = str(item or "").strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return {"label": label, "unit": unit, "aliases": deduped}


COMMON_SLOT_METADATA: Dict[str, Dict[str, Any]] = {
    "mass0": _slot_meta("初始总质量", "kg", ["mass0", "initial mass", "launch mass", "初始质量", "总质量", "发射质量"]),
    "fuel_mass": _slot_meta("燃料质量", "kg", ["fuel_mass", "fuel mass", "propellant mass", "燃料质量", "推进剂质量"]),
    "burn_rate": _slot_meta("燃烧速率", "kg/s", ["burn_rate", "burn rate", "mass flow rate", "燃烧速率", "燃料消耗速率"]),
    "thrust": _slot_meta("推力", "N", ["thrust", "engine thrust", "propulsive force", "推力", "发动机推力"]),
    "drag_coeff": _slot_meta("阻力系数", "-", ["drag_coeff", "drag coefficient", "Cd", "阻力系数"]),
    "area": _slot_meta("参考面积", "m^2", ["area", "reference area", "cross-sectional area", "参考面积", "截面积"]),
    "air_density": _slot_meta("空气密度", "kg/m^3", ["air_density", "air density", "空气密度", "大气密度"]),
    "water_density": _slot_meta("水密度", "kg/m^3", ["water_density", "water density", "水密度", "海水密度"]),
    "displaced_volume": _slot_meta("排水体积", "m^3", ["displaced_volume", "displaced volume", "排水体积", "排开体积"]),
    "g": _slot_meta("重力加速度", "m/s^2", ["g", "gravity", "重力加速度", "重力"]),
    "dt": _slot_meta("时间步长", "s", ["dt", "time step", "step size", "时间步长", "步长"]),
    "stop_time": _slot_meta("仿真时长", "s", ["stop_time", "stop time", "simulation time", "仿真时长", "仿真时间", "总时长"]),
    "launch_angle_deg": _slot_meta("发射角", "deg", ["launch_angle_deg", "launch angle", "发射角"]),
    "init_speed": _slot_meta("初始速度", "m/s", ["init_speed", "initial speed", "initial velocity", "初始速度", "初速度"]),
    "burn_time": _slot_meta("燃烧时间", "s", ["burn_time", "burn time", "燃烧时间"]),
    "init_flight_path_deg": _slot_meta("初始弹道倾角", "deg", ["init_flight_path_deg", "initial flight path angle", "初始弹道倾角"]),
    "pitch_end_deg": _slot_meta("俯仰程序结束角", "deg", ["pitch_end_deg", "pitch end angle", "俯仰程序结束角"]),
    "pitch_ramp_time": _slot_meta("俯仰程序过渡时间", "s", ["pitch_ramp_time", "pitch ramp time", "俯仰程序时间"]),
    "lift_to_drag": _slot_meta("升阻比", "-", ["lift_to_drag", "lift-to-drag", "L/D", "升阻比"]),
    "init_altitude": _slot_meta("初始高度", "m", ["init_altitude", "initial altitude", "初始高度", "再入高度", "altitude", "高度"]),
    "entry_angle_deg": _slot_meta("再入角", "deg", ["entry_angle_deg", "entry angle", "reentry angle", "再入角"]),
    "mass": _slot_meta("质量", "kg", ["mass", "vehicle mass", "质量", "本体质量"]),
    "lift_coeff": _slot_meta("升力系数", "-", ["lift_coeff", "lift coefficient", "Cl", "升力系数"]),
    "bank_angle_deg": _slot_meta("倾侧角", "deg", ["bank_angle_deg", "bank angle", "滚转角", "倾侧角"]),
    "climb_cmd_deg": _slot_meta("爬升指令角", "deg", ["climb_cmd_deg", "climb command angle", "爬升角指令"]),
    "missile_speed": _slot_meta("拦截器速度", "m/s", ["missile_speed", "interceptor speed", "拦截器速度", "导弹速度"]),
    "target_speed": _slot_meta("目标速度", "m/s", ["target_speed", "target speed", "目标速度"]),
    "target_heading_deg": _slot_meta("目标航向角", "deg", ["target_heading_deg", "target heading", "目标航向角"]),
    "nav_gain": _slot_meta("导航比", "-", ["nav_gain", "navigation gain", "PN gain", "导航比", "比例导引系数"]),
    "init_range": _slot_meta("初始距离", "m", ["init_range", "initial range", "初始距离"]),
    "init_los_deg": _slot_meta("初始视线角", "deg", ["init_los_deg", "initial LOS angle", "初始视线角"]),
    "target_depth": _slot_meta("目标深度", "m", ["target_depth", "target depth", "目标深度"]),
    "depth_gain": _slot_meta("深度控制增益", "-", ["depth_gain", "depth gain", "深度控制增益"]),
    "init_depth": _slot_meta("初始深度", "m", ["init_depth", "initial depth", "初始深度"]),
    "ballast_gain": _slot_meta("压载控制增益", "N/m", ["ballast_gain", "ballast gain", "压载增益"]),
    "altitude0": _slot_meta("初始轨道高度", "m", ["altitude0", "initial altitude", "orbit altitude", "初始轨道高度", "altitude", "高度", "轨道高度"]),
    "v0": _slot_meta("初始轨道速度", "m/s", ["v0", "initial orbital speed", "初始轨道速度"]),
    "mean_motion": _slot_meta("平均角速度", "rad/s", ["mean_motion", "mean motion", "平均角速度"]),
    "x0": _slot_meta("初始X位置", "m", ["x0", "initial x", "初始x", "初始X位置"]),
    "y0": _slot_meta("初始Y位置", "m", ["y0", "initial y", "初始y", "初始Y位置"]),
    "vx0": _slot_meta("初始X速度", "m/s", ["vx0", "initial vx", "初始vx", "初始X速度", "vx", "v_x", "初始横向速度"]),
    "vy0": _slot_meta("初始Y速度", "m/s", ["vy0", "initial vy", "初始vy", "初始Y速度", "vy", "v_y", "初始纵向速度"]),
    "transfer_dv": _slot_meta("变轨脉冲Δv", "m/s", ["transfer_dv", "delta v", "变轨脉冲", "脉冲增速"]),
    "transfer_burn_time": _slot_meta("脉冲时刻", "s", ["transfer_burn_time", "burn time", "impulse time", "脉冲时刻"]),
    "steps": _slot_meta("采样步数", "-", ["steps", "sample count", "步数", "采样步数"]),
    "process_noise": _slot_meta("过程噪声强度", "-", ["process_noise", "process noise", "system noise", "过程噪声", "状态噪声"]),
    "measurement_noise": _slot_meta("测量噪声强度", "-", ["measurement_noise", "measurement noise", "observation noise", "测量噪声", "观测噪声", "量测噪声"]),
    "target_speed_x": _slot_meta("目标X方向速度", "m/s", ["target_speed_x", "target vx", "目标x速度", "横向速度", "x向速度", "vx", "v_x", "目标横向速度", "目标x方向速度"]),
    "target_speed_y": _slot_meta("目标Y方向速度", "m/s", ["target_speed_y", "target vy", "目标y速度", "纵向速度", "y向速度", "vy", "v_y", "目标纵向速度", "目标y方向速度"]),
    "radar_noise": _slot_meta("雷达噪声强度", "-", ["radar_noise", "radar noise", "雷达噪声"]),
    "eo_noise": _slot_meta("光电噪声强度", "-", ["eo_noise", "electro-optical noise", "光电噪声"]),
    "bearing_noise": _slot_meta("方位角噪声强度", "rad", ["bearing_noise", "bearing noise", "方位角噪声"]),
    "sensor_x": _slot_meta("传感器X位置", "m", ["sensor_x", "sensor x", "传感器x位置"]),
    "sensor_y": _slot_meta("传感器Y位置", "m", ["sensor_y", "sensor y", "传感器y位置"]),
    "red0": _slot_meta("红方初始兵力", "-", ["red0", "red force", "red initial force", "红方兵力", "红方总兵力"]),
    "blue0": _slot_meta("蓝方初始兵力", "-", ["blue0", "blue force", "blue initial force", "蓝方兵力", "蓝方总兵力"]),
    "alpha": _slot_meta("红方杀伤率系数", "-", ["alpha", "red attrition coefficient", "red kill coefficient", "红方杀伤系数", "红方杀伤率"]),
    "beta": _slot_meta("蓝方杀伤率系数", "-", ["beta", "blue attrition coefficient", "blue kill coefficient", "蓝方杀伤系数", "蓝方杀伤率"]),
    "coverage0": _slot_meta("初始覆盖度", "-", ["coverage0", "initial coverage", "sensor coverage", "recon coverage", "初始覆盖度", "侦察覆盖"]),
    "feed0": _slot_meta("初始情报供给", "-", ["feed0", "initial feed", "intel feed", "recon feed", "情报供给", "情报输入"]),
    "decay_rate": _slot_meta("衰减率", "1/s", ["decay_rate", "decay rate", "coverage decay", "衰减率", "覆盖衰减", "感知衰减"]),
    "fusion_gain": _slot_meta("融合增益", "-", ["fusion_gain", "fusion gain", "information fusion gain", "融合增益", "信息融合增益", "态势融合增益"]),
    "proximity0": _slot_meta("初始接近度代理", "-", ["proximity0", "initial proximity", "初始接近度"]),
    "closing_rate": _slot_meta("接近速率", "1/s", ["closing_rate", "closing rate", "接近速率"]),
    "intent_weight": _slot_meta("意图权重", "-", ["intent_weight", "intent weight", "意图权重"]),
    "asset_value": _slot_meta("资产价值权重", "-", ["asset_value", "asset value", "资产价值"]),
    "lethality_weight": _slot_meta("毁伤权重", "-", ["lethality_weight", "lethality weight", "毁伤权重"]),
    "red_salvo0": _slot_meta("来袭齐射初始规模", "-", ["red_salvo0", "initial raid size", "初始齐射规模"]),
    "blue_interceptors0": _slot_meta("拦截弹初始库存", "-", ["blue_interceptors0", "initial interceptor inventory", "拦截弹库存"]),
    "raid_size": _slot_meta("来袭速率", "1/s", ["raid_size", "raid size rate", "来袭速率"]),
    "p_kill": _slot_meta("单发杀伤概率", "-", ["p_kill", "probability of kill", "单发杀伤概率"]),
    "interceptor_regen": _slot_meta("拦截器补充速率", "1/s", ["interceptor_regen", "interceptor regeneration", "补充速率"]),
}


def _ordered_unique(values: Iterable[str]) -> List[str]:
    ordered: List[str] = []
    seen: set[str] = set()
    for item in values:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _family_schema(
    display_name: str,
    scene: str,
    *,
    identify_slots: Iterable[str] = (),
    critical_slots: Iterable[str] = (),
    defaultable_slots: Iterable[str] = (),
    required_outputs: Iterable[str] = ("plot",),
    assumptions: Iterable[str] = (),
) -> Dict[str, Any]:
    return {
        "display_name": display_name,
        "scene": scene,
        "identify_slots": _ordered_unique(identify_slots),
        "critical_slots": _ordered_unique(critical_slots),
        "defaultable_slots": _ordered_unique(defaultable_slots),
        "required_outputs": list(required_outputs),
        "assumptions": list(assumptions),
    }


FAMILY_SCHEMA_BLUEPRINTS: Dict[str, Dict[str, Any]] = {
    "launch_dynamics": _family_schema("一维垂直发射", "火箭 / 导弹一维垂直发射动力学", identify_slots=["fuel_mass", "burn_rate"], critical_slots=["mass0", "fuel_mass", "thrust"], defaultable_slots=["burn_rate", "drag_coeff", "area", "stop_time", "dt"], required_outputs=["plot", "altitude", "velocity", "acceleration"], assumptions=["沿垂直方向一维运动", "可按默认大气与重力常数建模"]),
    "trajectory_ode": _family_schema("二维弹道 / 飞行动力学", "二维平面飞行、弹道或导弹轨迹", identify_slots=["launch_angle_deg", "init_speed"], critical_slots=["mass0", "thrust", "launch_angle_deg", "init_speed"], defaultable_slots=["drag_coeff", "burn_time", "stop_time", "dt"], required_outputs=["plot", "trajectory", "velocity"], assumptions=["平面二维运动", "忽略姿态高阶耦合"]),
    "powered_ascent": _family_schema("动力上升段", "带俯仰程序的动力上升段轨迹", identify_slots=["pitch_end_deg", "pitch_ramp_time"], critical_slots=["mass0", "fuel_mass", "thrust", "pitch_end_deg"], defaultable_slots=["burn_rate", "init_flight_path_deg", "pitch_ramp_time", "stop_time", "dt"], required_outputs=["plot", "trajectory", "mass", "speed"], assumptions=["采用程序俯仰近似", "可按默认阻力与重力建模"]),
    "reentry_dynamics": _family_schema("再入动力学", "再入段轨迹、气动减速与热流代理", identify_slots=["entry_angle_deg", "lift_to_drag"], critical_slots=["mass0", "init_altitude", "init_speed", "entry_angle_deg"], defaultable_slots=["drag_coeff", "area", "lift_to_drag", "stop_time", "dt"], required_outputs=["plot", "trajectory", "heat_load"], assumptions=["采用指数大气模型", "热流为工程代理量"]),
    "aircraft_point_mass": _family_schema("飞机质点模型", "飞机质点运动、爬升和转弯", identify_slots=["climb_cmd_deg", "bank_angle_deg"], critical_slots=["mass", "thrust", "init_speed", "init_altitude"], defaultable_slots=["lift_coeff", "bank_angle_deg", "climb_cmd_deg", "stop_time", "dt"], required_outputs=["plot", "trajectory", "speed", "heading"], assumptions=["采用质点模型", "忽略姿态与控制面细节"]),
    "interceptor_guidance": _family_schema("拦截制导", "拦截器-目标二维相对运动与比例导引", identify_slots=["nav_gain", "init_los_deg"], critical_slots=["missile_speed", "target_speed", "init_range", "nav_gain"], defaultable_slots=["target_heading_deg", "init_los_deg", "stop_time", "dt"], required_outputs=["plot", "intercept_geometry", "miss_distance"], assumptions=["目标匀速运动", "采用比例导引近似"]),
    "underwater_launch": _family_schema("水下发射", "水下管内 / 出管一维发射动力学", identify_slots=["displaced_volume", "water_density"], critical_slots=["mass", "thrust", "displaced_volume"], defaultable_slots=["drag_coeff", "area", "water_density", "stop_time", "dt"], required_outputs=["plot", "displacement", "velocity", "acceleration"], assumptions=["一维轴向运动", "可考虑浮力、阻力与重力"]),
    "underwater_cruise": _family_schema("水下巡航", "水下航行体巡航与深度保持", identify_slots=["target_depth", "depth_gain"], critical_slots=["mass", "thrust", "target_depth", "init_speed"], defaultable_slots=["depth_gain", "drag_coeff", "init_depth", "stop_time", "dt"], required_outputs=["plot", "range", "depth", "speed"], assumptions=["采用二维深度-航程近似", "深度指令由简化增益控制"]),
    "submarine_depth_control": _family_schema("潜艇深度控制", "潜艇纵向深度控制与压载调节", identify_slots=["target_depth", "ballast_gain"], critical_slots=["mass", "target_depth", "ballast_gain"], defaultable_slots=["drag_coeff", "displaced_volume", "stop_time", "dt"], required_outputs=["plot", "depth", "vertical_speed", "ballast_force"], assumptions=["采用纵向一维模型", "压载调节作为等效控制力"]),
    "orbital_dynamics": _family_schema("二体轨道动力学", "地心平面二体轨道传播", identify_slots=["altitude0", "v0"], critical_slots=["altitude0", "v0"], defaultable_slots=["stop_time", "dt"], required_outputs=["plot", "orbit", "altitude"], assumptions=["采用平面二体模型", "忽略J2与摄动"]),
    "relative_orbit": _family_schema("相对轨道", "近圆轨道编队相对运动", identify_slots=["x0", "y0", "mean_motion"], critical_slots=["x0", "y0", "vx0", "vy0"], defaultable_slots=["mean_motion", "stop_time", "dt"], required_outputs=["plot", "relative_motion", "relative_distance"], assumptions=["采用CW线性相对运动方程", "适用于近圆参考轨道"]),
    "orbit_transfer": _family_schema("脉冲变轨", "脉冲变轨与轨道能量变化", identify_slots=["transfer_dv", "transfer_burn_time"], critical_slots=["altitude0", "v0", "transfer_dv", "transfer_burn_time"], defaultable_slots=["stop_time", "dt"], required_outputs=["plot", "orbit_transfer", "specific_energy"], assumptions=["变轨脉冲视为瞬时作用", "轨道传播采用平面二体近似"]),
    "tracking_estimation": _family_schema("卡尔曼目标跟踪", "单传感器二维目标跟踪与估计", identify_slots=["measurement_noise", "process_noise"], critical_slots=["measurement_noise", "target_speed_x", "target_speed_y"], defaultable_slots=["process_noise", "steps", "dt", "x0", "y0"], required_outputs=["plot", "truth", "measurement", "estimate", "position_error"], assumptions=["采用常速度目标模型", "采用线性卡尔曼滤波"]),
    "sensor_fusion_tracking": _family_schema("多传感器融合跟踪", "雷达 / 光电等多源观测融合跟踪", identify_slots=["radar_noise", "eo_noise"], critical_slots=["radar_noise", "eo_noise", "target_speed_x", "target_speed_y"], defaultable_slots=["process_noise", "steps", "dt", "x0", "y0"], required_outputs=["plot", "radar_measurement", "eo_measurement", "estimate"], assumptions=["采用顺序融合更新", "多传感器在同一参考坐标系下工作"]),
    "bearing_only_tracking": _family_schema("纯方位跟踪", "纯方位观测目标跟踪与EKF估计", identify_slots=["bearing_noise", "sensor_x", "sensor_y"], critical_slots=["sensor_x", "sensor_y", "bearing_noise"], defaultable_slots=["target_speed_x", "target_speed_y", "steps", "dt", "x0", "y0"], required_outputs=["plot", "bearing", "estimate", "position_error"], assumptions=["采用扩展卡尔曼滤波", "观测为纯方位角"]),
    "combat_attrition": _family_schema("兵力消耗", "兰彻斯特平方律对抗消耗", identify_slots=["alpha", "beta"], critical_slots=["red0", "blue0", "alpha", "beta"], defaultable_slots=["stop_time", "dt"], required_outputs=["plot", "force_levels", "phase_portrait"], assumptions=["采用连续消耗模型", "杀伤系数在窗口内视为常数"]),
    "battlefield_awareness": _family_schema("战场态势感知", "覆盖度、情报供给与态势感知融合", identify_slots=["coverage0", "feed0"], critical_slots=["coverage0", "feed0"], defaultable_slots=["decay_rate", "fusion_gain", "stop_time", "dt"], required_outputs=["plot", "coverage", "awareness"], assumptions=["态势感知以覆盖与情报融合代理"]),
    "threat_assessment": _family_schema("威胁评估", "接近度、意图与资产价值驱动的威胁评估", identify_slots=["closing_rate", "asset_value"], critical_slots=["proximity0", "closing_rate", "asset_value"], defaultable_slots=["intent_weight", "lethality_weight", "stop_time", "dt"], required_outputs=["plot", "threat_score", "intent"], assumptions=["威胁分数为工程评估代理量"]),
    "salvo_engagement": _family_schema("齐射拦截交战", "齐射来袭与拦截弹库存交换", identify_slots=["p_kill", "blue_interceptors0"], critical_slots=["red_salvo0", "blue_interceptors0", "p_kill"], defaultable_slots=["raid_size", "interceptor_regen", "stop_time", "dt"], required_outputs=["plot", "intercepted", "leakers", "inventory"], assumptions=["交战结果由齐射交换与漏网代理表示"]),
}


def _fallback_slot_meta(slot_name: str) -> Dict[str, Any]:
    label = slot_name.replace("_", " ").strip().title() or slot_name
    aliases = [slot_name, slot_name.replace("_", " ")]
    return _slot_meta(label, "-", aliases)


def _slot_roles(slot_name: str, blueprint: Dict[str, Any]) -> List[str]:
    roles: List[str] = []
    if slot_name in blueprint.get("identify_slots", []):
        roles.append("identify")
    if slot_name in blueprint.get("critical_slots", []):
        roles.append("critical")
    if slot_name in blueprint.get("defaultable_slots", []):
        roles.append("defaultable")
    return roles or ["optional"]


def _clarify_priority(roles: Iterable[str]) -> int:
    ordered_roles = list(roles)
    if "identify" in ordered_roles:
        return 0
    if "critical" in ordered_roles:
        return 1
    if "defaultable" in ordered_roles:
        return 2
    return 3


def _normalize_blueprint(blueprint: Dict[str, Any]) -> Dict[str, Any]:
    identify_slots = _ordered_unique(blueprint.get("identify_slots", []))
    critical_slots = _ordered_unique(blueprint.get("critical_slots", blueprint.get("required_slots", [])))
    defaultable_slots = _ordered_unique(blueprint.get("defaultable_slots", blueprint.get("recommended_slots", [])))
    return {
        "display_name": blueprint.get("display_name", ""),
        "scene": blueprint.get("scene", ""),
        "identify_slots": identify_slots,
        "critical_slots": critical_slots,
        "defaultable_slots": defaultable_slots,
        "all_slots": _ordered_unique([*identify_slots, *critical_slots, *defaultable_slots]),
        "required_slots": list(critical_slots),
        "recommended_slots": list(defaultable_slots),
        "assumptions": list(blueprint.get("assumptions", [])),
        "required_outputs": list(blueprint.get("required_outputs", ["plot"])),
    }


def _build_family_slot_defs(family: str, blueprint: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    ordered_keys = list(blueprint.get("all_slots", []))
    for key in FAMILY_PARAMETER_DEFAULTS.get(family, {}).keys():
        if key not in ordered_keys:
            ordered_keys.append(key)
    slot_defs: Dict[str, Dict[str, Any]] = {}
    for key in ordered_keys:
        slot_meta = deepcopy(COMMON_SLOT_METADATA.get(key, _fallback_slot_meta(key)))
        roles = _slot_roles(key, blueprint)
        slot_meta.update(
            {
                "collection_roles": roles,
                "clarify_priority": _clarify_priority(roles),
                "is_identify_slot": "identify" in roles,
                "is_critical_slot": "critical" in roles,
                "is_defaultable_slot": "defaultable" in roles,
            }
        )
        slot_defs[key] = slot_meta
    return slot_defs


SLOT_SCHEMAS: Dict[str, Dict[str, Any]] = {}
for _family_name, _blueprint in FAMILY_SCHEMA_BLUEPRINTS.items():
    _normalized_blueprint = _normalize_blueprint(_blueprint)
    _normalized_blueprint["display_name"] = _normalized_blueprint.get("display_name", _family_name) or _family_name
    _normalized_blueprint["slot_defs"] = _build_family_slot_defs(_family_name, _normalized_blueprint)
    SLOT_SCHEMAS[_family_name] = _normalized_blueprint

class FamilySchemaRegistry:
    """Registry facade for family-level structured generation schemas."""

    def __init__(self, model_lookup: Dict[str, Dict[str, Any]] | None = None):
        self.model_lookup = model_lookup or {}

    def bind_model_lookup(self, model_lookup: Dict[str, Dict[str, Any]]) -> None:
        self.model_lookup = model_lookup or {}

    def supports_family(self, family: str) -> bool:
        return family in SLOT_SCHEMAS

    def get_schema(self, family: str) -> Dict[str, Any]:
        return SLOT_SCHEMAS.get(family, {})

    def get_slot_defs(self, family: str) -> Dict[str, Dict[str, Any]]:
        return self.get_schema(family).get("slot_defs", {})

    def identify_slots(self, family: str) -> List[str]:
        return list(self.get_schema(family).get("identify_slots", []))

    def critical_slots(self, family: str) -> List[str]:
        schema = self.get_schema(family)
        return list(schema.get("critical_slots", schema.get("required_slots", [])))

    def defaultable_slots(self, family: str) -> List[str]:
        schema = self.get_schema(family)
        return list(schema.get("defaultable_slots", schema.get("recommended_slots", [])))

    def summarize_slot_collection(
        self,
        family: str,
        collected_slots: Dict[str, Any] | None,
        defaults: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        collected_keys = set((collected_slots or {}).keys())
        identify_slots = self.identify_slots(family)
        critical_slots = self.critical_slots(family)
        defaultable_slots = self.defaultable_slots(family)
        missing_identify_slots = [slot for slot in identify_slots if slot not in collected_keys]
        missing_critical_slots = [slot for slot in critical_slots if slot not in collected_keys]
        missing_defaultable_slots = [slot for slot in defaultable_slots if slot not in collected_keys]
        default_values = defaults or {}
        defaultable_with_defaults = [slot for slot in missing_defaultable_slots if slot in default_values]
        defaultable_without_defaults = [slot for slot in missing_defaultable_slots if slot not in default_values]
        active_missing_slots = list(missing_critical_slots or missing_defaultable_slots)
        unresolved_slots = _ordered_unique([*missing_critical_slots, *missing_defaultable_slots])
        collection_stage = "ready"
        if missing_critical_slots:
            collection_stage = "critical"
        elif missing_defaultable_slots:
            collection_stage = "defaultable"
        return {
            "identify_slots": identify_slots,
            "critical_slots": critical_slots,
            "defaultable_slots": defaultable_slots,
            "missing_identify_slots": missing_identify_slots,
            "missing_critical_slots": missing_critical_slots,
            "missing_defaultable_slots": missing_defaultable_slots,
            "defaultable_slots_with_defaults": defaultable_with_defaults,
            "defaultable_slots_without_defaults": defaultable_without_defaults,
            "active_missing_slots": active_missing_slots,
            "unresolved_slots": unresolved_slots,
            "collection_stage": collection_stage,
            "status": "ready" if not unresolved_slots else "collecting",
            "required_slots": list(critical_slots),
            "recommended_slots": list(defaultable_slots),
        }

    def display_name(self, family: str) -> str:
        return str(self.get_schema(family).get("display_name", family or "未知模型族"))

    def resolve_family(
        self,
        model_or_family: str = "",
        model_id: str = "",
        family_hint: str = "",
        model_lookup: Dict[str, Dict[str, Any]] | None = None,
    ) -> str:
        lookup = model_lookup if model_lookup is not None else self.model_lookup
        direct = str(model_or_family or family_hint or "").strip()
        if direct in SLOT_SCHEMAS:
            return direct
        candidate_model_id = str(model_id or model_or_family or "").strip()
        if candidate_model_id:
            return str(lookup.get(candidate_model_id, {}).get("template_family", "")).strip()
        return ""

    def resolve_generation_family(
        self,
        generation_ir: Dict[str, Any],
        model_lookup: Dict[str, Dict[str, Any]] | None = None,
    ) -> str:
        if not isinstance(generation_ir, dict):
            return ""
        lookup = model_lookup if model_lookup is not None else self.model_lookup
        candidates = [
            generation_ir.get("schema_family"),
            generation_ir.get("slot_collection", {}).get("schema_family")
            if isinstance(generation_ir.get("slot_collection"), dict)
            else "",
            generation_ir.get("codegen", {}).get("template_family")
            if isinstance(generation_ir.get("codegen"), dict)
            else "",
            generation_ir.get("domain", {}).get("model_family")
            if isinstance(generation_ir.get("domain"), dict)
            else "",
            self.resolve_family(model_id=str(generation_ir.get("model_id", "")).strip(), model_lookup=lookup),
        ]
        for candidate in candidates:
            family = str(candidate or "").strip()
            if family:
                return family
        return ""


__all__ = [
    "COMMON_SLOT_METADATA",
    "FAMILY_SCHEMA_BLUEPRINTS",
    "FamilySchemaRegistry",
    "SLOT_SCHEMAS",
]
