"""digital-employee 共享的 app_secret 可逆加密工具。

主密钥从环境变量 ``APP_SECRET_KEY`` 读取（passphrase 形式，由 PBKDF2 派生
为 Fernet 密钥），密文带 ``enc:v1:`` 前缀以便与明文过渡期数据兼容。

典型用法：

    from secret_crypto import encrypt, decrypt, is_encrypted

    cipher = encrypt("plain-app-secret")     # -> "enc:v1:..."
    plain = decrypt(cipher)                   # -> "plain-app-secret"
    plain = decrypt("legacy-plain-secret")    # -> "legacy-plain-secret"（无前缀当明文）
"""

from secret_crypto.crypto import CryptoError, decrypt, encrypt, is_encrypted

__all__ = ["CryptoError", "decrypt", "encrypt", "is_encrypted"]
