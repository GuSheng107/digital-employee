"""跨服务共享的管理端权限码。"""

from __future__ import annotations

from enum import StrEnum

# 权限码统一命名格式：模块以 a-z 开头，冒号分隔，如 ``admin:report:manage``。
# 与 frontend/src/constants/access-control.ts、UserPermission 表单校验保持一致。
PERMISSION_CODE_PATTERN = r"^[a-z][a-z0-9_]*:[a-z0-9_:]+$"


class PermissionCode(StrEnum):
    """接口授权与菜单可见性共用的权限码。"""

    USER_MANAGE = "admin:user:manage"
    USER_READONLY = "admin:user:readonly"
    PERMISSION_MANAGE = "admin:permission:manage"
    PERMISSION_READONLY = "admin:permission:readonly"
    INVITE_CODE_MANAGE = "admin:invite_code:manage"
    INVITE_CODE_READONLY = "admin:invite_code:readonly"
    MENU_MANAGE = "admin:menu:manage"
    MENU_READONLY = "admin:menu:readonly"
    DATA_PLATFORM_DASHBOARD = "admin:data_platform:dashboard"
    DATA_PLATFORM_DATA_ITEMS = "admin:data_platform:data_items"
    DATA_PLATFORM_CONFIG = "admin:data_platform:config"
    BOT_MANAGE = "admin:bot:manage"
    BOT_READONLY = "admin:bot:readonly"
    AGENT_MANAGE = "admin:agent:manage"
    AGENT_READONLY = "admin:agent:readonly"
    OBSERVABILITY_LOG_VIEW = "admin:observability:log:view"


def expand_manage_to_readonly(permission_codes: list[str] | set[str]) -> set[str]:
    """把 manage 权限码扩展出对应的 readonly 变体（manage 是 readonly 的超集）。

    仅处理以 ``:manage`` 结尾的权限码，替换为 ``:readonly``；
    其他形态（如数据中台、日志查看等非 manage/readonly 命名）原样保留。

    返回的集合始终包含原始权限码，且不会产生 ``xxx:manage:readonly``
    这类不存在的冗余变体。
    """
    expanded = set(permission_codes)
    for code in permission_codes:
        if code.endswith(":manage"):
            expanded.add(f"{code[: -len('manage')]}readonly")
    return expanded
