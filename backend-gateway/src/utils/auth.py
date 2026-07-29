# -*- coding: utf-8 -*-
"""通过 backend-share/auth-utils 获取用户上下文并执行接口鉴权。"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from api_common import (
    PermissionDeniedError,
    ServiceUnavailableError,
    TokenInvalidError,
)
from auth_utils import (
    AuthClient,
    AuthenticatedUser,
    AuthenticationError,
    AuthorizationError,
    AuthServiceUnavailableError,
)
from fastapi import Header


@lru_cache
def get_auth_client() -> AuthClient:
    """复用 share 包提供的 backend-auth 客户端。"""
    return AuthClient()


def close_auth_client() -> None:
    """关闭并清除缓存的共享认证客户端。"""
    client = get_auth_client()
    client.close()
    get_auth_client.cache_clear()


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise TokenInvalidError(message="缺少登录凭证")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise TokenInvalidError(message="登录凭证格式无效")
    return token.strip()


def require_permission(
    *permission_codes: str,
) -> Callable[..., AuthenticatedUser]:
    """创建统一的跨服务权限依赖。"""

    def _check(
        authorization: str | None = Header(default=None),
    ) -> AuthenticatedUser:
        access_token = _extract_bearer(authorization)
        try:
            return get_auth_client().require_any_permission(
                access_token,
                tuple(permission_codes),
            )
        except AuthenticationError as exc:
            raise TokenInvalidError(
                message="登录状态无效或已过期",
            ) from exc
        except AuthorizationError as exc:
            message = (
                "请先修改管理员重置的临时密码"
                if str(exc) == "password change required"
                else "无权访问该接口"
            )
            raise PermissionDeniedError(message=message) from exc
        except AuthServiceUnavailableError as exc:
            raise ServiceUnavailableError(
                message="认证服务暂不可用",
            ) from exc

    return _check
