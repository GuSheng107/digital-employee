"""跨服务基础设施与鉴权边界回归测试。"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_ROOT = PROJECT_ROOT / "backend-gateway"
FORBIDDEN_INFRA_MODULES = {
    "aio_pika",
    "asyncpg",
    "minio",
    "pika",
    "psycopg",
    "psycopg2",
    "redis",
    "sqlalchemy",
}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.partition(".")[0])
    return imported


def test_gateway_does_not_import_infrastructure_drivers() -> None:
    """网关只能经 backend-share 调用基础设施。"""
    violations: list[str] = []
    for path in (GATEWAY_ROOT / "src").rglob("*.py"):
        forbidden = _imported_roots(path) & FORBIDDEN_INFRA_MODULES
        if forbidden:
            violations.append(f"{path.relative_to(GATEWAY_ROOT)}: {sorted(forbidden)}")
    assert not violations, "\n".join(violations)


def test_gateway_dependencies_exclude_infrastructure_drivers() -> None:
    """网关依赖清单不得重新引入 DB、Redis、MinIO 或 MQ 驱动。"""
    config = tomllib.loads(
        (GATEWAY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    dependencies = config["project"]["dependencies"]
    dependency_names = {
        dependency.split("=", 1)[0].split("[", 1)[0].lower()
        for dependency in dependencies
    }
    assert dependency_names.isdisjoint(
        {
            "aio-pika",
            "asyncpg",
            "minio",
            "pika",
            "psycopg",
            "psycopg2-binary",
            "redis",
            "sqlalchemy",
        }
    )
    assert {"auth-utils", "data-client"}.issubset(dependency_names)


def test_gateway_admin_api_uses_shared_auth_permission() -> None:
    """管理接口不得回退为网关本地 API Key 鉴权。"""
    source = (GATEWAY_ROOT / "src" / "main.py").read_text(encoding="utf-8")
    assert "PermissionCode.BOT_MANAGE" in source
    assert "require_permission" in source
    assert "verify_admin_api_key" not in source
