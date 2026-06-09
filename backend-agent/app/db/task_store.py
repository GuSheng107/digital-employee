from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.db.ai_work_store import _ai_work_primary_key_column, _quote_identifier
from app.db.core import connect_database, initialize_database, _row_value
from app.utils import CST, utc_now
from app.yaml_config import get_yaml_config

SYSTEM_DATABASE_CLEANUP_TASK_KEY = "system.database_cleanup"
SYSTEM_MEMORY_UPDATE_TASK_KEY = "system.memory_update"
SYSTEM_SELF_REVIEW_CHAT_MEMORY_TASK_KEY = "system.self_review_chat_memory"
SYSTEM_SELF_REVIEW_DOCUMENT_MEMORY_TASK_KEY = "system.self_review_document_memory"
VALID_TASK_SCOPES = {"system", "user"}
MEMORY_UPDATE_REVIEW_REQUIRED_PREFIX = "[memory_update_manual_review]"
DEFAULT_CHAT_MEMORY_REVIEW_PROMPT = json.dumps({
    "review_mode": "review",
    "review_prompt": (
        "审查会话记忆的整体质量与使用效果，从以下维度逐项评估：\n"
        "1. 命中率：显式记忆、用户偏好、工作事实是否在真实会话中被有效召回和使用；\n"
        "2. 冗余度：是否存在内容重复、语义重叠的记忆项浪费 token 预算；\n"
        "3. 漏召回：是否存在用户提问时应该命中但未命中的记忆；\n"
        "4. 无关注入：是否注入了与当前对话无关的记忆内容；\n"
        "5. 优先级合理性：高优先级记忆是否确实更重要，低优先级记忆是否被不当降级；\n"
        "6. 时效性：是否存在过时、失效的记忆项需要更新或删除。\n"
        "对每个发现的问题给出 severity（high/medium/low）和具体修复建议。"
    ),
}, ensure_ascii=False)
DEFAULT_DOCUMENT_MEMORY_REVIEW_PROMPT = json.dumps({
    "review_mode": "review",
    "review_prompt": (
        "审查文档记忆的写入质量和使用效果，从以下维度逐项评估：\n"
        "1. 使用率：文档记忆是否在真实会话中被有效召回和使用；\n"
        "2. 检索质量：speed_lookup 和 retrieval 描述是否准确、无重复、能命中自然语言查询；\n"
        "3. 内容质量：key_points 和 business_facts 是否完整、准确、无冗余；\n"
        "4. 归类准确性：记忆项是否被正确归类到对应字段，是否存在错误归类；\n"
        "5. 漏召回：是否存在用户提问时应该命中但未命中的文档知识；\n"
        "6. 切分合理性：文档是否被合理拆分为独立记忆项，是否存在孤立术语或不完整事实。\n"
        "对每个发现的问题给出 severity（high/medium/low）和具体修复建议。"
    ),
}, ensure_ascii=False)


def _canonicalize_task_scope(scope: str, *, default: str = "user") -> str:
    normalized = str(scope or "").strip().lower()
    if normalized in VALID_TASK_SCOPES:
        return normalized
    return default


_UNLIMITED_PROMPT_HANDLERS = frozenset({
    "memory_update",
    "document_memory_extraction",
    "self_review_chat_memory",
    "self_review_document_memory",
    "explicit_memory",
    "bot_task",
})


def _normalize_task_prompt(prompt_text: str, *, handler_name: str = "") -> str:
    text = str(prompt_text or "").strip()
    if handler_name in _UNLIMITED_PROMPT_HANDLERS:
        return text
    return text[:2000]


def _parse_utc(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CST)
    return parsed.astimezone(CST)


def _periodic_status(row: dict[str, Any], *, now_text: str) -> str:
    if str(row.get("task_type") or "") == "one_time":
        run_state = str(row.get("run_state") or "")
        if run_state == "running":
            return "running"
        last_status = str(row.get("last_run_status") or "")
        if last_status == "completed":
            return "completed"
        if last_status == "failed":
            return "failed"
        return "pending"
    if str(row["run_state"] or "") == "running":
        return "running"
    last_status = str(row.get("last_run_status") or "")
    if last_status == "failed":
        return "failed"
    if not bool(row["is_enabled"]):
        return "paused"
    return "active"


def _cycle_label(schedule_type: str, schedule_value: int, *, task_type: str = "periodic") -> str:
    if task_type == "one_time":
        return ""
    if schedule_type == "interval_days" and schedule_value > 0:
        return f"每{schedule_value}天"
    return schedule_type or "-"


