"""Notify the current Bot owner. Args: --content [--reason] [--chat-id] [--bot-key]."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)

# Add project root to sys.path to enable app imports
_SCRIPT_DIR = Path(__file__).resolve()
for parent in _SCRIPT_DIR.parents:
    if (parent / "app").is_dir() and (parent / "pyproject.toml").is_file():
        sys.path.insert(0, str(parent))
        break
else:
    sys.path.insert(0, str(Path.cwd()))

# Import sqlite3 after sys.path is set (required for Windows)
import sqlite3

# Now import app modules
try:
    from app.db.core import connect_database
    from app.utils import default_database_path, resolve_database_path, utc_now
    from app.manual_reply_queue import enqueue_manual_reply
    from app import manual_reply_queue as _unused_import_check  # noqa
except Exception as exc:
    print(
        json.dumps(
            {"ok": False, "error": f"Failed to load app modules: {exc}"},
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    sys.exit(1)

# Constants
_DUPLICATE_WINDOW_SECONDS = 300
_MAX_CONTENT_LENGTH = 10000
_MAX_REASON_LENGTH = 2000


def _escape_like(text: str, escape: str = "$") -> str:
    return text.replace(escape, escape + escape).replace("%", escape + "%").replace("_", escape + "_")


def _log_error(
    database_path: Path,
    category: str,
    level: str,
    source: str,
    message: str,
    detail: str = "",
    error_code: str = "",
) -> None:
    """Log error to project_logs table."""
    try:
        now = utc_now()
        trace_id = uuid4().hex
        with connect_database(database_path) as conn:
            conn.execute(
                """
                INSERT INTO project_logs (
                    id, trace_id, created_at, category, level, source, message,
                    detail, error_code
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid4().hex,
                    trace_id,
                    now,
                    category,
                    level,
                    source,
                    message,
                    detail,
                    error_code,
                ),
            )
    except Exception as exc:
        logger.warning("_log_error failed: %s", exc)


def _check_duplicate_notification(
    database_path: Path,
    chat_id: str,
    content: str,
    bot_key: str,
) -> bool:
    """Check if similar notification was already sent in last 5 minutes."""
    from datetime import datetime, timezone
    from datetime import timedelta

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=_DUPLICATE_WINDOW_SECONDS)).isoformat()
    try:
        with connect_database(database_path) as conn:
            rows = conn.execute(
                """
                SELECT id FROM manual_reply_commands
                WHERE chat_id = ?
                  AND bot_key = ?
                  AND created_at >= ?
                  AND content LIKE ? ESCAPE '$'
                LIMIT 1
                """,
                (chat_id, bot_key, cutoff, f"%{_escape_like(content[:200])}%"),
            ).fetchall()
            return bool(rows)
    except Exception as exc:
        logger.warning("_check_duplicate_notification failed for chat_id=%s: %s", chat_id, exc)
        return False


def _find_bot_name(database_path: Path, bot_key: str) -> str:
    if not database_path.is_file():
        return bot_key
    try:
        with connect_database(database_path) as conn:
            row = conn.execute(
                "SELECT name FROM bot_config WHERE bot_key = ?",
                (bot_key,),
            ).fetchone()
        return str(row["name"]).strip() if row and str(row["name"]).strip() else bot_key
    except Exception as exc:
        logger.warning("_find_bot_name failed for bot_key=%s: %s", bot_key, exc)
        return bot_key


