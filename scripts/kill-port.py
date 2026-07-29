#!/usr/bin/env python3
"""跨平台端口进程清理工具。

按端口查找占用进程并强制结束，默认覆盖项目现有服务的端口。
支持 Windows 与 Unix（依赖 netstat / lsof）。

Usage:
    python kill-port.py              # 清理全部默认服务端口
    python kill-port.py 8020 5173    # 仅清理指定端口
"""

from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Sequence

# 默认服务端口（须与 start 脚本中的端口一致）
DEFAULT_PORTS: dict[int, str] = {
    8864: "backend-gateway",
    8010: "backend-data",
    8020: "backend-auth",
    5173: "frontend",
}

IS_WINDOWS: bool = sys.platform == "win32"

logger = logging.getLogger("kill-port")


def _run(cmd: Sequence[str]) -> tuple[str, str]:
    """运行子命令并返回 (stdout, stderr)。

    在 Windows 下抑制控制台弹窗。

    Args:
        cmd: 命令及其参数列表。

    Returns:
        二元组 (标准输出, 标准错误)，已按 replace 错误处理解码为文本。
    """
    kwargs: dict[str, object] = {"capture_output": True, "text": True, "errors": "replace"}
    if IS_WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
    result = subprocess.run(list(cmd), **kwargs)  # type: ignore[arg-type]
    return result.stdout, result.stderr


def find_pids(port: int) -> set[str]:
    """返回占用指定端口的进程 PID 集合。

    Args:
        port: 目标端口号。

    Returns:
        PID 字符串集合，可能为空集。
    """
    if IS_WINDOWS:
        return _find_pids_windows(port)
    return _find_pids_unix(port)


def _find_pids_windows(port: int) -> set[str]:
    """Windows 下通过 netstat 获取占用端口的 PID 集合。"""
    stdout, _ = _run(["netstat", "-ano"])
    pids: set[str] = set()
    suffix = f":{port}"
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        if parts[0].upper() == "TCP" and parts[3].upper() != "LISTENING":
            continue
        local_addr = parts[1]
        if not local_addr.endswith(suffix):
            continue
        pid = parts[-1]
        if pid.isdigit() and pid != "0":
            pids.add(pid)
    return pids


def _find_pids_unix(port: int) -> set[str]:
    """Unix 下通过 lsof 获取占用端口的 PID 集合。"""
    stdout, _ = _run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"])
    pids: set[str] = set()
    for line in stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.add(line)
    return pids


def kill_pid(pid: str) -> None:
    """按 PID 强制结束进程。

    Args:
        pid: 目标进程的 PID 字符串。
    """
    if IS_WINDOWS:
        _run(["taskkill", "/PID", pid, "/F"])
    else:
        _run(["kill", "-9", pid])


def kill_port(port: int, label: str = "") -> int:
    """查找并结束占用指定端口的进程。

    Args:
        port: 目标端口号。
        label: 端口对应的业务标签，仅用于日志展示。

    Returns:
        被结束的进程数量。
    """
    label_text = f" ({label})" if label else ""
    pids = find_pids(port)
    if not pids:
        logger.info("Port %s%s: no process found", port, label_text)
        return 0
    for pid in sorted(pids):
        kill_pid(pid)
        logger.info("Port %s%s: killed PID %s", port, label_text, pid)
    return len(pids)


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    Args:
        argv: 命令行参数列表，默认取 sys.argv[1:]。

    Returns:
        进程退出码，0 表示成功。
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    args = list(argv) if argv is not None else sys.argv[1:]
    if args:
        try:
            ports = [(int(arg), "") for arg in args]
        except ValueError:
            logger.error("Error: port arguments must be integers")
            return 1
    else:
        ports = [(port, label) for port, label in DEFAULT_PORTS.items()]

    logger.info("Killing processes on %d port(s)...\n", len(ports))

    total_killed = 0
    for port, label in ports:
        total_killed += kill_port(port, label)

    logger.info("\nDone! Killed %d process(es).", total_killed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
