from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, Path as FastAPIPath, Request, UploadFile
from pathlib import Path

from app.api_response import ApiError
from app.db.skill_store import (
    get_enabled_skill_names,
    get_skill_display_names,
    set_skill_enabled,
    sync_skill_catalog,
    update_skill_display_names,
)
from app.exceptions import AppError, NotFoundError, ValidationError
from app.routers._deps import get_database_path, get_project_root
from app.routers._utils import _collect_skill_bot_usage, _enrich_bot_bound_item
from app.routers.auth import require_admin, require_non_guest
from app.skills_store import delete_skill, install_skills_zip, parse_skills_zip, scan_skills

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _get_skill_scope_from_fs(project_root: Path, skill_name: str) -> str:
    for skill in scan_skills(project_root):
        if skill["name"] == skill_name:
            return str(skill.get("scope") or "bot").strip()
    return ""


def _get_system_skill_names(project_root: Path) -> set[str]:
    return {
        skill["name"]
        for skill in scan_skills(project_root)
        if str(skill.get("scope") or "bot") == "system"
    }


@router.get("", summary="获取技能列表", description="获取所有可用的技能列表，包括已启用和未启用的")
def get_skills(
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    enabled_names = get_enabled_skill_names(database_path)
    display_names = get_skill_display_names(database_path)
    skills = scan_skills(project_root, enabled_names, display_names)
    sync_skill_catalog(database_path, skills)
    usage_map = _collect_skill_bot_usage(
        database_path,
        [str(item.get("name") or "").strip() for item in skills],
    )
    skills = [
        _enrich_bot_bound_item(item, usage_map.get(str(item.get("name") or "").strip()))
        for item in skills
    ]
    return {"skills": skills}


@router.post("/parse", summary="解析技能包", description="解析技能 zip 文件，预览技能内容但不安装")
async def parse_skills_endpoint(
    request: Request,
    file: UploadFile = File(..., description="技能 zip 文件"),
) -> dict[str, Any]:
    require_non_guest(request)
    filename = file.filename or ""
    if not filename.lower().endswith(".zip"):
        raise ValidationError("只支持上传 zip 文件。")
    try:
        result = parse_skills_zip(await file.read())
        return {"ok": True, "skills": result["skills"], "total_files": result["total_files"]}
    except Exception as exc:
        raise ApiError(
            "Skills zip 解析失败",
            status_code=400,
            log_message="Failed to parse skills zip.",
        ) from exc


@router.post("/upload", summary="上传/编辑技能", description="上传新技能或编辑现有技能，同时可以更新技能显示名")
async def upload_skills_endpoint(
    request: Request,
    file: UploadFile | None = File(None, description="技能 zip 文件（新增时必填）"),
    type: str = Form("new", description="操作类型：new（新增）或 edit（编辑）"),
    skill_name: str = Form("", description="要编辑的技能名称（编辑时必填）"),
    display_names: str = Form("", description="技能显示名映射 JSON 字符串"),
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    require_non_guest(request)
    action_type = type.strip().lower() or "new"
    try:
        raw_display_names = str(display_names or "").strip()
        if action_type == "new":
            if file is None:
                raise ValidationError("新增技能时必须上传 zip 文件。")
            filename = file.filename or ""
            if not filename.lower().endswith(".zip"):
                raise ValidationError("只支持上传 zip 文件。")
            result = install_skills_zip(project_root, await file.read())
        elif action_type == "edit":
            clean_skill_name = skill_name.strip()
            if not clean_skill_name:
                raise ValidationError("编辑技能时必须提供 skill_name。")
            if _get_skill_scope_from_fs(project_root, clean_skill_name) == "system":
                raise ValidationError("系统级 Skill 不允许编辑")
            usage = _collect_skill_bot_usage(database_path, [clean_skill_name]).get(clean_skill_name)
            if usage and usage["mounted_bot_count"] > 0:
                raise ValidationError(
                    f"Skill [{usage['item_label']}] 已被 Bot [{', '.join(usage['mounted_bot_names'])}] 挂载，无法编辑",
                )
            result = {"extracted_files": 0}
        else:
            raise ValidationError("type 仅支持 new 或 edit。")

        if raw_display_names:
            try:
                payload = json.loads(raw_display_names)
            except json.JSONDecodeError as exc:
                raise ValidationError("技能显示名 payload 无效") from exc
            if not isinstance(payload, dict):
                raise ValidationError("技能显示名 payload 必须是对象")
            update_skill_display_names(
                database_path,
                {
                    str(key).strip(): str(value).strip()
                    for key, value in payload.items()
                    if str(key).strip()
                },
                system_names=_get_system_skill_names(project_root),
            )
        enabled_names = get_enabled_skill_names(database_path)
        dn = get_skill_display_names(database_path)
        skills = scan_skills(project_root, enabled_names, dn)
        sync_skill_catalog(database_path, skills)
        return {"ok": True, "extracted_files": result["extracted_files"], "skills": skills}
    except (ApiError, AppError):
        raise
    except Exception as exc:
        raise ApiError(
            "Skills zip 上传失败",
            status_code=400,
            log_message="Failed to upload skills zip.",
        ) from exc


@router.post("/{skill_name}/enabled", summary="启用/禁用技能", description="启用或禁用指定技能，已被 Bot 挂载的技能无法禁用")
def update_skill_enabled(
    request: Request,
    skill_name: str = FastAPIPath(..., description="技能名称"),
    payload: dict[str, Any] = Body(..., description="包含 enabled 字段的参数：enabled（布尔，true=启用，false=禁用）"),
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    require_non_guest(request)
    enabled = bool(payload.get("enabled", False))
    skill_scope = _get_skill_scope_from_fs(project_root, skill_name)
    if not enabled:
        usage = _collect_skill_bot_usage(database_path, [skill_name]).get(skill_name)
        if usage and usage["mounted_bot_count"] > 0:
            raise ValidationError(
                f"Skill [{usage['item_label']}] 已被 Bot [{', '.join(usage['mounted_bot_names'])}] 挂载，无法禁用",
            )
    set_skill_enabled(database_path, skill_name, enabled, scope=skill_scope or "bot")
    enabled_names = get_enabled_skill_names(database_path)
    display_names = get_skill_display_names(database_path)
    skills = scan_skills(project_root, enabled_names, display_names)
    sync_skill_catalog(database_path, skills)
    usage_map = _collect_skill_bot_usage(
        database_path,
        [str(item.get("name") or "").strip() for item in skills],
    )
    skills = [
        _enrich_bot_bound_item(item, usage_map.get(str(item.get("name") or "").strip()))
        for item in skills
    ]
    return {"skills": skills}


@router.delete("/{skill_name}", summary="删除技能", description="删除指定技能，已被 Bot 挂载的技能无法删除")
def delete_skill_api(
    request: Request,
    skill_name: str = FastAPIPath(..., description="技能名称"),
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    require_admin(request)
    if _get_skill_scope_from_fs(project_root, skill_name) == "system":
        raise ValidationError("系统级 Skill 不允许删除")
    usage = _collect_skill_bot_usage(database_path, [skill_name]).get(skill_name)
    if usage and usage["mounted_bot_count"] > 0:
        raise ValidationError(
            f"Skill [{usage['item_label']}] 已被 Bot [{', '.join(usage['mounted_bot_names'])}] 挂载，无法删除",
        )
    success = delete_skill(project_root, skill_name)
    if not success:
        raise NotFoundError("Skill 未找到")
    enabled_names = get_enabled_skill_names(database_path)
    display_names = get_skill_display_names(database_path)
    skills = scan_skills(project_root, enabled_names, display_names)
    sync_skill_catalog(database_path, skills)
    return {"ok": True, "skills": skills}
