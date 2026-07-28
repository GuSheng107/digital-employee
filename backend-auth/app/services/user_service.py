"""用户管理服务：列表、创建、分配角色、更新个人信息、用户权限/菜单管理。"""

from __future__ import annotations

from api_common import DuplicateResourceError, ResourceNotFoundError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import get_vip_display
from app.core.security import hash_password
from app.models.menu import Menu
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User


class UserService:
    """用户管理服务。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_users(self, *, page: int = 1, page_size: int = 20) -> dict:
        """分页查询用户列表。

        过滤掉 admin 角色用户（管理员不可见），防止误操作管理员账号。
        """
        # 过滤条件：未软删 且 不拥有 super_admin/manager 角色（管理员不可见）
        base_filter = (
            User.deleted_at.is_(None),
            ~User.roles.any(Role.code.in_(["super_admin", "manager"])),
        )

        # 查询总数
        total = self._session.scalar(
            select(func.count(User.id)).where(*base_filter)
        ) or 0

        # 分页查询
        offset = (page - 1) * page_size
        users = self._session.scalars(
            select(User)
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
                    "roles": roles,
                    "last_login_at": user.last_login_at.isoformat()
                    if user.last_login_at
                    else None,
                    "created_at": user.created_at.isoformat()
                    if user.created_at
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
        password: str,
        nickname: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        role_codes: list[str] | None = None,
    ) -> dict:
        """管理员创建用户（不需要邀请码）。"""
        # 校验用户名唯一
        existing = self._session.scalars(
            select(User).where(
                User.username == username, User.deleted_at.is_(None)
            )
        ).first()
        if existing is not None:
            raise DuplicateResourceError(message="用户名已存在")

        # 创建用户
        user = User(
            username=username,
            password_hash=hash_password(password),
            nickname=nickname,
            email=email,
            phone=phone,
            status=1,
        )
        self._session.add(user)
        self._session.flush()

        # 分配角色
        if role_codes:
            roles = self._session.scalars(
                select(Role).where(
                    Role.code.in_(role_codes), Role.deleted_at.is_(None)
                )
            ).all()
            user.roles.extend(roles)

        self._session.commit()

        return {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "roles": [r.code for r in user.roles],
        }

    def assign_roles(self, *, user_id: int, role_codes: list[str]) -> dict:
        """分配用户角色（覆盖式）。

        权限组语义：角色作为模板，分配时把角色的权限点与菜单复制到用户的
        独立集合（user_permissions / user_menus）。之后用户可独立增删自己
        的权限/菜单，角色变更不再影响已分配用户。

        合并策略：
        - 先收集当前用户已有的权限/菜单 id 集合
        - 把新角色集合的权限/菜单 union 进去
        - 若用户原本有角色但新分配中移除了某角色，则该角色独有的权限/菜单
          仍保留在用户独立集合中（避免误删用户后续手动添加的权限）
        - 简化处理：分配角色时只新增不删除（用户手动增删走单独接口）
        """
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ResourceNotFoundError(message="用户不存在")

        # 查询目标角色
        roles = (
            self._session.scalars(
                select(Role).where(
                    Role.code.in_(role_codes), Role.deleted_at.is_(None)
                )
            ).all()
            if role_codes
            else []
        )

        # 覆盖式更新角色
        user.roles = list(roles)

        # 把所有分配角色的权限点和菜单 union 到用户独立集合（只增不减）
        existing_perm_ids = {p.id for p in user.permissions}
        existing_menu_ids = {m.id for m in user.menus}

        new_perm_ids: set[int] = set()
        new_menu_ids: set[int] = set()
        for role in roles:
            for perm in role.permissions:
                new_perm_ids.add(perm.id)
            for menu in role.menus:
                if menu.deleted_at is None:
                    new_menu_ids.add(menu.id)

        # 批量查询需要新增的 Permission / Menu 对象
        to_add_perm_ids = new_perm_ids - existing_perm_ids
        to_add_menu_ids = new_menu_ids - existing_menu_ids

        if to_add_perm_ids:
            perms = self._session.scalars(
                select(Permission).where(Permission.id.in_(to_add_perm_ids))
            ).all()
            user.permissions = list(user.permissions) + list(perms)

        if to_add_menu_ids:
            menus = self._session.scalars(
                select(Menu).where(Menu.id.in_(to_add_menu_ids))
            ).all()
            user.menus = list(user.menus) + list(menus)

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

    def assign_user_menus(self, *, user_id: int, menu_ids: list[int]) -> dict:
        """分配用户独立菜单（覆盖式）。

        与角色菜单解耦：用户菜单为角色模板复制后的副本，可个性化增删。
        """
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ResourceNotFoundError(message="用户不存在")

        menus: list[Menu] = []
        if menu_ids:
            menus = list(
                self._session.scalars(
                    select(Menu).where(Menu.id.in_(menu_ids), Menu.deleted_at.is_(None))
                ).all()
            )

        user.menus = menus
        self._session.commit()

        return {
            "user_id": user_id,
            "menu_ids": [m.id for m in user.menus if m.deleted_at is None],
        }

    def get_user_permissions(self, *, user_id: int) -> list[dict]:
        """获取用户独立权限列表。"""
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ResourceNotFoundError(message="用户不存在")
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

    def assign_user_permissions(self, *, user_id: int, permission_ids: list[int]) -> dict:
        """分配用户独立权限（覆盖式）。"""
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ResourceNotFoundError(message="用户不存在")

        perms: list[Permission] = []
        if permission_ids:
            perms = list(
                self._session.scalars(
                    select(Permission).where(Permission.id.in_(permission_ids))
                ).all()
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
        """上传用户头像到 Minio（通过 backend-data）。

        Args:
            user_id: 用户 ID
            filename: 原始文件名
            data: 文件二进制内容
            content_type: MIME 类型

        Returns:
            {"avatar_url": str}
        """
        from data_client import get_data_client

        # 存储路径前缀：avatars/{user_id}
        prefix = f"avatars/{user_id}"

        # 调用 backend-data 上传
        result = get_data_client().upload_file(
            prefix=prefix,
            filename=filename,
            data=data,
            content_type=content_type,
        )

        avatar_url = result.get("file_url", "")

        # 更新用户 avatar_url
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ResourceNotFoundError(message="用户不存在")
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
        password: str | None = None,
    ) -> dict:
        """更新当前用户个人信息。

        ``password`` 非空时同步更新密码哈希（用于个人信息页自助修改密码）。
        """
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ResourceNotFoundError(message="用户不存在")

        if nickname is not None:
            user.nickname = nickname
        if email is not None:
            user.email = email
        if phone is not None:
            user.phone = phone
        if password:
            user.password_hash = hash_password(password)

        self._session.commit()

        return {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "email": user.email,
            "phone": user.phone,
            "avatar_url": user.avatar_url,
        }

    def reset_user_password(self, *, user_id: int, new_password: str) -> dict:
        """管理员重置指定用户的密码（覆盖式，不校验旧密码）。"""
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise ResourceNotFoundError(message="用户不存在")
        user.password_hash = hash_password(new_password)
        self._session.commit()
        return {"user_id": user_id, "username": user.username}
