"""FastAPI 通用依赖。

提供 API Key 认证依赖，用于保护非健康检查类端点。
"""

import secrets

from fastapi import Header, HTTPException

from app.core.config import settings


async def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """校验请求头 ``X-API-Key`` 是否与服务端配置一致。

    当 ``API_KEY`` 未配置时跳过校验，便于本地开发；
    生产环境应通过环境变量显式配置 ``API_KEY``。

    使用 ``secrets.compare_digest`` 进行常量时间比较，避免时序攻击。

    Args:
        x_api_key: 请求头 ``X-API-Key`` 的值，缺失或为空表示未携带。

    Raises:
        HTTPException: 当 ``API_KEY`` 已配置但请求头缺失或不匹配时，
            返回 401 未授权。
    """
    expected = settings.api_key
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="invalid api key")
