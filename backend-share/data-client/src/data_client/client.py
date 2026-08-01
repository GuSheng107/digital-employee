"""backend-data 服务的共享 HTTP 客户端。

其他后端只能通过本客户端访问 PostgreSQL、Redis、MinIO 等基础设施能力。
"""

from __future__ import annotations

import os
import threading
import gzip
import json
from datetime import datetime
from typing import Any, TypedDict

import httpx
from api_common import (
    ApiException,
    ConflictError,
    DependencyUnavailableError,
    DuplicateResourceError,
    ErrorCode,
    InvalidCredentialsError,
    PermissionDeniedError,
    RateLimitExceededError,
    ResourceNotFoundError,
    ServiceUnavailableError,
    SessionReplacedError,
    TokenExpiredError,
    TokenInvalidError,
    UserDisabledError,
    ValidationError,
)
from observability import propagation_headers

DEFAULT_BACKEND_DATA_BASE_URL = "http://127.0.0.1:8010"
DEFAULT_TIMEOUT_SECONDS = 30.0

# 业务错误码 → 异常子类映射。backend-data 抛出的具体异常经响应信封序列化后
# 只保留 code 字段；DataClient 据此重建对应子类，使调用方可按异常类型分支
# 处理（如迁移脚本捕获 DuplicateResourceError 做跳过而非视为失败）。
_CODE_TO_EXCEPTION: dict[str, type[ApiException]] = {
    cls.code: cls
    for cls in (
        ValidationError,
        InvalidCredentialsError,
        UserDisabledError,
        ResourceNotFoundError,
        DuplicateResourceError,
        ConflictError,
        TokenExpiredError,
        TokenInvalidError,
        SessionReplacedError,
        PermissionDeniedError,
        RateLimitExceededError,
        DependencyUnavailableError,
        ServiceUnavailableError,
    )
}


class IdentityRateLimitItem(TypedDict):
    """认证限流桶消费参数。"""

    bucket: str
    identifier_hash: str
    limit: int
    window_seconds: int


class IdentityRateLimitResetItem(TypedDict):
    """认证限流桶重置参数。"""

    bucket: str
    identifier_hash: str


class DataClient:
    """backend-data HTTP 客户端。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        configured_url = (
            base_url
            or os.environ.get("BACKEND_DATA_BASE_URL")
            or DEFAULT_BACKEND_DATA_BASE_URL
        )
        self._base_url = configured_url.rstrip("/")
        self._api_key = api_key or os.environ.get("BACKEND_DATA_API_KEY", "")
        self._timeout = timeout
        self._sync_client = httpx.Client(timeout=self._timeout)
        self._async_client: httpx.AsyncClient | None = None

    def register_identity(
        self,
        *,
        username: str,
        password_hash: str,
        email: str,
        phone: str,
        invite_code: str,
        access_token: str,
        refresh_token: str,
    ) -> dict[str, Any]:
        """创建注册用户并写入初始会话。"""
        return self._request_dict(
            "POST",
            "/api/v1/identity/auth/register",
            json={
                "username": username,
                "password_hash": password_hash,
                "email": email,
                "phone": phone,
                "invite_code": invite_code,
                "access_token": access_token,
                "refresh_token": refresh_token,
            },
        )

    def get_credentials(self, username: str) -> dict[str, Any] | None:
        """读取 backend-auth 内部使用的用户凭据。"""
        data = self._request(
            "POST",
            "/api/v1/identity/auth/credentials",
            json={"username": username},
        )
        if data is None:
            return None
        return self._ensure_dict(data)

    def complete_login(
        self,
        *,
        user_id: int,
        client_ip: str | None,
        access_token: str,
        refresh_token: str,
    ) -> dict[str, Any]:
        """完成登录审计与单会话 token 写入。"""
        return self._request_dict(
            "POST",
            "/api/v1/identity/auth/complete-login",
            json={
                "user_id": user_id,
                "client_ip": client_ip,
                "access_token": access_token,
                "refresh_token": refresh_token,
            },
        )

    def refresh_identity_session(
        self,
        *,
        refresh_token: str,
        new_access_token: str,
        new_refresh_token: str,
    ) -> dict[str, Any]:
        """轮换一次性 refresh token。"""
        return self._request_dict(
            "POST",
            "/api/v1/identity/auth/refresh",
            json={
                "refresh_token": refresh_token,
                "new_access_token": new_access_token,
                "new_refresh_token": new_refresh_token,
            },
        )

    def logout_identity_session(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
    ) -> None:
        """撤销当前会话。"""
        self._request(
            "POST",
            "/api/v1/identity/auth/logout",
            json={
                "access_token": access_token,
                "refresh_token": refresh_token,
            },
        )

    def get_identity_context(
        self,
        access_token: str,
        *,
        include_menus: bool = True,
    ) -> dict[str, Any]:
        """读取 access token 对应的可信用户上下文。"""
        return self._request_dict(
            "POST",
            "/api/v1/identity/auth/context",
            json={
                "access_token": access_token,
                "include_menus": include_menus,
            },
        )

    def consume_identity_rate_limit(
        self,
        *,
        bucket: str,
        identifier_hash: str,
        limit: int,
        window_seconds: int,
    ) -> dict[str, Any]:
        """通过 backend-data 消费认证接口限流计数。"""
        return self._request_dict(
            "POST",
            "/api/v1/identity/auth/rate-limit/consume",
            json={
                "bucket": bucket,
                "identifier_hash": identifier_hash,
                "limit": limit,
                "window_seconds": window_seconds,
            },
        )

    def consume_identity_rate_limits(
        self,
        items: list[IdentityRateLimitItem],
    ) -> list[dict[str, Any]]:
        """通过一次 backend-data 调用消费多个认证限流桶。"""
        return self._request_list(
            "POST",
            "/api/v1/identity/auth/rate-limit/consume-many",
            json={"items": items},
        )

    def list_users(self, *, page: int, page_size: int) -> dict[str, Any]:
        """分页读取可管理用户。"""
        return self._request_dict(
            "GET",
            "/api/v1/identity/users",
            params={"page": page, "page_size": page_size},
        )

    def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        nickname: str | None,
        email: str | None,
        phone: str | None,
        role_codes: list[str],
        actor_user_id: int,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
        is_vip: bool,
        vip_level: int | None,
        vip_expires_at: datetime | None,
    ) -> dict[str, Any]:
        """创建用户。"""
        return self._request_dict(
            "POST",
            "/api/v1/identity/users",
            json={
                "username": username,
                "password_hash": password_hash,
                "nickname": nickname,
                "email": email,
                "phone": phone,
                "role_codes": role_codes,
                "actor_user_id": actor_user_id,
                "actor_role_codes": actor_role_codes,
                "actor_permission_codes": actor_permission_codes,
                "is_vip": is_vip,
                "vip_level": vip_level,
                "vip_expires_at": (
                    vip_expires_at.isoformat() if vip_expires_at else None
                ),
            },
        )

    def update_profile(
        self,
        *,
        user_id: int,
        nickname: str | None,
        email: str | None,
        phone: str | None,
        password_hash: str | None,
    ) -> dict[str, Any]:
        """更新个人资料。"""
        return self._request_dict(
            "POST",
            f"/api/v1/identity/users/{user_id}/profile",
            json={
                "nickname": nickname,
                "email": email,
                "phone": phone,
                "password_hash": password_hash,
            },
        )

    def upload_avatar(
        self,
        *,
        user_id: int,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> dict[str, Any]:
        """上传头像并保存用户头像 URL。"""
        return self._request_dict(
            "POST",
            f"/api/v1/identity/users/{user_id}/avatar",
            files={"file": (filename, data, content_type)},
        )

    def assign_user_roles(
        self,
        *,
        user_id: int,
        role_codes: list[str],
        actor_user_id: int,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> dict[str, Any]:
        """覆盖用户角色。"""
        return self._request_dict(
            "POST",
            f"/api/v1/identity/users/{user_id}/roles",
            json={
                "role_codes": role_codes,
                "actor_user_id": actor_user_id,
                "actor_role_codes": actor_role_codes,
                "actor_permission_codes": actor_permission_codes,
            },
        )

    def reset_user_password(
        self,
        *,
        user_id: int,
        password_hash: str,
        actor_user_id: int,
        actor_role_codes: list[str],
    ) -> dict[str, Any]:
        """保存管理员重置后的密码哈希。"""
        return self._request_dict(
            "POST",
            f"/api/v1/identity/users/{user_id}/password",
            json={
                "password_hash": password_hash,
                "actor_user_id": actor_user_id,
                "actor_role_codes": actor_role_codes,
            },
        )

    def update_user_vip(
        self,
        *,
        user_id: int,
        is_vip: bool,
        vip_level: int | None,
        vip_expires_at: datetime | None,
        actor_user_id: int,
        actor_role_codes: list[str],
    ) -> dict[str, Any]:
        """更新 VIP 设置。"""
        return self._request_dict(
            "POST",
            f"/api/v1/identity/users/{user_id}/vip",
            json={
                "is_vip": is_vip,
                "vip_level": vip_level,
                "vip_expires_at": (
                    vip_expires_at.isoformat() if vip_expires_at else None
                ),
                "actor_user_id": actor_user_id,
                "actor_role_codes": actor_role_codes,
            },
        )

    def update_user_status(
        self,
        *,
        user_id: int,
        status: int,
        actor_user_id: int,
        actor_role_codes: list[str],
    ) -> dict[str, Any]:
        """启用或停用用户。"""
        return self._request_dict(
            "POST",
            f"/api/v1/identity/users/{user_id}/status",
            json={
                "status": status,
                "actor_user_id": actor_user_id,
                "actor_role_codes": actor_role_codes,
            },
        )

    def delete_user(
        self,
        *,
        user_id: int,
        actor_user_id: int,
        actor_role_codes: list[str],
    ) -> dict[str, Any]:
        """按可信操作者层级软删除用户。"""
        return self._request_dict(
            "DELETE",
            f"/api/v1/identity/users/{user_id}",
            json={
                "actor_user_id": actor_user_id,
                "actor_role_codes": actor_role_codes,
            },
        )

    def get_user_menus(self, user_id: int) -> list[dict[str, Any]]:
        """读取用户独立菜单。"""
        return self._request_list(
            "GET",
            f"/api/v1/identity/users/{user_id}/menus",
        )

    def assign_user_menus(
        self,
        *,
        user_id: int,
        menu_ids: list[int],
        actor_user_id: int,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> dict[str, Any]:
        """覆盖用户独立菜单。"""
        return self._request_dict(
            "POST",
            f"/api/v1/identity/users/{user_id}/menus",
            json={
                "ids": menu_ids,
                "actor_user_id": actor_user_id,
                "actor_role_codes": actor_role_codes,
                "actor_permission_codes": actor_permission_codes,
            },
        )

    def get_user_permissions(
        self,
        user_id: int,
    ) -> list[dict[str, Any]]:
        """读取用户独立权限。"""
        return self._request_list(
            "GET",
            f"/api/v1/identity/users/{user_id}/permissions",
        )

    def assign_user_permissions(
        self,
        *,
        user_id: int,
        permission_ids: list[int],
        actor_user_id: int,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> dict[str, Any]:
        """覆盖用户独立权限。"""
        return self._request_dict(
            "POST",
            f"/api/v1/identity/users/{user_id}/permissions",
            json={
                "ids": permission_ids,
                "actor_user_id": actor_user_id,
                "actor_role_codes": actor_role_codes,
                "actor_permission_codes": actor_permission_codes,
            },
        )

    def list_roles(self) -> list[dict[str, Any]]:
        """读取可管理角色。"""
        return self._request_list("GET", "/api/v1/identity/roles")

    def create_role(
        self,
        *,
        code: str,
        name: str,
        description: str,
        menu_ids: list[int],
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> dict[str, Any]:
        """创建角色。"""
        return self._request_dict(
            "POST",
            "/api/v1/identity/roles",
            json={
                "code": code,
                "name": name,
                "description": description,
                "menu_ids": menu_ids,
                "actor_role_codes": actor_role_codes,
                "actor_permission_codes": actor_permission_codes,
            },
        )

    def update_role(
        self,
        *,
        role_id: int,
        name: str | None,
        description: str | None,
        menu_ids: list[int] | None,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> dict[str, Any]:
        """更新角色。"""
        return self._request_dict(
            "POST",
            f"/api/v1/identity/roles/{role_id}",
            json={
                "name": name,
                "description": description,
                "menu_ids": menu_ids,
                "actor_role_codes": actor_role_codes,
                "actor_permission_codes": actor_permission_codes,
            },
        )

    def delete_role(
        self,
        role_id: int,
        *,
        actor_role_codes: list[str],
    ) -> dict[str, Any]:
        """软删除角色。"""
        return self._request_dict(
            "DELETE",
            f"/api/v1/identity/roles/{role_id}",
            json={"actor_role_codes": actor_role_codes},
        )

    def get_role_menus(self, role_id: int) -> list[dict[str, Any]]:
        """读取角色菜单。"""
        return self._request_list(
            "GET",
            f"/api/v1/identity/roles/{role_id}/menus",
        )

    def assign_role_menus(
        self,
        *,
        role_id: int,
        menu_ids: list[int],
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> dict[str, Any]:
        """覆盖角色菜单。"""
        return self._request_dict(
            "POST",
            f"/api/v1/identity/roles/{role_id}/menus",
            json={
                "ids": menu_ids,
                "actor_role_codes": actor_role_codes,
                "actor_permission_codes": actor_permission_codes,
            },
        )

    def list_menus(self) -> list[dict[str, Any]]:
        """读取菜单目录。"""
        return self._request_list("GET", "/api/v1/identity/menus")

    def create_menu(self, payload: dict[str, Any]) -> dict[str, Any]:
        """创建菜单。"""
        return self._request_dict(
            "POST",
            "/api/v1/identity/menus",
            json=payload,
        )

    def update_menu(
        self,
        *,
        menu_id: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """更新菜单。"""
        return self._request_dict(
            "POST",
            f"/api/v1/identity/menus/{menu_id}",
            json=payload,
        )

    def delete_menu(self, menu_id: int) -> dict[str, Any]:
        """软删除菜单。"""
        return self._request_dict(
            "DELETE",
            f"/api/v1/identity/menus/{menu_id}",
        )

    def list_permissions(self) -> list[dict[str, Any]]:
        """读取权限码目录。"""
        return self._request_list("GET", "/api/v1/identity/permissions")

    def create_invite_code(
        self,
        *,
        remaining: int,
        expires_in_hours: int,
        created_by: int,
        custom_code: str | None,
    ) -> dict[str, Any]:
        """创建随机或自定义邀请码。"""
        return self._request_dict(
            "POST",
            "/api/v1/identity/invite-codes",
            json={
                "remaining": remaining,
                "expires_in_hours": expires_in_hours,
                "created_by": created_by,
                "custom_code": custom_code,
            },
        )

    def list_invite_codes(
        self,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """分页读取邀请码列表。"""
        return self._request_dict(
            "GET",
            "/api/v1/identity/invite-codes",
            params={"page": page, "page_size": page_size},
        )

    def update_invite_code(
        self,
        *,
        code: str,
        remaining: int,
        expires_in_hours: int,
    ) -> dict[str, Any]:
        """更新邀请码的剩余次数与过期时间。"""
        return self._request_dict(
            "POST",
            f"/api/v1/identity/invite-codes/{code}",
            json={
                "remaining": remaining,
                "expires_in_hours": expires_in_hours,
            },
        )

    def delete_invite_code(
        self,
        *,
        code: str,
    ) -> dict[str, Any]:
        """删除邀请码。"""
        return self._request_dict(
            "DELETE",
            f"/api/v1/identity/invite-codes/{code}",
        )

    def test_dependencies(
        self,
        *,
        target: str,
    ) -> dict[str, Any]:
        """由 backend-data 统一执行基础设施健康检查。"""
        return self._request_dict(
            "POST",
            "/api/v1/system/test-connections",
            json={"target": target},
        )

    def upload_file(
        self,
        *,
        prefix: str,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """通用文件上传。"""
        return self._request_dict(
            "POST",
            "/api/v1/storage/upload",
            files={"file": (filename, data, content_type)},
            data={"prefix": prefix},
        )

    def upload_object(
        self,
        *,
        object_name: str,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """由 backend-data 按业务对象名上传文件。"""
        return self._request_dict(
            "POST",
            "/api/v1/storage/objects",
            files={"file": (filename, data, content_type)},
            data={"object_name": object_name},
        )

    def download_object(self, object_name: str) -> tuple[bytes, str]:
        """由 backend-data 下载对象内容，调用方不接触 MinIO 配置。"""
        try:
            response = self._sync_client.get(
                f"{self._base_url}/api/v1/storage/objects/content",
                headers=self._headers(),
                params={"object_name": object_name},
            )
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                message="backend-data 服务暂不可用",
                detail=str(exc),
            ) from exc
        if response.status_code >= 400:
            self._raise_response_error(response)
        content_type = response.headers.get(
            "content-type",
            "application/octet-stream",
        ).split(";", 1)[0]
        return response.content, content_type

    def download_object_by_url(self, file_url: str) -> tuple[bytes, str]:
        """由 backend-data 校验存储 URL 并下载对象。"""
        try:
            response = self._sync_client.get(
                f"{self._base_url}/api/v1/storage/objects/by-url",
                headers=self._headers(),
                params={"file_url": file_url},
            )
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                message="backend-data 服务暂不可用",
                detail=str(exc),
            ) from exc
        if response.status_code >= 400:
            self._raise_response_error(response)
        content_type = response.headers.get(
            "content-type",
            "application/octet-stream",
        ).split(";", 1)[0]
        return response.content, content_type

    async def ensure_message_broker(self) -> dict[str, Any]:
        """要求 backend-data 建立并核验消息拓扑。"""
        return await self._async_request_dict(
            "POST",
            "/api/v1/infrastructure/message-broker/topology",
        )

    async def publish_inbound_message(
        self,
        *,
        platform: str,
        bot_id: str,
        payload: str,
    ) -> dict[str, Any]:
        """通过 backend-data 发布网关入站消息。"""
        return await self._async_request_dict(
            "POST",
            "/api/v1/infrastructure/message-broker/inbound",
            json={
                "platform": platform,
                "bot_id": bot_id,
                "payload": payload,
            },
        )

    async def claim_outbound_message(
        self,
        *,
        timeout_seconds: float,
    ) -> dict[str, Any] | None:
        """从 backend-data 领取带租约的出站消息。"""
        value = await self._async_request(
            "GET",
            "/api/v1/infrastructure/message-broker/outbound/claim",
            params={"timeout_seconds": timeout_seconds},
            timeout=max(self._timeout, timeout_seconds + 5.0),
        )
        if value is None:
            return None
        return self._ensure_dict(value)

    async def acknowledge_outbound_message(
        self,
        receipt_id: str,
    ) -> dict[str, Any]:
        """确认出站消息处理成功。"""
        return await self._async_request_dict(
            "POST",
            "/api/v1/infrastructure/message-broker/outbound/ack",
            json={"receipt_id": receipt_id},
        )

    async def reject_outbound_message(
        self,
        receipt_id: str,
    ) -> dict[str, Any]:
        """释放出站消息租约以便重试。"""
        return await self._async_request_dict(
            "POST",
            "/api/v1/infrastructure/message-broker/outbound/nack",
            json={"receipt_id": receipt_id},
        )

    def reset_identity_rate_limit(
        self,
        *,
        bucket: str,
        identifier_hash: str,
    ) -> None:
        """通过 backend-data 清除成功登录后的账号限流桶。"""
        self._request(
            "POST",
            "/api/v1/identity/auth/rate-limit/reset",
            json={
                "bucket": bucket,
                "identifier_hash": identifier_hash,
            },
        )

    def reset_identity_rate_limits(
        self,
        items: list[IdentityRateLimitResetItem],
    ) -> None:
        """通过一次 backend-data 调用清除多个认证限流桶。"""
        self._request(
            "POST",
            "/api/v1/identity/auth/rate-limit/reset-many",
            json={"items": items},
        )

    def create_identity_captcha(self) -> dict[str, Any]:
        """要求 backend-data 生成并保存一次性算术验证码。"""
        return self._request_dict(
            "POST",
            "/api/v1/identity/auth/captcha",
        )

    def verify_identity_captcha(
        self,
        *,
        captcha_id: str,
        captcha_answer: str,
    ) -> None:
        """要求 backend-data 一次性消费并校验算术验证码。"""
        self._request(
            "POST",
            "/api/v1/identity/auth/captcha/verify",
            json={
                "captcha_id": captcha_id,
                "captcha_answer": captcha_answer,
            },
        )

    async def submit_trace_batch(self, payload: dict[str, Any]) -> None:
        """使用 gzip 向 backend-data 上报可能包含长正文的日志批次。"""
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        await self._async_request(
            "POST",
            "/api/v1/observability/events/batch",
            content=gzip.compress(serialized),
            headers={
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
            },
        )

    async def aclose(self) -> None:
        """关闭复用的异步 HTTP 连接池。"""
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    # ── Bot 管理 ──────────────────────────────────

    def list_bots(
        self,
        *,
        page: int,
        page_size: int,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """分页查询 Bot 列表（支持按 created_by 筛选）。"""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if created_by is not None:
            params["created_by"] = created_by
        return self._request_dict(
            "GET",
            "/api/v1/bots",
            params=params,
        )

    def list_active_bots(self) -> list[dict[str, Any]]:
        """查询全部活跃 Bot（含 app_secret 明文）。"""
        return self._request_list("GET", "/api/v1/bots/active")

    def get_bot(self, *, bot_id: str) -> dict[str, Any]:
        """获取单个 Bot 详情。"""
        return self._request_dict("GET", f"/api/v1/bots/{bot_id}")

    def create_bot(
        self,
        *,
        bot_id: str,
        name: str,
        platform: str,
        app_id: str,
        app_secret: str,
        mode: str = "test",
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """创建 Bot。"""
        payload: dict[str, Any] = {
            "bot_id": bot_id,
            "name": name,
            "platform": platform,
            "app_id": app_id,
            "app_secret": app_secret,
            "mode": mode,
        }
        if created_by is not None:
            payload["created_by"] = created_by
        return self._request_dict(
            "POST",
            "/api/v1/bots",
            json=payload,
        )

    def update_bot(self, *, bot_id: str, **fields: Any) -> dict[str, Any]:
        """更新 Bot 配置。"""
        return self._request_dict(
            "POST",
            f"/api/v1/bots/{bot_id}",
            json=fields,
        )

    def delete_bot(self, bot_id: str) -> dict[str, Any]:
        """软删除 Bot。"""
        return self._request_dict(
            "DELETE",
            f"/api/v1/bots/{bot_id}",
        )

    # ── Agent 管理 ─────────────────────────────────

    def list_agents(
        self,
        *,
        page: int,
        page_size: int,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """分页查询 Agent 列表。"""
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if created_by is not None:
            params["created_by"] = created_by
        return self._request_dict(
            "GET",
            "/api/v1/agents",
            params=params,
        )

    def get_agent(self, *, agent_id: str) -> dict[str, Any]:
        """获取单个 Agent 详情。"""
        return self._request_dict("GET", f"/api/v1/agents/{agent_id}")

    def create_agent(
        self,
        *,
        agent_id: str,
        name: str,
        status: int = 1,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """创建 Agent。"""
        payload: dict[str, Any] = {
            "agent_id": agent_id,
            "name": name,
            "status": status,
        }
        if created_by is not None:
            payload["created_by"] = created_by
        return self._request_dict(
            "POST",
            "/api/v1/agents",
            json=payload,
        )

    def update_agent(self, *, agent_id: str, **fields: Any) -> dict[str, Any]:
        """更新 Agent 配置。"""
        return self._request_dict(
            "POST",
            f"/api/v1/agents/{agent_id}",
            json=fields,
        )

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        """软删除 Agent。"""
        return self._request_dict(
            "DELETE",
            f"/api/v1/agents/{agent_id}",
        )

    def close(self) -> None:
        """关闭复用的同步 HTTP 连接池。"""
        self._sync_client.close()

    def _request_dict(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self._ensure_dict(self._request(method, path, **kwargs))

    def _request_list(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        value = self._request(method, path, **kwargs)
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise ServiceUnavailableError(
                message="backend-data response contract mismatch"
            )
        return value

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        headers = self._headers(kwargs.pop("headers", None))
        try:
            response = self._sync_client.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                message="backend-data 服务暂不可用",
                detail=str(exc),
            ) from exc

        return self._parse_envelope(response)

    async def _async_request_dict(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self._ensure_dict(await self._async_request(method, path, **kwargs))

    async def _async_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        headers = self._headers(kwargs.pop("headers", None))
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await self._async_client.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError(
                message="backend-data 服务暂不可用",
                detail=str(exc),
            ) from exc
        return self._parse_envelope(response)

    def _headers(
        self,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, str]:
        headers = propagation_headers()
        headers.update(extra_headers or {})
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        return headers

    @classmethod
    def _parse_envelope(cls, response: httpx.Response) -> Any:
        try:
            body = response.json()
        except ValueError as exc:
            raise ServiceUnavailableError(
                message="backend-data 返回了无效响应",
                detail=f"HTTP {response.status_code}",
            ) from exc
        if not isinstance(body, dict):
            raise ServiceUnavailableError(
                message="backend-data response contract mismatch"
            )
        if body.get("success") is not True or response.status_code >= 400:
            cls._raise_response_error(response, body=body)
        return body.get("data")

    @staticmethod
    def _raise_response_error(
        response: httpx.Response,
        *,
        body: dict[str, Any] | None = None,
    ) -> None:
        if body is None:
            try:
                parsed = response.json()
            except ValueError as exc:
                raise ServiceUnavailableError(
                    message="backend-data 返回了无效响应",
                    detail=f"HTTP {response.status_code}",
                ) from exc
            body = parsed if isinstance(parsed, dict) else {}
        data = body.get("data")
        code = data.get("code") if isinstance(data, dict) else None
        detail = data.get("detail") if isinstance(data, dict) else None
        exc_cls = (
            _CODE_TO_EXCEPTION.get(code, ApiException)
            if isinstance(code, str)
            else ApiException
        )
        raise exc_cls(
            code=code if isinstance(code, str) else None,
            message=(
                body.get("message")
                if isinstance(body.get("message"), str)
                else "backend-data request failed"
            ),
            http_status=response.status_code,
            detail=detail,
        )

    @staticmethod
    def _ensure_dict(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ServiceUnavailableError(
                message="backend-data response contract mismatch"
            )
        return value


_data_client: DataClient | None = None
_data_client_lock = threading.Lock()


def get_data_client() -> DataClient:
    """获取进程内 DataClient 单例。"""
    global _data_client
    if _data_client is None:
        with _data_client_lock:
            if _data_client is None:
                _data_client = DataClient()
    return _data_client
