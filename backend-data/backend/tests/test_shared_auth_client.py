"""共享 auth-utils 客户端回归测试。"""

from __future__ import annotations

from typing import Any

import pytest
from auth_utils import AuthClient, AuthorizationError, PermissionCode
from auth_utils import client as auth_client_module


class _FakeResponse:
    """最小 httpx.Response 替身。"""

    status_code = 200

    def json(self) -> dict[str, Any]:
        """返回 backend-auth /auth/me 标准信封。"""
        return {
            "success": True,
            "message": "ok",
            "data": {
                "id": 7,
                "username": "manager",
                "roles": ["manager"],
                "permissions": [PermissionCode.DATA_PLATFORM_DATA_ITEMS],
            },
        }


def test_shared_auth_client_returns_user_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """其他服务可经 share 获取可信用户与权限上下文。"""
    monkeypatch.setattr(
        auth_client_module.httpx,
        "get",
        lambda *_args, **_kwargs: _FakeResponse(),
    )
    client = AuthClient(base_url="http://auth.invalid")

    user = client.require_any_permission(
        "token",
        (PermissionCode.DATA_PLATFORM_DATA_ITEMS,),
    )

    assert user.id == 7
    assert user.username == "manager"


def test_shared_auth_client_rejects_missing_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """manager 没有显式权限时不能通过跨服务鉴权。"""
    monkeypatch.setattr(
        auth_client_module.httpx,
        "get",
        lambda *_args, **_kwargs: _FakeResponse(),
    )
    client = AuthClient(base_url="http://auth.invalid")

    with pytest.raises(AuthorizationError):
        client.require_any_permission(
            "token",
            (PermissionCode.DATA_PLATFORM_CONFIG,),
        )
