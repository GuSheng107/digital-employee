"""Nacos 配置中心轻量客户端封装（兼容 Nacos 3.x）。

设计目标：
1. 启动时一次性拉取配置（fetch_config / load_to_environ），不订阅变更。
2. Nacos 不可用时静默降级到本地 .env/yaml，仅打日志，不阻塞启动。
3. 凭证（NACOS_* 系列环境变量）从 os.environ 读取，不入库不入 Nacos，
   避免循环依赖。
4. load_to_environ 将嵌套 YAML 拍平后注入 os.environ
   （postgres.host -> POSTGRES_HOST），pydantic-settings / os.getenv 自动读到，
   优先级高于本地 .env 文件。

实现说明：
- 不使用 nacos-sdk-python（v1 仅支持 Nacos 1.x/2.x 的 v1 HTTP API，
  Nacos 3.x 已废弃 v1 API，返回 404）。
- 直接用 httpx 调用 Nacos 3.x 的 v3 REST API：
  - 登录：POST /nacos/v1/auth/login（v1 login API 仍兼容）
  - 拉配置：GET /nacos/v3/admin/cs/config?dataId=&groupName=&namespaceId=&accessToken=
- v3 API 参数名与 v1 不同：groupName（不是 group）、namespaceId（不是 tenant）。
- v3 API 返回 JSON wrapper {"code":0,"data":{"content":"..."}}，实际配置在
  data.content 字段。
"""

from __future__ import annotations
import os
from typing import Any

import httpx
import yaml


class NacosConfigError(Exception):
    """Nacos 配置初始化相关异常（凭证缺失等）。"""


def _flatten_dict(
    data: dict[str, Any],
    parent_key: str = "",
    sep: str = "_",
) -> dict[str, Any]:
    """递归拍平嵌套 dict。

    {"postgres": {"host": "x", "port": 5432}} -> {"postgres_host": "x", "postgres_port": 5432}
    多层嵌套同理：{"a": {"b": {"c": 1}}} -> {"a_b_c": 1}

    非 dict 类型的值原样保留（str/int/bool/None/list 都直接放到拍平后的 key 下）。
    """
    items: list[tuple[str, Any]] = []
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            items.extend(_flatten_dict(value, new_key, sep).items())
        else:
            items.append((new_key, value))
    return dict(items)


