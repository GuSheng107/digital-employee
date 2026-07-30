"""Bot 路由 Payload 校验单测。

覆盖 CreateBotPayload / UpdateBotPayload 的 Literal platform/mode 约束：
- 合法值通过。
- 非法 platform（如 qq）/mode（如 staging）被拒。
- 必填字段缺失被拒。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.routes.bots import CreateBotPayload, UpdateBotPayload


def _valid_create_kwargs() -> dict:
    return {
        "bot_id": "bot-1",
        "name": "飞书机器人",
        "platform": "feishu",
        "app_id": "cli_xxx",
        "app_secret": "secret",
        "mode": "test",
    }


# ── CreateBotPayload ──────────────────────────────────


def test_create_payload_accepts_feishu() -> None:
    """platform=feishu 合法。"""
    payload = CreateBotPayload(**_valid_create_kwargs())
    assert payload.platform == "feishu"


def test_create_payload_accepts_wechat() -> None:
    """platform=wechat 合法。"""
    kwargs = _valid_create_kwargs()
    kwargs["platform"] = "wechat"
    payload = CreateBotPayload(**kwargs)
    assert payload.platform == "wechat"


def test_create_payload_rejects_unknown_platform() -> None:
    """platform=qq 应被 Literal 拒绝。"""
    kwargs = _valid_create_kwargs()
    kwargs["platform"] = "qq"
    with pytest.raises(ValidationError):
        CreateBotPayload(**kwargs)


def test_create_payload_accepts_mode_prod() -> None:
    """mode=prod 合法。"""
    kwargs = _valid_create_kwargs()
    kwargs["mode"] = "prod"
    payload = CreateBotPayload(**kwargs)
    assert payload.mode == "prod"


def test_create_payload_rejects_unknown_mode() -> None:
    """mode=staging 应被 Literal 拒绝。"""
    kwargs = _valid_create_kwargs()
    kwargs["mode"] = "staging"
    with pytest.raises(ValidationError):
        CreateBotPayload(**kwargs)


def test_create_payload_mode_defaults_to_test() -> None:
    """mode 未传时默认 test。"""
    kwargs = _valid_create_kwargs()
    del kwargs["mode"]
    payload = CreateBotPayload(**kwargs)
    assert payload.mode == "test"


def test_create_payload_rejects_missing_platform() -> None:
    """platform 必填。"""
    kwargs = _valid_create_kwargs()
    del kwargs["platform"]
    with pytest.raises(ValidationError):
        CreateBotPayload(**kwargs)


def test_create_payload_rejects_empty_bot_id() -> None:
    """bot_id 空串违反 min_length=1。"""
    kwargs = _valid_create_kwargs()
    kwargs["bot_id"] = ""
    with pytest.raises(ValidationError):
        CreateBotPayload(**kwargs)


def test_create_payload_rejects_empty_app_secret() -> None:
    """app_secret 空串违反 min_length=1。"""
    kwargs = _valid_create_kwargs()
    kwargs["app_secret"] = ""
    with pytest.raises(ValidationError):
        CreateBotPayload(**kwargs)


# ── UpdateBotPayload ──────────────────────────────────


def test_update_payload_all_none_allowed() -> None:
    """Update 全字段可空（未传即不修改）。"""
    payload = UpdateBotPayload()
    assert payload.name is None
    assert payload.platform is None
    assert payload.mode is None
    assert payload.app_id is None
    assert payload.app_secret is None


def test_update_payload_accepts_feishu() -> None:
    """platform=feishu 合法。"""
    payload = UpdateBotPayload(platform="feishu")
    assert payload.platform == "feishu"


def test_update_payload_accepts_wechat() -> None:
    """platform=wechat 合法。"""
    payload = UpdateBotPayload(platform="wechat")
    assert payload.platform == "wechat"


def test_update_payload_rejects_unknown_platform() -> None:
    """platform=ding 应被 Literal 拒绝。"""
    with pytest.raises(ValidationError):
        UpdateBotPayload(platform="ding")


def test_update_payload_accepts_mode_prod() -> None:
    """mode=prod 合法。"""
    payload = UpdateBotPayload(mode="prod")
    assert payload.mode == "prod"


def test_update_payload_rejects_unknown_mode() -> None:
    """mode=staging 应被 Literal 拒绝。"""
    with pytest.raises(ValidationError):
        UpdateBotPayload(mode="staging")


def test_update_payload_rejects_empty_name() -> None:
    """name 空串违反 min_length=1。"""
    with pytest.raises(ValidationError):
        UpdateBotPayload(name="")


def test_update_payload_rejects_empty_app_id() -> None:
    """app_id 空串违反 min_length=1。"""
    with pytest.raises(ValidationError):
        UpdateBotPayload(app_id="")
