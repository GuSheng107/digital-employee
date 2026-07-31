"""secret_crypto 包单元测试。

覆盖：
- 加解密往返
- Fernet 随机 IV 保证同明文产生不同密文
- 密文前缀识别
- 明文过渡期兼容（无前缀当明文）
- 缺失 APP_SECRET_KEY 时的错误语义
- 密钥不匹配 / 密文损坏抛 CryptoError
- 空值边界
"""

from __future__ import annotations

import pytest

from secret_crypto import CryptoError, decrypt, encrypt, is_encrypted
from secret_crypto.crypto import PREFIX


@pytest.fixture
def app_secret_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """注入测试用 APP_SECRET_KEY 环境变量。"""
    key = "test-passphrase-please-not-in-prod-0123456789"
    monkeypatch.setenv("APP_SECRET_KEY", key)
    return key


OTHER_SECRET_KEY = "another-different-passphrase-for-mismatch-test"


class TestRoundTrip:
    """加解密往返。"""

    def test_round_trip_returns_original(self, app_secret_key: str) -> None:
        plain = "feishu-app-secret-abc123"
        cipher = encrypt(plain)
        assert cipher != plain
        assert cipher.startswith(PREFIX)
        assert decrypt(cipher) == plain

    def test_unicode_round_trip(self, app_secret_key: str) -> None:
        plain = "中文密钥-🔐-emoji"
        assert decrypt(encrypt(plain)) == plain

    def test_long_secret_round_trip(self, app_secret_key: str) -> None:
        plain = "x" * 10_000
        assert decrypt(encrypt(plain)) == plain


class TestCiphertextProperties:
    """密文属性。"""

    def test_same_plaintext_yields_different_ciphertext(self, app_secret_key: str) -> None:
        plain = "same-secret"
        # Fernet 内部使用随机 IV，同明文每次加密产生不同密文
        ciphers = {encrypt(plain) for _ in range(5)}
        assert len(ciphers) == 5

    def test_different_plaintext_yields_different_ciphertext(self, app_secret_key: str) -> None:
        c1 = encrypt("secret-one")
        c2 = encrypt("secret-two")
        assert c1 != c2


class TestPrefixAndPlaintextCompat:
    """前缀识别与明文过渡期兼容。"""

    def test_is_encrypted_true_for_prefixed(self, app_secret_key: str) -> None:
        assert is_encrypted(encrypt("plain")) is True

    def test_is_encrypted_false_for_plaintext(self) -> None:
        assert is_encrypted("plain-secret-no-prefix") is False

    def test_is_encrypted_false_for_empty(self) -> None:
        assert is_encrypted("") is False

    def test_is_encrypted_false_for_none(self) -> None:
        assert is_encrypted(None) is False

    def test_decrypt_plaintext_returns_as_is(self, app_secret_key: str) -> None:
        # 无前缀的值视为明文原样返回，兼容未迁移的存量数据
        assert decrypt("legacy-plain-secret") == "legacy-plain-secret"

    def test_decrypt_empty_string_returns_empty(self, app_secret_key: str) -> None:
        assert decrypt("") == ""

    def test_encrypt_empty_string_returns_empty(self, app_secret_key: str) -> None:
        assert encrypt("") == ""


class TestMissingKey:
    """APP_SECRET_KEY 缺失场景。"""

    def test_encrypt_raises_when_key_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("APP_SECRET_KEY", raising=False)
        with pytest.raises(CryptoError, match="APP_SECRET_KEY"):
            encrypt("plain")

    def test_decrypt_plaintext_works_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 明文过渡期：无前缀的值不依赖密钥，应原样返回
        monkeypatch.delenv("APP_SECRET_KEY", raising=False)
        assert decrypt("legacy-plain") == "legacy-plain"

    def test_decrypt_empty_works_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("APP_SECRET_KEY", raising=False)
        assert decrypt("") == ""

    def test_decrypt_ciphertext_raises_when_key_missing(
        self, app_secret_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cipher = encrypt("plain")
        monkeypatch.delenv("APP_SECRET_KEY", raising=False)
        with pytest.raises(CryptoError, match="APP_SECRET_KEY"):
            decrypt(cipher)


class TestKeyMismatchAndTamper:
    """密钥不匹配与密文损坏。"""

    def test_decrypt_with_wrong_key_raises(
        self, app_secret_key: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 用原始密钥加密
        cipher = encrypt("plain-with-original-key")
        # 切换为另一组密钥后解密，应抛 CryptoError
        monkeypatch.setenv("APP_SECRET_KEY", OTHER_SECRET_KEY)
        with pytest.raises(CryptoError, match="密文解密失败"):
            decrypt(cipher)

    def test_decrypt_tampered_ciphertext_raises(self, app_secret_key: str) -> None:
        cipher = encrypt("plain")
        # 篡改密文尾部字符
        tampered = cipher[:-1] + ("A" if cipher[-1] != "A" else "B")
        with pytest.raises(CryptoError, match="密文解密失败"):
            decrypt(tampered)

    def test_decrypt_truncated_ciphertext_raises(self, app_secret_key: str) -> None:
        cipher = encrypt("plain")
        # 截断密文
        truncated = cipher[: len(PREFIX) + 10]
        with pytest.raises(CryptoError, match="密文解密失败"):
            decrypt(truncated)
