"""Nacos 配置中心轻量客户端封装。

设计目标：
1. 启动时一次性拉取配置（fetch_config / load_to_environ），不订阅变更。
2. Nacos 不可用时静默降级到本地 .env/yaml，仅打日志，不阻塞启动。
3. 凭证（NACOS_* 系列环境变量）从 os.environ 读取，不入库不入 Nacos，
   避免循环依赖。
4. load_to_environ 将配置注入 os.environ，pydantic-settings / os.getenv
   自动读到，优先级高于本地 .env 文件。
"""

from __future__ import annotations

import logging
import os
from typing import Any

import yaml

logger = logging.getLogger("nacos_client")

# 抑制 nacos-sdk-python v1 内部 logger 在 loguru 环境下的 stream flush 错误。
# nacos SDK 用 stdlib logging，被应用层 loguru InterceptHandler 拦截后 stream
# 可能失效，导致 SDK 调用 logger.warning() 时触发 OSError: Bad file descriptor。
# 给 nacos.* logger 显式加 NullHandler 并禁用 propagate，让 SDK 日志走我们的
# NacosClient 自己的日志（fetch_config 已捕获所有异常并打 "[Nacos]" 前缀日志）。
_nacos_sdk_logger = logging.getLogger("nacos")
_nacos_sdk_logger.addHandler(logging.NullHandler())
_nacos_sdk_logger.propagate = False


class NacosConfigError(Exception):
    """Nacos 配置初始化相关异常（凭证缺失等）。"""


class NacosClient:
    """从 Nacos 配置中心拉取配置的轻量客户端。

    使用 nacos-sdk-python v1 同步 API（兼容 Nacos 0.8 ~ 2.x，HTTP REST）。
    一次性拉取，不订阅变更，不维护长连接。

    所有实例字段在构造时确定，fetch_config 内部创建 SDK client，
    避免持有连接状态。
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
    ) -> None:
        self._server_addr = server_addr
        self._username = username
        self._password = password
        self._namespace = namespace
        self._data_id = data_id
        self._group = group
        self._timeout = timeout

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
        return cls(
            server_addr=server_addr,
            username=username,
            password=password,
            namespace=namespace,
            data_id=data_id,
            group=group,
            timeout=timeout,
        )

    @classmethod
    def from_env_optional(
        cls,
        default_data_id: str | None = None,
        default_namespace: str = "dev",
    ) -> "NacosClient | None":
        """from_env 的可选版本：缺少凭证时返回 None 而非抛异常。

        适用于「未配置 Nacos 凭证即跳过」的场景，让本地开发不必强制配置 Nacos。
        """
        if not os.getenv("NACOS_SERVER_ADDR"):
            logger.info(
                "[Nacos] NACOS_SERVER_ADDR 未设置，跳过 Nacos 配置拉取，使用本地配置。"
            )
            return None
        try:
            return cls.from_env(default_data_id, default_namespace)
        except NacosConfigError as exc:
            logger.warning("[Nacos] %s，降级到本地配置。", exc)
            return None

    def fetch_config(self) -> dict[str, Any]:
        """从 Nacos 拉取配置并解析为 dict。

        Returns:
            配置字典。Nacos 拉取失败、配置为空或根节点非 dict 时返回 {}。
        """
        try:
            import nacos  # nacos-sdk-python v1 同步 API
        except ImportError as exc:
            logger.warning(
                "[Nacos] nacos-sdk-python 未安装，跳过 Nacos 配置拉取: %s", exc,
            )
            return {}

        try:
            client = nacos.NacosClient(
                server_addresses=self._server_addr,
                namespace=self._namespace,
                username=self._username,
                password=self._password,
            )
            raw: str | None = client.get_config(
                self._data_id,
                self._group,
                timeout=self._timeout,
            )
            if not raw:
                logger.warning(
                    "[Nacos] 配置为空: namespace=%s data_id=%s group=%s",
                    self._namespace,
                    self._data_id,
                    self._group,
                )
                return {}

            data = yaml.safe_load(raw) or {}
            if not isinstance(data, dict):
                logger.warning(
                    "[Nacos] 配置根节点不是 dict (类型=%s)，跳过",
                    type(data).__name__,
                )
                return {}

            logger.info(
                "[Nacos] 配置拉取成功: namespace=%s data_id=%s keys=%d",
                self._namespace,
                self._data_id,
                len(data),
            )
            return data
        except Exception as exc:  # noqa: BLE001 - 任何异常都降级
            logger.warning(
                "[Nacos] 配置拉取失败，降级到本地配置: %s: %s",
                type(exc).__name__,
                exc,
            )
            return {}

    def load_to_environ(
        self,
        *,
        upper: bool = True,
        prefix: str = "",
    ) -> dict[str, Any]:
        """拉取配置并注入 os.environ。

        pydantic-settings / os.getenv 自动读到这些环境变量，
        优先级高于本地 .env 文件。

        Args:
            upper: 是否把 key 转为大写（默认 True，匹配 pydantic-settings
                env 命名约定，如 `core_db_host` → `CORE_DB_HOST`）。
            prefix: 注入到 os.environ 时的 key 前缀（默认无前缀）。

        Returns:
            Nacos 拉取到的原始 dict（含失败时的空 dict）。
        """
        data = self.fetch_config()
        for key, value in data.items():
            env_key = prefix + (key.upper() if upper else key)
            os.environ[env_key] = str(value)
        return data
