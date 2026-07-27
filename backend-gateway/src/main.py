# -*- coding: utf-8 -*-
"""FastAPI 启动入口与 Admin API 路由定义。

提供健康检查端点及用于动态更新/注入/删除 Bot 凭证的 Admin 控制台接口。
"""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# 启动时尽早加载 .env，让 Nacos 凭证（NACOS_*）可被 NacosClient 读到。
# 必须在 import 业务模块（src.utils.minio_client 等）之前完成，
# 因为这些模块在 import 时就会读环境变量。
load_dotenv()

# 从 Nacos 拉取共享基础设施配置并注入 os.environ，优先级高于本地 .env。
# 失败时静默降级（缺凭证/包未安装/网络异常都仅打日志），不阻塞启动。

from nacos_client import adapter as nacos_adapter


def _adapt_nacos_to_gateway_env() -> None:
    """把 Nacos 拍平的 key 适配到 backend-gateway 期望的字段名。

    Nacos dev.yaml 用嵌套结构（minio.host / rabbitmq.host 等），
    NacosClient.load_to_environ 拍平后注入 MINIO_HOST / RABBITMQ_HOST 等。
    backend-gateway 代码用 os.getenv 读 MINIO_ENDPOINT / RABBITMQ_URL 等，
    需要这层适配转换。

    Nacos 优先级高于本地 .env：src 存在时覆盖 dst，确保 Nacos 配置生效。
    本地调试时设 NACOS_SERVER_ADDR 为空可跳过 Nacos 拉取，回退到 .env。
    """
    # MinIO: host + api_port -> endpoint
    nacos_adapter.compose_endpoint("MINIO_HOST", "MINIO_API_PORT", "MINIO_ENDPOINT")
    nacos_adapter.copy_overwrite("MINIO_USERNAME", "MINIO_ACCESS_KEY")
    nacos_adapter.copy_overwrite("MINIO_PASSWORD", "MINIO_SECRET_KEY")
    # RabbitMQ: host + amqp_port + user + pass -> url（凭证 URL 编码在 adapter 内处理）
    nacos_adapter.compose_rabbitmq_url()


try:
    from nacos_client import NacosClient

    _nacos_client = NacosClient.from_env_optional(default_data_id="dev.yaml")
    if _nacos_client is not None:
        _nacos_client.load_to_environ()
        _adapt_nacos_to_gateway_env()
except Exception as _nacos_exc:  # noqa: BLE001
    # 捕获所有异常（含 ImportError / NacosClient 内部异常 / YAML 解析异常），
    # 统一降级到本地配置，避免任一环节失败阻断服务启动。
    import logging
    logging.getLogger("nacos_client").warning(
        "[Nacos] 初始化失败 (%s: %s)，降级到本地配置。",
        type(_nacos_exc).__name__,
        _nacos_exc,
    )


import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from loguru import logger

from src.core.schemas import (
    BotConfig,
    BotConfigRequest,
    BotStatusResponse,
    HealthResponse,
)
from src.manager import BotManager
from src.utils.auth import verify_admin_api_key
from src.utils.rabbitmq import mq_client

# 配置日志输出到文件
logger.add(
    "log/backend-gateway.log",
    rotation="10 MB",
    retention="7 days",
    encoding="utf-8",
    enqueue=True,
)

