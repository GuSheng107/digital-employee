"""跨服务共享的管理端权限码。"""

from __future__ import annotations

from enum import StrEnum


class PermissionCode(StrEnum):
    """接口授权与菜单可见性共用的权限码。"""

    USER_MANAGE = "admin:user:manage"
    USER_PERMISSION = "admin:user:permission"
    INVITE_CODE_MANAGE = "admin:invite_code:manage"
    MENU_MANAGE = "admin:menu:manage"
    DATA_PLATFORM_DASHBOARD = "admin:data_platform:dashboard"
    DATA_PLATFORM_DATA_ITEMS = "admin:data_platform:data_items"
    DATA_PLATFORM_CONFIG = "admin:data_platform:config"
