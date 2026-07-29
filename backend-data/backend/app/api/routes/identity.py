"""backend-auth 专用的身份域数据接口。

路由只接受服务 API Key，不接受浏览器 Bearer token，避免 backend-data 与
backend-auth 形成循环鉴权。所有 PostgreSQL、Redis、MinIO 操作在这里完成。
"""

from __future__ import annotations

from api_common import ValidationError
from auth_utils import AVATAR_MAX_SIZE_BYTES
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_core_db_session
from app.schemas.common import ApiResponse
from app.schemas.identity import (
    AccessTokenIdentityRequest,
    CompleteLoginRequest,
    DeleteIdentityUserRequest,
    CreateIdentityInviteCodeRequest,
    CreateIdentityMenuRequest,
    CreateIdentityRoleRequest,
    CreateIdentityUserRequest,
    IdsRequest,
    LogoutIdentitySessionRequest,
    RefreshIdentitySessionRequest,
    RegisterIdentityRequest,
    ResetIdentityPasswordRequest,
    RoleCodesRequest,
    UpdateIdentityMenuRequest,
    UpdateIdentityProfileRequest,
    UpdateIdentityRoleRequest,
    UpdateIdentityStatusRequest,
    UpdateIdentityVipRequest,
    UsernameIdentityRequest,
)
from app.services.identity_auth_service import IdentityAuthService
from app.services.identity_invite_code_service import InviteCodeService
from app.services.identity_menu_service import MenuService
from app.services.identity_permission_service import PermissionService
from app.services.identity_role_service import RoleService
from app.services.identity_user_service import UserService
from app.utils.response import success_response

router = APIRouter()


