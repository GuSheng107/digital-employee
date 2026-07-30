"""企业微信智能机器人长连接模块。

导出 WeChatBot 机器人实例类与 WeChatAdapter 消息适配器类。
"""

from src.platforms.wechat.adapter import WeChatAdapter
from src.platforms.wechat.bot import WeChatBot

__all__ = ["WeChatBot", "WeChatAdapter"]
