from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Path as FastAPIPath, Query, Request, UploadFile, File
from fastapi.responses import FileResponse
from pathlib import Path

from app.bot_process_manager import BotProcessManager
from app.database import get_database_info
from app.db.bot_store import list_bot_configs
from app.db.mapping_store import get_bot_mapping_counts
from app.db.task_store import list_system_alerts
from app.db.settings_store import load_settings_from_database
from app.db.document_store import (
    insert_document,
    list_documents,
    get_document_by_id,
    delete_document,
    find_duplicate_filename,
)
from app.db.task_store import create_one_time_task
from app.document_text_extractor import extract_text_from_file, validate_characters
from app.exceptions import NotFoundError, ValidationError
from app.routers._deps import get_database_path, get_manager, get_project_root
from app.routers._utils import _bot_api_view
from app.routers.auth import require_admin, require_non_guest
from app.chat_store import get_bot_unread_total
from app.yaml_config import get_yaml_config

router = APIRouter(prefix="/api", tags=["system"])

DOC_DIR_NAME = ".doc"
_MEMORY_TIMELINE_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

_FILE_SIGNATURES = {
    ".doc": [b"\xd0\xcf\x11\xe0"],
    ".docx": [b"PK\x03\x04"],
}

_TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv"}


@router.get("/status", summary="获取系统状态", description="获取系统运行状态，包括 Bot 状态、Agent 配置、数据库信息等")
def status(
    database_path: Path = Depends(get_database_path),
    manager: BotProcessManager = Depends(get_manager),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    current_settings = load_settings_from_database(database_path)
    bots = list_bot_configs(database_path)
    bot_keys = [str(bot["bot_key"]) for bot in bots]
    mapping_counts = get_bot_mapping_counts(database_path, bot_keys) if bot_keys else {}
    unread_totals = {bk: get_bot_unread_total(bot_key=bk, database_path=database_path) for bk in bot_keys}
    active_provider = current_settings.agent.providers.get(current_settings.agent.provider)
    bot_list = [_bot_api_view(bot, mapping_counts=mapping_counts, unread_totals=unread_totals) for bot in bots]
    return {
        "bots": bot_list,
        "bot_statuses": manager.all_statuses(bots),
        "crash_events": manager.get_unacknowledged_crashes(),
        "system_alerts": list_system_alerts(database_path),
        "agent": {
            "enabled": current_settings.agent.enabled,
            "auto_reply": current_settings.agent.auto_reply,
            "provider": current_settings.agent.provider,
            "model": active_provider.model if active_provider else "",
        },
        "web": {"dist_exists": (project_root / "web" / "dist" / "index.html").exists()},
        "database": get_database_info(database_path),
    }


@router.post("/crash-events/ack", summary="确认崩溃事件", description="确认单个或所有崩溃事件")
def ack_crash_events(
    request: Request,
    payload: dict[str, Any] = Body(..., description="包含 event_id 字段的参数：event_id（字符串，可选，指定要确认的单个事件，不提供则确认所有）"),
    manager: BotProcessManager = Depends(get_manager),
) -> dict[str, Any]:
    require_non_guest(request)
    event_id = str(payload.get("event_id") or "").strip()
    if event_id:
        ok = manager.acknowledge_crash(event_id)
        return {"ok": ok}
    count = manager.acknowledge_all_crashes()
    return {"ok": True, "acknowledged_count": count}


@router.post("/exit", summary="退出系统", description="安全退出系统，会先发送关闭消息给所有运行中的 Bot，然后停止服务器")
async def exit_system(
    request: Request,
    database_path: Path = Depends(get_database_path),
    manager: BotProcessManager = Depends(get_manager),
) -> dict[str, Any]:
    require_admin(request)
    from app.api_response import ApiError
    from app.routers.bots import _send_shutdown_text_if_needed
    from app.web_server import close_console
    try:
        bots = list_bot_configs(database_path)
        for bot in bots:
            bot_key = str(bot.get("bot_key", ""))
            if not bot_key:
                continue
            status = manager.status(bot_key)
            if status.get("running"):
                _send_shutdown_text_if_needed(
                    bot_key=bot_key,
                    database_path=database_path,
                )
        server = getattr(request.app.state, "uvicorn_server", None)
        if server is not None:
            server.should_exit = True
            import threading
            import time
            def close_later():
                time.sleep(0.5)
                close_console()
            threading.Thread(target=close_later, daemon=True).start()
        else:
            close_console()
            sys.exit(0)
        return {"ok": True, "message": "系统正在退出"}
    except SystemExit:
        raise
    except Exception as exc:
        raise ApiError(
            "系统退出失败",
            status_code=500,
            log_message="Failed to exit system.",
        ) from exc


def _resolve_doc_dir(project_root: Path) -> Path:
    doc_dir = project_root / DOC_DIR_NAME
    doc_dir.mkdir(parents=True, exist_ok=True)
    return doc_dir


def _get_doc_config(project_root: Path):
    config = get_yaml_config(project_root)
    allowed_extensions = set(config.get("doc.allowed_extensions"))
    max_file_size = config.get("doc.max_file_size")
    max_characters = int(config.get("doc.max_characters"))
    return allowed_extensions, max_file_size, max_characters


def _validate_file_type(filename: str, allowed_extensions: set) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in allowed_extensions:
        raise ValidationError(
            f"不支持的文件类型: {ext}，仅支持 {', '.join(sorted(allowed_extensions))}"
        )
    return ext


def _validate_file_size(content: bytes, filename: str, max_file_size: int) -> None:
    if len(content) > max_file_size:
        raise ValidationError(
            f"文件 {filename} 大小超过限制（最大 {max_file_size // (1024 * 1024)}MB）"
        )


def _validate_file_header(content: bytes, ext: str) -> None:
    if ext in _TEXT_EXTENSIONS:
        return
    signatures = _FILE_SIGNATURES.get(ext)
    if not signatures:
        return
    for sig in signatures:
        if content[: len(sig)] == sig:
            return
    raise ValidationError(f"文件内容与扩展名 {ext} 不匹配，可能为伪装文件")


def _resolve_duplicate_filename(database_path: Path, filename: str) -> str:
    existing = find_duplicate_filename(database_path, filename)
    if filename not in existing:
        return filename
    stem, dot, ext = filename.rpartition(".")
    if not dot:
        stem = filename
        ext = ""
    counter = 1
    while True:
        if ext:
            candidate = f"{stem} ({counter}).{ext}"
        else:
            candidate = f"{stem} ({counter})"
        if candidate not in existing:
            return candidate
        counter += 1


def _parse_split_pattern(filename):
    dot_pos = filename.rfind('.')
    if dot_pos == -1:
        stem = filename
    else:
        stem = filename[:dot_pos]
    underscore_pos = stem.rfind('_')
    if underscore_pos == -1:
        return None
    num_part = stem[underscore_pos + 1:]
    if not num_part.isdigit():
        return None
    n = int(num_part)
    if n <= 0:
        return None
    basename = stem[:underscore_pos]
    if not basename:
        return None
    return (basename, n)


def _resolve_memory_source_id(doc: dict[str, Any]) -> str:
    filename = str(doc.get("filename") or "").strip()
    parsed = _parse_split_pattern(filename)
    if parsed is not None:
        basename, _ = parsed
        return basename
    return str(doc.get("id") or "").strip()


def _get_memory_manager(project_root: Path):
    from app.memory_file_manager import MemoryFileManager
    memory_root = project_root / ".memory"
    return MemoryFileManager(memory_root)


def _document_memory_label_map(database_path: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    for doc in list_documents(database_path):
        source_id = _resolve_memory_source_id(doc)
        if not source_id:
            continue
        filename = str(doc.get("filename") or "").strip()
        parsed = _parse_split_pattern(filename)
        label = parsed[0] if parsed is not None else filename
        if label:
            labels.setdefault(source_id, label)
    return labels


def _normalize_memory_file_key(file_key: str) -> str:
    from app.memory_schema import MEMORY_JSON_FILES

    value = str(file_key or "").strip().replace("\\", "/")
    if not value or value.startswith("/") or ":" in value:
        raise ValidationError(f"无效的记忆文件标识: {file_key}")
    parts = [part for part in value.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise ValidationError(f"无效的记忆文件标识: {file_key}")
    if len(parts) == 1:
        key = parts[0]
        if key.endswith(".json"):
            key = key[:-5]
        if key in MEMORY_JSON_FILES:
            return key
        raise ValidationError(f"无效的记忆文件标识: {file_key}")
    if len(parts) != 2:
        raise ValidationError(f"无效的记忆文件标识: {file_key}")
    bucket, name = parts
    if name.endswith(".json"):
        name = name[:-5]
    if bucket == "timeline" and _MEMORY_TIMELINE_MONTH_RE.fullmatch(name):
        return f"timeline/{name}"
    if bucket == "documents" and name and name not in {".", ".."} and "/" not in name and "\\" not in name and ":" not in name:
        return f"documents/{name}"
    raise ValidationError(f"无效的记忆文件标识: {file_key}")


def _classify_review_report(f: Path) -> str:
    name = f.name
    if name.startswith("会话记忆使用审核_") or name.startswith("chat_usage_review_"):
        return "chat"
    if name.startswith("memory_files_review_"):
        return "memory_files"
    if name.startswith("compress_"):
        return "compress"
    if name.startswith("promote_inbox_"):
        return "promote_inbox"
    try:
        first_line = f.read_text(encoding="utf-8").split("\n", 1)[0]
        if "文档记忆使用审核" in first_line:
            return "document"
        if "会话记忆使用审核" in first_line:
            return "chat"
    except Exception:
        pass
    return "document"


@router.get("/documents", summary="获取文档列表", description="获取所有已上传的文档列表")
def get_documents(
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    docs = list_documents(database_path)
    return {"documents": docs}


@router.get("/documents/config", summary="获取文档配置", description="获取文档上传的配置信息")
def get_documents_config(
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    allowed_extensions, max_file_size, max_characters = _get_doc_config(project_root)
    return {
        "allowed_extensions": list(allowed_extensions),
        "max_file_size": max_file_size,
        "max_characters": max_characters,
    }


@router.post("/documents/upload", summary="上传文档", description="上传一个或多个文档到知识库，支持 doc、docx、txt 格式")
async def upload_documents(
    request: Request,
    files: list[UploadFile] = File(..., description="要上传的文档文件列表"),
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    require_non_guest(request)
    if not files:
        raise ValidationError("请选择至少一个文件")

    allowed_extensions, max_file_size, max_characters = _get_doc_config(project_root)

    split_data = [None] * len(files)
    basename_counts = {}
    for i, file in enumerate(files):
        filename = str(file.filename or "").strip()
        result = _parse_split_pattern(filename)
        if result:
            basename, index = result
            split_data[i] = (basename, index)
            basename_counts[basename] = basename_counts.get(basename, 0) + 1

    doc_dir = _resolve_doc_dir(project_root)
    uploaded = []

    for i, file in enumerate(files):
        filename = str(file.filename or "").strip()
        if not filename:
            raise ValidationError("文件名不能为空")

        ext = _validate_file_type(filename, allowed_extensions)
        content = await file.read()
        _validate_file_size(content, filename, max_file_size)
        _validate_file_header(content, ext)

        text = extract_text_from_file(content, ext)
        validate_characters(text, filename, max_characters)

        resolved_name = _resolve_duplicate_filename(database_path, filename)
        storage_name = f"{uuid4()}{ext}"
        storage_path = doc_dir / storage_name
        storage_path.write_bytes(content)

        mime_type = ""
        if ext == ".doc":
            mime_type = "application/msword"
        elif ext == ".docx":
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif ext == ".txt":
            mime_type = "text/plain"
        elif ext == ".md":
            mime_type = "text/markdown"
        elif ext == ".json":
            mime_type = "application/json"
        elif ext == ".csv":
            mime_type = "text/csv"

        doc = insert_document(
            database_path,
            filename=resolved_name,
            storage_name=storage_name,
            storage_path=str(storage_path),
            file_size=len(content),
            file_type=ext,
            mime_type=mime_type,
        )
        uploaded.append(doc)

        split_series = None
        split_index = None
        split_total = None
        if split_data[i] is not None:
            basename, index = split_data[i]
            split_series = basename
            split_index = index
            split_total = basename_counts[basename]

        create_one_time_task(
            database_path,
            name="知识提取",
            description="对用户上传的文档做知识和记忆提取",
            executor_kind="platform_agent",
            executor_id="",
            handler_name="document_memory_extraction",
            prompt_text=json.dumps({
                "doc_id": str(doc["id"]),
                "split_series": split_series,
                "split_index": split_index,
                "split_total": split_total,
            }, ensure_ascii=False),
            execute_at="",
            task_scope="system",
        )

    return {"ok": True, "documents": uploaded}


@router.get("/documents/{doc_id}/delete-preview", summary="预览删除文档影响", description="预览删除文档会影响哪些记忆文件和内容")
def preview_remove_document(
    doc_id: str = FastAPIPath(..., description="文档 ID"),
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    doc = get_document_by_id(database_path, doc_id)
    if doc is None:
        raise NotFoundError("文档未找到")

    mgr = _get_memory_manager(project_root)
    source_id = _resolve_memory_source_id(doc)
    try:
        preview = mgr.preview_remove_document_source(source_id)
    except Exception:
        preview = {"affected_files": [], "memory_items_count": 0, "document_exists": False}

    return {
        "ok": True,
        "doc_id": doc_id,
        "filename": doc.get("filename", ""),
        "source_id": source_id,
        "preview": preview,
        "message": (
            f"删除文档 '{doc.get('filename', '')}' 将影响以下记忆文件:\n"
            f"- 文档记忆文件: {source_id}.json ({preview['memory_items_count']} 条记忆条目)\n"
            f"- 其他关联文件: {', '.join(preview['affected_files']) if preview['affected_files'] else '无'}"
        ),
    }


@router.delete("/documents/{doc_id}", summary="删除文档", description="删除指定的文档及其关联记忆。如需确认请先调用预览接口")
def remove_document(
    request: Request,
    doc_id: str = FastAPIPath(..., description="文档 ID"),
    confirm: bool = False,
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    require_admin(request)
    doc = get_document_by_id(database_path, doc_id)
    if doc is None:
        raise NotFoundError("文档未找到")

    from app.api_response import ApiError
    from app.db.core import connect_database
    with connect_database(database_path) as conn:
        running_task = conn.execute(
            "SELECT task_key FROM scheduled_tasks WHERE handler_name = 'document_memory_extraction' AND run_state = 'running' AND prompt_text LIKE ?",
            (f'%{doc_id}%',),
        ).fetchone()
        if running_task is not None:
            raise ApiError("该文档有正在执行的提取任务，请先删除任务或等待完成", status_code=409)

    if not confirm:
        mgr = _get_memory_manager(project_root)
        source_id = _resolve_memory_source_id(doc)
        preview = mgr.preview_remove_document_source(source_id)

        raise ApiError(
            message="请确认删除操作",
            status_code=400,
            log_message=f"Document deletion requires confirmation: {doc_id}",
            extra_detail=json.dumps({
                "doc_id": doc_id,
                "filename": doc.get("filename", ""),
                "source_id": source_id,
                "affected_files": preview["affected_files"],
                "memory_items_count": preview["memory_items_count"],
                "hint": "请调用预览接口 GET /api/documents/{doc_id}/delete-preview 查看详情，或在删除请求中添加 ?confirm=true 参数确认删除",
            }, ensure_ascii=False),
        )

    storage_path = project_root / DOC_DIR_NAME / doc["storage_name"]
    if storage_path.exists():
        storage_path.unlink()

    updated_files: list[str] = []
    try:
        mgr = _get_memory_manager(project_root)
        source_id = _resolve_memory_source_id(doc)
        updated_files = mgr.remove_document_source(source_id)
    except Exception:
        pass

    delete_document(database_path, doc_id)

    return {
        "ok": True,
        "message": f"文档 '{doc.get('filename', '')}' 及其关联记忆已删除",
        "deleted_files": updated_files,
    }


@router.get("/documents/{doc_id}/download", summary="下载文档", description="下载指定的文档文件")
def download_document(
    doc_id: str = FastAPIPath(..., description="文档 ID"),
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> FileResponse:
    doc = get_document_by_id(database_path, doc_id)
    if doc is None:
        raise NotFoundError("文档未找到")

    storage_path = project_root / DOC_DIR_NAME / doc["storage_name"]
    if not storage_path.exists():
        raise NotFoundError("文档文件不存在")

    return FileResponse(
        path=str(storage_path),
        filename=doc["filename"],
        media_type="application/octet-stream",
    )


@router.get("/memory/files", summary="获取记忆文件列表", description="列出所有记忆文件及其统计信息")
def memory_list_files(
    project_root: Path = Depends(get_project_root),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    mgr = _get_memory_manager(project_root)
    return {"files": mgr.list_files(document_labels=_document_memory_label_map(database_path))}


@router.get("/memory/items/{file_key:path}", summary="获取记忆条目列表", description="列出指定记忆文件中的所有条目")
def memory_list_items(
    file_key: str = FastAPIPath(..., description="记忆文件标识，如 explicit、timeline/2025-05"),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    file_key = _normalize_memory_file_key(file_key)
    mgr = _get_memory_manager(project_root)
    items = mgr.get_items(file_key)
    return {
        "file_key": file_key,
        "items": [item.model_dump() for item in items],
    }


@router.get("/memory/item", summary="获取单条记忆", description="根据 file_key 和 item_id 获取单条记忆条目")
def memory_get_item(
    file_key: str = Query(..., description="记忆文件标识"),
    item_id: str = Query(..., description="条目 ID"),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    file_key = _normalize_memory_file_key(file_key)
    mgr = _get_memory_manager(project_root)
    item = mgr.get_item(file_key, item_id)
    if item is None:
        raise NotFoundError("记忆条目未找到")
    return {"file_key": file_key, "item": item.model_dump()}


@router.post("/memory/items/{file_key:path}", summary="新增记忆条目", description="在指定记忆文件中新增一条记忆")
def memory_add_item(
    request: Request,
    file_key: str = FastAPIPath(..., description="记忆文件标识"),
    payload: dict[str, Any] = Body(..., description="记忆条目数据，包含 content、content_type、speed_lookup 等字段"),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    require_non_guest(request)
    from app.memory_schema import MemoryItem
    file_key = _normalize_memory_file_key(file_key)
    content = str(payload.get("content") or "").strip()
    if not content:
        raise ValidationError("记忆内容不能为空")
    item_data = {"content": content}
    for field in ("content_type", "speed_lookup", "source", "source_id", "priority"):
        if field in payload:
            item_data[field] = payload[field]
    item = MemoryItem(**item_data)
    mgr = _get_memory_manager(project_root)
    added = mgr.add_item(file_key, item)
    return {"ok": True, "item": added.model_dump()}


@router.put("/memory/item", summary="更新记忆条目", description="更新指定记忆条目的内容")
def memory_update_item(
    request: Request,
    payload: dict[str, Any] = Body(..., description="包含 file_key、item_id 和要更新的字段"),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    require_non_guest(request)
    file_key = str(payload.get("file_key") or "").strip()
    item_id = str(payload.get("item_id") or "").strip()
    if not file_key:
        raise ValidationError("file_key 不能为空")
    file_key = _normalize_memory_file_key(file_key)
    if not item_id:
        raise ValidationError("item_id 不能为空")
    updates = {k: v for k, v in payload.items() if k not in ("file_key", "item_id")}
    mgr = _get_memory_manager(project_root)
    updated = mgr.update_item(file_key, item_id, updates)
    if updated is None:
        raise NotFoundError("记忆条目未找到")
    return {"ok": True, "item": updated.model_dump()}


@router.delete("/memory/item", summary="删除记忆条目", description="删除指定记忆文件中的某条记忆")
def memory_delete_item(
    request: Request,
    file_key: str = Query(..., description="记忆文件标识"),
    item_id: str = Query(..., description="条目 ID"),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    require_admin(request)
    file_key = _normalize_memory_file_key(file_key)
    mgr = _get_memory_manager(project_root)
    deleted = mgr.delete_item(file_key, item_id)
    if not deleted:
        raise NotFoundError("记忆条目未找到")
    return {"ok": True}


@router.get("/memory/search", summary="搜索记忆条目", description="在所有记忆文件中搜索匹配的条目")
def memory_search(
    q: str = Query(..., description="搜索关键词"),
    file_key: str = Query("", description="限定搜索的文件标识，为空则搜索所有文件"),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    mgr = _get_memory_manager(project_root)
    fk = _normalize_memory_file_key(file_key) if file_key.strip() else None
    results = mgr.search_items(q, file_key=fk)
    return {
        "query": q,
        "results": [
            {
                "file_key": r["file_key"],
                "score": r["score"],
                "item": r["item"].model_dump(),
            }
            for r in results
        ],
    }


@router.get("/memory/audits", summary="获取记忆审计日志", description="查询最近的记忆使用审计记录")
def get_memory_audits(
    days: int = 7,
    limit: int = 50,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    from app.db.memory_usage_audit_store import list_recent_memory_usage_audits
    audits = list_recent_memory_usage_audits(
        database_path,
        days=min(max(1, days), 30),
        limit=min(max(1, limit), 200),
    )
    return {"audits": audits, "total": len(audits)}


@router.get("/memory/reviews", summary="获取记忆审核报告", description="列出 .memory/reviews/ 目录下的审核报告")
def memory_list_reviews(
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    reviews_dir = project_root / ".memory" / "reviews"
    reports: list[dict[str, Any]] = []
    if reviews_dir.is_dir():
        raw_files = []
        for f in reviews_dir.iterdir():
            if f.is_file() and f.suffix in (".md", ".json"):
                stat = f.stat()
                report_type = _classify_review_report(f)
                raw_files.append({
                    "filename": f.name,
                    "size": stat.st_size,
                    "modified_at": int(stat.st_mtime * 1000),
                    "report_type": report_type,
                    "_sort_key": stat.st_mtime,
                })
        raw_files.sort(key=lambda x: x["_sort_key"], reverse=True)
        for item in raw_files:
            del item["_sort_key"]
            reports.append(item)
    return {"reports": reports}


@router.get("/memory/reviews/{filename}", summary="获取审核报告内容", description="读取指定审核报告的内容")
def memory_get_review(
    filename: str = FastAPIPath(..., description="报告文件名"),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    from fastapi.responses import PlainTextResponse
    reviews_dir = project_root / ".memory" / "reviews"
    filepath = reviews_dir / filename
    if not filepath.is_file() or ".." in filename or "/" in filename or "\\" in filename:
        raise ValidationError(f"报告文件不存在: {filename}")
    content = filepath.read_text(encoding="utf-8")
    return {"filename": filename, "content": content}


@router.delete("/memory/reviews/{filename}", summary="删除审核报告", description="删除指定的审核报告文件，不会删除已修改的记忆内容")
def memory_delete_review(
    request: Request,
    filename: str = FastAPIPath(..., description="报告文件名"),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    require_admin(request)
    reviews_dir = project_root / ".memory" / "reviews"
    filepath = reviews_dir / filename
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ValidationError(f"无效的文件名: {filename}")
    if not filepath.is_file():
        raise NotFoundError(f"报告文件不存在: {filename}")
    filepath.unlink()
    return {"ok": True, "filename": filename}
