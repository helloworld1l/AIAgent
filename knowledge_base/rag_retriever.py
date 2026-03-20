"""
Hybrid RAG retriever for MATLAB modeling knowledge.

Pipeline:
1) BM25 lexical recall
2) Vector recall (Qdrant preferred, local embedding fallback)
3) Rule-based rerank and score fusion
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import requests

from agents.structured_generation.schema_registry import SLOT_SCHEMAS
from config.settings import settings
from knowledge_base.document_loader import DEFAULT_DOCS_DIR, load_file_documents
from knowledge_base.matlab_model_data import get_model_catalog
from knowledge_base.model_family_codegen import FAMILY_LIBRARY

logger = logging.getLogger(__name__)

TRACE_CLARIFY_STAGE_OBJECT = "object"
TRACE_CLARIFY_STAGE_FAMILY = "family"
TRACE_CLARIFY_STAGE_READY = "ready"
TRACE_OBJECT_REASONS = {
    "military_equipment_needs_object",
    "battlefield_situation_needs_object",
    "out_of_scope",
}

DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "aerospace": [
        "aerospace", "rocket", "rocket launch", "launch dynamics", "vertical launch", "propulsion",
        "burn rate", "fuel mass", "mass depletion", "thrust-to-weight ratio",
        "航空航天", "运载火箭", "火箭发射", "垂直发射", "升空", "推进剂", "燃料质量", "燃烧速率", "质量递减", "推重比",
    ],
    "underwater": [
        "torpedo", "submarine", "underwater", "underwater launch", "tube launch", "buoyancy",
        "water drag", "displaced volume", "hydrodynamic", "naval weapon",
        "鱼雷", "潜艇", "水下", "水下发射", "出管", "浮力", "水阻", "排水体积", "水下推进", "水中阻力",
    ],
    "missile": [
        "missile", "interceptor", "trajectory", "flight dynamics", "launch angle", "boost phase",
        "planar trajectory", "ballistic trajectory", "intercept trajectory",
        "导弹", "拦截弹", "飞行轨迹", "二维弹道", "发射角", "仰角", "推进段", "弹道", "末制导", "射程",
    ],
    "space": [
        "satellite", "orbit", "orbital", "spacecraft", "two-body", "orbital dynamics",
        "low earth orbit", "gravitational parameter", "perigee", "apogee", "orbital period",
        "卫星", "轨道", "轨道传播", "二体", "航天器", "近地轨道", "引力参数", "近地点", "远地点", "轨道周期", "轨道高度",
    ],
    "military_equipment": [
        "military equipment", "weapon platform", "fire control", "guidance", "torpedo launch",
        "missile flight", "radar tracking",
        "军工装备", "武器平台", "火控", "制导", "鱼雷发射", "导弹飞行", "雷达跟踪", "装备建模",
    ],
    "radar_tracking": [
        "radar", "tracking", "target tracking", "kalman", "surveillance", "measurement noise",
        "process noise", "track estimation", "target trajectory",
        "雷达", "目标跟踪", "航迹", "卡尔曼滤波", "观测噪声", "过程噪声", "跟踪估计", "探测", "预警", "测量误差",
    ],
    "battlefield_situation": [
        "battlefield situation", "situation awareness", "warning", "reconnaissance", "target discovery",
        "awareness", "coverage", "fusion", "threat assessment", "threat score",
        "战场态势", "态势感知", "预警", "侦察", "目标发现", "敌我态势", "战场感知",
    ],
    "battlefield": [
        "battlefield", "attrition", "lanchester", "red blue", "combat", "battle damage",
        "force comparison", "combat effectiveness", "salvo", "leaker", "raid", "interceptor inventory",
        "threat", "threat assessment", "threat score", "awareness", "coverage",
        "战场", "红蓝对抗", "兵力消耗", "战损", "兰彻斯特", "作战效能", "力量对比", "消耗模型",
    ],
}

QUERY_DOMAIN_PARENT_DOMAINS: set[str] = {
    "aerospace",
    "military_equipment",
    "battlefield_situation",
}

QUERY_DOMAIN_KEYWORD_BUCKETS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "aerospace": {
        "object": ("rocket", "\u8fd0\u8f7d\u706b\u7bad"),
        "scene": (
            "rocket launch", "launch dynamics", "vertical launch", "propulsion",
            "burn rate", "fuel mass", "mass depletion", "thrust-to-weight ratio",
            "\u706b\u7bad\u53d1\u5c04", "\u5782\u76f4\u53d1\u5c04", "\u5347\u7a7a", "\u63a8\u8fdb\u5242",
            "\u71c3\u6599\u8d28\u91cf", "\u71c3\u70e7\u901f\u7387", "\u8d28\u91cf\u9012\u51cf", "\u63a8\u91cd\u6bd4",
        ),
        "noise": ("aerospace", "\u822a\u7a7a\u822a\u5929"),
    },
    "underwater": {
        "object": ("torpedo", "submarine", "\u9c7c\u96f7", "\u6f5c\u8247"),
        "scene": (
            "underwater", "underwater launch", "tube launch", "buoyancy", "water drag",
            "displaced volume", "hydrodynamic", "naval weapon",
            "\u6c34\u4e0b", "\u6c34\u4e0b\u53d1\u5c04", "\u51fa\u7ba1", "\u6d6e\u529b", "\u6c34\u963b",
            "\u6392\u6c34\u4f53\u79ef", "\u6c34\u4e0b\u63a8\u8fdb", "\u6c34\u4e2d\u963b\u529b",
        ),
    },
    "missile": {
        "object": ("missile", "interceptor", "\u5bfc\u5f39", "\u62e6\u622a\u5f39"),
        "scene": (
            "trajectory", "flight dynamics", "launch angle", "boost phase", "planar trajectory",
            "ballistic trajectory", "intercept trajectory",
            "\u98de\u884c\u8f68\u8ff9", "\u4e8c\u7ef4\u5f39\u9053", "\u53d1\u5c04\u89d2", "\u4ef0\u89d2",
            "\u63a8\u8fdb\u6bb5", "\u5f39\u9053", "\u672b\u5236\u5bfc", "\u5c04\u7a0b",
        ),
    },
    "space": {
        "object": ("satellite", "spacecraft", "\u536b\u661f", "\u822a\u5929\u5668"),
        "scene": (
            "orbit", "orbital", "orbit propagation", "two-body", "orbital dynamics",
            "low earth orbit", "gravitational parameter", "perigee", "apogee", "orbital period",
            "\u8f68\u9053", "\u8f68\u9053\u4f20\u64ad", "\u4e8c\u4f53", "\u8fd1\u5730\u8f68\u9053",
            "\u5f15\u529b\u53c2\u6570", "\u8fd1\u5730\u70b9", "\u8fdc\u5730\u70b9", "\u8f68\u9053\u5468\u671f", "\u8f68\u9053\u9ad8\u5ea6",
        ),
    },
    "military_equipment": {
        "noise": (
            "military equipment", "weapon platform", "fire control", "guidance",
            "torpedo launch", "missile flight", "radar tracking",
            "\u519b\u5de5\u88c5\u5907", "\u6b66\u5668\u5e73\u53f0", "\u706b\u63a7", "\u5236\u5bfc",
            "\u9c7c\u96f7\u53d1\u5c04", "\u5bfc\u5f39\u98de\u884c", "\u96f7\u8fbe\u8ddf\u8e2a", "\u88c5\u5907\u5efa\u6a21",
        ),
    },
    "radar_tracking": {
        "object": (
            "radar", "radar tracking", "target tracking", "tracking",
            "\u96f7\u8fbe", "\u96f7\u8fbe\u8ddf\u8e2a", "\u76ee\u6807\u8ddf\u8e2a",
        ),
        "scene": (
            "kalman", "kalman filter", "surveillance", "measurement noise", "process noise",
            "track estimation", "target trajectory",
            "\u5361\u5c14\u66fc", "\u5361\u5c14\u66fc\u6ee4\u6ce2", "\u822a\u8ff9", "\u89c2\u6d4b\u566a\u58f0",
            "\u8fc7\u7a0b\u566a\u58f0", "\u8ddf\u8e2a\u4f30\u8ba1", "\u63a2\u6d4b", "\u6d4b\u91cf\u8bef\u5dee",
        ),
        "noise": ("\u9884\u8b66",),
    },
    "battlefield_situation": {
        "object": (
            "situation awareness", "reconnaissance", "target discovery", "battlefield awareness",
            "\u6001\u52bf\u611f\u77e5", "\u4fa6\u5bdf", "\u76ee\u6807\u53d1\u73b0", "\u6218\u573a\u611f\u77e5",
        ),
        "scene": (
            "warning", "coverage", "fusion", "threat assessment", "threat score",
            "\u9884\u8b66", "\u654c\u6211\u6001\u52bf",
        ),
        "noise": ("battlefield situation", "awareness", "\u6218\u573a\u6001\u52bf"),
    },
    "battlefield": {
        "object": (
            "attrition", "red blue", "combat", "battle damage", "force comparison", "combat effectiveness",
            "\u5175\u529b\u6d88\u8017", "\u7ea2\u84dd\u5bf9\u6297", "\u6218\u635f", "\u529b\u91cf\u5bf9\u6bd4", "\u4f5c\u6218\u6548\u80fd",
        ),
        "scene": (
            "lanchester", "salvo", "leaker", "raid", "interceptor inventory",
            "\u5170\u5f7b\u65af\u7279", "\u6d88\u8017\u6a21\u578b",
        ),
        "noise": (
            "battlefield", "threat", "threat assessment", "threat score", "awareness", "coverage",
            "\u6218\u573a",
        ),
    },
}

DOMAIN_TAG_HINTS: Dict[str, set[str]] = {
    "aerospace": {"aerospace", "propulsion", "launch_dynamics", "flight_dynamics", "orbital_dynamics", "space", "spacecraft", "orbit"},
    "underwater": {"underwater", "naval_weapon", "launch_dynamics", "military_equipment"},
    "missile": {"missile", "flight_dynamics", "trajectory_ode", "aerospace"},
    "space": {"space", "orbit", "spacecraft", "orbital_dynamics", "aerospace"},
    "military_equipment": {"military_equipment", "naval_weapon", "underwater", "missile", "radar", "tracking", "tracking_estimation"},
    "radar_tracking": {"radar", "tracking", "tracking_estimation", "battlefield_situation", "military_equipment"},
    "battlefield_situation": {"battlefield", "battlefield_situation", "combat", "force_comparison", "military_analysis", "combat_attrition", "battlefield_awareness", "threat_assessment", "salvo_engagement", "tracking", "radar"},
    "battlefield": {"battlefield", "battlefield_situation", "combat", "force_comparison", "military_analysis", "combat_attrition", "battlefield_awareness", "threat_assessment", "salvo_engagement"},
}

DOMAIN_LABELS: Dict[str, str] = {
    "aerospace": "航空航天",
    "underwater": "水下发射",
    "missile": "导弹轨迹",
    "space": "轨道航天",
    "military_equipment": "军工装备",
    "radar_tracking": "雷达跟踪",
    "battlefield_situation": "战场态势",
    "battlefield": "战场对抗",
}

DOMAIN_PRIORITY: Dict[str, int] = {
    "underwater": 8,
    "radar_tracking": 8,
    "space": 7,
    "missile": 7,
    "battlefield": 7,
    "aerospace": 5,
    "military_equipment": 4,
    "battlefield_situation": 4,
}

DOMAIN_FAMILY_DOMAIN_HINTS: Dict[str, set[str]] = {
    "aerospace": {"aerospace"},
    "underwater": {"underwater"},
    "missile": {"aerospace"},
    "space": {"orbital"},
    "military_equipment": {"aerospace", "underwater", "tracking", "battlefield", "orbital"},
    "radar_tracking": {"tracking"},
    "battlefield_situation": {"battlefield", "tracking"},
    "battlefield": {"battlefield", "tracking"},
}

FAMILY_ACCEPTANCE_OVERRIDES: Dict[str, str] = {
    "aircraft_point_mass": "trajectory_ode",
    "interceptor_guidance": "trajectory_ode",
    "submarine_depth_control": "underwater_launch",
}

FAMILY_OBJECT_HINTS: Dict[str, List[str]] = {
    "launch_dynamics": ["rocket", "火箭", "vertical launch", "垂直发射", "1d launch", "vertical ascent", "导弹发射", "一维垂直发射"],
    "trajectory_ode": ["missile", "导弹", "2d trajectory", "planar trajectory", "launch angle", "拦截", "弹道", "二维弹道"],
    "powered_ascent": ["launch vehicle", "boost phase", "program pitch", "上升段", "运载火箭"],
    "reentry_dynamics": ["reentry vehicle", "warhead", "hypersonic glide", "再入段", "热流"],
    "aircraft_point_mass": ["aircraft", "UAV", "fighter", "climb turn", "飞机质点"],
    "interceptor_guidance": ["interceptor", "拦截", "制导", "target", "proportional navigation", "末制导", "拦截几何"],
    "underwater_launch": ["torpedo", "underwater launch", "tube ejection", "buoyancy", "水下出管"],
    "underwater_cruise": ["torpedo", "AUV", "underwater vehicle", "cruise", "深度保持"],
    "submarine_depth_control": ["submarine", "ballast", "depth keeping", "潜深控制", "纵向运动"],
    "orbital_dynamics": ["satellite", "卫星", "orbit propagation", "轨道", "on-orbit", "two-body", "二体轨道"],
    "relative_orbit": ["formation flying", "deputy satellite", "chief-deputy", "relative motion", "编队飞行"],
    "orbit_transfer": ["transfer orbit", "impulsive burn", "Hohmann", "变轨", "轨道能量"],
    "tracking_estimation": ["radar target", "single-target tracking", "kalman filter", "track estimation", "航迹跟踪"],
    "sensor_fusion_tracking": ["multi-sensor", "radar", "EO/IR", "fusion tracking", "传感器融合"],
    "bearing_only_tracking": ["bearing-only", "passive sensor", "azimuth", "EKF", "纯方位"],
    "combat_attrition": ["red-blue forces", "force attrition", "lanchester", "kill coefficient", "兵力消耗"],
    "battlefield_awareness": ["situation awareness", "coverage fusion", "recon feed", "warning picture", "态势感知"],
    "threat_assessment": ["threat", "closing target", "asset defense", "intent", "威胁评分"],
    "salvo_engagement": ["salvo", "interceptor inventory", "leakers", "防空拦截", "齐射交战"],
}

DOMAIN_COMBINATION_HINTS: List[Tuple[Tuple[str, ...], str]] = [
    (("underwater", "missile"), "当前请求同时包含水下发射和导弹轨迹线索，请先明确介质环境是水下还是空气中，这会直接决定是鱼雷模型还是导弹模型。"),
    (("underwater", "aerospace"), "当前请求同时包含水下与航空航天线索，请先明确对象是鱼雷/潜艇水下发射，还是火箭/导弹空中发射。"),
    (("missile", "space"), "当前请求同时包含导弹飞行和轨道航天线索，请先明确对象是导弹飞行段，还是卫星/航天器轨道传播。"),
    (("battlefield", "radar_tracking"), "当前请求同时包含战场对抗和雷达跟踪线索，请先明确是单目标雷达跟踪，还是战场层态势感知/预警问题。"),
    (("battlefield_situation", "military_equipment"), "当前请求同时包含军工装备和战场态势线索，请先明确主目标是单平台动力学，还是战场层兵力/态势建模。"),
]

DOMAIN_CLARIFY_HINTS: Dict[str, str] = {
    "aerospace": "\u8bf7\u660e\u786e\u5bf9\u8c61\u662f\u706b\u7bad\u3001\u5bfc\u5f39\u3001\u536b\u661f\u8fd8\u662f\u822a\u5929\u5668\uff0c\u5e76\u8865\u5145\u4ecb\u8d28\u73af\u5883\uff08\u5927\u6c14\u5c42\u5185\u6216\u8f68\u9053\u7a7a\u95f4\uff09\u4ee5\u53ca\u8d28\u91cf\u3001\u63a8\u529b\u3001\u8f68\u9053\u9ad8\u5ea6\u7b49\u5173\u952e\u53c2\u6570\u3002",
    "underwater": "\u8bf7\u660e\u786e\u5bf9\u8c61\u662f\u9c7c\u96f7\u8fd8\u662f\u6f5c\u8247\u6c34\u4e0b\u53d1\u5c04\uff0c\u5e76\u8865\u5145\u8d28\u91cf\u3001\u63a8\u529b\u3001\u963b\u529b\u7cfb\u6570\u3001\u6392\u6c34\u4f53\u79ef\u7b49\u5173\u952e\u53c2\u6570\u3002",
    "missile": "\u8bf7\u660e\u786e\u5bf9\u8c61\u662f\u5bfc\u5f39\u3001\u62e6\u622a\u5f39\u8fd8\u662f\u4e00\u822c\u98de\u884c\u8f68\u8ff9\u95ee\u9898\uff0c\u5e76\u8865\u5145\u8d28\u91cf\u3001\u63a8\u529b\u3001\u53d1\u5c04\u89d2\u3001\u521d\u901f\u5ea6\u3001\u63a8\u8fdb\u65f6\u95f4\u7b49\u53c2\u6570\u3002",
    "space": "\u8bf7\u660e\u786e\u662f\u536b\u661f\u8f68\u9053\u3001\u5728\u8f68\u673a\u52a8\u8fd8\u662f\u4e00\u822c\u822a\u5929\u98de\u884c\uff0c\u5e76\u8865\u5145\u8f68\u9053\u9ad8\u5ea6\u3001\u521d\u901f\u5ea6\u3001\u5f15\u529b\u53c2\u6570\u3001\u4eff\u771f\u65f6\u957f\u7b49\u53c2\u6570\u3002",
    "military_equipment": "\u8bf7\u660e\u786e\u88c5\u5907\u5bf9\u8c61\u662f\u9c7c\u96f7\u3001\u5bfc\u5f39\u8fd8\u662f\u96f7\u8fbe\u7cfb\u7edf\uff0c\u5e76\u8865\u5145\u6240\u5904\u4ecb\u8d28\u73af\u5883\u4ee5\u53ca\u63a8\u529b\u3001\u963b\u529b\u3001\u566a\u58f0\u7b49\u5173\u952e\u53c2\u6570\u3002",
    "radar_tracking": "\u8bf7\u660e\u786e\u662f\u96f7\u8fbe\u76ee\u6807\u8ddf\u8e2a\u8fd8\u662f\u66f4\u9ad8\u5c42\u7684\u6001\u52bf\u611f\u77e5\u95ee\u9898\uff0c\u5e76\u8865\u5145\u521d\u59cb\u4f4d\u7f6e\u3001\u76ee\u6807\u901f\u5ea6\u3001\u89c2\u6d4b\u566a\u58f0\u3001\u8fc7\u7a0b\u566a\u58f0\u7b49\u53c2\u6570\u3002",
    "battlefield_situation": "\u8bf7\u660e\u786e\u662f\u6218\u573a\u6001\u52bf\u611f\u77e5\u3001\u9884\u8b66\u4fa6\u5bdf\u8fd8\u662f\u5175\u529b\u6f14\u5316\u95ee\u9898\uff0c\u5e76\u8bf4\u660e\u5173\u6ce8\u5c42\u7ea7\u662f\u5355\u76ee\u6807\u3001\u5355\u5e73\u53f0\uff0c\u8fd8\u662f\u6218\u573a\u5c42\u3002",
    "battlefield": "\u8bf7\u660e\u786e\u662f\u7ea2\u84dd\u5175\u529b\u6d88\u8017\u3001\u6218\u635f\u8bc4\u4f30\u8fd8\u662f\u6001\u52bf\u6f14\u5316\uff0c\u5e76\u8865\u5145\u53cc\u65b9\u521d\u59cb\u5175\u529b\u3001\u6740\u4f24\u7cfb\u6570\u3001\u4eff\u771f\u65f6\u957f\u7b49\u53c2\u6570\u3002",
}

SUPPORTED_DOMAIN_SUMMARY = "\u5f53\u524d\u7cfb\u7edf\u4e3b\u8981\u652f\u6301\u822a\u7a7a\u822a\u5929\u3001\u6c34\u4e0b\u53d1\u5c04\u3001\u8f68\u9053\u822a\u5929\u3001\u96f7\u8fbe\u8ddf\u8e2a/\u4f30\u8ba1\u3001\u6218\u573a\u6001\u52bf\u4e0e\u7ea2\u84dd\u5bf9\u6297\u7b49 MATLAB \u5efa\u6a21\u4efb\u52a1\u3002"

OUT_OF_SCOPE_TOPIC_LABELS: Dict[str, str] = {
    "finance": "\u91d1\u878d\u4ea4\u6613/\u7b56\u7565\u56de\u6d4b",
    "medical": "\u533b\u7597\u8bca\u65ad/\u4e34\u5e8a\u9884\u6d4b",
    "legal": "\u6cd5\u5f8b\u5408\u89c4/\u5408\u540c\u5206\u6790",
    "recommendation": "\u63a8\u8350\u7cfb\u7edf/\u5e7f\u544a\u6295\u653e",
    "enterprise": "\u901a\u7528\u4f01\u4e1a\u6570\u636e\u5206\u6790",
}

OUT_OF_SCOPE_KEYWORDS: Dict[str, List[str]] = {
    "finance": [
        "\u9ad8\u9891\u4ea4\u6613", "\u91cf\u5316\u4ea4\u6613", "\u4ea4\u6613\u7b56\u7565", "\u7b56\u7565\u56de\u6d4b", "\u56de\u6d4b", "\u6ed1\u70b9", "\u624b\u7eed\u8d39",
        "trading", "backtest", "portfolio", "order book",
    ],
    "medical": [
        "\u533b\u7597", "\u8bca\u65ad", "\u75c5\u4f8b", "\u75c5\u5386", "\u60a3\u8005", "\u836f\u7269", "\u4e34\u5e8a", "\u5f71\u50cf",
        "medical", "diagnosis", "clinical",
    ],
    "legal": [
        "\u6cd5\u5f8b", "\u5408\u540c", "\u8bc9\u8bbc", "\u6cd5\u6761", "\u5408\u89c4", "legal", "contract", "compliance",
    ],
    "recommendation": [
        "\u63a8\u8350\u7cfb\u7edf", "\u5e7f\u544a\u6295\u653e", "\u7528\u6237\u753b\u50cf", "\u70b9\u51fb\u7387", "ctr", "recommendation", "ranking",
    ],
    "enterprise": [
        "\u4f9b\u5e94\u94fe", "\u9500\u552e\u9884\u6d4b", "\u4ed3\u50a8", "\u7535\u5546", "\u5ba2\u670d\u8d28\u68c0", "\u8206\u60c5",
        "inventory", "sales forecast",
    ],
}


PARENT_DOMAIN_GUARDS: Dict[str, Dict[str, Any]] = {
    "military_equipment": {
        "label": "\u519b\u5de5\u88c5\u5907",
        "clarify_prompt": "\u5f53\u524d\u53ea\u843d\u5728\u519b\u5de5\u88c5\u5907\u7236\u57df\uff0c\u4fe1\u606f\u8fd8\u4e0d\u8db3\u4ee5\u76f4\u63a5\u9501\u5b9a\u5230\u5177\u4f53 family\u3002\u8bf7\u5148\u660e\u786e\u5efa\u6a21\u5bf9\u8c61\u3002",
        "object_groups": [
            {
                "label": "\u9c7c\u96f7 / \u6f5c\u8247 / \u6c34\u4e0b\u53d1\u5c04",
                "keywords": ["\u9c7c\u96f7", "\u6f5c\u8247", "\u6c34\u4e0b", "\u6c34\u4e0b\u53d1\u5c04", "torpedo", "submarine", "underwater"],
                "families": ["underwater_launch", "underwater_cruise", "submarine_depth_control"],
            },
            {
                "label": "\u5bfc\u5f39 / \u706b\u7bad / \u62e6\u622a\u98de\u884c",
                "keywords": ["\u5bfc\u5f39", "\u62e6\u622a", "\u706b\u7bad", "\u98de\u884c", "\u5f39\u9053", "missile", "interceptor", "rocket", "trajectory"],
                "families": ["trajectory_ode", "interceptor_guidance", "launch_dynamics", "powered_ascent", "reentry_dynamics", "aircraft_point_mass"],
            },
            {
                "label": "\u96f7\u8fbe / \u76ee\u6807\u8ddf\u8e2a / \u4f20\u611f\u5668\u878d\u5408",
                "keywords": ["\u96f7\u8fbe", "\u8ddf\u8e2a", "\u76ee\u6807\u8ddf\u8e2a", "\u4f20\u611f\u5668", "\u878d\u5408", "kalman", "radar", "tracking", "sensor fusion"],
                "families": ["tracking_estimation", "sensor_fusion_tracking", "bearing_only_tracking"],
            },
            {
                "label": "\u536b\u661f / \u8f68\u9053 / \u822a\u5929\u5668",
                "keywords": ["\u536b\u661f", "\u8f68\u9053", "\u822a\u5929\u5668", "spacecraft", "satellite", "orbit", "orbital"],
                "families": ["orbital_dynamics", "relative_orbit", "orbit_transfer"],
            },
            {
                "label": "\u6218\u573a\u5bf9\u6297 / \u6001\u52bf\u8bc4\u4f30",
                "keywords": ["\u6218\u573a", "\u6001\u52bf", "\u5175\u529b", "\u5a01\u80c1", "\u9f50\u5c04", "battlefield", "attrition", "threat", "salvo"],
                "families": ["battlefield_awareness", "threat_assessment", "combat_attrition", "salvo_engagement"],
            },
        ],
    },
    "battlefield_situation": {
        "label": "\u6218\u573a\u6001\u52bf",
        "clarify_prompt": "\u5f53\u524d\u8bf7\u6c42\u5904\u4e8e\u6218\u573a\u6001\u52bf\u7236\u57df\uff0c\u5fc5\u987b\u5148\u660e\u786e\u95ee\u9898\u5c42\u7ea7\u4e0e\u5bf9\u8c61\uff0c\u518d\u8fdb\u5165\u5177\u4f53 family\u3002",
        "object_groups": [
            {
                "label": "\u6218\u573a\u6001\u52bf\u611f\u77e5 / \u9884\u8b66\u4fa6\u5bdf",
                "keywords": ["\u6001\u52bf\u611f\u77e5", "\u9884\u8b66", "\u4fa6\u5bdf", "awareness", "situation awareness", "reconnaissance", "warning"],
                "families": ["battlefield_awareness"],
            },
            {
                "label": "\u5a01\u80c1\u8bc4\u4f30",
                "keywords": ["\u5a01\u80c1", "threat", "threat assessment", "intent", "\u5371\u9669\u7b49\u7ea7"],
                "families": ["threat_assessment"],
            },
            {
                "label": "\u5355\u76ee\u6807\u96f7\u8fbe\u8ddf\u8e2a / \u8f68\u8ff9\u4f30\u8ba1",
                "keywords": ["\u96f7\u8fbe", "\u8ddf\u8e2a", "\u76ee\u6807", "\u8f68\u8ff9", "kalman", "radar", "tracking", "track"],
                "families": ["tracking_estimation", "sensor_fusion_tracking", "bearing_only_tracking"],
            },
            {
                "label": "\u7ea2\u84dd\u5175\u529b\u6d88\u8017",
                "keywords": ["\u5175\u529b", "\u6d88\u8017", "\u7ea2\u84dd", "lanchester", "attrition", "battle damage"],
                "families": ["combat_attrition"],
            },
            {
                "label": "\u9f50\u5c04\u62e6\u622a / \u9632\u7a7a\u4ea4\u6218",
                "keywords": ["\u9f50\u5c04", "\u62e6\u622a", "\u9632\u7a7a", "\u4ea4\u6218", "salvo", "intercept", "leaker"],
                "families": ["salvo_engagement"],
            },
        ],
    },
}


class MatlabRAGRetriever:
    def __init__(self, index_path: str | None = None):
        self.index_path = index_path or os.path.join(
            os.path.dirname(__file__), "matlab_knowledge_index.json"
        )
        self.docs_dir = DEFAULT_DOCS_DIR
        self.catalog = get_model_catalog()
        self.model_by_id = {item["model_id"]: item for item in self.catalog}
        self.model_ids_by_family: Dict[str, List[str]] = defaultdict(list)
        self.default_model_by_family: Dict[str, Dict[str, Any]] = {}
        for item in self.catalog:
            model_id = str(item.get("model_id", "")).strip()
            family = str(item.get("template_family", "")).strip()
            if not model_id or not family:
                continue
            self.model_ids_by_family[family].append(model_id)
            if family not in self.default_model_by_family:
                self.default_model_by_family[family] = item
            trunk_family = self._resolve_trunk_family(family)
            if trunk_family and trunk_family not in self.default_model_by_family:
                self.default_model_by_family[trunk_family] = item
        self._model_aliases = self._build_model_aliases()
        self.documents = self._load_documents()
        self._ensure_unique_doc_ids()
        self._doc_by_id = {int(d["id"]): d for d in self.documents}
        self._family_prototype_docs = {
            str(doc.get("payload", {}).get("template_family", "")).strip(): {
                "text": doc.get("text", ""),
                "payload": dict(doc.get("payload", {})),
            }
            for doc in self.documents
            if str(doc.get("payload", {}).get("type", "")).lower() == "family_prototype"
            and str(doc.get("payload", {}).get("template_family", "")).strip()
        }

        # BM25 index
        self._doc_tokens: List[List[str]] = []
        self._doc_term_freq: List[Dict[str, int]] = []
        self._doc_len: List[int] = []
        self._doc_freq: Dict[str, int] = {}
        self._avgdl = 0.0
        self._build_bm25_index()

        # Vector backend (lazy init)
        self._vector_initialized = False
        self._vector_ready = False
        self._vector_backend = "none"
        self._vector_error = ""
        self._embedding_model = None
        self._qdrant_client = None
        self._doc_embeddings: List[List[float]] | None = None

    def _load_documents(self) -> List[Dict[str, Any]]:
        catalog_docs = self._build_catalog_documents()
        file_docs = load_file_documents(self.docs_dir)

        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    docs = json.load(f)
                if isinstance(docs, list) and docs:
                    persisted_docs = [
                        doc
                        for doc in docs
                        if str(doc.get("payload", {}).get("type", "")).lower() != "document"
                    ]
                    return self._merge_documents(persisted_docs, file_docs, catalog_docs)
            except Exception:
                pass

        return self._merge_documents(file_docs, catalog_docs)

    def _build_model_aliases(self) -> Dict[str, List[str]]:
        aliases: Dict[str, List[str]] = {}
        for item in self.catalog:
            model_id = str(item.get("model_id", "")).strip()
            if not model_id:
                continue
            values = {model_id.lower(), str(item.get("name", "")).lower()}
            for kw in item.get("keywords", []):
                kw_text = str(kw).strip().lower()
                if kw_text:
                    values.add(kw_text)
            aliases[model_id] = sorted(v for v in values if len(v) >= 2)
        return aliases

    def _ensure_unique_doc_ids(self) -> None:
        seen: set[int] = set()
        for idx, doc in enumerate(self.documents):
            raw_id = doc.get("id")
            try:
                doc_id = int(raw_id)
            except Exception:
                doc_id = idx
            while doc_id in seen:
                doc_id += 100000
            seen.add(doc_id)
            doc["id"] = doc_id

    def _build_catalog_documents(self) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        for idx, item in enumerate(self.catalog):
            docs.append(
                {
                    "id": idx * 10,
                    "text": (
                        f"model_id: {item['model_id']}; name: {item['name']}; category: {item['category']}; "
                        f"template_family: {item.get('template_family', '')}; "
                        f"domain_tags: {', '.join(item.get('domain_tags', []))}; "
                        f"description: {item['description']}; keywords: {', '.join(item.get('keywords', []))}"
                    ),
                    "payload": {
                        "type": "model",
                        "model_id": item["model_id"],
                        "name": item["name"],
                        "category": item["category"],
                        "template_family": item.get("template_family", ""),
                        "domain_tags": item.get("domain_tags", []),
                        "equation_fragments": item.get("equation_fragments", []),
                        "description": item["description"],
                        "keywords": item.get("keywords", []),
                        "default_params": item.get("default_params", {}),
                    },
                }
            )
            for e_idx, example in enumerate(item.get("examples", []), start=1):
                docs.append(
                    {
                        "id": idx * 10 + e_idx,
                        "text": (
                            f"example: {example} -> model {item['model_id']}; "
                            f"template_family: {item.get('template_family', '')}; "
                            f"domain_tags: {', '.join(item.get('domain_tags', []))}; "
                            f"equation_fragments: {', '.join(item.get('equation_fragments', []))}"
                        ),
                        "payload": {
                            "type": "example",
                            "model_id": item["model_id"],
                            "template_family": item.get("template_family", ""),
                            "domain_tags": item.get("domain_tags", []),
                            "equation_fragments": item.get("equation_fragments", []),
                            "example": example,
                        },
                    }
                )
        docs.extend(self._build_family_prototype_documents(start_id=200000))
        return docs

    def _build_family_prototype_documents(self, start_id: int = 200000) -> List[Dict[str, Any]]:
        docs: List[Dict[str, Any]] = []
        for idx, family in enumerate(SLOT_SCHEMAS.keys()):
            payload = self._build_family_prototype_payload(family)
            docs.append(
                {
                    "id": start_id + idx * 10,
                    "text": self._build_family_prototype_text(payload),
                    "payload": payload,
                }
            )
            for q_idx, question in enumerate(payload.get("typical_queries", []), start=1):
                docs.append(
                    {
                        "id": start_id + idx * 10 + q_idx,
                        "text": (
                            f"family_example: {question} -> template_family {family}; "
                            f"display_name: {payload.get('display_name', family)}; "
                            f"scene: {payload.get('scene', '')}; "
                            f"object_words: {', '.join(payload.get('object_words', []))}; "
                            f"key_slots: {', '.join(payload.get('key_slots', []))}; "
                            f"anti_confusion_words: {', '.join(payload.get('anti_confusion_words', []))}"
                        ),
                        "payload": {
                            "type": "family_example",
                            "template_family": family,
                            "domain_tags": payload.get("domain_tags", []),
                            "family_tier": payload.get("family_tier", ""),
                            "parent_family": payload.get("parent_family", ""),
                            "display_name": payload.get("display_name", family),
                            "scene": payload.get("scene", ""),
                            "object_words": payload.get("object_words", []),
                            "key_slots": payload.get("key_slots", []),
                            "anti_confusion_words": payload.get("anti_confusion_words", []),
                            "keywords": payload.get("keywords", []),
                            "example": question,
                        },
                    }
                )
        return docs

    def _build_family_prototype_payload(self, family: str) -> Dict[str, Any]:
        schema = SLOT_SCHEMAS.get(family, {})
        family_meta = FAMILY_LIBRARY.get(family, {})
        display_name = str(schema.get("display_name", family)).strip()
        scene = str(schema.get("scene", "")).strip()
        domain = str(family_meta.get("domain", "")).strip()
        family_tier = str(family_meta.get("family_tier", "")).strip()
        parent_family = str(family_meta.get("parent_family", "")).strip()
        key_slots = self._ordered_family_slots(family, schema)
        object_words = self._family_object_words(family, display_name, scene)
        anti_confusion_words = self._family_anti_confusion_words(family, domain)
        typical_queries = self._family_typical_queries(family, display_name, scene, object_words, key_slots, schema)

        keywords: List[str] = []

        def append_keyword(value: str) -> None:
            text = str(value or "").strip()
            if text and text.lower() not in {item.lower() for item in keywords}:
                keywords.append(text)

        for value in [
            family,
            family.replace("_", " "),
            display_name,
            scene,
            domain,
            family_tier,
            parent_family,
        ]:
            append_keyword(value)
        for value in object_words + anti_confusion_words + typical_queries:
            append_keyword(value)
        slot_defs = schema.get("slot_defs", {}) if isinstance(schema, dict) else {}
        for slot_name in key_slots:
            append_keyword(slot_name)
            slot_meta = slot_defs.get(slot_name, {}) if isinstance(slot_defs, dict) else {}
            append_keyword(str(slot_meta.get("label", "")).strip())
            for alias in list(slot_meta.get("aliases", []))[:4]:
                append_keyword(str(alias))

        domain_tags = [tag for tag in [domain, family, parent_family, self._resolve_trunk_family(family)] if tag]
        if family_tier:
            domain_tags.append(f"family_tier:{family_tier}")
        domain_tags = list(dict.fromkeys(domain_tags))

        return {
            "type": "family_prototype",
            "template_family": family,
            "domain_tags": domain_tags,
            "family_tier": family_tier,
            "parent_family": parent_family,
            "display_name": display_name,
            "scene": scene,
            "object_words": object_words,
            "key_slots": key_slots,
            "anti_confusion_words": anti_confusion_words,
            "typical_queries": typical_queries,
            "keywords": keywords,
            "description": scene,
        }

    def _build_family_prototype_text(self, payload: Dict[str, Any]) -> str:
        family = str(payload.get("template_family", "")).strip()
        display_name = str(payload.get("display_name", family)).strip()
        return (
            f"family: {family}; display_name: {display_name}; scene: {payload.get('scene', '')}; "
            f"domain_tags: {', '.join(payload.get('domain_tags', []))}; "
            f"family_tier: {payload.get('family_tier', '')}; "
            f"parent_family: {payload.get('parent_family', '')}; "
            f"object_words: {', '.join(payload.get('object_words', []))}; "
            f"key_slots: {', '.join(payload.get('key_slots', []))}; "
            f"anti_confusion_words: {', '.join(payload.get('anti_confusion_words', []))}; "
            f"typical_queries: {' || '.join(payload.get('typical_queries', []))}"
        )

    def _ordered_family_slots(self, family: str, schema: Dict[str, Any]) -> List[str]:
        ordered_slots: List[str] = []
        slot_groups = [
            list(schema.get("identify_slots", [])),
            list(schema.get("critical_slots", schema.get("required_slots", []))),
            list(schema.get("defaultable_slots", schema.get("recommended_slots", []))),
        ]
        for key in [slot for group in slot_groups for slot in group]:
            slot_name = str(key or "").strip()
            if slot_name and slot_name not in ordered_slots:
                ordered_slots.append(slot_name)
        for key in FAMILY_LIBRARY.get(family, {}).get("state_variables", []):
            slot_name = str(key or "").strip()
            if slot_name and slot_name not in ordered_slots:
                ordered_slots.append(slot_name)
        return ordered_slots[:8]

    def _family_object_words(self, family: str, display_name: str, scene: str) -> List[str]:
        values: List[str] = []
        seen: set[str] = set()

        def append_unique(value: str) -> None:
            text = str(value or "").strip()
            if not text:
                return
            lowered = text.lower()
            if lowered in seen:
                return
            seen.add(lowered)
            values.append(text)

        for value in FAMILY_OBJECT_HINTS.get(family, []):
            append_unique(value)
        for chunk in re.split(r"[、,，/\\;；\-\s]+", f"{display_name} {scene}"):
            cleaned = str(chunk or "").strip()
            if len(cleaned) >= 2:
                append_unique(cleaned)
            if len(values) >= 5:
                break
        return values[:5]

    def _family_anti_confusion_words(self, family: str, domain: str) -> List[str]:
        values: List[str] = []
        seen: set[str] = set()

        def append_unique(value: str) -> None:
            text = str(value or "").strip()
            if not text:
                return
            lowered = text.lower()
            if lowered in seen:
                return
            seen.add(lowered)
            values.append(text)

        family_meta = FAMILY_LIBRARY.get(family, {})
        parent_family = str(family_meta.get("parent_family", "")).strip()
        trunk_family = self._resolve_trunk_family(family)
        if parent_family:
            append_unique(parent_family)
        if trunk_family and trunk_family != family:
            append_unique(trunk_family)
        for sibling, meta in FAMILY_LIBRARY.items():
            if sibling == family:
                continue
            if str(meta.get("domain", "")).strip() != domain:
                continue
            append_unique(sibling)
            display_name = str(SLOT_SCHEMAS.get(sibling, {}).get("display_name", sibling)).strip()
            append_unique(display_name)
            if len(values) >= 6:
                break
        return values[:6]

    def _family_typical_queries(
        self,
        family: str,
        display_name: str,
        scene: str,
        object_words: List[str],
        key_slots: List[str],
        schema: Dict[str, Any],
    ) -> List[str]:
        slot_defs = schema.get("slot_defs", {}) if isinstance(schema, dict) else {}
        slot_labels: List[str] = []
        slot_aliases: List[str] = []
        for slot_name in key_slots[:4]:
            slot_meta = slot_defs.get(slot_name, {}) if isinstance(slot_defs, dict) else {}
            label = str(slot_meta.get("label", slot_name)).strip() or slot_name
            slot_labels.append(label)
            aliases = [str(alias).strip() for alias in slot_meta.get("aliases", []) if str(alias).strip()]
            slot_aliases.append(aliases[1] if len(aliases) > 1 else (aliases[0] if aliases else slot_name))

        object_primary = object_words[0] if object_words else display_name or family
        object_secondary = object_words[1] if len(object_words) > 1 else object_primary
        slot_label_phrase = "、".join(slot_labels[:3]) if slot_labels else "关键参数"
        slot_alias_phrase = ", ".join(slot_aliases[:3]) if slot_aliases else family.replace("_", " ")

        queries = [
            f"构建{display_name}MATLAB模型",
            f"生成{scene}仿真代码，给定{slot_label_phrase}",
            f"做一个{object_primary}场景的{display_name}模型，重点看{slot_label_phrase}",
            f"build {family.replace('_', ' ')} matlab model with {slot_alias_phrase}",
        ]
        if object_secondary and object_secondary != object_primary:
            queries.append(f"针对{object_primary}与{object_secondary}，生成{display_name}仿真脚本")

        deduped: List[str] = []
        seen: set[str] = set()
        for query in queries:
            normalized = str(query or "").strip()
            if not normalized:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(normalized)
            if len(deduped) >= 5:
                break
        return deduped

    def _dedupe_text_values(self, values: List[Any]) -> List[str]:
        deduped: List[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(text)
        return deduped

    def _payload_family_profile(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        family = self._resolve_payload_family(payload)
        schema = SLOT_SCHEMAS.get(family, {}) if family else {}
        family_meta = FAMILY_LIBRARY.get(family, {}) if family else {}
        display_name = str(payload.get("display_name", "") or schema.get("display_name", "") or family).strip()
        scene = str(payload.get("scene", "") or schema.get("scene", "")).strip()
        family_domain = str(family_meta.get("domain", "")).strip()
        parent_family = str(payload.get("parent_family", "") or family_meta.get("parent_family", "")).strip()

        object_words = self._dedupe_text_values(list(payload.get("object_words", [])))
        if not object_words and family:
            object_words = self._family_object_words(family, display_name, scene)

        anti_confusion_words = self._dedupe_text_values(list(payload.get("anti_confusion_words", [])))
        if not anti_confusion_words and family:
            anti_confusion_words = self._family_anti_confusion_words(family, family_domain)

        return {
            "family": family,
            "display_name": display_name,
            "scene": scene,
            "domain": family_domain,
            "parent_family": parent_family,
            "object_words": object_words,
            "anti_confusion_words": anti_confusion_words,
        }

    def _scene_match_values(self, scene: str, display_name: str = "") -> List[str]:
        values: List[str] = []
        seen: set[str] = set()

        def append_unique(value: str) -> None:
            text = str(value or "").strip()
            if not text:
                return
            lowered = text.lower()
            if lowered in seen:
                return
            seen.add(lowered)
            values.append(text)

        append_unique(scene)
        append_unique(display_name)
        for chunk in re.split(r"[、，,；;（）()\/\s]+", scene):
            cleaned = str(chunk or "").strip()
            if len(cleaned) >= 2:
                append_unique(cleaned)
        return values[:8]

    def _query_value_matches(self, query_lower: str, query_terms: set[str], values: List[Any]) -> List[str]:
        matched: List[str] = []
        for value in self._dedupe_text_values(values):
            normalized = value.lower().strip()
            if not normalized:
                continue
            has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in normalized)
            is_phrase = " " in normalized or has_cjk or len(normalized) >= 10
            hit = normalized in query_lower if is_phrase else (normalized in query_terms or normalized in query_lower)
            if hit:
                matched.append(value)
        return matched

    def _payload_positive_keywords(self, payload: Dict[str, Any], profile: Dict[str, Any]) -> List[str]:
        filtered: List[str] = []
        family_name = str(profile.get("family", "")).lower().strip()
        negative_terms = {
            str(profile.get("domain", "")).lower().strip(),
            str(profile.get("parent_family", "")).lower().strip(),
            str(payload.get("family_tier", "")).lower().strip(),
        }
        negative_terms.update(str(term).lower().strip() for term in profile.get("anti_confusion_words", []))
        negative_terms.update(
            normalized
            for normalized in (str(tag).lower().strip() for tag in payload.get("domain_tags", []))
            if normalized and normalized != family_name
        )
        negative_terms = {term for term in negative_terms if term}

        for keyword in self._dedupe_text_values(list(payload.get("keywords", []))):
            normalized = keyword.lower().strip()
            if normalized and normalized not in negative_terms:
                filtered.append(keyword)

        payload_type = str(payload.get("type", "")).lower()
        if payload_type in {"family_prototype", "family_example"}:
            curated = filtered + [
                str(profile.get("family", "")).strip(),
                str(profile.get("family", "")).replace("_", " ").strip(),
                str(profile.get("display_name", "")).strip(),
                str(profile.get("scene", "")).strip(),
            ]
            curated.extend(list(profile.get("object_words", [])))
            curated.extend(list(payload.get("typical_queries", [])))
            return self._dedupe_text_values(curated)

        return self._dedupe_text_values(filtered)

    def _merge_documents(self, *doc_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen_keys = set()

        def add_doc(doc: Dict[str, Any]) -> None:
            payload = doc.get("payload", {})
            key = (
                payload.get("type", ""),
                payload.get("model_id", ""),
                str(payload.get("example", "")),
                str(payload.get("description", "")),
                str(payload.get("source_file", "")),
                str(payload.get("chunk_index", "")),
                doc.get("text", ""),
            )
            if key in seen_keys:
                return
            seen_keys.add(key)
            merged.append(doc)

        for docs in doc_groups:
            for doc in docs:
                add_doc(doc)
        return merged

    def _build_bm25_index(self) -> None:
        doc_freq: Dict[str, int] = defaultdict(int)
        lengths: List[int] = []
        tokens_store: List[List[str]] = []
        tf_store: List[Dict[str, int]] = []

        for doc in self.documents:
            tokens = [t.lower() for t in _extract_terms(doc.get("text", ""))]
            if not tokens:
                tokens = ["__empty__"]
            tf = Counter(tokens)
            tokens_store.append(tokens)
            tf_store.append(dict(tf))
            lengths.append(len(tokens))
            for term in tf.keys():
                doc_freq[term] += 1

        self._doc_tokens = tokens_store
        self._doc_term_freq = tf_store
        self._doc_len = lengths
        self._doc_freq = dict(doc_freq)
        self._avgdl = (sum(lengths) / len(lengths)) if lengths else 1.0

    def _bm25_scores(self, query_terms: List[str]) -> Dict[int, float]:
        if not query_terms:
            return {}
        n_docs = len(self.documents)
        if n_docs == 0:
            return {}

        k1 = 1.5
        b = 0.75
        scores: Dict[int, float] = defaultdict(float)
        avgdl = self._avgdl or 1.0

        for term in [t.lower() for t in query_terms]:
            df = self._doc_freq.get(term, 0)
            if df == 0:
                continue
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            for idx, doc in enumerate(self.documents):
                tf = self._doc_term_freq[idx].get(term, 0)
                if tf <= 0:
                    continue
                dl = self._doc_len[idx]
                denom = tf + k1 * (1.0 - b + b * dl / avgdl)
                value = idf * (tf * (k1 + 1.0)) / max(1e-9, denom)
                scores[int(doc["id"])] += value

        return dict(scores)

    def _ensure_vector_backend(self) -> bool:
        if self._vector_initialized:
            return self._vector_ready
        self._vector_initialized = True

        backend = str(getattr(settings, "RETRIEVAL_VECTOR_BACKEND", "auto")).strip().lower()
        if backend in {"off", "none", "disable", "disabled"}:
            self._vector_backend = "none"
            self._vector_ready = False
            self._vector_error = "vector_backend_disabled"
            return False

        try:
            self._ensure_hf_cached_download_compat()
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            self._vector_backend = "none"
            self._vector_ready = False
            self._vector_error = f"embedding_init_failed: {exc}"
            logger.warning("Vector retrieval disabled: %s", self._vector_error)
            return False

        try:
            self._embedding_model = SentenceTransformer(
                settings.EMBEDDING_MODEL,
                device=settings.EMBEDDING_DEVICE,
            )
        except Exception as exc:
            self._vector_backend = "none"
            self._vector_ready = False
            self._vector_error = f"embedding_model_load_failed: {exc}"
            logger.warning("Vector retrieval disabled: %s", self._vector_error)
            return False

        if backend in {"auto", "qdrant"}:
            try:
                from qdrant_client import QdrantClient

                client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT, timeout=3)
                try:
                    client.get_collection(settings.QDRANT_COLLECTION)
                except Exception as get_exc:
                    # Some qdrant-client versions may fail to parse newer server response.
                    if not self._qdrant_collection_exists_http():
                        raise get_exc
                    logger.warning(
                        "Qdrant client/server schema mismatch detected, use REST compatibility mode: %s",
                        get_exc,
                    )
                    self._vector_error = f"qdrant_client_compat_mode: {get_exc}"
                self._qdrant_client = client
                self._vector_backend = "qdrant"
                self._vector_ready = True
                logger.info(
                    "Hybrid retriever vector backend enabled: qdrant(%s:%s/%s)",
                    settings.QDRANT_HOST,
                    settings.QDRANT_PORT,
                    settings.QDRANT_COLLECTION,
                )
                return True
            except Exception as exc:
                self._vector_error = f"qdrant_unavailable: {exc}"
                if backend == "qdrant":
                    self._vector_backend = "none"
                    self._vector_ready = False
                    logger.warning("Vector backend=qdrant required but unavailable: %s", exc)
                    return False

        # Local vector fallback
        try:
            self._prepare_local_doc_embeddings()
            self._vector_backend = "local"
            self._vector_ready = True
            logger.info("Hybrid retriever vector backend enabled: local")
            return True
        except Exception as exc:
            self._vector_backend = "none"
            self._vector_ready = False
            self._vector_error = f"local_vector_prepare_failed: {exc}"
            logger.warning("Vector retrieval disabled: %s", self._vector_error)
            return False

    def _prepare_local_doc_embeddings(self) -> None:
        if self._embedding_model is None:
            raise RuntimeError("embedding model is not initialized")
        if self._doc_embeddings is not None:
            return
        texts = [doc.get("text", "") for doc in self.documents]
        vectors = self._embedding_model.encode(texts, normalize_embeddings=True)
        self._doc_embeddings = [list(map(float, v)) for v in vectors]

    @staticmethod
    def _ensure_hf_cached_download_compat() -> None:
        """
        Compatibility shim:
        sentence-transformers<2.3 imports `cached_download` from huggingface_hub,
        but newer huggingface_hub removed this symbol.
        """
        try:
            import huggingface_hub  # type: ignore
        except Exception:
            return

        if hasattr(huggingface_hub, "cached_download"):
            return

        try:
            from huggingface_hub import hf_hub_download  # type: ignore
        except Exception:
            return

        def cached_download(
            url: str,
            cache_dir: str | None = None,
            force_filename: str | None = None,
            use_auth_token: str | None = None,
            token: str | None = None,
            local_files_only: bool = False,
            proxies: Dict[str, str] | None = None,
            **_: Any,
        ) -> str:
            target_cache = cache_dir or str(Path.home() / ".cache" / "huggingface" / "hub")
            os.makedirs(target_cache, exist_ok=True)

            parsed = urlparse(url)
            match = re.match(
                r"^(?P<repo>.+?)/resolve/(?P<rev>[^/]+)/(?P<file>.+)$",
                parsed.path.lstrip("/"),
            )
            if match:
                repo_id = match.group("repo")
                revision = match.group("rev")
                filename = match.group("file")
                downloaded = hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    revision=revision,
                    cache_dir=target_cache,
                    token=token or use_auth_token,
                    local_files_only=local_files_only,
                )
                if force_filename:
                    forced_path = os.path.join(target_cache, force_filename)
                    if not os.path.exists(forced_path):
                        with open(downloaded, "rb") as src, open(forced_path, "wb") as dst:
                            dst.write(src.read())
                    return forced_path
                return downloaded

            file_name = force_filename or os.path.basename(parsed.path) or "download.bin"
            local_path = os.path.join(target_cache, file_name)
            if os.path.exists(local_path):
                return local_path
            if local_files_only:
                raise FileNotFoundError(f"local_files_only=True and file not found: {local_path}")

            import requests

            headers = {}
            auth_token = token or use_auth_token
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"
            with requests.get(url, stream=True, timeout=120, proxies=proxies, headers=headers) as resp:
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            return local_path

        setattr(huggingface_hub, "cached_download", cached_download)

    def _vector_scores(self, query: str, top_n: int) -> Tuple[Dict[int, float], str]:
        if not self._ensure_vector_backend():
            return {}, "none"

        assert self._embedding_model is not None
        query_vec_raw = self._embedding_model.encode([query], normalize_embeddings=True)[0]
        query_vec = list(map(float, query_vec_raw))

        if self._vector_backend == "qdrant" and self._qdrant_client is not None:
            try:
                raw = self._vector_search_qdrant(query_vec, top_n)
                return _normalize_score_map(raw), "qdrant"
            except Exception as exc:
                self._vector_error = f"qdrant_search_failed: {exc}"
                logger.warning("Qdrant search failed, fallback local vector: %s", exc)
                self._prepare_local_doc_embeddings()
                raw = self._vector_search_local(query_vec, top_n)
                return _normalize_score_map(raw), "local"

        self._prepare_local_doc_embeddings()
        raw = self._vector_search_local(query_vec, top_n)
        return _normalize_score_map(raw), "local"

    def get_retrieval_health(self) -> Dict[str, Any]:
        configured_vector_backend = str(getattr(settings, "RETRIEVAL_VECTOR_BACKEND", "auto")).strip().lower()
        configured_bm25_weight = float(getattr(settings, "RETRIEVAL_BM25_WEIGHT", 0.55))
        configured_vector_weight = float(getattr(settings, "RETRIEVAL_VECTOR_WEIGHT", 0.45))
        vector_ready = self._ensure_vector_backend()
        hybrid_effective = bool(vector_ready and self._vector_backend in {"qdrant", "local"})

        effective_bm25_weight = configured_bm25_weight
        effective_vector_weight = configured_vector_weight
        if not hybrid_effective:
            effective_bm25_weight = 1.0
            effective_vector_weight = 0.0

        return {
            "status": "healthy" if hybrid_effective else "degraded",
            "hybrid_effective": hybrid_effective,
            "vector_ready": bool(vector_ready),
            "configured_vector_backend": configured_vector_backend,
            "active_vector_backend": self._vector_backend,
            "vector_error": self._vector_error,
            "configured_bm25_weight": round(configured_bm25_weight, 4),
            "configured_vector_weight": round(configured_vector_weight, 4),
            "effective_bm25_weight": round(effective_bm25_weight, 4),
            "effective_vector_weight": round(effective_vector_weight, 4),
            "qdrant_enabled": self._vector_backend == "qdrant",
            "local_vector_enabled": self._vector_backend == "local",
        }

    def _vector_search_qdrant(self, query_vec: List[float], top_n: int) -> Dict[int, float]:
        assert self._qdrant_client is not None
        hits = None
        try:
            hits = self._qdrant_client.search(
                collection_name=settings.QDRANT_COLLECTION,
                query_vector=query_vec,
                limit=top_n,
                with_payload=True,
            )
        except Exception:
            try:
                points = self._qdrant_client.query_points(
                    collection_name=settings.QDRANT_COLLECTION,
                    query=query_vec,
                    limit=top_n,
                    with_payload=True,
                )
                hits = getattr(points, "points", points)
            except Exception:
                return self._vector_search_qdrant_http(query_vec, top_n)

        raw_scores: Dict[int, float] = {}
        for hit in hits or []:
            point_id = getattr(hit, "id", None)
            doc_id = _safe_to_int(point_id)
            if doc_id is None:
                payload = getattr(hit, "payload", {}) or {}
                doc_id = _safe_to_int(payload.get("id"))
            if doc_id is None or doc_id not in self._doc_by_id:
                continue
            raw_scores[doc_id] = float(getattr(hit, "score", 0.0))
        return raw_scores

    def _vector_search_qdrant_http(self, query_vec: List[float], top_n: int) -> Dict[int, float]:
        base_url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
        collection = settings.QDRANT_COLLECTION
        payload = {"vector": query_vec, "limit": top_n, "with_payload": True}
        endpoints = [
            f"{base_url}/collections/{collection}/points/search",
            f"{base_url}/collections/{collection}/points/query",
        ]

        last_error = ""
        for endpoint in endpoints:
            body = payload if endpoint.endswith("/search") else {
                "query": query_vec,
                "limit": top_n,
                "with_payload": True,
            }
            try:
                resp = requests.post(endpoint, json=body, timeout=8)
                if resp.status_code == 404:
                    last_error = f"404:{endpoint}"
                    continue
                resp.raise_for_status()
                data = resp.json()
                result = data.get("result", [])
                if isinstance(result, dict) and "points" in result:
                    result = result.get("points", [])
                raw_scores: Dict[int, float] = {}
                for hit in result or []:
                    doc_id = _safe_to_int(hit.get("id"))
                    if doc_id is None:
                        payload_obj = hit.get("payload", {}) or {}
                        doc_id = _safe_to_int(payload_obj.get("id"))
                    if doc_id is None or doc_id not in self._doc_by_id:
                        continue
                    raw_scores[doc_id] = float(hit.get("score", 0.0))
                return raw_scores
            except Exception as exc:
                last_error = str(exc)
                continue

        raise RuntimeError(f"qdrant_rest_search_failed: {last_error}")

    def _qdrant_collection_exists_http(self) -> bool:
        url = (
            f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
            f"/collections/{settings.QDRANT_COLLECTION}"
        )
        try:
            resp = requests.get(url, timeout=4)
            if resp.status_code == 200:
                return True
            return False
        except Exception:
            return False

    def _vector_search_local(self, query_vec: List[float], top_n: int) -> Dict[int, float]:
        if self._doc_embeddings is None:
            return {}
        scored: List[Tuple[int, float]] = []
        for idx, vec in enumerate(self._doc_embeddings):
            score = sum(float(a) * float(b) for a, b in zip(query_vec, vec))
            doc_id = int(self.documents[idx]["id"])
            scored.append((doc_id, float(score)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return dict(scored[:top_n])

    def retrieve(self, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
        text = (query or "").strip()
        if not text:
            return []
        query_terms = _extract_terms(text)
        if not query_terms:
            return self._fallback_docs(top_k)

        candidate_multiplier = max(2, int(getattr(settings, "RETRIEVAL_CANDIDATE_MULTIPLIER", 4)))
        candidate_k = max(top_k, top_k * candidate_multiplier)

        bm25_raw = self._bm25_scores(query_terms)
        bm25_norm = _normalize_score_map(bm25_raw)

        vector_norm, vector_backend = self._vector_scores(text, top_n=candidate_k)
        vector_enabled = bool(vector_norm)

        candidate_ids = set(_top_keys(bm25_norm, candidate_k))
        candidate_ids.update(_top_keys(vector_norm, candidate_k))
        if not candidate_ids:
            return self._fallback_docs(top_k)

        bm25_weight = float(getattr(settings, "RETRIEVAL_BM25_WEIGHT", 0.55))
        vector_weight = float(getattr(settings, "RETRIEVAL_VECTOR_WEIGHT", 0.45))
        if not vector_enabled:
            bm25_weight = 1.0
            vector_weight = 0.0
        total_w = max(1e-9, bm25_weight + vector_weight)
        bm25_weight /= total_w
        vector_weight /= total_w
        rerank_blend = min(0.9, max(0.0, float(getattr(settings, "RETRIEVAL_RERANK_BLEND", 0.35))))

        ranked: List[Dict[str, Any]] = []
        for doc_id in candidate_ids:
            doc = self._doc_by_id.get(doc_id)
            if not doc:
                continue
            bm25_s = bm25_norm.get(doc_id, 0.0)
            vec_s = vector_norm.get(doc_id, 0.0)
            fused = bm25_weight * bm25_s + vector_weight * vec_s
            rerank, rerank_multiplier = self._rerank_score(text, query_terms, doc)
            final_norm = ((1.0 - rerank_blend) * fused + rerank_blend * rerank) * rerank_multiplier
            final_score = final_norm * 20.0
            ranked.append(
                {
                    "score": round(final_score, 4),
                    "id": doc_id,
                    "text": doc.get("text", ""),
                    "payload": doc.get("payload", {}),
                    "score_detail": {
                        "bm25": round(bm25_s, 5),
                        "vector": round(vec_s, 5),
                        "fused": round(fused, 5),
                        "rerank": round(rerank, 5),
                        "rerank_multiplier": round(rerank_multiplier, 5),
                        "backend": vector_backend,
                    },
                }
            )

        ranked.sort(key=lambda x: x["score"], reverse=True)
        if not ranked:
            return self._fallback_docs(top_k)
        return ranked[:top_k]

    def _fallback_docs(self, top_k: int) -> List[Dict[str, Any]]:
        fallback = self.documents[:top_k]
        return [
            {
                "score": 0.0,
                "id": item.get("id"),
                "text": item.get("text", ""),
                "payload": item.get("payload", {}),
                "score_detail": {
                    "bm25": 0.0,
                    "vector": 0.0,
                    "fused": 0.0,
                    "rerank": 0.0,
                    "rerank_multiplier": 1.0,
                    "backend": self._vector_backend,
                },
            }
            for item in fallback
        ]

    def _rerank_score(self, query: str, query_terms: List[str], doc: Dict[str, Any]) -> Tuple[float, float]:
        query_lower = query.lower()
        doc_text = doc.get("text", "")
        doc_lower = doc_text.lower()
        payload = doc.get("payload", {})
        query_term_set = {t.lower() for t in query_terms}
        profile = self._payload_family_profile(payload)
        query_domains = self._detect_query_domains(query)
        primary_query_domain = query_domains[0] if query_domains else ""
        broad_query_terms: set[str] = set()
        if primary_query_domain in PARENT_DOMAIN_GUARDS:
            broad_query_terms.update(
                term
                for term in {
                    primary_query_domain.lower().strip(),
                    primary_query_domain.replace("_", " ").lower().strip(),
                    str(DOMAIN_LABELS.get(primary_query_domain, "")).lower().strip(),
                }
                if term
            )

        doc_terms = set(t.lower() for t in _extract_terms(doc_text))
        overlap = 0.0
        if query_term_set and doc_terms:
            overlap = len([term for term in query_term_set if term in doc_terms]) / max(1, len(query_term_set))

        model_id = str(payload.get("model_id", "")).lower()
        model_match = 1.0 if model_id and model_id in query_lower else 0.0
        keyword_matches = self._query_value_matches(
            query_lower,
            query_term_set,
            [
                value
                for value in self._payload_positive_keywords(payload, profile)
                if str(value).lower().strip() not in broad_query_terms
            ],
        )
        keyword_hit = min(1.0, len(keyword_matches) / 3.0)

        alias_hit = 0.0
        raw_model_id = str(payload.get("model_id", ""))
        if raw_model_id:
            alias_list = self._model_aliases.get(raw_model_id, [])
            family_name = str(profile.get("family", "")).lower().strip()
            blocked_aliases = {
                str(profile.get("domain", "")).lower().strip(),
                str(profile.get("parent_family", "")).lower().strip(),
            }
            blocked_aliases.update(str(term).lower().strip() for term in profile.get("anti_confusion_words", []))
            blocked_aliases.update(broad_query_terms)
            blocked_aliases.update(
                normalized
                for normalized in (str(tag).lower().strip() for tag in payload.get("domain_tags", []))
                if normalized and normalized != family_name
            )
            hits = 0
            for alias in alias_list:
                if alias in blocked_aliases:
                    continue
                if alias in query_lower:
                    hits += 1
            alias_hit = min(1.0, hits / 2.0)

        family_identity_matches = self._query_value_matches(
            query_lower,
            query_term_set,
            [
                str(profile.get("family", "")).strip(),
                str(profile.get("family", "")).replace("_", " ").strip(),
                str(profile.get("display_name", "")).strip(),
            ],
        )
        family_identity_hit = 1.0 if family_identity_matches else 0.0

        object_words = list(profile.get("object_words", []))
        object_matches = self._query_value_matches(query_lower, query_term_set, object_words)
        object_hit = min(1.0, len(object_matches) / max(1, min(3, len(object_words))))

        scene_values = self._scene_match_values(
            str(profile.get("scene", "")).strip(),
            str(profile.get("display_name", "")).strip(),
        )
        scene_matches = self._query_value_matches(query_lower, query_term_set, scene_values)
        scene_hit = 0.0
        scene_text = str(profile.get("scene", "")).strip().lower()
        if scene_text and scene_text in query_lower:
            scene_hit = 1.0
        elif scene_matches:
            scene_hit = min(1.0, len(scene_matches) / max(1, min(3, len(scene_values))))

        payload_tags = self._candidate_domain_tags(payload, str(profile.get("family", "")))
        domain_hit = 0.0
        soft_domain_matches: List[str] = []
        strict_domain_matches: List[str] = []
        family_domain = str(profile.get("domain", "")).strip().lower()
        if query_domains and payload_tags:
            for domain in query_domains:
                if payload_tags.intersection(DOMAIN_TAG_HINTS.get(domain, set())):
                    soft_domain_matches.append(domain)
                if family_domain and family_domain in DOMAIN_FAMILY_DOMAIN_HINTS.get(domain, set()):
                    strict_domain_matches.append(domain)
            soft_ratio = len(soft_domain_matches) / max(1, len(query_domains))
            strict_ratio = len(strict_domain_matches) / max(1, len(query_domains))
            domain_hit = min(1.0, 0.55 * soft_ratio + 0.45 * strict_ratio)

        domain_conflict_penalty = 0.0
        if query_domains:
            if not soft_domain_matches:
                domain_conflict_penalty = 0.55
            elif primary_query_domain and primary_query_domain not in soft_domain_matches:
                domain_conflict_penalty = 0.45
            elif (
                primary_query_domain
                and primary_query_domain not in PARENT_DOMAIN_GUARDS
                and primary_query_domain not in strict_domain_matches
            ):
                domain_conflict_penalty = 0.25

        parent_domain_penalty = 0.0
        if primary_query_domain in PARENT_DOMAIN_GUARDS:
            weak_specificity = (
                family_identity_hit == 0.0
                and model_match == 0.0
                and object_hit == 0.0
                and scene_hit < 0.34
            )
            if weak_specificity:
                parent_domain_penalty = 0.22

        anti_confusion_matches = self._query_value_matches(
            query_lower,
            query_term_set,
            list(profile.get("anti_confusion_words", [])),
        )
        anti_confusion_penalty = 0.0
        if anti_confusion_matches:
            anti_confusion_penalty = min(0.42, 0.16 * len(anti_confusion_matches))
            if (
                family_identity_hit == 0.0
                and model_match == 0.0
                and alias_hit < 0.5
                and object_hit == 0.0
                and scene_hit < 0.34
            ):
                anti_confusion_penalty = min(0.6, anti_confusion_penalty + 0.18)

        payload_type = str(payload.get("type", "")).lower()
        positive_signal = max(keyword_hit, object_hit, scene_hit, family_identity_hit, model_match, alias_hit)
        example_bonus = 0.08 if payload_type in {"example", "family_example"} and positive_signal > 0.0 else 0.0
        family_bonus = 0.05 if payload_type == "family_prototype" and max(object_hit, scene_hit, family_identity_hit) > 0.0 else 0.0
        phrase_bonus = 0.2 if query_lower in doc_lower else 0.0

        score = (
            0.18 * overlap
            + 0.18 * model_match
            + 0.16 * keyword_hit
            + 0.16 * alias_hit
            + 0.2 * domain_hit
            + 0.14 * family_identity_hit
            + 0.18 * object_hit
            + 0.14 * scene_hit
            + phrase_bonus
            + example_bonus
            + family_bonus
            - domain_conflict_penalty
            - parent_domain_penalty
            - anti_confusion_penalty
        )
        multiplier = 1.0
        if domain_conflict_penalty >= 0.5:
            multiplier *= 0.35
        elif domain_conflict_penalty >= 0.25:
            multiplier *= 0.7
        if parent_domain_penalty > 0.0:
            multiplier *= 0.78
        if anti_confusion_penalty >= 0.5:
            multiplier *= 0.5
        elif anti_confusion_penalty > 0.0:
            multiplier *= max(0.65, 1.0 - anti_confusion_penalty)
        return min(1.0, max(0.0, score)), max(0.2, min(1.0, multiplier))

    def _resolve_payload_family(self, payload: Dict[str, Any]) -> str:
        family = str(payload.get("template_family", "")).strip()
        if family:
            return family
        model_id = str(payload.get("model_id", "")).strip()
        if model_id:
            return str(self.model_by_id.get(model_id, {}).get("template_family", "")).strip()
        return ""

    def _resolve_trunk_family(self, family: str) -> str:
        family_name = str(family or "").strip()
        current_family = family_name
        visited: set[str] = set()
        while current_family and current_family not in visited:
            visited.add(current_family)
            meta = FAMILY_LIBRARY.get(current_family, {})
            if not meta:
                return current_family
            if str(meta.get("family_tier", "")).strip() == "trunk":
                return current_family
            parent_family = str(meta.get("parent_family", "")).strip()
            if not parent_family:
                return current_family
            current_family = parent_family
        return family_name

    def _resolve_acceptance_family(self, family: str) -> str:
        normalized = str(family or "").strip()
        if not normalized:
            return ""
        trunk_family = self._resolve_trunk_family(normalized)
        if trunk_family and trunk_family != normalized:
            return trunk_family
        override_family = str(FAMILY_ACCEPTANCE_OVERRIDES.get(normalized, "")).strip()
        if override_family:
            return override_family
        return normalized

    def infer_candidate_models(
        self,
        retrieved_docs: List[Dict[str, Any]],
        top_k: int = 3,
        selected_family: str = "",
    ) -> List[Dict[str, Any]]:
        selected_family = self._resolve_trunk_family(selected_family)
        score_map: Dict[str, float] = defaultdict(float)
        for item in retrieved_docs:
            payload = item.get("payload", {})
            model_id = str(payload.get("model_id", "")).strip()
            if not model_id:
                continue
            if selected_family:
                payload_family = self._resolve_trunk_family(self._resolve_payload_family(payload))
                if payload_family != selected_family:
                    continue
            score_map[model_id] += float(item.get("score", 0))

        if not score_map and selected_family:
            fallback_model = self.default_model_by_family.get(selected_family, {})
            fallback_model_id = str(fallback_model.get("model_id", "")).strip()
            if fallback_model_id:
                return [self._candidate_from_model_id(fallback_model_id)]
            return [self._candidate_from_family(selected_family)]

        if not score_map:
            return []

        ranked = sorted(score_map.items(), key=lambda x: x[1], reverse=True)[:top_k]
        results: List[Dict[str, Any]] = []
        for model_id, score in ranked:
            model = self.model_by_id.get(model_id, {})
            results.append(
                {
                    "model_id": model_id,
                    "score": round(score, 4),
                    "name": model.get("name", model_id),
                    "category": model.get("category", ""),
                    "template_family": model.get("template_family", ""),
                    "domain_tags": model.get("domain_tags", []),
                    "equation_fragments": model.get("equation_fragments", []),
                    "description": model.get("description", ""),
                }
            )
        return results


    def infer_candidate_families(
        self,
        query: str,
        retrieved_docs: List[Dict[str, Any]],
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        query_domain_scores = self._score_query_domains(query)
        ranked = self._aggregate_family_candidates(query, retrieved_docs, query_domain_scores)
        return ranked[:top_k]



    def assess_generation_match(self, query: str, retrieved_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        query_domains = self._detect_query_domains(query)
        primary_query_domain = query_domains[0] if query_domains else ""
        strong_query_domains = [domain for domain in query_domains if DOMAIN_PRIORITY.get(domain, 0) >= 7]

        manual_selection = self._extract_manual_generation_selection(query)
        explicit_model_id = str(manual_selection.get("model_id", "")).strip()
        explicit_family = str(manual_selection.get("template_family", "")).strip()

        if explicit_model_id and not explicit_family:
            explicit_family = str(self.model_by_id.get(explicit_model_id, {}).get("template_family", "")).strip()

        family_candidates = self.infer_candidate_families(query, retrieved_docs, top_k=3)
        selected_family = self._resolve_trunk_family(explicit_family) if explicit_family else ""
        if selected_family:
            explicit_family_item = next(
                (item for item in family_candidates if str(item.get("family", "")).strip() == selected_family),
                {},
            )
            if not explicit_family_item:
                explicit_family_item = {
                    "family": selected_family,
                    "score": 999.0,
                    "models": list(self.model_ids_by_family.get(selected_family, [])),
                    "domain": FAMILY_LIBRARY.get(selected_family, {}).get("domain", ""),
                    "family_tier": FAMILY_LIBRARY.get(selected_family, {}).get("family_tier", ""),
                    "matched_query_domains": query_domains[:1],
                    "domain_rank": 0 if query_domains else 999,
                    "domain_score": 999.0,
                    "doc_hits": 0,
                    "evidence_families": [explicit_family],
                }
            family_candidates = [explicit_family_item] + [
                item for item in family_candidates if str(item.get("family", "")).strip() != selected_family
            ]

        top_family_item = family_candidates[0] if family_candidates else {}
        selected_family = selected_family or str(top_family_item.get("family", "")).strip()
        candidates = self.infer_candidate_models(retrieved_docs, top_k=3, selected_family=selected_family)
        top_candidate = candidates[0] if candidates else {}

        if explicit_model_id:
            top_candidate = self._candidate_from_model_id(explicit_model_id)
            candidates = [top_candidate] + [item for item in candidates if item.get("model_id") != explicit_model_id]
        top_family = explicit_family or selected_family or str(top_candidate.get("template_family", "")).strip()
        if explicit_family:
            top_family = explicit_family
        top_score = float(top_candidate.get("score", 0.0) or 0.0)
        second_score = float(candidates[1].get("score", 0.0) or 0.0) if len(candidates) > 1 else 0.0
        total_score = sum(float(item.get("score", 0.0) or 0.0) for item in candidates[:3])
        top_share = top_score / total_score if total_score > 0 else 0.0
        gap_ratio = (top_score - second_score) / top_score if top_score > 0 else 0.0

        if explicit_family:
            top_family = explicit_family
            if not top_candidate or self._resolve_trunk_family(str(top_candidate.get("template_family", "")).strip()) != self._resolve_trunk_family(explicit_family):
                top_candidate = self._candidate_from_family(explicit_family, fallback=top_candidate)
                candidates = [top_candidate] + [
                    item
                    for item in candidates
                    if self._resolve_trunk_family(str(item.get("template_family", "")).strip()) != self._resolve_trunk_family(explicit_family)
                ]
        top_family_domain = str(FAMILY_LIBRARY.get(selected_family or top_family, {}).get("domain", "") or "").strip()
        family_top_score = float(top_family_item.get("score", 0.0) or 0.0)
        second_family_score = float(family_candidates[1].get("score", 0.0) or 0.0) if len(family_candidates) > 1 else 0.0
        family_total_score = sum(float(item.get("score", 0.0) or 0.0) for item in family_candidates[:3])
        family_top_share = family_top_score / family_total_score if family_total_score > 0 else 0.0
        family_gap_ratio = (family_top_score - second_family_score) / family_top_score if family_top_score > 0 else 0.0

        candidate_tags = self._candidate_domain_tags(top_candidate, top_family)
        matched_domains: List[str] = []
        conflicting_domains: List[str] = []
        for domain in query_domains:
            hints = DOMAIN_TAG_HINTS.get(domain, set())
            if candidate_tags.intersection(hints):
                matched_domains.append(domain)
            else:
                conflicting_domains.append(domain)

        matched_ratio = (len(matched_domains) / len(query_domains)) if query_domains else 1.0
        strict_matched_domains = [
            domain
            for domain in query_domains
            if top_family_domain and top_family_domain in DOMAIN_FAMILY_DOMAIN_HINTS.get(domain, set())
        ]
        strict_conflicting_domains = [domain for domain in query_domains if domain not in strict_matched_domains]
        matched_strong_domains = [domain for domain in strong_query_domains if domain in strict_matched_domains]
        keyword_hits = self._candidate_keyword_hits(query, top_candidate)

        has_manual_selection = bool(explicit_model_id or explicit_family)
        default_guardrail = {"triggered": False, "reason": "", "suggestions": [], "preferred_families": []}
        domain_conflict = (not has_manual_selection) and bool(query_domains) and (
            not strict_matched_domains
            or (len(strong_query_domains) > 1 and len(matched_strong_domains) < len(strong_query_domains))
            or (len(query_domains) == 1 and primary_query_domain in strict_conflicting_domains)
            or (len(query_domains) > 1 and len(strict_conflicting_domains) > len(strict_matched_domains) and matched_ratio < 0.5)
        )
        ambiguous_family = (not has_manual_selection) and len(family_candidates) > 1 and (
            (family_top_share < 0.62 and family_gap_ratio < 0.24)
            or family_top_share < 0.52
        )
        ambiguous_candidate = (not has_manual_selection) and len(candidates) > 1 and (
            (top_share < 0.58 and gap_ratio < 0.25)
            or top_share < 0.50
            or (gap_ratio < 0.12 and keyword_hits < 2)
        )
        low_confidence = (not has_manual_selection) and (
            not candidates
            or top_score <= 0
            or top_share < 0.34
            or family_top_share < 0.40
            or (keyword_hits == 0 and (not matched_domains or top_share < 0.55))
            or (top_share < 0.45 and keyword_hits < 2)
            or (family_top_share < 0.48 and keyword_hits < 2)
        )

        parent_domain_guard = self._assess_parent_domain_guard(
            query=query,
            query_domains=query_domains,
            primary_query_domain=primary_query_domain,
            top_family=top_family,
        )
        if has_manual_selection:
            parent_domain_guard = dict(default_guardrail)

        out_of_scope_guard = (
            self._assess_out_of_scope_guard(
                query=query,
                query_domains=query_domains,
                top_share=top_share,
                family_top_share=family_top_share,
                keyword_hits=keyword_hits,
                has_manual_selection=has_manual_selection,
            )
            if not parent_domain_guard.get("triggered", False)
            else dict(default_guardrail)
        )
        family_confirmation_guard = (
            self._assess_family_confirmation_gate(
                top_family=top_family,
                top_family_domain=top_family_domain,
                query_domains=query_domains,
                family_candidates=family_candidates,
                family_top_share=family_top_share,
                family_gap_ratio=family_gap_ratio,
                keyword_hits=keyword_hits,
            )
            if not has_manual_selection
            and not parent_domain_guard.get("triggered", False)
            and not out_of_scope_guard.get("triggered", False)
            else dict(default_guardrail)
        )
        if parent_domain_guard.get("triggered"):
            active_guardrail = parent_domain_guard
        elif out_of_scope_guard.get("triggered"):
            active_guardrail = out_of_scope_guard
        else:
            active_guardrail = family_confirmation_guard

        reject_reasons: List[str] = []
        if parent_domain_guard.get("triggered"):
            reject_reasons.append(str(parent_domain_guard.get("reason", "parent_domain_needs_object")))
        elif out_of_scope_guard.get("triggered"):
            reject_reasons.append(str(out_of_scope_guard.get("reason", "out_of_scope")))
        else:
            if family_confirmation_guard.get("triggered"):
                reject_reasons.append(str(family_confirmation_guard.get("reason", "family_needs_confirmation")))
            if not candidates:
                reject_reasons.append("no_candidate")
            if domain_conflict:
                reject_reasons.append("domain_conflict")
            if low_confidence and "no_candidate" not in reject_reasons:
                reject_reasons.append("low_confidence")
            if ambiguous_family and not family_confirmation_guard.get("triggered"):
                reject_reasons.append("ambiguous_family")
            if ambiguous_candidate:
                reject_reasons.append("ambiguous_candidate")

        should_generate = not reject_reasons
        reason = reject_reasons[0] if reject_reasons else "matched"
        clarify_stage = self._suggest_generation_clarify_stage(
            reject_reasons,
            top_family=top_family,
            family_candidates=family_candidates,
        )
        suggestions = self._build_clarify_suggestions(
            query_domains,
            candidates,
            family_candidates,
            reject_reasons,
            guardrail=active_guardrail,
        )
        trace = self._build_generation_match_trace(
            query_domains=query_domains,
            top_family=top_family,
            family_top_share=family_top_share,
            reject_reasons=reject_reasons,
            clarify_stage=clarify_stage,
            should_generate=should_generate,
        )
        self._log_generation_match_trace(trace)
        return {
            "should_generate": should_generate,
            "reason": reason,
            "reject_reasons": reject_reasons,
            "clarify_stage": clarify_stage,
            "query_domains": query_domains,
            "primary_query_domain": primary_query_domain,
            "matched_domains": matched_domains,
            "conflicting_domains": conflicting_domains,
            "strictly_matched_domains": strict_matched_domains,
            "strictly_conflicting_domains": strict_conflicting_domains,
            "top_candidate": top_candidate,
            "top_candidates": candidates,
            "top_family": top_family,
            "top_family_domain": top_family_domain,
            "family_candidates": family_candidates,
            "top_share": round(top_share, 4),
            "gap_ratio": round(gap_ratio, 4),
            "family_top_share": round(family_top_share, 4),
            "family_gap_ratio": round(family_gap_ratio, 4),
            "matched_ratio": round(matched_ratio, 4),
            "keyword_hits": keyword_hits,
            "suggestions": suggestions,
            "guardrail": active_guardrail,
            "top_trunk_family": top_family,
            "trunk_family_candidates": family_candidates,
            "trace": trace,
        }

    @staticmethod
    def _normalize_trace_list(values: Any) -> List[str]:
        if isinstance(values, (list, tuple, set)):
            return [str(item).strip() for item in values if str(item).strip()]
        if str(values or "").strip():
            return [str(values).strip()]
        return []

    def _suggest_generation_clarify_stage(
        self,
        reject_reasons: List[str],
        top_family: str = "",
        family_candidates: List[Dict[str, Any]] | None = None,
    ) -> str:
        normalized_reasons = self._normalize_trace_list(reject_reasons)
        if not normalized_reasons:
            return TRACE_CLARIFY_STAGE_READY
        if any(reason.endswith("_needs_object") or reason in TRACE_OBJECT_REASONS for reason in normalized_reasons):
            return TRACE_CLARIFY_STAGE_OBJECT
        if str(top_family or "").strip() or family_candidates:
            return TRACE_CLARIFY_STAGE_FAMILY
        return TRACE_CLARIFY_STAGE_OBJECT

    def _build_generation_match_trace(
        self,
        query_domains: List[str],
        top_family: str,
        family_top_share: float,
        reject_reasons: List[str],
        clarify_stage: str,
        should_generate: bool,
    ) -> Dict[str, Any]:
        return {
            "source": "rag_retriever",
            "event": "assess_generation_match",
            "query_domains": self._normalize_trace_list(query_domains),
            "top_family": str(top_family or "").strip(),
            "family_top_share": round(float(family_top_share or 0.0), 4),
            "reject_reasons": self._normalize_trace_list(reject_reasons),
            "clarify_stage": str(clarify_stage or TRACE_CLARIFY_STAGE_READY).strip(),
            "missing_slots": [],
            "should_generate": bool(should_generate),
            "final_generated": None,
        }

    def _log_generation_match_trace(self, trace: Dict[str, Any]) -> None:
        logger.info("generation_trace=%s", json.dumps(trace, ensure_ascii=False, sort_keys=True))

    def _extract_manual_generation_selection(self, query: str) -> Dict[str, str]:
        lowered = str(query or "").lower()
        model_match = re.search(r"model_id\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)", lowered)
        family_match = re.search(r"template_family\s*=\s*([a-zA-Z_][a-zA-Z0-9_]*)", lowered)
        model_id = model_match.group(1) if model_match else ""
        template_family = family_match.group(1) if family_match else ""
        if model_id and model_id not in self.model_by_id:
            model_id = ""
        if template_family and template_family not in FAMILY_LIBRARY:
            template_family = ""
        return {
            "model_id": model_id,
            "template_family": template_family,
        }

    def _candidate_from_model_id(self, model_id: str) -> Dict[str, Any]:
        model = dict(self.model_by_id.get(model_id, {}))
        if not model:
            return {}
        return {
            "model_id": model_id,
            "score": 999.0,
            "name": model.get("name", model_id),
            "category": model.get("category", ""),
            "template_family": model.get("template_family", ""),
            "domain_tags": model.get("domain_tags", []),
            "equation_fragments": model.get("equation_fragments", []),
            "description": model.get("description", ""),
        }

    def _candidate_from_family(self, family: str, fallback: Dict[str, Any] | None = None) -> Dict[str, Any]:
        for model_id, model in self.model_by_id.items():
            if str(model.get("template_family", "")).strip() == family:
                return self._candidate_from_model_id(model_id)
        candidate = dict(fallback or {})
        candidate["model_id"] = family
        candidate["name"] = family
        candidate["template_family"] = family
        candidate["score"] = max(float(candidate.get("score", 0.0) or 0.0), 999.0)
        candidate.setdefault("domain_tags", [])
        candidate.setdefault("equation_fragments", [])
        candidate.setdefault("description", "")
        candidate.setdefault("category", "")
        return candidate

    def _assess_parent_domain_guard(
        self,
        query: str,
        query_domains: List[str],
        primary_query_domain: str,
        top_family: str,
    ) -> Dict[str, Any]:
        active_domain = ""
        if primary_query_domain in PARENT_DOMAIN_GUARDS:
            active_domain = primary_query_domain
        else:
            for domain in query_domains:
                if domain in PARENT_DOMAIN_GUARDS:
                    active_domain = domain
                    break
        if not active_domain:
            return {"triggered": False, "reason": "", "suggestions": [], "preferred_families": []}

        config = PARENT_DOMAIN_GUARDS.get(active_domain, {})
        matched_groups = self._match_parent_object_groups(query, config)
        reason = f"{active_domain}_needs_object"

        if not matched_groups:
            return {
                "triggered": True,
                "reason": reason,
                "domain": active_domain,
                "matched_groups": [],
                "preferred_families": [],
                "suggestions": self._build_parent_domain_guard_suggestions(active_domain, config, []),
            }

        if len(matched_groups) > 1 and matched_groups[0]["hits"] == matched_groups[1]["hits"]:
            preferred_families = []
            for group in matched_groups[:2]:
                for family in group.get("families", []):
                    if family not in preferred_families:
                        preferred_families.append(family)
            return {
                "triggered": True,
                "reason": reason,
                "domain": active_domain,
                "matched_groups": matched_groups,
                "preferred_families": preferred_families,
                "suggestions": self._build_parent_domain_guard_suggestions(active_domain, config, matched_groups),
            }

        top_group = matched_groups[0]
        preferred_families = list(top_group.get("families", []))
        if top_family and preferred_families and top_family not in preferred_families:
            return {
                "triggered": True,
                "reason": reason,
                "domain": active_domain,
                "matched_groups": matched_groups,
                "preferred_families": preferred_families,
                "suggestions": self._build_parent_domain_guard_suggestions(active_domain, config, matched_groups),
            }

        top_family_tier = str(FAMILY_LIBRARY.get(top_family, {}).get("family_tier", "")).strip()
        if top_family and top_family_tier and top_family_tier != "trunk":
            return {
                "triggered": True,
                "reason": reason,
                "domain": active_domain,
                "matched_groups": matched_groups,
                "preferred_families": preferred_families,
                "suggestions": self._build_parent_domain_guard_suggestions(active_domain, config, matched_groups),
            }

        return {
            "triggered": False,
            "reason": "",
            "domain": active_domain,
            "matched_groups": matched_groups,
            "preferred_families": preferred_families,
            "suggestions": [],
        }

    def _detect_out_of_scope_topics(self, query: str) -> List[str]:
        lowered = (query or "").lower()
        query_terms = {term.lower() for term in _extract_terms(query)}
        matched_topics: List[str] = []
        for topic, keywords in OUT_OF_SCOPE_KEYWORDS.items():
            for keyword in keywords:
                normalized = str(keyword or "").lower().strip()
                if not normalized:
                    continue
                has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in normalized)
                is_phrase = " " in normalized or has_cjk or len(normalized) >= 10
                hit = normalized in lowered if is_phrase else (normalized in query_terms or normalized in lowered)
                if hit:
                    matched_topics.append(topic)
                    break
        return matched_topics

    def _assess_out_of_scope_guard(
        self,
        query: str,
        query_domains: List[str],
        top_share: float,
        family_top_share: float,
        keyword_hits: int,
        has_manual_selection: bool,
    ) -> Dict[str, Any]:
        if has_manual_selection:
            return {"triggered": False, "reason": "", "suggestions": [], "preferred_families": []}

        matched_topics = self._detect_out_of_scope_topics(query)
        no_supported_signal = not query_domains and keyword_hits == 0
        weak_candidate_signal = top_share < 0.48 and family_top_share < 0.48
        if not matched_topics or (not no_supported_signal and not weak_candidate_signal):
            return {"triggered": False, "reason": "", "suggestions": [], "preferred_families": []}

        topic_labels = [OUT_OF_SCOPE_TOPIC_LABELS.get(topic, topic) for topic in matched_topics]
        suggestions = [
            "\u5f53\u524d\u8bf7\u6c42\u66f4\u50cf\u662f " + " / ".join(topic_labels) + " \u95ee\u9898\uff0c\u4e0d\u5728\u5f53\u524d\u534a\u5f00\u653e\u57df MATLAB \u5efa\u6a21\u8303\u56f4\u5185\u3002",
            SUPPORTED_DOMAIN_SUMMARY,
            "\u5982\u679c\u4f60\u5e0c\u671b\u7ee7\u7eed\uff0c\u8bf7\u6539\u5199\u4e3a\u652f\u6301\u57df\u5185\u7684\u5177\u4f53\u5bf9\u8c61 + \u573a\u666f/\u4ecb\u8d28 + \u5173\u952e\u53c2\u6570\uff0c\u4f8b\u5982\u201c\u536b\u661f\u4e8c\u4f53\u8f68\u9053\u6a21\u578b\u201d\u201c\u9c7c\u96f7\u6c34\u4e0b\u53d1\u5c04\u6a21\u578b\u201d\u201c\u96f7\u8fbe\u76ee\u6807\u8ddf\u8e2a\u6a21\u578b\u201d\u3002",
        ]
        return {
            "triggered": True,
            "reason": "out_of_scope",
            "suggestions": suggestions,
            "preferred_families": [],
            "matched_topics": matched_topics,
        }

    def _assess_family_confirmation_gate(
        self,
        top_family: str,
        top_family_domain: str,
        query_domains: List[str],
        family_candidates: List[Dict[str, Any]],
        family_top_share: float,
        family_gap_ratio: float,
        keyword_hits: int,
    ) -> Dict[str, Any]:
        if not top_family:
            return {"triggered": False, "reason": "", "suggestions": [], "preferred_families": []}

        trusted_single_domain = (
            len(query_domains) == 1
            and bool(top_family_domain)
            and top_family_domain in DOMAIN_FAMILY_DOMAIN_HINTS.get(query_domains[0], set())
            and keyword_hits >= 2
            and family_top_share >= 0.56
            and family_gap_ratio >= 0.40
        )
        if trusted_single_domain:
            return {"triggered": False, "reason": "", "suggestions": [], "preferred_families": []}

        weak_family_signal = (
            (family_top_share < 0.60 and keyword_hits < 3)
            or (family_top_share < 0.66 and keyword_hits < 2)
            or (family_gap_ratio < 0.35 and keyword_hits < 2)
        )
        if not weak_family_signal:
            return {"triggered": False, "reason": "", "suggestions": [], "preferred_families": []}

        preferred_families = [item.get("family", "") for item in family_candidates[:3] if item.get("family")]
        suggestions: List[str] = []
        if preferred_families:
            suggestions.append(
                "\u5f53\u524d family \u8fd8\u4e0d\u591f\u7a33\u5b9a\uff0c\u8bf7\u5148\u5728\u8fd9\u4e9b\u6a21\u578b\u65cf\u4e2d\u786e\u8ba4\u4e00\u4e2a\uff1a" + " / ".join(preferred_families) + "\u3002"
            )
            suggestions.append(
                "\u5982\u679c\u4f60\u5df2\u786e\u8ba4\u6a21\u578b\u65cf\uff0c\u53ef\u4ee5\u76f4\u63a5\u8bf4\u660e `template_family=" + preferred_families[0] + "`\u3002"
            )
        else:
            suggestions.append("\u5f53\u524d family \u7f6e\u4fe1\u5ea6\u4e0d\u8db3\uff0c\u8bf7\u5148\u8865\u5145\u5bf9\u8c61\u3001\u4ecb\u8d28\u73af\u5883\u548c\u5173\u952e\u4f5c\u7528\u529b\u540e\u518d\u751f\u6210\u3002")
        return {
            "triggered": True,
            "reason": "family_needs_confirmation",
            "suggestions": suggestions,
            "preferred_families": preferred_families,
        }

    def _match_parent_object_groups(self, query: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        lowered = (query or "").lower()
        terms = {term.lower() for term in _extract_terms(query)}
        matched: List[Dict[str, Any]] = []
        for group in config.get("object_groups", []):
            matched_keywords: List[str] = []
            for keyword in group.get("keywords", []):
                normalized = str(keyword or "").lower().strip()
                if not normalized:
                    continue
                if normalized in lowered or normalized in terms:
                    matched_keywords.append(str(keyword))
            if matched_keywords:
                item = dict(group)
                item["hits"] = len(matched_keywords)
                item["matched_keywords"] = matched_keywords
                matched.append(item)
        matched.sort(key=lambda item: (-int(item.get("hits", 0)), item.get("label", "")))
        return matched

    def _build_parent_domain_guard_suggestions(
        self,
        domain: str,
        config: Dict[str, Any],
        matched_groups: List[Dict[str, Any]],
    ) -> List[str]:
        suggestions: List[str] = []

        def append_unique(message: str) -> None:
            if message and message not in suggestions:
                suggestions.append(message)

        append_unique(str(config.get("clarify_prompt", "")).strip())
        labels = [group.get("label", "") for group in (matched_groups or config.get("object_groups", []))[:5] if group.get("label")]
        if labels:
            append_unique("请先明确对象属于以下哪一类：" + " / ".join(labels) + "。")

        for group in (matched_groups or config.get("object_groups", []))[:3]:
            families = [family for family in group.get("families", []) if family]
            if not families:
                continue
            append_unique(
                "如果你的对象更接近“"
                + str(group.get("label", ""))
                + "”，可以直接说明 `template_family="
                + families[0]
                + "`。"
            )

        if domain == "battlefield_situation":
            append_unique("战场态势父域默认不直接落具体 family，必须先确认是态势感知、威胁评估、雷达跟踪、兵力消耗还是齐射拦截。")
        if domain == "military_equipment":
            append_unique("军工装备父域默认不直接落具体 family，必须先确认对象是鱼雷/潜艇、导弹/火箭、雷达跟踪、卫星轨道还是战场对抗。")
        return suggestions[:5]

    def _query_contains_domain_keyword(
        self,
        lowered: str,
        query_terms: set[str],
        keyword: str,
    ) -> bool:
        normalized = keyword.lower().strip()
        if not normalized:
            return False
        has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in normalized)
        is_phrase = " " in normalized or has_cjk or len(normalized) >= 10
        return normalized in lowered if is_phrase else (normalized in query_terms or normalized in lowered)

    def _match_query_domain_bucket(
        self,
        lowered: str,
        query_terms: set[str],
        keywords: Tuple[str, ...],
    ) -> List[str]:
        matches: List[str] = []
        seen: set[str] = set()
        for keyword in keywords:
            normalized = keyword.lower().strip()
            if not normalized or normalized in seen:
                continue
            if self._query_contains_domain_keyword(lowered, query_terms, normalized):
                seen.add(normalized)
                matches.append(normalized)
        return matches

    def _query_domain_bucket_score(self, keywords: List[str], bucket: str) -> int:
        score = 0
        for keyword in keywords:
            has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in keyword)
            is_phrase = " " in keyword or len(keyword) >= 10 or (has_cjk and len(keyword) >= 3)
            if bucket == "object":
                score += 5 if is_phrase else 4
            elif bucket == "scene":
                score += 3 if is_phrase else 2
            elif bucket == "noise":
                score += 2 if is_phrase else 1
            else:
                score += 2 if is_phrase else 1
        return score

    def _score_query_domains(self, query: str) -> List[Tuple[str, int]]:
        lowered = (query or "").lower()
        query_terms = {term.lower() for term in _extract_terms(query)}
        scored_with_signals: List[Tuple[str, int, bool, bool, bool]] = []
        best_specific_score = 0

        for domain, keywords in DOMAIN_KEYWORDS.items():
            buckets = QUERY_DOMAIN_KEYWORD_BUCKETS.get(domain, {})
            object_matches = self._match_query_domain_bucket(
                lowered,
                query_terms,
                tuple(buckets.get("object", ())),
            )
            scene_matches = self._match_query_domain_bucket(
                lowered,
                query_terms,
                tuple(buckets.get("scene", ())),
            )
            noise_matches = self._match_query_domain_bucket(
                lowered,
                query_terms,
                tuple(buckets.get("noise", ())),
            )

            bucket_terms = set(object_matches) | set(scene_matches) | set(noise_matches)
            fallback_matches: List[str] = []
            for keyword in keywords:
                normalized = keyword.lower().strip()
                if not normalized or normalized in bucket_terms:
                    continue
                if self._query_contains_domain_keyword(lowered, query_terms, normalized):
                    fallback_matches.append(normalized)

            score = 0
            score += self._query_domain_bucket_score(object_matches, "object")
            score += self._query_domain_bucket_score(scene_matches, "scene")
            score += self._query_domain_bucket_score(noise_matches, "noise")
            score += self._query_domain_bucket_score(fallback_matches, "fallback")

            if object_matches and scene_matches:
                score += 4
            elif len(object_matches) >= 2:
                score += 2
            elif len(scene_matches) >= 2:
                score += 1

            has_object = bool(object_matches)
            has_scene = bool(scene_matches)
            has_noise = bool(noise_matches)
            if domain in QUERY_DOMAIN_PARENT_DOMAINS and not has_object and not has_scene:
                score = min(score, 2)

            if score > 0:
                if has_object or has_scene:
                    best_specific_score = max(best_specific_score, score)
                scored_with_signals.append((domain, score, has_object, has_scene, has_noise))

        scored: List[Tuple[str, int]] = []
        for domain, score, has_object, has_scene, has_noise in scored_with_signals:
            if (
                domain in QUERY_DOMAIN_PARENT_DOMAINS
                and has_noise
                and not has_object
                and not has_scene
                and best_specific_score > score
            ):
                continue
            scored.append((domain, score))

        scored.sort(key=lambda item: (-item[1], -DOMAIN_PRIORITY.get(item[0], 0), item[0]))
        return scored


    def _detect_query_domains(self, query: str) -> List[str]:
        return [domain for domain, _ in self._score_query_domains(query)]

    def _aggregate_family_candidates(
        self,
        query: str,
        retrieved_docs: List[Dict[str, Any]],
        query_domain_scores: List[Tuple[str, int]] | None = None,
    ) -> List[Dict[str, Any]]:
        family_scores: Dict[str, float] = defaultdict(float)
        family_query_scores: Dict[str, float] = defaultdict(float)
        family_retrieval_scores: Dict[str, float] = defaultdict(float)
        family_models: Dict[str, List[str]] = defaultdict(list)
        family_evidence: Dict[str, List[str]] = defaultdict(list)
        family_doc_hits: Dict[str, int] = defaultdict(int)
        query_domain_scores = query_domain_scores or []
        query_terms = [term.lower() for term in _extract_terms(query)]

        for raw_family, doc in self._family_prototype_docs.items():
            acceptance_family = self._resolve_acceptance_family(raw_family)
            if not acceptance_family:
                continue
            rerank_score, rerank_multiplier = self._rerank_score(query, query_terms, doc)
            query_score = round(float(rerank_score or 0.0) * float(rerank_multiplier or 0.0), 4)
            if query_score <= 0:
                continue
            family_query_scores[acceptance_family] = max(
                family_query_scores[acceptance_family],
                query_score,
            )
            if raw_family not in family_evidence[acceptance_family]:
                family_evidence[acceptance_family].append(raw_family)

        raw_family_retrieval_scores: Dict[str, float] = defaultdict(float)
        raw_family_doc_hits: Dict[str, int] = defaultdict(int)
        for item in retrieved_docs:
            payload = item.get("payload", {})
            raw_family = self._resolve_payload_family(payload)
            if not raw_family:
                continue
            acceptance_family = self._resolve_acceptance_family(raw_family)
            if not acceptance_family:
                continue
            raw_family_doc_hits[raw_family] += 1
            raw_family_retrieval_scores[raw_family] = max(
                raw_family_retrieval_scores[raw_family],
                float(item.get("score", 0.0) or 0.0),
            )
            family_doc_hits[acceptance_family] += 1
            if raw_family not in family_evidence[acceptance_family]:
                family_evidence[acceptance_family].append(raw_family)
            model_id = str(payload.get("model_id", "")).strip()
            if model_id and model_id not in family_models[acceptance_family]:
                family_models[acceptance_family].append(model_id)

        for raw_family, raw_score in raw_family_retrieval_scores.items():
            acceptance_family = self._resolve_acceptance_family(raw_family)
            if not acceptance_family:
                continue
            family_retrieval_scores[acceptance_family] += round(raw_score * 0.18, 4)

        candidate_families: set[str] = set()
        candidate_families.update(family_query_scores.keys())
        candidate_families.update(family_retrieval_scores.keys())
        for family in SLOT_SCHEMAS.keys():
            acceptance_family = self._resolve_acceptance_family(family)
            if not acceptance_family:
                continue
            family_domain = str(FAMILY_LIBRARY.get(acceptance_family, {}).get("domain", "")).strip()
            if any(
                family_domain and family_domain in DOMAIN_FAMILY_DOMAIN_HINTS.get(query_domain, set())
                for query_domain, _ in query_domain_scores
            ):
                candidate_families.add(acceptance_family)

        ranked: List[Dict[str, Any]] = []
        for family in candidate_families:
            meta = FAMILY_LIBRARY.get(family, {})
            family_domain = str(meta.get("domain", "")).strip()
            matched_query_domains: List[str] = []
            domain_rank = 999
            domain_score = 0.0
            for index, (query_domain, query_domain_score) in enumerate(query_domain_scores):
                if family_domain and family_domain in DOMAIN_FAMILY_DOMAIN_HINTS.get(query_domain, set()):
                    matched_query_domains.append(query_domain)
                    domain_rank = min(domain_rank, index)
                    domain_score = max(domain_score, float(query_domain_score))
            query_score = float(family_query_scores.get(family, 0.0) or 0.0)
            retrieval_score = float(family_retrieval_scores.get(family, 0.0) or 0.0)
            retrieval_cap = query_score + (0.05 if matched_query_domains else 0.0)
            if retrieval_cap >= 0.0:
                retrieval_score = min(retrieval_score, retrieval_cap)
            domain_bonus = 0.0
            if matched_query_domains:
                domain_bonus = 0.8 + min(0.5, domain_score / 10.0)
            score = round(query_score * 3.0 + retrieval_score + domain_bonus, 4)
            ranked.append(
                {
                    "family": family,
                    "score": score,
                    "models": family_models.get(family, []),
                    "domain": family_domain,
                    "family_tier": str(meta.get("family_tier", "")).strip(),
                    "matched_query_domains": matched_query_domains,
                    "domain_rank": domain_rank,
                    "domain_score": round(domain_score, 4),
                    "doc_hits": family_doc_hits.get(family, 0),
                    "evidence_families": family_evidence.get(family, []),
                    "query_score": round(query_score, 4),
                    "retrieval_score": round(retrieval_score, 4),
                }
            )
        ranked.sort(
            key=lambda item: (
                0 if item.get("matched_query_domains") else 1,
                int(item.get("domain_rank", 999)) if item.get("domain_rank", None) is not None else 999,
                -float(item.get("domain_score", 0.0) or 0.0),
                -float(item.get("query_score", 0.0) or 0.0),
                0 if str(item.get("family_tier", "")).strip() == "trunk" else 1,
                -float(item.get("score", 0.0) or 0.0),
                -float(item.get("retrieval_score", 0.0) or 0.0),
                -int(item.get("doc_hits", 0) or 0),
                str(item.get("family", "")),
            )
        )
        return ranked


    def _candidate_domain_tags(self, candidate: Dict[str, Any], family: str) -> set[str]:
        candidate_tags = {str(tag).lower() for tag in candidate.get("domain_tags", [])}
        if family:
            candidate_tags.add(family.lower())
            family_domain = str(FAMILY_LIBRARY.get(family, {}).get("domain", "")).lower().strip()
            if family_domain:
                candidate_tags.add(family_domain)
        return candidate_tags


    def _candidate_keyword_hits(self, query: str, candidate: Dict[str, Any]) -> int:
        model_id = str(candidate.get("model_id", "")).strip()
        model_meta = self.model_by_id.get(model_id, {})
        lowered = (query or "").lower()
        terms = {term.lower() for term in _extract_terms(query)}
        hits = 0
        for keyword in model_meta.get("keywords", []):
            normalized = str(keyword or "").lower().strip()
            if not normalized:
                continue
            if normalized in lowered or normalized in terms:
                hits += 1
        return hits


    def _build_clarify_suggestions(
        self,
        query_domains: List[str],
        candidates: List[Dict[str, Any]],
        family_candidates: List[Dict[str, Any]],
        reject_reasons: List[str],
        guardrail: Dict[str, Any] | None = None,
    ) -> List[str]:
        suggestions: List[str] = []
        domain_set = set(query_domains)
        guardrail = guardrail or {}

        def append_unique(message: str) -> None:
            if message and message not in suggestions:
                suggestions.append(message)

        for message in guardrail.get("suggestions", []):
            append_unique(str(message))

        if "out_of_scope" in reject_reasons:
            append_unique(SUPPORTED_DOMAIN_SUMMARY)
            append_unique("\u5982\u679c\u4f60\u8981\u7ee7\u7eed\uff0c\u8bf7\u628a\u95ee\u9898\u6536\u655b\u5230\u5f53\u524d\u652f\u6301\u57df\u5185\u7684\u5177\u4f53\u5bf9\u8c61\u3001\u573a\u666f\u548c\u5173\u952e\u53c2\u6570\u3002")
            return suggestions[:5]

        if "domain_conflict" in reject_reasons:
            append_unique("\u8bf7\u5148\u660e\u786e\u4e3b\u5efa\u6a21\u5c42\u7ea7\uff1a\u662f\u98de\u884c/\u8f68\u9053\u52a8\u529b\u5b66\u3001\u5236\u5bfc\u8ddf\u8e2a\uff0c\u8fd8\u662f\u6218\u573a\u6001\u52bf\u8bc4\u4f30\u3002")
        if "low_confidence" in reject_reasons:
            append_unique("\u8bf7\u8865\u5145\u5efa\u6a21\u5bf9\u8c61\u3001\u8fd0\u52a8\u4ecb\u8d28\u3001\u5173\u952e\u4f5c\u7528\u529b\u548c\u671f\u671b\u8f93\u51fa\uff0c\u4ee5\u4fbf\u7a33\u5b9a\u9501\u5b9a\u6a21\u578b\u65cf\u3002")
        if "family_needs_confirmation" in reject_reasons:
            append_unique("\u5f53\u524d top family \u8fd8\u4e0d\u591f\u7a33\uff0c\u8bf7\u5148\u786e\u8ba4\u5bf9\u8c61\u6216\u76f4\u63a5\u6307\u5b9a template_family\u3002")
        if "ambiguous_family" in reject_reasons and family_candidates:
            family_labels = [item.get("family", "") for item in family_candidates[:3] if item.get("family")]
            if family_labels:
                append_unique("\u5f53\u524d\u5019\u9009\u6a21\u578b\u65cf\u63a5\u8fd1\uff1a" + " / ".join(family_labels) + "\u3002\u8bf7\u76f4\u63a5\u6307\u5b9a\u4e00\u4e2a template_family\u3002")
        if "ambiguous_candidate" in reject_reasons and candidates:
            candidate_names = [f"{item.get('model_id', '')}" for item in candidates[:3] if item.get("model_id")]
            if candidate_names:
                append_unique("\u5f53\u524d\u5019\u9009\u6a21\u578b\u63a5\u8fd1\uff1a" + " / ".join(candidate_names) + "\u3002\u8bf7\u76f4\u63a5\u6307\u5b9a\u4e00\u4e2a model_id\u3002")

        if len(query_domains) > 1:
            for combo, hint in DOMAIN_COMBINATION_HINTS:
                if set(combo).issubset(domain_set):
                    append_unique(hint)
            domain_labels = [DOMAIN_LABELS.get(domain, domain) for domain in query_domains[:3]]
            append_unique("\u5f53\u524d\u8bf7\u6c42\u540c\u65f6\u5305\u542b " + "\u3001".join(domain_labels) + " \u7ebf\u7d22\uff0c\u8bf7\u5148\u8bf4\u660e\u4e3b\u5efa\u6a21\u5bf9\u8c61\u3002")

        for domain in query_domains[:3]:
            hint = DOMAIN_CLARIFY_HINTS.get(domain)
            if hint:
                append_unique(hint)

        for candidate in candidates[:2]:
            model_id = candidate.get("model_id", "")
            model_name = candidate.get("name", model_id)
            family = candidate.get("template_family", "")
            if model_id:
                append_unique(f"\u5982\u679c\u4f60\u5df2\u786e\u8ba4\u4f7f\u7528 {model_name}\uff0c\u53ef\u4ee5\u76f4\u63a5\u8bf4\u660e `model_id={model_id}`\u3002")
            if family:
                append_unique(f"\u5982\u679c\u4f60\u66f4\u60f3\u6309\u6a21\u578b\u65cf\u6f84\u6e05\uff0c\u53ef\u4ee5\u76f4\u63a5\u8bf4\u660e `template_family={family}`\u3002")

        if not suggestions:
            append_unique("\u8bf7\u8865\u5145\u5efa\u6a21\u5bf9\u8c61\u3001\u73af\u5883\u4ecb\u8d28\u3001\u5173\u952e\u52a8\u529b\u5b66\u56e0\u7d20\u548c\u671f\u671b\u8f93\u51fa\uff0c\u6211\u518d\u4e3a\u4f60\u751f\u6210 MATLAB \u811a\u672c\u3002")
        return suggestions[:5]
    def get_model_defaults(self, model_id: str) -> Dict[str, Any]:
        return dict(self.model_by_id.get(model_id, {}).get("default_params", {}))


    def list_supported_models(self) -> List[Dict[str, Any]]:
        return self.catalog

def _extract_terms(text: str) -> List[str]:
    terms = re.findall(r"[A-Za-z_]+|[\u4e00-\u9fff]{1,4}|\d+(?:\.\d+)?", text)
    dedup: List[str] = []
    seen = set()
    for t in terms:
        key = t.lower()
        if key not in seen:
            seen.add(key)
            dedup.append(t)
    return dedup


def _normalize_score_map(scores: Dict[int, float]) -> Dict[int, float]:
    if not scores:
        return {}
    values = list(scores.values())
    min_v = min(values)
    max_v = max(values)
    if abs(max_v - min_v) < 1e-12:
        return {k: 1.0 for k in scores}
    return {k: (v - min_v) / (max_v - min_v) for k, v in scores.items()}


def _top_keys(score_map: Dict[int, float], top_n: int) -> List[int]:
    return [k for k, _ in sorted(score_map.items(), key=lambda x: x[1], reverse=True)[:top_n]]


def _safe_to_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None
