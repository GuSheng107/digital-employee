from __future__ import annotations

"""Web 管理控制台服务器模块。

创建并运行 FastAPI Web 服务器，提供管理控制台的 SPA 静态资源服务、
API 路由注册、Bot 子进程生命周期管理（启动/停止/监控）、
看门狗自动重启和定时任务调度等功能。
"""

import asyncio
import ctypes
import os
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.asyncio_compat import install_asyncio_exception_filter
from app.auth_middleware import install_auth_middleware
from app.bot_process_manager import BotProcessManager
from app.api_response import install_api_exception_handlers
from app.db.core import initialize_database
from app.db.settings_store import load_settings_from_database
from app.logger import configure_logging, get_logger
from app.routers.auth import router as auth_router
from app.routers.system import router as system_router
from app.routers.bots import router as bots_router
from app.routers.agents import router as agents_router
from app.routers.skills import router as skills_router
from app.routers.mcp import router as mcp_router
from app.routers.chats import router as chats_router
from app.routers.data import router as data_router
from app.routers.tasks import router as tasks_router
from app.routers.feedback import router as feedback_router
from app.task_runtime import ensure_task_runtime
from app.task_scheduler import TaskScheduler
from app.utils import default_database_path
from app.watchdog import BotWatchdog
from agent_runtime.skills_integration import init_memory


def close_console() -> None:
    """关闭当前控制台窗口（仅 Windows）"""
    if os.name == 'nt':
        try:
            # 获取控制台窗口句柄
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32
            console_window = kernel32.GetConsoleWindow()
            if console_window:
                # 发送关闭消息
                user32.PostMessageW(console_window, 0x0010, 0, 0)
        except Exception:
            pass


