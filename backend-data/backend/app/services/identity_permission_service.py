"""backend-data 内部权限目录查询与维护服务。"""

from __future__ import annotations

from api_common import ConflictError, DuplicateResourceError, ResourceNotFoundError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.menu import Menu
from app.models.permission import Permission, RolePermission
from app.models.user_permission import UserPermission


class PermissionService:
    """提供管理端可选择的规范权限码目录，并支持动态新增/删除权限码。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_permissions(self) -> list[dict]:
        """按模块、权限码排序返回全部权限定义。"""
        permissions = self._session.scalars(
            select(Permission).order_by(
                Permission.module,
                Permission.code,
                Permission.id,
            )
        ).all()
        return [
            {
                "id": permission.id,
                "code": permission.code,
                "name": permission.name,
                "description": permission.description,
                "module": permission.module,
            }
            for permission in permissions
        ]

    def create_permission(
        self,
        *,
        code: str,
        name: str,
        description: str = "",
        module: str | None = None,
    ) -> dict:
        """新建权限码。

        动态新建的权限码仅用于菜单可见性与角色授权，不参与后端接口鉴权
        （接口鉴权仍依赖 ``auth-utils`` 的静态 ``PermissionCode`` 枚举）。

        Raises:
            DuplicateResourceError: 权限码已存在。
        """
        existing = self._session.scalar(
            select(Permission.id).where(Permission.code == code).limit(1)
        )
        if existing is not None:
            raise DuplicateResourceError(message=f"权限码已存在：{code}")

        permission = Permission(
            code=code,
            name=name,
            description=description,
            module=module,
        )
        self._session.add(permission)
        self._session.flush()
        result = self._to_dict(permission)
        self._session.commit()
        return result

    def delete_permission(self, *, permission_id: int) -> dict:
        """物理删除权限码。

        删除前校验该权限码未被任何角色、用户或菜单引用，否则拒绝删除，
        避免遗留悬空引用导致菜单/授权失效。

        Raises:
            ResourceNotFoundError: 权限码不存在。
        """
        permission = self._session.get(Permission, permission_id)
        if permission is None:
            raise ResourceNotFoundError(message="权限码不存在")

        # 校验无角色引用
        role_ref = self._session.scalar(
            select(RolePermission.role_id)
            .where(RolePermission.permission_id == permission_id)
            .limit(1)
        )
        if role_ref is not None:
            raise ConflictError(message="该权限码已被角色引用，请先解除关联")

        # 校验无用户运行时权限快照引用
        user_ref = self._session.scalar(
            select(UserPermission.user_id)
            .where(UserPermission.permission_id == permission_id)
            .limit(1)
        )
        if user_ref is not None:
            raise ConflictError(message="该权限码已被用户引用，请先解除关联")

        # 校验无菜单 permission 字段引用（menus.permission 为普通字符串列，无外键约束）
        menu_ref = self._session.scalar(
            select(Menu.id)
            .where(
                Menu.permission == permission.code,
                Menu.deleted_at.is_(None),
            )
            .limit(1)
        )
        if menu_ref is not None:
            raise ConflictError(message="该权限码已被菜单引用，请先解除关联")

        self._session.delete(permission)
        self._session.commit()
        return {"permission_id": permission_id, "deleted": True}

    @staticmethod
    def _to_dict(permission: Permission) -> dict:
        return {
            "id": permission.id,
            "code": permission.code,
            "name": permission.name,
            "description": permission.description,
            "module": permission.module,
        }
