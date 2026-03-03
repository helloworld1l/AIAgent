"""
Database模块初始化文件
"""
from .crm_db import CRMDatabase
from .models import Customer

__all__ = ['CRMDatabase', 'Customer']