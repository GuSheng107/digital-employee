"""权限码管理相关请求/响应 schema。"""

from __future__ import annotations

from auth_utils import PERMISSION_CODE_PATTERN
from pydantic import BaseModel, Field, field_validator


class PermissionItem(BaseModel):
    """权限码目录项。"""

    id: int
    code: str
    name: str
    description: str = ""
    module: str | None = None


class CreatePermissionRequest(BaseModel):
    """动态创建权限码请求。"""

    code: str = Field(
        ...,
        min_length=3,
        max_length=128,
        pattern=PERMISSION_CODE_PATTERN,
        description="权限码，如 admin:report:manage",
    )
    name: str = Field(..., min_length=1, max_length=64, description="权限码名称")
    description: str = Field(default="", max_length=255, description="权限码描述")
    module: str | None = Field(default=None, max_length=32, description="所属模块")

    @field_validator("code", mode="before")
    @classmethod
    def strip_code(cls, value: object) -> object:
        """去除权限码首尾空白，避免与前端规范化结果不一致。"""
        if isinstance(value, str):
            return value.strip()
        return value
