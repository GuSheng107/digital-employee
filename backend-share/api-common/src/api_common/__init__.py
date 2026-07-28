"""digital-employee 后端共享的 API 响应模型与工具。

统一响应信封：``{"success": bool, "message": str, "data": Any}``。
各后端服务（auth/data/gateway）统一引用本包，避免重复维护。

典型用法
========

成功响应::

    from api_common import ApiResponse, success_response

    @router.get("/me", response_model=ApiResponse)
    def me() -> dict:
        return success_response(user_info)

业务异常::

    from api_common import InvalidCredentialsError

    raise InvalidCredentialsError(message="用户名或密码错误")
"""

from api_common.exceptions import (
    ApiException,
    BillingRequiredError,
    ContentFilteredError,
    ContextLengthExceededError,
    DependencyUnavailableError,
    DuplicateResourceError,
    EmbeddingFailedError,
    GenerationFailedError,
    InternalError,
    InvalidCredentialsError,
    ModelUnavailableError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitExceededError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    TokenExpiredError,
    TokenInvalidError,
    UserDisabledError,
    ValidationError,
    VectorStoreError,
)
from api_common.response import (
    ApiResponse,
    ErrorCode,
    ErrorResponse,
    PageResponse,
    fail_response,
    success_response,
)

__all__ = [
    # 响应模型
    "ApiResponse",
    "ErrorResponse",
    "PageResponse",
    "ErrorCode",
    "success_response",
    "fail_response",
    # 异常基类
    "ApiException",
    # 4xx
    "ValidationError",
    "InvalidCredentialsError",
    "UserDisabledError",
    "ResourceNotFoundError",
    "DuplicateResourceError",
    # 401/403
    "TokenExpiredError",
    "TokenInvalidError",
    "PermissionDeniedError",
    # 429/402
    "RateLimitExceededError",
    "QuotaExceededError",
    "BillingRequiredError",
    # AI 应用
    "ModelUnavailableError",
    "ContextLengthExceededError",
    "ContentFilteredError",
    "GenerationFailedError",
    "EmbeddingFailedError",
    "VectorStoreError",
    # 5xx
    "InternalError",
    "DependencyUnavailableError",
    "ServiceUnavailableError",
]
