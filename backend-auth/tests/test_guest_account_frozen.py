"""游客账号密码冻结单测。

覆盖 backend-auth 侧的自助改密拦截：
- ``youke`` 提交新密码应被 PermissionDeniedError 拒绝。
- 游客仅更新资料（不带密码）不受影响。
- 非游客账号自助改密流程保持原有行为。
"""

from __future__ import annotations

import pytest
from api_common import PermissionDeniedError

from app.core.security import hash_password
from app.services.user_service import UserService
from tests.conftest import FakeDataClient


class _ProfileFakeDataClient(FakeDataClient):
    """扩展 fake：补充 update_profile / get_credentials。"""

    def __init__(self, current_password: str = "old-password") -> None:
        super().__init__()
        # 生成真实哈希，使 verify_password 的分支可被正常走到
        self._password_hash = hash_password(current_password)
        self.profile_calls: list[dict] = []

    def get_credentials(self, username: str) -> dict | None:
        self.calls.append(("get_credentials", {"username": username}))
        return {"id": 2, "password_hash": self._password_hash, "status": 1}

    def update_profile(self, **payload: dict) -> dict:
        self.calls.append(("update_profile", payload))
        self.profile_calls.append(payload)
        return {"id": payload.get("user_id", 2), "username": "test", "status": "updated"}


def _update_profile_kwargs(password: str | None) -> dict:
    """构造 update_profile 公共参数。"""
    return {
        "user_id": 2,
        "username": "youke",
        "nickname": "游客",
        "email": None,
        "phone": None,
        "password": password,
        "current_password": "old-password" if password else None,
    }


def test_guest_cannot_change_own_password(fake_data_client: FakeDataClient) -> None:
    """youke 自助改密应被拒绝，且不应触达数据层。"""
    client = _ProfileFakeDataClient()
    service = UserService(client)
    with pytest.raises(PermissionDeniedError):
        service.update_profile(**_update_profile_kwargs("NewPassword!123"))
    # 拦截发生在调用 backend-data 之前
    assert all(name != "update_profile" for name, _ in client.calls)


def test_guest_can_update_profile_without_password(
    fake_data_client: FakeDataClient,
) -> None:
    """youke 不带密码仅更新资料应正常放行。"""
    client = _ProfileFakeDataClient()
    service = UserService(client)
    result = service.update_profile(**_update_profile_kwargs(None))
    assert result["status"] == "updated"
    assert client.profile_calls[-1]["password_hash"] is None


def test_non_guest_can_change_password(fake_data_client: FakeDataClient) -> None:
    """普通账号改密流程保持原有行为（校验旧密码后放行）。"""
    client = _ProfileFakeDataClient()
    service = UserService(client)
    kwargs = _update_profile_kwargs("NewPassword!123")
    kwargs["username"] = "normal_user"
    result = service.update_profile(**kwargs)
    assert result["status"] == "updated"
    # 密码哈希已透传给数据层
    assert client.profile_calls[-1]["password_hash"] is not None


def test_non_guest_with_wrong_current_password_is_rejected(
    fake_data_client: FakeDataClient,
) -> None:
    """普通账号旧密码校验失败应抛 InvalidCredentialsError（原行为回归）。"""
    from api_common import InvalidCredentialsError

    client = _ProfileFakeDataClient()
    # 通过替换 verify_password 的输入模拟旧密码不匹配
    service = UserService(client)
    kwargs = _update_profile_kwargs("NewPassword!123")
    kwargs["username"] = "normal_user"
    kwargs["current_password"] = "totally-wrong"
    with pytest.raises(InvalidCredentialsError):
        service.update_profile(**kwargs)
    assert all(name != "update_profile" for name, _ in client.calls)
