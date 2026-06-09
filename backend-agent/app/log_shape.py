from __future__ import annotations

import re

_FILE_LINE_PATTERN = re.compile(r'\bFile\s+"[^"]+",\s+line\s+\d+')
_TRACEBACK_MARKERS = (
    "Traceback (most recent call last):",
    "During handling of the above exception",
    "During task with name",
)
_VERBOSE_MESSAGE_LENGTH = 1000
_SUMMARY_LENGTH = 240


def normalize_project_log_shape(
    *,
    source: str,
    message: str,
    detail: str = "",
) -> tuple[str, str]:
    """Keep project log rows in the same shape: summary in message, body in detail."""
    current_message = str(message or "")
    current_detail = str(detail or "")
    if not _should_move_message_to_detail(current_message):
        return current_message, current_detail

    parts = []
    if current_detail.strip():
        parts.append(current_detail.strip())
    if current_message.strip() and current_message.strip() not in current_detail:
        parts.append(current_message.strip())
    return _summarize_verbose_message(source=source, message=current_message), "\n".join(parts)


def _should_move_message_to_detail(message: str) -> bool:
    text = str(message or "")
    if not text.strip():
        return False
    if any(marker in text for marker in _TRACEBACK_MARKERS):
        return True
    if _FILE_LINE_PATTERN.search(text):
        return True
    if len(text) >= _VERBOSE_MESSAGE_LENGTH and "\n" in text:
        return True
    return False


def _summarize_verbose_message(*, source: str, message: str) -> str:
    source_text = str(source or "").strip().lower()
    if source_text.startswith("bot_process"):
        return "Bot 进程输出异常堆栈。"
    if any(marker in message for marker in _TRACEBACK_MARKERS) or _FILE_LINE_PATTERN.search(message):
        return "异常堆栈已记录到详情。"
    for line in message.splitlines():
        stripped = line.strip()
        if stripped:
            return _trim_summary(stripped)
    return "日志详情已记录到详情。"


def _trim_summary(value: str) -> str:
    text = str(value or "").strip()
    if len(text) <= _SUMMARY_LENGTH:
        return text
    return f"{text[:_SUMMARY_LENGTH].rstrip()}..."
