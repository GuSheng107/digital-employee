"""FastAPI 通用依赖。

- ``verify_api_key``：保护非健康检查类业务端点（与 backend-data 一致）。
- ``get_auth_service``：构造带数据库会话的 AuthService。
- ``get_current_user``：从 Authorization 头解析 access_token，返回当前用户。
- ``require_admin``：校验当前用户是否拥有 admin 角色，复用 get_current_user。
- ``require_permission``：校验当前用户是否持有指定权限码（细粒度权限控制）。

异常策略：业务异常统一使用 ``api_common.ApiException`` 子类，由全局
异常处理器转换为统一响应信封，路由层无需 try/except。
"""

from __future__ import annotations

from collections.abc import Callable

from api_common import (
    PermissionDeniedError,
    TokenInvalidError,
    verify_service_api_key,
)
from auth_utils import ADMIN_ROLE_CODES, FULL_ACCESS_ROLE_CODES
from fastapi import Depends, Header

from app.core.config import settings
from app.schemas.auth import UserInfo
from app.services.auth_service import AuthService


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """校验请求头 ``X-API-Key`` 是否与服务端配置一致。

    当 ``API_KEY`` 未配置时按 fail-closed 返回服务不可用；
    所有环境都应通过环境变量显式配置 ``API_KEY``。

    使用 ``secrets.compare_digest`` 进行常量时间比较，避免时序攻击。

    Args:
        x_api_key: 请求头 ``X-API-Key`` 的值，缺失或为空表示未携带。

    Raises:
        ServiceUnavailableError: 当 ``API_KEY`` 未配置时。
        TokenInvalidError: 当请求头缺失或不匹配时。
    """
    verify_service_api_key(provided=x_api_key, expected=settings.api_key)


def get_auth_service() -> AuthService:
    """构造只依赖共享 data-client 的 AuthService。"""
    return AuthService()


def _extract_bearer(authorization: str | None) -> str:
    """从 Authorization 头解析 Bearer token。

    Raises:
        TokenInvalidError: Authorization 头缺失、格式错误或 token 为空。
    """
    if not authorization:
        raise TokenInvalidError(message="missing authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise TokenInvalidError(message="invalid authorization scheme")
    token = parts[1].strip()
    if not token:
        raise TokenInvalidError(message="empty bearer token")
    return token


def get_current_user(
    authorization: str | None = Header(default=None),
    service: AuthService = Depends(get_auth_service),
) -> UserInfo:
    """解析 access_token 并返回当前登录用户信息。

    Raises:
        TokenInvalidError: token 无效/过期。
        UserDisabledError: 用户已被禁用。
    """
    token = _extract_bearer(authorization)
    return service.get_current_user(token)


def require_admin(
    current_user: UserInfo = Depends(get_current_user),
) -> UserInfo:
    """校验当前用户是否为管理员（super_admin 或 manager 角色）。

    - ``super_admin``：超级管理员（admin 账号专属），默认拥有所有权限。
    - ``manager``：被授权的管理员，vip_level=66，同样拥有管理接口权限。

    作为可复用依赖：既可在 ``dependencies=[Depends(require_admin)]`` 中
    仅用于鉴权拦截，也可作为参数依赖 ``current_user: UserInfo = Depends(require_admin)``
    同时获取当前用户对象。

    Raises:
        PermissionDeniedError: 当前用户不是管理员。
    """
    if not ADMIN_ROLE_CODES.intersection(current_user.roles):
        raise PermissionDeniedError(message="需要管理员权限")
    return current_user


def require_permission(
    *permission_codes: str,
) -> Callable[..., UserInfo]:
    """创建细粒度权限校验依赖。

    校验当前用户是否持有指定的权限码之一（满足其一即放行，OR 语义）。
    与 ``require_admin`` 不同，本依赖基于用户的权限码列表校验，
    防止用户通过修改 token 绕过前端菜单隐藏直接访问接口。

    仅 ``super_admin`` 拥有不可撤销的全权限旁路；``manager`` 必须通过
    角色权限显式授权，避免“管理员角色等于永久万能权限”的越权风险。

    权限码来源于 ``permissions`` 表的 ``code`` 字段，也对应菜单的
    ``permission`` 字段。用户登录后持有的权限码 = ``user_permissions``
    表中关联的权限点（角色作为模板已复制到用户独立集合）。

    用法::

        @router.get(
            "/users",
            dependencies=[Depends(require_permission("user:read", "user:manage"))],
        )
        def list_users(): ...

    Args:
        *permission_codes: 需要的权限码（满足其一即可）。

    Returns:
        FastAPI 依赖函数，校验通过返回当前用户，否则抛出 PermissionDeniedError。

    Raises:
        PermissionDeniedError: 当前用户不持有任何指定的权限码。
    """

    def _check(
        current_user: UserInfo = Depends(get_current_user),
    ) -> UserInfo:
        if current_user.must_change_password:
            raise PermissionDeniedError(message="请先修改管理员重置的临时密码")
        # 最高权限账号旁路；普通管理员仍按显式权限码校验。
        if FULL_ACCESS_ROLE_CODES.intersection(current_user.roles):
            return current_user
        # 检查用户是否持有任一所需权限码
        user_perms = set(current_user.permissions)
        if not any(code in user_perms for code in permission_codes):
            raise PermissionDeniedError(message="无权访问该接口")
        return current_user

    return _check
