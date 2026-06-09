from __future__ import annotations

"""WeCom Bot Agent 入口模块。

根据命令行参数决定启动模式：
- Web 管理控制台模式（默认）：启动 FastAPI Web 服务器，提供 Bot 管理界面
- Bot 长连接模式（--run-bot）：启动企微 WebSocket 长连接，接收并处理用户消息
"""

import argparse
import asyncio
import os
import platform
import ssl
import sys
from pathlib import Path

from app.asyncio_compat import install_asyncio_exception_filter
from app.config_loader import Settings, validate_settings
from app.db.bot_store import get_bot_runtime_settings
from app.db.core import initialize_database
from app.utils import default_database_path
from app.logger import configure_logging, get_logger
from app.process_utils import remove_pid_file, write_pid_file
from app.web_server import run_web_server
from wecom_bot.long_connection import run_long_connection


def fix_dashscope_http_error_compatibility() -> None:
    """修复 DashScope 响应对象与 requests.exceptions.HTTPError 兼容性问题。"""
    try:
        import langchain_community.llms.tongyi as tongyi_llm
        import langchain_community.chat_models.tongyi as tongyi_chat

        def _check_response(resp):
            if resp.status_code == 200:
                return resp
            raise RuntimeError(
                f"通义千问 API 错误: status_code={resp.status_code}, "
                f"code={resp.get('code')}, message={resp.get('message')}"
            )

        tongyi_llm.check_response = _check_response
        tongyi_chat.check_response = _check_response
    except Exception:
        pass


def fix_mac_ssl_certificates() -> None:
    """
    修复Mac系统上Python SSL证书验证失败问题。
    针对 [SSL: CERTIFICATE_VERIFY_FAILED] 错误的解决方案。
    """
    if platform.system() != "Darwin":
        return
    
    try:
        import certifi
        cert_path = certifi.where()
        os.environ["SSL_CERT_FILE"] = cert_path
        os.environ["REQUESTS_CA_BUNDLE"] = cert_path
        print(f"已配置SSL证书路径: {cert_path}")
    except ImportError:
        print("警告: certifi库未安装，请运行: pip install certifi")


def pid_file_path(bot_key: str) -> Path:
    clean_key = "".join(char for char in bot_key if char.isalnum() or char in {"_", "-"})
    return Path("data") / f"bot-{clean_key or 'bot'}.pid"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WeCom bot controller")
    parser.add_argument(
        "--run-bot",
        action="store_true",
        help="Run the bot service instead of the controller UI.",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root directory. Defaults to current directory.",
    )
    parser.add_argument(
        "--parent-pid",
        type=int,
        default=0,
        help="Parent UI process id for child-process lifecycle management.",
    )
    parser.add_argument(
        "--bot-key",
        default="",
        help="Bot config key for multi-bot worker mode.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Web server host. Defaults to 0.0.0.0.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Web server port. Defaults to 8765.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open browser automatically.",
    )
    return parser.parse_args()


async def async_bot_main(
    settings: Settings,
    parent_pid: int,
    project_root: Path,
    bot_key: str,
) -> None:
    loop = asyncio.get_running_loop()
    if os.name == "nt":
        install_asyncio_exception_filter(loop, logger=get_logger("main.asyncio"))
    if settings.wecom_bot.mode != "long_connection":
        raise NotImplementedError("Only long_connection mode is implemented in this phase.")

    await run_long_connection(
        settings,
        parent_pid=parent_pid or None,
        project_root=project_root,
        bot_key=bot_key,
    )


def run_bot(args: argparse.Namespace) -> int:
    try:
        project_root = Path(args.project_root).resolve()
        database_path = default_database_path(project_root)
        initialize_database(database_path)
        configure_logging("INFO", database_path=database_path)
        settings = get_bot_runtime_settings(
            database_path,
            bot_key=args.bot_key,
        )
        validate_settings(settings, require_bot_credentials=True)
        configure_logging(
            settings.logging.level,
            database_path=database_path,
        )
        provider = settings.agent.providers.get(settings.agent.provider)
        if provider and provider.type == "dashscope":
            fix_dashscope_http_error_compatibility()
        current_pid_file = pid_file_path(args.bot_key)
        write_pid_file(current_pid_file, os.getpid())
        asyncio.run(async_bot_main(settings, args.parent_pid, project_root, args.bot_key))
    except KeyboardInterrupt:
        return 130
    except Exception:
        get_logger("main").exception("Bot service exited with an error.")
        return 1
    finally:
        remove_pid_file(pid_file_path(args.bot_key))
    return 0


def main() -> int:
    # 启动时尝试修复Mac SSL证书问题
    fix_mac_ssl_certificates()
    
    args = parse_args()

    if args.run_bot:
        return run_bot(args)

    project_root = Path(args.project_root).resolve()
    return run_web_server(
        project_root,
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
    )


if __name__ == "__main__":
    raise SystemExit(main())
