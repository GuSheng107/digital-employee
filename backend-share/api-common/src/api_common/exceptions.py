"""统一业务异常体系。

设计目标
========

1. **业务错误码有明确归属**：每个异常携带 ``ErrorCode`` 常量，前端可通过
   ``error.code`` 做差异化处理（401 跳登录、429 限流退避、CONTENT_FILTERED
   显示内容审核提示等）。
2. **响应信封一致**：异常经全局处理器转换后仍返回
   ``{"success": False, "message": str, "data": {"code": str, "detail": str}}``，
   与成功响应结构对齐，前端拦截器无需区分异常路径。
3. **HTTP 语义保留**：异常携带 ``http_status``，全局处理器按此设置响应状态码，
   便于网关/监控按 HTTP 状态做告警与统计。

使用方式
========

路由中直接 raise，无需再拼装 HTTPException：

    from api_common import ApiException, ErrorCode

    raise ApiException(
        code=ErrorCode.INVALID_CREDENTIALS,
        message="用户名或密码错误",
        http_status=401,
    )

也可使用预定义子类，进一步降低调用成本：

    from api_common import InvalidCredentialsError
    raise InvalidCredentialsError()
"""

from __future__ import annotations

import secrets
from typing import Any

from api_common.response import ErrorCode


class ApiException(Exception):
    """业务异常基类。

    Args:
        code: 业务错误码，取自 :class:`api_common.ErrorCode`。
        message: 面向用户的错误文案，将直接放入响应 ``message`` 字段。
        http_status: 对应的 HTTP 状态码，默认 400。
        detail: 可选的错误详情，放入响应 ``data.detail``，便于排查问题。
    """

    code: str = ErrorCode.INTERNAL_ERROR
    message: str = "internal error"
    http_status: int = 500

    def __init__(
        self,
        *,
        code: str | None = None,
        message: str | None = None,
        http_status: int | None = None,
        detail: Any | None = None,
    ) -> None:
        self.code = code if code is not None else self.code
        self.message = message if message is not None else self.message
        self.http_status = http_status if http_status is not None else self.http_status
        self.detail = detail
        super().__init__(self.message)

    def to_response(self) -> dict:
        """转换为统一响应信封字典。"""
        return {
            "success": False,
            "message": self.message,
            "data": {
                "code": self.code,
                "detail": self.detail if self.detail is not None else "",
            },
        }


# ── 400 客户端请求错误 ──────────────────────────────────────────


class ValidationError(ApiException):
    """请求参数校验失败。"""

    code = ErrorCode.VALIDATION_FAILED
    message = "request validation failed"
    http_status = 422


class InvalidCredentialsError(ApiException):
    """用户名或密码错误。"""

    code = ErrorCode.INVALID_CREDENTIALS
    message = "invalid credentials"
    http_status = 401


class UserDisabledError(ApiException):
    """用户已被禁用。"""

    code = ErrorCode.USER_DISABLED
    message = "user disabled"
    http_status = 401


class ResourceNotFoundError(ApiException):
    """资源不存在。"""

    code = ErrorCode.RESOURCE_NOT_FOUND
    message = "resource not found"
    http_status = 404


class DuplicateResourceError(ApiException):
    """资源已存在（重复创建）。"""

    code = ErrorCode.DUPLICATE_RESOURCE
    message = "resource already exists"
    http_status = 409


class ConflictError(ApiException):
    """资源当前状态与请求操作冲突。"""

    code = ErrorCode.RESOURCE_CONFLICT
    message = "resource state conflict"
    http_status = 409


# ── 401/403 认证与授权 ─────────────────────────────────────────


class TokenExpiredError(ApiException):
    """token 已过期。"""

    code = ErrorCode.TOKEN_EXPIRED
    message = "token expired"
    http_status = 401


class TokenInvalidError(ApiException):
    """token 无效。"""

    code = ErrorCode.TOKEN_INVALID
    message = "invalid token"
    http_status = 401


class PermissionDeniedError(ApiException):
    """无权限访问该资源。"""

    code = ErrorCode.PERMISSION_DENIED
    message = "permission denied"
    http_status = 403


# ── 429 限流与配额 ──────────────────────────────────────────────


class RateLimitExceededError(ApiException):
    """请求过于频繁，触发限流。"""

    code = ErrorCode.RATE_LIMIT_EXCEEDED
    message = "rate limit exceeded"
    http_status = 429


class QuotaExceededError(ApiException):
    """配额已耗尽。"""

    code = ErrorCode.QUOTA_EXCEEDED
    message = "quota exceeded"
    http_status = 429


class BillingRequiredError(ApiException):
    """需要付费/充值才能使用。"""

    code = ErrorCode.BILLING_REQUIRED
    message = "billing required"
    http_status = 402


# ── AI 应用专属 ─────────────────────────────────────────────────


class ModelUnavailableError(ApiException):
    """模型服务不可用。"""

    code = ErrorCode.MODEL_UNAVAILABLE
    message = "model unavailable"
    http_status = 503


class ContextLengthExceededError(ApiException):
    """上下文长度超限。"""

    code = ErrorCode.CONTEXT_LENGTH_EXCEEDED
    message = "context length exceeded"
    http_status = 413


class ContentFilteredError(ApiException):
    """内容被安全策略过滤。"""

    code = ErrorCode.CONTENT_FILTERED
    message = "content filtered by safety policy"
    http_status = 400


class GenerationFailedError(ApiException):
    """模型生成失败。"""

    code = ErrorCode.GENERATION_FAILED
    message = "generation failed"
    http_status = 502


class EmbeddingFailedError(ApiException):
    """向量化失败。"""

    code = ErrorCode.EMBEDDING_FAILED
    message = "embedding failed"
    http_status = 502


class VectorStoreError(ApiException):
    """向量库异常。"""

    code = ErrorCode.VECTOR_STORE_ERROR
    message = "vector store error"
    http_status = 500


# ── 5xx 服务端错误 ─────────────────────────────────────────────


class InternalError(ApiException):
    """服务内部错误。"""

    code = ErrorCode.INTERNAL_ERROR
    message = "internal server error"
    http_status = 500


class DependencyUnavailableError(ApiException):
    """依赖服务（DB/Redis/Minio 等）不可用。"""

    code = ErrorCode.DEPENDENCY_UNAVAILABLE
    message = "dependency unavailable"
    http_status = 503


class ServiceUnavailableError(ApiException):
    """服务暂不可用。"""

    code = ErrorCode.SERVICE_UNAVAILABLE
    message = "service unavailable"
    http_status = 503


def verify_service_api_key(
    *,
    provided: str | None,
    expected: str,
) -> None:
    """以 fail-closed 策略校验服务间 API Key。"""
    if not expected:
        raise ServiceUnavailableError(message="服务间 API Key 尚未配置")
    if not provided or not secrets.compare_digest(provided, expected):
        raise TokenInvalidError(message="服务凭证无效")
