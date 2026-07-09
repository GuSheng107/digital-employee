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

from loguru import logger

from src.core.base import BaseBot
from src.core.schemas import BotConfig, BotConfigFile, BotStatusResponse
from src.core.hub import hub
from src.platforms.feishu.bot import FeishuBot
from src.platforms.wechat.bot import WeChatBot



class BotManager:
    """Bot 实例生命周期与配置管理器。

    Attributes:
        config_path: 本地静态配置文件路径。
    """

    def __init__(self, *, config_path: str = "config/bot.json") -> None:
        """初始化 BotManager。

        Args:
            config_path: 静态配置文件路径。
        """
        self.config_path: Path = Path(config_path)
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

    def load_from_file(self) -> None:
        """从本地静态文件加载 Bot 配置并初始化启动。"""
        if not self.config_path.exists():
            logger.warning(
                "本地静态配置文件 {} 不存在，跳过本地配置加载。", self.config_path
            )
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 使用 Pydantic 校验配置文件
            config_file = BotConfigFile.model_validate(data)
            logger.info(
                "成功从本地读取并校验静态配置，共包含 {} 个 Bot。",
                len(config_file.bots),
            )

            for bot_cfg in config_file.bots:
                self.add_or_update_bot(bot_cfg)

        except Exception as exc:
            logger.error("加载静态配置文件失败: {}", exc)

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
        logger.info("已向全部 Bot 实例注入主事件循环。")

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
                logger.info(
                    "[BotID: {}] 凭证与状态未发生变更，跳过重启。", bot_id
                )
                return

            logger.info("[BotID: {}] 正在热加载 Bot 配置...", bot_id)

            # 如果存在旧 Bot 实例，先执行平滑停止
            if old_bot is not None:
                logger.info(
                    "[BotID: {}] 检测到旧实例运行或配置变更，执行停止...", bot_id
                )
                old_bot.stop()
                self.bots.pop(bot_id, None)

            # 创建新的具体平台 Bot 实例
            if bot_cfg.platform == "feishu":
                new_bot = FeishuBot(bot_id=bot_id, config=new_config_dict)
            elif bot_cfg.platform == "wechat":
                new_bot = WeChatBot(bot_id=bot_id, config=new_config_dict)
            else:
                logger.error(
                    "[BotID: {}] 不支持的平台类型: {}", bot_id, bot_cfg.platform
                )
                return

            self.bots[bot_id] = new_bot
            self.active_configs[bot_id] = new_config_dict

            # 如果主事件循环已注入，则同步注入给新 Bot
            if self._main_loop is not None and hasattr(new_bot, "inject_main_loop"):
                new_bot.inject_main_loop(self._main_loop)

            # 启动新 Bot 实例的子线程
            new_bot.start()
            logger.info("[BotID: {}] 热更新并启动成功。", bot_id)

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
                logger.warning(
                    "[BotID: {}] 无法注销实例，指定的 Bot 不存在。", bot_id
                )
                return False

            bot.stop()
            self.bots.pop(bot_id, None)
            self.active_configs.pop(bot_id, None)
            logger.info("[BotID: {}] Bot 已成功移除。", bot_id)
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
        logger.info("Watchdog 守护线程已启动。")

    def shutdown(self) -> None:
        """停止管理器。关闭所有 Bot 实例，并关停 Watchdog。"""
        logger.info("正在关闭 BotManager...")
        self._watchdog_running = False

        # 浅拷贝 keys 避免迭代时修改 dict 报错
        bot_ids = list(self.bots.keys())
        for bot_id in bot_ids:
            self.remove_bot(bot_id)

        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=5.0)
            self._watchdog_thread = None

        logger.info("BotManager 已安全关闭。")

    def _watchdog_loop(self) -> None:
        """Watchdog 内部主循环，每 10 秒扫描一次不活跃线程。"""
        while self._watchdog_running:
            time.sleep(10.0)
            if not self._watchdog_running:
                break

            with self._lock:
                for bot_id, bot in self.bots.items():
                    # 如果 Bot 标记为应该运行，但对应的底层线程已经死掉
                    if bot._is_running and (
                        bot._thread is None or not bot._thread.is_alive()
                    ):
                        logger.warning(
                            "[BotID: {}] 检测到 Bot 线程异常终止（僵尸状态），正在尝试重新拉起...",
                            bot_id,
                        )
                        try:
                            # 清理残留线程对象，重新拉起
                            bot._thread = None
                            bot.start()
                        except Exception as exc:
                            logger.error(
                                "[BotID: {}] Watchdog 重启 Bot 失败: {}",
                                bot_id,
                                exc,
                            )
