"""FastAPI 启动入口。

构造应用实例、注册全局异常处理、挂载 CORS 中间件与 API 路由。
统一响应格式为 ``{"success": bool, "message": str, "data": Any}``。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.router import api_router
from app.core.config import settings
from app.schemas.common import ApiResponse
from app.schemas.health import ServiceInfo
from app.utils.response import fail_response, success_response


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


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """统一处理 HTTPException。

    对 5xx 服务端异常进行日志记录并对外脱敏；4xx 客户端异常
    沿用 detail 文案，便于调用方定位问题。
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
        content=fail_response(message=message),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """请求体校验失败统一返回 422 与详细错误信息。"""
    return JSONResponse(
        status_code=422,
        content=fail_response(message="request validation failed", data=exc.errors()),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底未捕获异常，避免向上抛出原始堆栈。"""
    logger.exception(
        "[UNHANDLED] {} {}: {}",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content=fail_response(message="internal server error"),
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
