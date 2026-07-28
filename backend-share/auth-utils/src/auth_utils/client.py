"""backend-auth 用户上下文与权限校验客户端。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

AUTH_ME_PATH = "/api/v1/auth/me"
ROLE_CODE_SUPER_ADMIN = "super_admin"
DEFAULT_AUTH_BASE_URL = "http://127.0.0.1:8020"
DEFAULT_TIMEOUT_SECONDS = 5.0


class AuthenticationError(RuntimeError):
    """access token 无效、过期或缺失。"""


class AuthorizationError(RuntimeError):
    """用户已认证但不具备目标权限。"""


class AuthServiceUnavailableError(RuntimeError):
    """backend-auth 网络或服务异常。"""


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """跨服务使用的最小用户上下文。"""

    id: int
    username: str
    roles: tuple[str, ...]
    permissions: tuple[str, ...]


def _read_string_list(value: Any) -> tuple[str, ...]:
    """把未知 JSON 值安全转换为字符串元组。"""
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


class AuthClient:
    """通过 backend-auth HTTP API 获取可信用户上下文并做权限判定。"""

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        configured_url = (
            base_url
            or os.environ.get("BACKEND_AUTH_BASE_URL")
            or DEFAULT_AUTH_BASE_URL
        )
        self._base_url = configured_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_current_user(self, access_token: str) -> AuthenticatedUser:
        """向 backend-auth 校验 token 并返回最小用户上下文。"""
        if not access_token:
            raise AuthenticationError("missing access token")
        try:
            response = httpx.get(
                f"{self._base_url}{AUTH_ME_PATH}",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=self._timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise AuthServiceUnavailableError("backend-auth unavailable") from exc

        if response.status_code == 401:
            raise AuthenticationError("invalid or expired access token")
        if response.status_code == 403:
            raise AuthorizationError("permission denied")
        if response.status_code >= 500:
            raise AuthServiceUnavailableError("backend-auth unavailable")

        try:
            payload = response.json()
        except ValueError as exc:
            raise AuthServiceUnavailableError("invalid backend-auth response") from exc
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise AuthenticationError("backend-auth rejected access token")

        data = payload.get("data")
        if not isinstance(data, dict):
            raise AuthServiceUnavailableError("missing backend-auth user context")
        user_id = data.get("id")
        username = data.get("username")
        if not isinstance(user_id, int) or not isinstance(username, str):
            raise AuthServiceUnavailableError("invalid backend-auth user context")
        return AuthenticatedUser(
            id=user_id,
            username=username,
            roles=_read_string_list(data.get("roles")),
            permissions=_read_string_list(data.get("permissions")),
        )

    def require_any_permission(
        self,
        access_token: str,
        required_permissions: tuple[str, ...],
    ) -> AuthenticatedUser:
        """校验用户持有任一目标权限；超级管理员拥有全权限旁路。"""
        user = self.get_current_user(access_token)
        if ROLE_CODE_SUPER_ADMIN in user.roles:
            return user
        if not any(
            permission in user.permissions
            for permission in required_permissions
        ):
            raise AuthorizationError("permission denied")
        return user
