# -*- coding: utf-8 -*-
"""FastAPI 启动入口与 Admin API 路由定义。

提供健康检查端点及用于动态更新/注入/删除 Bot 凭证的 Admin 控制台接口。
"""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, HTTPException

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
