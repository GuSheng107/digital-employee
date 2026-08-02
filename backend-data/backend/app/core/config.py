from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from dotenv import load_dotenv
from nacos_client import adapter as nacos_adapter
from pydantic import AliasChoices, Field
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

    client = NacosClient.from_env_required()
    client.load_to_environ()
    _adapt_nacos_to_backend_data_env()


def _adapt_nacos_to_backend_data_env() -> None:
    """把 Nacos 拍平的 key 适配到 backend-data Settings 期望的字段名。

    Nacos dev.yaml 用嵌套结构（postgres.host / minio.host 等），
    NacosClient.load_to_environ 拍平后注入 POSTGRES_HOST / MINIO_HOST 等。
    backend-data Settings 字段命名为 CORE_DB_HOST / MINIO_ENDPOINT 等，
    需要这层适配转换。

    Nacos 优先级高于本地 .env：src 存在时覆盖 dst，确保 Nacos 配置生效。
    本地调试时设 NACOS_SERVER_ADDR 为空可跳过 Nacos 拉取，回退到 .env。
    """
    # Postgres -> core_db_*
    nacos_adapter.copy_overwrite("POSTGRES_HOST", "CORE_DB_HOST")
    nacos_adapter.copy_overwrite("POSTGRES_PORT", "CORE_DB_PORT")
    nacos_adapter.copy_overwrite("POSTGRES_USERNAME", "CORE_DB_USER")
    nacos_adapter.copy_overwrite("POSTGRES_PASSWORD", "CORE_DB_PASSWORD")
    # 库名: 优先 core_database,兜底 database(dev.yaml 单库场景)
    nacos_adapter.copy_overwrite("POSTGRES_DATABASE", "CORE_DB_NAME")
    nacos_adapter.copy_overwrite("POSTGRES_CORE_DATABASE", "CORE_DB_NAME")
    # Postgres -> vector_db_*
    nacos_adapter.copy_overwrite("POSTGRES_HOST", "VECTOR_DB_HOST")
    nacos_adapter.copy_overwrite("POSTGRES_PORT", "VECTOR_DB_PORT")
    nacos_adapter.copy_overwrite("POSTGRES_USERNAME", "VECTOR_DB_USER")
    nacos_adapter.copy_overwrite("POSTGRES_PASSWORD", "VECTOR_DB_PASSWORD")
    # 库名: 优先 vector_database,兜底 database(dev.yaml 单库场景)
    nacos_adapter.copy_overwrite("POSTGRES_DATABASE", "VECTOR_DB_NAME")
    nacos_adapter.copy_overwrite("POSTGRES_VECTOR_DATABASE", "VECTOR_DB_NAME")
    # MinIO: host + api_port -> endpoint
    nacos_adapter.compose_endpoint("MINIO_HOST", "MINIO_API_PORT", "MINIO_ENDPOINT")
    nacos_adapter.copy_overwrite("MINIO_USERNAME", "MINIO_ACCESS_KEY")
    nacos_adapter.copy_overwrite("MINIO_PASSWORD", "MINIO_SECRET_KEY")
    # Redis 已匹配（REDIS_HOST/REDIS_PORT/REDIS_PASSWORD），无需转换
    # RabbitMQ 仅由 backend-data 持有连接与拓扑配置。
    nacos_adapter.compose_rabbitmq_url()
    # API Key: Nacos 的 data.api_key -> DATA_API_KEY -> API_KEY（服务端校验）
    # 同时复用为 APP_SECRET_KEY（crypto 加密口令），仅后端间传递，不暴露到前端
    nacos_adapter.copy_overwrite("DATA_API_KEY", "API_KEY")
    nacos_adapter.copy_overwrite("DATA_API_KEY", "APP_SECRET_KEY")
    # Ports: Nacos 的 data.port -> DATA_PORT -> APP_PORT
    nacos_adapter.copy_overwrite("DATA_PORT", "APP_PORT")
    # RabbitMQ 拓扑名称：Nacos 拍平的 RABBITMQ_EXCHANGE / INBOUND_QUEUE / OUTBOUND_QUEUE
    # / ROUTING_KEY / DLX / DLQ 等字段名与 settings 完全一致，无需适配转换。


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
    backend_auth_base_url: str = "http://127.0.0.1:8020"
    # 用于保护内部端点的 API Key；为空时按 fail-closed 拒绝服务间访问。
    api_key: str = Field(default="", repr=False)

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
    redis_username: str = ""
    redis_password: str = Field(default="", repr=False)
    redis_ssl: bool = False
    redis_watch_max_retries: int = Field(default=20, ge=1, le=100)
    token_redis_prefix: str = "auth"
    access_token_ttl_seconds: int = 1800
    refresh_token_ttl_seconds: int = 604800
    password_change_redis_prefix: str = "auth:password-change-required"
    captcha_redis_prefix: str = "auth:captcha"
    captcha_ttl_seconds: int = 120
    invite_code_redis_prefix: str = "invite_code"
    invite_code_default_ttl_seconds: int = 604800
    message_relay_redis_prefix: str = "message-relay"
    message_relay_ttl_seconds: int = 604800
    message_lease_seconds: int = 60
    message_max_delivery_attempts: int = 5
    message_dead_letter_limit: int = 1000

    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = Field(default="", repr=False)
    minio_secret_key: str = Field(default="", repr=False)
    minio_secure: bool = False
    minio_default_bucket: str = Field(
        default="digital-employee",
        validation_alias=AliasChoices("MINIO_DEFAULT_BUCKET", "MINIO_BUCKET_NAME"),
    )
    storage_object_max_size_bytes: int = 20 * 1024 * 1024

    rabbitmq_url: str = Field(
        default="amqp://guest:guest@127.0.0.1:5672/",
        repr=False,
    )
    # Topic 交换机名称（backend-data 统一声明，share 包幂等获取引用）
    rabbitmq_exchange: str = "digital_employee.events"
    # 上行（终端 -> 系统）入站消息队列
    rabbitmq_inbound_queue: str = "inbound_queue"
    # 下行（系统 -> 终端）出站消息队列
    rabbitmq_outbound_queue: str = "outbound_queue"
    # 入站消息路由键
    rabbitmq_inbound_routing_key: str = "inbound.message"
    # 出站消息路由键
    rabbitmq_outbound_routing_key: str = "outbound.message"
    # 死信交换机名称（Direct 类型）
    rabbitmq_dlx: str = "digital_employee.dlx"
    # 死信队列名称
    rabbitmq_dlq: str = "outbound_dlq"
    # 消费者预取计数
    rabbitmq_prefetch_count: int = 20

    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @property
    def docs_enabled(self) -> bool:
        """是否对外暴露 Swagger / ReDoc 文档站点。

        生产环境关闭以减少攻击面，其余环境默认开启便于联调。
        """
        return self.app_env != "production"

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
        """Redis 连接 URL，支持 ACL username 与含特殊字符的密码。

        密码中的 ``@`` 等特殊字符会做 URL 编码，避免解析错位。
        """
        scheme = "rediss" if self.redis_ssl else "redis"
        if self.redis_username and self.redis_password:
            auth = f"{quote(self.redis_username, safe='')}:{quote(self.redis_password, safe='')}@"
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
            "vector_db": {
                "database": self.vector_db_name,
                "sslmode": self.vector_db_sslmode,
            },
            "redis": {
                "db": self.redis_db,
                "ssl": self.redis_ssl,
            },
            "minio": {
                "secure": self.minio_secure,
                "default_bucket": self.minio_default_bucket,
            },
            "cors_origins": self.cors_origins_list,
        }


ConnectionTarget = Literal["all", "postgres", "core_db", "vector_db", "redis", "minio"]


@lru_cache
def get_settings() -> Settings:
    _load_nacos_config_to_environ()
    return Settings()


settings = get_settings()
