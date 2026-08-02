"""Identity auth context menu/permission regression tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.menu import Menu, RoleMenu
from app.models.permission import Permission, RolePermission
from app.models.role import Role, UserRole
from app.models.user import User
from app.models.user_permission import UserMenu, UserPermission
from app.services.identity_auth_service import IdentityAuthService


@pytest.fixture
def identity_engine() -> Generator[Engine, None, None]:
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
        RolePermission.__table__,
        Menu.__table__,
        RoleMenu.__table__,
        UserPermission.__table__,
        UserMenu.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    yield engine
    Base.metadata.drop_all(engine, tables=tables)
    engine.dispose()


@pytest.fixture
def identity_session_factory(identity_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=identity_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


class _FakeSessions:
    def read_access_token(self, access_token: str) -> int | None:
        return 1 if access_token == "valid-token" else None

    def was_access_session_replaced(self, access_token: str) -> bool:
        return False

    def is_password_change_required(self, user_id: int) -> bool:
        return False


def test_current_user_context_includes_role_menus_when_user_menu_snapshot_is_stale(
    identity_session_factory: sessionmaker[Session],
) -> None:
    with identity_session_factory() as session:
        user = User(
            id=1,
            username="alice",
            password_hash="hash",
            status=1,
            is_vip=False,
            vip_level=0,
        )
        role = Role(id=10, code="manager", name="Manager", is_builtin=False)
        employee_permission = Permission(
            id=100,
            code="admin:employee:manage",
            name="Digital Employee",
        )
        bot_permission = Permission(
            id=101,
            code="admin:bot:manage",
            name="Bot Manage",
        )
        profile_menu = Menu(
            id=1101,
            parent_id=0,
            menu_type=2,
            title="个人信息",
            path="/profile",
            sort=1,
            visible=True,
        )
        employee_menu = Menu(
            id=2005,
            parent_id=0,
            menu_type=2,
            title="数字员工",
            path="/digital-employees",
            permission="admin:employee:manage",
            sort=2,
            visible=True,
        )
        bot_menu = Menu(
            id=2006,
            parent_id=0,
            menu_type=2,
            title="Bot管理",
            path="/bots",
            permission="admin:bot:manage",
            sort=3,
            visible=True,
        )

        role.permissions = [employee_permission, bot_permission]
        role.menus = [profile_menu, employee_menu, bot_menu]
        user.roles = [role]
        user.menus = [profile_menu]
        user.permissions = []
        session.add(user)
        session.commit()

        service = IdentityAuthService(session)
        service._sessions = _FakeSessions()

        context = service.get_current_user_context("valid-token")

    assert context["permissions"] == [
        "admin:bot:manage",
        "admin:employee:manage",
    ]
    assert {menu["id"] for menu in context["menus"]} == {1101, 2005, 2006}
