"""Bot 抽象基类定义。

定义所有平台 Bot 实例的生命周期接口，为二期多平台扩展预留抽象层。
"""

import abc
import threading
import time
from typing import Any

# Watchdog 连续重启计数上限：超过后标记为 dead 不再自动重启，需人工干预。
MAX_CONSECUTIVE_RESTARTS = 5

# Bot 稳定运行达到该阈值后，重启计数清零（视为偶发崩溃而非持续故障）。
UPTIME_RESET_THRESHOLD_SECONDS = 300.0

# 指数退避参数：每次重启后下一次重启需等待 backoff_initial * 2^count 秒，
# 上限为 backoff_max。
BACKOFF_INITIAL_SECONDS = 1.0
BACKOFF_MAX_SECONDS = 60.0


class BaseBot(abc.ABC):
    """Bot 实例抽象基类。

    定义统一的生命周期管理接口，所有平台实现必须继承此类。

    Attributes:
        bot_id: Bot 实例唯一标识。
        config: Bot 配置字典。
        mode: 运行模式（``test`` 内存模拟 / ``prod`` MQ 投递）。
    """

    def __init__(self, *, bot_id: str, config: dict[str, Any]) -> None:
        """初始化 BaseBot。

        Args:
            bot_id: Bot 实例唯一标识。
            config: Bot 配置字典，必须包含 app_id/app_secret，可选 mode。
        """
        self.bot_id: str = bot_id
        self.config: dict[str, Any] = config
        self._thread: threading.Thread | None = None
        self._is_running: bool = False
        self._start_time: float | None = None
        self._last_error: str | None = None
        # 运行模式收敛到基类：避免子类遗漏导致 hub 回落到默认 test 模式。
        self.mode: str = config.get("mode", "test")

        # Watchdog 退避状态：_restart_count 记录连续崩溃重启次数，
        # _last_restart_ts 记录最近一次重启时间戳，用于计算退避等待。
        self._restart_count: int = 0
        self._last_restart_ts: float | None = None

    @property
    def is_running(self) -> bool:
        """返回 Bot 是否正在运行。"""
        return self._is_running and self._thread is not None and self._thread.is_alive()

    @property
    def thread_id(self) -> int | None:
        """返回 Bot 运行所在的线程 ID。"""
        if self._thread is not None and self._thread.is_alive():
            return self._thread.ident
        return None

    @property
    def uptime_seconds(self) -> float | None:
        """返回 Bot 运行时长（秒）。"""
        if self._start_time is not None and self.is_running:
            return time.time() - self._start_time
        return None

    @property
    def last_error(self) -> str | None:
        """返回最近一次异常信息。"""
        return self._last_error

    @property
    def restart_count(self) -> int:
        """返回连续崩溃重启次数。"""
        return self._restart_count

    @property
    def is_zombie(self) -> bool:
        """判断 Bot 是否处于僵尸状态。

        僵尸状态指 ``_is_running`` 标记为 True 但底层线程已不存在或已死亡，
        需要由 Watchdog 重新拉起。该属性用于将 ``_is_running`` 与 ``_thread``
        的访问收拢在 Bot 内部，避免管理器直接读取私有字段。

        Returns:
            True 表示 Bot 处于僵尸状态，需要重启；False 表示正常运行或已正常停止。
        """
        if not self._is_running:
            return False
        return self._thread is None or not self._thread.is_alive()

    def start(self) -> None:
        """启动 Bot 实例。

        在独立子线程中启动 Bot 的主循环。
        """
        if self.is_running:
            return

        self._is_running = True
        self._start_time = time.time()
        self._last_error = None
        self._thread = threading.Thread(
            target=self._safe_run,
            name=f"bot-{self.bot_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """停止 Bot 实例。

        子类应在 _on_stop 中实现具体的停止逻辑（如断开 WebSocket）。
        """
        if not self._is_running:
            return
        self._is_running = False
        self._on_stop()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
        self._thread = None
        self._start_time = None

    def record_restart(self) -> None:
        """记录一次 Watchdog 触发的重启，递增连续重启计数并刷新时间戳。"""
        self._restart_count += 1
        self._last_restart_ts = time.time()

    def reset_restart_count_if_healthy(self) -> None:
        """当 Bot 稳定运行超过阈值后清零重启计数。

        在每次 Watchdog 扫描时调用：若 Bot 仍健康运行且 uptime 已超阈值，
        视为偶发崩溃已恢复，计数清零，下次崩溃按初始退避重新计数。
        """
        if self._restart_count == 0:
            return
        uptime = self.uptime_seconds
        if uptime is not None and uptime >= UPTIME_RESET_THRESHOLD_SECONDS:
            self._restart_count = 0

    def should_retry(self) -> bool:
        """判断 Watchdog 是否还应继续重启该 Bot。

        Returns:
            True 表示连续重启次数未超上限，可继续尝试；False 表示已达上限，
            标记为 dead，需人工干预。
        """
        return self._restart_count < MAX_CONSECUTIVE_RESTARTS

    def restart_backoff_seconds(self) -> float:
        """计算当前重启计数下的退避等待秒数。

        Returns:
            退避秒数（指数增长，上限 BACKOFF_MAX_SECONDS）。
        """
        return min(
            BACKOFF_INITIAL_SECONDS * (2**self._restart_count),
            BACKOFF_MAX_SECONDS,
        )

    def is_within_restart_backoff(self, now: float | None = None) -> bool:
        """判断当前时间是否仍处于上次重启的退避窗口内。

        Args:
            now: 当前时间戳，None 时取 time.time()。

        Returns:
            True 表示尚未到下一次重启时间，应跳过本次重启。
        """
        if self._last_restart_ts is None:
            return False
        current = now if now is not None else time.time()
        return current - self._last_restart_ts < self.restart_backoff_seconds()

    def _safe_run(self) -> None:
        """线程安全的运行包装器，捕获异常并记录。

        注意：异常路径下**不**重置 ``_is_running``——保留 True 标记 + 死线程
        即为僵尸状态，由 Watchdog 检测并重启。``_is_running=False`` 仅由
        ``stop()`` 设置，用于区分"用户主动停止"与"运行中崩溃"。
        """
        try:
            self._run()
        except Exception as exc:
            self._last_error = str(exc)

    @abc.abstractmethod
    def _run(self) -> None:
        """Bot 主运行逻辑，子类必须实现。"""
        pass

    @abc.abstractmethod
    def _on_stop(self) -> None:
        """停止时的清理逻辑，子类必须实现。"""
        pass
