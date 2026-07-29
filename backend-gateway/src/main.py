# -*- coding: utf-8 -*-
"""FastAPI 启动入口与 Admin API 路由定义。

提供健康检查端点及用于动态更新/注入/删除 Bot 凭证的 Admin 控制台接口。
"""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import uvicorn
from api_common import ApiException
from auth_utils import PermissionCode
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from nacos_client import NacosClient

from src.core.schemas import (
    BotConfig,
    BotConfigRequest,
    BotStatusResponse,
    HealthResponse,
)
from src.manager import BotManager
from src.utils.auth import close_auth_client, require_permission
from src.utils.data_access import message_bus_client


def _load_service_configuration() -> None:
    """加载本地和 Nacos 服务配置；基础设施凭证不由网关适配。"""
    load_dotenv()
    try:
        nacos_client = NacosClient.from_env_optional()
        if nacos_client is not None:
            nacos_client.load_to_environ()
    except Exception:  # noqa: BLE001
        return


_load_service_configuration()

# 初始化全局 BotManager 实例
manager: BotManager = BotManager(config_path="config/bot.json")


async def _outbound_relay_loop() -> None:
    """经 data-client 长轮询领取消息，并按处理结果 ACK/NACK。"""
    from src.core.hub import hub

    while True:
        receipt_id: str | None = None
        finalized = False
        try:
            claimed = await message_bus_client.claim()
            if claimed is None:
                continue
            raw_receipt = claimed.get("receipt_id")
            payload = claimed.get("payload")
            if not isinstance(raw_receipt, str) or not isinstance(payload, str):
                raise ValueError("backend-data 返回了无效消息租约")
            receipt_id = raw_receipt

            delivered = await hub.consume_outbound_payload(payload)
            if delivered:
                await message_bus_client.acknowledge(receipt_id)
            else:
                await message_bus_client.reject(receipt_id)
            finalized = True
        except asyncio.CancelledError:
            raise
        except Exception:
            message_bus_client.is_available = False
            if receipt_id is not None and not finalized:
                with suppress(Exception):
                    await message_bus_client.reject(receipt_id)
            await asyncio.sleep(message_bus_client.retry_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI 生命周期管理上下文。

    启动时完成以下初始化序列：
    1. 经 data-client 要求 backend-data 核验消息拓扑。
    2. 从配置文件加载机器人并注入主事件循环。
    3. 启动 share 消息租约轮询与 Watchdog 守护线程。
    """
    # 1. backend-data 是唯一消息基础设施持有者；网关只检查 share 契约。
    try:
        await message_bus_client.ensure_ready()
        logger.info("[MESSAGE-RELAY] backend-data 消息能力已就绪。")
    except Exception as exc:
        logger.error(
            "[MESSAGE-RELAY] backend-data 消息能力暂不可用 ({})。"
            "网关将保留 Test 模式并在后台重试。",
            exc,
        )

    # 2. 加载 Bot 配置并注入主事件循环
    main_loop = asyncio.get_running_loop()
    manager.load_from_file()
    manager.inject_main_loop_to_all(main_loop)

    # 3. 启动消息租约轮询和 Watchdog
    relay_task = asyncio.create_task(_outbound_relay_loop())
    manager.start_watchdog()
    try:
        yield
    finally:
        relay_task.cancel()
        with suppress(asyncio.CancelledError):
            await relay_task
        manager.shutdown()
        await message_bus_client.close()
        close_auth_client()


app: FastAPI = FastAPI(
    title="BOT Gateway Service",
    description="智能机器人系统消息侧网关（基础设施经 backend-data 访问）",
    version="3.0.0",
    lifespan=lifespan,
)


@app.exception_handler(ApiException)
async def api_exception_handler(
    _request: Request,
    exc: ApiException,
) -> JSONResponse:
    """统一输出业务错误码与具体错误信息。"""
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_response(),
    )


# CORS 中间件：允许前端管理后台跨域调用 Admin API。
# 默认放行本地开发前端端口（5173），可通过环境变量 CORS_ORIGINS 扩展。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        *(
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "").split(",")
            if origin.strip()
        ),
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
    dependencies=[Depends(require_permission(PermissionCode.BOT_MANAGE))],
)
async def get_bots() -> list[BotStatusResponse]:
    """获取所有 Bot 实例当前的运行详情。

    Returns:
        包含所有 Bot 标识、平台、子线程 ID、运行时间及最后异常信息的列表。
    """
    return manager.get_all_status()


@app.post(
    "/api/v1/admin/bots",
    dependencies=[Depends(require_permission(PermissionCode.BOT_MANAGE))],
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
    return {
        "status": "success",
        "message": f"Bot {req.bot_id} has been added or updated",
    }


@app.delete(
    "/api/v1/admin/bots/{bot_id}",
    dependencies=[Depends(require_permission(PermissionCode.BOT_MANAGE))],
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