def _periodic_task_dict(row: Any, *, now_text: str) -> dict[str, Any]:
    item = {
        "task_key": str(row["task_key"]),
        "task_name": str(row["name"]),
        "task_scope": _canonicalize_task_scope(str(row["task_scope"]), default="user"),
        "task_type": str(row["task_type"]),
        "executor_kind": str(row["executor_kind"]),
        "executor_id": str(_row_value(row, "executor_id", "")),
        "handler_name": str(row["handler_name"]),
        "schedule_type": str(row["schedule_type"]),
        "schedule_value": int(row["schedule_value"]),
        "schedule_time": str(_row_value(row, "schedule_time", "00:00")),
        "cycle_label": _cycle_label(str(row["schedule_type"]), int(row["schedule_value"]), task_type=str(row["task_type"])),
        "prompt_text": _normalize_task_prompt(str(row["prompt_text"]), handler_name=str(row["handler_name"])),
        "description": str(row["description"]),
        "is_enabled": bool(row["is_enabled"]),
        "run_state": str(row["run_state"]),
        "last_run_at": str(row["last_run_at"]),
        "last_run_status": str(row["last_run_status"]),
        "last_run_message": str(row["last_run_message"]),
        "next_run_at": str(row["next_run_at"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "notify_bot_key": str(_row_value(row, "notify_bot_key", "")),
    }
    item["status"] = _periodic_status(item, now_text=now_text)
    return item


def _system_created_at() -> str:
    now = datetime.now(CST)
    return now.replace(minute=0, second=0, microsecond=0).isoformat()


def ensure_default_periodic_tasks(database_path: Path) -> None:
    initialize_database(database_path)
    now = utc_now()
    system_created = _system_created_at()
    
    prompt_text = (
        "• 物理清除 30 天以前的所有用户对话\n"
        "• 物理清除已删除超过 30 天的 Bot 及其关联数据\n"
        "• 清除 30 天前的 Token 消耗记录\n"
        "• 清除 30 天前已完成的一次性任务\n"
        "• 清除 15 天前的所有项目日志\n"
        "• 执行 SQLite VACUUM 优化数据库大小"
    )
    
    with connect_database(database_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO scheduled_tasks (
                task_key, name, task_scope, task_type, executor_kind, executor_id, handler_name,
                schedule_type, schedule_value, schedule_time, prompt_text, description, is_enabled,
                run_state, last_run_at, last_run_status, last_run_message, next_run_at,
                locked_at, created_at, updated_at
            )
            VALUES (?, ?, 'system', 'periodic', 'builtin', '', 'database_cleanup',
                    'interval_days', 15, '22:00', ?, ?, 1, 'idle', '', '', '', ?, '', ?, ?)
            """,
            (
                SYSTEM_DATABASE_CLEANUP_TASK_KEY,
                "数据库清理",
                prompt_text,
                "清理冗余数据",
                _next_run_at_utc("interval_days", 15, "22:00", base=now),
                system_created,
                now,
            ),
        )
        conn.execute(
            """
            UPDATE scheduled_tasks
            SET prompt_text = ?,
                updated_at = ?
            WHERE task_key = ?
              AND task_scope = 'system'
              AND handler_name = 'database_cleanup'
            """,
            (prompt_text, now, SYSTEM_DATABASE_CLEANUP_TASK_KEY),
        )


def ensure_agent_dependent_tasks(database_path: Path) -> None:
    from app.db.settings_store import get_platform_settings
    
    provider = str(get_platform_settings().get("platform_agent_provider") or "").strip()
    if not provider:
        return
    
    initialize_database(database_path)
    now = utc_now()

    with connect_database(database_path) as conn:
        existing = conn.execute(
            "SELECT task_key FROM scheduled_tasks WHERE task_key IN (?, ?, ?)",
            (
                SYSTEM_MEMORY_UPDATE_TASK_KEY,
                SYSTEM_SELF_REVIEW_CHAT_MEMORY_TASK_KEY,
                SYSTEM_SELF_REVIEW_DOCUMENT_MEMORY_TASK_KEY,
            ),
        ).fetchall()
        existing_keys = {str(row["task_key"]) for row in existing}

        if SYSTEM_MEMORY_UPDATE_TASK_KEY not in existing_keys:
            conn.execute(
                """
                INSERT INTO scheduled_tasks (
                    task_key, name, task_scope, task_type, executor_kind, executor_id, handler_name,
                    schedule_type, schedule_value, schedule_time, prompt_text, description, is_enabled,
                    run_state, last_run_at, last_run_status, last_run_message, next_run_at,
                    locked_at, created_at, updated_at
                )
                VALUES (?, ?, 'system', 'periodic', 'platform_agent', '', 'memory_update',
                        'interval_days', 7, '20:00', '', ?, 1, 'idle', '', '', '', ?, '', ?, ?)
                """,
                (
                    SYSTEM_MEMORY_UPDATE_TASK_KEY,
                    "记忆更新",
                    "定期从会话记录中提取和更新记忆",
                    _next_run_at_utc("interval_days", 7, "20:00", base=now),
                    now,
                    now,
                ),
            )

        if SYSTEM_SELF_REVIEW_CHAT_MEMORY_TASK_KEY not in existing_keys:
            conn.execute(
                """
                INSERT INTO scheduled_tasks (
                    task_key, name, task_scope, task_type, executor_kind, executor_id, handler_name,
                    schedule_type, schedule_value, schedule_time, prompt_text, description, is_enabled,
                    run_state, last_run_at, last_run_status, last_run_message, next_run_at,
                    locked_at, created_at, updated_at
                )
                VALUES (?, ?, 'system', 'periodic', 'platform_agent', '', 'self_review_chat_memory',
                        'interval_days', 7, '20:00', ?, ?, 0, 'idle', '', '', '', ?, '', ?, ?)
                """,
                (
                    SYSTEM_SELF_REVIEW_CHAT_MEMORY_TASK_KEY,
                    "聊天记忆审核",
                    DEFAULT_CHAT_MEMORY_REVIEW_PROMPT,
                    "定期审查和优化聊天记录记忆",
                    _next_run_at_utc("interval_days", 13, "20:00", base=now),
                    now,
                    now,
                ),
            )

        if SYSTEM_SELF_REVIEW_DOCUMENT_MEMORY_TASK_KEY not in existing_keys:
            conn.execute(
                """
                INSERT INTO scheduled_tasks (
                    task_key, name, task_scope, task_type, executor_kind, executor_id, handler_name,
                    schedule_type, schedule_value, schedule_time, prompt_text, description, is_enabled,
                    run_state, last_run_at, last_run_status, last_run_message, next_run_at,
                    locked_at, created_at, updated_at
                )
                VALUES (?, ?, 'system', 'periodic', 'platform_agent', '', 'self_review_document_memory',
                        'interval_days', 7, '20:00', ?, ?, 0, 'idle', '', '', '', ?, '', ?, ?)
                """,
                (
                    SYSTEM_SELF_REVIEW_DOCUMENT_MEMORY_TASK_KEY,
                    "文档记忆审核",
                    DEFAULT_DOCUMENT_MEMORY_REVIEW_PROMPT,
                    "定期审查和优化文档记忆",
                    _next_run_at_utc("interval_days", 13, "20:00", base=now),
                    now,
                    now,
                ),
            )

    normalized_specs = (
        (
            SYSTEM_MEMORY_UPDATE_TASK_KEY,
            "memory_update",
            "记忆更新",
            "定期从真实会话中抽取并更新系统记忆",
            "",
            "20:00",
            1,
        ),
        (
            SYSTEM_SELF_REVIEW_CHAT_MEMORY_TASK_KEY,
            "self_review_chat_memory",
            "会话记忆审查",
            "定期审查聊天与草稿链路中的记忆使用效果",
            DEFAULT_CHAT_MEMORY_REVIEW_PROMPT,
            "21:00",
            0,
        ),
        (
            SYSTEM_SELF_REVIEW_DOCUMENT_MEMORY_TASK_KEY,
            "self_review_document_memory",
            "文档记忆审查",
            "定期审查文档记忆质量及真实会话中的使用效果",
            DEFAULT_DOCUMENT_MEMORY_REVIEW_PROMPT,
            "22:00",
            0,
        ),
    )
    with connect_database(database_path) as conn:
        for task_key, handler_name, name, description, prompt_text, schedule_time, default_enabled in normalized_specs:
            next_run_at = _next_run_at_utc("interval_days", 7, schedule_time, base=now)
            conn.execute(
                """
                UPDATE scheduled_tasks
                SET name = ?,
                    task_scope = 'system',
                    task_type = 'periodic',
                    executor_kind = 'platform_agent',
                    executor_id = '',
                    handler_name = ?,
                    schedule_type = 'interval_days',
                    schedule_value = 7,
                    schedule_time = ?,
                    prompt_text = CASE
                        WHEN COALESCE(prompt_text, '') = '' THEN ?
                        ELSE prompt_text
                    END,
                    description = ?,
                    -- 不覆盖用户的 is_enabled 选择，只在 INSERT 时设置默认值
                    is_enabled = is_enabled,
                    run_state = CASE
                        WHEN run_state IN ('running', 'manual_pending') THEN run_state
                        ELSE 'idle'
                    END,
                    next_run_at = CASE
                        WHEN COALESCE(last_run_at, '') = '' AND (COALESCE(next_run_at, '') = '' OR schedule_time != ? OR schedule_value != 7)
                            THEN ?
                        ELSE next_run_at
                    END,
                    updated_at = ?
                WHERE task_key = ?
                """,
                (
                    name,
                    handler_name,
                    schedule_time,
                    prompt_text,
                    description,
                    schedule_time,
                    next_run_at,
                    now,
                    task_key,
                ),
            )

        for task_key, default_prompt in (
            (SYSTEM_SELF_REVIEW_CHAT_MEMORY_TASK_KEY, DEFAULT_CHAT_MEMORY_REVIEW_PROMPT),
            (SYSTEM_SELF_REVIEW_DOCUMENT_MEMORY_TASK_KEY, DEFAULT_DOCUMENT_MEMORY_REVIEW_PROMPT),
        ):
            row = conn.execute(
                "SELECT prompt_text FROM scheduled_tasks WHERE task_key = ?",
                (task_key,),
            ).fetchone()
            if row and row["prompt_text"]:
                try:
                    json.loads(row["prompt_text"])
                except (json.JSONDecodeError, ValueError):
                    conn.execute(
                        "UPDATE scheduled_tasks SET prompt_text = ?, updated_at = ? WHERE task_key = ?",
                        (default_prompt, now, task_key),
                    )


def has_enabled_agent_dependent_tasks(database_path: Path) -> bool:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) as cnt FROM scheduled_tasks
            WHERE task_scope = 'system'
              AND is_enabled = 1
              AND handler_name IN ('memory_update', 'self_review_chat_memory', 'self_review_document_memory')
            """,
        ).fetchone()
    return int(row["cnt"]) > 0


def get_enabled_agent_dependent_tasks(database_path: Path) -> list[dict[str, Any]]:
    """获取所有启用状态的依赖平台 Agent 的任务列表"""
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT task_key, name, handler_name, is_enabled FROM scheduled_tasks
            WHERE task_scope = 'system'
              AND is_enabled = 1
              AND handler_name IN ('memory_update', 'self_review_chat_memory', 'self_review_document_memory')
            """,
        ).fetchall()
    return [dict(row) for row in rows]


def list_system_alerts(database_path: Path) -> list[dict[str, Any]]:
    initialize_database(database_path)
    alerts: list[dict[str, Any]] = []
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT task_key, name, handler_name, last_run_message, updated_at
            FROM scheduled_tasks
            WHERE handler_name = 'memory_update'
              AND is_enabled = 0
              AND last_run_status = 'failed'
              AND last_run_message LIKE ?
            ORDER BY updated_at DESC
            """,
            (f"{MEMORY_UPDATE_REVIEW_REQUIRED_PREFIX}%",),
        ).fetchall()
    for row in rows:
        raw_message = str(row["last_run_message"] or "")
        message = raw_message.removeprefix(MEMORY_UPDATE_REVIEW_REQUIRED_PREFIX).strip()
        alerts.append(
            {
                "id": f"task:{row['task_key']}:memory_update_review",
                "type": "memory_update_review_required",
                "task_key": str(row["task_key"]),
                "task_name": str(row["name"]),
                "handler_name": str(row["handler_name"]),
                "message": message or "记忆更新任务存在未处理的会话记录，请前往任务管理处理。",
                "updated_at": str(row["updated_at"] or ""),
            }
        )
    return alerts


def is_agent_dependent_handler(handler_name: str) -> bool:
    return handler_name in ("memory_update", "self_review_chat_memory", "self_review_document_memory", "document_memory_extraction", "explicit_memory")


def reset_running_periodic_tasks(database_path: Path) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE scheduled_tasks
            SET run_state = 'idle',
                locked_at = '',
                updated_at = ?
            WHERE run_state = 'running'
            """,
            (now,),
        )


def unclaim_task(database_path: Path, *, task_key: str, task_type: str = "") -> bool:
    initialize_database(database_path)
    now = utc_now()
    target_state = "idle" if task_type == "periodic" else "pending"
    with connect_database(database_path) as conn:
        cursor = conn.execute(
            """
            UPDATE scheduled_tasks
            SET run_state = ?,
                locked_at = '',
                updated_at = ?
            WHERE task_key = ?
              AND run_state = 'running'
            """,
            (target_state, now, task_key),
        )
        return cursor.rowcount > 0


def claim_due_periodic_tasks(database_path: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    initialize_database(database_path)
    now = utc_now()
    claim_limit_max = int(get_yaml_config().get("task.claim_limit_max"))
    current_limit = max(1, min(int(limit or 1), claim_limit_max))
    claimed: list[dict[str, Any]] = []
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM scheduled_tasks
            WHERE (is_enabled = 1 OR run_state = 'manual_pending')
              AND run_state IN ('idle', 'running', 'manual_pending')
              AND next_run_at != ''
              AND next_run_at <= ?
            ORDER BY next_run_at ASC, task_key ASC
            LIMIT ?
            """,
            (now, current_limit),
        ).fetchall()
        for row in rows:
            task_key = str(row["task_key"])
            schedule_type = str(row["schedule_type"])
            schedule_value = int(row["schedule_value"])
            next_run_at_str = str(row["next_run_at"])
            # 如果 next_run_at 严重过期（超过 2 个周期），修正到近期时间
            if schedule_type == "interval_days" and schedule_value > 0:
                next_run_at = _parse_utc(next_run_at_str)
                now_dt = _parse_utc(now)
                if next_run_at is not None and now_dt is not None:
                    delta_days = (now_dt - next_run_at).total_seconds() / 86400
                    overdue_multiplier = float(get_yaml_config().get("task.overdue_cycle_multiplier"))
                    if delta_days > schedule_value * overdue_multiplier:
                        # 严重过期，重算 next_run_at 到近期时间
                        new_next_run_at = _next_run_at_utc("interval_days", schedule_value, str(row["schedule_time"]), base=now)
                        conn.execute(
                            """
                            UPDATE scheduled_tasks
                            SET next_run_at = ?,
                                updated_at = ?
                            WHERE task_key = ?
                            """,
                            (new_next_run_at, now, task_key),
                        )
                        # 这个周期不执行，跳过
                        continue
            # 正常认领
            cursor = conn.execute(
                """
                UPDATE scheduled_tasks
                SET run_state = 'running',
                    locked_at = ?,
                    updated_at = ?
                WHERE task_key = ?
                  AND (is_enabled = 1 OR run_state = 'manual_pending')
                  AND run_state IN ('idle', 'running', 'manual_pending')
                  AND next_run_at != ''
                  AND next_run_at <= ?
                """,
                (now, now, task_key, now),
            )
            if not cursor.rowcount:
                continue
            task = _periodic_task_dict(row, now_text=now)
            task["run_state"] = "running"
            task["status"] = "running"
            claimed.append(task)
    return claimed


