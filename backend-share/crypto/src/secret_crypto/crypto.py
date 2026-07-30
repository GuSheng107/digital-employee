"""app_secret 可逆加密实现。

设计要点：
1. 使用 Fernet（AES-128-CBC + HMAC-SHA256）做认证加密，密文不可被篡改。
2. 主密钥以 passphrase 形式从环境变量 ``APP_SECRET_KEY`` 读取，经 PBKDF2-HMAC-SHA256
   派生为 Fernet 兼容的 32 字节 URL-safe base64 密钥。passphrase 形式便于运维
   配置，无需手动生成 base64 密钥。
3. 密文统一带 ``enc:v1:`` 前缀。``enc:v1:`` 版本号用于未来主密钥轮换或算法升级
   时按版本路由解密路径。
4. 读取时无前缀的值视为明文原样返回，兼容存量数据迁移前的过渡期。
5. PBKDF2 salt 在包内固定——服务端单租户密钥场景下可接受；多租户或更强安全
   要求时需升级为随机 salt 并随密文存储。
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

# 密文前缀，版本号 v1 预留给未来密钥轮换 / 算法升级。
PREFIX = "enc:v1:"

# PBKDF2 派生 salt（固定）。多目标攻击强度受限，服务端单租户密钥场景可接受。
_SALT = b"digital-employee-app-secret-v1"

# OWASP 2023 推荐 PBKDF2-HMAC-SHA256 迭代次数。
_KDF_ITERATIONS = 600_000


class CryptoError(Exception):
    """app_secret 加解密相关异常（密钥缺失、密文损坏、密钥不匹配等）。"""


def _derive_fernet_key(passphrase: str) -> bytes:
    """从 passphrase 派生 Fernet 兼容的 URL-safe base64 32 字节密钥。

    Args:
        passphrase: 用户提供的明文 passphrase。

    Returns:
        URL-safe base64 编码的 32 字节密钥，可直接传给 Fernet。
    """
    raw = hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        _SALT,
        _KDF_ITERATIONS,
        dklen=32,
    )
    return base64.urlsafe_b64encode(raw)


def _get_fernet() -> Fernet:
    """从环境变量 ``APP_SECRET_KEY`` 构造 Fernet 实例。

    Returns:
        Fernet 实例。

    Raises:
        CryptoError: 环境变量未设置时抛出。
    """
    passphrase = os.getenv("APP_SECRET_KEY")
    if not passphrase:
        raise CryptoError(
            "APP_SECRET_KEY 环境变量未设置。"
            "请在 .env 或系统环境变量中配置一个足够长的随机字符串作为 app_secret 主密钥。"
        )
    return Fernet(_derive_fernet_key(passphrase))


def encrypt(plaintext: str) -> str:
    """加密明文 app_secret，返回带 ``enc:v1:`` 前缀的密文。

    Args:
        plaintext: 待加密的明文 app_secret。

    Returns:
        形如 ``enc:v1:<fernet-token>`` 的密文字符串。空字符串原样返回（不加密）。

    Raises:
        CryptoError: ``APP_SECRET_KEY`` 未设置或加密失败时抛出。
    """
    if not plaintext:
        return plaintext
    fernet = _get_fernet()
    token = fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{PREFIX}{token}"


def decrypt(value: str) -> str:
    """解密 app_secret。

    带 ``enc:v1:`` 前缀的值用 Fernet 解密；无前缀的值视为明文原样返回，
    兼容存量数据未完成迁移前的过渡期。

    Args:
        value: 待解密的密文（带前缀）或明文（无前缀）。

    Returns:
        解密后的明文字符串。空字符串原样返回。

    Raises:
        CryptoError: ``APP_SECRET_KEY`` 未设置、密文损坏或密钥与加密时不一致时抛出。
    """
    if not value or not value.startswith(PREFIX):
        return value
    fernet = _get_fernet()
    token = value[len(PREFIX) :].encode("ascii")
    try:
        return fernet.decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise CryptoError(
            "app_secret 密文解密失败：APP_SECRET_KEY 与加密时不一致或密文已损坏。"
        ) from exc


def is_encrypted(value: str | None) -> bool:
    """判断 value 是否为加密格式（带 ``enc:v1:`` 前缀）。

    Args:
        value: 待判断的值，可为 None。

    Returns:
        True 表示 value 是加密格式；False 表示 value 为 None、空字符串或明文。
    """
    return value is not None and value.startswith(PREFIX)
