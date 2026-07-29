"""VIP、强制改密与权限判定回归测试。"""

from __future__ import annotations

import pytest
from api_common import PermissionDeniedError
from auth_utils import PermissionCode, get_vip_display

from app.api.deps import require_permission
from app.schemas.auth import UserInfo


def _build_user(
    *,
    roles: list[str],
    permissions: list[str],
    must_change_password: bool = False,
) -> UserInfo:
    """构造权限依赖需要的最小用户。"""
    return UserInfo(
        id=1,
        username="tester",
        is_vip=False,
        vip_level=0,
        status=1,
        roles=roles,
        permissions=permissions,
        must_change_password=must_change_password,
    )


def test_vip_display_distinguishes_manager_and_super_admin() -> None:
    """66 与 99 必须展示不同管理身份。"""
    assert get_vip_display(66) == "管理员"
    assert get_vip_display(99) == "超级管理员"


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


def test_password_reset_user_cannot_use_business_permissions() -> None:
    """管理员重置后的用户必须先完成自助改密。"""
    dependency = require_permission(PermissionCode.MENU_MANAGE)
    user = _build_user(
        roles=["super_admin"],
        permissions=[PermissionCode.MENU_MANAGE],
        must_change_password=True,
    )

    with pytest.raises(PermissionDeniedError, match="请先修改"):
        dependency(current_user=user)
