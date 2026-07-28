"""密码哈希与 token 生成安全工具。

- 密码哈希：passlib + bcrypt，单向不可逆，verify 时常量时间比较。
- token 生成：secrets.token_urlsafe(32)，opaque 字符串，状态完全存 Redis。
- 不使用 JWT：所有状态在服务端，支持主动失效，避免客户端签名无法撤销的问题。
"""

from __future__ import annotations

import secrets

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """使用 bcrypt 对明文密码进行哈希。

    Args:
        password: 明文密码。

    Returns:
        bcrypt 哈希字符串（含 salt 与版本信息）。
    """
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """常量时间比较明文密码与哈希是否匹配。

    Args:
        password: 用户输入的明文密码。
        password_hash: 数据库中存储的哈希字符串。

    Returns:
        匹配返回 True，否则 False。哈希格式非法时同样返回 False，
        避免向上抛出异常暴露内部状态。
    """
    try:
        return _pwd_context.verify(password, password_hash)
    except (ValueError, TypeError):
        return False


def generate_token() -> str:
    """生成 opaque token 字符串。

    使用 secrets.token_urlsafe(32) 生成 43 字符的 URL 安全随机串，
    熵足够抵御暴力枚举，状态完全存 Redis，不含任何 payload。
    """
    return secrets.token_urlsafe(32)
