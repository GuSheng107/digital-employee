"""backend-data 内部用户数据服务。

用户、角色、权限、头像元数据和强制改密标志的实际读写全部收敛在本服务。
backend-auth 只通过共享 data-client 调用这些能力。
"""

from __future__ import annotations

from datetime import UTC, datetime

from api_common import (
    DuplicateResourceError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError,
)
from auth_utils import (
    BUSINESS_VIP_LEVELS,
    PROTECTED_ROLE_CODES,
    ROLE_CODE_MANAGER,
    ROLE_CODE_SUPER_ADMIN,
    VipLevel,
    get_vip_display,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.menu import Menu
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User
from app.services.identity_session_service import IdentitySessionService
from app.services.storage_service import StorageService


class UserService:
    """用户管理服务。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_users(self, *, page: int = 1, page_size: int = 20) -> dict:
        """分页查询用户列表。

        仅隐藏最高权限账号。普通管理员（VIP66）属于可维护账号，应在用户
        管理中展示；超级管理员（VIP99）则始终隔离在通用管理接口之外。
        """
        # 过滤条件：未软删且不拥有受保护的 super_admin 角色。
        base_filter = (
            User.deleted_at.is_(None),
            ~User.roles.any(Role.code.in_(PROTECTED_ROLE_CODES)),
        )

        # 查询总数
        total = (
            self._session.scalar(select(func.count(User.id)).where(*base_filter)) or 0
        )

        # 分页查询
        offset = (page - 1) * page_size
        users = self._session.scalars(
            select(User)
            .options(selectinload(User.roles))
            .where(*base_filter)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(page_size)
        ).all()

        items = []
        for user in users:
            roles = [r.code for r in user.roles]
            items.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "nickname": user.nickname,
                    "email": user.email,
                    "phone": user.phone,
                    "avatar_url": user.avatar_url,
                    "status": user.status,
                    "is_vip": user.is_vip,
                    "vip_level": user.vip_level,
                    "vip_level_display": get_vip_display(user.vip_level),
                    "vip_expires_at": user.vip_expires_at.isoformat()
                    if user.vip_expires_at
                    else None,
                    "roles": roles,
                    "last_login_at": user.last_login_at.isoformat()
                    if user.last_login_at
                    else None,
                    "last_login_ip": user.last_login_ip,
                    "created_at": user.created_at.isoformat()
                    if user.created_at
                    else None,
                    "updated_at": user.updated_at.isoformat()
                    if user.updated_at
                    else None,
                }
            )

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }

    def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        nickname: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        role_codes: list[str] | None = None,
        actor_user_id: int,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
        is_vip: bool = False,
        vip_level: int | None = None,
        vip_expires_at: datetime | None = None,
    ) -> dict:
        """管理员创建用户（不需要邀请码）。"""
        requested_role_codes = set(role_codes or [])
        if PROTECTED_ROLE_CODES.intersection(requested_role_codes):
            raise PermissionDeniedError(
                message="不能通过用户管理接口分配超级管理员角色"
            )
        self._ensure_manager_assignment_allowed(
            role_codes=requested_role_codes,
            actor_role_codes=actor_role_codes,
        )
        if ROLE_CODE_MANAGER in requested_role_codes and is_vip:
            raise ValidationError(message="管理员身份不能同时配置业务 VIP")

        self._ensure_unique_username(username)
        self._ensure_unique_email(email)
        normalized_is_vip, normalized_level, normalized_expires_at = (
            self._normalize_vip_settings(
                role_codes=requested_role_codes,
                is_vip=is_vip,
                vip_level=vip_level,
                vip_expires_at=vip_expires_at,
            )
        )

        user = User(
            username=username,
            password_hash=password_hash,
            nickname=nickname,
            email=email,
            phone=phone,
            status=1,
            is_vip=normalized_is_vip,
            vip_level=normalized_level,
            vip_expires_at=normalized_expires_at,
        )
        self._session.add(user)
        self._session.flush()

        if requested_role_codes:
            roles = self._load_roles(requested_role_codes)
            self._ensure_permissions_within_actor_scope(
                permission_codes={
                    permission.code
                    for role in roles
                    for permission in role.permissions
                },
                actor_role_codes=actor_role_codes,
                actor_permission_codes=actor_permission_codes,
            )
            user.roles.extend(roles)

        self._session.commit()

        return {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "roles": [r.code for r in user.roles],
            "is_vip": user.is_vip,
            "vip_level": user.vip_level,
            "vip_expires_at": user.vip_expires_at.isoformat()
            if user.vip_expires_at
            else None,
        }

    def _ensure_unique_username(
        self,
        username: str,
        *,
        exclude_user_id: int | None = None,
    ) -> None:
        """校验未删除用户中的用户名唯一性。"""
        statement = select(User.id).where(
            User.username == username,
            User.deleted_at.is_(None),
        )
        if exclude_user_id is not None:
            statement = statement.where(User.id != exclude_user_id)
        if self._session.scalar(statement.limit(1)) is not None:
            raise DuplicateResourceError(message="用户名已存在")

    def _ensure_unique_email(
        self,
        email: str | None,
        *,
        exclude_user_id: int | None = None,
    ) -> None:
        """校验非空邮箱唯一性。"""
        if not email:
            return
        statement = select(User.id).where(
            User.email == email,
            User.deleted_at.is_(None),
        )
        if exclude_user_id is not None:
            statement = statement.where(User.id != exclude_user_id)
        if self._session.scalar(statement.limit(1)) is not None:
            raise DuplicateResourceError(message="邮箱已被其他用户使用")

    def assign_roles(
        self,
        *,
        user_id: int,
        role_codes: list[str],
        actor_role_codes: list[str],
        actor_user_id: int,
        actor_permission_codes: list[str],
    ) -> dict:
        """分配用户角色（覆盖式）。

        角色作为权限模板。角色覆盖后，用户权限与菜单同步覆盖为新角色集合
        的模板内容，避免移除角色后遗留已降级权限；后续仍可通过独立接口
        在操作者权限范围内调整。
        """
        if PROTECTED_ROLE_CODES.intersection(role_codes):
            raise PermissionDeniedError(
                message="不能通过用户管理接口分配超级管理员角色"
            )
        self._ensure_manager_assignment_allowed(
            role_codes=role_codes,
            actor_role_codes=actor_role_codes,
        )

        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ResourceNotFoundError(message="用户不存在")
        self._ensure_not_protected_account(user)
        self._ensure_actor_can_manage_user(
            user=user,
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
        )

        # 查询目标角色
        roles = self._load_roles(set(role_codes)) if role_codes else []
        self._ensure_permissions_within_actor_scope(
            permission_codes={
                permission.code
                for role in roles
                for permission in role.permissions
            },
            actor_role_codes=actor_role_codes,
            actor_permission_codes=actor_permission_codes,
        )

        # 覆盖式更新角色
        user.roles = list(roles)
        assigned_role_codes = {role.code for role in roles}
        if ROLE_CODE_MANAGER in assigned_role_codes:
            user.is_vip = True
            user.vip_level = VipLevel.MANAGER
            user.vip_expires_at = None
        elif user.vip_level == VipLevel.MANAGER:
            user.is_vip = False
            user.vip_level = VipLevel.NORMAL
            user.vip_expires_at = None

        new_perm_ids: set[int] = set()
        new_menu_ids: set[int] = set()
        for role in roles:
            for perm in role.permissions:
                new_perm_ids.add(perm.id)
            for menu in role.menus:
                if menu.deleted_at is None:
                    new_menu_ids.add(menu.id)

        user.permissions = (
            list(
                self._session.scalars(
                    select(Permission).where(Permission.id.in_(new_perm_ids))
                ).all()
            )
            if new_perm_ids
            else []
        )
        user.menus = (
            list(
                self._session.scalars(
                    select(Menu).where(Menu.id.in_(new_menu_ids))
                ).all()
            )
            if new_menu_ids
            else []
        )

        self._session.commit()

        return {
            "user_id": user_id,
            "roles": [r.code for r in user.roles],
        }

    def get_user_menus(self, *, user_id: int) -> list[dict]:
        """获取用户独立菜单列表（含菜单完整字段，用于前端树展示）。"""
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ResourceNotFoundError(message="用户不存在")
        self._ensure_not_protected_account(user)
        menus = [m for m in user.menus if m.deleted_at is None]
        return [
            {
                "id": m.id,
                "parent_id": m.parent_id,
                "menu_type": m.menu_type,
                "title": m.title,
                "path": m.path,
                "icon": m.icon,
                "permission": m.permission,
                "sort": m.sort,
                "visible": m.visible,
            }
            for m in menus
        ]

    def assign_user_menus(
        self,
        *,
        user_id: int,
        menu_ids: list[int],
        actor_user_id: int,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> dict:
        """分配用户独立菜单（覆盖式）。

        与角色菜单解耦：用户菜单为角色模板复制后的副本，可个性化增删。
        """
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ResourceNotFoundError(message="用户不存在")
        self._ensure_not_protected_account(user)
        self._ensure_actor_can_manage_user(
            user=user,
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
        )

        menus: list[Menu] = []
        if menu_ids:
            menus = list(
                self._session.scalars(
                    select(Menu).where(Menu.id.in_(menu_ids), Menu.deleted_at.is_(None))
                ).all()
            )
            found_menu_ids = {menu.id for menu in menus}
            missing_menu_ids = sorted(set(menu_ids) - found_menu_ids)
            if missing_menu_ids:
                missing_text = ", ".join(str(menu_id) for menu_id in missing_menu_ids)
                raise ValidationError(message=f"菜单不存在：{missing_text}")

        permission_codes = {menu.permission for menu in menus if menu.permission}
        self._ensure_permissions_within_actor_scope(
            permission_codes=permission_codes,
            actor_role_codes=actor_role_codes,
            actor_permission_codes=actor_permission_codes,
        )
        permissions = (
            list(
                self._session.scalars(
                    select(Permission).where(Permission.code.in_(permission_codes))
                ).all()
            )
            if permission_codes
            else []
        )
        found_permission_codes = {permission.code for permission in permissions}
        missing_permission_codes = sorted(permission_codes - found_permission_codes)
        if missing_permission_codes:
            raise ValidationError(
                message=(
                    "菜单引用了未定义权限码：" f"{', '.join(missing_permission_codes)}"
                )
            )

        # 用户直接菜单与直接权限必须保持一致，避免出现“菜单已勾选但接口
        # 仍然 403”的双轨配置。角色权限仍通过角色关系动态参与最终并集。
        user.menus = menus
        user.permissions = permissions
        self._session.commit()

        return {
            "user_id": user_id,
            "menu_ids": [m.id for m in user.menus if m.deleted_at is None],
            "permission_codes": sorted(
                permission.code for permission in user.permissions
            ),
        }

    def get_user_permissions(self, *, user_id: int) -> list[dict]:
        """获取用户独立权限列表。"""
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ResourceNotFoundError(message="用户不存在")
        self._ensure_not_protected_account(user)
        return [
            {
                "id": p.id,
                "code": p.code,
                "name": p.name,
                "description": p.description,
                "module": p.module,
            }
            for p in user.permissions
        ]

    def assign_user_permissions(
        self,
        *,
        user_id: int,
        permission_ids: list[int],
        actor_user_id: int,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> dict:
        """分配用户独立权限（覆盖式）。"""
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ResourceNotFoundError(message="用户不存在")
        self._ensure_not_protected_account(user)
        self._ensure_actor_can_manage_user(
            user=user,
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
        )

        perms: list[Permission] = []
        if permission_ids:
            perms = list(
                self._session.scalars(
                    select(Permission).where(Permission.id.in_(permission_ids))
                ).all()
            )
            found_permission_ids = {permission.id for permission in perms}
            missing_permission_ids = sorted(set(permission_ids) - found_permission_ids)
            if missing_permission_ids:
                missing_text = ", ".join(
                    str(permission_id) for permission_id in missing_permission_ids
                )
                raise ValidationError(message=f"权限不存在：{missing_text}")
        self._ensure_permissions_within_actor_scope(
            permission_codes={permission.code for permission in perms},
            actor_role_codes=actor_role_codes,
            actor_permission_codes=actor_permission_codes,
        )

        user.permissions = perms
        self._session.commit()

        return {
            "user_id": user_id,
            "permission_ids": [p.id for p in user.permissions],
        }

    def upload_avatar(
        self,
        *,
        user_id: int,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> dict:
        """上传头像并保存 URL。

        Args:
            user_id: 用户 ID
            filename: 原始文件名
            data: 文件二进制内容
            content_type: MIME 类型

        Returns:
            {"avatar_url": str}
        """
        user = self._get_user(user_id)
        result = StorageService().upload_avatar(
            user_id=user_id,
            filename=filename,
            data=data,
            content_type=content_type,
        )
        avatar_url = str(result["file_url"])
        user.avatar_url = avatar_url
        self._session.commit()

        return {"avatar_url": avatar_url}

    def update_profile(
        self,
        *,
        user_id: int,
        nickname: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        password_hash: str | None = None,
    ) -> dict:
        """更新当前用户个人信息。

        ``password`` 非空时同步更新密码哈希（用于个人信息页自助修改密码）。
        """
        user = self._get_user(user_id)

        if nickname is not None:
            user.nickname = nickname
        if email is not None:
            self._ensure_unique_email(email, exclude_user_id=user_id)
            user.email = email
        if phone is not None:
            user.phone = phone
        if password_hash:
            user.password_hash = password_hash

        self._session.commit()
        if password_hash:
            IdentitySessionService().clear_password_change_required(user_id)

        return {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "email": user.email,
            "phone": user.phone,
            "avatar_url": user.avatar_url,
            "must_change_password": False
            if password_hash
            else IdentitySessionService().is_password_change_required(user_id),
        }

    def reset_user_password(
        self,
        *,
        user_id: int,
        password_hash: str,
        actor_user_id: int,
        actor_role_codes: list[str],
    ) -> dict:
        """管理员重置指定用户的密码（覆盖式，不校验旧密码）。"""
        user = self._get_user(user_id)
        self._ensure_not_protected_account(user)
        self._ensure_actor_can_manage_user(
            user=user,
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
        )
        user.password_hash = password_hash
        self._session.commit()
        session_service = IdentitySessionService()
        session_service.require_password_change(user_id)
        session_service.revoke_all_user_tokens(user_id)
        return {
            "user_id": user_id,
            "username": user.username,
            "must_change_password": True,
        }

    def update_vip(
        self,
        *,
        user_id: int,
        is_vip: bool,
        vip_level: int | None,
        vip_expires_at: datetime | None,
        actor_user_id: int,
        actor_role_codes: list[str],
    ) -> dict:
        """更新普通用户的 VIP 设置。"""
        user = self._get_user(user_id)
        self._ensure_not_protected_account(user)
        self._ensure_actor_can_manage_user(
            user=user,
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
        )
        role_codes = {role.code for role in user.roles}
        if ROLE_CODE_MANAGER in role_codes:
            raise ValidationError(message="管理员身份不能配置业务 VIP")
        normalized = self._normalize_vip_settings(
            role_codes=role_codes,
            is_vip=is_vip,
            vip_level=vip_level,
            vip_expires_at=vip_expires_at,
        )
        user.is_vip, user.vip_level, user.vip_expires_at = normalized
        self._session.commit()
        return {
            "user_id": user.id,
            "is_vip": user.is_vip,
            "vip_level": user.vip_level,
            "vip_level_display": get_vip_display(user.vip_level),
            "vip_expires_at": user.vip_expires_at.isoformat()
            if user.vip_expires_at
            else None,
        }

    def update_status(
        self,
        *,
        user_id: int,
        status: int,
        actor_user_id: int,
        actor_role_codes: list[str],
    ) -> dict:
        """启用或停用用户；停用时撤销全部会话。"""
        if status not in {0, 1}:
            raise ValidationError(message="用户状态仅支持启用或停用")
        user = self._get_user(user_id)
        self._ensure_not_protected_account(user)
        self._ensure_actor_can_manage_user(
            user=user,
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
        )
        user.status = status
        self._session.commit()
        if status == 0:
            IdentitySessionService().revoke_all_user_tokens(user_id)
        return {"user_id": user_id, "status": user.status}

    def delete_user(
        self,
        *,
        user_id: int,
        actor_user_id: int,
        actor_role_codes: list[str],
    ) -> dict:
        """按管理层级软删除用户并撤销全部会话。"""
        user = self._get_user(user_id)
        self._ensure_not_protected_account(user)
        if actor_user_id == user_id:
            raise PermissionDeniedError(message="不能删除当前登录账号")
        target_role_codes = {role.code for role in user.roles}
        if (
            ROLE_CODE_MANAGER in target_role_codes
            and ROLE_CODE_SUPER_ADMIN not in actor_role_codes
        ):
            raise PermissionDeniedError(message="仅超级管理员可以删除管理员账号")
        user.status = 0
        user.deleted_at = datetime.now(UTC)
        user.roles = []
        user.permissions = []
        user.menus = []
        self._session.commit()
        session_service = IdentitySessionService()
        session_service.revoke_all_user_tokens(user_id)
        session_service.clear_password_change_required(user_id)
        return {"user_id": user_id, "deleted": True}

    def _get_user(self, user_id: int) -> User:
        """读取未软删除用户。"""
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ResourceNotFoundError(message="用户不存在")
        return user

    def _load_roles(self, role_codes: set[str]) -> list[Role]:
        """加载有效角色，并拒绝未知或已删除的角色代码。"""
        if not role_codes:
            return []
        roles = list(
            self._session.scalars(
                select(Role).where(
                    Role.code.in_(role_codes),
                    Role.deleted_at.is_(None),
                )
            ).all()
        )
        found_codes = {role.code for role in roles}
        missing_codes = sorted(role_codes - found_codes)
        if missing_codes:
            raise ValidationError(message=f"角色不存在：{', '.join(missing_codes)}")
        return roles

    @staticmethod
    def _ensure_manager_assignment_allowed(
        *,
        role_codes: set[str] | list[str],
        actor_role_codes: list[str],
    ) -> None:
        """限制管理员角色只能由超级管理员授予。"""
        if (
            ROLE_CODE_MANAGER in role_codes
            and ROLE_CODE_SUPER_ADMIN not in actor_role_codes
        ):
            raise PermissionDeniedError(message="仅超级管理员可以分配管理员角色")

    @staticmethod
    def _ensure_not_protected_account(user: User) -> None:
        """禁止通用用户管理接口读取或修改超级管理员账号。"""
        role_codes = {role.code for role in user.roles}
        if PROTECTED_ROLE_CODES.intersection(role_codes):
            raise PermissionDeniedError(message="超级管理员账号不允许通过用户管理维护")

    @staticmethod
    def _ensure_actor_can_manage_user(
        *,
        user: User,
        actor_user_id: int,
        actor_role_codes: list[str],
    ) -> None:
        """禁止自维护，并限制普通管理员维护同级管理员。"""
        if actor_user_id == user.id:
            raise PermissionDeniedError(message="不能通过管理接口修改当前登录账号")
        target_role_codes = {role.code for role in user.roles}
        if (
            ROLE_CODE_MANAGER in target_role_codes
            and ROLE_CODE_SUPER_ADMIN not in actor_role_codes
        ):
            raise PermissionDeniedError(message="仅超级管理员可以维护管理员账号")

    @staticmethod
    def _ensure_permissions_within_actor_scope(
        *,
        permission_codes: set[str],
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> None:
        """禁止普通管理员授予超出自身范围的权限。"""
        if ROLE_CODE_SUPER_ADMIN in actor_role_codes:
            return
        unauthorized_codes = sorted(permission_codes - set(actor_permission_codes))
        if unauthorized_codes:
            raise PermissionDeniedError(
                message=f"不能授予超出自身范围的权限：{', '.join(unauthorized_codes)}"
            )

    def _normalize_vip_settings(
        self,
        *,
        role_codes: set[str],
        is_vip: bool,
        vip_level: int | None,
        vip_expires_at: datetime | None,
    ) -> tuple[bool, int, datetime | None]:
        """校验并归一化管理身份与业务 VIP 的互斥规则。"""
        if ROLE_CODE_MANAGER in role_codes:
            return True, int(VipLevel.MANAGER), None
        if not is_vip:
            return False, int(VipLevel.NORMAL), None
        try:
            level = VipLevel(vip_level)
        except (TypeError, ValueError) as exc:
            raise ValidationError(message="请选择有效的 VIP 等级") from exc
        if level not in BUSINESS_VIP_LEVELS:
            raise ValidationError(message="VIP 等级仅支持 VIP1-VIP9")
        if vip_expires_at is None:
            raise ValidationError(message="开启 VIP 后必须设置过期时间")
        normalized_expiry = (
            vip_expires_at.replace(tzinfo=UTC)
            if vip_expires_at.tzinfo is None
            else vip_expires_at.astimezone(UTC)
        )
        if normalized_expiry <= datetime.now(UTC):
            raise ValidationError(message="VIP 过期时间必须晚于当前时间")
        return True, int(level), normalized_expiry
