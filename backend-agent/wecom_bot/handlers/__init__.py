from __future__ import annotations

"""企微机器人事件处理器包。

提供消息处理、管理员绑定、媒体转发和手动回复等核心处理器模块，
通过 BotContext 依赖注入容器实现与主机器人实例的解耦。
"""

from wecom_bot.handlers.binding_manager import BindingManager
from wecom_bot.handlers.context import BotContext
from wecom_bot.handlers.manual_reply_handler import ManualReplyHandler
from wecom_bot.handlers.media_handler import MediaHandler

__all__ = ["MediaHandler", "BindingManager", "ManualReplyHandler", "BotContext"]
