"""身份域单会话与角色保护回归测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from api_common import TokenInvalidError

from app.services.identity_role_service import RoleService
from app.services.identity_session_service import IdentitySessionService


def test_redis_client_avoids_acl_restricted_script_and_transaction_commands() -> None:
    """生产 Redis 最小权限账号禁用 EVAL/WATCH/MULTI，代码不得重新引入。"""
    source = (
        Path(__file__).resolve().parents[1] / "app" / "core" / "redis_client.py"
    ).read_text(encoding="utf-8")

    assert ".eval(" not in source
    assert ".pipeline(" not in source
    assert ".watch(" not in source
    assert ".multi(" not in source


class _FakeRedis:
    """记录单会话清理涉及的 Redis 操作。"""

    def __init__(self) -> None:
        self.revoked: dict[str, str] | None = None

    def revoke_user_token_pair(self, **kwargs: str) -> None:
        """记录单键会话撤销参数。"""
        self.revoked = kwargs


class _FakeAtomicRedis:
    """记录单会话原子替换与 refresh 轮换调用。"""

    def __init__(self) -> None:
        self.replaced = False
        self.rotated = True

    def replace_user_token_pair(self, **_kwargs: Any) -> None:
        self.replaced = True

    def rotate_user_token_pair(self, **_kwargs: Any) -> bool:
        return self.rotated

    def get(self, _key: str) -> None:
        return None


class _ScalarResult:
    """模拟 SQLAlchemy ScalarResult。"""

    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def all(self) -> list[Any]:
        """返回测试数据。"""
        return self._values


class _RoleSession:
    """仅实现角色列表所需的 session 协议。"""

    def __init__(self, roles: list[Any]) -> None:
        self._roles = roles

    def scalars(self, _statement: Any) -> _ScalarResult:
        """忽略 SQL 表达式并返回预置角色。"""
        return _ScalarResult(self._roles)


def test_revoke_all_user_tokens_delegates_single_session_cleanup() -> None:
    """会话撤销必须由 Redis 包装层按同一用户锁统一完成。"""
    redis = _FakeRedis()
    service = IdentitySessionService.__new__(IdentitySessionService)
    service._redis = redis
    service._token_prefix = "auth"

    service.revoke_all_user_tokens(7)

    assert redis.revoked == {
        "user_tokens_key": "auth:user:7:tokens",
        "access_key_prefix": "auth:access:",
        "refresh_key_prefix": "auth:refresh:",
        "pair_key_prefix": "auth:pair:",
    }


def test_login_atomically_replaces_previous_token_pair() -> None:
    """并发登录必须调用 Redis 原子替换，而不是先删后写多个命令。"""
    redis = _FakeAtomicRedis()
    service = IdentitySessionService.__new__(IdentitySessionService)
    service._redis = redis
    service._token_prefix = "auth"
    service._password_change_prefix = "auth:password-change-required"
    service._access_ttl = 1800
    service._refresh_ttl = 604800

    metadata = service.replace_token_pair(
        user_id=7,
        access_token="new-access",
        refresh_token="new-refresh",
    )

    assert redis.replaced is True
    assert metadata["user_id"] == 7


def test_refresh_token_can_only_be_rotated_once() -> None:
    """Redis 原子轮换失败时必须按失效 refresh token 拒绝。"""
    redis = _FakeAtomicRedis()
    redis.rotated = False
    service = IdentitySessionService.__new__(IdentitySessionService)
    service._redis = redis
    service._token_prefix = "auth"
    service._password_change_prefix = "auth:password-change-required"
    service._access_ttl = 1800
    service._refresh_ttl = 604800

    with pytest.raises(TokenInvalidError):
        service.rotate_token_pair(
            old_refresh_token="used-refresh",
            user_id=7,
            new_access_token="new-access",
            new_refresh_token="new-refresh",
        )


def test_role_list_never_exposes_super_admin() -> None:
    """最高权限角色不能出现在可管理角色列表。"""
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

    result = RoleService(_RoleSession(roles)).list_roles()

    assert [role["code"] for role in result] == ["manager"]
