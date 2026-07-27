"""digital-employee 共享的 Nacos 配置中心客户端。

启动时一次性拉取配置并注入 os.environ，Nacos 不可用时静默降级到本地配置。
仅支持配置中心 API，不支持服务发现/订阅。

典型用法：
    from nacos_client import NacosClient

    client = NacosClient.from_env_optional(default_data_id="dev.yaml")
    if client is not None:
        client.load_to_environ()
"""

from nacos_client.client import NacosClient, NacosConfigError

__all__ = ["NacosClient", "NacosConfigError"]
