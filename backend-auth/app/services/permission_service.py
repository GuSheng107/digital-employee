"""权限目录查询服务。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.permission import Permission


class PermissionService:
    """提供管理端可选择的规范权限码目录。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_permissions(self) -> list[dict]:
        """按模块、权限码排序返回全部权限定义。"""
        permissions = self._session.scalars(
            select(Permission).order_by(
                Permission.module,
                Permission.code,
                Permission.id,
            )
        ).all()
        return [
            {
                "id": permission.id,
                "code": permission.code,
                "name": permission.name,
                "description": permission.description,
                "module": permission.module,
            }
            for permission in permissions
        ]
