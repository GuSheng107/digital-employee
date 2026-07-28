"""认证业务编排层：双 token 体系核心实现。

Token 为 opaque 字符串，状态完全存 Redis：
- ``{prefix}:access:{token}``  -> user_id      (TTL = access_token_ttl)
- ``{prefix}:refresh:{token}`` -> user_id      (TTL = refresh_token_ttl)
- ``{prefix}:pair:{refresh}``  -> access_token  (TTL = refresh_token_ttl)
- ``{prefix}:user:{uid}:tokens`` -> set[token]  (用户活跃 token 集合)

pair key 建立 refresh_token 与 access_token 的配对关系，使 refresh 时能
精确撤销对应的 access_token，兑现"refresh 一次性使用"的安全承诺。

不使用 JWT：所有状态在服务端，支持主动失效，避免客户端签名无法撤销的问题。
各服务可本地直连同一 Redis 验证 access_token，去中心化鉴权。
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from api_common import (
    DuplicateResourceError,
    InvalidCredentialsError,
    TokenInvalidError,
    UserDisabledError,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import get_vip_display
from app.core.redis_client import get_redis_client
from app.core.security import generate_token, hash_password, verify_password
from app.models.menu import Menu
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import MenuNode, TokenPair, UserInfo


class AuthService:
    """认证服务：登录、刷新、登出、当前用户信息。"""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._redis = get_redis_client()
        self._prefix = settings.token_redis_prefix
        self._access_ttl = settings.access_token_ttl_seconds
        self._refresh_ttl = settings.refresh_token_ttl_seconds

    def register(self, username: str, password: str, invite_code: str) -> TokenPair:
        """用户注册，校验邀请码，创建用户并签发双 token。

        Args:
            username: 用户名（4-64 字符）。
            password: 明文密码（8-128 字符）。
            invite_code: 邀请码。

        Returns:
            双 token 响应对象。

        Raises:
            InvalidCredentialsError: 邀请码无效或已用完。
            DuplicateResourceError: 用户名已存在。
        """
        # 1. 校验邀请码
        invite_key = f"invite_code:{invite_code}"
        invite_data = self._redis.get_json(invite_key)
        if invite_data is None:
            raise InvalidCredentialsError(message="邀请码无效或已用完")
        remaining = int(invite_data.get("remaining", 0))
        if remaining <= 0:
            raise InvalidCredentialsError(message="邀请码无效或已用完")

        # 2. 校验用户名唯一
        existing = self._fetch_user_by_username(username)
        if existing is not None:
            raise DuplicateResourceError(message="用户名已存在")

        # 3. 创建用户
        password_hash = hash_password(password)
        user = User(
            username=username,
            password_hash=password_hash,
            status=1,
        )
        self._session.add(user)
        self._session.flush()  # 获取 user.id

        # 4. 分配 user 角色（普通用户）
        user_role = self._session.scalars(
            select(Role).where(Role.code == "user", Role.deleted_at.is_(None))
        ).first()
        if user_role is not None:
            user.roles.append(user_role)
        self._session.commit()

        # 5. 邀请码 remaining -1，按剩余过期时间回写 TTL
        invite_data["remaining"] = remaining - 1
        if invite_data["remaining"] <= 0:
            self._redis.delete(invite_key)
        else:
            expires_at = invite_data.get("expires_at")
            if expires_at:
                ttl = int(expires_at - time.time())
                if ttl > 0:
                    self._redis.set_json(invite_key, invite_data, ttl_seconds=ttl)
                else:
                    self._redis.delete(invite_key)
            else:
                self._redis.set_json(invite_key, invite_data, ttl_seconds=604800)

        # 6. 签发双 token
        return self._issue_token_pair(user.id)

    def login(self, username: str, password: str, client_ip: str | None = None) -> TokenPair:
        """用户名密码登录，签发双 token。

        Args:
            username: 用户名。
            password: 明文密码。
            client_ip: 客户端 IP，用于记录 last_login_ip。

        Returns:
            双 token 响应对象。

        Raises:
            InvalidCredentialsError: 用户名不存在或密码错误。
            UserDisabledError: 用户已被禁用。
        """
        user = self._fetch_user_by_username(username)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError(message="用户名或密码错误")
        if user.status != 1:
            raise UserDisabledError(message="用户已被禁用")

        self._update_login_state(user, client_ip)
        return self._issue_token_pair(user.id)

    def refresh(self, refresh_token: str) -> TokenPair:
        """用 refresh_token 换取新的双 token。

        安全承诺（一次性使用）：
        1. 旧 refresh_token 立即失效。
        2. 通过 pair key 精确撤销对应的 access_token，避免旧 access 在
           剩余 TTL 内继续可用。
        3. 校验用户状态，被禁用用户的 refresh_token 不得换发新 token。

        Args:
            refresh_token: 上一次签发的 refresh_token。

        Returns:
            新的双 token 响应对象。

        Raises:
            TokenInvalidError: refresh_token 无效或已过期。
            UserDisabledError: 用户已被禁用。
        """
        user_id = self._read_token("refresh", refresh_token)
        if user_id is None:
            raise TokenInvalidError(message="refresh_token 无效或已过期")

        # 校验用户状态：被禁用/删除的用户不得刷新，防止禁用后仍可换 token
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise TokenInvalidError(message="用户不存在或已删除")
        if user.status != 1:
            raise UserDisabledError(message="用户已被禁用")

        # 一次性使用：撤销旧 refresh + 配对 access + pair 关联
        paired_access = self._redis.get(self._pair_key(refresh_token))
        self._revoke_token("refresh", refresh_token, user_id=user_id)
        if paired_access is not None:
            self._revoke_token("access", paired_access, user_id=user_id)
        self._redis.delete(self._pair_key(refresh_token))

        return self._issue_token_pair(user_id)

    def logout(self, access_token: str, refresh_token: str | None = None) -> None:
        """登出，撤销 access_token 与可选的 refresh_token 及其配对关系。

        Args:
            access_token: 当前 access_token，必填。
            refresh_token: 当前 refresh_token，可选。
        """
        user_id = self._read_token("access", access_token)
        self._revoke_token("access", access_token, user_id=user_id)
        if refresh_token:
            self._revoke_token("refresh", refresh_token, user_id=user_id)
            self._redis.delete(self._pair_key(refresh_token))

    def get_current_user(self, access_token: str) -> UserInfo:
        """根据 access_token 获取当前登录用户信息。

        Args:
            access_token: 请求头携带的 access_token。

        Returns:
            用户信息（含角色 code 列表、权限 code 列表与可见菜单树）。

        Raises:
            TokenInvalidError: access_token 无效或已过期。
        """
        user_id = self._read_token("access", access_token)
        if user_id is None:
            raise TokenInvalidError(message="access_token 无效或已过期")

        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise TokenInvalidError(message="用户不存在或已删除")
        if user.status != 1:
            raise UserDisabledError(message="用户已被禁用")

        role_codes = [r.code for r in user.roles]
        # 权限组语义：权限/菜单从用户独立集合读取（角色作为模板已复制到用户）
        permission_codes = [p.code for p in user.permissions]
        # super_admin（超管）和 manager（管理员）默认拥有所有可见菜单，
        # 无需依赖 user_menus 快照——新增菜单后立即可见，便于维护。
        # 其他用户仍走 user.menus 独立集合（由角色模板复制而来）。
        admin_roles = {"super_admin", "manager"}
        menu_set: dict[int, Menu] = {}
        if admin_roles.intersection(role_codes):
            admin_menus = self._session.scalars(
                select(Menu).where(
                    Menu.deleted_at.is_(None),
                    Menu.menu_type != 3,
                    Menu.visible.is_(True),
                )
            ).all()
            menu_set = {m.id: m for m in admin_menus}
        else:
            for menu in user.menus:
                if menu.deleted_at is None and menu.menu_type != 3 and menu.visible:
                    menu_set[menu.id] = menu
        menu_nodes = [
            MenuNode(
                id=menu.id,
                parent_id=menu.parent_id,
                menu_type=menu.menu_type,
                title=menu.title,
                path=menu.path,
                component=menu.component,
                icon=menu.icon,
                permission=menu.permission,
                sort=menu.sort,
                visible=menu.visible,
            )
            for menu in menu_set.values()
        ]
        menu_tree = self._build_menu_tree(menu_nodes)
        return UserInfo(
            id=user.id,
            username=user.username,
            nickname=user.nickname,
            email=user.email,
            phone=user.phone,
            avatar_url=user.avatar_url,
            is_vip=user.is_vip,
            vip_level=user.vip_level,
            vip_level_display=get_vip_display(user.vip_level),
            status=user.status,
            roles=role_codes,
            permissions=permission_codes,
            menus=menu_tree,
        )

    # ---------- 内部工具方法 ----------

    def _build_menu_tree(self, nodes: list[MenuNode]) -> list[MenuNode]:
        """将扁平菜单列表构建为树形结构。

        parent_id 为 0 或指向不存在节点时视为根节点；其余节点挂载到
        对应父节点的 children 列表。全部节点（含子节点）按 sort 升序排序。

        Args:
            nodes: 扁平的菜单节点列表。

        Returns:
            根节点列表，每个根节点的 children 已按 sort 排序。
        """
        node_map = {n.id: n for n in nodes}
        roots: list[MenuNode] = []
        for node in nodes:
            if node.parent_id == 0 or node.parent_id not in node_map:
                roots.append(node)
            else:
                node_map[node.parent_id].children.append(node)
        roots.sort(key=lambda n: n.sort)
        for node in nodes:
            node.children.sort(key=lambda n: n.sort)
        return roots

    def _fetch_user_by_username(self, username: str) -> User | None:
        """按用户名查询未软删的用户。"""
        stmt = select(User).where(
            User.username == username,
            User.deleted_at.is_(None),
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def _update_login_state(self, user: User, client_ip: str | None) -> None:
        """更新用户最近登录时间与 IP。"""
        user.last_login_at = datetime.now(UTC)
        if client_ip:
            user.last_login_ip = client_ip
        self._session.commit()

    def _issue_token_pair(self, user_id: int) -> TokenPair:
        """签发一对新的 access/refresh token 并写入 Redis。

        同时建立 pair 关联（refresh_token -> access_token），使 refresh 时
        能精确撤销对应的 access_token。
        """
        access_token = generate_token()
        refresh_token = generate_token()

        self._redis.set(
            self._access_key(access_token),
            str(user_id),
            ttl_seconds=self._access_ttl,
        )
        self._redis.set(
            self._refresh_key(refresh_token),
            str(user_id),
            ttl_seconds=self._refresh_ttl,
        )
        # pair key：refresh_token -> access_token，TTL 跟随 refresh
        self._redis.set(
            self._pair_key(refresh_token),
            access_token,
            ttl_seconds=self._refresh_ttl,
        )
        # 维护用户活跃 token 集合（用于全量登出），TTL 跟随 refresh
        user_tokens_key = self._user_tokens_key(user_id)
        self._redis.sadd(user_tokens_key, access_token, refresh_token)
        self._redis.expire(user_tokens_key, self._refresh_ttl)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_in=self._access_ttl,
            refresh_expires_in=self._refresh_ttl,
            user_id=user_id,
        )

    def _read_token(self, kind: str, token: str) -> int | None:
        """读取 token 对应的 user_id，不存在返回 None。"""
        key = self._token_key(kind, token)
        raw = self._redis.get(key)
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _revoke_token(
        self, kind: str, token: str, *, user_id: int | None = None
    ) -> None:
        """撤销单个 token，并从用户活跃 token 集合中移除。

        Args:
            kind: token 类型（access/refresh）。
            token: token 字符串。
            user_id: 若已知用户 ID，则同步清理用户 token 集合中的对应记录。
        """
        key = self._token_key(kind, token)
        self._redis.delete(key)
        if user_id is not None:
            self._redis.srem(self._user_tokens_key(user_id), token)

    def _access_key(self, token: str) -> str:
        return f"{self._prefix}:access:{token}"

    def _refresh_key(self, token: str) -> str:
        return f"{self._prefix}:refresh:{token}"

    def _pair_key(self, refresh_token: str) -> str:
        """refresh_token 与 access_token 的配对关系 key。"""
        return f"{self._prefix}:pair:{refresh_token}"

    def _token_key(self, kind: str, token: str) -> str:
        """根据 kind（access/refresh）拼接 Redis key。"""
        if kind == "access":
            return self._access_key(token)
        if kind == "refresh":
            return self._refresh_key(token)
        raise ValueError(f"unknown token kind: {kind}")

    def _user_tokens_key(self, user_id: int) -> str:
        return f"{self._prefix}:user:{user_id}:tokens"