def create_app(project_root: Path) -> FastAPI:
    """创建并配置 FastAPI 应用实例。

    初始化数据库、加载配置、注册中间件和路由、挂载静态资源，
    并在应用生命周期中启动看门狗和定时任务调度器。

    Args:
        project_root: 项目根目录路径。

    Returns:
        配置完成的 FastAPI 应用实例。
    """
    project_root = project_root.resolve()
    manager = BotProcessManager(project_root)
    logger = get_logger("web_server")
    database_path = default_database_path(project_root)

    initialize_database(database_path)
    ensure_task_runtime(database_path)
    settings = load_settings_from_database(database_path)
    configure_logging(
        settings.logging.level,
        database_path=database_path,
    )

    # ── 双 Token 认证 (Redis，必需) ──
    # 双 Token 认证强依赖 Redis：未配置 redis.url 时服务拒绝启动。
    from app.yaml_config import get_yaml_config
    from app.redis_token_manager import DualTokenManager
    import redis.asyncio as aioredis

    _yaml = get_yaml_config(project_root)
    _redis_url = str(_yaml.get("redis.url") or "").strip()
    if not _redis_url:
        raise RuntimeError(
            "Redis 未配置：双 Token 认证强依赖 Redis，请在 config.yaml 中设置 redis.url 后重启服务。"
        )

    _redis = aioredis.from_url(
        _redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    _at_ttl = int(_yaml.get("redis.at_ttl_seconds") or 10800)
    _rt_ttl = int(_yaml.get("redis.rt_ttl_seconds") or 604800)
    _at_abs = int(_yaml.get("redis.at_absolute_lifetime_seconds") or 86400)
    _rt_grace = int(_yaml.get("redis.rt_grace_seconds") or 900)
    _dual_mgr = DualTokenManager(
        _redis,
        at_ttl_seconds=_at_ttl,
        rt_ttl_seconds=_rt_ttl,
        at_absolute_lifetime_seconds=_at_abs,
        rt_grace_seconds=_rt_grace,
    )
    from app.auth import set_dual_token_manager
    set_dual_token_manager(_dual_mgr)
    logger.info("dual-token auth enabled (Redis)")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_memory(project_root=project_root)
        watchdog = BotWatchdog(manager)
        scheduler = TaskScheduler(database_path, manager, project_root=project_root)
        watchdog.start()
        scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()
            watchdog.stop()
            manager.stop_all()
            if _redis is not None:
                await _redis.aclose()

    app = FastAPI(title="WeCom Bot Agent Console", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.database_path = database_path
    app.state.project_root = project_root
    app.state.manager = manager

    # 中间件执行顺序 (Starlette LIFO)：
    #   请求 → _trace_api_response (生成 trace_id，最外层)
    #        → _guard_api_session (认证 + IP 白名单，复用 trace_id)
    #        → 路由
    # 因此先安装 auth，再安装 trace/exception handlers，使 trace 成为最外层。
    install_auth_middleware(app)
    install_api_exception_handlers(app, database_path=database_path, logger=logger)

    app.include_router(auth_router)
    app.include_router(system_router)
    app.include_router(bots_router)
    app.include_router(agents_router)
    app.include_router(skills_router)
    app.include_router(mcp_router)
    app.include_router(chats_router)
    app.include_router(data_router)
    app.include_router(tasks_router)
    app.include_router(feedback_router)

    mount_web_assets(app, project_root)
    return app


def mount_web_assets(app: FastAPI, project_root: Path) -> None:
    """挂载前端 SPA 静态资源到 FastAPI 应用。

    将 Vue 构建产物（assets、avatars、brand 目录）挂载为静态文件服务，
    并注册通配路由以支持 SPA 的 HTML5 History 模式。

    Args:
        app: FastAPI 应用实例。
        project_root: 项目根目录路径，web/dist 子目录包含前端构建产物。
    """
    dist_dir = project_root / "web" / "dist"
    assets_dir = dist_dir / "assets"
    avatars_dir = dist_dir / "avatars"
    brand_dir = dist_dir / "brand"

    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    if avatars_dir.exists():
        app.mount("/avatars", StaticFiles(directory=avatars_dir), name="avatars")
    if brand_dir.exists():
        app.mount("/brand", StaticFiles(directory=brand_dir), name="brand")

    @app.get("/{full_path:path}", response_model=None)
    def spa(full_path: str):
        index_path = dist_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse(
            "<h1>WeCom Bot Agent Console</h1>"
            "<p>Vue assets are missing. Run <code>npm install</code> and "
            "<code>npm run build</code> in the <code>web</code> directory.</p>"
        )


def run_web_server(
    project_root: Path,
    host: str = "0.0.0.0",
    port: int = 8765,
    open_browser: bool = True,
) -> int:
    """启动 Web 管理控制台服务器。

    创建 FastAPI 应用并通过 uvicorn 运行，可选在启动后自动打开浏览器。
    支持 Ctrl+C 优雅退出，返回退出码。

    Args:
        project_root: 项目根目录路径。
        host: 监听地址，默认为 0.0.0.0。
        port: 监听端口，默认为 8765。
        open_browser: 是否在启动后自动打开浏览器，默认为 True。

    Returns:
        退出码，0 表示正常退出，130 表示被 Ctrl+C 中断。
    """
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is not installed.") from exc

    if open_browser:
        _logger = get_logger("web_server")
        browser_host = "localhost" if host in ("0.0.0.0", "") else host

        def _open_browser() -> None:
            webbrowser.open(f"http://{browser_host}:{port}")
            _logger.info("Browser opened: http://%s:%s", browser_host, port)

        threading.Timer(1.0, _open_browser).start()

    app = create_app(project_root)
    server_config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(server_config)
    app.state.uvicorn_server = server

    async def _serve() -> None:
        if os.name == "nt":
            install_asyncio_exception_filter(
                asyncio.get_running_loop(),
                logger=get_logger("web_server.asyncio"),
            )
        await server.serve()

    try:
        asyncio.run(_serve())
    except KeyboardInterrupt:
        close_console()
        return 130
    close_console()
    return 0
