"""Bot 管理编排，实际数据操作由 backend-data 完成。

落库成功后通过 ``X-Internal-Token`` 触发 backend-gateway 热重载，
使新配置立即生效。reload 失败仅记录告警日志（最终一致），不阻塞
CRUD 返回——数据已落库，Gateway 下次重启或人工 reload 仍可收敛。
"""

from __future__ import annotations

from typing import Any, Protocol

from data_client import DataClient, get_data_client
from loguru import logger

from app.core.config import settings

# Gateway reload 请求超时（秒）。CRUD 已落库，reload 仅是触发，超时不应阻塞响应。
_RELOAD_TIMEOUT_SECONDS = 5.0


class HttpPostCallable(Protocol):
    """httpx.post 等同步 POST 调用的最小协议，便于测试注入。"""

    def __call__(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> Any:
        """发起 POST 请求并返回响应对象（需含 status_code 与 text 属性）。"""
        ...


def _default_http_post(
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
) -> Any:
    """默认 reload 实现：经 httpx.post 同步触发 Gateway。"""
    import httpx

    return httpx.post(url, headers=headers, timeout=timeout)


class BotService:
    """Bot 管理代理。

    Args:
        data_client: 数据客户端，默认从 ``get_data_client`` 获取。
        gateway_url: Gateway 基地址，默认读 ``settings.gateway_base_url``。
        internal_token: 服务间内部令牌，默认读 ``settings.internal_admin_token``。
        http_post: 可注入的 POST 调用，便于单测替换 httpx；默认走 ``httpx.post``。
    """

    def __init__(
        self,
        data_client: DataClient | None = None,
        *,
        gateway_url: str | None = None,
        internal_token: str | None = None,
        http_post: HttpPostCallable | None = None,
    ) -> None:
        self._data = data_client or get_data_client()
        self._gateway_url = (
            gateway_url if gateway_url is not None else settings.gateway_base_url
        ).rstrip("/")
        self._internal_token = (
            internal_token if internal_token is not None else settings.internal_admin_token
        )
        self._http_post = http_post or _default_http_post

    def list_bots(self, *, page: int, page_size: int) -> dict[str, Any]:
        """分页查询 Bot 列表。"""
        return self._data.list_bots(page=page, page_size=page_size)

    def create_bot(self, **payload: Any) -> dict[str, Any]:
        """创建 Bot，落库成功后触发 Gateway reload。"""
        result = self._data.create_bot(**payload)
        self._reload_gateway(action="create", bot_id=payload.get("bot_id"))
        return result

    def update_bot(self, *, bot_id: str, **fields: Any) -> dict[str, Any]:
        """更新 Bot 配置，落库成功后触发 Gateway reload。"""
        result = self._data.update_bot(bot_id=bot_id, **fields)
        self._reload_gateway(action="update", bot_id=bot_id)
        return result

    def delete_bot(self, *, bot_id: str) -> dict[str, Any]:
        """软删除 Bot，落库成功后触发 Gateway reload。"""
        result = self._data.delete_bot(bot_id)
        self._reload_gateway(action="delete", bot_id=bot_id)
        return result

    def _reload_gateway(self, *, action: str, bot_id: str | None) -> None:
        """触发 Gateway /api/v1/admin/reload 热重载。

        失败（令牌未配置 / 网络异常 / 非 2xx 响应）仅记录告警日志，
        不抛异常——数据已落库，最终一致即可。

        Args:
            action: 触发 reload 的 CRUD 动作名（create/update/delete），仅用于日志。
            bot_id: 关联 Bot ID，仅用于日志。
        """
        if not self._internal_token:
            logger.warning(
                "[BOT-RELOAD] INTERNAL_ADMIN_TOKEN 未配置，跳过 Gateway reload "
                f"action={action} bot_id={bot_id}"
            )
            return

        url = f"{self._gateway_url}/api/v1/admin/reload"
        try:
            resp = self._http_post(
                url,
                headers={"X-Internal-Token": self._internal_token},
                timeout=_RELOAD_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            logger.warning(
                f"[BOT-RELOAD] Gateway reload 异常 action={action} bot_id={bot_id} "
                f"url={url} error={exc}"
            )
            return

        status_code = getattr(resp, "status_code", None)
        if status_code is None or status_code >= 400:
            body = getattr(resp, "text", "")
            logger.warning(
                f"[BOT-RELOAD] Gateway reload 失败 action={action} bot_id={bot_id} "
                f"status={status_code} body={body}"
            )
            return
        logger.info(
            f"[BOT-RELOAD] Gateway reload 成功 action={action} bot_id={bot_id} "
            f"status={status_code}"
        )
