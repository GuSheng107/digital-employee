"""ORM 模型公共基类。

复用 database.py 中的 DeclarativeBase，避免循环引用。
统一在此导出，所有模型文件 import Base 时都从这里取。
"""

from app.core.database import Base

__all__ = ["Base"]
