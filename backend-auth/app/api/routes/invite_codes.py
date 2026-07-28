"""邀请码管理路由（需要 invite_code:manage 权限）。

- POST /invite-codes：创建邀请码。
- GET  /invite-codes：列出所有邀请码。

两个端点都通过 access_token 鉴权（不挂载 API Key），并要求当前用户
持有 ``invite_code:manage`` 权限码（admin 角色自动放行）。
"""

from __future__ import annotations

from api_common import ApiResponse, success_response
from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.schemas.auth import UserInfo
from app.schemas.invite_code import CreateInviteCodeRequest
from app.services.invite_code_service import InviteCodeService

router = APIRouter()


@router.post("", response_model=ApiResponse)
def create_invite_code(
    payload: CreateInviteCodeRequest,
    current_user: UserInfo = Depends(require_admin),
) -> dict:
    """创建邀请码，需要 invite_code:manage 权限。"""
    service = InviteCodeService()
    result = service.create(
        remaining=payload.remaining,
        expires_in_hours=payload.expires_in_hours,
        created_by=current_user.id,
    )
    return success_response(result)


@router.get(
    "",
    response_model=ApiResponse,
    dependencies=[Depends(require_admin)],
)
def list_invite_codes() -> dict:
    """列出所有邀请码，需要 invite_code:manage 权限。"""
    service = InviteCodeService()
    return success_response(service.list_all())