# 初始化全局 BotManager 实例
manager: BotManager = BotManager(config_path="config/bot.json")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI 生命周期管理上下文。

    启动时完成以下初始化序列：
    1. 建立 RabbitMQ 连接并声明拓扑结构。
    2. 注册 MQ 出站队列消费者回调。
    3. 从配置文件加载机器人并注入主事件循环。
    4. 启动 Watchdog 守护线程。
    """
    # 1. 尝试连接 RabbitMQ 并声明拓扑，失败则容错降级
    try:
        outbound_queue = await mq_client.connect_and_setup()
        # 2. 注册出站队列消费者（由 hub 处理 Agent 回复）
        from src.core.hub import hub
        await outbound_queue.consume(hub.consume_outbound)
        logger.info("[MQ] RabbitMQ 消费者注册成功，生产模式就绪。")
    except Exception as exc:
        logger.error(
            "[MQ] 警告：RabbitMQ 连接或初始化失败 ({})。网关将降级运行：所有 Prod 模式 Bot 的消息发送可能受阻，Test 模式 Bot 仍可正常运行。",
            exc,
        )

    # 3. 启动后台重连与连接状态监控守护协程（每分钟执行一次检测重连）
    async def _mq_reconnect_loop():
        from src.core.hub import hub
        while True:
            try:
                await asyncio.sleep(60.0)
                if not mq_client.is_connected:
                    logger.info("[MQ] 检测到 RabbitMQ 当前处于断开状态，尝试自动重连中...")
                    outbound_queue = await mq_client.connect_and_setup()
                    await outbound_queue.consume(hub.consume_outbound)
                    logger.info("[MQ] RabbitMQ 自动重连成功并已重新订阅出站队列！")
            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.error("[MQ] RabbitMQ 自动重连尝试失败，60秒后将再次重试: {}", err)

    reconnect_task = asyncio.create_task(_mq_reconnect_loop())

    # 4. 加载 Bot 配置并注入主事件循环
    main_loop = asyncio.get_running_loop()
    manager.load_from_file()
    manager.inject_main_loop_to_all(main_loop)

    # 5. 启动 Watchdog
    manager.start_watchdog()
    try:
        yield
    finally:
        # 服务关闭时清理
        reconnect_task.cancel()
        manager.shutdown()
        await mq_client.close()


app: FastAPI = FastAPI(
    title="BOT Gateway Service",
    description="智能机器人系统消息侧网关（三期：RabbitMQ 双模路由）",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS 中间件：允许前端管理后台跨域调用 Admin API。
# 默认放行本地开发前端端口（5173），可通过环境变量 CORS_ORIGINS 扩展。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        *(origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()),
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


@app.get("/api/v1/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """健康检查端点，实时返回系统状态及所有活跃 Bot 的状态详情。

    Returns:
        系统的健康状态及各 Bot 运行详情。
    """
    bots_status: list[BotStatusResponse] = manager.get_all_status()
    active_count: int = sum(1 for bot in bots_status if bot.is_running)

    return HealthResponse(
        status="ok",
        active_bots=active_count,
        bots=bots_status,
    )


@app.get(
    "/api/v1/admin/bots",
    response_model=list[BotStatusResponse],
    dependencies=[Depends(verify_admin_api_key)],
)
async def get_bots() -> list[BotStatusResponse]:
    """获取所有 Bot 实例当前的运行详情。

    Returns:
        包含所有 Bot 标识、平台、子线程 ID、运行时间及最后异常信息的列表。
    """
    return manager.get_all_status()


@app.post(
    "/api/v1/admin/bots",
    dependencies=[Depends(verify_admin_api_key)],
)
async def add_or_update_bot(req: BotConfigRequest) -> dict[str, str]:
    """动态添加或更新 Bot 凭证。

    若 Bot 已存在且凭证或配置变更，将触发底层长连接热重启。

    Args:
        req: 动态注入 Bot 的配置请求体。

    Returns:
        更新状态字典。
    """
    bot_cfg = BotConfig(
        bot_id=req.bot_id,
        platform=req.platform,
        mode=req.mode,
        app_id=req.app_id,
        app_secret=req.app_secret,
    )
    manager.add_or_update_bot(bot_cfg)
    return {"status": "success", "message": f"Bot {req.bot_id} has been added or updated"}


@app.delete(
    "/api/v1/admin/bots/{bot_id}",
    dependencies=[Depends(verify_admin_api_key)],
)
async def delete_bot(bot_id: str) -> dict[str, str]:
    """销毁并注销指定的 Bot 实例，断开其与平台的长连接。

    Args:
        bot_id: 待销毁的 Bot 唯一标识。

    Returns:
        销毁状态字典。

    Raises:
        HTTPException: 若对应的 Bot 不存在，则返回 404 错误。
    """
    success: bool = manager.remove_bot(bot_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Bot with id '{bot_id}' not found",
        )
    return {"status": "success", "message": f"Bot {bot_id} has been removed"}


if __name__ == "__main__":
    port = int(os.getenv("GATEWAY_PORT", os.getenv("PORT", "8864")))
    # 生产部署时建议通过 CLI 传入 reload 配置，此处硬编码 reload=False 以防主线程重载导致子线程混乱
    uvicorn.run("src.main:app", host="0.0.0.0", port=port, reload=False)
