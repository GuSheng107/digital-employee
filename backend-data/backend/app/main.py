from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from api_common import (
    ApiException,
    ApiResponse,
    DependencyUnavailableError,
    ErrorCode,
    InternalError,
    success_response,
)
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from observability import TraceMiddleware, TraceService
from psycopg2 import errorcodes
from sqlalchemy.exc import ProgrammingError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import close_auth_client
from app.api.router import api_router
from app.core.business_observability import configure_business_observability
from app.core.config import settings
from app.core.observability import persist_trace_batch
from app.schemas.health import ServiceInfo
from app.services.message_broker_service import get_message_broker_service

configure_business_observability()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await get_message_broker_service().close()
        close_auth_client()


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
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
app.add_middleware(
    TraceMiddleware,
    service=TraceService.BACKEND_DATA,
    sink=persist_trace_batch,
)


@app.exception_handler(ApiException)
async def api_exception_handler(request: Request, exc: ApiException) -> JSONResponse:
    """把业务异常转换为带错误码的统一响应信封。"""
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


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """统一处理 HTTPException。

    对 5xx 服务端异常进行日志记录并对外脱敏；4xx 客户端异常
    沿用 detail 文案，便于调用方定位问题。
    """
    if exc.status_code >= 500:
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
    validation_errors = [
        {
            "location": [str(part) for part in error.get("loc", ())],
            "message": str(error.get("msg", "请求参数校验失败")),
            "type": str(error.get("type", "validation_error")),
        }
        for error in exc.errors()
    ]
    first_message = (
        validation_errors[0]["message"] if validation_errors else "请求参数校验失败"
    )
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


@app.exception_handler(ProgrammingError)
async def database_programming_error_handler(
    request: Request,
    exc: ProgrammingError,
) -> JSONResponse:
    """把缺表等数据库结构问题转换为可定位的依赖错误码。"""
    database_code = getattr(exc.orig, "pgcode", None)
    if database_code == errorcodes.UNDEFINED_TABLE:
        error = DependencyUnavailableError(
            message="数据库业务表尚未初始化，请先执行结构变更 SQL",
        )
        return JSONResponse(
            status_code=error.http_status,
            content=error.to_response(),
        )
    return JSONResponse(
        status_code=500,
        content=InternalError().to_response(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=InternalError().to_response(),
    )


@app.get("/", response_model=ApiResponse)
def root() -> dict:
    return success_response(
        ServiceInfo(
            name=settings.app_name,
            version=settings.app_version,
            environment=settings.app_env,
            status="running",
        ).model_dump()
    )


@app.get("/health")
def health() -> dict:
    return {"success": True, "message": "ok", "data": {"status": "healthy"}}


app.include_router(api_router, prefix=settings.api_prefix)
