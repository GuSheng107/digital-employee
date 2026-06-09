from __future__ import annotations

"""流式 AI 响应编排模块，支持取消检测和进度追踪。"""

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from agent_runtime.service import AgentService
from app.db.ai_work_store import is_ai_work_cancel_requested, update_ai_work_item


class StreamStatus(Enum):
    """流式响应状态枚举，标识完成、取消或失败。"""

    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class StreamResult:
    """流式响应结果，包含状态、回答文本和可能的异常。"""

    status: StreamStatus
    answer: str = ""
    error: Exception | None = None


@dataclass
class StreamCallbacks:
    """流式响应回调集合，用于在流式输出的各个阶段触发自定义逻辑。"""

    on_token: Callable[[str], None] | None = None
    on_start: Callable[[], Any] | None = None
    on_cancel: Callable[[], Any] | None = None
    on_complete: Callable[[str], Any] | None = None
    on_fail: Callable[[str, Exception], Any] | None = None


class StreamAnswerOrchestrator:
    """流式回答编排器，协调 Agent 服务的流式输出，支持取消检测和进度更新。"""

    def __init__(
        self,
        *,
        database_path: Path,
        trace_id: str,
        agent_service: AgentService,
        bot_key: str = "",
        update_interval: float = 0.5,
    ) -> None:
        self._database_path = database_path
        self._trace_id = trace_id
        self._agent_service = agent_service
        self._bot_key = bot_key
        self._update_interval = update_interval

    def _is_cancelled(self) -> bool:
        return is_ai_work_cancel_requested(self._database_path, self._trace_id)

    async def stream(
        self,
        user_text: str,
        chat_id: str,
        *,
        sender_id: str = "",
        sender_name: str = "",
        call_type: str = "chat",
        callbacks: StreamCallbacks | None = None,
    ) -> StreamResult:
        cb = callbacks or StreamCallbacks()
        collected_parts: list[str] = []

        try:
            update_ai_work_item(
                self._database_path,
                trace_id=self._trace_id,
                status="running",
                stage="构建上下文并调用 Agent（流式）",
            )
            if cb.on_start:
                cb.on_start()

            last_update = 0.0
            async for token in self._agent_service.stream_answer(
                user_text,
                chat_id=chat_id,
                sender_id=sender_id,
                sender_name=sender_name,
                trace_id=self._trace_id,
                call_type=call_type,
                bot_key=self._bot_key,
                cancel_check=self._is_cancelled,
            ):
                if self._is_cancelled():
                    break
                collected_parts.append(token)
                if cb.on_token:
                    cb.on_token(token)
                now = time.time()
                if now - last_update > self._update_interval:
                    if not self._is_cancelled():
                        update_ai_work_item(
                            self._database_path,
                            trace_id=self._trace_id,
                            status="running",
                            answer="".join(collected_parts),
                            stage="Agent 推理中",
                        )
                    last_update = now

            if self._is_cancelled():
                update_ai_work_item(
                    self._database_path,
                    trace_id=self._trace_id,
                    status="cancelled",
                    answer="",
                    stage="已截断",
                )
                if cb.on_cancel:
                    cb.on_cancel()
                return StreamResult(status=StreamStatus.CANCELLED)

            full_answer = "".join(collected_parts)
            update_ai_work_item(
                self._database_path,
                trace_id=self._trace_id,
                status="completed",
                answer=full_answer,
                stage="完成",
            )
            if cb.on_complete:
                cb.on_complete(full_answer)
            return StreamResult(status=StreamStatus.COMPLETED, answer=full_answer)

        except Exception as exc:
            partial_answer = "".join(collected_parts)
            update_ai_work_item(
                self._database_path,
                trace_id=self._trace_id,
                status="failed",
                answer=partial_answer,
                error=str(exc),
                stage="异常截断",
            )
            if cb.on_fail:
                cb.on_fail(partial_answer, exc)
            return StreamResult(status=StreamStatus.FAILED, answer=partial_answer, error=exc)
