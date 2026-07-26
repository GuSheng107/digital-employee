# -*- coding: utf-8 -*-
"""数据模型定义。

使用 Pydantic v2 定义 Bot 配置、API 请求和响应等数据结构。
"""

from enum import Enum
from pydantic import BaseModel, Field


class BotConfig(BaseModel):
    """单个 Bot 实例的配置模型。"""

    bot_id: str = Field(..., description="Bot 实例唯一标识")
    platform: str = Field(default="feishu", description="平台类型")
    app_id: str = Field(..., description="飞书应用 APP_ID 或企业微信机器人 BOTID")
    app_secret: str = Field(..., description="飞书应用 APP_SECRET 或企业微信机器人 Secret")
    mode: str = Field(default="test", description="运行模式：test（内存模拟）或 prod（MQ生产投递）")


class BotConfigFile(BaseModel):
    """bot.json 配置文件顶层结构。"""

    bots: list[BotConfig] = Field(default_factory=list, description="Bot 配置列表")


class BotConfigRequest(BaseModel):
    """通过 Admin API 动态注入的 Bot 配置请求体。"""

    bot_id: str = Field(..., description="Bot 实例唯一标识")
    platform: str = Field(default="feishu", description="平台类型")
    app_id: str = Field(..., description="飞书应用 APP_ID 或企业微信机器人 BOTID")
    app_secret: str = Field(..., description="飞书应用 APP_SECRET 或企业微信机器人 Secret")
    mode: str = Field(default="test", description="运行模式：test（内存模拟）或 prod（MQ生产投递）")


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

class MessageType(str, Enum):
    """归一化的消息类型枚举。"""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    CARD = "card"
    INTERACTIVE = "interactive"

    def __str__(self) -> str:
        return self.value


class CardOptionItem(BaseModel):
    """卡片选项单元模型（平台无关）。"""

    key: str | None = Field(default=None, description="选项标识（若空则适配器自动按索引分配 A, B, C...）")
    label: str = Field(..., description="选项展示文案")
    value: str | None = Field(default=None, description="回传数值（若为空则使用 label）")


class CardInputConfig(BaseModel):
    """卡片自填输入框配置（平台无关）。"""

    name: str = Field(default="custom_option_d", description="输入框字段名")
    placeholder: str = Field(default="D 选项：自定义输入选项内容", description="输入框占位文案")


class QuestionCardData(BaseModel):
    """全局公共题目/问卷卡片数据模型（与各 IM 平台解耦）。"""

    card_id: str | None = Field(default=None, description="卡片模板 ID 或唯一标识")
    title: str = Field(..., description="卡片标题")
    description: str | None = Field(default=None, description="题目正文或详细描述")
    options: list[str | CardOptionItem] = Field(
        default_factory=list, description="选项列表（支持纯字符串列表或 CardOptionItem）"
    )
    custom_input: CardInputConfig | None = Field(default=None, description="自填输入框配置（可选）")
    submit_text: str = Field(default="提交选择", description="提交按钮文本")


class MessageContent(BaseModel):
    """多模态消息的内容区块定义。"""

    msg_type: MessageType = Field(default=MessageType.TEXT, description="消息类型")
    text: str | None = Field(default=None, description="文本内容")
    file_url: str | None = Field(default=None, description="已转存至本地 MinIO 的统一对象 URL")
    file_name: str | None = Field(default=None, description="文件原始名称（可选）")
    card_json: str | dict | None = Field(default=None, description="交互卡片 JSON 结构或对象（平台特定备用）")
    card_data: QuestionCardData | dict | None = Field(default=None, description="解耦的全局公共卡片数据模型")

class StandardMessage(BaseModel):
    """全局统一的归一化消息体模型。"""

    message_id: str | None = Field(default=None, description="原始消息 ID（回复时关联，发新消息时为空）")
    platform: str = Field(..., description="底层 IM 平台类型，如 feishu")
    bot_id: str = Field(..., description="关联的机器人实例唯一 ID")
    chat_type: str = Field(..., description="会话场景，如 p2p（单聊）或 group（群聊）")
    session_id: str = Field(..., description="发送的目标会话 ID（单聊为对方 open_id，群聊为群聊 ID）")
    sender_id: str | None = Field(default=None, description="发送方用户唯一 ID（可选）")
    content: list[MessageContent] = Field(default_factory=list, description="多模态消息内容区块列表")

