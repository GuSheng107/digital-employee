"""BotManager 单测。

重点覆盖：
- add_or_update_bot 先校验 platform 再停旧 Bot：非法平台不破坏现有实例。
- 配置变更触发平滑热重启；配置未变更时 no-op。
- remove_bot / get_bot / get_all_status 基本语义。

通过 monkeypatch 将 src.manager.FeishuBot / WeChatBot 替换为测试 stub，
避免触发真实 lark-oapi / wecom_aibot_sdk 初始化。
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from src.core.schemas import BotConfig
from src.manager import BotManager
from tests.conftest import _StubBot


@pytest.fixture
def patched_manager(monkeypatch: pytest.MonkeyPatch) -> BotManager:
    """构造一个 FeishuBot/WeChatBot 均被 stub 替换的 BotManager。"""

    def _feishu_factory(*, bot_id: str, config: dict[str, Any]) -> _StubBot:
        return _StubBot(bot_id=bot_id, config=config, behavior="block")

    def _wechat_factory(*, bot_id: str, config: dict[str, Any]) -> _StubBot:
        return _StubBot(bot_id=bot_id, config=config, behavior="block")

    monkeypatch.setattr("src.manager.FeishuBot", _feishu_factory)
    monkeypatch.setattr("src.manager.WeChatBot", _wechat_factory)
    return BotManager()


def _make_cfg(
    bot_id: str = "test-bot",
    platform: str = "feishu",
    mode: str = "test",
    app_id: str = "id-1",
    app_secret: str = "secret-1",
) -> BotConfig:
    return BotConfig(
        bot_id=bot_id,
        platform=platform,
        mode=mode,
        app_id=app_id,
        app_secret=app_secret,
    )


class TestPlatformValidationOrder:
    """先校验 platform 再停旧 Bot：非法平台不应破坏现有实例。"""

    def test_invalid_platform_does_not_create_bot(self, patched_manager: BotManager) -> None:
        # BotConfig 的 Literal 已在 schema 层拒非法 platform，但 manager 仍需
        # 防御性校验（schema 可能被绕过，例如 reload_from_database 直接构造 dict）
        # 这里通过 monkeypatch 绕过 Literal 校验：直接调 add_or_update_bot
        # 传一个 platform 非法的 BotConfig
        cfg = _make_cfg(platform="feishu")
        cfg.__dict__["platform"] = "telegram"  # type: ignore[assignment]
        patched_manager.add_or_update_bot(cfg)
        assert patched_manager.bots == {}

    def test_invalid_platform_preserves_existing_bot(self, patched_manager: BotManager) -> None:
        # 先加一个合法 feishu bot
        patched_manager.add_or_update_bot(_make_cfg(bot_id="b1", platform="feishu"))
        time.sleep(0.1)
        original_bot = patched_manager.get_bot("b1")
        assert original_bot is not None
        assert original_bot.is_running is True

        # 尝试用非法 platform 更新同一 bot_id：不应停旧 Bot
        cfg = _make_cfg(bot_id="b1", platform="feishu", app_secret="changed")
        cfg.__dict__["platform"] = "telegram"  # type: ignore[assignment]
        patched_manager.add_or_update_bot(cfg)

        # 旧 Bot 仍在运行，未被停止
        assert original_bot.is_running is True
        assert patched_manager.get_bot("b1") is original_bot


class TestHotUpdate:
    """配置变更触发平滑热重启。"""

    def test_same_config_is_noop(self, patched_manager: BotManager) -> None:
        cfg = _make_cfg(bot_id="b1")
        patched_manager.add_or_update_bot(cfg)
        time.sleep(0.1)
        first_bot = patched_manager.get_bot("b1")

        # 同配置再次调用：no-op，Bot 实例不变
        patched_manager.add_or_update_bot(cfg)
        assert patched_manager.get_bot("b1") is first_bot

    def test_config_change_restarts_bot(self, patched_manager: BotManager) -> None:
        cfg = _make_cfg(bot_id="b1", app_secret="s1")
        patched_manager.add_or_update_bot(cfg)
        time.sleep(0.1)
        first_bot = patched_manager.get_bot("b1")
        assert first_bot is not None

        # 修改 app_secret 触发热重启
        new_cfg = _make_cfg(bot_id="b1", app_secret="s2")
        patched_manager.add_or_update_bot(new_cfg)
        time.sleep(0.1)

        # 旧 Bot 被停止，新 Bot 启动
        assert first_bot.is_running is False
        assert first_bot.stop_called is True
        new_bot = patched_manager.get_bot("b1")
        assert new_bot is not None
        assert new_bot is not first_bot
        assert new_bot.is_running is True

    def test_mode_change_triggers_restart(self, patched_manager: BotManager) -> None:
        cfg = _make_cfg(bot_id="b1", mode="test")
        patched_manager.add_or_update_bot(cfg)
        time.sleep(0.1)
        first_bot = patched_manager.get_bot("b1")
        assert first_bot.mode == "test"

        # 切换 mode 触发重启
        new_cfg = _make_cfg(bot_id="b1", mode="prod")
        patched_manager.add_or_update_bot(new_cfg)
        time.sleep(0.1)
        new_bot = patched_manager.get_bot("b1")
        assert new_bot is not first_bot
        assert new_bot.mode == "prod"


class TestRemoveAndGetStatus:
    """remove_bot / get_all_status 基本语义。"""

    def test_remove_bot_stops_and_unregisters(self, patched_manager: BotManager) -> None:
        patched_manager.add_or_update_bot(_make_cfg(bot_id="b1"))
        time.sleep(0.1)
        bot = patched_manager.get_bot("b1")

        ok = patched_manager.remove_bot("b1")
        assert ok is True
        assert bot is not None
        assert bot.stop_called is True
        assert patched_manager.get_bot("b1") is None

    def test_remove_nonexistent_returns_false(self, patched_manager: BotManager) -> None:
        assert patched_manager.remove_bot("nope") is False

    def test_get_all_status_reports_running_bot(self, patched_manager: BotManager) -> None:
        patched_manager.add_or_update_bot(_make_cfg(bot_id="b1", platform="feishu", mode="prod"))
        time.sleep(0.1)
        statuses = patched_manager.get_all_status()
        assert len(statuses) == 1
        s = statuses[0]
        assert s.bot_id == "b1"
        assert s.platform == "feishu"
        assert s.is_running is True
