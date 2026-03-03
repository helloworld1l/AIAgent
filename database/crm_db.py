"""
CRM数据库操作类
"""
import sqlite3
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import sys
import os

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config.settings import settings
from .models import Customer

logger = logging.getLogger(__name__)

class CRMDatabase:
    """CRM数据库操作类"""
    
    def __init__(self, db_path: str = None):
        """
        初始化数据库连接
        
        Args:
            db_path: 数据库文件路径，默认为配置中的路径
        """
        if db_path:
            self.db_path = db_path
        else:
            # 从配置获取或使用默认路径
            try:
                if hasattr(settings, 'DATABASE_URL'):
                    self.db_path = settings.DATABASE_URL.replace('sqlite:///', '')
                else:
                    self.db_path = 'crm_database.db'
            except:
                self.db_path = 'crm_database.db'
        
        logger.info(f"初始化CRM数据库: {self.db_path}")
        
        # 确保数据库文件存在并初始化表结构
        self._initialize_database()
    
    def _initialize_database(self):
        """初始化数据库表结构"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 读取并执行schema.sql
            schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
            if os.path.exists(schema_path):
                with open(schema_path, 'r', encoding='utf-8') as f:
                    schema_sql = f.read()
                
                # 执行所有SQL语句
                cursor.executescript(schema_sql)
                logger.info("数据库表结构初始化完成")
            else:
                logger.warning(f"schema.sql文件不存在: {schema_path}")
                # 创建基本的customers表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS customers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        phone TEXT NOT NULL,
                        email TEXT,
                        customer_source TEXT,
                        create_time TIMESTAMP,
                        last_contact_time TIMESTAMP,
                        customer_status TEXT,
                        customer_level TEXT,
                        order_amount REAL,
                        follow_up_status TEXT,
                        region TEXT,
                        industry TEXT,
                        tags TEXT,
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                logger.info("创建基本表结构完成")
            
            conn.commit()
            conn.close()
            
            # 检查是否有数据，如果没有则生成示例数据
            if self.get_customer_count() == 0:
                logger.info("检测到空数据库，正在生成示例数据...")
                self._seed_sample_data()
                
        except Exception as e:
            logger.error(f"数据库初始化失败: {str(e)}")
            raise
    
    def _seed_sample_data(self):
        """生成示例数据"""
        try:
            # 导入seed_data模块并执行
            from .seed_data import create_sample_data
            create_sample_data(self.db_path)
        except Exception as e:
            logger.error(f"生成示例数据失败: {str(e)}")
            # 如果导入失败，插入少量示例数据
            self._insert_minimal_sample_data()
    
    def _insert_minimal_sample_data(self):
        """插入最简示例数据"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 插入一些示例数据
            sample_customers = [
                ('张三', '13800138000', 'zhangsan@example.com', '百度', 
                 '2024-01-15 10:30:00', '2024-02-20 14:20:00',
                 'potential', 'A', 1500.00, 'contacted', '北京', 'IT', '重要客户,新客户', '示例客户1'),
                ('李四', '13900139000', 'lisi@example.com', '腾讯广告',
                 '2024-02-10 09:15:00', '2024-03-01 16:45:00',
                 'interested', 'VIP', 50000.00, 'following', '上海', '金融', '高价值,长期合作', '示例客户2'),
                ('王五', '13700137000', 'wangwu@example.com', '推荐',
                 '2024-03-05 14:20:00', None,
                 'potential', 'B', None, 'not_contacted', '广州', '教育', '新客户', '示例客户3'),
            ]
            
            for customer in sample_customers:
                cursor.execute('''
                    INSERT INTO customers (
                        name, phone, email, customer_source, create_time, last_contact_time,
                        customer_status, customer_level, order_amount, follow_up_status,
                        region, industry, tags, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', customer)
            
            conn.commit()
            conn.close()
            logger.info("已插入最简示例数据")
            
        except Exception as e:
            logger.error(f"插入最简示例数据失败: {str(e)}")
    
    def get_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 使返回结果为字典格式
        return conn
    
    def get_customer_count(self) -> int:
        """获取客户总数"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM customers")
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            logger.error(f"获取客户总数失败: {str(e)}")
            return 0
    
    def query_customers(self, conditions: List[Dict[str, Any]] = None, 
                        limit: int = 50) -> List[Dict[str, Any]]:
        """
        根据条件查询客户
        
        Args:
            conditions: 查询条件列表，每个条件为字典，包含field, operator, value
            limit: 返回结果数量限制
            
        Returns:
            客户数据列表
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # 构建查询SQL
            query = "SELECT * FROM customers"
            params = []
            allowed_fields = {
                "id", "name", "phone", "email", "customer_source", "create_time",
                "last_contact_time", "customer_status", "customer_level", "order_amount",
                "follow_up_status", "region", "industry", "tags", "notes",
            }
            date_fields = {"create_time", "last_contact_time"}
            
            if conditions and len(conditions) > 0:
                where_clauses = []
                for cond in conditions:
                    field = cond.get('field')
                    operator = cond.get('operator')
                    value = cond.get('value')
                    
                    if not field or not operator:
                        continue
                    if field not in allowed_fields:
                        logger.warning(f"忽略不支持的字段: {field}")
                        continue

                    # 处理不同的操作符
                    if operator == '等于' and value is not None:
                        where_clauses.append(f"{field} = ?")
                        params.append(value)
                    elif operator == '不等于' and value is not None:
                        where_clauses.append(f"{field} != ?")
                        params.append(value)
                    elif operator == '包含' and value is not None:
                        where_clauses.append(f"{field} LIKE ?")
                        params.append(f"%{value}%")
                    elif operator == '大于' and value is not None:
                        where_clauses.append(f"{field} > ?")
                        params.append(value)
                    elif operator == '小于' and value is not None:
                        where_clauses.append(f"{field} < ?")
                        params.append(value)
                    elif operator == '大于等于' and value is not None:
                        where_clauses.append(f"{field} >= ?")
                        params.append(value)
                    elif operator == '小于等于' and value is not None:
                        where_clauses.append(f"{field} <= ?")
                        params.append(value)
                    elif operator == '在...之间' and isinstance(value, list) and len(value) == 2:
                        if field in date_fields:
                            where_clauses.append(f"DATE({field}) BETWEEN DATE(?) AND DATE(?)")
                        else:
                            where_clauses.append(f"{field} BETWEEN ? AND ?")
                        params.extend(value)
                    elif operator == '在范围内' and isinstance(value, list) and len(value) == 2:
                        where_clauses.append(f"DATE({field}) BETWEEN DATE(?) AND DATE(?)")
                        params.extend(value)
                    elif operator == '在最近天内' and value is not None:
                        try:
                            days = int(value)
                        except (TypeError, ValueError):
                            continue
                        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
                        where_clauses.append(f"DATE({field}) >= DATE(?)")
                        params.append(start_date)
                    elif operator == '超过天未联系' and value is not None and field == "last_contact_time":
                        try:
                            days = int(value)
                        except (TypeError, ValueError):
                            continue
                        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
                        where_clauses.append(f"({field} IS NULL OR DATE({field}) < DATE(?))")
                        params.append(cutoff_date)
                    elif operator in ('是空', '为空'):
                        where_clauses.append(f"{field} IS NULL")
                    elif operator in ('非空', '不为空'):
                        where_clauses.append(f"{field} IS NOT NULL")
                
                if where_clauses:
                    query += " WHERE " + " AND ".join(where_clauses)
            
            query += f" ORDER BY create_time DESC LIMIT {limit}"
            
            # 执行查询
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # 转换为字典列表
            customers = []
            for row in rows:
                customer_dict = dict(row)
                customers.append(customer_dict)
            
            conn.close()
            logger.info(f"查询到 {len(customers)} 个客户")
            return customers
            
        except Exception as e:
            logger.error(f"查询客户失败: {str(e)}")
            return []
    
    def get_customer_by_id(self, customer_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取客户"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"获取客户失败: {str(e)}")
            return None
    
    def search_customers(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """关键词搜索客户"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            query = """
                SELECT * FROM customers 
                WHERE name LIKE ? OR phone LIKE ? OR email LIKE ? 
                      OR region LIKE ? OR industry LIKE ? OR tags LIKE ?
                ORDER BY create_time DESC 
                LIMIT ?
            """
            params = [f"%{keyword}%"] * 6 + [limit]
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            customers = [dict(row) for row in rows]
            conn.close()
            
            return customers
        except Exception as e:
            logger.error(f"搜索客户失败: {str(e)}")
            return []
    
    def get_field_values(self, field: str) -> List[str]:
        """获取某个字段的所有可能值"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(f"SELECT DISTINCT {field} FROM customers WHERE {field} IS NOT NULL")
            values = [row[0] for row in cursor.fetchall()]
            conn.close()
            return values
        except Exception as e:
            logger.error(f"获取字段值失败: {str(e)}")
            return []
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            stats = {}
            
            # 客户总数
            cursor.execute("SELECT COUNT(*) FROM customers")
            stats['total_customers'] = cursor.fetchone()[0]
            
            # 按状态统计
            cursor.execute("""
                SELECT customer_status, COUNT(*) as count 
                FROM customers 
                WHERE customer_status IS NOT NULL
                GROUP BY customer_status
            """)
            stats['by_status'] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # 按来源统计
            cursor.execute("""
                SELECT customer_source, COUNT(*) as count 
                FROM customers 
                WHERE customer_source IS NOT NULL
                GROUP BY customer_source
            """)
            stats['by_source'] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # 按地区统计
            cursor.execute("""
                SELECT region, COUNT(*) as count 
                FROM customers 
                WHERE region IS NOT NULL
                GROUP BY region
                ORDER BY count DESC
                LIMIT 10
            """)
            stats['by_region'] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # 最近30天新增客户
            thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            cursor.execute("""
                SELECT COUNT(*) FROM customers 
                WHERE DATE(create_time) >= ?
            """, (thirty_days_ago,))
            stats['recent_30_days'] = cursor.fetchone()[0]
            
            conn.close()
            return stats
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {str(e)}")
            return {}


def test_database():
    """测试数据库功能"""
    print("测试CRM数据库模块...")
    
    try:
        # 创建数据库实例
        db = CRMDatabase()
        
        # 测试统计信息
        print(f"客户总数: {db.get_customer_count()}")
        
        # 测试条件查询
        conditions = [
            {'field': 'customer_source', 'operator': '等于', 'value': '百度'},
            {'field': 'region', 'operator': '等于', 'value': '北京'}
        ]
        
        customers = db.query_customers(conditions, limit=5)
        print(f"\n条件查询结果数量: {len(customers)}")
        if customers:
            print("前5个客户:")
            for i, customer in enumerate(customers[:5], 1):
                print(f"  {i}. {customer['name']} - {customer['region']} - {customer['customer_source']}")
        
        # 测试关键词搜索
        search_results = db.search_customers('北京', limit=3)
        print(f"\n关键词'北京'搜索到 {len(search_results)} 个客户")
        
        # 测试统计信息
        stats = db.get_statistics()
        print(f"\n统计信息:")
        print(f"  按状态分布: {stats.get('by_status', {})}")
        print(f"  按来源分布: {stats.get('by_source', {})}")
        
    except Exception as e:
        print(f"测试失败: {str(e)}")


if __name__ == '__main__':
    test_database()
