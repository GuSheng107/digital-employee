from __future__ import annotations

"""帧缓存模块。

实现基于内存的企微 WebSocket 帧缓存，支持 TTL 过期淘汰和最大条目数限制。
用于在被动回复场景下暂存原始帧数据，以便后续手动回复时能获取对应的帧上下文。
"""

import time
from typing import Any


class FrameStore:
    """基于内存的帧缓存存储，支持 TTL 过期淘汰和最大条目数限制。

    以 trace_id 为键缓存原始帧数据，默认 TTL 为 300 秒，最大条目数为 1000。
    当条目数超过上限时，按插入时间淘汰最早的条目。支持按 trace_id
    或 chat_id 查找并弹出帧。
    """
    _TTL_SECONDS = 300
    _MAX_ENTRIES = 1000

    def __init__(self) -> None:
        self._frames: dict[str, tuple[dict[str, Any], float, str]] = {}

    def store(self, trace_id: str, frame: dict[str, Any], *, chat_id: str = "") -> None:
        if not trace_id:
            return
        now = time.time()
        self._frames[trace_id] = (frame, now, chat_id)
        if len(self._frames) > self._MAX_ENTRIES:
            sorted_keys = sorted(self._frames.keys(), key=lambda k: self._frames[k][1])
            for k in sorted_keys[: len(sorted_keys) - self._MAX_ENTRIES]:
                self._frames.pop(k, None)

    def pop(self, trace_id: str) -> dict[str, Any] | None:
        if not trace_id:
            return None
        self._evict_expired()
        entry = self._frames.pop(trace_id, None)
        if entry is None:
            return None
        frame, ts, _ = entry
        if time.time() - ts > self._TTL_SECONDS:
            return None
        return frame

    def pop_for_chat(self, chat_id: str) -> dict[str, Any] | None:
        if not chat_id:
            return None
        self._evict_expired()
        best_key = None
        best_ts = 0.0
        for k, (_, ts, cid) in self._frames.items():
            if cid == chat_id and ts > best_ts:
                best_key = k
                best_ts = ts
        if best_key is None:
            return None
        entry = self._frames.pop(best_key)
        frame, ts, _ = entry
        if time.time() - ts > self._TTL_SECONDS:
            return None
        return frame

    def _evict_expired(self) -> None:
        now = time.time()
        expired_keys = [k for k, (_, ts, _) in self._frames.items() if now - ts > self._TTL_SECONDS]
        for k in expired_keys:
            self._frames.pop(k, None)
