"""业务枚举定义。

集中维护跨层的业务枚举，避免在路由/服务/前端多处硬编码数字含义。
当前覆盖 VIP 等级：1-9 为常规 VIP，66 为管理员，99 为超级管理员，
0 为普通用户。
"""

from __future__ import annotations

from enum import IntEnum


class VipLevel(IntEnum):
    """VIP 等级枚举。

    - ``NORMAL``(0)：普通用户，无 VIP 权益。
    - ``VIP1`` ~ ``VIP9``：常规 VIP 等级，数字越大权益越高。
    - ``MANAGER``(66)：管理员特殊标记，非业务 VIP，仅用于身份识别。
    - ``SUPER_ADMIN``(99)：超级管理员特殊标记，非业务 VIP，仅用于身份识别。
    """

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


def get_vip_display(level: int | None) -> str:
    """将 vip_level 数值转为展示文案。

    - 0 或 None：``普通用户``
    - 1-9：``VIP1`` ~ ``VIP9``
    - 66：``管理员``
    - 99：``超级管理员``
    - 其他：``普通用户``（兜底，避免脏数据导致前端报错）
    """
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
    return member.name  # VIP1 ~ VIP9
