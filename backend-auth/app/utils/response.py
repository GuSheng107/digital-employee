"""统一响应构造工具。"""

from __future__ import annotations

from typing import Any


def success_response(data: Any = None, message: str = "ok") -> dict:
    """构造成功响应字典。"""
    return {"success": True, "message": message, "data": data}


def fail_response(message: str = "error", data: Any = None) -> dict:
    """构造失败响应字典。"""
    return {"success": False, "message": message, "data": data}
