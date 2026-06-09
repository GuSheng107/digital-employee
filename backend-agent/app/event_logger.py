from __future__ import annotations

"""结构化运行时事件日志模块。

实现运行时事件的分类、级别管理和持久化记录，支持 AI 任务、网络、
系统、媒体、消息等各类事件的日志记录，以及 AI 工作项状态更新和取消检测。
"""

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from app.db.ai_work_store import is_ai_work_cancel_requested, update_ai_work_item
from app.db.log_store import insert_project_log


class EventLevel(str, Enum):
    """事件级别枚举，定义 INFO、WARNING、ERROR 三个级别。"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class EventCategory(str, Enum):
    """事件分类枚举，定义 AI、系统、Bot、媒体、网络、消息、任务、数据等类别。"""
    AI = "ai"
    SYSTEM = "system"
    BOT = "bot"
    MEDIA = "media"
    NETWORK = "network"
    MESSAGE = "message"
    TASK = "task"
    DATA = "data"


@dataclass
class RuntimeEvent:
    """运行时事件数据类，包含追踪 ID、来源、消息、详情、级别和分类。"""
    trace_id: str
    source: str
    message: str
    detail: str = ""
    level: EventLevel = EventLevel.INFO
    category: EventCategory = EventCategory.SYSTEM


class EventLogger:
    """结构化事件日志记录器，将运行时事件持久化到数据库并支持多种便捷的事件记录方法。

    提供 AI 任务、媒体、网络、消息、系统、手动回复等各类事件的快捷记录方法，
    以及 AI 工作项状态更新和取消检测功能。
    """

    def __init__(self, database_path: Path, *, logger: logging.Logger | None = None) -> None:
        self._database_path = database_path
        self._logger = logger

    def emit(self, event: RuntimeEvent, *, raise_on_error: bool = False) -> str:
        try:
            return insert_project_log(
                self._database_path,
                level=event.level.value,
                category=event.category.value,
                source=event.source,
                message=event.message,
                detail=event.detail,
                trace_id=event.trace_id,
            )
        except Exception as exc:
            if self._logger:
                self._logger.exception(
                    "Failed to persist runtime event log.",
                    extra={"trace_id": event.trace_id, "category": "system"},
                )
            if raise_on_error:
                raise
            return ""

    def log_event(
        self,
        *,
        trace_id: str,
        source: str,
        category: str,
        message: str,
        detail: str = "",
        level: str = "INFO",
    ) -> str:
        try:
            event_level = EventLevel(level)
        except ValueError:
            event_level = EventLevel.INFO
        try:
            event_category = EventCategory(category)
        except ValueError:
            event_category = EventCategory.SYSTEM
        return self.emit(RuntimeEvent(
            trace_id=trace_id,
            source=source,
            message=message,
            detail=detail,
            level=event_level,
            category=event_category,
        ))

    def ai_started(self, *, trace_id: str, source: str = "ai_task", detail: str = "") -> str:
        return self.emit(RuntimeEvent(
            trace_id=trace_id,
            source=source,
            message="AI task started",
            detail=detail,
            level=EventLevel.INFO,
            category=EventCategory.AI,
        ))

    def ai_completed(self, *, trace_id: str, source: str = "ai_task", detail: str = "") -> str:
        return self.emit(RuntimeEvent(
            trace_id=trace_id,
            source=source,
            message="AI task completed",
            detail=detail,
            level=EventLevel.INFO,
            category=EventCategory.AI,
        ))

    def ai_cancelled(self, *, trace_id: str, source: str = "ai_task", detail: str = "") -> str:
        return self.emit(RuntimeEvent(
            trace_id=trace_id,
            source=source,
            message="AI task cancelled",
            detail=detail,
            level=EventLevel.INFO,
            category=EventCategory.AI,
        ))

    def ai_failed(self, *, trace_id: str, source: str = "ai_task", detail: str = "") -> str:
        return self.emit(RuntimeEvent(
            trace_id=trace_id,
            source=source,
            message="AI task failed",
            detail=detail,
            level=EventLevel.ERROR,
            category=EventCategory.AI,
        ))

    def media_event(self, *, trace_id: str, message: str, detail: str = "", level: EventLevel = EventLevel.INFO) -> str:
        return self.emit(RuntimeEvent(
            trace_id=trace_id,
            source="media",
            message=message,
            detail=detail,
            level=level,
            category=EventCategory.MEDIA,
        ))

    def binding_event(self, *, trace_id: str, message: str, detail: str = "", level: EventLevel = EventLevel.INFO) -> str:
        return self.emit(RuntimeEvent(
            trace_id=trace_id,
            source="binding",
            message=message,
            detail=detail,
            level=level,
            category=EventCategory.SYSTEM,
        ))

    def manual_reply_event(self, *, trace_id: str, message: str, detail: str = "", level: EventLevel = EventLevel.INFO) -> str:
        return self.emit(RuntimeEvent(
            trace_id=trace_id,
            source="manual_reply",
            message=message,
            detail=detail,
            level=level,
            category=EventCategory.MESSAGE,
        ))

    def system_event(self, *, trace_id: str, message: str, detail: str = "", level: EventLevel = EventLevel.INFO) -> str:
        return self.emit(RuntimeEvent(
            trace_id=trace_id,
            source="system",
            message=message,
            detail=detail,
            level=level,
            category=EventCategory.SYSTEM,
        ))

    def network_event(self, *, trace_id: str, message: str, detail: str = "", level: EventLevel = EventLevel.ERROR) -> str:
        return self.emit(RuntimeEvent(
            trace_id=trace_id,
            source="message_send",
            message=message,
            detail=detail,
            level=level,
            category=EventCategory.NETWORK,
        ))

    def message_event(self, *, trace_id: str, message: str, detail: str = "", level: EventLevel = EventLevel.INFO) -> str:
        return self.emit(RuntimeEvent(
            trace_id=trace_id,
            source="message_router",
            message=message,
            detail=detail,
            level=level,
            category=EventCategory.MESSAGE,
        ))

    def token_usage(self, *, trace_id: str, message: str, detail: str = "") -> str:
        return self.emit(RuntimeEvent(
            trace_id=trace_id,
            source="token_usage",
            message=message,
            detail=detail,
            level=EventLevel.INFO,
            category=EventCategory.AI,
        ))

    def update_ai_work(
        self,
        *,
        trace_id: str,
        status: str,
        answer: str = "",
        stage: str = "",
        error: str = "",
    ) -> None:
        update_ai_work_item(
            self._database_path,
            trace_id=trace_id,
            status=status,
            answer=answer,
            stage=stage,
            error=error,
        )

    def is_ai_cancelled(self, trace_id: str) -> bool:
        return is_ai_work_cancel_requested(self._database_path, trace_id)
