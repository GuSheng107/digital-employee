"""邀请码管理路由（需要 invite_code:manage 权限）。

- POST /invite-codes：创建邀请码。
- GET  /invite-codes：列出所有邀请码。

两个端点都通过 access_token 鉴权（不挂载 API Key），并要求当前用户
持有 ``invite_code:manage`` 权限码（admin 角色自动放行）。
"""

from __future__ import annotations

from api_common import ApiResponse, success_response
from auth_utils import PermissionCode
from fastapi import APIRouter, Depends, Query

from app.api.deps import require_permission
from app.schemas.auth import UserInfo
from app.schemas.invite_code import CreateInviteCodeRequest
from app.services.invite_code_service import InviteCodeService

router = APIRouter()


@router.post("", response_model=ApiResponse)
def create_invite_code(
    payload: CreateInviteCodeRequest,
    current_user: UserInfo = Depends(require_permission(PermissionCode.INVITE_CODE_MANAGE)),
) -> dict:
    """创建邀请码，需要 invite_code:manage 权限。"""
    service = InviteCodeService()
    result = service.create(
        remaining=payload.remaining,
        expires_in_hours=payload.expires_in_hours,
        created_by=current_user.id,
        custom_code=payload.custom_code,
    )
    return success_response(result)


@router.get(
    "",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.INVITE_CODE_MANAGE))],
)
def list_invite_codes(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """分页列出邀请码，需要 invite_code:manage 权限。"""
    service = InviteCodeService()
    return success_response(service.list_page(page=page, page_size=page_size))
