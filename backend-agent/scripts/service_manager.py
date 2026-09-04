"""Windows Agent 后台进程启停管理。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import psutil

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIRECTORY = PROJECT_ROOT / ".runtime"
PID_FILE = RUNTIME_DIRECTORY / "agent.json"
STOP_REQUEST_FILE = RUNTIME_DIRECTORY / "stop.request"
LOG_DIRECTORY = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIRECTORY / "agent.log"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8030
STARTUP_TIMEOUT_SECONDS = 30.0
STOP_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class ProcessRecord:
    """持久化的 Agent 进程身份。"""

    pid: int
    create_time: float
    host: str
    port: int


def _read_record() -> ProcessRecord | None:
    """读取 PID 文件，格式非法时视为无记录。"""
    if not PID_FILE.exists():
        return None
    try:
        payload: Any = json.loads(PID_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        return ProcessRecord(
            pid=int(payload["pid"]),
            create_time=float(payload["create_time"]),
            host=str(payload["host"]),
            port=int(payload["port"]),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError):
        return None


def _write_record(record: ProcessRecord) -> None:
    """原子写入 Agent 进程身份。"""
    RUNTIME_DIRECTORY.mkdir(parents=True, exist_ok=True)
    temporary_path = PID_FILE.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(asdict(record), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, PID_FILE)


def _remove_record() -> None:
    """删除 PID 文件。"""
    PID_FILE.unlink(missing_ok=True)


def _remove_stop_request() -> None:
    """删除可能残留的优雅停止请求。"""
    STOP_REQUEST_FILE.unlink(missing_ok=True)


def _resolve_process(record: ProcessRecord) -> psutil.Process | None:
    """校验 PID、创建时间和启动命令，防止误操作其他进程。"""
    try:
        process = psutil.Process(record.pid)
        if abs(process.create_time() - record.create_time) > 1.0:
            return None
        command_line = process.cmdline()
        expected_entry = (PROJECT_ROOT / "scripts" / "run_server.py").resolve()
        if not any(
            Path(argument).name == "run_server.py" and Path(argument).resolve() == expected_entry
            for argument in command_line
        ):
            return None
        return process
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return None


def _health_url(*, host: str, port: int) -> str:
    """构造服务存活检查地址。"""
    return f"http://{host}:{port}/api/v1/health"


def _is_healthy(*, host: str, port: int) -> bool:
    """检查 Agent 存活端点是否返回 200。"""
    try:
        with urlopen(_health_url(host=host, port=port), timeout=1.0) as response:
            return int(response.status) == 200
    except OSError:
        return False


def _wait_until_healthy(
    process: psutil.Process,
    *,
    host: str,
    port: int,
) -> bool:
    """等待 Agent 健康检查通过或子进程提前退出。"""
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not process.is_running():
            return False
        if _is_healthy(host=host, port=port):
            return True
        time.sleep(0.25)
    return False


def _terminate_process(process: psutil.Process) -> None:
    """终止进程，并在宽限期结束后升级为强制结束。"""
    try:
        process.terminate()
        process.wait(timeout=STOP_TIMEOUT_SECONDS)
    except psutil.TimeoutExpired:
        process.kill()
        process.wait(timeout=STOP_TIMEOUT_SECONDS)
    except psutil.NoSuchProcess:
        pass


def start_service(*, host: str, port: int) -> int:
    """后台启动 Agent 服务。

    Args:
        host: Uvicorn 监听地址。
        port: Uvicorn 监听端口。

    Returns:
        进程退出码，0 表示启动成功。
    """
    existing_record = _read_record()
    if existing_record is not None:
        existing_process = _resolve_process(existing_record)
        if existing_process is not None:
            print(f"Agent 已在运行，PID={existing_record.pid}")
            return 0
        _remove_record()

    _remove_stop_request()

    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "run_server.py"),
        "--host",
        host,
        "--port",
        str(port),
    ]
    creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    popen_kwargs: dict[str, Any] = {
        "cwd": PROJECT_ROOT,
        "stdin": subprocess.DEVNULL,
        "stderr": subprocess.STDOUT,
        "creationflags": creation_flags,
    }
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True

    with LOG_FILE.open("ab") as log_handle:
        process = subprocess.Popen(
            command,
            stdout=log_handle,
            **popen_kwargs,
        )
    tracked_process = psutil.Process(process.pid)
    record = ProcessRecord(
        pid=process.pid,
        create_time=tracked_process.create_time(),
        host=host,
        port=port,
    )
    _write_record(record)

    if _wait_until_healthy(tracked_process, host=host, port=port):
        print(f"Agent 启动成功：http://{host}:{port}，PID={process.pid}")
        print(f"日志文件：{LOG_FILE}")
        return 0

    try:
        _terminate_process(tracked_process)
    finally:
        _remove_record()
        _remove_stop_request()
    print(f"Agent 启动失败，请查看日志：{LOG_FILE}", file=sys.stderr)
    return 1


def stop_service() -> int:
    """安全停止 PID 文件记录的 Agent 服务。"""
    record = _read_record()
    if record is None:
        _remove_record()
        _remove_stop_request()
        print("Agent 未运行")
        return 0

    process = _resolve_process(record)
    if process is None:
        _remove_record()
        _remove_stop_request()
        print("Agent 进程记录已失效，已清理")
        return 0

    try:
        RUNTIME_DIRECTORY.mkdir(parents=True, exist_ok=True)
        STOP_REQUEST_FILE.write_text("stop\n", encoding="utf-8")
        process.wait(timeout=STOP_TIMEOUT_SECONDS)
    except psutil.TimeoutExpired:
        _terminate_process(process)
    except psutil.NoSuchProcess:
        pass
    finally:
        _remove_record()
        _remove_stop_request()
    print(f"Agent 已停止，PID={record.pid}")
    return 0


def _parse_args() -> argparse.Namespace:
    """解析服务管理命令行参数。"""
    parser = argparse.ArgumentParser(description="管理 backend-agent 后台进程")
    parser.add_argument("action", choices=("start", "stop"))
    parser.add_argument("--host", default=os.getenv("AGENT_HOST", DEFAULT_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("AGENT_PORT", str(DEFAULT_PORT))),
    )
    return parser.parse_args()


def main() -> int:
    """执行 Agent 服务启动或停止命令。"""
    arguments = _parse_args()
    if arguments.action == "start":
        return start_service(host=str(arguments.host), port=int(arguments.port))
    return stop_service()


if __name__ == "__main__":
    raise SystemExit(main())
