"""认证业务编排层。

backend-auth 负责密码哈希校验与 token 生成；所有 PostgreSQL/Redis 读写
通过 backend-share 的 data-client 交由 backend-data 执行。
"""

from __future__ import annotations

import hashlib

from api_common import InvalidCredentialsError, UserDisabledError
from data_client import (
    DataClient,
    IdentityRateLimitItem,
    IdentityRateLimitResetItem,
    get_data_client,
)

from app.core.config import settings
from app.core.rate_limit import AuthRateLimitBucket
from app.core.security import generate_token, hash_password, verify_password
from app.schemas.auth import CaptchaChallenge, MenuNode, TokenPair, UserInfo


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
        captcha_id: str,
        captcha_answer: str,
        client_ip: str | None = None,
    ) -> TokenPair:
        """注册用户并签发双 token。"""
        normalized_ip = client_ip or "unknown"
        self._consume_rate_limits(
            [
                (
                    AuthRateLimitBucket.REGISTER_IP,
                    normalized_ip,
                    settings.register_ip_rate_limit,
                    settings.register_ip_rate_window_seconds,
                ),
                (
                    AuthRateLimitBucket.REGISTER_IDENTITY,
                    (f"{username.casefold()}:{email.casefold()}:" f"{phone.casefold()}"),
                    settings.register_identity_rate_limit,
                    settings.register_identity_rate_window_seconds,
                ),
            ]
        )
        self._data.verify_identity_captcha(
            captcha_id=captcha_id,
            captcha_answer=captcha_answer,
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
        captcha_id: str,
        captcha_answer: str,
        client_ip: str | None = None,
    ) -> TokenPair:
        """校验凭据并落实同账号单会话策略。"""
        normalized_ip = client_ip or "unknown"
        normalized_account = username.casefold()
        self._consume_rate_limits(
            [
                (
                    AuthRateLimitBucket.LOGIN_IP,
                    normalized_ip,
                    settings.login_ip_rate_limit,
                    settings.login_ip_rate_window_seconds,
                ),
                (
                    AuthRateLimitBucket.LOGIN_PAIR,
                    f"{normalized_ip}:{normalized_account}",
                    settings.login_pair_rate_limit,
                    settings.login_pair_rate_window_seconds,
                ),
                (
                    AuthRateLimitBucket.LOGIN_ACCOUNT,
                    normalized_account,
                    settings.login_account_rate_limit,
                    settings.login_account_rate_window_seconds,
                ),
            ]
        )
        self._data.verify_identity_captcha(
            captcha_id=captcha_id,
            captcha_answer=captcha_answer,
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
        self._reset_rate_limits(
            [
                (
                    AuthRateLimitBucket.LOGIN_PAIR,
                    f"{normalized_ip}:{normalized_account}",
                ),
                (AuthRateLimitBucket.LOGIN_ACCOUNT, normalized_account),
            ]
        )
        return self._build_token_pair(
            access_token=access_token,
            refresh_token=refresh_token,
            metadata=metadata,
        )

    def create_captcha(self, client_ip: str | None = None) -> CaptchaChallenge:
        """按客户端 IP 限流后生成算术图片验证码。"""
        self._consume_rate_limit(
            bucket=AuthRateLimitBucket.CAPTCHA_IP,
            identifier=client_ip or "unknown",
            limit=settings.captcha_ip_rate_limit,
            window_seconds=settings.captcha_ip_rate_window_seconds,
        )
        return CaptchaChallenge.model_validate(self._data.create_identity_captcha())

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

    _MAX_MENU_DEPTH = 50

    @staticmethod
    def _build_menu_tree(nodes: list[MenuNode]) -> list[MenuNode]:
        """将扁平菜单按 parent_id 构建为树，最大深度 50 防止环路。"""
        node_map = {node.id: node for node in nodes}
        roots: list[MenuNode] = []
        for node in nodes:
            if node.parent_id == 0 or node.parent_id not in node_map:
                roots.append(node)
            else:
                node_map[node.parent_id].children.append(node)
        roots.sort(key=lambda node: node.sort)

        # 按深度排序子节点，并做环路防护
        for node in nodes:
            node.children.sort(key=lambda child: child.sort)
            ancestry: set[int] = set()
            current: MenuNode | None = node_map.get(node.parent_id) if node.parent_id else None
            depth = 0
            while current is not None:
                if current.id in ancestry or depth > AuthService._MAX_MENU_DEPTH:
                    # 检测到环路或超深，切断引用并提升为根节点
                    current.children = [
                        c for c in current.children if c.id != node.id
                    ]
                    node.parent_id = 0
                    if node not in roots:
                        roots.append(node)
                    break
                ancestry.add(current.id)
                depth += 1
                current = (
                    node_map.get(current.parent_id)
                    if current.parent_id
                    else None
                )
        roots.sort(key=lambda root: root.sort)
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
        bucket: AuthRateLimitBucket,
        identifier: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        """委托 backend-data 消费认证限流计数。"""
        identifier_hash = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
        self._data.consume_identity_rate_limit(
            bucket=bucket.value,
            identifier_hash=identifier_hash,
            limit=limit,
            window_seconds=window_seconds,
        )

    def _consume_rate_limits(
        self,
        entries: list[tuple[AuthRateLimitBucket, str, int, int]],
    ) -> None:
        """在一次 backend-data 调用中消费多个认证限流桶。"""
        rate_limit_items: list[IdentityRateLimitItem] = [
            {
                "bucket": bucket.value,
                "identifier_hash": hashlib.sha256(identifier.encode("utf-8")).hexdigest(),
                "limit": limit,
                "window_seconds": window_seconds,
            }
            for bucket, identifier, limit, window_seconds in entries
        ]
        self._data.consume_identity_rate_limits(rate_limit_items)

    def _reset_rate_limit(
        self,
        *,
        bucket: AuthRateLimitBucket,
        identifier: str,
    ) -> None:
        """成功登录后清除账号相关失败窗口，IP 总量窗口继续保留。"""
        identifier_hash = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
        self._data.reset_identity_rate_limit(
            bucket=bucket.value,
            identifier_hash=identifier_hash,
        )

    def _reset_rate_limits(
        self,
        entries: list[tuple[AuthRateLimitBucket, str]],
    ) -> None:
        """在一次 backend-data 调用中清除多个认证限流桶。"""
        reset_items: list[IdentityRateLimitResetItem] = [
            {
                "bucket": bucket.value,
                "identifier_hash": hashlib.sha256(identifier.encode("utf-8")).hexdigest(),
            }
            for bucket, identifier in entries
        ]
        self._data.reset_identity_rate_limits(reset_items)
