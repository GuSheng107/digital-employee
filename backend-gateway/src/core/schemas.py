# -*- coding: utf-8 -*-
"""数据模型定义。

使用 Pydantic v2 定义 Bot 配置、API 请求和响应等数据结构。
"""

from pydantic import BaseModel, Field


class BotConfig(BaseModel):
    """单个 Bot 实例的配置模型。"""

    bot_id: str = Field(..., description="Bot 实例唯一标识")
    platform: str = Field(default="feishu", description="平台类型")
    app_id: str = Field(..., description="飞书应用 APP_ID")
    app_secret: str = Field(..., description="飞书应用 APP_SECRET")


class BotConfigFile(BaseModel):
    """bot.json 配置文件顶层结构。"""

    bots: list[BotConfig] = Field(default_factory=list, description="Bot 配置列表")


class BotConfigRequest(BaseModel):
    """通过 Admin API 动态注入的 Bot 配置请求体。"""

    bot_id: str = Field(..., description="Bot 实例唯一标识")
    platform: str = Field(default="feishu", description="平台类型")
    app_id: str = Field(..., description="飞书应用 APP_ID")
    app_secret: str = Field(..., description="飞书应用 APP_SECRET")


class BotStatusResponse(BaseModel):
    """Bot 运行状态响应模型。"""

    bot_id: str
    platform: str
    is_running: bool = Field(default=False, description="Bot 是否正在运行")
    thread_id: int | None = Field(default=None, description="线程 ID")
    uptime_seconds: float | None = Field(default=None, description="运行时长（秒）")
    last_error: str | None = Field(default=None, description="最近一次异常信息")


class HealthResponse(BaseModel):
    """健康检查响应模型。"""

    status: str = Field(default="ok", description="服务状态")
    active_bots: int = Field(default=0, description="活跃 Bot 数量")
    bots: list[BotStatusResponse] = Field(default_factory=list, description="各 Bot 状态详情")
