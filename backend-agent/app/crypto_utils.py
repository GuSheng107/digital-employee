from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .exceptions import CryptoError


class CryptoUtils:
    """加密解密工具类，用于安全存储 API Key 等敏感信息"""

    def __init__(self, key_dir: Path):
        self.key_dir = key_dir
        self.key_dir.mkdir(parents=True, exist_ok=True)
        self.key_file = self.key_dir / ".encryption_key"
        self._fernet: Fernet | None = None

    def _get_or_create_key(self) -> bytes:
        """获取或创建加密密钥"""
        if self.key_file.exists():
            return self.key_file.read_bytes()

        # 生成新密钥
        key = Fernet.generate_key()
        self.key_file.write_bytes(key)
        # 设置权限，仅当前用户可读写
        try:
            os.chmod(self.key_file, 0o600)
        except (OSError, AttributeError):
            pass
        return key

    def _get_fernet(self) -> Fernet:
        """获取 Fernet 实例"""
        if self._fernet is None:
            key = self._get_or_create_key()
            self._fernet = Fernet(key)
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        """加密字符串"""
        if not plaintext:
            return ""
        fernet = self._get_fernet()
        encrypted = fernet.encrypt(plaintext.encode("utf-8"))
        return base64.urlsafe_b64encode(encrypted).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """解密字符串"""
        if not ciphertext:
            return ""
        try:
            fernet = self._get_fernet()
            decoded = base64.urlsafe_b64decode(ciphertext.encode("utf-8"))
            decrypted = fernet.decrypt(decoded)
            return decrypted.decode("utf-8")
        except (InvalidToken, ValueError, base64.binascii.Error) as e:
            raise CryptoError("解密失败") from e


# 全局加密工具实例，固定使用 data 目录
_crypto_utils: CryptoUtils | None = None


def get_crypto_utils() -> CryptoUtils:
    """获取全局加密工具实例"""
    global _crypto_utils
    if _crypto_utils is None:
        _crypto_utils = CryptoUtils(Path("data"))
    return _crypto_utils
