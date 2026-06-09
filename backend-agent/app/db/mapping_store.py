from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db.core import connect_database, initialize_database
from app.utils import utc_now


def get_bot_skill_mappings(database_path: Path, bot_key: str) -> list[str]:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            "SELECT skill_name FROM bot_skill_mapping WHERE bot_key = ? ORDER BY skill_name",
            (bot_key,),
        ).fetchall()
    return [str(row["skill_name"]) for row in rows]


def get_bot_mcp_mappings(database_path: Path, bot_key: str) -> list[str]:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            "SELECT server_id FROM bot_mcp_mapping WHERE bot_key = ? ORDER BY server_id",
            (bot_key,),
        ).fetchall()
    return [str(row["server_id"]) for row in rows]


def save_bot_skill_mappings(database_path: Path, bot_key: str, skill_names: list[str]) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute("DELETE FROM bot_skill_mapping WHERE bot_key = ?", (bot_key,))
        for skill_name in skill_names:
            clean_name = str(skill_name or "").strip()
            if not clean_name:
                continue
            conn.execute(
                """
                INSERT INTO bot_skill_mapping (bot_key, skill_name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(bot_key, skill_name) DO UPDATE SET
                    updated_at = excluded.updated_at
                """,
                (bot_key, clean_name, now, now),
            )


def save_bot_mcp_mappings(database_path: Path, bot_key: str, server_ids: list[str]) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute("DELETE FROM bot_mcp_mapping WHERE bot_key = ?", (bot_key,))
        for server_id in server_ids:
            clean_id = str(server_id or "").strip()
            if not clean_id:
                continue
            conn.execute(
                """
                INSERT INTO bot_mcp_mapping (bot_key, server_id, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(bot_key, server_id) DO UPDATE SET
                    updated_at = excluded.updated_at
                """,
                (bot_key, clean_id, now, now),
            )


def get_bot_mapping_counts(database_path: Path, bot_keys: list[str]) -> dict[str, dict[str, int]]:
    if not bot_keys:
        return {}
    initialize_database(database_path)
    placeholders = ",".join("?" for _ in bot_keys)
    result: dict[str, dict[str, int]] = {key: {"enabled_skill_count": 0, "enabled_mcp_count": 0} for key in bot_keys}
    with connect_database(database_path) as conn:
        skill_rows = conn.execute(
            f"SELECT bot_key, COUNT(*) AS cnt FROM bot_skill_mapping WHERE bot_key IN ({placeholders}) GROUP BY bot_key",
            bot_keys,
        ).fetchall()
        for row in skill_rows:
            key = str(row["bot_key"])
            if key in result:
                result[key]["enabled_skill_count"] = int(row["cnt"])

        mcp_rows = conn.execute(
            f"SELECT bot_key, COUNT(*) AS cnt FROM bot_mcp_mapping WHERE bot_key IN ({placeholders}) GROUP BY bot_key",
            bot_keys,
        ).fetchall()
        for row in mcp_rows:
            key = str(row["bot_key"])
            if key in result:
                result[key]["enabled_mcp_count"] = int(row["cnt"])
    return result
