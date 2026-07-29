"""菜单更新与权限同步回归测试。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.services.identity_menu_service import MenuService


class _MenuSession:
    """实现菜单更新所需的最小 Session 协议。"""

    def __init__(self, menu: Any) -> None:
        self.menu = menu
        self.committed = False

    def get(self, _model: Any, _object_id: int) -> Any:
        return self.menu

    def scalar(self, _statement: Any) -> None:
        return None

    def commit(self) -> None:
        self.committed = True


def test_menu_update_can_explicitly_clear_nullable_fields() -> None:
    """显式 null 必须清空旧值，而不是被误判为字段未传。"""
    menu = SimpleNamespace(
        id=7,
        parent_id=0,
        menu_type=1,
        title="系统",
        path="/system",
        component="system/index",
        icon="SettingOutlined",
        permission="admin:menu:manage",
        sort=10,
        visible=True,
        deleted_at=None,
    )
    session = _MenuSession(menu)

    result = MenuService(session).update_menu(
        menu_id=7,
        updates={
            "path": None,
            "component": None,
            "icon": None,
            "permission": None,
        },
    )

    assert result["path"] is None
    assert result["component"] is None
    assert result["icon"] is None
    assert result["permission"] is None
    assert session.committed is True
