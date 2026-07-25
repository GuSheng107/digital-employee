from collections.abc import Generator
from contextlib import contextmanager
from enum import Enum

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class DatabaseRole(str, Enum):
    CORE = "core"
    VECTOR = "vector"
    DDL = "ddl"


class Base(DeclarativeBase):
    pass


class DatabaseClientWrapper:
    """Centralized SQLAlchemy wrapper for one PostgreSQL database role."""

    def __init__(self, role: DatabaseRole) -> None:
        self.role = role
        if role == DatabaseRole.CORE:
            self.database_url = settings.core_database_url
        elif role == DatabaseRole.VECTOR:
            self.database_url = settings.vector_database_url
        else:
            if not settings.ddl_database_url:
                raise RuntimeError("DDL_DATABASE_URL is not configured.")
            self.database_url = settings.ddl_database_url
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

    def create_all(self) -> None:
        Base.metadata.create_all(bind=self.engine)


_database_clients: dict[DatabaseRole, DatabaseClientWrapper] = {}


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


def init_core_schema() -> None:
    from app.models import data_item  # noqa: F401

    get_database_client(DatabaseRole.CORE).create_all()
