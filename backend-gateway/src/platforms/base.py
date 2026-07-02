# -*- coding: utf-8 -*-
"""平台适配器抽象基类定义。

为多平台扩展（如企业微信、钉钉等）预留标准化的接口契约。
"""

import abc
from typing import Any
from src.core.schemas import StandardMessage


class BaseAdapter(abc.ABC):
    """适配器抽象基类。

    所有特定平台（如飞书）的适配器实现类必须继承此类，负责平台格式与中枢协议的翻译。
    """

    @abc.abstractmethod
    def handle_receive(self, data: Any) -> None:
        """接收特定平台推送的原始事件，转换为 StandardMessage 并投递至中枢入站层。

        Args:
            data: 平台推送的原始事件对象。
        """
        pass

    @abc.abstractmethod
    def send_message(self, msg: StandardMessage) -> None:
        """将归一化标准出站消息转换为平台特有请求，并调用接口发送。

        Args:
            msg: 出站的标准归一化消息体。
        """
        pass