def _find_owner_conversation_for_bot(database_path: Path, bot_key: str) -> dict | None:
    if not database_path.is_file():
        return None
    try:
        with connect_database(database_path) as conn:
            conn.row_factory = sqlite3.Row  # noqa
            row = conn.execute(
                """
                SELECT chat_id, external_chat_id, chat_name, display_name,
                       bot_key, conversation_kind, chat_type
                FROM conversations
                WHERE conversation_kind = 'me'
                  AND bot_key = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (bot_key,),
            ).fetchone()
        return dict(row) if row else None
    except Exception as exc:
        logger.warning("_find_owner_conversation_for_bot failed for bot_key=%s: %s", bot_key, exc)
        return None


def _find_conversation_by_chat_id(database_path: Path, chat_id: str) -> dict | None:
    if not database_path.is_file():
        return None
    try:
        with connect_database(database_path) as conn:
            conn.row_factory = sqlite3.Row  # noqa
            row = conn.execute(
                """
                SELECT chat_id, chat_name, display_name, bot_key,
                       conversation_kind, chat_type, sender_id, sender_name
                FROM conversations
                WHERE chat_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (chat_id,),
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def _resolve_sender_display_name(database_path: Path, sender_id: str, fallback: str) -> str:
    if not sender_id:
        return fallback
    try:
        with connect_database(database_path) as conn:
            row = conn.execute(
                "SELECT display_name FROM user_profile WHERE user_id = ?",
                (sender_id.strip(),),
            ).fetchone()
        if row and str(row["display_name"] or "").strip():
            return str(row["display_name"]).strip()
    except Exception as exc:
        logger.warning("_resolve_sender_display_name failed for sender_id=%s: %s", sender_id, exc)
    return fallback


def _build_source_label(
    chat_type: str,
    display_name: str,
    chat_name: str,
    sender_display_name: str,
) -> str:
    effective_name = display_name or chat_name or ""
    is_group = chat_type in ("group", "room")
    sender = sender_display_name.strip() if sender_display_name else ""
    if is_group and effective_name and sender:
        return f"{effective_name}:{sender}"
    if is_group and effective_name:
        return effective_name
    if sender:
        return sender
    return effective_name or "未知来源"


def _build_result_notification_content(content: str, bot_display_name: str) -> str:
    return "\n".join(
        [
            f"**{bot_display_name}** 任务结果通知",
            "",
            content.strip(),
        ]
    ).strip()


def _build_notification_content(
    user_question: str,
    reason: str,
    bot_display_name: str,
    source_label: str,
) -> str:
    parts = [
        f"🔔 **{bot_display_name}** 需要人工介入",
        "",
        f"**来自：** {source_label}",
        f"**问题：** {user_question}",
        f"**原因：** {reason}",
        "",
        "请及时查看并处理。",
    ]
    return "\n".join(parts)


def _validate_input(content: str, reason: str) -> tuple[bool, str]:
    if len(content) > _MAX_CONTENT_LENGTH:
        return False, f"content too long (max {_MAX_CONTENT_LENGTH})"
    if reason and len(reason) > _MAX_REASON_LENGTH:
        return False, f"reason too long (max {_MAX_REASON_LENGTH})"
    if not content.strip():
        return False, "content cannot be empty"
    return True, ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Notify bot owner")
    parser.add_argument("--content", required=True, help="The user's original question")
    parser.add_argument(
        "--reason",
        default="",
        help="Why the agent cannot answer; optional for task result delivery",
    )
    parser.add_argument(
        "--chat-id",
        default=os.environ.get("CHAT_ID", ""),
        help="Current conversation chat_id (auto-injected via CHAT_ID env var when available)",
    )
    parser.add_argument(
        "--bot-key",
        default=os.environ.get("BOT_KEY"),
        required=os.environ.get("BOT_KEY") is None,
        help="Current bot_key for precise routing (auto-injected via BOT_KEY env var)",
    )
    
    # 修复：如果有多余的参数，将它们合并到 --content 中
    if len(sys.argv) > 1:
        new_argv = [sys.argv[0]]
        i = 1
        while i < len(sys.argv):
            arg = sys.argv[i]
            if arg == "--content":
                # 找到 --content，将后面所有不是以 -- 开头的参数合并
                new_argv.append(arg)
                i += 1
                content_parts = []
                while i < len(sys.argv) and not sys.argv[i].startswith("--"):
                    content_parts.append(sys.argv[i])
                    i += 1
                if content_parts:
                    new_argv.append(" ".join(content_parts))
            else:
                new_argv.append(arg)
                i += 1
        sys.argv = new_argv
    
    args = parser.parse_args()

    project_root = Path(os.environ["PROJECT_ROOT"]) if os.environ.get("PROJECT_ROOT") else None
    database_path = resolve_database_path(
        default_database_path(project_root) if project_root else None
    )
    if not database_path.is_file():
        _log_error(
            database_path,
            "notify_me",
            "error",
            "notify.py",
            f"Database not found at {database_path}",
        )
        print(
            json.dumps(
                {"ok": False, "error": f"Database not found at {database_path}"},
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    # Validate input
    valid, validation_error = _validate_input(args.content, args.reason)
    if not valid:
        _log_error(
            database_path,
            "notify_me",
            "warn",
            "notify.py",
            f"Input validation failed: {validation_error}",
        )
        print(
            json.dumps(
                {"ok": False, "error": validation_error},
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    bot_display_name = _find_bot_name(database_path, args.bot_key)

    owner_conv = _find_owner_conversation_for_bot(database_path, args.bot_key)
    if owner_conv is None:
        _log_error(
            database_path,
            "notify_me",
            "error",
            "notify.py",
            f"No owner conversation found for bot_key={args.bot_key}",
        )
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"Bot [{bot_display_name}] 尚未绑定管理员会话，无法发送通知",
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    target_conv = owner_conv
    target_external_chat_id = (
        str(target_conv.get("external_chat_id") or "").strip()
        or str(target_conv.get("chat_id") or "").strip()
    )
    if not target_external_chat_id:
        print(
            json.dumps(
                {"ok": False, "error": f"Bot [{bot_display_name}] 未找到可发送的管理员会话"},
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    reason_text = str(args.reason or "").strip()
    source_conv = _find_conversation_by_chat_id(database_path, args.chat_id) if args.chat_id else None
    sender_id = str(source_conv.get("sender_id", "")) if source_conv else ""
    raw_sender_name = str(source_conv.get("sender_name", "")) if source_conv else ""
    sender_display_name = _resolve_sender_display_name(
        database_path, sender_id, raw_sender_name
    )
    source_label = (
        _build_source_label(
            chat_type=str(source_conv.get("chat_type", "")) if source_conv else "",
            display_name=str(source_conv.get("display_name", "")) if source_conv else "",
            chat_name=str(source_conv.get("chat_name", "")) if source_conv else "",
            sender_display_name=sender_display_name,
        )
        if source_conv
        else "定时任务"
    )

    notification_content = (
        _build_notification_content(args.content, reason_text, bot_display_name, source_label)
        if reason_text
        else _build_result_notification_content(args.content, bot_display_name)
    )
    trace_id = str(os.environ.get("TRACE_ID") or "").strip()
    metadata = {
        "source": "notify_me_skill",
        "mode": "handoff" if reason_text else "result",
        "user_question": args.content[:500],
        "reason": reason_text[:500],
        "chat_id": args.chat_id,
    }
    if trace_id:
        metadata["trace_id"] = trace_id
    skip_record = str(os.environ.get("NOTIFY_SKIP_RECORD") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    is_duplicate = _check_duplicate_notification(
        database_path=database_path,
        chat_id=target_external_chat_id,
        content=notification_content,
        bot_key=args.bot_key,
    )
    if is_duplicate:
        print(
            json.dumps(
                {
                    "ok": True,
                    "notified": [],
                    "skipped": "duplicate",
                    "bot_key": args.bot_key,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    # Enqueue notification using official function
    try:
        command = enqueue_manual_reply(
            chat_id=target_external_chat_id,
            chat_name=target_conv.get("display_name") or target_conv.get("chat_name") or target_external_chat_id,
            content=notification_content,
            database_path=database_path,
            bot_key=args.bot_key,
            conversation_chat_id=target_conv["chat_id"],
            external_chat_id=target_external_chat_id,
            metadata=metadata,
            skip_record=skip_record,
        )

        print(
            json.dumps(
                {
                    "ok": True,
                    "notified": [
                        {
                            "chat_id": target_external_chat_id,
                            "chat_name": target_conv.get("display_name") or target_conv.get("chat_name") or target_external_chat_id,
                            "command_id": command.id,
                        }
                    ],
                    "target": "owner",
                    "bot_key": args.bot_key,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    except Exception as exc:
        _log_error(
            database_path,
            "notify_me",
            "error",
            "notify.py",
            f"Failed to enqueue notification: {exc}",
            detail=str(exc),
        )
        print(
            json.dumps(
                {"ok": False, "error": f"Failed to enqueue notification: {exc}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