def _next_run_at_utc(schedule_type: str, schedule_value: int, schedule_time: str = "00:00", *, base: str | None = None) -> str:
    current = _parse_utc(base or "") or datetime.now(CST)
    try:
        hour, minute = map(int, schedule_time.split(":"))
    except (ValueError, AttributeError):
        hour, minute = 0, 0

    if schedule_type == "interval_days" and schedule_value > 0:
        target = current + timedelta(days=schedule_value)
    else:
        target = current + timedelta(days=1)
    target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target.isoformat()


def mark_periodic_task_finished(
    database_path: Path,
    *,
    task_key: str,
    run_status: str,
    message: str,
) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT schedule_type, schedule_value, schedule_time
            FROM scheduled_tasks
            WHERE task_key = ?
            """,
            (task_key,),
        ).fetchone()
        if row is None:
            return
        schedule_type = str(row["schedule_type"])
        schedule_value = int(row["schedule_value"])
        schedule_time = str(_row_value(row, "schedule_time", "00:00"))
        next_run_at = _next_run_at_utc(schedule_type, schedule_value, schedule_time, base=now)
        if run_status == "failed":
            conn.execute(
                """
                UPDATE scheduled_tasks
                SET run_state = 'idle',
                    is_enabled = 0,
                    locked_at = '',
                    last_run_at = ?,
                    last_run_status = ?,
                    last_run_message = ?,
                    next_run_at = ?,
                    updated_at = ?
                WHERE task_key = ?
                """,
                (now, run_status, str(message or "")[:2000], next_run_at, now, task_key),
            )
        else:
            conn.execute(
                """
                UPDATE scheduled_tasks
                SET run_state = 'idle',
                    locked_at = '',
                    last_run_at = ?,
                    last_run_status = ?,
                    last_run_message = ?,
                    next_run_at = ?,
                    updated_at = ?
                WHERE task_key = ?
                """,
                (now, run_status, str(message or "")[:2000], next_run_at, now, task_key),
            )


def list_periodic_tasks(
    database_path: Path,
    *,
    scope: str = "",
    keyword: str = "",
    status: str = "",
    task_type: str = "",
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    ensure_default_periodic_tasks(database_path)
    initialize_database(database_path)
    current_page = max(1, int(page or 1))
    current_page_size = min(max(1, int(page_size or 10)), 100)
    search_scope = str(scope or "").strip()
    if search_scope and search_scope not in VALID_TASK_SCOPES:
        return {
            "tasks": [],
            "total": 0,
            "page": current_page,
            "page_size": current_page_size,
            "total_pages": 1,
        }
    search_keyword = str(keyword or "").strip()
    search_status = str(status or "").strip()
    search_task_type = str(task_type or "").strip()
    clauses: list[str] = ["task_type = 'periodic'"]
    params: list[Any] = []
    if search_scope:
        clauses.append("task_scope = ?")
        params.append(search_scope)
    if search_task_type:
        clauses.append("task_type = ?")
        params.append(search_task_type)
    if search_keyword:
        pattern = f"%{search_keyword}%"
        clauses.append("(task_key LIKE ? OR name LIKE ? OR description LIKE ? OR prompt_text LIKE ?)")
        params.extend([pattern, pattern, pattern, pattern])
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    now = utc_now()
    with connect_database(database_path) as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM scheduled_tasks
            {where_sql}
            ORDER BY
                CASE task_scope WHEN 'system' THEN 0 ELSE 1 END,
                CASE task_type WHEN 'periodic' THEN 0 ELSE 1 END,
                next_run_at ASC,
                task_key ASC
            """,
            params,
        ).fetchall()
    items = [_periodic_task_dict(row, now_text=now) for row in rows]
    if search_status:
        items = [item for item in items if item["status"] == search_status]
    total = len(items)
    offset = (current_page - 1) * current_page_size
    paged_items = items[offset:offset + current_page_size]
    total_pages = (total + current_page_size - 1) // current_page_size if total > 0 else 1
    return {
        "tasks": paged_items,
        "total": total,
        "page": current_page,
        "page_size": current_page_size,
        "total_pages": total_pages,
    }


