"""角色管理相关请求/响应 schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RoleItem(BaseModel):
    """角色信息。"""

    id: int
    code: str
    name: str
    description: str = ""
    is_builtin: bool = False
    menu_ids: list[int] = Field(default_factory=list)


class CreateRoleRequest(BaseModel):
    """创建角色请求。"""

    code: str = Field(..., min_length=2, max_length=64, description="角色代码，唯一")
    name: str = Field(..., min_length=1, max_length=64, description="角色名称")
    description: str = Field(default="", max_length=255, description="角色描述")
    menu_ids: list[int] = Field(default_factory=list, description="关联菜单 ID 列表")


class UpdateRoleRequest(BaseModel):
    """更新角色请求。

    ``code`` 不可修改（作为业务唯一标识）。内置角色仅允许修改描述与菜单。
    """

    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    menu_ids: list[int] | None = Field(default=None, description="为空表示不修改菜单")


class AssignMenusRequest(BaseModel):
    """分配角色菜单请求。"""

    menu_ids: list[int] = Field(default_factory=list)
