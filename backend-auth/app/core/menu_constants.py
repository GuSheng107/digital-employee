"""菜单节点类型的统一定义。"""

from __future__ import annotations

from enum import IntEnum


class MenuType(IntEnum):
    """菜单树节点类型。"""

    DIRECTORY = 1
    PAGE = 2
    ACTION = 3