def list_one_time_tasks(
    database_path: Path,
    *,
    scope: str = "",
    keyword: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 10,
) -> dict[str, Any]:
    initialize_database(database_path)
    current_page = max(1, int(page or 1))
    current_page_size = min(max(1, int(page_size or 10)), 100)
    search_scope = str(scope or "").strip()
    if search_scope and search_scope not in VALID_TASK_SCOPES:
        return {
            "tasks": [],
            "total": 0,
            "page": current_page,
            "page_size": current_page_size,
            "total_pages": 1,
        }
    search_keyword = str(keyword or "").strip()
    search_status = str(status or "").strip()
    
    # 首先从 scheduled_tasks 表获取一次性任务
    st_clauses: list[str] = ["task_type = 'one_time'"]
    st_params: list[Any] = []
    if search_scope:
        st_clauses.append("task_scope = ?")
        st_params.append(search_scope)
    if search_keyword:
        pattern = f"%{search_keyword}%"
        st_clauses.append("(task_key LIKE ? OR name LIKE ? OR description LIKE ? OR prompt_text LIKE ?)")
        st_params.extend([pattern, pattern, pattern, pattern])
    
    st_where_sql = f"WHERE {' AND '.join(st_clauses)}" if st_clauses else ""
    
    # 然后从 ai_work_items 表获取一次性任务
    draft_predicate = (
        "(aw.stage = '按钮触发生成回复' "
        "OR EXISTS (SELECT 1 FROM token_usage tu WHERE tu.trace_id = aw.trace_id AND tu.call_type = 'draft' LIMIT 1))"
    )
    name_case = f"CASE WHEN {draft_predicate} THEN 'AI草稿' ELSE '智能回复' END"
    scope_case = "'system'"
    key_case = f"CASE WHEN {draft_predicate} THEN 'ai_draft' ELSE 'smart_reply' END"
    aw_clauses: list[str] = []
    aw_params: list[Any] = []
    if search_status:
        aw_clauses.append("aw.status = ?")
        aw_params.append(search_status)
    if search_scope:
        aw_clauses.append(f"{scope_case} = ?")
        aw_params.append(search_scope)
    if search_keyword:
        pattern = f"%{search_keyword}%"
        aw_clauses.append(
            f"(aw.chat_name LIKE ? OR aw.question LIKE ? OR aw.answer LIKE ? OR {name_case} LIKE ?)"
        )
        aw_params.extend([pattern, pattern, pattern, pattern])
    aw_where_sql = f"WHERE {' AND '.join(aw_clauses)}" if aw_clauses else ""
    
    all_tasks = []
    now = utc_now()
    
    with connect_database(database_path) as conn:
        ai_work_pk_sql = _quote_identifier(_ai_work_primary_key_column(conn))
        # 获取 scheduled_tasks 中的一次性任务
        st_rows = conn.execute(
            f"""
            SELECT *
            FROM scheduled_tasks
            {st_where_sql}
            ORDER BY created_at DESC, task_key DESC
            """,
            st_params,
        ).fetchall()
        
        for row in st_rows:
            task = _periodic_task_dict(row, now_text=now)
            task["task_type"] = "one_time"
            all_tasks.append(task)
        
        # 获取 ai_work_items 中的任务
        aw_count_row = conn.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM ai_work_items aw
            {aw_where_sql}
            """,
            aw_params,
        ).fetchone()
        aw_total = int(aw_count_row["total"])
        aw_rows = conn.execute(
            f"""
            SELECT
                aw.{ai_work_pk_sql} AS task_id,
                {key_case} AS task_key,
                {name_case} AS task_name,
                {scope_case} AS task_scope,
                aw.status,
                aw.chat_id,
                aw.chat_name,
                aw.question,
                aw.answer,
                aw.error,
                aw.stage,
                aw.started_at,
                aw.updated_at,
                aw.finished_at
            FROM ai_work_items aw
            {aw_where_sql}
            ORDER BY COALESCE(NULLIF(aw.started_at, ''), aw.updated_at) DESC, aw.{ai_work_pk_sql} DESC
            """,
            aw_params,
        ).fetchall()
        
        for row in aw_rows:
            all_tasks.append({
                "task_id": str(row["task_id"]),
                "task_key": str(row["task_key"]),
                "task_name": str(row["task_name"]),
                "task_scope": str(row["task_scope"]),
                "task_type": "one_time",
                "executor_kind": "bot",
                "executor_id": "",
                "description": "回答用户问题",
                "status": str(row["status"]),
                "chat_id": str(row["chat_id"]),
                "chat_name": str(row["chat_name"]),
                "prompt_text": _normalize_task_prompt(str(row["question"])),
                "result_text": str(row["answer"]),
                "error": str(row["error"]),
                "stage": str(row["stage"]),
                "started_at": str(row["started_at"]),
                "created_at": str(row["started_at"]),
                "updated_at": str(row["updated_at"]),
                "finished_at": str(row["finished_at"]),
            })
    
    # 按状态过滤
    if search_status:
        all_tasks = [t for t in all_tasks if t["status"] == search_status]
    
    # 排序
    all_tasks.sort(
        key=lambda t: (
            0 if t["task_scope"] == "system" else 1,
            t.get("created_at") or t.get("updated_at") or "",
        ),
        reverse=True,
    )
    
    total = len(all_tasks)
    offset = (current_page - 1) * current_page_size
    paged_tasks = all_tasks[offset: offset + current_page_size]
    total_pages = (total + current_page_size - 1) // current_page_size if total > 0 else 1
    
    return {
        "tasks": paged_tasks,
        "total": total,
        "page": current_page,
        "page_size": current_page_size,
        "total_pages": total_pages,
    }


def get_periodic_task(database_path: Path, *, task_key: str) -> dict[str, Any] | None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT * FROM scheduled_tasks WHERE task_key = ?",
            (task_key,),
        ).fetchone()
    if row is None:
        return None
    return _periodic_task_dict(row, now_text=now)


def enable_periodic_task(database_path: Path, *, task_key: str) -> bool:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT task_scope, is_enabled FROM scheduled_tasks WHERE task_key = ?",
            (task_key,),
        ).fetchone()
        if row is None:
            return False
        if bool(row["is_enabled"]):
            return False
        conn.execute(
            """
            UPDATE scheduled_tasks
            SET is_enabled = 1, updated_at = ?
            WHERE task_key = ? AND is_enabled = 0
            """,
            (now, task_key),
        )
        return conn.execute("SELECT changes()").fetchone()[0] > 0


def disable_periodic_task(database_path: Path, *, task_key: str) -> bool:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT task_scope, is_enabled, run_state FROM scheduled_tasks WHERE task_key = ?",
            (task_key,),
        ).fetchone()
        if row is None:
            return False
        if not bool(row["is_enabled"]):
            return False
        if str(row["run_state"]) == "running":
            return False
        conn.execute(
            """
            UPDATE scheduled_tasks
            SET is_enabled = 0, updated_at = ?
            WHERE task_key = ? AND is_enabled = 1 AND run_state != 'running'
            """,
            (now, task_key),
        )
        return conn.execute("SELECT changes()").fetchone()[0] > 0


def update_periodic_task(
    database_path: Path,
    *,
    task_key: str,
    name: str | None = None,
    description: str | None = None,
    executor_kind: str | None = None,
    executor_id: str | None = None,
    schedule_type: str | None = None,
    schedule_value: int | None = None,
    schedule_time: str | None = None,
    prompt_text: str | None = None,
    task_type: str | None = None,
    notify_bot_key: str | None = None,
) -> bool:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT task_scope, is_enabled, task_type, handler_name FROM scheduled_tasks WHERE task_key = ?",
            (task_key,),
        ).fetchone()
        if row is None:
            return False
        
        # 记忆更新、文档提取和记忆审查任务允许编辑，即使是系统任务也可以
        is_editable_system_task = str(row["task_scope"]) == "system" and str(row["handler_name"]) in ["memory_update", "document_memory_extraction", "self_review_chat_memory", "self_review_document_memory"]
        
        if str(row["task_scope"]) == "system" and not is_editable_system_task:
            return False
        if str(row["task_type"]) == "periodic" and bool(row["is_enabled"]) and not is_editable_system_task:
            return False
        sets: list[str] = ["updated_at = ?"]
        params: list[Any] = [now]
        if name is not None:
            sets.append("name = ?")
            params.append(str(name).strip()[:200])
        if description is not None:
            sets.append("description = ?")
            params.append(str(description).strip()[:2000])
        if executor_kind is not None:
            sets.append("executor_kind = ?")
            params.append(str(executor_kind).strip())
        if executor_id is not None:
            sets.append("executor_id = ?")
            params.append(str(executor_id).strip())
        if schedule_type is not None:
            sets.append("schedule_type = ?")
            params.append(str(schedule_type).strip())
        if schedule_value is not None:
            sets.append("schedule_value = ?")
            params.append(max(0, int(schedule_value)))
        if schedule_time is not None:
            sets.append("schedule_time = ?")
            params.append(str(schedule_time).strip())
        if prompt_text is not None:
            sets.append("prompt_text = ?")
            params.append(str(prompt_text).strip())
        if task_type is not None:
            sets.append("task_type = ?")
            params.append(str(task_type).strip())
            if str(task_type).strip() == "one_time":
                sets.append("schedule_type = ?")
                params.append("")
                sets.append("schedule_value = ?")
                params.append(0)
                sets.append("schedule_time = ?")
                params.append("")
                sets.append("next_run_at = ?")
                params.append("")
                sets.append("last_run_at = ?")
                params.append("")
                sets.append("last_run_status = ?")
                params.append("")
                sets.append("last_run_message = ?")
                params.append("")
                sets.append("is_enabled = ?")
                params.append(1)
                sets.append("run_state = ?")
                params.append("pending")
                sets.append("locked_at = ?")
                params.append("")
        if notify_bot_key is not None:
            sets.append("notify_bot_key = ?")
            params.append(str(notify_bot_key).strip())

        if str(row["task_type"]) == "periodic" and (schedule_type is not None or schedule_value is not None or schedule_time is not None):
            current = conn.execute(
                "SELECT schedule_type, schedule_value, schedule_time FROM scheduled_tasks WHERE task_key = ?",
                (task_key,),
            ).fetchone()
            if current:
                st = schedule_type if schedule_type is not None else str(current["schedule_type"])
                sv = schedule_value if schedule_value is not None else int(current["schedule_value"])
                stime = schedule_time if schedule_time is not None else str(_row_value(current, "schedule_time", "00:00"))
                next_run_at = _next_run_at_utc(st, sv, stime, base=now)
                sets.append("next_run_at = ?")
                params.append(next_run_at)

        params.append(task_key)
        
        if is_editable_system_task:
            conn.execute(
                f"""
                UPDATE scheduled_tasks
                SET {', '.join(sets)}
                WHERE task_key = ?
                """,
                params,
            )
        else:
            conn.execute(
                f"""
                UPDATE scheduled_tasks
                SET {', '.join(sets)}
                WHERE task_key = ? AND task_scope = 'user'
                """,
                params,
            )
        return conn.execute("SELECT changes()").fetchone()[0] > 0


_PROTECTED_HANDLERS = frozenset({
    "memory_update",
    "self_review_chat_memory",
    "self_review_document_memory",
    "database_cleanup",
})

def delete_periodic_task(database_path: Path, *, task_key: str) -> tuple[bool, str]:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT task_scope, is_enabled, task_type, handler_name, run_state FROM scheduled_tasks WHERE task_key = ?",
            (task_key,),
        ).fetchone()
        if row is None:
            return False, "任务不存在"
        handler_name = str(row["handler_name"] or "")
        if handler_name in _PROTECTED_HANDLERS:
            return False, "系统核心任务不允许删除"
        if str(row["run_state"]) == "running":
            return False, "执行中的任务不允许删除"
        if str(row["task_type"]) == "periodic" and bool(row["is_enabled"]):
            return False, "周期任务启用中不允许删除，请先停用"
        conn.execute(
            "DELETE FROM scheduled_tasks WHERE task_key = ?",
            (task_key,),
        )
        return conn.execute("SELECT changes()").fetchone()[0] > 0, ""


def create_periodic_task(
    database_path: Path,
    *,
    name: str,
    description: str = "",
    executor_kind: str = "bot",
    executor_id: str = "",
    handler_name: str = "",
    schedule_type: str = "interval_days",
    schedule_value: int = 1,
    schedule_time: str = "00:00",
    prompt_text: str = "",
    task_scope: str = "user",
    notify_bot_key: str = "",
) -> dict[str, Any] | None:
    initialize_database(database_path)
    now = utc_now()
    from uuid import uuid4
    scope = _canonicalize_task_scope(task_scope, default="user")
    task_key = f"{scope}.{uuid4().hex[:12]}"
    is_enabled = 1 if scope == "system" else 0
    next_run_at = _next_run_at_utc(schedule_type, schedule_value, schedule_time, base=now)
    with connect_database(database_path) as conn:
        conn.execute(
            """
            INSERT INTO scheduled_tasks (
                task_key, name, task_scope, task_type, executor_kind, executor_id, handler_name,
                schedule_type, schedule_value, schedule_time, prompt_text, description, is_enabled,
                run_state, last_run_at, last_run_status, last_run_message, next_run_at,
                locked_at, created_at, updated_at, notify_bot_key
            )
            VALUES (?, ?, ?, 'periodic', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'idle', '', '', '', ?, '', ?, ?, ?)
            """,
            (
                task_key,
                str(name).strip()[:200],
                scope,
                str(executor_kind).strip(),
                str(executor_id).strip(),
                str(handler_name).strip(),
                str(schedule_type).strip(),
                max(1, int(schedule_value)),
                str(schedule_time).strip(),
                str(prompt_text).strip(),
                str(description).strip()[:2000],
                is_enabled,
                next_run_at,
                now,
                now,
                str(notify_bot_key).strip(),
            ),
        )
    return get_periodic_task(database_path, task_key=task_key)


def claim_due_one_time_tasks(database_path: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    initialize_database(database_path)
    now = utc_now()
    claim_limit_max = int(get_yaml_config().get("task.claim_limit_max"))
    current_limit = max(1, min(int(limit or 1), claim_limit_max))
    claimed: list[dict[str, Any]] = []
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM scheduled_tasks
            WHERE task_type = 'one_time'
              AND is_enabled = 1
              AND run_state = 'pending'
              AND next_run_at != ''
              AND next_run_at <= ?
            ORDER BY next_run_at ASC, task_key ASC
            LIMIT ?
            """,
            (now, current_limit),
        ).fetchall()
        for row in rows:
            cursor = conn.execute(
                """
                UPDATE scheduled_tasks
                SET run_state = 'running',
                    locked_at = ?,
                    updated_at = ?
                WHERE task_key = ?
                  AND task_type = 'one_time'
                  AND is_enabled = 1
                  AND run_state = 'pending'
                  AND next_run_at != ''
                  AND next_run_at <= ?
                """,
                (now, now, str(row["task_key"]), now),
            )
            if not cursor.rowcount:
                continue
            task = _periodic_task_dict(row, now_text=now)
            task["run_state"] = "running"
            task["status"] = "running"
            claimed.append(task)
    return claimed


