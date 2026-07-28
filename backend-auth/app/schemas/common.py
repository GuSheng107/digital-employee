"""通用响应模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    """统一 API 响应结构。"""

    success: bool
    message: str = "ok"
    data: Any = None
