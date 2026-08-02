#!/usr/bin/env python3
"""跨平台启动数字员工项目的全部运行服务。"""

from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

LOGGER = logging.getLogger("start-all")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVICE_PORTS = (8010, 8020, 8864, 5173)
HEALTH_ATTEMPTS = 40
HEALTH_INTERVAL_SECONDS = 0.5
HEALTH_TIMEOUT_SECONDS = 2.0
PRODUCTION_ENVIRONMENT = {
    "APP_ENV": "production",
    "NACOS_NAMESPACE": "prod",
}
FRONTEND_PRODUCTION_ENVIRONMENT = {
    "NODE_ENV": "production",
    "VITE_APP_ENV": "production",
}


@dataclass(frozen=True)
class ServiceSpec:
    """描述一个由一键脚本管理的项目服务。"""

    name: str
    working_directory: Path
    command: tuple[str, ...]
    health_url: str
    environment: dict[str, str]


@dataclass(frozen=True)
class EndpointCheck:
    """描述启动后的 HTTP 验收请求。"""

    name: str
    url: str
    headers: dict[str, str]
    method: str = "GET"
    body: bytes | None = None


def _read_env_file(path: Path) -> dict[str, str]:
    """读取简单 dotenv 文件，不执行变量展开。"""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_value = value.strip()
        if (
            len(normalized_value) >= 2
            and normalized_value[0] == normalized_value[-1]
            and normalized_value[0] in {'"', "'"}
        ):
            normalized_value = normalized_value[1:-1]
        values[key.strip()] = normalized_value
    return values


def _ensure_env_file(project_directory: Path) -> Path:
    """确保项目存在本地 .env，并返回其路径。"""
    env_path = project_directory / ".env"
    if env_path.exists():
        return env_path
    example_path = project_directory / ".env.example"
    if not example_path.exists():
        raise RuntimeError(f"缺少配置文件：{env_path}")
    shutil.copyfile(example_path, env_path)
    LOGGER.info("已从示例创建配置文件：%s", env_path)
    return env_path


