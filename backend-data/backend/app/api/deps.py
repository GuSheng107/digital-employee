"""FastAPI 通用认证依赖。

- 服务间调用使用 ``X-API-Key``。
- 浏览器用户调用转发 Bearer token，并通过共享 ``auth-utils`` 向
  backend-auth 获取可信用户上下文和权限判定。
"""

import secrets
from collections.abc import Callable
from functools import lru_cache

from api_common import (
    PermissionDeniedError,
    ServiceUnavailableError,
    TokenInvalidError,
    verify_service_api_key,
)
from auth_utils import (
    AuthClient,
    AuthenticationError,
    AuthorizationError,
    AuthServiceUnavailableError,
)
from fastapi import Header

from app.core.config import settings


async def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """校验请求头 ``X-API-Key`` 是否与服务端配置一致。

    ``API_KEY`` 未配置时拒绝内部接口访问，避免服务间鉴权静默失效；
    已配置时使用常量时间比较校验请求凭证。

    Args:
        x_api_key: 请求头 ``X-API-Key`` 的值，缺失或为空表示未携带。

    Raises:
        ServiceUnavailableError: 当服务端未配置 ``API_KEY`` 时。
        TokenInvalidError: 当请求头缺失或不匹配时。
    """
    verify_service_api_key(provided=x_api_key, expected=settings.api_key)


@lru_cache
def get_auth_client() -> AuthClient:
    """构造并复用共享 backend-auth 客户端。"""
    return AuthClient(
        base_url=settings.backend_auth_base_url,
        timeout_seconds=float(settings.dependency_timeout_seconds),
    )


def _extract_bearer(authorization: str | None) -> str:
    """解析 Bearer token。"""
    if not authorization:
        raise TokenInvalidError(message="missing authorization header")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise TokenInvalidError(message="invalid authorization scheme")
    return token.strip()


def _matches_service_api_key(x_api_key: str | None) -> bool:
    """判断请求是否携带有效服务间 API Key。"""
    expected = settings.api_key
    return bool(
        expected
        and x_api_key
        and secrets.compare_digest(x_api_key, expected)
    )


def require_service_or_permission(
    *permission_codes: str,
) -> Callable[..., None]:
    """创建“服务 API Key 或用户权限码”二选一依赖。"""

    def _check(
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
    ) -> None:
        if _matches_service_api_key(x_api_key):
            return
        access_token = _extract_bearer(authorization)
        try:
            get_auth_client().require_any_permission(
                access_token,
                tuple(permission_codes),
            )
        except AuthenticationError as exc:
            raise TokenInvalidError(message="登录状态无效或已过期") from exc
        except AuthorizationError as exc:
            raise PermissionDeniedError(message="无权访问该数据中台接口") from exc
        except AuthServiceUnavailableError as exc:
            raise ServiceUnavailableError(message="认证服务暂不可用") from exc

    return _check
