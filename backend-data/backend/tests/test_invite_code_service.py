"""自定义邀请码原子创建测试。"""

from __future__ import annotations

from typing import Any

import pytest
from api_common import DuplicateResourceError

from app.services.identity_invite_code_service import InviteCodeService


class _FakeRedis:
    def __init__(self, *, created: bool) -> None:
        self.created = created
        self.key: str | None = None
        self.payload: dict[str, Any] | None = None

    def set_json_if_absent(
        self,
        key: str,
        value: dict[str, Any],
        *,
        ttl_seconds: int,
    ) -> bool:
        assert ttl_seconds > 0
        self.key = key
        self.payload = value
        return self.created


def _service(redis: _FakeRedis) -> InviteCodeService:
    service = InviteCodeService.__new__(InviteCodeService)
    service._redis = redis
    service._key_prefix = "invite_code:"
    return service


def test_custom_invite_code_uses_atomic_create() -> None:
    redis = _FakeRedis(created=True)

    result = _service(redis).create(
        remaining=2,
        expires_in_hours=24,
        created_by=7,
        custom_code="TEAM-2026",
    )

    assert result["code"] == "TEAM-2026"
    assert redis.key == "invite_code:TEAM-2026"
    assert redis.payload is not None
    assert redis.payload["remaining"] == 2


def test_duplicate_custom_invite_code_is_rejected() -> None:
    redis = _FakeRedis(created=False)

    with pytest.raises(DuplicateResourceError):
        _service(redis).create(
            remaining=1,
            expires_in_hours=24,
            created_by=7,
            custom_code="TEAM-2026",
        )
