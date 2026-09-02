"""Agent 配置测试。"""

from __future__ import annotations

from app.core.config import Settings, _adapt_nacos_fields


def test_settings_defaults_use_agent_port() -> None:
    """默认配置应使用 Agent 独立端口。"""
    configured = Settings(_env_file=None)
    assert configured.app_port == 8030
    assert configured.app_name == "Digital Employee Agent"
    assert configured.log_level == "INFO"


def test_settings_hide_data_api_key_from_repr() -> None:
    """配置对象的 repr 不应暴露服务密钥。"""
    configured = Settings(_env_file=None, data_api_key="sensitive-value")
    assert "sensitive-value" not in repr(configured)


def test_adapt_nacos_fields_overwrites_target(monkeypatch) -> None:
    """Nacos Agent 端口应覆盖通用应用端口。"""
    monkeypatch.setenv("AGENT_PORT", "18030")
    monkeypatch.setenv("APP_PORT", "8030")
    _adapt_nacos_fields()
    assert Settings(_env_file=None).app_port == 18030


def test_docs_disabled_in_production() -> None:
    """生产环境不应开放接口文档。"""
    configured = Settings(_env_file=None, app_env="production")
    assert configured.docs_enabled is False
