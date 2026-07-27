# nacos-client

digital-employee 三个后端共享的 Nacos 配置中心轻量客户端。

## 设计目标

1. **启动时一次性拉取**：不订阅变更，避免连接池重建等复杂度。
2. **失败降级**：Nacos 不可用时静默 fallback 到本地 `.env`/`.yaml`，仅打日志。
3. **凭证外置**：`NACOS_*` 系列变量从 `os.environ` 读取，不入库不入 Nacos。
4. **零侵入接入**：`load_to_environ()` 注入 `os.environ`，`pydantic-settings` /
   `os.getenv` 自动生效。
5. **Nacos 3.x 兼容**：直接用 httpx 调 v3 REST API（`/nacos/v3/admin/cs/config`），
   不依赖 nacos-sdk-python（v1 仅支持 Nacos 1.x/2.x v1 API，Nacos 3.x 已废弃）。
6. **嵌套 YAML 拍平**：`postgres.host` → `POSTGRES_HOST` 自动注入，调用方通过
   pydantic alias 适配各自 Settings 字段命名。

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
| `NACOS_SCHEME` | 否 | `http` | http 或 https |

## 接入示例

```python
from nacos_client import NacosClient

# 在 Settings 实例化前调用
client = NacosClient.from_env_optional(default_data_id="dev.yaml")
if client is not None:
    client.load_to_environ()  # 嵌套 YAML 拍平后注入 os.environ

# pydantic-settings 自动读 os.environ
# 字段命名不匹配时用 validation_alias 适配：
#   core_db_host: str = Field(alias="POSTGRES_HOST")  # 读 Nacos 拍平的 key
settings = get_settings()
```

## 拍平规则

嵌套 YAML 自动拍平后注入 os.environ（key 全大写）：

```yaml
# Nacos 上的 dev.yaml
postgres:
  host: 101.37.69.110
  port: 15432
```

→ 注入 os.environ：
```
POSTGRES_HOST=101.37.69.110
POSTGRES_PORT=15432
```

调用方 pydantic Settings 字段如命名为 `core_db_host`，用 `validation_alias` 适配：

```python
from pydantic import Field

class Settings(BaseSettings):
    core_db_host: str = Field(default="", validation_alias="POSTGRES_HOST")
```

## 降级行为

- `NACOS_SERVER_ADDR` 未设置：跳过拉取，使用本地配置。
- 网络异常或鉴权失败：返回 `{}`，使用本地配置。
- 配置不存在（404）：返回 `{}`，使用本地配置。

所有降级路径仅打日志，不抛异常。
