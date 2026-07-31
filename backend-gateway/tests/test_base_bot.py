"""BaseBot 生命周期与僵尸态语义单测。

重点覆盖：
- mode 由 BaseBot.__init__ 从 config 读取（FeishuBot 历史漏写 self.mode 的根因）。
- _safe_run 异常路径不重置 _is_running：保留 True + 死线程 = 僵尸态，由 Watchdog 重启。
- stop() 主动停止时 _is_running=False，区分"用户停止"与"运行中崩溃"。
- Watchdog 退避辅助方法：record_restart / should_retry / backoff / 健康清零。
"""

from __future__ import annotations

import time

from src.core.base import (
    BACKOFF_INITIAL_SECONDS,
    BACKOFF_MAX_SECONDS,
    MAX_CONSECUTIVE_RESTARTS,
    UPTIME_RESET_THRESHOLD_SECONDS,
)


class TestModeFromConfig:
    """mode 归属基类。"""

    def test_mode_read_from_config(self, make_stub_bot) -> None:
        bot = make_stub_bot(mode="prod")
        assert bot.mode == "prod"

    def test_mode_defaults_to_test_when_missing(self, make_stub_bot) -> None:
        # StubBot 通过 make_stub_bot 总是注入 mode，这里手动构造缺失 mode 的 config
        from tests.conftest import _StubBot

        bot = _StubBot(
            bot_id="no-mode-bot",
            config={"app_id": "x", "app_secret": "y"},
            behavior="exit",
        )
        assert bot.mode == "test"


class TestSafeRunCrashSemantics:
    """_safe_run 崩溃语义：不重置 _is_running，保留僵尸态供 Watchdog 检测。"""

    def test_crashed_bot_becomes_zombie(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="crash")
        bot.start()
        # 等待子线程退出（crash 立即抛异常）
        bot._thread.join(timeout=1.0) if bot._thread else None

        # 关键断言：崩溃后 _is_running 仍为 True，但线程已死 → 僵尸态
        assert bot._is_running is True
        assert bot.is_running is False
        assert bot.is_zombie is True
        assert bot.last_error is not None
        assert "stub crash" in bot.last_error

    def test_blocking_bot_is_running_not_zombie(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="block")
        bot.start()
        try:
            time.sleep(0.1)  # 给子线程启动时间
            assert bot.is_running is True
            assert bot.is_zombie is False
            assert bot.last_error is None
        finally:
            bot.stop()

    def test_stop_sets_is_running_false(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="block")
        bot.start()
        time.sleep(0.1)
        bot.stop()

        # stop() 主动停止：_is_running=False，非僵尸态（区分崩溃与主动停止）
        assert bot._is_running is False
        assert bot.is_running is False
        assert bot.is_zombie is False
        assert bot.stop_called is True

    def test_stop_is_idempotent(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="block")
        bot.start()
        time.sleep(0.1)
        bot.stop()
        bot.stop()  # 二次停止不应抛异常
        assert bot._is_running is False


class TestRestartTracking:
    """Watchdog 退避辅助方法。"""

    def test_record_restart_increments_count_and_sets_ts(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="exit")
        before = time.time()
        bot.record_restart()
        after = time.time()
        assert bot._restart_count == 1
        assert bot._last_restart_ts is not None
        assert before <= bot._last_restart_ts <= after

    def test_should_retry_true_below_limit(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="exit")
        for _ in range(MAX_CONSECUTIVE_RESTARTS - 1):
            bot.record_restart()
        assert bot._restart_count == MAX_CONSECUTIVE_RESTARTS - 1
        assert bot.should_retry() is True

    def test_should_retry_false_at_limit(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="exit")
        for _ in range(MAX_CONSECUTIVE_RESTARTS):
            bot.record_restart()
        assert bot.should_retry() is False

    def test_backoff_grows_exponentially_until_cap(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="exit")
        # count=0 → 1s
        assert bot.restart_backoff_seconds() == BACKOFF_INITIAL_SECONDS
        bot.record_restart()
        # count=1 → 2s
        assert bot.restart_backoff_seconds() == BACKOFF_INITIAL_SECONDS * 2
        bot.record_restart()
        # count=2 → 4s
        assert bot.restart_backoff_seconds() == BACKOFF_INITIAL_SECONDS * 4

        # 推到上限
        for _ in range(20):
            bot.record_restart()
        assert bot.restart_backoff_seconds() == BACKOFF_MAX_SECONDS

    def test_is_within_backoff_false_without_prior_restart(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="exit")
        assert bot.is_within_restart_backoff() is False

    def test_is_within_backoff_true_right_after_restart(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="exit")
        bot.record_restart()
        # 刚重启：必然在 2s 退避窗口内
        assert bot.is_within_restart_backoff() is True

    def test_is_within_backoff_false_after_window(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="exit")
        bot.record_restart()
        # 模拟已过退避窗口：传入未来时间戳
        future = time.time() + bot.restart_backoff_seconds() + 1.0
        assert bot.is_within_restart_backoff(now=future) is False

    def test_reset_restart_count_when_healthy_uptime_exceeds_threshold(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="block")
        bot.record_restart()
        bot.record_restart()
        assert bot._restart_count == 2

        # 启动并模拟 uptime 超过阈值
        bot.start()
        try:
            # 直接篡改 _start_time 模拟长期运行（避免真实等待 5 分钟）
            bot._start_time = time.time() - (UPTIME_RESET_THRESHOLD_SECONDS + 1)
            bot.reset_restart_count_if_healthy()
            assert bot._restart_count == 0
        finally:
            bot.stop()

    def test_reset_restart_count_skipped_when_below_uptime_threshold(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="block")
        bot.record_restart()
        bot.start()
        try:
            # uptime 不足阈值，不清零
            bot._start_time = time.time() - 1.0
            bot.reset_restart_count_if_healthy()
            assert bot._restart_count == 1
        finally:
            bot.stop()

    def test_reset_restart_count_noop_when_count_zero(self, make_stub_bot) -> None:
        bot = make_stub_bot(behavior="exit")
        # 未曾重启：调用清零无副作用
        bot.reset_restart_count_if_healthy()
        assert bot._restart_count == 0