@router.post("/auth/register", response_model=ApiResponse)
def register_identity(
    payload: RegisterIdentityRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """创建注册用户并写入初始会话。"""
    result = IdentityAuthService(session).register(**payload.model_dump())
    return success_response(result)


@router.post("/auth/credentials", response_model=ApiResponse)
def get_credentials(
    payload: UsernameIdentityRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """读取 backend-auth 校验密码所需的内部凭据。"""
    return success_response(
        IdentityAuthService(session).get_credentials(payload.username)
    )


@router.post("/auth/complete-login", response_model=ApiResponse)
def complete_login(
    payload: CompleteLoginRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """更新登录审计并落实单会话策略。"""
    return success_response(
        IdentityAuthService(session).complete_login(**payload.model_dump())
    )


@router.post("/auth/refresh", response_model=ApiResponse)
def refresh_session(
    payload: RefreshIdentitySessionRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """一次性轮换 refresh/access token。"""
    return success_response(
        IdentityAuthService(session).refresh_session(**payload.model_dump())
    )


@router.post("/auth/logout", response_model=ApiResponse)
def logout(
    payload: LogoutIdentitySessionRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """撤销当前会话。"""
    IdentityAuthService(session).logout(**payload.model_dump())
    return success_response()


@router.post("/auth/context", response_model=ApiResponse)
def get_current_user_context(
    payload: AccessTokenIdentityRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """读取 access token 对应的可信用户上下文。"""
    return success_response(
        IdentityAuthService(session).get_current_user_context(payload.access_token)
    )


@router.get("/users", response_model=ApiResponse)
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_core_db_session),
) -> dict:
    """分页查询可管理用户。"""
    return success_response(
        UserService(session).list_users(page=page, page_size=page_size)
    )


@router.post("/users", response_model=ApiResponse)
def create_user(
    payload: CreateIdentityUserRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """创建用户。"""
    return success_response(UserService(session).create_user(**payload.model_dump()))


@router.put("/users/{user_id}/profile", response_model=ApiResponse)
def update_profile(
    user_id: int,
    payload: UpdateIdentityProfileRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """更新用户个人资料。"""
    return success_response(
        UserService(session).update_profile(
            user_id=user_id,
            **payload.model_dump(),
        )
    )


@router.post("/users/{user_id}/avatar", response_model=ApiResponse)
def upload_avatar(
    user_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_core_db_session),
) -> dict:
    """上传头像并保存用户头像 URL。"""
    content = file.file.read()
    if len(content) > AVATAR_MAX_SIZE_BYTES:
        raise ValidationError(message="头像文件不能超过 3MB")
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise ValidationError(message="仅支持上传图片文件")
    return success_response(
        UserService(session).upload_avatar(
            user_id=user_id,
            filename=file.filename or "avatar",
            data=content,
            content_type=content_type,
        )
    )


@router.put("/users/{user_id}/roles", response_model=ApiResponse)
def assign_user_roles(
    user_id: int,
    payload: RoleCodesRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """覆盖用户角色并同步模板权限。"""
    return success_response(
        UserService(session).assign_roles(
            user_id=user_id,
            role_codes=payload.role_codes,
        )
    )


@router.put("/users/{user_id}/password", response_model=ApiResponse)
def reset_user_password(
    user_id: int,
    payload: ResetIdentityPasswordRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """保存管理员重置密码并设置强制改密标志。"""
    return success_response(
        UserService(session).reset_user_password(
            user_id=user_id,
            password_hash=payload.password_hash,
        )
    )


@router.put("/users/{user_id}/vip", response_model=ApiResponse)
def update_user_vip(
    user_id: int,
    payload: UpdateIdentityVipRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """更新用户 VIP 设置。"""
    return success_response(
        UserService(session).update_vip(
            user_id=user_id,
            **payload.model_dump(),
        )
    )


@router.put("/users/{user_id}/status", response_model=ApiResponse)
def update_user_status(
    user_id: int,
    payload: UpdateIdentityStatusRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """启用或停用用户。"""
    return success_response(
        UserService(session).update_status(
            user_id=user_id,
            status=payload.status,
        )
    )


@router.delete("/users/{user_id}", response_model=ApiResponse)
def delete_user(
    user_id: int,
    payload: DeleteIdentityUserRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """按管理员层级软删除用户并撤销会话。"""
    return success_response(
        UserService(session).delete_user(
            user_id=user_id,
            actor_user_id=payload.actor_user_id,
            actor_role_codes=payload.actor_role_codes,
        )
    )


@router.get("/users/{user_id}/menus", response_model=ApiResponse)
def get_user_menus(
    user_id: int,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """读取用户独立菜单。"""
    return success_response(UserService(session).get_user_menus(user_id=user_id))


@router.put("/users/{user_id}/menus", response_model=ApiResponse)
def assign_user_menus(
    user_id: int,
    payload: IdsRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """覆盖用户独立菜单。"""
    return success_response(
        UserService(session).assign_user_menus(
            user_id=user_id,
            menu_ids=payload.ids,
        )
    )


@router.get("/users/{user_id}/permissions", response_model=ApiResponse)
def get_user_permissions(
    user_id: int,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """读取用户独立权限。"""
    return success_response(UserService(session).get_user_permissions(user_id=user_id))


@router.put("/users/{user_id}/permissions", response_model=ApiResponse)
def assign_user_permissions(
    user_id: int,
    payload: IdsRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """覆盖用户独立权限。"""
    return success_response(
        UserService(session).assign_user_permissions(
            user_id=user_id,
            permission_ids=payload.ids,
        )
    )


@router.get("/roles", response_model=ApiResponse)
def list_roles(
    session: Session = Depends(get_core_db_session),
) -> dict:
    """读取可管理角色。"""
    return success_response(RoleService(session).list_roles())


@router.post("/roles", response_model=ApiResponse)
def create_role(
    payload: CreateIdentityRoleRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """创建角色。"""
    return success_response(RoleService(session).create_role(**payload.model_dump()))


@router.put("/roles/{role_id}", response_model=ApiResponse)
def update_role(
    role_id: int,
    payload: UpdateIdentityRoleRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """更新角色。"""
    return success_response(
        RoleService(session).update_role(
            role_id=role_id,
            **payload.model_dump(),
        )
    )


@router.delete("/roles/{role_id}", response_model=ApiResponse)
def delete_role(
    role_id: int,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """软删除角色。"""
    return success_response(RoleService(session).delete_role(role_id=role_id))


@router.get("/roles/{role_id}/menus", response_model=ApiResponse)
def get_role_menus(
    role_id: int,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """读取角色菜单。"""
    return success_response(RoleService(session).get_role_menus(role_id=role_id))


@router.put("/roles/{role_id}/menus", response_model=ApiResponse)
def assign_role_menus(
    role_id: int,
    payload: IdsRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """覆盖角色菜单。"""
    return success_response(
        RoleService(session).assign_menus(
            role_id=role_id,
            menu_ids=payload.ids,
        )
    )


@router.get("/menus", response_model=ApiResponse)
def list_menus(
    session: Session = Depends(get_core_db_session),
) -> dict:
    """读取菜单目录。"""
    return success_response(MenuService(session).list_menus())


@router.post("/menus", response_model=ApiResponse)
def create_menu(
    payload: CreateIdentityMenuRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """创建菜单。"""
    return success_response(MenuService(session).create_menu(**payload.model_dump()))


@router.put("/menus/{menu_id}", response_model=ApiResponse)
def update_menu(
    menu_id: int,
    payload: UpdateIdentityMenuRequest,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """更新菜单。"""
    return success_response(
        MenuService(session).update_menu(
            menu_id=menu_id,
            updates=payload.model_dump(exclude_unset=True),
        )
    )


@router.delete("/menus/{menu_id}", response_model=ApiResponse)
def delete_menu(
    menu_id: int,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """软删除菜单。"""
    return success_response(MenuService(session).delete_menu(menu_id=menu_id))


@router.get("/permissions", response_model=ApiResponse)
def list_permissions(
    session: Session = Depends(get_core_db_session),
) -> dict:
    """读取权限码目录。"""
    return success_response(PermissionService(session).list_permissions())


@router.post("/invite-codes", response_model=ApiResponse)
def create_invite_code(
    payload: CreateIdentityInviteCodeRequest,
) -> dict:
    """创建随机或自定义邀请码。"""
    return success_response(
        InviteCodeService().create(
            remaining=payload.remaining,
            expires_in_hours=payload.expires_in_hours,
            created_by=payload.created_by,
            custom_code=(
                payload.custom_code.strip().upper() if payload.custom_code else None
            ),
        )
    )


@router.get("/invite-codes", response_model=ApiResponse)
def list_invite_codes() -> dict:
    """读取有效与失效邀请码。"""
    return success_response(InviteCodeService().list_all())
