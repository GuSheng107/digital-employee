"""认证业务编排层。

backend-auth 负责密码哈希校验与 token 生成；所有 PostgreSQL/Redis 读写
通过 backend-share 的 data-client 交由 backend-data 执行。
"""

from __future__ import annotations

import hashlib

from api_common import InvalidCredentialsError, UserDisabledError
from data_client import DataClient, get_data_client

from app.core.config import settings
from app.core.security import generate_token, hash_password, verify_password
from app.schemas.auth import MenuNode, TokenPair, UserInfo


class AuthService:
    """登录、注册、刷新、登出与用户上下文编排。"""

    def __init__(self, data_client: DataClient | None = None) -> None:
        self._data = data_client or get_data_client()

    def register(
        self,
        *,
        username: str,
        password: str,
        email: str,
        phone: str,
        invite_code: str,
        client_ip: str | None = None,
    ) -> TokenPair:
        """注册用户并签发双 token。"""
        self._consume_rate_limit(
            bucket="register",
            identifier=f"{client_ip or 'unknown'}:{username.casefold()}",
            limit=settings.register_rate_limit,
            window_seconds=settings.register_rate_window_seconds,
        )
        access_token = generate_token()
        refresh_token = generate_token()
        metadata = self._data.register_identity(
            username=username,
            password_hash=hash_password(password),
            email=email,
            phone=phone,
            invite_code=invite_code,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        return self._build_token_pair(
            access_token=access_token,
            refresh_token=refresh_token,
            metadata=metadata,
        )

    def login(
        self,
        username: str,
        password: str,
        client_ip: str | None = None,
    ) -> TokenPair:
        """校验凭据并落实同账号单会话策略。"""
        self._consume_rate_limit(
            bucket="login",
            identifier=f"{client_ip or 'unknown'}:{username.casefold()}",
            limit=settings.login_rate_limit,
            window_seconds=settings.login_rate_window_seconds,
        )
        credentials = self._data.get_credentials(username)
        if (
            credentials is None
            or not isinstance(credentials.get("password_hash"), str)
            or not verify_password(password, credentials["password_hash"])
        ):
            raise InvalidCredentialsError(message="用户名或密码错误")
        if credentials.get("status") != 1:
            raise UserDisabledError(message="用户已被禁用")
        user_id = credentials.get("id")
        if not isinstance(user_id, int):
            raise InvalidCredentialsError(message="用户名或密码错误")

        access_token = generate_token()
        refresh_token = generate_token()
        metadata = self._data.complete_login(
            user_id=user_id,
            client_ip=client_ip,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        return self._build_token_pair(
            access_token=access_token,
            refresh_token=refresh_token,
            metadata=metadata,
        )

    def refresh(self, refresh_token: str) -> TokenPair:
        """一次性轮换 refresh/access token。"""
        access_token = generate_token()
        new_refresh_token = generate_token()
        metadata = self._data.refresh_identity_session(
            refresh_token=refresh_token,
            new_access_token=access_token,
            new_refresh_token=new_refresh_token,
        )
        return self._build_token_pair(
            access_token=access_token,
            refresh_token=new_refresh_token,
            metadata=metadata,
        )

    def logout(
        self,
        access_token: str,
        refresh_token: str | None = None,
    ) -> None:
        """撤销 access token 与可选 refresh token。"""
        self._data.logout_identity_session(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def get_current_user(self, access_token: str) -> UserInfo:
        """读取可信用户上下文并构建菜单树。"""
        payload = self._data.get_identity_context(access_token)
        raw_menus = payload.get("menus")
        menu_nodes = (
            [MenuNode.model_validate(item) for item in raw_menus]
            if isinstance(raw_menus, list)
            else []
        )
        payload["menus"] = self._build_menu_tree(menu_nodes)
        return UserInfo.model_validate(payload)

    def get_authorization_context(self, access_token: str) -> UserInfo:
        """读取不包含菜单树的跨服务最小鉴权上下文。"""
        payload = self._data.get_identity_context(
            access_token,
            include_menus=False,
        )
        payload["menus"] = []
        return UserInfo.model_validate(payload)

    @staticmethod
    def _build_menu_tree(nodes: list[MenuNode]) -> list[MenuNode]:
        """将扁平菜单按 parent_id 构建为树。"""
        node_map = {node.id: node for node in nodes}
        roots: list[MenuNode] = []
        for node in nodes:
            if node.parent_id == 0 or node.parent_id not in node_map:
                roots.append(node)
            else:
                node_map[node.parent_id].children.append(node)
        roots.sort(key=lambda node: node.sort)
        for node in nodes:
            node.children.sort(key=lambda child: child.sort)
        return roots

    @staticmethod
    def _build_token_pair(
        *,
        access_token: str,
        refresh_token: str,
        metadata: dict,
    ) -> TokenPair:
        """把 backend-data 返回的 TTL 元数据组装为公开 token 响应。"""
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_in=int(metadata["access_expires_in"]),
            refresh_expires_in=int(metadata["refresh_expires_in"]),
            user_id=int(metadata["user_id"]),
            must_change_password=bool(metadata.get("must_change_password", False)),
        )

    def _consume_rate_limit(
        self,
        *,
        bucket: str,
        identifier: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        """委托 backend-data 消费认证限流计数。"""
        identifier_hash = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
        self._data.consume_identity_rate_limit(
            bucket=bucket,
            identifier_hash=identifier_hash,
            limit=limit,
            window_seconds=window_seconds,
        )
