"""支持 Windows 优雅停止的 Uvicorn 运行入口。"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import suppress
from pathlib import Path

import uvicorn

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STOP_REQUEST_FILE = PROJECT_ROOT / ".runtime" / "stop.request"
STOP_POLL_INTERVAL_SECONDS = 0.2


async def _watch_stop_request(server: uvicorn.Server) -> None:
    """监听停止文件，并通知 Uvicorn 执行优雅关闭。"""
    while not server.should_exit:
        if STOP_REQUEST_FILE.exists():
            server.should_exit = True
            return
        await asyncio.sleep(STOP_POLL_INTERVAL_SECONDS)


async def serve(*, host: str, port: int) -> int:
    """运行 Uvicorn，并在收到本地停止请求时完成生命周期清理。"""
    config = uvicorn.Config(
        "app.main:app",
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    watcher = asyncio.create_task(_watch_stop_request(server))
    try:
        await server.serve()
    finally:
        watcher.cancel()
        with suppress(asyncio.CancelledError):
            await watcher
        STOP_REQUEST_FILE.unlink(missing_ok=True)
    return 0 if server.started else 1


def _parse_args() -> argparse.Namespace:
    """解析 Uvicorn 监听参数。"""
    parser = argparse.ArgumentParser(description="运行 backend-agent 服务")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    return parser.parse_args()


def main() -> int:
    """启动支持本地停止请求的 Agent 服务。"""
    arguments = _parse_args()
    return asyncio.run(serve(host=str(arguments.host), port=int(arguments.port)))


if __name__ == "__main__":
    raise SystemExit(main())
