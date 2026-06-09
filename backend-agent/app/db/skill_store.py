from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from app.db.core import connect_database, initialize_database
from app.utils import utc_now

_logger = logging.getLogger(__name__)


def get_enabled_skill_names(database_path: Path) -> list[str]:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            "SELECT skill_name FROM skill_config WHERE enabled = 1 AND scope <> 'system' ORDER BY skill_name"
        ).fetchall()
    return [str(row["skill_name"]) for row in rows]


def sync_skill_catalog(database_path: Path, skills: list[dict[str, Any]]) -> None:
    initialize_database(database_path)
    now = utc_now()
    scanned_names: set[str] = set()
    with connect_database(database_path) as conn:
        for skill in skills:
            name = str(skill.get("name") or "").strip()
            if not name:
                continue
            scope = str(skill.get("scope") or "bot").strip() or "bot"
            if scope == "system":
                scanned_names.add(name)
                continue
            scanned_names.add(name)
            enabled = bool(skill.get("enabled"))
            display_name = str(skill.get("display_name") or name)
            try:
                conn.execute(
                    """
                    INSERT INTO skill_config (
                        skill_name, display_name, enabled, description, relative_path, source, scope,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'local', ?, ?, ?)
                    ON CONFLICT(skill_name) DO UPDATE SET
                        display_name = CASE
                            WHEN skill_config.display_name != '' THEN skill_config.display_name
                            ELSE excluded.display_name
                        END,
                        enabled = skill_config.enabled,
                        description = excluded.description,
                        relative_path = excluded.relative_path,
                        source = excluded.source,
                        scope = excluded.scope,
                        updated_at = excluded.updated_at
                    """,
                    (
                        name,
                        display_name,
                        int(enabled),
                        str(skill.get("description") or ""),
                        str(skill.get("relative_path") or ""),
                        scope,
                        now,
                        now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                if "skill_config.display_name" in str(exc) or "idx_skill_config_unique_display_name" in str(exc):
                    _logger.warning("Skill display name conflict during sync, skipping: %s", name)
                    continue
                raise
        conn.execute(
            "DELETE FROM skill_config WHERE scope <> 'system' AND skill_name NOT IN (%s)" % ",".join("?" * len(scanned_names)),
            list(scanned_names),
        ) if scanned_names else conn.execute("DELETE FROM skill_config WHERE scope <> 'system'")


def set_skill_enabled(database_path: Path, skill_name: str, enabled: bool, *, display_name: str = "", scope: str = "bot") -> None:
    if scope == "system":
        raise ValueError("系统级技能不允许修改启用状态")
    initialize_database(database_path)
    now = utc_now()
    effective_display_name = display_name or skill_name
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT scope FROM skill_config WHERE skill_name = ?",
            (skill_name,),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE skill_config SET enabled = ?, updated_at = ?
                WHERE skill_name = ?
                """,
                (int(enabled), now, skill_name),
            )
        else:
            conn.execute(
                """
                INSERT INTO skill_config (skill_name, display_name, enabled, scope, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (skill_name, effective_display_name, int(enabled), scope, now, now),
            )


def get_skill_display_names(database_path: Path) -> dict[str, str]:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            "SELECT skill_name, display_name FROM skill_config WHERE scope <> 'system' ORDER BY skill_name"
        ).fetchall()
    result: dict[str, str] = {}
    for row in rows:
        skill_name = str(row["skill_name"] or "").strip()
        if not skill_name:
            continue
        display_name = str(row["display_name"] or "").strip() or skill_name
        result[skill_name] = display_name
    return result


def _validate_skill_display_name_unique(
    conn: Any,
    display_name: str,
    *,
    exclude_skill_name: str | None = None,
    system_names: set[str] | None = None,
) -> None:
    row = conn.execute(
        """
        SELECT skill_name
        FROM skill_config
        WHERE display_name = ? AND (? IS NULL OR skill_name <> ?)
        LIMIT 1
        """,
        (display_name, exclude_skill_name, exclude_skill_name),
    ).fetchone()
    if row is not None:
        raise ValueError("技能显示名称必须唯一。")

    if system_names and display_name in system_names:
        raise ValueError("技能显示名称与系统级技能冲突，请更换名称。")


def _validate_skill_name_not_system_conflict(
    skill_name: str,
    *,
    system_names: set[str] | None = None,
) -> None:
    if system_names and skill_name in system_names:
        raise ValueError("技能名称与系统级技能冲突，请更换名称。")


def update_skill_display_names(database_path: Path, display_names: dict[str, str], *, system_names: set[str] | None = None) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        for skill_name, display_name in display_names.items():
            clean_name = str(skill_name or "").strip()
            if not clean_name:
                continue
            clean_display_name = str(display_name or "").strip() or clean_name
            _validate_skill_name_not_system_conflict(clean_name, system_names=system_names)
            _validate_skill_display_name_unique(conn, clean_display_name, exclude_skill_name=clean_name, system_names=system_names)
            try:
                conn.execute(
                    """
                    INSERT INTO skill_config (skill_name, display_name, enabled, scope, created_at, updated_at)
                    VALUES (?, ?, 0, 'bot', ?, ?)
                    ON CONFLICT(skill_name) DO UPDATE SET
                        display_name = excluded.display_name,
                        updated_at = excluded.updated_at
                    """,
                    (clean_name, clean_display_name, now, now),
                )
            except sqlite3.IntegrityError as exc:
                if "skill_config.display_name" in str(exc) or "idx_skill_config_unique_display_name" in str(exc):
                    raise ValueError("技能显示名称必须唯一。") from exc
                raise
