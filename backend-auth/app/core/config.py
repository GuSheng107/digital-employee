"""backend-auth 应用配置。

认证服务不持有 PostgreSQL、Redis、MinIO 或 MQ 连接配置；它仅配置自身
HTTP 服务以及通过 backend-share 调用 backend-data 所需的服务地址。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    backend_data_base_url: str = "http://127.0.0.1:8010"
    backend_data_api_key: str = Field(default="", repr=False)
    # 服务间内部令牌：CRUD 落库后触发 Gateway /api/v1/admin/reload。
    # 与 backend-gateway 的 INTERNAL_ADMIN_TOKEN 保持一致；留空时 reload 会被 Gateway 拒绝。
    internal_admin_token: str = Field(default="", repr=False)
    gateway_base_url: str = "http://127.0.0.1:8864"
    phone_default_region: str = "CN"
    login_ip_rate_limit: int = 30
    login_ip_rate_window_seconds: int = 60
    login_pair_rate_limit: int = 5
    login_pair_rate_window_seconds: int = 300
    login_account_rate_limit: int = 10
    login_account_rate_window_seconds: int = 900
    register_ip_rate_limit: int = 5
    register_ip_rate_window_seconds: int = 900
    register_identity_rate_limit: int = 3
    register_identity_rate_window_seconds: int = 3600
    captcha_ip_rate_limit: int = 30
    captcha_ip_rate_window_seconds: int = 60
    trusted_proxy_networks: str = "127.0.0.1/32,::1/128"

    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS 允许来源列表。"""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def trusted_proxy_networks_list(self) -> list[str]:
        """返回允许提供 X-Forwarded-For 的代理 IP 或 CIDR。"""
        return [
            network.strip()
            for network in self.trusted_proxy_networks.split(",")
            if network.strip()
        ]

    @property
    def docs_enabled(self) -> bool:
        """是否对外暴露 Swagger / ReDoc 文档站点。

        生产环境关闭以减少攻击面，其余环境默认开启便于联调。
        """
        return self.app_env != "production"

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
