# -*- coding: utf-8 -*-
"""FastAPI 启动入口与 Admin API 路由定义。

提供健康检查端点及用于动态更新/注入/删除 Bot 凭证的 Admin 控制台接口。
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException

from loguru import logger

from src.core.schemas import (
    BotConfig,
    BotConfigRequest,
    BotStatusResponse,
    HealthResponse,
)
from src.manager import BotManager

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
async def lifespan(app: FastAPI):
    """FastAPI 生命周期管理上下文。

    在 FastAPI 启动时从配置文件加载机器人并开启 Watchdog，
    在服务关闭时释放所有的网络长连接与子线程资源。
    """
    # 启动前初始化
    manager.load_from_file()
    manager.start_watchdog()
    yield
    # 服务关闭时清理
    manager.shutdown()


app: FastAPI = FastAPI(
    title="BOT Gateway Service",
    description="智能机器人系统消息侧网关一期",
    version="1.0.0",
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


@app.get("/api/v1/admin/bots", response_model=list[BotStatusResponse])
async def get_bots() -> list[BotStatusResponse]:
    """获取所有 Bot 实例当前的运行详情。

    Returns:
        包含所有 Bot 标识、平台、子线程 ID、运行时间及最后异常信息的列表。
    """
    return manager.get_all_status()


@app.post("/api/v1/admin/bots")
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
        app_id=req.app_id,
        app_secret=req.app_secret,
    )
    manager.add_or_update_bot(bot_cfg)
    return {"status": "success", "message": f"Bot {req.bot_id} has been added or updated"}


@app.delete("/api/v1/admin/bots/{bot_id}")
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
    # 生产部署时建议通过 CLI 传入 reload 配置，此处硬编码 reload=False 以防主线程重载导致子线程混乱
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False)
