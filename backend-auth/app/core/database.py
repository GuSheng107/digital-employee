"""SQLAlchemy 数据库引擎与会话工厂。

backend-auth 共用 PostgreSQL 的 db_data 库（与 backend-data 同库，
通过 SQLAlchemy ORM 操作 users/roles/menus/bots 等表）。
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的声明基类。"""


class DatabaseClient:
    """PostgreSQL 引擎与会话工厂的集中封装。

    引擎与会话工厂均懒加载，首次访问时创建并缓存，避免进程启动时
    立即建立数据库连接。
    """

    def __init__(self) -> None:
        self.database_url = settings.core_database_url
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def engine(self) -> Engine:
        """懒加载 SQLAlchemy 引擎。

        启用 pool_pre_ping 避免使用已断开的连接，future=True 使用 2.0 风格。
        """
        if self._engine is None:
            self._engine = create_engine(
                self.database_url,
                pool_pre_ping=True,
                future=True,
            )
        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        """懒加载会话工厂。"""
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
            )
        return self._session_factory

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """提供事务会话上下文。

        自动提交/回滚，由调用方决定是否在异常时回滚。
        """
        with self.session_factory() as session:
            yield session

    def ping(self) -> None:
        """探活数据库连接，失败时抛出异常。"""
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))


_database_client: DatabaseClient | None = None


def get_database_client() -> DatabaseClient:
    """获取全局数据库客户端单例。"""
    global _database_client
    if _database_client is None:
        _database_client = DatabaseClient()
    return _database_client


def get_engine() -> Engine:
    """获取全局 SQLAlchemy 引擎。"""
    return get_database_client().engine


def get_session_factory() -> sessionmaker[Session]:
    """获取全局会话工厂。"""
    return get_database_client().session_factory


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI 依赖：提供一个数据库会话并在请求结束时关闭。"""
    with get_database_client().session() as session:
        yield session
