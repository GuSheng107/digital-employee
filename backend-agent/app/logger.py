from __future__ import annotations

"""日志配置与 Logger 工厂模块。

提供应用程序的日志配置功能，包括结构化 JSON 格式化器、控制台格式化器、
SQLite 数据库日志处理器，以及日志级别配置和 Logger 获取的工厂方法。
"""

import json
import logging
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.db.core import connect_database, initialize_database
from app.db.core import is_database_locked_error
from app.log_categories import classify_log_category
from app.log_shape import normalize_project_log_shape
from app.utils import CST

BOT_MESSAGE_LOGGER_NAME = "bot.message"

STRUCTURED_LOG_FIELDS = (
    "category",
    "trace_id",
    "bot_key",
    "chat_id",
    "chat_name",
    "sender_id",
    "reply_source",
    "stage",
    "duration_ms",
    "error_code",
    "request_method",
    "request_path",
)


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=CST).isoformat()
        base = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in STRUCTURED_LOG_FIELDS:
            value = getattr(record, field, None)
            if value is not None and value != "":
                base[field] = value
        if record.exc_info and record.exc_info[1] is not None:
            base["exception_type"] = type(record.exc_info[1]).__name__
            base["exception_message"] = str(record.exc_info[1])
        return json.dumps(base, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=CST).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        parts = [f"{timestamp} {record.levelname:5s} {record.name} - {record.getMessage()}"]
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            parts.append(f"trace_id={trace_id}")
        category = getattr(record, "category", None)
        if category:
            parts.append(f"category={category}")
        bot_key = getattr(record, "bot_key", None)
        if bot_key:
            parts.append(f"bot_key={bot_key}")
        chat_id = getattr(record, "chat_id", None)
        if chat_id:
            parts.append(f"chat_id={chat_id}")
        if record.exc_info and record.exc_info[1] is not None:
            parts.append(
                "".join(traceback.format_exception(*record.exc_info))
            )
        return " ".join(parts)


class SQLiteLogHandler(logging.Handler):
    def __init__(self, database_path: Path, level: int = logging.NOTSET) -> None:
        super().__init__(level=level)
        self.database_path = database_path.resolve()

    def emit(self, record: logging.LogRecord) -> None:
        # 过滤 DEBUG 级别日志
        if record.levelno < logging.INFO:
            return
        try:
            trace_id = str(getattr(record, "trace_id", "") or uuid4())
            message = record.getMessage()
            detail = ""
            if record.exc_info:
                detail = "".join(traceback.format_exception(*record.exc_info))
            message, detail = normalize_project_log_shape(
                source=record.name,
                message=message,
                detail=detail,
            )

            structured_extra = {}
            for field in STRUCTURED_LOG_FIELDS:
                value = getattr(record, field, None)
                if value is not None and value != "":
                    structured_extra[field] = str(value)
            if structured_extra:
                existing_detail = detail.strip()
                extra_json = json.dumps(structured_extra, ensure_ascii=False)
                detail = f"{extra_json}\n{existing_detail}" if existing_detail else extra_json
            category = classify_log_category(
                source=record.name,
                message=message,
                detail=detail,
                category=str(getattr(record, "category", "") or ""),
            )

            initialize_database(self.database_path)
            with connect_database(self.database_path) as conn:
                conn.execute(
                    """
                    INSERT INTO project_logs (
                        id, trace_id, created_at, category, level, source, message, detail, error_code
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid4().hex,
                        trace_id,
                        datetime.now(CST).isoformat(),
                        category,
                        record.levelname,
                        record.name,
                        message,
                        detail,
                        str(getattr(record, "error_code", "") or ""),
                    ),
                )
        except sqlite3.OperationalError as exc:
            if is_database_locked_error(exc):
                return
            self.handleError(record)
        except Exception:
            self.handleError(record)


def configure_logging(
    level: str,
    *,
    database_path: Path,
) -> None:
    # 确保最低日志级别为 INFO，不允许 DEBUG
    level_upper = level.upper()
    if level_upper in ("DEBUG", "NOTSET"):
        level_upper = "INFO"
    log_level = getattr(logging, level_upper, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()

    db_handler = SQLiteLogHandler(database_path, level=log_level)
    db_handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(db_handler)

    import sys
    if sys.platform == "win32":
        import codecs
        # Windows 控制台设置 UTF-8 编码
        console_handler = logging.StreamHandler(stream=codecs.getwriter("utf-8")(sys.stdout.buffer))
    else:
        console_handler = logging.StreamHandler()
    console_handler.setFormatter(ConsoleFormatter())
    root_logger.addHandler(console_handler)

    message_logger = logging.getLogger(BOT_MESSAGE_LOGGER_NAME)
    message_logger.setLevel(logging.INFO)
    message_logger.propagate = False

    for handler in list(message_logger.handlers):
        message_logger.removeHandler(handler)
        handler.close()

    message_logger.addHandler(logging.NullHandler())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def get_bot_message_logger() -> logging.Logger:
    return logging.getLogger(BOT_MESSAGE_LOGGER_NAME)
