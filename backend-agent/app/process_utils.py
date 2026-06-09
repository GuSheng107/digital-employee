from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def is_process_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False

    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    synchronize = 0x00100000
    process_handle = ctypes.windll.kernel32.OpenProcess(synchronize, 0, pid)
    if not process_handle:
        return False

    try:
        wait_timeout = 0x00000102
        result = ctypes.windll.kernel32.WaitForSingleObject(process_handle, 0)
        return result == wait_timeout
    finally:
        ctypes.windll.kernel32.CloseHandle(process_handle)


def read_pid_file(path: Path) -> int | None:
    if not path.exists():
        return None

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None

    try:
        return int(raw)
    except ValueError:
        return None


def write_pid_file(path: Path, pid: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(pid), encoding="utf-8")


def remove_pid_file(path: Path) -> None:
    if path.exists():
        path.unlink()


def stop_process(pid: int | None) -> bool:
    if not is_process_running(pid):
        return True

    if sys.platform == "win32":
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    # 优雅停止：先发送 SIGTERM，等待后再发送 SIGKILL
    try:
        os.kill(pid, signal.SIGTERM)
        # 等待最多 5 秒让进程优雅退出
        for _ in range(50):
            if not is_process_running(pid):
                return True
            time.sleep(0.1)
        # 如果还在运行，强制终止
        os.kill(pid, signal.SIGKILL)
        # 再次确认
        time.sleep(0.2)
        return not is_process_running(pid)
    except OSError:
        return False
