-- CRM数据库表结构
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT,
    customer_source TEXT,  -- 客户来源
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 创建时间
    last_contact_time TIMESTAMP,  -- 最后联系时间
    customer_status TEXT,  -- 客户状态：potential(潜在), interested(意向), deal(成交), lost(流失)
    customer_level TEXT,  -- 客户等级：A, B, C, VIP
    order_amount REAL,  -- 订单金额
    follow_up_status TEXT,  -- 跟进状态：not_contacted(未联系), contacted(已联系), following(跟进中)
    region TEXT,  -- 地区
    industry TEXT,  -- 行业
    tags TEXT,  -- 标签，逗号分隔
    notes TEXT,  -- 备注
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建索引以加速查询
CREATE INDEX IF NOT EXISTS idx_customer_source ON customers(customer_source);
CREATE INDEX IF NOT EXISTS idx_customer_status ON customers(customer_status);
CREATE INDEX IF NOT EXISTS idx_region ON customers(region);
CREATE INDEX IF NOT EXISTS idx_create_time ON customers(create_time);
CREATE INDEX IF NOT EXISTS idx_last_contact_time ON customers(last_contact_time);
CREATE INDEX IF NOT EXISTS idx_order_amount ON customers(order_amount);