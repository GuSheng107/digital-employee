"""认证域输入校验与规范化。

手机号校验使用 libphonenumber 元数据，默认地区来自配置；当前设为 CN，
未来切换国家/地区无需修改号码段正则。数据库统一保存 E.164 格式。
"""

from __future__ import annotations

import re

import phonenumbers
from api_common import ValidationError
from phonenumbers import NumberParseException, PhoneNumberFormat

from app.core.config import settings

PASSWORD_MIN_LENGTH = 11
PASSWORD_MAX_LENGTH = 128
PASSWORD_COMPLEXITY_PATTERN = re.compile(
    rf"^(?=.{{{PASSWORD_MIN_LENGTH},{PASSWORD_MAX_LENGTH}}}$)"
    r"(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9\s]).+$",
    re.DOTALL,
)


def validate_password_complexity(password: str) -> str:
    """校验自助设置密码的长度与复杂度。"""
    if not PASSWORD_COMPLEXITY_PATTERN.fullmatch(password):
        raise ValueError("密码至少 11 位，且必须包含英文字母、数字和符号")
    return password


def normalize_phone_number(phone: str) -> str:
    """校验当前配置地区的号码并规范化为 E.164。"""
    value = phone.strip()
    try:
        parsed = phonenumbers.parse(value, settings.phone_default_region)
    except NumberParseException as exc:
        raise ValueError("请输入有效的手机号码") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("请输入有效的手机号码")
    region = phonenumbers.region_code_for_number(parsed)
    if region != settings.phone_default_region:
        raise ValueError(f"当前仅支持 {settings.phone_default_region} 地区号码")
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def normalize_email_address(email: str | None) -> str | None:
    """去除邮箱首尾空白并统一为小写，避免大小写造成重复账号。"""
    if email is None:
        return None
    normalized = email.strip().lower()
    return normalized or None


def validate_admin_reset_password(password: str) -> str:
    """管理员重置密码仅要求非空与数据库可存储长度。"""
    if not password:
        raise ValueError("重置密码不能为空")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"重置密码不能超过 {PASSWORD_MAX_LENGTH} 位")
    return password


def ensure_phone_region_is_supported() -> None:
    """启动/测试时校验默认手机号地区配置。"""
    if settings.phone_default_region not in phonenumbers.SUPPORTED_REGIONS:
        raise ValidationError(
            message=("PHONE_DEFAULT_REGION 配置无效：" f"{settings.phone_default_region}")
        )
