from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Digital Employee Data Platform"
    app_version: str = "0.1.0"
    app_env: str = "local"
    app_host: str = "127.0.0.1"
    app_port: int = 8010
    api_prefix: str = "/api/v1"
    dependency_timeout_seconds: int = 3

    core_db_host: str = "127.0.0.1"
    core_db_port: int = 5432
    core_db_name: str = "digital_employee_core"
    core_db_user: str = "digital_employee_app"
    core_db_password: str = Field(default="", repr=False)
    core_db_sslmode: str = "disable"

    vector_db_host: str = "127.0.0.1"
    vector_db_port: int = 5432
    vector_db_name: str = "digital_employee_vector"
    vector_db_user: str = "digital_employee_app"
    vector_db_password: str = Field(default="", repr=False)
    vector_db_sslmode: str = "disable"

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = Field(default="", repr=False)
    redis_ssl: bool = False

    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = Field(default="", repr=False)
    minio_secret_key: str = Field(default="", repr=False)
    minio_secure: bool = False
    minio_default_bucket: str = Field(
        default="digital-employee",
        validation_alias=AliasChoices("MINIO_DEFAULT_BUCKET", "MINIO_BUCKET_NAME"),
    )

    cors_origins: str = "http://127.0.0.1:5174,http://localhost:5174"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @staticmethod
    def _postgres_url(
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        sslmode: str,
        connect_timeout: int,
    ) -> str:
        return URL.create(
            drivername="postgresql+psycopg2",
            username=user,
            password=password,
            host=host,
            port=port,
            database=database,
            query={"sslmode": sslmode, "connect_timeout": str(connect_timeout)},
        ).render_as_string(hide_password=False)

    @property
    def core_database_url(self) -> str:
        return self._postgres_url(
            self.core_db_host,
            self.core_db_port,
            self.core_db_name,
            self.core_db_user,
            self.core_db_password,
            self.core_db_sslmode,
            self.dependency_timeout_seconds,
        )

    @property
    def vector_database_url(self) -> str:
        return self._postgres_url(
            self.vector_db_host,
            self.vector_db_port,
            self.vector_db_name,
            self.vector_db_user,
            self.vector_db_password,
            self.vector_db_sslmode,
            self.dependency_timeout_seconds,
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        scheme = "rediss" if self.redis_ssl else "redis"
        return f"{scheme}://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    def public_config(self) -> dict:
        return {
            "app": {
                "name": self.app_name,
                "version": self.app_version,
                "env": self.app_env,
                "host": self.app_host,
                "port": self.app_port,
                "api_prefix": self.api_prefix,
            },
            "core_db": {
                "host": self.core_db_host,
                "port": self.core_db_port,
                "database": self.core_db_name,
                "user": self.core_db_user,
                "sslmode": self.core_db_sslmode,
            },
            "vector_db": {
                "host": self.vector_db_host,
                "port": self.vector_db_port,
                "database": self.vector_db_name,
                "user": self.vector_db_user,
                "sslmode": self.vector_db_sslmode,
            },
            "redis": {
                "host": self.redis_host,
                "port": self.redis_port,
                "db": self.redis_db,
                "ssl": self.redis_ssl,
            },
            "minio": {
                "endpoint": self.minio_endpoint,
                "secure": self.minio_secure,
                "default_bucket": self.minio_default_bucket,
            },
            "cors_origins": self.cors_origins_list,
        }


ConnectionTarget = Literal["all", "postgres", "core_db", "vector_db", "redis", "minio"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
