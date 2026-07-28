"""菜单管理相关请求/响应 schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MenuItem(BaseModel):
    """菜单信息（扁平结构，含 parent_id 用于前端构建树）。"""

    id: int
    parent_id: int = 0
    menu_type: int = Field(..., description="1=目录 2=菜单 3=按钮")
    title: str
    path: str | None = None
    component: str | None = None
    icon: str | None = None
    permission: str | None = None
    sort: int = 0
    visible: bool = True


class CreateMenuRequest(BaseModel):
    """创建菜单请求。"""

    parent_id: int = Field(default=0, ge=0)
    menu_type: int = Field(..., ge=1, le=3, description="1=目录 2=菜单 3=按钮")
    title: str = Field(..., min_length=1, max_length=64)
    path: str | None = Field(default=None, max_length=255)
    component: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=64)
    permission: str | None = Field(default=None, max_length=128)
    sort: int = Field(default=0, ge=0)
    visible: bool = True


class UpdateMenuRequest(BaseModel):
    """更新菜单请求（所有字段可选，未传不修改）。"""

    parent_id: int | None = Field(default=None, ge=0)
    menu_type: int | None = Field(default=None, ge=1, le=3)
    title: str | None = Field(default=None, min_length=1, max_length=64)
    path: str | None = Field(default=None, max_length=255)
    component: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=64)
    permission: str | None = Field(default=None, max_length=128)
    sort: int | None = Field(default=None, ge=0)
    visible: bool | None = None
