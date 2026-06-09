from __future__ import annotations

"""机器人上下文容器模块。

定义 BotContext 依赖注入容器，为各处理器模块提供统一的状态和服务访问接口，
包括 WebSocket 客户端、配置、绑定信息、消息记录、事件日志等。
"""

from pathlib import Path
from typing import Any, Callable


class BotContext:
    """机器人上下文依赖注入容器。

    通过回调函数封装对主机器人实例状态和服务的访问，使各处理器模块
    无需直接依赖主类即可完成消息发送、配置读取、绑定状态更新等操作。
    所有属性均通过 property 暴露，确保访问时始终获取最新状态。
    """
    def __init__(
        self,
        *,
        database_path: Path,
        project_root: Path,
        bot_key: str,
        logger: Any,
        bot_message_logger: Any,
        get_client: Callable[[], Any],
        get_settings: Callable[[], Any],
        get_bound_chat_id: Callable[[], str],
        get_bound_user_id: Callable[[], str],
        get_bound_chat_name: Callable[[], str],
        get_keepalive: Callable[[], Any],
        get_frame_store: Callable[[], Any],
        get_agent_service: Callable[[], Any],
        set_bound_chat_id: Callable[[str], None],
        set_bound_user_id: Callable[[str], None],
        set_bound_chat_name: Callable[[str], None],
        log_event: Callable[..., None],
        record_bot_message: Callable[..., None],
        record_user_message: Callable[..., str],
        send_ai_reply_message: Callable[..., Any],
        format_local_time: Callable[[str], str],
        handle_conversation_send_failure: Callable[..., None],
        refresh_runtime_settings: Callable[[], None],
        frame_req_id: Callable[..., str],
        send_media_asset: Callable[..., Any],
        is_size_limit_exceeded: Callable[[str, int], bool],
        send_message_with_retry: Callable[..., Any],
    ) -> None:
        self.database_path = database_path
        self.project_root = project_root
        self.bot_key = bot_key
        self.logger = logger
        self.bot_message_logger = bot_message_logger
        self._get_client = get_client
        self._get_settings = get_settings
        self._get_bound_chat_id = get_bound_chat_id
        self._get_bound_user_id = get_bound_user_id
        self._get_bound_chat_name = get_bound_chat_name
        self._get_keepalive = get_keepalive
        self._get_frame_store = get_frame_store
        self._get_agent_service = get_agent_service
        self._set_bound_chat_id = set_bound_chat_id
        self._set_bound_user_id = set_bound_user_id
        self._set_bound_chat_name = set_bound_chat_name
        self._log_event = log_event
        self._record_bot_message = record_bot_message
        self._record_user_message = record_user_message
        self._send_ai_reply_message = send_ai_reply_message
        self._format_local_time = format_local_time
        self._handle_conversation_send_failure = handle_conversation_send_failure
        self._refresh_runtime_settings = refresh_runtime_settings
        self._frame_req_id = frame_req_id
        self._send_media_asset = send_media_asset
        self._is_size_limit_exceeded = is_size_limit_exceeded
        self._send_message_with_retry = send_message_with_retry

    @property
    def client(self) -> Any:
        return self._get_client()

    @property
    def settings(self) -> Any:
        return self._get_settings()

    @property
    def bound_chat_id(self) -> str:
        return self._get_bound_chat_id()

    @bound_chat_id.setter
    def bound_chat_id(self, value: str) -> None:
        self._set_bound_chat_id(value)

    @property
    def bound_user_id(self) -> str:
        return self._get_bound_user_id()

    @bound_user_id.setter
    def bound_user_id(self, value: str) -> None:
        self._set_bound_user_id(value)

    @property
    def bound_chat_name(self) -> str:
        return self._get_bound_chat_name()

    @bound_chat_name.setter
    def bound_chat_name(self, value: str) -> None:
        self._set_bound_chat_name(value)

    @property
    def keepalive(self) -> Any:
        return self._get_keepalive()

    @property
    def frame_store(self) -> Any:
        return self._get_frame_store()

    @property
    def agent_service(self) -> Any:
        return self._get_agent_service()

    def log_event(self, **kwargs: Any) -> None:
        self._log_event(**kwargs)

    def record_bot_message(self, **kwargs: Any) -> None:
        self._record_bot_message(**kwargs)

    def record_user_message(self, **kwargs: Any) -> str:
        return self._record_user_message(**kwargs)

    async def send_ai_reply_message(self, **kwargs: Any) -> Any:
        return await self._send_ai_reply_message(**kwargs)

    def format_local_time(self, created_at: str) -> str:
        return self._format_local_time(created_at)

    def handle_conversation_send_failure(self, **kwargs: Any) -> None:
        self._handle_conversation_send_failure(**kwargs)

    def refresh_runtime_settings(self) -> None:
        self._refresh_runtime_settings()

    def frame_req_id(self, **kwargs: Any) -> str:
        return self._frame_req_id(**kwargs)

    async def send_media_asset(self, **kwargs: Any) -> Any:
        return await self._send_media_asset(**kwargs)

    def is_size_limit_exceeded(self, media_type: str, size: int) -> bool:
        return self._is_size_limit_exceeded(media_type, size)

    async def send_message_with_retry(self, **kwargs: Any) -> None:
        await self._send_message_with_retry(**kwargs)
