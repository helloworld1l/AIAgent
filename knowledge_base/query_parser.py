"""
将自然语言查询解析为可执行的结构化筛选条件。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from knowledge_base.conditions_data import FIELD_ALIASES, FIELD_VALUE_SYNONYMS


DATE_FORMAT = "%Y-%m-%d"
DATE_FIELDS = {"create_time", "last_contact_time"}


def parse_query_filters(question: str) -> List[Dict[str, Any]]:
    """解析自然语言查询为过滤条件。"""
    text = (question or "").strip()
    if not text:
        return []

    filters: List[Dict[str, Any]] = []

    amount_filter = _parse_order_amount_filter(text)
    if amount_filter:
        filters.append(amount_filter)

    create_time_filter = _parse_create_time_filter(text)
    if create_time_filter:
        filters.append(create_time_filter)

    last_contact_filter = _parse_last_contact_filter(text)
    if last_contact_filter:
        filters.append(last_contact_filter)

    for field in (
        "customer_source",
        "customer_status",
        "customer_level",
        "follow_up_status",
        "region",
        "industry",
        "tags",
    ):
        if field == "follow_up_status" and not _has_follow_up_hint(text):
            continue
        condition = _parse_categorical_filter(text, field)
        if condition:
            filters.append(condition)

    return _deduplicate(filters)


def _parse_order_amount_filter(text: str) -> Optional[Dict[str, Any]]:
    if not any(keyword in text for keyword in FIELD_ALIASES["order_amount"]):
        return None

    between_match = re.search(
        r"(?:金额|订单金额|消费金额|付款金额|已付款金额).{0,10}?(?:介于|在)?\s*"
        r"([0-9]+(?:\.[0-9]+)?(?:万|千)?)\s*(?:到|至|~|-)\s*([0-9]+(?:\.[0-9]+)?(?:万|千)?)",
        text,
    )
    if between_match:
        left = _parse_number_token(between_match.group(1))
        right = _parse_number_token(between_match.group(2))
        if left is not None and right is not None:
            low, high = sorted([left, right])
            return {"field": "order_amount", "operator": "在...之间", "value": [low, high]}

    patterns = [
        ("大于等于", r"(?:不少于|不低于|至少|>=)\s*([0-9]+(?:\.[0-9]+)?(?:万|千)?)"),
        ("小于等于", r"(?:不超过|不高于|至多|<=)\s*([0-9]+(?:\.[0-9]+)?(?:万|千)?)"),
        ("大于", r"(?:大于|高于|超过|>)\s*([0-9]+(?:\.[0-9]+)?(?:万|千)?)"),
        ("小于", r"(?:小于|低于|<)\s*([0-9]+(?:\.[0-9]+)?(?:万|千)?)"),
        ("等于", r"(?:等于|为|=)\s*([0-9]+(?:\.[0-9]+)?(?:万|千)?)"),
    ]
    for operator, pattern in patterns:
        matched = re.search(pattern, text)
        if matched:
            amount = _parse_number_token(matched.group(1))
            if amount is not None:
                return {"field": "order_amount", "operator": operator, "value": amount}

    direct_amount = re.search(r"([0-9]+(?:\.[0-9]+)?(?:万|千)?)", text)
    if direct_amount:
        amount = _parse_number_token(direct_amount.group(1))
        if amount is not None:
            return {"field": "order_amount", "operator": "大于", "value": amount}

    return None


def _parse_create_time_filter(text: str) -> Optional[Dict[str, Any]]:
    has_create_hint = any(alias in text for alias in FIELD_ALIASES["create_time"]) or any(
        token in text for token in ["创建", "录入", "建档", "新增"]
    )
    if not has_create_hint and ("联系" in text or "跟进" in text):
        return None
    if not _has_time_hint(text):
        return None

    date_range = _extract_custom_date_range(text)
    if date_range:
        start, end = date_range
        return {"field": "create_time", "operator": "在范围内", "value": [start, end]}

    phrase_ranges = {
        "今天": _today_range,
        "昨日": _yesterday_range,
        "昨天": _yesterday_range,
        "本周": _this_week_range,
        "这周": _this_week_range,
        "上周": _last_week_range,
        "本月": _this_month_range,
        "这个月": _this_month_range,
        "上月": _last_month_range,
        "上个月": _last_month_range,
        "本季度": _this_quarter_range,
        "今年": _this_year_range,
    }
    for phrase, fn in phrase_ranges.items():
        if phrase in text:
            start, end = fn()
            return {"field": "create_time", "operator": "在范围内", "value": [start, end]}

    recent_match = re.search(r"最近\s*(\d{1,3})\s*天", text)
    if recent_match:
        days = int(recent_match.group(1))
        start = (datetime.now() - timedelta(days=days)).strftime(DATE_FORMAT)
        end = datetime.now().strftime(DATE_FORMAT)
        return {"field": "create_time", "operator": "在范围内", "value": [start, end]}

    if "近一周" in text:
        start = (datetime.now() - timedelta(days=7)).strftime(DATE_FORMAT)
        end = datetime.now().strftime(DATE_FORMAT)
        return {"field": "create_time", "operator": "在范围内", "value": [start, end]}

    return None


def _parse_last_contact_filter(text: str) -> Optional[Dict[str, Any]]:
    has_contact_hint = any(alias in text for alias in FIELD_ALIASES["last_contact_time"])
    has_neg_contact = ("联系" in text and ("未联系" in text or "没有联系" in text))
    if not (has_contact_hint or has_neg_contact):
        return None

    if "从未联系" in text or "从来没联系" in text:
        return {"field": "last_contact_time", "operator": "是空", "value": None}

    long_uncontacted = re.search(r"(?:超过|超出)\s*(\d{1,3})\s*天未联系", text)
    if long_uncontacted:
        return {
            "field": "last_contact_time",
            "operator": "超过天未联系",
            "value": int(long_uncontacted.group(1)),
        }

    recent_not_contacted = re.search(r"最近\s*(\d{1,3})\s*天(?:没有|未)联系", text)
    if recent_not_contacted:
        return {
            "field": "last_contact_time",
            "operator": "超过天未联系",
            "value": int(recent_not_contacted.group(1)),
        }

    recent_contacted = re.search(r"(?:最近|近)\s*(\d{1,3})\s*天.*联系", text)
    if recent_contacted and "未联系" not in text and "没有联系" not in text:
        return {
            "field": "last_contact_time",
            "operator": "在最近天内",
            "value": int(recent_contacted.group(1)),
        }

    phrase_days = {
        "一周内": 7,
        "7天内": 7,
        "一个月内": 30,
        "30天内": 30,
        "三个月内": 90,
        "90天内": 90,
        "半年内": 180,
    }
    for phrase, days in phrase_days.items():
        if phrase in text:
            return {"field": "last_contact_time", "operator": "在最近天内", "value": days}

    return None


def _parse_categorical_filter(text: str, field: str) -> Optional[Dict[str, Any]]:
    matched_value = _match_field_value(field, text)
    if matched_value is None:
        return None

    operator = "不等于" if _contains_negation(text, matched_value) else "等于"
    if field == "tags":
        operator = "包含" if operator == "等于" else "不等于"

    return {"field": field, "operator": operator, "value": matched_value}


def _match_field_value(field: str, text: str) -> Optional[str]:
    value_synonyms = FIELD_VALUE_SYNONYMS.get(field, {})
    if value_synonyms:
        for alias in sorted(value_synonyms.keys(), key=len, reverse=True):
            if alias and alias in text.lower():
                return value_synonyms[alias]

    if field in ("region", "industry"):
        values = _known_values_by_field(field)
        for item in sorted(values, key=len, reverse=True):
            if item in text:
                return item

    condition_aliases = FIELD_ALIASES.get(field, [])
    for alias in sorted(condition_aliases, key=len, reverse=True):
        pattern = re.compile(rf"{re.escape(alias)}(?:为|是|等于|=|包含)?\s*([^\s,，。；;]+)")
        matched = pattern.search(text)
        if matched:
            return matched.group(1)

    return None


def _known_values_by_field(field: str) -> List[str]:
    if field == "region":
        return ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安", "重庆"]
    if field == "industry":
        return ["IT", "金融", "教育", "医疗", "零售", "制造", "房地产", "咨询", "媒体", "物流"]
    return []


def _contains_negation(text: str, value: str) -> bool:
    value_pattern = re.escape(value)
    negative_patterns = [
        rf"(不等于|不是|非)\s*{value_pattern}",
        rf"{value_pattern}\s*(以外|之外)",
    ]
    return any(re.search(pattern, text) for pattern in negative_patterns)


def _extract_custom_date_range(text: str) -> Optional[Tuple[str, str]]:
    date_regex = (
        r"((?:20\d{2})[-/年](?:0?[1-9]|1[0-2])[-/月](?:0?[1-9]|[12]\d|3[01])日?)"
        r"\s*(?:到|至|~|-)\s*"
        r"((?:20\d{2})[-/年](?:0?[1-9]|1[0-2])[-/月](?:0?[1-9]|[12]\d|3[01])日?)"
    )
    matched = re.search(date_regex, text)
    if not matched:
        return None

    left = _normalize_date(matched.group(1))
    right = _normalize_date(matched.group(2))
    if left is None or right is None:
        return None
    start, end = sorted([left, right])
    return start, end


def _normalize_date(raw: str) -> Optional[str]:
    clean = raw.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-")
    try:
        dt = datetime.strptime(clean, DATE_FORMAT)
        return dt.strftime(DATE_FORMAT)
    except ValueError:
        return None


def _parse_number_token(token: str) -> Optional[float]:
    token = token.strip()
    multiplier = 1.0
    if token.endswith("万"):
        multiplier = 10000.0
        token = token[:-1]
    elif token.endswith("千"):
        multiplier = 1000.0
        token = token[:-1]

    try:
        return float(token) * multiplier
    except ValueError:
        return None


def _has_time_hint(text: str) -> bool:
    hints = [
        "创建",
        "录入",
        "建档",
        "本周",
        "上周",
        "本月",
        "上月",
        "最近",
        "今天",
        "昨天",
        "今年",
    ]
    return any(hint in text for hint in hints)


def _has_follow_up_hint(text: str) -> bool:
    hints = ["跟进", "回访", "联系状态", "跟进状态", "回访状态"]
    return any(hint in text for hint in hints)


def _today_range() -> Tuple[str, str]:
    today = datetime.now().strftime(DATE_FORMAT)
    return today, today


def _yesterday_range() -> Tuple[str, str]:
    day = (datetime.now() - timedelta(days=1)).strftime(DATE_FORMAT)
    return day, day


def _this_week_range() -> Tuple[str, str]:
    now = datetime.now()
    start = now - timedelta(days=now.weekday())
    return start.strftime(DATE_FORMAT), now.strftime(DATE_FORMAT)


def _last_week_range() -> Tuple[str, str]:
    now = datetime.now()
    this_week_start = now - timedelta(days=now.weekday())
    last_week_start = this_week_start - timedelta(days=7)
    last_week_end = this_week_start - timedelta(days=1)
    return last_week_start.strftime(DATE_FORMAT), last_week_end.strftime(DATE_FORMAT)


def _this_month_range() -> Tuple[str, str]:
    now = datetime.now()
    start = now.replace(day=1)
    return start.strftime(DATE_FORMAT), now.strftime(DATE_FORMAT)


def _last_month_range() -> Tuple[str, str]:
    now = datetime.now()
    this_month_start = now.replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    return last_month_start.strftime(DATE_FORMAT), last_month_end.strftime(DATE_FORMAT)


def _this_quarter_range() -> Tuple[str, str]:
    now = datetime.now()
    quarter = (now.month - 1) // 3
    start_month = quarter * 3 + 1
    start = now.replace(month=start_month, day=1)
    return start.strftime(DATE_FORMAT), now.strftime(DATE_FORMAT)


def _this_year_range() -> Tuple[str, str]:
    now = datetime.now()
    start = now.replace(month=1, day=1)
    return start.strftime(DATE_FORMAT), now.strftime(DATE_FORMAT)


def _deduplicate(filters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique: List[Dict[str, Any]] = []
    for item in filters:
        key = (
            item.get("field"),
            item.get("operator"),
            str(item.get("value")),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
