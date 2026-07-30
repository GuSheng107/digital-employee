# -*- coding: utf-8 -*-
"""Bot 实例管理器定义。

负责 Bot 的生命周期管理、本地/动态配置合并、热更新重启及 Watchdog 守护线程。
"""

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any
from pydantic import ValidationError

from loguru import logger
from src.core.base import BaseBot
from src.core.schemas import BotConfig, BotStatusResponse
from src.core.hub import hub
from src.platforms.feishu.bot import FeishuBot
from src.platforms.wechat.bot import WeChatBot

from data_client import get_data_client


class BotManager:
    """Bot 实例生命周期与配置管理器。"""

    def __init__(self) -> None:
        """初始化 BotManager。"""
        self.bots: dict[str, BaseBot] = {}
        # 保护 bots 字典与操作的线程锁
        self._lock: threading.Lock = threading.Lock()
        # 内存中合并后的最新配置字典（bot_id -> 原始 dict 配置）
        self.active_configs: dict[str, dict[str, Any]] = {}

        # Watchdog 守护线程状态
        self._watchdog_thread: threading.Thread | None = None
        self._watchdog_running: bool = False
        # FastAPI 主事件循环引用，用于动态添加 Bot 时注入
        self._main_loop: asyncio.AbstractEventLoop | None = None

        # 注册 Bot 查找器给全局消息中枢，化解循环导包
        hub.register_bot_provider(self.get_bot)

    def load_from_database(self) -> None:
        """从 backend-data 数据库拉取活跃 Bot 配置并初始化启动。"""
        try:
            active_bots = get_data_client().list_active_bots()
        except Exception as exc:
            logger.error("[BOT-MANAGER] 从数据库拉取机器人配置失败: {}", exc)
            return

        for bot_dict in active_bots:
            try:
                bot_cfg = BotConfig(
                    bot_id=bot_dict["bot_id"],
                    platform=bot_dict.get("platform", "feishu"),
                    app_id=bot_dict.get("app_id", ""),
                    app_secret=bot_dict.get("app_secret", ""),
                    mode=bot_dict.get("mode", "test"),
                )
                self.add_or_update_bot(bot_cfg)
            except (KeyError, ValidationError) as exc:
                logger.warning("[BOT-MANAGER] 机器配置转换失败 ({}): {}", bot_dict.get("bot_id"), exc)

    def reload_from_database(self) -> None:
        """从 backend-data 重新拉取配置，与内存中的对比执行增/删/改。

        前端修改 Bot 配置后调用此方法触发热重载。
        """
        try:
            active_bots = get_data_client().list_active_bots()
        except Exception:
            return

        # 构建最新配置快照
        new_config_map: dict[str, dict[str, Any]] = {}
        for bot_dict in active_bots:
            bid = bot_dict.get("bot_id")
            if bid:
                new_config_map[bid] = bot_dict

        # 移除数据库中已不存在的 Bot
        current_bot_ids = list(self.bots.keys())
        for bid in current_bot_ids:
            if bid not in new_config_map:
                self.remove_bot(bid)

        # 添加或更新数据库中的 Bot
        for bid, bot_dict in new_config_map.items():
            try:
                bot_cfg = BotConfig(
                    bot_id=bid,
                    platform=bot_dict.get("platform", "feishu"),
                    app_id=bot_dict.get("app_id", ""),
                    app_secret=bot_dict.get("app_secret", ""),
                    mode=bot_dict.get("mode", "test"),
                )
                self.add_or_update_bot(bot_cfg)
            except (KeyError, ValidationError):
                pass

    def inject_main_loop_to_all(self, loop: asyncio.AbstractEventLoop) -> None:
        """将 FastAPI 主事件循环注入给所有已加载的 Bot 实例。

        在 lifespan 启动阶段调用，确保所有 Bot 的适配器均能安全地
        跨线程向异步中枢投递消息。

        Args:
            loop: FastAPI/Uvicorn 运行中的主异步事件循环。
        """
        with self._lock:
            for bot_id, bot in self.bots.items():
                if hasattr(bot, "inject_main_loop"):
                    bot.inject_main_loop(loop)
        self._main_loop = loop

    def add_or_update_bot(self, bot_cfg: BotConfig) -> None:
        """添加或更新 Bot 实例，支持平滑热重启。

        Args:
            bot_cfg: Bot 实例配置对象。
        """
        bot_id = bot_cfg.bot_id
        new_config_dict = bot_cfg.model_dump()

        with self._lock:
            old_bot = self.bots.get(bot_id)
            old_config = self.active_configs.get(bot_id)

            # 检查配置是否发生变更。如果没变更且已经在运行，无需任何操作
            if (
                old_bot is not None
                and old_bot.is_running
                and old_config == new_config_dict
            ):
                return

            # 如果存在旧 Bot 实例，先执行平滑停止
            if old_bot is not None:
                old_bot.stop()
                self.bots.pop(bot_id, None)

            # 创建新的具体平台 Bot 实例
            if bot_cfg.platform == "feishu":
                new_bot = FeishuBot(bot_id=bot_id, config=new_config_dict)
            elif bot_cfg.platform == "wechat":
                new_bot = WeChatBot(bot_id=bot_id, config=new_config_dict)
            else:
                return

            self.bots[bot_id] = new_bot
            self.active_configs[bot_id] = new_config_dict

            # 如果主事件循环已注入，则同步注入给新 Bot
            if self._main_loop is not None and hasattr(new_bot, "inject_main_loop"):
                new_bot.inject_main_loop(self._main_loop)

            # 启动新 Bot 实例的子线程
            new_bot.start()

    def remove_bot(self, bot_id: str) -> bool:
        """停止并注销指定的 Bot 实例。

        Args:
            bot_id: 待移除的 Bot 标识。

        Returns:
            是否成功移除。
        """
        with self._lock:
            bot = self.bots.get(bot_id)
            if bot is None:
                return False

            bot.stop()
            self.bots.pop(bot_id, None)
            self.active_configs.pop(bot_id, None)
            return True

    def get_bot(self, bot_id: str) -> BaseBot | None:
        """通过 BotID 线程安全地查询对应的 Bot 实例。

        Args:
            bot_id: 机器人的唯一 ID。

        Returns:
            Bot 实例，不存在则返回 None。
        """
        with self._lock:
            return self.bots.get(bot_id)

    def get_all_status(self) -> list[BotStatusResponse]:
        """获取当前内存中所有 Bot 实例的运行状态。

        Returns:
            各 Bot 的运行状态响应对象列表。
        """
        status_list: list[BotStatusResponse] = []
        with self._lock:
            for bot_id, bot in self.bots.items():
                status_list.append(
                    BotStatusResponse(
                        bot_id=bot_id,
                        platform=bot.config.get("platform", "unknown"),
                        is_running=bot.is_running,
                        thread_id=bot.thread_id,
                        uptime_seconds=bot.uptime_seconds,
                        last_error=bot.last_error,
                    )
                )
        return status_list

    def start_watchdog(self) -> None:
        """启动 Watchdog 守护线程，定期保活僵尸线程。"""
        if self._watchdog_running:
            return

        self._watchdog_running = True
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop,
            name="bot-manager-watchdog",
            daemon=True,
        )
        self._watchdog_thread.start()

    def shutdown(self) -> None:
        """停止管理器。关闭所有 Bot 实例，并关停 Watchdog。"""
        self._watchdog_running = False

        # 浅拷贝 keys 避免迭代时修改 dict 报错
        bot_ids = list(self.bots.keys())
        for bot_id in bot_ids:
            self.remove_bot(bot_id)

        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=5.0)
            self._watchdog_thread = None

    def _watchdog_loop(self) -> None:
        """Watchdog 内部主循环，每 10 秒扫描一次不活跃线程。"""
        while self._watchdog_running:
            time.sleep(10.0)
            if not self._watchdog_running:
                break

            with self._lock:
                for bot_id, bot in self.bots.items():
                    # 通过公开属性判断是否处于僵尸状态，避免直接读取私有字段
                    if bot.is_zombie:
                        try:
                            # start() 会重置 _thread，无需外部清理私有字段
                            bot.start()
                        except Exception:
                            pass
