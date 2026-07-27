# nacos-client

digital-employee 三个后端共享的 Nacos 配置中心轻量客户端。

## 设计目标

1. **启动时一次性拉取**：不订阅变更，避免连接池重建等复杂度。
2. **失败降级**：Nacos 不可用时静默 fallback 到本地 `.env`/`.yaml`，仅打日志。
3. **凭证外置**：`NACOS_*` 系列变量从 `os.environ` 读取，不入库不入 Nacos。
4. **零侵入接入**：`load_to_environ()` 注入 `os.environ`，`pydantic-settings` /
   `os.getenv` 自动生效。

## 安装（在子项目 pyproject.toml 中）

```toml
dependencies = [
    "nacos-client = { path = "../../backend-share/nacos-client" }",
]
```

## 环境变量

| 变量 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `NACOS_SERVER_ADDR` | 是 | - | `host:port`，多个用逗号分隔 |
| `NACOS_USERNAME` | 是 | - | Nacos 账号 |
| `NACOS_PASSWORD` | 是 | - | Nacos 密码 |
| `NACOS_NAMESPACE` | 否 | `dev` | 命名空间 ID（dev/prod） |
| `NACOS_DATA_ID` | 否 | `${NAMESPACE}.yaml` | 配置文件 ID |
| `NACOS_GROUP` | 否 | `DEFAULT_GROUP` | 配置分组 |
| `NACOS_TIMEOUT` | 否 | `5.0` | 拉取超时（秒） |

## 接入示例

```python
from nacos_client import NacosClient

# 在 Settings 实例化前调用
client = NacosClient.from_env_optional(default_data_id="dev.yaml")
if client is not None:
    client.load_to_environ()

# pydantic-settings 自动读 os.environ，无需改 Settings 类
settings = get_settings()
```

## 降级行为

- `NACOS_SERVER_ADDR` 未设置：跳过拉取，使用本地配置。
- `nacos-sdk-python` 未安装：跳过拉取，使用本地配置。
- 网络异常或鉴权失败：返回 `{}`，使用本地配置。

所有降级路径仅打日志，不抛异常。
