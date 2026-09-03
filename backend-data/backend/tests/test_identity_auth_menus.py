"""Identity auth context menu/permission regression tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from auth_utils import expand_manage_to_readonly, validate_role_codes
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


def test_expand_manage_to_readonly_covers_manage_naming() -> None:
    """manage 权限码应扩展出对应的 readonly 变体。"""
    expanded = expand_manage_to_readonly(
        ["admin:menu:manage", "admin:permission:manage", "admin:bot:manage"]
    )
    assert "admin:menu:readonly" in expanded
    assert "admin:permission:readonly" in expanded
    assert "admin:bot:readonly" in expanded
    # 原始权限码始终保留
    assert "admin:menu:manage" in expanded
    assert "admin:permission:manage" in expanded
    # 不得产生 xxx:manage:readonly 这类不存在的冗余变体
    assert "admin:menu:manage:readonly" not in expanded
    assert "admin:bot:manage:readonly" not in expanded


def test_expand_manage_to_readonly_keeps_non_manage_codes() -> None:
    """非 :manage 后缀的权限码（如数据中台、日志）应原样保留，不追加 readonly。"""
    expanded = expand_manage_to_readonly(
        ["admin:data_platform:dashboard", "admin:observability:log:view"]
    )
    assert expanded == {"admin:data_platform:dashboard", "admin:observability:log:view"}


def test_validate_role_codes_identity_mutual_exclusion() -> None:
    """身份角色之间互斥，同时出现多个身份角色应返回错误。"""
    assert validate_role_codes(["user", "manager"]) is not None
    assert validate_role_codes(["manager", "super_admin"]) is not None


def test_validate_role_codes_manager_exclusive() -> None:
    """manager 独占，不能叠加自定义角色。"""
    assert validate_role_codes(["manager", "editor"]) is not None


def test_validate_role_codes_user_plus_custom_allowed() -> None:
    """user 可叠加自定义角色。"""
    assert validate_role_codes(["user", "editor"]) is None


def test_validate_role_codes_custom_multi_allowed() -> None:
    """多个自定义角色可叠加。"""
    assert validate_role_codes(["editor", "auditor"]) is None


def test_validate_role_codes_empty_and_single_allowed() -> None:
    """空列表或单角色均合法。"""
    assert validate_role_codes([]) is None
    assert validate_role_codes(["user"]) is None
    assert validate_role_codes(["manager"]) is None


def test_menu_bound_to_readonly_is_visible_to_manage_holder(
    identity_session_factory: sessionmaker[Session],
) -> None:
    """菜单绑 readonly 码时，持有对应 manage 码的用户也应看到该菜单。"""
    with identity_session_factory() as session:
        user = User(
            id=1,
            username="bob",
            password_hash="hash",
            status=1,
            is_vip=False,
            vip_level=0,
        )
        role = Role(id=10, code="manager", name="Manager", is_builtin=False)
        manage_permission = Permission(
            id=101,
            code="admin:bot:manage",
            name="Bot Manage",
        )
        bot_menu = Menu(
            id=2006,
            parent_id=0,
            menu_type=2,
            title="Bot管理",
            path="/bots",
            permission="admin:bot:readonly",
            sort=3,
            visible=True,
        )
        role.permissions = [manage_permission]
        role.menus = [bot_menu]
        user.roles = [role]
        user.menus = []
        user.permissions = []
        session.add(user)
        session.commit()

        service = IdentityAuthService(session)
        service._sessions = _FakeSessions()

        context = service.get_current_user_context("valid-token")

    # 持有 admin:bot:manage 的用户应看到绑 admin:bot:readonly 的菜单
    assert {menu["id"] for menu in context["menus"]} == {2006}
