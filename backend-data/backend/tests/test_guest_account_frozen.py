"""游客账号密码冻结单测（backend-data 数据层）。

覆盖：
- ``update_profile`` 携带 password_hash 时对 youke 拒绝写入。
- ``reset_user_password`` 对 youke 拒绝（管理员重置同样冻结）。
- 非游客账号不受影响。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from api_common import PermissionDeniedError
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.menu import Menu
from app.models.permission import Permission
from app.models.role import Role, UserRole
from app.models.user import User
from app.models.user_permission import UserMenu, UserPermission
from app.services.identity_user_service import UserService


class _FakeSessionService:
    """Redis 替身：仅记录强制改密标志调用，不依赖真实 Redis。"""

    def __init__(self) -> None:
        self._required: set[int] = set()

    def require_password_change(self, user_id: int) -> None:
        self._required.add(user_id)

    def clear_password_change_required(self, user_id: int) -> None:
        self._required.discard(user_id)

    def is_password_change_required(self, user_id: int) -> bool:
        return user_id in self._required

    def revoke_all_user_tokens(self, user_id: int) -> None:
        return None


@pytest.fixture
def fake_session_service(monkeypatch: pytest.MonkeyPatch) -> _FakeSessionService:
    """将 UserService 模块内的 IdentitySessionService 替换为 Redis 替身。"""
    fake = _FakeSessionService()
    monkeypatch.setattr(
        "app.services.identity_user_service.IdentitySessionService",
        lambda: fake,
    )
    return fake


@pytest.fixture
def user_engine() -> Generator[Engine, None, None]:
    """创建 SQLite 内存引擎，建身份相关表。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        User.__table__,
        Role.__table__,
        UserRole.__table__,
        Permission.__table__,
        UserPermission.__table__,
        Menu.__table__,
        UserMenu.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    yield engine
    Base.metadata.drop_all(engine, tables=tables)
    engine.dispose()


@pytest.fixture
def user_session_factory(user_engine: Engine) -> sessionmaker[Session]:
    """返回绑定到 SQLite 内存引擎的 session factory。"""
    return sessionmaker(
        bind=user_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def _seed_user(session: Session, user_id: int, username: str) -> None:
    """写入一个启用状态的普通用户。"""
    session.add(
        User(
            id=user_id,
            username=username,
            password_hash="old-hash",
            status=1,
            is_vip=False,
            vip_level=0,
        )
    )
    session.commit()


def test_guest_update_profile_with_password_is_rejected(
    user_session_factory: sessionmaker[Session],
) -> None:
    """youke 携带新密码哈希的自助改密应被拒绝。"""
    with user_session_factory() as session:
        _seed_user(session, user_id=2, username="youke")
        with pytest.raises(PermissionDeniedError):
            UserService(session).update_profile(
                user_id=2,
                nickname=None,
                email=None,
                phone=None,
                password_hash="new-hash",
            )
        # 密码哈希未被覆盖
        user = session.get(User, 2)
        assert user.password_hash == "old-hash"


def test_guest_update_profile_without_password_is_allowed(
    user_session_factory: sessionmaker[Session],
    fake_session_service: _FakeSessionService,
) -> None:
    """youke 仅更新昵称等资料字段应正常放行。"""
    with user_session_factory() as session:
        _seed_user(session, user_id=2, username="youke")
        result = UserService(session).update_profile(
            user_id=2,
            nickname="游客昵称",
            email=None,
            phone=None,
            password_hash=None,
        )
        assert result["nickname"] == "游客昵称"
        assert session.get(User, 2).password_hash == "old-hash"


def test_guest_password_reset_by_admin_is_rejected(
    user_session_factory: sessionmaker[Session],
) -> None:
    """管理员重置 youke 密码应被拒绝，避免强制改密死锁。"""
    with user_session_factory() as session:
        _seed_user(session, user_id=2, username="youke")
        with pytest.raises(PermissionDeniedError):
            UserService(session).reset_user_password(
                user_id=2,
                password_hash="admin-set-hash",
                actor_user_id=99,
                actor_role_codes=["super_admin"],
            )
        assert session.get(User, 2).password_hash == "old-hash"


def test_non_guest_password_reset_is_allowed(
    user_session_factory: sessionmaker[Session],
    fake_session_service: _FakeSessionService,
) -> None:
    """非游客账号重置流程保持原有行为。

    目标用户无 manager 角色，super_admin 作为 actor 不受同级限制。
    """
    with user_session_factory() as session:
        _seed_user(session, user_id=3, username="normal_user")
        result = UserService(session).reset_user_password(
            user_id=3,
            password_hash="admin-set-hash",
            actor_user_id=99,
            actor_role_codes=["super_admin"],
        )
        assert result["must_change_password"] is True
        assert session.get(User, 3).password_hash == "admin-set-hash"
