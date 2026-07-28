"""应用配置层。

启动时优先从 Nacos 配置中心拉取共享基础设施连接信息（DB/Redis），
Nacos 不可达时静默降级到本地 .env。所有敏感凭证只从环境变量读取，
不入库不入 Nacos，避免循环依赖。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _load_nacos_config_to_environ() -> None:
    """启动时从 Nacos 拉取配置并注入 os.environ。

    优先级高于本地 .env 文件，使 pydantic-settings 自动读到 Nacos 配置。
    失败时静默降级（缺凭证/包未安装/网络异常都仅打日志），不阻塞启动。
    """
    try:
        from nacos_client import NacosClient
    except ImportError:
        return  # nacos-client 未安装，仅本地开发场景

    client = NacosClient.from_env_optional()
    if client is not None:
        client.load_to_environ()
        _adapt_nacos_to_backend_auth_env()


def _adapt_nacos_to_backend_auth_env() -> None:
    """把 Nacos 拍平的 key 适配到 backend-auth Settings 期望的字段名。

    Nacos prod.yaml 用嵌套结构（postgres.host / redis.host 等），
    NacosClient.load_to_environ 拍平后注入 POSTGRES_HOST / REDIS_HOST 等。
    backend-auth Settings 字段命名为 CORE_DB_HOST 等，需要这层适配转换。

    Nacos 优先级高于本地 .env：src 存在时覆盖 dst，确保 Nacos 配置生效。
    """
    from nacos_client import adapter as nacos_adapter

    # Postgres -> core_db_*
    nacos_adapter.copy_overwrite("POSTGRES_HOST", "CORE_DB_HOST")
    nacos_adapter.copy_overwrite("POSTGRES_PORT", "CORE_DB_PORT")
    nacos_adapter.copy_overwrite("POSTGRES_USERNAME", "CORE_DB_USER")
    nacos_adapter.copy_overwrite("POSTGRES_PASSWORD", "CORE_DB_PASSWORD")
    nacos_adapter.copy_overwrite("POSTGRES_DATABASE", "CORE_DB_NAME")
    nacos_adapter.copy_overwrite("POSTGRES_CORE_DATABASE", "CORE_DB_NAME")
    # Redis 字段名已匹配（REDIS_HOST/REDIS_PORT/REDIS_PASSWORD），无需转换


class Settings(BaseSettings):
    """应用配置模型，从环境变量与 .env 文件加载。"""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Digital Employee Auth"
    app_version: str = "0.1.0"
    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8020
    api_prefix: str = "/api/v1"
    dependency_timeout_seconds: int = 3
    api_key: str = Field(default="", repr=False)

    # 双 token 配置
    access_token_ttl_seconds: int = 1800
    refresh_token_ttl_seconds: int = 604800
    token_redis_prefix: str = "auth"

    # PostgreSQL（共用 db_data 库）
    core_db_host: str = "127.0.0.1"
    core_db_port: int = 5432
    core_db_name: str = "db_data"
    core_db_user: str = "app_usr"
    core_db_password: str = Field(default="", repr=False)
    core_db_sslmode: str = "disable"

    # Redis
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_username: str = ""
    redis_password: str = Field(default="", repr=False)
    redis_ssl: bool = False

    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS 允许来源列表。"""
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def docs_enabled(self) -> bool:
        """是否对外暴露 Swagger / ReDoc 文档站点。

        生产环境关闭以减少攻击面，其余环境默认开启便于联调。
        """
        return self.app_env != "production"

    @property
    def core_database_url(self) -> str:
        """PostgreSQL 连接 URL（含连接超时与 SSL 模式查询参数）。"""
        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.core_db_user,
            password=self.core_db_password,
            host=self.core_db_host,
            port=self.core_db_port,
            database=self.core_db_name,
            query={
                "sslmode": self.core_db_sslmode,
                "connect_timeout": str(self.dependency_timeout_seconds),
            },
        ).render_as_string(hide_password=False)

    @property
    def redis_url(self) -> str:
        """Redis 连接 URL，支持 ACL username 与含特殊字符的密码。

        密码中的 ``@`` 等特殊字符会做 URL 编码，避免解析错位。
        """
        scheme = "rediss" if self.redis_ssl else "redis"
        if self.redis_username and self.redis_password:
            auth = (
                f"{quote(self.redis_username, safe='')}:"
                f"{quote(self.redis_password, safe='')}@"
            )
        elif self.redis_password:
            auth = f":{quote(self.redis_password, safe='')}@"
        else:
            auth = ""
        return f"{scheme}://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    def public_config(self) -> dict:
        """返回可供前端展示的非敏感系统配置。

        仅暴露静态的、面向排障与展示的元信息，剔除主机、端口、用户等
        可能泄漏部署拓扑的字段。
        """
        return {
            "app": {
                "name": self.app_name,
                "version": self.app_version,
                "env": self.app_env,
                "api_prefix": self.api_prefix,
            },
            "core_db": {
                "database": self.core_db_name,
                "sslmode": self.core_db_sslmode,
            },
            "redis": {
                "db": self.redis_db,
                "ssl": self.redis_ssl,
            },
            "cors_origins": self.cors_origins_list,
        }


ConnectionTarget = Literal["all", "postgres", "core_db", "redis"]


@lru_cache
def get_settings() -> Settings:
    """加载并缓存 Settings 实例。

    首次调用时触发 Nacos 配置拉取并适配字段名，之后通过 lru_cache 复用。
    """
    _load_nacos_config_to_environ()
    return Settings()


settings = get_settings()
