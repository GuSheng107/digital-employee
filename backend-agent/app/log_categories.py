from __future__ import annotations

VALID_LOG_CATEGORIES = (
    "system",
    "network",
    "ai",
    "task",
    "data",
    "bot",
    "media",
    "message",
)

def normalize_log_category(value: str, *, default: str = "system") -> str:
    normalized = str(value or "").strip().lower()
    if normalized in VALID_LOG_CATEGORIES:
        return normalized
    return default


def classify_log_category(
    *,
    source: str = "",
    message: str = "",
    detail: str = "",
    category: str = "",
) -> str:
    explicit = normalize_log_category(category, default="")
    if explicit:
        # 如果显式指定了 manual_reply，我们将其转换为 message
        if explicit == "manual_reply":
            return "message"
        return explicit

    source_text = str(source or "").strip().lower()
    combined = " ".join(
        part for part in (source_text, str(message or "").lower(), str(detail or "").lower()) if part
    )

    # 检查是否为媒体消息相关：优先匹配媒体分类
    if source_text.startswith("media") or any(
        token in combined
        for token in (
            "media_forward", "message_parser", "admin_message", "媒体", "media", "image", "video", "audio", "attachment", "附件", "图片", "视频", "音频"
        )
    ):
        return "media"
    
    # 检查是否为消息相关（包括手动回复）
    if source_text.startswith("manual_reply") or "manual_reply" in combined or source_text.startswith("message_"):
        return "message"
    
    if source_text.startswith("bot_process.") or "bot process" in combined:
        return "bot"
    if source_text.startswith("api:") or any(
        token in combined
        for token in ("websocket", "httpx", "network", "socket", "reply_stream", "send_message")
    ):
        return "network"
    if any(
        token in combined
        for token in ("ai_task", "ai_work", "queue", "任务", "并发槽", "cancel_requested")
    ):
        return "task"
    if any(
        token in combined
        for token in (
            "agent_runtime",
            "openai",
            "dashscope",
            "zhipu",
            "claude",
            "gemini",
            "deepseek",
            "moonshot",
            "minimax",
            "llm",
            "token",
            "模型",
            "agent",
        )
    ):
        return "ai"
    if any(
        token in combined
        for token in ("database", "sqlite", "vacuum", "data_management", "token_usage", "data_reset")
    ):
        return "data"
    if any(token in combined for token in ("web_server", "startup", "shutdown", "system", "bind", "unbind", "rebind")):
        return "system"
    if source_text.startswith("wecom_bot."):
        return "network"
    return "system"
