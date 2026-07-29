"""用户角色保护与菜单权限一致性测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from api_common import PermissionDeniedError, ValidationError
from auth_utils import VipLevel

from app.services.identity_auth_service import IdentityAuthService
from app.services.identity_user_service import UserService


class _ScalarResult:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def all(self) -> list[Any]:
        return self._values


class _SequenceSession:
    """按调用顺序返回查询结果的 Session 测试替身。"""

    def __init__(self, user: Any, scalar_results: list[list[Any]]) -> None:
        self.user = user
        self.scalar_results = list(scalar_results)
        self.committed = False

    def get(self, _model: Any, _object_id: int) -> Any:
        return self.user

    def scalars(self, _statement: Any) -> _ScalarResult:
        return _ScalarResult(self.scalar_results.pop(0))

    def commit(self) -> None:
        self.committed = True


def test_assign_user_menus_synchronizes_direct_permissions() -> None:
    user = SimpleNamespace(
        id=8,
        deleted_at=None,
        roles=[],
        menus=[],
        permissions=[],
    )
    menu = SimpleNamespace(
        id=11,
        deleted_at=None,
        permission="admin:user:manage",
    )
    permission = SimpleNamespace(
        id=21,
        code="admin:user:manage",
    )
    session = _SequenceSession(user, [[menu], [permission]])

    result = UserService(session).assign_user_menus(
        user_id=8,
        menu_ids=[11],
    )

    assert result["menu_ids"] == [11]
    assert result["permission_codes"] == ["admin:user:manage"]
    assert user.permissions == [permission]
    assert session.committed is True


def test_unknown_role_code_is_rejected() -> None:
    session = _SequenceSession(user=None, scalar_results=[[]])

    with pytest.raises(ValidationError, match="角色不存在"):
        UserService(session)._load_roles({"missing-role"})


def test_super_admin_account_is_protected_from_generic_management() -> None:
    user = SimpleNamespace(
        roles=[SimpleNamespace(code="super_admin")],
    )

    with pytest.raises(PermissionDeniedError, match="超级管理员"):
        UserService._ensure_not_protected_account(user)


def test_manager_cannot_delete_peer_manager() -> None:
    user = SimpleNamespace(
        id=8,
        deleted_at=None,
        roles=[SimpleNamespace(code="manager")],
    )
    session = _SequenceSession(user=user, scalar_results=[])

    with pytest.raises(PermissionDeniedError, match="仅超级管理员"):
        UserService(session).delete_user(
            user_id=8,
            actor_user_id=9,
            actor_role_codes=["manager"],
        )


def test_user_cannot_delete_current_account() -> None:
    user = SimpleNamespace(
        id=8,
        deleted_at=None,
        roles=[SimpleNamespace(code="user")],
    )
    session = _SequenceSession(user=user, scalar_results=[])

    with pytest.raises(PermissionDeniedError, match="当前登录账号"):
        UserService(session).delete_user(
            user_id=8,
            actor_user_id=8,
            actor_role_codes=["manager"],
        )


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (VipLevel.MANAGER, (True, int(VipLevel.MANAGER))),
        (VipLevel.SUPER_ADMIN, (True, int(VipLevel.SUPER_ADMIN))),
    ],
)
def test_management_vip_levels_are_permanent(
    level: VipLevel,
    expected: tuple[bool, int],
) -> None:
    """VIP66/VIP99 是管理身份，不依赖业务 VIP 过期时间。"""
    user = SimpleNamespace(
        is_vip=True,
        vip_level=level,
        vip_expires_at=None,
    )

    assert IdentityAuthService._effective_vip(None, user) == expected


def test_expired_business_vip_is_downgraded_in_login_context() -> None:
    user = SimpleNamespace(
        is_vip=True,
        vip_level=VipLevel.VIP1,
        vip_expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    assert IdentityAuthService._effective_vip(None, user) == (
        False,
        int(VipLevel.NORMAL),
    )