def mark_one_time_task_finished(
    database_path: Path,
    *,
    task_key: str,
    run_status: str,
    message: str,
) -> None:
    initialize_database(database_path)
    now = utc_now()
    run_state = run_status
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE scheduled_tasks
            SET run_state = ?,
                locked_at = '',
                next_run_at = '',
                last_run_at = ?,
                last_run_status = ?,
                last_run_message = ?,
                updated_at = ?
            WHERE task_key = ?
            """,
            (run_state, now, run_status, str(message or "")[:2000], now, task_key),
        )


def reset_running_one_time_tasks(database_path: Path) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE scheduled_tasks
            SET run_state = 'pending',
                locked_at = '',
                updated_at = ?
            WHERE task_type = 'one_time'
              AND run_state = 'running'
            """,
            (now,),
        )


def list_overdue_tasks(database_path: Path) -> list[dict[str, Any]]:
    """列出所有过期任务（包括 periodic 和 one_time），用于启动诊断"""
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT task_key, name, task_type, schedule_type, schedule_value,
                   next_run_at, run_state, is_enabled
            FROM scheduled_tasks
            WHERE is_enabled = 1
              AND run_state NOT IN ('completed', 'failed')
              AND next_run_at != ''
              AND next_run_at <= ?
            ORDER BY next_run_at ASC, task_key ASC
            """,
            (now,),
        ).fetchall()
    return [dict(row) for row in rows]

def create_one_time_task(
    database_path: Path,
    *,
    name: str,
    description: str = "",
    executor_kind: str = "bot",
    executor_id: str = "",
    handler_name: str = "",
    prompt_text: str = "",
    execute_at: str = "",
    task_scope: str = "user",
) -> dict[str, Any] | None:
    initialize_database(database_path)
    now = utc_now()
    from uuid import uuid4
    scope = _canonicalize_task_scope(task_scope, default="user")
    task_key = f"{scope}.{uuid4().hex[:12]}"
    # 一次性任务默认 next_run_at 为空，不自动执行，需要手动触发
    next_run_at = execute_at or ""
    run_state = "pending"
    with connect_database(database_path) as conn:
        conn.execute(
            """
            INSERT INTO scheduled_tasks (
                task_key, name, task_scope, task_type, executor_kind, executor_id, handler_name,
                schedule_type, schedule_value, schedule_time, prompt_text, description, is_enabled,
                run_state, last_run_at, last_run_status, last_run_message, next_run_at,
                locked_at, created_at, updated_at
            )
            VALUES (?, ?, ?, 'one_time', ?, ?, ?, 'none', 0, '00:00', ?, ?, 1, ?, '', '', '', ?, '', ?, ?)
            """,
            (
                task_key,
                str(name).strip()[:200],
                scope,
                str(executor_kind).strip(),
                str(executor_id).strip(),
                str(handler_name).strip(),
                str(prompt_text).strip(),
                str(description).strip()[:2000],
                run_state,
                next_run_at,
                now,
                now,
            ),
        )
    return get_periodic_task(database_path, task_key=task_key)


def trigger_task_now(database_path: Path, *, task_key: str) -> bool:
    """立即触发任务执行，将 next_run_at 设置为当前时间，并调整相应状态"""
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT task_type, run_state, is_enabled, task_scope, handler_name, last_run_status
            FROM scheduled_tasks
            WHERE task_key = ?
            """,
            (task_key,),
        ).fetchone()
        if row is None:
            return False
        task_type = str(row["task_type"])
        handler_name = str(row["handler_name"])
        last_run_status = str(row["last_run_status"] or "")
        if handler_name == "database_cleanup":
            return False
        if is_agent_dependent_handler(handler_name):
            from app.db.settings_store import get_platform_settings
            provider = str(get_platform_settings().get("platform_agent_provider") or "").strip()
            if not provider:
                return False
        if task_type == "one_time":
            conn.execute(
                """
                UPDATE scheduled_tasks
                SET next_run_at = ?,
                    run_state = 'pending',
                    last_run_status = '',
                    last_run_message = '',
                    locked_at = '',
                    updated_at = ?
                WHERE task_key = ?
                """,
                (now, now, task_key),
            )
        else:
            conn.execute(
                """
                UPDATE scheduled_tasks
                SET next_run_at = ?,
                    run_state = 'manual_pending',
                    last_run_status = '',
                    last_run_message = '',
                    locked_at = '',
                    updated_at = ?
                WHERE task_key = ?
                """,
                (now, now, task_key),
            )
        return conn.execute("SELECT changes()").fetchone()[0] > 0
