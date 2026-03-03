"""
生成示例数据
"""
import sqlite3
import random
from datetime import datetime, timedelta
import sys
import os

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def _build_curated_customers(now: datetime):
    """构建一组稳定命中的演示数据，避免查询样例全部落空。"""
    return [
        {
            "name": "演示_百度本月潜在客户_A",
            "phone": "13800000001",
            "email": "demo_baidu_a@example.com",
            "customer_source": "百度",
            "create_time": now - timedelta(days=1),
            "last_contact_time": now - timedelta(days=1),
            "customer_status": "potential",
            "customer_level": "A",
            "order_amount": 12000.0,
            "follow_up_status": "contacted",
            "region": "上海",
            "industry": "IT",
            "tags": "重要客户,高价值",
            "notes": "用于验证: 本月+百度+潜在客户",
        },
        {
            "name": "演示_百度本月潜在客户_B",
            "phone": "13800000002",
            "email": "demo_baidu_b@example.com",
            "customer_source": "百度",
            "create_time": now,
            "last_contact_time": None,
            "customer_status": "potential",
            "customer_level": "B",
            "order_amount": 3000.0,
            "follow_up_status": "not_contacted",
            "region": "北京",
            "industry": "金融",
            "tags": "新客户,需要跟进",
            "notes": "用于验证: 从未联系/本月筛选",
        },
        {
            "name": "演示_上海互联网意向客户",
            "phone": "13800000003",
            "email": "demo_sh_it@example.com",
            "customer_source": "推荐",
            "create_time": now - timedelta(days=8),
            "last_contact_time": now - timedelta(days=2),
            "customer_status": "interested",
            "customer_level": "VIP",
            "order_amount": 58000.0,
            "follow_up_status": "following",
            "region": "上海",
            "industry": "IT",
            "tags": "长期合作,高价值",
            "notes": "用于验证: 地区+行业筛选",
        },
        {
            "name": "演示_超过30天未联系",
            "phone": "13800000004",
            "email": "demo_uncontacted@example.com",
            "customer_source": "线下活动",
            "create_time": now - timedelta(days=120),
            "last_contact_time": now - timedelta(days=45),
            "customer_status": "interested",
            "customer_level": "A",
            "order_amount": 8000.0,
            "follow_up_status": "not_contacted",
            "region": "深圳",
            "industry": "制造",
            "tags": "需要跟进",
            "notes": "用于验证: 超过30天未联系",
        },
    ]


def create_sample_data(db_path='crm_database.db'):
    """创建示例数据"""
    
    # 示例数据定义
    names = ['张三', '李四', '王五', '赵六', '钱七', '孙八', '周九', '吴十', '郑十一', '王十二',
             '刘十三', '陈十四', '杨十五', '黄十六', '朱十七', '何十八', '林十九', '高二十']
    
    sources = ['百度', '腾讯广告', '谷歌搜索', '推荐', '线下活动', '电话营销', '社交媒体', '邮件营销']
    statuses = ['potential', 'interested', 'deal', 'lost']
    levels = ['A', 'B', 'C', 'VIP']
    regions = ['北京', '上海', '广州', '深圳', '杭州', '成都', '武汉', '南京', '西安', '重庆']
    industries = ['IT', '金融', '教育', '医疗', '零售', '制造', '房地产', '咨询', '媒体', '物流']
    follow_up_statuses = ['not_contacted', 'contacted', 'following']
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 清空现有数据
    cursor.execute("DELETE FROM customers")

    now = datetime.now()

    # 先插入稳定命中的演示数据
    curated_customers = _build_curated_customers(now)
    for item in curated_customers:
        cursor.execute('''
            INSERT INTO customers (
                name, phone, email, customer_source, create_time, last_contact_time,
                customer_status, customer_level, order_amount, follow_up_status,
                region, industry, tags, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            item["name"],
            item["phone"],
            item["email"],
            item["customer_source"],
            item["create_time"].isoformat() if item["create_time"] else None,
            item["last_contact_time"].isoformat() if item["last_contact_time"] else None,
            item["customer_status"],
            item["customer_level"],
            item["order_amount"],
            item["follow_up_status"],
            item["region"],
            item["industry"],
            item["tags"],
            item["notes"],
        ))
    
    # 插入示例数据
    for i in range(len(curated_customers) + 1, 101):  # 总量保持100
        # 生成随机数据
        name = random.choice(names) + f'_{i:03d}'
        phone = f'138{random.randint(10000000, 99999999)}'
        email = f'customer{i:03d}@example.com'
        source = random.choice(sources)
        
        # 创建时间：最近1年内随机
        days_ago = random.randint(1, 365)
        create_time = now - timedelta(days=days_ago)
        
        # 最后联系时间：可能在创建时间之后，也可能没有
        if random.random() > 0.3:  # 70%的客户有联系记录
            contact_days = random.randint(0, days_ago)
            last_contact_time = create_time + timedelta(days=contact_days)
        else:
            last_contact_time = None
            
        status = random.choice(statuses)
        level = random.choice(levels)
        
        # 订单金额：如果状态是deal，则有较大金额
        if status == 'deal':
            order_amount = round(random.uniform(1000, 50000), 2)
        else:
            order_amount = round(random.uniform(0, 5000), 2) if random.random() > 0.7 else None
            
        follow_up = random.choice(follow_up_statuses)
        region = random.choice(regions)
        industry = random.choice(industries)
        
        # 生成标签
        tag_options = ['重要客户', '需要跟进', '长期合作', '高价值', '新客户', '老客户']
        selected_tags = random.sample(tag_options, random.randint(1, 3))
        tags = ','.join(selected_tags)
        
        # 插入数据
        cursor.execute('''
            INSERT INTO customers (
                name, phone, email, customer_source, create_time, last_contact_time,
                customer_status, customer_level, order_amount, follow_up_status,
                region, industry, tags, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            name, phone, email, source, 
            create_time.isoformat() if create_time else None,
            last_contact_time.isoformat() if last_contact_time else None,
            status, level, order_amount, follow_up,
            region, industry, tags, f'这是客户{i:03d}的备注信息'
        ))
    
    conn.commit()
    print(f"已生成100条示例客户数据到 {db_path}")
    
    # 显示统计信息
    cursor.execute("SELECT COUNT(*) FROM customers")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT customer_source, COUNT(*) FROM customers GROUP BY customer_source")
    print("\n按来源统计:")
    for source, count in cursor.fetchall():
        print(f"  {source}: {count}个")
    
    cursor.execute("SELECT customer_status, COUNT(*) FROM customers GROUP BY customer_status")
    print("\n按状态统计:")
    for status, count in cursor.fetchall():
        print(f"  {status}: {count}个")
    
    cursor.execute("SELECT region, COUNT(*) FROM customers GROUP BY region")
    print("\n按地区统计:")
    for region, count in cursor.fetchall():
        print(f"  {region}: {count}个")
    
    conn.close()

if __name__ == '__main__':
    # 从配置文件获取数据库路径
    try:
        from config.settings import settings
        db_path = settings.DATABASE_URL.replace('sqlite:///', '')
    except:
        db_path = 'crm_database.db'
    
    create_sample_data(db_path)