class NacosClient:
    """从 Nacos 配置中心拉取配置的轻量客户端。

    使用 httpx 直接调 Nacos 3.x v3 REST API。一次性拉取，不订阅变更，
    不维护长连接。所有实例字段在构造时确定，fetch_config 内部创建
    httpx 请求，避免持有连接状态。
    """

    def __init__(
        self,
        server_addr: str,
        username: str,
        password: str,
        namespace: str,
        data_id: str,
        group: str = "DEFAULT_GROUP",
        timeout: float = 5.0,
        scheme: str = "http",
    ) -> None:
        self._server_addr = server_addr
        self._username = username
        self._password = password
        self._namespace = namespace
        self._data_id = data_id
        self._group = group
        self._timeout = timeout
        self._scheme = scheme

    @classmethod
    def from_env(
        cls,
        default_data_id: str | None = None,
        default_namespace: str = "dev",
    ) -> "NacosClient":
        """从 NACOS_* 环境变量构造 NacosClient。

        环境变量：
        - NACOS_SERVER_ADDR (必填，例：106.54.60.80:18848)
        - NACOS_USERNAME    (必填)
        - NACOS_PASSWORD    (必填)
        - NACOS_NAMESPACE   (默认 dev)
        - NACOS_DATA_ID     (默认 ${NAMESPACE}.yaml)
        - NACOS_GROUP       (默认 DEFAULT_GROUP)
        - NACOS_TIMEOUT     (默认 5.0，秒)
        - NACOS_SCHEME      (默认 http)

        Args:
            default_data_id: 当 NACOS_DATA_ID 未设置时的兜底值。若也
                未提供则使用 f"{namespace}.yaml"。
            default_namespace: 当 NACOS_NAMESPACE 未设置时的兜底值。

        Returns:
            NacosClient 实例。

        Raises:
            NacosConfigError: 必填环境变量缺失时抛出。
        """
        namespace = os.getenv("NACOS_NAMESPACE", default_namespace)
        data_id = (
            os.getenv("NACOS_DATA_ID")
            or default_data_id
            or f"{namespace}.yaml"
        )
        server_addr = os.getenv("NACOS_SERVER_ADDR")
        username = os.getenv("NACOS_USERNAME")
        password = os.getenv("NACOS_PASSWORD")

        missing = []
        if not server_addr:
            missing.append("NACOS_SERVER_ADDR")
        if not username:
            missing.append("NACOS_USERNAME")
        if not password:
            missing.append("NACOS_PASSWORD")
        if missing:
            raise NacosConfigError(
                f"Nacos 环境变量缺失: {', '.join(missing)}。"
                "请在 .env 或系统环境变量中配置 NACOS_* 系列变量。"
            )

        timeout = float(os.getenv("NACOS_TIMEOUT", "5.0"))
        group = os.getenv("NACOS_GROUP", "DEFAULT_GROUP")
        scheme = os.getenv("NACOS_SCHEME", "http")
        return cls(
            server_addr=server_addr,
            username=username,
            password=password,
            namespace=namespace,
            data_id=data_id,
            group=group,
            timeout=timeout,
            scheme=scheme,
        )

    @classmethod
    def from_env_optional(
        cls,
        default_data_id: str | None = None,
        default_namespace: str = "dev",
    ) -> "NacosClient | None":
        """from_env 的可选版本：缺少凭证或配置异常时返回 None 而非抛异常。

        适用于「未配置 Nacos 凭证即跳过」的场景，让本地开发不必强制配置 Nacos。
        捕获所有异常（NacosConfigError、ValueError、TypeError 等）统一降级，
        避免任一配置项格式错误阻断服务启动。
        """
        if not os.getenv("NACOS_SERVER_ADDR"):
            return None
        try:
            return cls.from_env(default_data_id, default_namespace)
        except Exception:  # noqa: BLE001
            return None

    def _login(self) -> str | None:
        """登录 Nacos 拿 accessToken。

        Nacos 3.x 仍保留 v1 login API（/nacos/v1/auth/login），
        返回的 accessToken 可用于 v3 API 鉴权。
        """
        url = f"{self._scheme}://{self._server_addr}/nacos/v1/auth/login"
        try:
            resp = httpx.post(
                url,
                data={
                    "username": self._username,
                    "password": self._password,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
            token = resp.json().get("accessToken")
            if not token:
                return None
            return token
        except Exception:  # noqa: BLE001
            return None

    def _fetch_raw(self) -> str | None:
        """调 v3 API 拉配置原文（YAML 字符串）。

        Nacos 3.x v3 API 路径：/nacos/v3/admin/cs/config
        参数：dataId, groupName, namespaceId, accessToken
        返回 JSON wrapper {"code":0,"message":"success","data":{"content":"..."}}
        实际配置在 data.content 字段。
        """
        token = self._login()
        if token is None:
            return None

        url = f"{self._scheme}://{self._server_addr}/nacos/v3/admin/cs/config"
        try:
            resp = httpx.get(
                url,
                params={
                    "dataId": self._data_id,
                    "groupName": self._group,
                    "namespaceId": self._namespace,
                    "accessToken": token,
                },
                timeout=self._timeout,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 0:
                return None
            data = body.get("data") or {}
            return data.get("content")
        except Exception:  # noqa: BLE001
            return None

    def fetch_config(self) -> dict[str, Any]:
        """从 Nacos 拉取配置并解析为 dict（保持原始嵌套结构）。

        Returns:
            配置字典（嵌套结构原样保留）。Nacos 拉取失败、配置为空或
            根节点非 dict 时返回 {}。调用方如需注入 os.environ 应使用
            load_to_environ（会自动拍平嵌套 key）。
        """
        raw = self._fetch_raw()
        if not raw:
            return {}

        try:
            data = yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            return {}

        if not isinstance(data, dict):
            return {}
        return data

    def load_to_environ(
        self,
        *,
        upper: bool = True,
        prefix: str = "",
    ) -> dict[str, Any]:
        """拉取配置，拍平嵌套 key 后注入 os.environ。

        拍平规则：postgres.host -> postgres_host -> (大写) POSTGRES_HOST
        pydantic-settings / os.getenv 自动读到这些环境变量，
        优先级高于本地 .env 文件。

        Args:
            upper: 是否把 key 转为大写（默认 True，匹配 pydantic-settings
                env 命名约定）。
            prefix: 注入到 os.environ 时的 key 前缀（默认无前缀）。

        Returns:
            拍平后的 dict（含失败时的空 dict）。
        """
        data = self.fetch_config()
        flat = _flatten_dict(data)
        for key, value in flat.items():
            env_key = prefix + (key.upper() if upper else key)
            os.environ[env_key] = str(value)
        return flat
