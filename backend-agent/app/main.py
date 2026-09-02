"""backend-agent FastAPI 应用入口。"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from api_common import ApiResponse, ErrorCode, InternalError, success_response
from api_common.exceptions import ApiException
from data_client import get_data_client
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from observability import TraceBatch, TraceMiddleware, TraceService, TraceSink
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import Settings, settings
from app.core.logging import configure_logging
from app.core.runtime import RuntimeManager
from app.schemas.health import ServiceInfo

logger = logging.getLogger("backend_agent.app")


async def _export_trace_batch(batch: TraceBatch) -> None:
    """把 Agent Trace 委托给 backend-data 持久化。"""
    await get_data_client().submit_trace_batch(batch.model_dump(mode="json"))


async def _discard_trace_batch(_batch: TraceBatch) -> None:
    """丢弃 Trace 批次，供隔离测试构造应用。"""


async def _close_data_client() -> None:
    """关闭共享 data-client 的同步和异步连接池。"""
    client = get_data_client()
    await client.aclose()
    client.close()


def create_app(
    *,
    configured_settings: Settings | None = None,
    runtime: RuntimeManager | None = None,
    trace_sink: TraceSink | None = None,
) -> FastAPI:
    """创建可注入配置和运行时的 FastAPI 应用。

    Args:
        configured_settings: 测试或运行时覆盖配置。
        runtime: 测试或运行时覆盖生命周期管理器。
        trace_sink: Trace 输出函数；默认提交至 backend-data。

    Returns:
        配置完成的 FastAPI 应用。
    """
    active_settings = configured_settings or settings
    active_runtime = runtime or RuntimeManager()
    active_trace_sink = trace_sink or _export_trace_batch
    configure_logging(active_settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.settings = active_settings
        application.state.runtime = active_runtime
        await active_runtime.start()
        try:
            yield
        finally:
            await active_runtime.stop()
            if active_trace_sink is _export_trace_batch:
                await _close_data_client()

    application = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
        docs_url="/docs" if active_settings.docs_enabled else None,
        redoc_url="/redoc" if active_settings.docs_enabled else None,
        openapi_url="/openapi.json" if active_settings.docs_enabled else None,
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.runtime = active_runtime
    application.add_middleware(
        TraceMiddleware,
        service=TraceService.BACKEND_AGENT,
        sink=active_trace_sink,
    )

    @application.exception_handler(ApiException)
    async def api_exception_handler(
        _request: Request,
        exc: ApiException,
    ) -> JSONResponse:
        """把业务异常转换为统一错误响应。"""
        headers = None
        if exc.http_status == 429 and isinstance(exc.detail, dict):
            retry_after = exc.detail.get("retry_after_seconds")
            if isinstance(retry_after, int) and retry_after > 0:
                headers = {"Retry-After": str(retry_after)}
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_response(),
            headers=headers,
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        """把 Starlette HTTP 异常转换为统一错误响应。"""
        message = "internal server error" if exc.status_code >= 500 else str(exc.detail)
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

    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """把请求校验异常转换为统一错误响应。"""
        validation_errors = [
            {
                "location": [str(part) for part in error.get("loc", ())],
                "message": str(error.get("msg", "请求参数校验失败")),
                "type": str(error.get("type", "validation_error")),
            }
            for error in exc.errors()
        ]
        first_message = validation_errors[0]["message"] if validation_errors else "请求参数校验失败"
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "message": f"请求参数校验失败：{first_message}",
                "data": {
                    "code": ErrorCode.VALIDATION_FAILED,
                    "detail": validation_errors,
                },
            },
        )

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(
        _request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """兜底未捕获异常并对外隐藏内部细节。"""
        logger.error(
            "Unhandled Agent request error",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=500,
            content=InternalError().to_response(),
        )

    @application.get("/", response_model=ApiResponse)
    def root() -> dict[str, Any]:
        """返回 Agent 服务基本信息。"""
        return cast(
            dict[str, Any],
            success_response(
                ServiceInfo(
                    name=active_settings.app_name,
                    version=active_settings.app_version,
                    environment=active_settings.app_env,
                    status="running",
                ).model_dump()
            ),
        )

    application.include_router(api_router, prefix=active_settings.api_prefix)
    return application


app = create_app()
