"""SQLAlchemy ORM 模型层。

模型与 docs/schema.sql 中的表结构一一对应，共用 db_data 库。
通过统一导入 __init__，确保所有模型在 Base.metadata 注册。
"""

from app.models.agent import Agent, BotAgent
from app.models.base import Base
from app.models.bot import Bot, BotCallPermission, UserBot
from app.models.menu import Menu, RoleMenu
from app.models.permission import Permission, RolePermission
from app.models.role import Role, UserRole
from app.models.user import User

__all__ = [
    "Agent",
    "Base",
    "Bot",
    "BotAgent",
    "BotCallPermission",
    "Menu",
    "Permission",
    "Role",
    "RoleMenu",
    "RolePermission",
    "User",
    "UserBot",
    "UserRole",
]
