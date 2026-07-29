"""认证与授权域的跨服务常量。

这些值同时被 backend-auth 与 backend-data 使用，集中放在共享包中，
避免角色、菜单类型、VIP 等级和邀请码规则在不同服务间漂移。
"""

from __future__ import annotations

from enum import IntEnum


class MenuType(IntEnum):
    """菜单树节点类型。"""

    DIRECTORY = 1
    PAGE = 2
    ACTION = 3


class VipLevel(IntEnum):
    """VIP 与管理身份等级。"""

    NORMAL = 0
    VIP1 = 1
    VIP2 = 2
    VIP3 = 3
    VIP4 = 4
    VIP5 = 5
    VIP6 = 6
    VIP7 = 7
    VIP8 = 8
    VIP9 = 9
    MANAGER = 66
    SUPER_ADMIN = 99


ROLE_CODE_USER = "user"
ROLE_CODE_MANAGER = "manager"
ROLE_CODE_SUPER_ADMIN = "super_admin"

ADMIN_ROLE_CODES = frozenset({ROLE_CODE_SUPER_ADMIN, ROLE_CODE_MANAGER})
FULL_ACCESS_ROLE_CODES = frozenset({ROLE_CODE_SUPER_ADMIN})
PROTECTED_ROLE_CODES = frozenset({ROLE_CODE_SUPER_ADMIN})
BUSINESS_VIP_LEVELS = tuple(level for level in VipLevel if VipLevel.VIP1 <= level <= VipLevel.VIP9)

INVITE_CODE_MIN_LENGTH = 4
INVITE_CODE_MAX_LENGTH = 32
INVITE_CODE_GENERATED_LENGTH = 8
INVITE_CODE_ALLOWED_PATTERN = r"^[A-Z0-9_-]+$"
AVATAR_MAX_SIZE_BYTES = 3 * 1024 * 1024
AVATAR_CONTENT_TYPES = frozenset(
    {
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)
USER_PROFILE_ROUTE_PATH = "/system/user/profile"


def get_vip_display(level: int | None) -> str:
    """将 VIP 数值转换为统一展示文案。"""
    if level is None:
        return "普通用户"
    try:
        member = VipLevel(level)
    except ValueError:
        return "普通用户"
    if member is VipLevel.MANAGER:
        return "管理员"
    if member is VipLevel.SUPER_ADMIN:
        return "超级管理员"
    if member is VipLevel.NORMAL:
        return "普通用户"
    return member.name


def is_business_vip_level(level: int | None) -> bool:
    """判断等级是否属于可配置的业务 VIP1-VIP9。"""
    if level is None:
        return False
    try:
        return VipLevel(level) in BUSINESS_VIP_LEVELS
    except ValueError:
        return False


def detect_avatar_content_type(content: bytes) -> str | None:
    """根据文件签名识别允许的头像格式。"""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if (
        len(content) >= 12
        and content.startswith(b"RIFF")
        and content[8:12] == b"WEBP"
    ):
        return "image/webp"
    return None
