from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pathlib import Path
from typing import Any

from app.db.feedback_store import get_feedback_stats, list_feedback_alerts, list_feedbacks, list_feedbacks_by_message
from app.routers._deps import get_database_path

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.get("/stats", summary="获取反馈统计")
def feedback_stats(
    request: Request,
    days: int = 0,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    stats = get_feedback_stats(database_path, days=days)
    return {"ok": True, **stats}


@router.get("/list", summary="获取反馈列表")
def feedback_list(
    request: Request,
    result: str = "",
    days: int = 0,
    page: int = 1,
    page_size: int = 20,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    items = list_feedbacks(database_path, result=result, days=days, page=page, page_size=page_size)
    return {"ok": True, **items}


@router.get("/list-by-message", summary="按消息维度获取反馈列表")
def feedback_list_by_message(
    request: Request,
    result: str = "",
    days: int = 0,
    page: int = 1,
    page_size: int = 20,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    items = list_feedbacks_by_message(database_path, result=result, days=days, page=page, page_size=page_size)
    return {"ok": True, **items}


@router.get("/alerts", summary="获取反馈告警记录")
def feedback_alerts(
    request: Request,
    days: int = 0,
    page: int = 1,
    page_size: int = 20,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    items = list_feedback_alerts(database_path, days=days, page=page, page_size=page_size)
    return {"ok": True, **items}
