# -*- coding: utf-8 -*-
"""Admin API 鉴权依赖。

为 ``/api/v1/admin/*`` 路由提供轻量 API Key 校验，避免 Bot 凭证被未授权读写。
"""

import os

from fastapi import Header, HTTPException


async def verify_admin_api_key(
    x_api_key: str | None = Header(default=None),
) -> None:
    """校验请求头 ``X-API-Key`` 是否与服务端配置一致。

    当环境变量 ``GATEWAY_ADMIN_API_KEY`` 未配置时跳过校验，便于本地开发；
    生产环境应通过环境变量显式配置，以保护 Admin 接口。

    Args:
        x_api_key: 请求头 ``X-API-Key`` 的值，缺失或为空表示未携带。

    Raises:
        HTTPException: 当 ``GATEWAY_ADMIN_API_KEY`` 已配置但请求头缺失或不匹配时，
            返回 401 未授权。
    """
    expected = os.getenv("GATEWAY_ADMIN_API_KEY", "").strip()
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid api key")
