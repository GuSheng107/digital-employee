"""注册、资料修改与管理员重置密码校验测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.auth import RegisterRequest
from app.schemas.user import ResetPasswordRequest, UpdateProfileRequest

VALID_PASSWORD = "Example123!"
VALID_CN_PHONE = "13800138000"


def test_registration_normalizes_cn_phone_to_e164() -> None:
    payload = RegisterRequest(
        username="tester",
        password=VALID_PASSWORD,
        email=" Tester@Example.COM ",
        phone=VALID_CN_PHONE,
        invite_code="TEAM-2026",
    )

    assert payload.phone == "+8613800138000"
    assert str(payload.email) == "tester@example.com"


@pytest.mark.parametrize(
    "password",
    [
        "short1!",
        "longpassword!",
        "1234567890!",
        "Example1234",
    ],
)
def test_registration_rejects_noncompliant_password(password: str) -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            username="tester",
            password=password,
            email="tester@example.com",
            phone=VALID_CN_PHONE,
            invite_code="TEAM-2026",
        )


def test_profile_rejects_invalid_email_and_other_region_phone() -> None:
    with pytest.raises(ValidationError):
        UpdateProfileRequest(
            email="invalid-email",
            phone="+14155552671",
            password=VALID_PASSWORD,
        )


def test_admin_reset_password_is_exempt_from_complexity() -> None:
    payload = ResetPasswordRequest(new_password="1")

    assert payload.new_password == "1"
