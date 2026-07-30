"""角色管理服务：列表、创建、更新、删除、菜单分配。"""

from __future__ import annotations

from datetime import UTC, datetime

from api_common import (
    ConflictError,
    DuplicateResourceError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationError,
)
from auth_utils import (
    PROTECTED_ROLE_CODES,
    ROLE_CODE_MANAGER,
    ROLE_CODE_SUPER_ADMIN,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.menu import Menu
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User
from app.services.identity_access_sync_service import (
    IdentityAccessSyncService,
    UserAccessExtras,
)


class RoleService:
    """角色管理服务。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_roles(self) -> list[dict]:
        """列出可管理角色（含关联的菜单 ID 列表）。

        ``super_admin`` 是系统最高权限身份，不属于可分配、可维护的业务角色，
        因此不会出现在角色管理列表中。
        """
        roles = self._session.scalars(
            select(Role)
            .where(
                Role.deleted_at.is_(None),
                Role.code.not_in(PROTECTED_ROLE_CODES),
            )
            .order_by(Role.id)
        ).all()

        items = []
        for role in roles:
            # 防御性过滤：即使仓储测试桩或后续查询调整未应用 SQL 条件，
            # 最高权限角色也不能进入管理端响应。
            if role.code in PROTECTED_ROLE_CODES:
                continue
            menu_ids = [m.id for m in role.menus if m.deleted_at is None]
            permission_codes = sorted(
                permission.code for permission in role.permissions
            )
            items.append(
                {
                    "id": role.id,
                    "code": role.code,
                    "name": role.name,
                    "description": role.description,
                    "is_builtin": role.is_builtin,
                    "menu_ids": menu_ids,
                    "permission_codes": permission_codes,
                }
            )
        return items

    def create_role(
        self,
        *,
        code: str,
        name: str,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
        description: str = "",
        menu_ids: list[int] | None = None,
    ) -> dict:
        """创建自定义角色。

        Args:
            code: 角色代码，需唯一。
            name: 角色名称。
            description: 角色描述。
            menu_ids: 关联菜单 ID 列表。

        Raises:
            DuplicateResourceError: 角色代码已存在。
        """
        if code in PROTECTED_ROLE_CODES:
            raise PermissionDeniedError(message="该角色代码由系统保留")
        existing = self._session.scalars(
            select(Role).where(Role.code == code, Role.deleted_at.is_(None))
        ).first()
        if existing is not None:
            raise DuplicateResourceError(message="角色代码已存在")

        role = Role(
            code=code,
            name=name,
            description=description,
            is_builtin=False,
        )
        self._session.add(role)
        self._session.flush()

        if menu_ids:
            menus = self._load_menus(menu_ids)
            self._ensure_permissions_within_actor_scope(
                menus=menus,
                actor_role_codes=actor_role_codes,
                actor_permission_codes=actor_permission_codes,
            )
            role.menus = menus
            self._sync_role_permissions_from_menus(role, menus)

        self._session.commit()

        return {
            "id": role.id,
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "is_builtin": role.is_builtin,
            "menu_ids": [m.id for m in role.menus if m.deleted_at is None],
            "permission_codes": sorted(
                permission.code for permission in role.permissions
            ),
        }

    def update_role(
        self,
        *,
        role_id: int,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
        name: str | None = None,
        description: str | None = None,
        menu_ids: list[int] | None = None,
    ) -> dict:
        """更新角色信息。

        内置角色（is_builtin=True）不允许修改名称，仅允许修改描述与菜单。

        Raises:
            ResourceNotFoundError: 角色不存在。
            PermissionDeniedError: 尝试修改内置角色名称。
        """
        role = self._get_manageable_role(role_id)
        self._ensure_actor_can_manage_role(
            role=role,
            actor_role_codes=actor_role_codes,
        )

        if name is not None:
            if role.is_builtin:
                raise PermissionDeniedError(message="内置角色不允许修改名称")
            role.name = name
        if description is not None:
            role.description = description
        if menu_ids is not None:
            affected_users = self._capture_affected_users(role)
            menus = self._load_menus(menu_ids) if menu_ids else []
            self._ensure_permissions_within_actor_scope(
                menus=menus,
                actor_role_codes=actor_role_codes,
                actor_permission_codes=actor_permission_codes,
            )
            role.menus = menus
            self._sync_role_permissions_from_menus(role, menus)
            self._sync_affected_users(affected_users)

        self._session.commit()

        return {
            "id": role.id,
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "is_builtin": role.is_builtin,
            "menu_ids": [m.id for m in role.menus if m.deleted_at is None],
            "permission_codes": sorted(
                permission.code for permission in role.permissions
            ),
        }

    def delete_role(
        self,
        *,
        role_id: int,
        actor_role_codes: list[str],
    ) -> dict:
        """删除角色（软删除）。

        内置角色不可删除。如果角色仍关联用户，则阻止删除。

        Raises:
            ResourceNotFoundError: 角色不存在。
            PermissionDeniedError: 内置角色不可删除或角色仍关联用户。
        """
        role = self._get_manageable_role(role_id)
        self._ensure_actor_can_manage_role(
            role=role,
            actor_role_codes=actor_role_codes,
        )

        if role.is_builtin:
            raise PermissionDeniedError(message="内置角色不可删除")

        # 检查是否仍有关联用户
        if role.users:
            user_count = len([u for u in role.users if u.deleted_at is None])
            if user_count > 0:
                raise ConflictError(
                    message=f"角色仍关联 {user_count} 个用户，请先解除关联后再删除"
                )

        # 软删除：清除关联菜单后标记删除
        role.menus = []
        role.deleted_at = datetime.now(UTC)
        self._session.commit()

        return {"role_id": role_id, "deleted": True}

    def get_role_menus(self, *, role_id: int) -> list[dict]:
        """获取角色关联的菜单列表。"""
        role = self._get_manageable_role(role_id)

        menus = [m for m in role.menus if m.deleted_at is None]
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

    def assign_menus(
        self,
        *,
        role_id: int,
        menu_ids: list[int],
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> dict:
        """分配角色菜单（覆盖式）。"""
        role = self._get_manageable_role(role_id)
        self._ensure_actor_can_manage_role(
            role=role,
            actor_role_codes=actor_role_codes,
        )

        affected_users = self._capture_affected_users(role)

        # 查询目标菜单
        menus: list[Menu] = []
        if menu_ids:
            menus = self._load_menus(menu_ids)
        self._ensure_permissions_within_actor_scope(
            menus=menus,
            actor_role_codes=actor_role_codes,
            actor_permission_codes=actor_permission_codes,
        )

        # 覆盖式更新
        role.menus = menus
        self._sync_role_permissions_from_menus(role, menus)
        self._sync_affected_users(affected_users)
        self._session.commit()

        return {
            "role_id": role_id,
            "menu_ids": [m.id for m in role.menus],
            "permission_codes": sorted(
                permission.code for permission in role.permissions
            ),
        }

    def _load_menus(self, menu_ids: list[int]) -> list[Menu]:
        """按 ID 加载未删除菜单，并拒绝不存在的菜单 ID。"""
        menus = list(
            self._session.scalars(
                select(Menu).where(
                    Menu.id.in_(menu_ids),
                    Menu.deleted_at.is_(None),
                )
            ).all()
        )
        found_ids = {menu.id for menu in menus}
        missing_ids = sorted(set(menu_ids) - found_ids)
        if missing_ids:
            missing_text = ", ".join(str(menu_id) for menu_id in missing_ids)
            raise ValidationError(message=f"菜单不存在：{missing_text}")
        return menus

    def _sync_role_permissions_from_menus(
        self,
        role: Role,
        menus: list[Menu],
    ) -> None:
        """用所选菜单的权限码同步角色权限。

        菜单入口与接口权限共用一套权限码，避免出现“看得到页面但接口 403”
        或“接口可调用但页面入口不可见”的双轨配置。
        """
        permission_codes = {menu.permission for menu in menus if menu.permission}
        if not permission_codes:
            role.permissions = []
            return
        permissions = list(
            self._session.scalars(
                select(Permission).where(Permission.code.in_(permission_codes))
            ).all()
        )
        found_codes = {permission.code for permission in permissions}
        missing_codes = sorted(permission_codes - found_codes)
        if missing_codes:
            raise ValidationError(
                message=f"菜单引用了未定义权限码：{', '.join(missing_codes)}"
            )
        role.permissions = permissions

    def _capture_affected_users(
        self,
        role: Role,
    ) -> list[tuple[User, UserAccessExtras]]:
        """在修改角色模板前保存关联用户的独立授权。"""
        access_sync = IdentityAccessSyncService(self._session)
        return [
            (user, access_sync.capture_extras(user))
            for user in role.users
            if user.deleted_at is None
        ]

    def _sync_affected_users(
        self,
        affected_users: list[tuple[User, UserAccessExtras]],
    ) -> None:
        """把修改后的角色权限并集同步到关联用户。"""
        access_sync = IdentityAccessSyncService(self._session)
        for user, extras in affected_users:
            access_sync.sync_from_roles(user, extras=extras)

    def _get_manageable_role(self, role_id: int) -> Role:
        """读取可由通用角色管理接口维护的角色。

        超级管理员角色属于平台安全边界；即使调用方知道数据库 ID，也不能
        通过通用接口读取其菜单、修改或删除。
        """
        role = self._session.get(Role, role_id)
        if role is None or role.deleted_at is not None:
            raise ResourceNotFoundError(message="角色不存在")
        if role.code in PROTECTED_ROLE_CODES:
            raise PermissionDeniedError(message="超级管理员角色不允许维护")
        return role

    @staticmethod
    def _ensure_actor_can_manage_role(
        *,
        role: Role,
        actor_role_codes: list[str],
    ) -> None:
        """限制 manager 内置角色只能由超级管理员维护。"""
        if (
            role.code == ROLE_CODE_MANAGER
            and ROLE_CODE_SUPER_ADMIN not in actor_role_codes
        ):
            raise PermissionDeniedError(message="仅超级管理员可以维护管理员角色")

    @staticmethod
    def _ensure_permissions_within_actor_scope(
        *,
        menus: list[Menu],
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> None:
        """禁止普通管理员通过角色模板授予超出自身范围的权限。"""
        if ROLE_CODE_SUPER_ADMIN in actor_role_codes:
            return
        permission_codes = {
            menu.permission
            for menu in menus
            if menu.permission is not None
        }
        unauthorized_codes = sorted(permission_codes - set(actor_permission_codes))
        if unauthorized_codes:
            raise PermissionDeniedError(
                message=f"不能授予超出自身范围的权限：{', '.join(unauthorized_codes)}"
            )
