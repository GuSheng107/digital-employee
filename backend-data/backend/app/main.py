from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from api_common import (
    ApiException,
    DependencyUnavailableError,
    ErrorCode,
    InternalError,
)
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from psycopg2 import errorcodes
from sqlalchemy.exc import ProgrammingError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.config import settings
from app.schemas.common import ApiResponse
from app.schemas.health import ServiceInfo
from app.utils.response import success_response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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
    """把业务异常转换为带错误码的统一响应信封。"""
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
        logger.warning(
            "[DATABASE_SCHEMA] {} {} code={}",
            request.method,
            request.url.path,
            database_code,
        )
        return JSONResponse(
            status_code=error.http_status,
            content=error.to_response(),
        )
    logger.exception(
        "[DATABASE_PROGRAMMING_ERROR] {} {}: {}",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content=InternalError().to_response(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
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
