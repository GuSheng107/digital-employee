"""DataClient 异常重建测试。

验证 _raise_response_error 按 backend-data 返回的错误码重建对应异常子类，
使调用方可按异常类型分支处理（如迁移脚本捕获 DuplicateResourceError 做跳过
而非视为失败）。
"""

from __future__ import annotations

import httpx
import pytest
from api_common import (
    ApiException,
    DuplicateResourceError,
    ResourceNotFoundError,
)

from data_client.client import DataClient


def _make_body(*, code: str, message: str) -> dict:
    """构造 backend-data 错误响应信封。"""
    return {
        "success": False,
        "message": message,
        "data": {"code": code, "detail": ""},
    }


def test_duplicate_resource_error_reconstructed() -> None:
    """409 + DUPLICATE_RESOURCE 应重建为 DuplicateResourceError。"""
    response = httpx.Response(status_code=409)
    body = _make_body(code="DUPLICATE_RESOURCE", message="Bot 'x' 已存在")
    with pytest.raises(DuplicateResourceError) as exc_info:
        DataClient._raise_response_error(response, body=body)
    assert exc_info.value.http_status == 409
    assert "已存在" in exc_info.value.message


def test_resource_not_found_reconstructed() -> None:
    """404 + RESOURCE_NOT_FOUND 应重建为 ResourceNotFoundError。"""
    response = httpx.Response(status_code=404)
    body = _make_body(code="RESOURCE_NOT_FOUND", message="Bot 'x' 不存在")
    with pytest.raises(ResourceNotFoundError):
        DataClient._raise_response_error(response, body=body)


def test_unknown_code_falls_back_to_api_exception() -> None:
    """未知错误码应回落到 ApiException 基类（非子类）。"""
    response = httpx.Response(status_code=400)
    body = _make_body(code="SOME_UNKNOWN_CODE", message="未知错误")
    with pytest.raises(ApiException) as exc_info:
        DataClient._raise_response_error(response, body=body)
    assert type(exc_info.value) is ApiException
