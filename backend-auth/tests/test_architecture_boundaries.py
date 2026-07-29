"""服务职责边界回归测试。"""

from __future__ import annotations

import re
from pathlib import Path

AUTH_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_INFRA_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+" r"(?:sqlalchemy|redis|minio|aio_pika|pika)(?:\.|\s|$)",
    re.MULTILINE,
)


def test_backend_auth_does_not_import_infrastructure_clients() -> None:
    """认证服务不得直接导入数据库、缓存、对象存储或 MQ 客户端。"""
    violations: list[str] = []
    for source_path in (AUTH_ROOT / "app").rglob("*.py"):
        if FORBIDDEN_INFRA_IMPORT.search(source_path.read_text(encoding="utf-8")):
            violations.append(str(source_path.relative_to(AUTH_ROOT)))

    assert violations == []


def test_backend_auth_dependencies_do_not_include_infrastructure_drivers() -> None:
    """认证服务依赖表不得重新引入基础设施驱动。"""
    pyproject = (AUTH_ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    forbidden_packages = (
        "sqlalchemy",
        "psycopg2",
        '"redis',
        '"minio',
        "aio-pika",
        '"pika',
    )

    assert [package for package in forbidden_packages if package in pyproject] == []
