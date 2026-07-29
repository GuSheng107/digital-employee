import time
from collections.abc import Generator
from contextlib import contextmanager
from enum import Enum

from observability import (
    TraceEventType,
    TraceLevel,
    record_trace_event,
    sanitize_value,
)
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class DatabaseRole(str, Enum):
    CORE = "core"
    VECTOR = "vector"


class Base(DeclarativeBase):
    pass


class DatabaseClientWrapper:
    """Centralized SQLAlchemy wrapper for one PostgreSQL database role."""

    def __init__(self, role: DatabaseRole) -> None:
        self.role = role
        if role == DatabaseRole.CORE:
            self.database_url = settings.core_database_url
        else:
            self.database_url = settings.vector_database_url
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine(
                self.database_url,
                pool_pre_ping=True,
                future=True,
            )
            _configure_sql_observability(self._engine, self.role)
        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        if self._session_factory is None:
            self._session_factory = sessionmaker(
                bind=self.engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
            )
        return self._session_factory

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        with self.session_factory() as session:
            yield session

    def ping(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

_database_clients: dict[DatabaseRole, DatabaseClientWrapper] = {}


def _configure_sql_observability(engine: Engine, role: DatabaseRole) -> None:
    """为 SQLAlchemy 引擎接入不记录参数值的 SQL 执行事件。"""

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del cursor, statement, parameters, context, executemany
        info = getattr(connection, "info", None)
        if isinstance(info, dict):
            info.setdefault("_trace_sql_started", []).append(time.perf_counter_ns())

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del cursor, parameters, context
        info = getattr(connection, "info", None)
        started_ns = None
        if isinstance(info, dict):
            stack = info.get("_trace_sql_started")
            if isinstance(stack, list) and stack:
                started_ns = stack.pop()
        duration_ms = (
            (time.perf_counter_ns() - started_ns) // 1_000_000
            if isinstance(started_ns, int)
            else 0
        )
        record_trace_event(
            TraceEventType.DATABASE,
            "PostgreSQL 执行",
            attributes={
                "database_role": role.value,
                "statement": sanitize_value(statement),
                "executemany": executemany,
                "duration_ms": duration_ms,
            },
        )

    @event.listens_for(engine, "handle_error")
    def _handle_error(exception_context: object) -> None:
        original_exception = getattr(
            exception_context,
            "original_exception",
            None,
        )
        record_trace_event(
            TraceEventType.DATABASE,
            "PostgreSQL 执行异常",
            level=TraceLevel.ERROR,
            attributes={
                "database_role": role.value,
                "exception_type": (
                    type(original_exception).__name__
                    if original_exception is not None
                    else "DatabaseError"
                ),
            },
        )


def get_database_client(
    role: DatabaseRole = DatabaseRole.CORE,
) -> DatabaseClientWrapper:
    if role not in _database_clients:
        _database_clients[role] = DatabaseClientWrapper(role)
    return _database_clients[role]


def get_engine(role: DatabaseRole = DatabaseRole.CORE) -> Engine:
    return get_database_client(role).engine


def get_session_factory(role: DatabaseRole = DatabaseRole.CORE) -> sessionmaker[Session]:
    return get_database_client(role).session_factory


def get_core_db_session() -> Generator[Session, None, None]:
    with get_database_client(DatabaseRole.CORE).session() as session:
        yield session
