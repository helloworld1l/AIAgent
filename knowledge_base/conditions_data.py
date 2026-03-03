"""
CRM 筛选条件知识库定义。

说明：
- CRM_FILTER_CONDITIONS: 对外暴露给 API / 条件检索的结构化字段定义。
- FIELD_ALIASES: 字段同义词，用于自然语言解析。
- FIELD_VALUE_SYNONYMS: 值同义词 -> 数据库标准值映射。
- FIELD_VALUE_DISPLAY: 数据库标准值 -> 展示中文映射。
"""

CRM_FILTER_CONDITIONS = [
    {
        "field": "customer_source",
        "name": "客户来源",
        "description": "客户获客渠道",
        "operators": ["等于", "不等于", "包含"],
        "params": ["百度", "腾讯广告", "谷歌搜索", "推荐", "线下活动", "电话营销", "社交媒体", "邮件营销"],
        "field_type": "string",
        "aliases": ["来源", "渠道", "获客渠道", "客户来源"]
    },
    {
        "field": "create_time",
        "name": "创建时间",
        "description": "客户创建时间，可按相对时间或自定义日期范围筛选",
        "operators": ["今天", "昨天", "本周", "上周", "本月", "上月", "本季度", "今年", "最近7天", "最近30天", "最近90天", "在范围内"],
        "params": ["2025-01-01", "2026-03-03"],
        "field_type": "date",
        "aliases": ["创建时间", "添加时间", "录入时间", "建档时间"]
    },
    {
        "field": "last_contact_time",
        "name": "最近联系时间",
        "description": "客户最近一次联系时间",
        "operators": ["在最近天内", "超过天未联系", "是空", "非空", "在范围内"],
        "params": ["7天内", "30天内", "从未联系", "超过30天未联系"],
        "field_type": "date",
        "aliases": ["最后联系时间", "最近联系时间", "联系时间", "跟进时间"]
    },
    {
        "field": "customer_status",
        "name": "客户状态",
        "description": "客户销售阶段状态",
        "operators": ["等于", "不等于", "包含"],
        "params": ["潜在客户", "意向客户", "成交客户", "流失客户"],
        "field_type": "string",
        "aliases": ["状态", "客户状态", "销售状态", "阶段"]
    },
    {
        "field": "customer_level",
        "name": "客户等级",
        "description": "客户价值等级",
        "operators": ["等于", "不等于"],
        "params": ["A", "B", "C", "VIP"],
        "field_type": "string",
        "aliases": ["等级", "客户等级", "级别", "价值等级"]
    },
    {
        "field": "order_amount",
        "name": "订单金额",
        "description": "客户累计订单金额",
        "operators": ["大于", "小于", "大于等于", "小于等于", "等于", "在...之间"],
        "params": ["1000", "5000", "10000", "50000"],
        "field_type": "number",
        "aliases": ["订单金额", "金额", "成交金额", "消费金额", "付款金额", "已付款金额"]
    },
    {
        "field": "follow_up_status",
        "name": "跟进状态",
        "description": "客户当前跟进进度",
        "operators": ["等于", "不等于"],
        "params": ["未联系", "已联系", "跟进中"],
        "field_type": "string",
        "aliases": ["跟进状态", "回访状态", "联系状态", "跟进情况"]
    },
    {
        "field": "region",
        "name": "地区",
        "description": "客户所在区域",
        "operators": ["等于", "不等于", "包含"],
        "params": ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安", "重庆"],
        "field_type": "string",
        "aliases": ["地区", "城市", "所在地区", "区域"]
    },
    {
        "field": "industry",
        "name": "行业",
        "description": "客户所属行业",
        "operators": ["等于", "不等于", "包含"],
        "params": ["IT", "金融", "教育", "医疗", "零售", "制造", "房地产", "咨询", "媒体", "物流"],
        "field_type": "string",
        "aliases": ["行业", "所属行业", "行业类型"]
    },
    {
        "field": "tags",
        "name": "标签",
        "description": "客户业务标签（逗号分隔）",
        "operators": ["包含", "不等于"],
        "params": ["重要客户", "需要跟进", "长期合作", "高价值", "新客户", "老客户"],
        "field_type": "string",
        "aliases": ["标签", "客户标签", "标记"]
    }
]

FIELD_ALIASES = {
    item["field"]: item.get("aliases", []) for item in CRM_FILTER_CONDITIONS
}

FIELD_NAME_MAP = {
    "customer_source": "客户来源",
    "create_time": "创建时间",
    "last_contact_time": "最近联系时间",
    "customer_status": "客户状态",
    "customer_level": "客户等级",
    "order_amount": "订单金额",
    "follow_up_status": "跟进状态",
    "region": "地区",
    "industry": "行业",
    "tags": "标签"
}

FIELD_VALUE_SYNONYMS = {
    "customer_status": {
        "潜在客户": "potential",
        "新客户": "potential",
        "线索客户": "potential",
        "意向客户": "interested",
        "有意向客户": "interested",
        "成交客户": "deal",
        "已成交客户": "deal",
        "成单客户": "deal",
        "流失客户": "lost",
        "已流失客户": "lost",
    },
    "customer_level": {
        "a": "A",
        "a类": "A",
        "a级": "A",
        "b": "B",
        "b类": "B",
        "b级": "B",
        "c": "C",
        "c类": "C",
        "c级": "C",
        "vip": "VIP",
        "vip客户": "VIP",
    },
    "follow_up_status": {
        "未联系": "not_contacted",
        "未联系过": "not_contacted",
        "没有联系": "not_contacted",
        "没有联系过": "not_contacted",
        "从未联系": "not_contacted",
        "未跟进": "not_contacted",
        "已联系": "contacted",
        "联系过": "contacted",
        "跟进中": "following",
        "需要回访": "following",
        "待回访": "following",
    },
    "customer_source": {
        "百度": "百度",
        "百度推广": "百度",
        "腾讯": "腾讯广告",
        "腾讯广告": "腾讯广告",
        "谷歌": "谷歌搜索",
        "谷歌搜索": "谷歌搜索",
        "推荐": "推荐",
        "转介绍": "推荐",
        "线下活动": "线下活动",
        "地推": "线下活动",
        "电话营销": "电话营销",
        "电话": "电话营销",
        "社交媒体": "社交媒体",
        "社媒": "社交媒体",
        "邮件营销": "邮件营销",
        "邮件": "邮件营销",
    },
    "industry": {
        "互联网": "IT",
        "it": "IT",
        "信息技术": "IT",
        "金融": "金融",
        "教育": "教育",
        "医疗": "医疗",
        "零售": "零售",
        "制造业": "制造",
        "制造": "制造",
        "房地产": "房地产",
        "咨询": "咨询",
        "媒体": "媒体",
        "物流": "物流",
    },
}

FIELD_VALUE_DISPLAY = {
    "customer_status": {
        "potential": "潜在客户",
        "interested": "意向客户",
        "deal": "成交客户",
        "lost": "流失客户",
    },
    "follow_up_status": {
        "not_contacted": "未联系",
        "contacted": "已联系",
        "following": "跟进中",
    },
    "customer_level": {
        "A": "A类",
        "B": "B类",
        "C": "C类",
        "VIP": "VIP",
    },
}

CONDITION_EXAMPLES = [
    "查找本月从百度来源创建的潜在客户",
    "筛选最近30天没有联系过的意向客户",
    "找出订单金额大于1万元的A类客户",
    "查看上海地区IT行业的客户",
    "获取本周需要回访的客户列表",
    "查找从未联系过的深圳客户",
    "找出标签包含高价值且来源为推荐的客户",
]
