from time import perf_counter

from fastapi import HTTPException, Request
from loguru import logger
from sqlalchemy.engine import make_url
from sqlalchemy import text

from app.core.config import settings
from app.core.database import DatabaseRole, get_database_client
from app.schemas.ddl import DdlPreviewData, DdlTableDefinition
from app.services.ddl_generator import (
    DdlValidationError,
    build_create_table_sql,
    build_table_identifier,
)


EXECUTABLE_ENVS = {"local", "dev", "test"}


class DdlService:
    def preview(self, payload: DdlTableDefinition) -> DdlPreviewData:
        try:
            ddl = build_create_table_sql(payload)
        except DdlValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return DdlPreviewData(
            schema_name=payload.schema_name,
            table_name=payload.table_name,
            table_identifier=build_table_identifier(payload),
            ddl=ddl,
            execution_enabled=self.execution_enabled(),
        )

    def execute(self, payload: DdlTableDefinition, request: Request | None = None) -> dict:
        self._ensure_execution_allowed(payload)
        preview = self.preview(payload)
        start = perf_counter()

        audit_base = {
            "event": "ddl_create_table",
            "env": settings.app_env,
            "schema": payload.schema_name,
            "table": payload.table_name,
            "allowed_database": settings.ddl_allowed_database,
            "client": request.client.host if request and request.client else None,
        }
        logger.info("{audit}", audit={**audit_base, "result": "started"})

        try:
            client = get_database_client(DatabaseRole.DDL)
            with client.engine.begin() as connection:
                exists = connection.execute(
                    text("SELECT to_regclass(:identifier)"),
                    {"identifier": f"{payload.schema_name}.{payload.table_name}"},
                ).scalar()
                if exists is not None:
                    raise HTTPException(status_code=409, detail="table already exists")
                connection.exec_driver_sql(preview.ddl)

            elapsed_ms = round((perf_counter() - start) * 1000, 2)
            logger.info(
                "{audit}",
                audit={**audit_base, "result": "success", "elapsed_ms": elapsed_ms},
            )
            return {**preview.model_dump(), "executed": True}
        except HTTPException:
            logger.warning("{audit}", audit={**audit_base, "result": "table_exists"})
            raise
        except Exception as exc:
            elapsed_ms = round((perf_counter() - start) * 1000, 2)
            logger.error(
                "{audit}",
                audit={
                    **audit_base,
                    "result": "failed",
                    "elapsed_ms": elapsed_ms,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc)[:300],
                },
            )
            raise HTTPException(
                status_code=500,
                detail=f"DDL execution failed: {exc.__class__.__name__}",
            ) from exc

    def execution_enabled(self) -> bool:
        return bool(
            settings.ddl_execution_enabled
            and settings.app_env in EXECUTABLE_ENVS
            and settings.ddl_database_url
        )

    def _ensure_execution_allowed(self, payload: DdlTableDefinition) -> None:
        if settings.app_env not in EXECUTABLE_ENVS:
            raise HTTPException(status_code=403, detail="DDL execution is disabled outside local/dev/test")
        if not settings.ddl_execution_enabled:
            raise HTTPException(status_code=403, detail="DDL execution is disabled")
        if not settings.ddl_database_url:
            raise HTTPException(status_code=503, detail="DDL_DATABASE_URL is not configured")
        if settings.ddl_allowed_database:
            ddl_database_name = make_url(settings.ddl_database_url).database
            if ddl_database_name != settings.ddl_allowed_database:
                raise HTTPException(
                    status_code=403,
                    detail="DDL database is not allowed",
                )
        if payload.schema_name not in (settings.ddl_allowed_schemas_list or ["public"]):
            raise HTTPException(status_code=403, detail="schema is not allowed")
