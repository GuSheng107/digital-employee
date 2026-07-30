"""bot schema 单测：platform/mode Literal 校验。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.bot import CreateBotRequest, UpdateBotRequest


class TestCreateBotRequest:
    def test_valid_feishu_prod(self) -> None:
        """合法的 feishu + prod 组合应通过校验。"""
        req = CreateBotRequest(
            bot_id="bot-1",
            name="Bot",
            platform="feishu",
            app_id="app-1",
            app_secret="secret",
            mode="prod",
        )
        assert req.platform == "feishu"
        assert req.mode == "prod"

    def test_valid_wechat_test(self) -> None:
        """合法的 wechat + test 组合应通过校验。"""
        req = CreateBotRequest(
            bot_id="bot-1",
            name="Bot",
            platform="wechat",
            app_id="app-1",
            app_secret="secret",
        )
        assert req.platform == "wechat"
        assert req.mode == "test"  # 默认值

    @pytest.mark.parametrize("invalid_platform", ["", "qq", "dingtalk", "FEISHU", "feishu "])
    def test_invalid_platform_rejected(self, invalid_platform: str) -> None:
        """非法 platform 应被 422 拒绝。"""
        with pytest.raises(ValidationError):
            CreateBotRequest(
                bot_id="bot-1",
                name="Bot",
                platform=invalid_platform,
                app_id="app-1",
                app_secret="secret",
            )

    @pytest.mark.parametrize("invalid_mode", ["", "production", "debug", "TEST"])
    def test_invalid_mode_rejected(self, invalid_mode: str) -> None:
        """非法 mode 应被 422 拒绝。"""
        with pytest.raises(ValidationError):
            CreateBotRequest(
                bot_id="bot-1",
                name="Bot",
                platform="feishu",
                app_id="app-1",
                app_secret="secret",
                mode=invalid_mode,  # type: ignore[arg-type]
            )


class TestUpdateBotRequest:
    def test_partial_update_valid(self) -> None:
        """部分更新合法字段应通过。"""
        req = UpdateBotRequest(name="New Name", mode="prod")
        assert req.name == "New Name"
        assert req.mode == "prod"
        assert req.platform is None
        assert req.app_secret is None

    def test_invalid_platform_rejected(self) -> None:
        """非法 platform 在部分更新时也应被拒绝。"""
        with pytest.raises(ValidationError):
            UpdateBotRequest(platform="qq")

    def test_invalid_mode_rejected(self) -> None:
        """非法 mode 在部分更新时也应被拒绝。"""
        with pytest.raises(ValidationError):
            UpdateBotRequest(mode="production")  # type: ignore[arg-type]
