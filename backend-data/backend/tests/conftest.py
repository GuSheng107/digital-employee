"""backend-data bot_service 单测共享 fixture。

测试使用 SQLite 内存数据库（仅创建 bots 表），patch ``BotService._db``
使其指向 SQLite session，避免依赖真实 PostgreSQL 与 Nacos。
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

# 必须在任何 app.* / secret_crypto import 之前设置环境变量。
# APP_SECRET_KEY：secret_crypto 加密 passphrase（与运行时一致即可，测试用固定值）。
# NACOS_SERVER_ADDR：留空跳过 Nacos 拉取，避免测试依赖外部服务。
os.environ.setdefault("APP_SECRET_KEY", "test-passphrase-for-bot-service-tests")
os.environ.setdefault("NACOS_SERVER_ADDR", "")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.agent import Agent
from app.models.bot import Bot
from app.models.user import User
from app.services.bot_service import BotService


@pytest.fixture
def sqlite_engine() -> Generator[Engine, None, None]:
    """创建 SQLite 内存引擎，仅建 bots 表，测试结束后销毁。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # list_bots 联表 users / agents 展示创建者与 Agent 名称，需一并创建；
    # 其余模型（Role 等）不涉及，仍不创建以免 FK/relationship 干扰。
    Base.metadata.create_all(
        engine,
        tables=[User.__table__, Agent.__table__, Bot.__table__],
    )
    yield engine
    Base.metadata.drop_all(
        engine,
        tables=[Bot.__table__, Agent.__table__, User.__table__],
    )
    engine.dispose()


@pytest.fixture
def db_session_factory(sqlite_engine: Engine) -> sessionmaker[Session]:
    """返回绑定到 SQLite 内存引擎的 session factory。"""
    return sessionmaker(
        bind=sqlite_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


@pytest.fixture
def bot_service(monkeypatch, db_session_factory: sessionmaker[Session]) -> BotService:
    """返回使用 SQLite 内存 DB 的 BotService 实例。

    通过 monkeypatch 替换 ``bot_service`` 模块内的 ``get_database_client``，
    使其返回一个 fake client，session() 产出 SQLite session。
    """
    @contextmanager
    def _fake_session() -> Generator[Session, None, None]:
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    class _FakeClient:
        def session(self):
            return _fake_session()

    monkeypatch.setattr(
        "app.services.bot_service.get_database_client",
        lambda role: _FakeClient(),
    )
    return BotService()
