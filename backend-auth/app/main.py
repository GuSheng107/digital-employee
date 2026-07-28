"""FastAPI 启动入口。

构造应用实例、注册全局异常处理、挂载 CORS 中间件与 API 路由。
统一响应格式为 ``{"success": bool, "message": str, "data": Any}``，
错误响应的 ``data`` 字段统一为 ``{"code": str, "detail": str}``，
前端可通过 ``error.code`` 做差异化处理（如 401 跳登录、429 限流退避）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from api_common import (
    ApiResponse,
    ErrorCode,
    InternalError,
    success_response,
)
from api_common.exceptions import ApiException
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.router import api_router
from app.core.config import settings
from app.schemas.health import ServiceInfo


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期上下文（当前无启动/关闭副作用，预留扩展点）。"""
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.exception_handler(ApiException)
async def api_exception_handler(request: Request, exc: ApiException) -> JSONResponse:
    """业务异常统一处理。

    将 ``ApiException`` 转换为统一响应信封：
    ``{"success": False, "message": str, "data": {"code": str, "detail": str}}``。

    5xx 异常记录日志并对外脱敏；4xx 异常沿用业务文案。
    """
    if exc.http_status >= 500:
        logger.warning(
            "[ApiException] {} {} code={} status={} detail={}",
            request.method,
            request.url.path,
            exc.code,
            exc.http_status,
            exc.detail,
        )
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_response(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """FastAPI 内置 HTTPException 兜底处理。

    部分第三方依赖（如 Starlette 的认证中间件）仍会抛出 HTTPException，
    这里将其转换为统一信封，code 字段用 ``HTTP_{status}`` 标识，便于前端
    区分来源。
    """
    if exc.status_code >= 500:
        logger.warning(
            "[HTTPException] {} {} status={} detail={}",
            request.method,
            request.url.path,
            exc.status_code,
            exc.detail,
        )
        message = "internal server error"
    else:
        message = str(exc.detail) if exc.detail else "error"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": message,
            "data": {
                "code": f"HTTP_{exc.status_code}",
                "detail": str(exc.detail) if exc.detail else "",
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """请求体校验失败统一返回 422 与详细错误信息。"""
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "request validation failed",
            "data": {
                "code": ErrorCode.VALIDATION_FAILED,
                "detail": exc.errors(),
            },
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底未捕获异常，避免向上抛出原始堆栈。

    统一转换为 ``InternalError`` 响应，对外脱敏。
    """
    logger.exception(
        "[UNHANDLED] {} {}: {}",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content=InternalError().to_response(),
    )


@app.get("/", response_model=ApiResponse)
def root() -> dict:
    """根路径返回服务基本信息。"""
    return success_response(
        ServiceInfo(
            name=settings.app_name,
            version=settings.app_version,
            environment=settings.app_env,
            status="running",
        ).model_dump()
    )


app.include_router(api_router, prefix=settings.api_prefix)
