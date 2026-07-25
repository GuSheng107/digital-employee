from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.api.routes import ddl
from app.core.config import settings
from app.core.database import init_core_schema
from app.schemas.health import ServiceInfo
from app.utils.response import fail_response


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        try:
            init_core_schema()
        except Exception as exc:
            print(f"Skip auto create tables: {exc}")
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=fail_response(message=str(exc.detail)),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=fail_response(message="request validation failed", data=exc.errors()),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=fail_response(message=str(exc)),
    )


@app.get("/", response_model=ServiceInfo)
def root() -> ServiceInfo:
    return ServiceInfo(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        status="running",
    )


@app.get("/health")
def health() -> dict:
    return {"success": True, "message": "ok", "data": {"status": "healthy"}}


app.include_router(api_router, prefix=settings.api_prefix)
app.include_router(ddl.router, prefix="/api/ddl", tags=["ddl-compat"])
