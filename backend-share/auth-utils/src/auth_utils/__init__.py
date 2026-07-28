"""跨服务 backend-auth 鉴权与用户上下文客户端。"""

from auth_utils.client import (
    AuthClient,
    AuthenticatedUser,
    AuthenticationError,
    AuthorizationError,
    AuthServiceUnavailableError,
)
from auth_utils.permissions import PermissionCode

__all__ = [
    "AuthClient",
    "AuthenticatedUser",
    "AuthenticationError",
    "AuthorizationError",
    "AuthServiceUnavailableError",
    "PermissionCode",
]
