"""backend-agent 应用配置。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from nacos_client import NacosClient
from nacos_client import adapter as nacos_adapter
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _adapt_nacos_fields() -> None:
    """把 Nacos 拍平字段适配为 Agent Settings 字段。"""
    nacos_adapter.copy_overwrite("AGENT_PORT", "APP_PORT")
    nacos_adapter.copy_overwrite("DATA_BASE_URL", "BACKEND_DATA_BASE_URL")


def _load_nacos_config_to_environ() -> None:
    """从强制可用的 Nacos 配置中心加载服务配置。"""
    client = NacosClient.from_env_required()
    client.load_to_environ()
    _adapt_nacos_fields()


class Settings(BaseSettings):
    """Agent 服务配置模型。"""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Digital Employee Agent"
    app_version: str = "0.1.0"
    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8030
    api_prefix: str = "/api/v1"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    dependency_timeout_seconds: float = Field(default=3.0, gt=0)
    shutdown_grace_seconds: float = Field(default=10.0, gt=0)
    backend_data_base_url: str = "http://127.0.0.1:8010"
    data_api_key: str = Field(default="", repr=False)

    @property
    def docs_enabled(self) -> bool:
        """返回是否开放 Swagger 和 ReDoc。"""
        return self.app_env != "production"


@lru_cache
def get_settings() -> Settings:
    """加载并缓存 Agent 服务配置。"""
    _load_nacos_config_to_environ()
    return Settings()


settings = get_settings()
