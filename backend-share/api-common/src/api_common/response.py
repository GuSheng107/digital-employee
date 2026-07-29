"""统一 API 响应模型与构造工具。

所有后端服务返回的 HTTP 响应体都遵循同一信封：
    {"success": bool, "message": str, "data": Any}

构造函数返回 dict 而非 BaseModel 实例，便于 FastAPI 路由直接作为
响应体返回，无需额外 .model_dump() 转换。
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorCode:
    """业务错误码常量。

    按 HTTP 状态码语义分组，便于前端按错误码做差异化处理（如 401 跳登录、
    403 提示无权限、422 字段校验、429 限流退避）。
    覆盖通用 Web 错误与 AI 应用常见错误（模型/向量/配额/内容安全）。
    """

    # ── 400 客户端请求错误 ──
    VALIDATION_FAILED = "VALIDATION_FAILED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    USER_DISABLED = "USER_DISABLED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    DUPLICATE_RESOURCE = "DUPLICATE_RESOURCE"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"

    # ── 401/403 认证与授权 ──
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"
    SESSION_REPLACED = "SESSION_REPLACED"
    PERMISSION_DENIED = "PERMISSION_DENIED"

    # ── 429 限流与配额 ──
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    BILLING_REQUIRED = "BILLING_REQUIRED"

    # ── AI 应用专属 ──
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    CONTEXT_LENGTH_EXCEEDED = "CONTEXT_LENGTH_EXCEEDED"
    CONTENT_FILTERED = "CONTENT_FILTERED"
    GENERATION_FAILED = "GENERATION_FAILED"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    VECTOR_STORE_ERROR = "VECTOR_STORE_ERROR"

    # ── 5xx 服务端错误 ──
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


class ApiResponse(BaseModel):
    """统一 API 响应结构。

    - ``success``：业务是否成功（与 HTTP 状态码解耦，HTTP 200 也可能 success=False）。
    - ``message``：面向调用方的提示文案，前端可直接展示。
    - ``data``：业务数据，失败时可为 None 或携带错误详情。
    """

    success: bool
    message: str = "ok"
    data: Any = None


class ErrorResponse(BaseModel):
    """错误响应详情，可作为 ApiResponse.data 字段的结构化错误信息。"""

    code: str = ErrorCode.INTERNAL_ERROR
    detail: str = ""
    fields: dict[str, str] = Field(
        default_factory=dict,
        description="字段级错误信息，如表单校验失败时 {username: '必填'}",
    )


class PageResponse(BaseModel, Generic[T]):
    """分页响应数据，作为 ApiResponse.data 字段使用。"""

    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20


def success_response(data: Any = None, message: str = "ok") -> dict:
    """构造成功响应字典。"""
    return {"success": True, "message": message, "data": data}


def fail_response(
    message: str = "error",
    data: Any = None,
) -> dict:
    """构造失败响应字典。

    Args:
        message: 错误提示文案，前端可直接展示。
        data: 可选的错误详情，如 ErrorResponse 结构化字段。
    """
    return {"success": False, "message": message, "data": data}
