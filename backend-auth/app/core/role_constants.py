"""角色代码与角色集合的统一定义。

角色代码属于跨认证、授权、用户与角色管理模块共享的领域常量，
统一放在核心层，避免各服务散落字符串字面量后产生规则漂移。
"""

from __future__ import annotations

ROLE_CODE_USER = "user"
ROLE_CODE_MANAGER = "manager"
ROLE_CODE_SUPER_ADMIN = "super_admin"

ADMIN_ROLE_CODES = frozenset({ROLE_CODE_SUPER_ADMIN, ROLE_CODE_MANAGER})
FULL_ACCESS_ROLE_CODES = frozenset({ROLE_CODE_SUPER_ADMIN})
PROTECTED_ROLE_CODES = frozenset({ROLE_CODE_SUPER_ADMIN})
