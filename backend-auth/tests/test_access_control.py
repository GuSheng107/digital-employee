"""VIP、角色保护与权限判定回归测试。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from api_common import PermissionDeniedError
from auth_utils import PermissionCode

from app.api.deps import require_permission
from app.core.enums import get_vip_display
from app.schemas.auth import UserInfo
from app.services.role_service import RoleService


class _ScalarResult:
    """模拟 SQLAlchemy ScalarResult。"""

    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def all(self) -> list[Any]:
        """返回测试数据。"""
        return self._values


class _RoleSession:
    """仅实现 RoleService.list_roles 所需的 session 协议。"""

    def __init__(self, roles: list[Any]) -> None:
        self._roles = roles

    def scalars(self, _statement: Any) -> _ScalarResult:
        """忽略 SQL 表达式并返回预置角色。"""
        return _ScalarResult(self._roles)


def _build_user(*, roles: list[str], permissions: list[str]) -> UserInfo:
    """构造权限依赖需要的最小用户。"""
    return UserInfo(
        id=1,
        username="tester",
        is_vip=False,
        vip_level=0,
        status=1,
        roles=roles,
        permissions=permissions,
    )


def test_vip_display_distinguishes_manager_and_super_admin() -> None:
    """66 与 99 必须展示不同管理身份。"""
    assert get_vip_display(66) == "管理员"
    assert get_vip_display(99) == "超级管理员"


def test_role_list_never_exposes_super_admin() -> None:
    """即使查询桩返回最高角色，服务响应仍需防御性过滤。"""
    roles = [
        SimpleNamespace(
            id=1,
            code="super_admin",
            name="超级管理员",
            description="protected",
            is_builtin=True,
            menus=[],
            permissions=[],
        ),
        SimpleNamespace(
            id=2,
            code="manager",
            name="管理员",
            description="manageable",
            is_builtin=True,
            menus=[],
            permissions=[],
        ),
    ]
    service = RoleService(_RoleSession(roles))

    result = service.list_roles()

    assert [role["code"] for role in result] == ["manager"]


def test_manager_requires_explicit_permission() -> None:
    """manager 不再拥有隐式万能权限。"""
    dependency = require_permission(PermissionCode.MENU_MANAGE)
    with pytest.raises(PermissionDeniedError):
        dependency(current_user=_build_user(roles=["manager"], permissions=[]))


def test_super_admin_keeps_full_access_bypass() -> None:
    """super_admin 作为安全边界保留全权限旁路。"""
    dependency = require_permission(PermissionCode.MENU_MANAGE)
    user = _build_user(roles=["super_admin"], permissions=[])

    assert dependency(current_user=user) is user
