"""
数据模型定义
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Customer:
    """客户数据模型"""
    id: int
    name: str
    phone: str
    email: Optional[str] = None
    customer_source: Optional[str] = None  # 客户来源：百度、腾讯、谷歌等
    create_time: Optional[datetime] = None  # 创建时间
    last_contact_time: Optional[datetime] = None  # 最后联系时间
    customer_status: Optional[str] = None  # 客户状态：潜在、意向、成交、流失
    customer_level: Optional[str] = None  # 客户等级：A、B、C、VIP
    order_amount: Optional[float] = None  # 订单金额
    follow_up_status: Optional[str] = None  # 跟进状态：未联系、已联系、已跟进
    region: Optional[str] = None  # 地区：北京、上海、广州等
    industry: Optional[str] = None  # 行业：IT、金融、教育等
    tags: Optional[str] = None  # 标签：逗号分隔
    notes: Optional[str] = None  # 备注
    
    def to_dict(self):
        """转换为字典格式"""
        result = {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'email': self.email,
            'customer_source': self.customer_source,
            'customer_status': self.customer_status,
            'customer_level': self.customer_level,
            'order_amount': self.order_amount,
            'follow_up_status': self.follow_up_status,
            'region': self.region,
            'industry': self.industry,
            'tags': self.tags,
            'notes': self.notes
        }
        
        # 处理日期时间字段
        if self.create_time:
            result['create_time'] = self.create_time.isoformat()
        if self.last_contact_time:
            result['last_contact_time'] = self.last_contact_time.isoformat()
            
        return result