def _ensure_file_from_template(target: Path, template: Path) -> None:
    """首次运行时从无敏感信息的模板创建本地配置。"""
    if target.exists():
        return
    if not template.exists():
        raise RuntimeError(f"缺少配置模板：{template}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, target)
    LOGGER.info("已从模板创建本地配置：%s", target)


def _persist_env_value(path: Path, key: str, value: str) -> None:
    """原子更新 dotenv 中的单个值，保留其他本地配置。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    replacement = f"{key}={value}"
    updated_lines: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if (
            not replaced
            and not stripped.startswith("#")
            and "=" in line
            and line.split("=", 1)[0].strip() == key
        ):
            updated_lines.append(replacement)
            replaced = True
        else:
            updated_lines.append(line)
    if not replaced:
        updated_lines.append(replacement)

    temporary_path = path.with_name(
        f".{path.name}.{secrets.token_hex(6)}.tmp"
    )
    try:
        temporary_path.write_text(
            "\n".join(updated_lines) + "\n",
            encoding="utf-8",
        )
        if sys.platform != "win32":
            temporary_path.chmod(0o600)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _resolve_command(name: str, *, windows_name: str | None = None) -> str:
    """解析必需的可执行文件路径。"""
    candidate = windows_name if sys.platform == "win32" and windows_name else name
    executable = shutil.which(candidate)
    if executable is None:
        raise RuntimeError(f"未找到必需命令：{candidate}")
    return executable


def _build_environment(
    env_file: Path,
    *,
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """构造服务子进程环境，显式配置优先于父进程环境。"""
    environment = dict(os.environ)
    environment.update(_read_env_file(env_file))
    if overrides:
        environment.update(overrides)
    return environment


def _sync_python_project(uv: str, project_directory: Path) -> None:
    """严格按锁文件安装项目及可编辑的本地 share 依赖；当 lock 匹配失败时自动修复。"""
    LOGGER.info("正在同步 Python 依赖：%s", project_directory.name)
    result = subprocess.run(
        (uv, "sync", "--locked"),
        cwd=project_directory,
        check=False,
    )
    if result.returncode != 0:
        LOGGER.warning(
            "检测到 %s 锁文件需要更新，正在自动执行 uv lock 尝试修复...",
            project_directory.name,
        )
        lock_result = subprocess.run(
            (uv, "lock"),
            cwd=project_directory,
            check=False,
        )
        if lock_result.returncode == 0:
            result = subprocess.run(
                (uv, "sync", "--locked"),
                cwd=project_directory,
                check=False,
            )
    if result.returncode != 0:
        raise RuntimeError(f"Python 依赖同步失败：{project_directory}")


def _build_service_specs() -> list[ServiceSpec]:
    """构造按依赖顺序排列的服务定义。"""
    uv = _resolve_command("uv")
    npm = _resolve_command("npm", windows_name="npm.cmd")
    data_dir = PROJECT_ROOT / "backend-data" / "backend"
    auth_dir = PROJECT_ROOT / "backend-auth"
    gateway_dir = PROJECT_ROOT / "backend-gateway"
    frontend_dir = PROJECT_ROOT / "frontend"
    data_env_file = _ensure_env_file(data_dir)
    auth_env_file = _ensure_env_file(auth_dir)
    gateway_env_file = _ensure_env_file(gateway_dir)
    frontend_env_file = _ensure_env_file(frontend_dir)
    for project_directory in (data_dir, auth_dir, gateway_dir):
        _sync_python_project(uv, project_directory)
    LOGGER.info("正在检查并同步 Frontend 依赖...")
    if (frontend_dir / "node_modules").exists():
        LOGGER.info("Frontend node_modules 已存在，跳过依赖安装")
    else:
        install_command = (
            (npm, "ci")
            if (frontend_dir / "package-lock.json").exists()
            else (npm, "install")
        )
        install_result = subprocess.run(
            install_command,
            cwd=frontend_dir,
            check=False,
        )
        if install_result.returncode != 0:
            raise RuntimeError("Frontend 依赖安装失败")
    LOGGER.info("正在构建 Frontend production 产物...")
    build_result = subprocess.run(
        (npm, "run", "build"),
        cwd=frontend_dir,
        env=_build_environment(
            frontend_env_file,
            overrides=FRONTEND_PRODUCTION_ENVIRONMENT,
        ),
        check=False,
    )
    if build_result.returncode != 0:
        raise RuntimeError("Frontend production 构建失败")

    return [
        ServiceSpec(
            name="Backend Data",
            working_directory=data_dir,
            command=(uv, "run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8010"),
            health_url="http://127.0.0.1:8010/api/v1/health",
            environment=_build_environment(
                data_env_file,
                overrides=PRODUCTION_ENVIRONMENT,
            ),
        ),
        ServiceSpec(
            name="Backend Auth",
            working_directory=auth_dir,
            command=(uv, "run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8020"),
            health_url="http://127.0.0.1:8020/api/v1/health",
            environment=_build_environment(
                auth_env_file,
                overrides=PRODUCTION_ENVIRONMENT,
            ),
        ),
        ServiceSpec(
            name="Backend Gateway",
            working_directory=gateway_dir,
            command=(uv, "run", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", "8864"),
            health_url="http://127.0.0.1:8864/api/v1/health",
            environment=_build_environment(
                gateway_env_file,
                overrides=PRODUCTION_ENVIRONMENT,
            ),
        ),
        ServiceSpec(
            name="Frontend",
            working_directory=frontend_dir,
            command=(
                npm,
                "run",
                "preview",
                "--",
                "--host",
                "127.0.0.1",
                "--port",
                "5173",
            ),
            health_url="http://127.0.0.1:5173",
            environment=_build_environment(
                frontend_env_file,
                overrides=FRONTEND_PRODUCTION_ENVIRONMENT,
            ),
        ),
    ]


def _clean_project_ports() -> None:
    """调用仓库端口工具清理旧服务进程。"""
    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "kill-port.py"),
        *(str(port) for port in SERVICE_PORTS),
    ]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise RuntimeError("旧服务端口清理失败")


def _start_service(service: ServiceSpec) -> subprocess.Popen[bytes]:
    """在独立进程会话中启动服务。"""
    kwargs: dict[str, object] = {
        "cwd": service.working_directory,
        "env": service.environment,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(service.command, **kwargs)  # type: ignore[arg-type]


def _request_endpoint(check: EndpointCheck) -> tuple[int, object | None]:
    """请求验收端点并返回 HTTP 状态码与 JSON 响应。"""
    request = Request(  # noqa: S310
        check.url,
        data=check.body,
        headers=check.headers,
        method=check.method,
    )
    with urlopen(  # noqa: S310
        request,
        timeout=HEALTH_TIMEOUT_SECONDS,
    ) as response:
        body = response.read()
        if not body:
            return response.status, None
        try:
            return response.status, json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return response.status, None


def _wait_for_health(service: ServiceSpec, process: subprocess.Popen[bytes]) -> None:
    """等待服务健康检查通过，否则抛出启动失败。"""
    for _ in range(HEALTH_ATTEMPTS):
        if process.poll() is not None:
            raise RuntimeError(
                f"{service.name} 进程提前退出，退出码：{process.returncode}"
            )
        try:
            status, _ = _request_endpoint(
                EndpointCheck(
                    name=service.name,
                    url=service.health_url,
                    headers={},
                )
            )
            if 200 <= status < 400:
                LOGGER.info("%s 已就绪：%s", service.name, service.health_url)
                return
        except (OSError, URLError):
            pass
        time.sleep(HEALTH_INTERVAL_SECONDS)
    raise RuntimeError(f"{service.name} 健康检查超时：{service.health_url}")


def main() -> int:
    """清理旧进程，按依赖顺序启动并验证全部服务。"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        services = _build_service_specs()
        _clean_project_ports()
        for service in services:
            LOGGER.info("正在启动 %s...", service.name)
            process = _start_service(service)
            _wait_for_health(service, process)
    except (OSError, RuntimeError) as exc:
        LOGGER.error("一键启动失败：%s", exc)
        try:
            _clean_project_ports()
        except (OSError, RuntimeError):
            pass
        return 1

    LOGGER.info("全部服务启动成功：")
    for service in services:
        LOGGER.info("- %s: %s", service.name, service.health_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
