from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db.core import connect_database
from app.utils import utc_now


def insert_document(
    database_path: Path,
    *,
    filename: str,
    storage_name: str,
    file_size: int,
    file_type: str,
    storage_path: str = "",
    mime_type: str = "",
) -> dict[str, Any]:
    now = utc_now()
    doc_id = str(uuid4())
    with connect_database(database_path) as conn:
        conn.execute(
            """
            INSERT INTO uploaded_documents (id, filename, storage_name, storage_path, file_size, file_type, mime_type, parse_status, created_at, updated_at, convert_status, convert_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, '', '')
            """,
            (doc_id, filename, storage_name, storage_path, file_size, file_type, mime_type, now, now),
        )
    return {
        "id": doc_id,
        "filename": filename,
        "storage_name": storage_name,
        "storage_path": storage_path,
        "file_size": file_size,
        "file_type": file_type,
        "mime_type": mime_type,
        "parse_status": "pending",
        "parsed_at": "",
        "parse_error": "",
        "convert_status": "",
        "convert_at": "",
        "created_at": now,
        "updated_at": now,
    }


def list_documents(database_path: Path) -> list[dict[str, Any]]:
    with connect_database(database_path) as conn:
        rows = conn.execute(
            "SELECT * FROM uploaded_documents ORDER BY created_at DESC"
        ).fetchall()
    return [_doc_from_row(row) for row in rows]


def get_document_by_id(database_path: Path, doc_id: str) -> dict[str, Any] | None:
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT * FROM uploaded_documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
    if row is None:
        return None
    return _doc_from_row(row)


def delete_document(database_path: Path, doc_id: str) -> bool:
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT storage_name FROM uploaded_documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
        if row is None:
            return False
        conn.execute(
            "DELETE FROM uploaded_documents WHERE id = ?",
            (doc_id,),
        )
    return True


def find_duplicate_filename(database_path: Path, filename: str) -> list[str]:
    with connect_database(database_path) as conn:
        rows = conn.execute(
            "SELECT filename FROM uploaded_documents WHERE filename = ? OR filename LIKE ?",
            (filename, _duplicate_pattern(filename)),
        ).fetchall()
    return [str(row["filename"]) for row in rows]


def list_pending_documents(database_path: Path) -> list[dict[str, Any]]:
    with connect_database(database_path) as conn:
        rows = conn.execute(
            "SELECT * FROM uploaded_documents WHERE parse_status = 'pending' ORDER BY created_at ASC"
        ).fetchall()
    return [_doc_from_row(row) for row in rows]


def update_document_parse_status(database_path: Path, doc_id: str, status: str, error: str = "") -> None:
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            "UPDATE uploaded_documents SET parse_status = ?, parsed_at = ?, parse_error = ?, updated_at = ? WHERE id = ?",
            (status, now, error, now, doc_id),
        )


def update_document_convert_status(database_path: Path, doc_id: str, status: str) -> None:
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            "UPDATE uploaded_documents SET convert_status = ?, convert_at = ?, updated_at = ? WHERE id = ?",
            (status, now, now, doc_id),
        )


def _duplicate_pattern(filename: str) -> str:
    stem, dot, ext = filename.rpartition(".")
    if dot:
        return f"{stem} (%).{ext}"
    return f"{filename} (%)"


def _doc_from_row(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "filename": str(row["filename"]),
        "storage_name": str(row["storage_name"]),
        "storage_path": str(row["storage_path"]) if row["storage_path"] else "",
        "file_size": int(row["file_size"]),
        "file_type": str(row["file_type"]),
        "mime_type": str(row["mime_type"]) if row["mime_type"] else "",
        "parse_status": str(row["parse_status"]) if row["parse_status"] else "pending",
        "parsed_at": str(row["parsed_at"]) if row["parsed_at"] else "",
        "parse_error": str(row["parse_error"]) if row["parse_error"] else "",
        "convert_status": str(row["convert_status"]) if row["convert_status"] else "",
        "convert_at": str(row["convert_at"]) if row["convert_at"] else "",
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }
