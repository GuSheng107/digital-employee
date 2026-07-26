from __future__ import annotations

from typing import Any

from app.logger import get_logger


_logger = get_logger("auth")


def _config_flag_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, int):
        return value == 1
    return False


def get_guest_account_config() -> dict[str, str] | None:
    from app.yaml_config import get_yaml_config

    guest_cfg = get_yaml_config().get("guest_account")
    if not isinstance(guest_cfg, dict) or not _config_flag_enabled(guest_cfg.get("enabled", False)):
        return None
    username = str(guest_cfg.get("username") or "").strip()
    password = str(guest_cfg.get("password") or "")
    if not username or not password:
        return None
    return {
        "username": username,
        "password": password,
    }


def extract_bearer_token(authorization: str | None) -> str:
    value = str(authorization or "").strip()
    if not value:
        return ""
    prefix = "Bearer "
    if value.lower().startswith(prefix.lower()):
        return value[len(prefix):].strip()
    return ""


# ═══════════════════════════════════════════════════════════════════
# 双 Token 认证 (Redis opaque token)
# ═══════════════════════════════════════════════════════════════════


_DUAL_TOKEN_MANAGER: "DualTokenManager | None" = None


class DualTokenError(Exception):
    """双 token 异常，msg 可直接展示给前端。"""
    def __init__(self, msg: str, status_code: int = 401) -> None:
        super().__init__(msg)
        self.msg = msg
        self.status_code = status_code


def set_dual_token_manager(manager: "DualTokenManager | None") -> None:
    """注入 DualTokenManager 实例（由 web_server 启动时调用）。"""
    global _DUAL_TOKEN_MANAGER
    _DUAL_TOKEN_MANAGER = manager


def get_dual_token_manager() -> "DualTokenManager | None":
    return _DUAL_TOKEN_MANAGER


async def issue_token_pair(username: str, role: str) -> "TokenPair":
    """签发双 token pair。"""
    mgr = _DUAL_TOKEN_MANAGER
    if mgr is None:
        raise DualTokenError("认证服务未就绪", status_code=503)
    return await mgr.issue_token_pair(username, role)


async def validate_access_token(plain_text: str) -> "TokenUser":
    """验证 access token，成功返回 TokenUser，失败抛 DualTokenError。"""
    mgr = _DUAL_TOKEN_MANAGER
    if mgr is None:
        raise DualTokenError("认证服务未就绪", status_code=503)
    user = await mgr.validate_access_token(plain_text)
    if user is None:
        raise DualTokenError("登录已过期，请重新登录")
    return user


async def refresh_token_pair(plain_text: str) -> "TokenPair":
    """用 refresh token 换新 pair。失败抛 DualTokenError。"""
    mgr = _DUAL_TOKEN_MANAGER
    if mgr is None:
        raise DualTokenError("认证服务未就绪", status_code=503)
    from app.redis_token_manager import _AuthError as _RAE
    try:
        return await mgr.refresh_token_pair(plain_text)
    except _RAE as exc:
        raise DualTokenError(str(exc)) from exc


async def revoke_token_pair(access_token: str) -> None:
    """登出：撤销 token pair。"""
    mgr = _DUAL_TOKEN_MANAGER
    if mgr is None:
        return
    from app.redis_token_manager import _AuthError
    try:
        await mgr.revoke_token_pair(access_token)
    except _AuthError as exc:
        _logger.warning("Ignore invalid token during logout: %s", exc)


async def revoke_all_user_tokens(username: str) -> int:
    """强制下线用户所有设备。"""
    mgr = _DUAL_TOKEN_MANAGER
    if mgr is None:
        raise DualTokenError("认证服务未就绪", status_code=503)
    return await mgr.revoke_all_user_tokens(username)


async def user_from_access_token(plain_text: str) -> "TokenUser | None":
    """只读获取 token 对应的用户（不续期）。"""
    mgr = _DUAL_TOKEN_MANAGER
    if mgr is None:
        return None
    return await mgr.user_from_access_token(plain_text)
