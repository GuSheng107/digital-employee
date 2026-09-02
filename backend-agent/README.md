# Backend Agent

数字员工 Agent 运行时服务。当前版本只提供规范化服务骨架、健康检查、
生命周期管理和链路追踪，不消费 RabbitMQ 消息，也不调用大模型。

## 环境要求

- Python 3.11+
- uv
- 可用的 Nacos 配置中心

## 本地启动

先从示例创建本地配置并填写 Nacos 凭证：

```powershell
Copy-Item .env.example .env
```

前台调试：

```powershell
uv sync --locked
uv run uvicorn app.main:app --host 127.0.0.1 --port 8030
```

Windows 后台启动和停止：

```powershell
start.bat
stop.bat
```

日志写入 `logs/agent.log`，运行信息写入 `.runtime/agent.json`。

## 验证

```powershell
uv run ruff check app scripts tests
uv run mypy app scripts
uv run pytest -q
```

健康检查：

```text
GET http://127.0.0.1:8030/api/v1/health
GET http://127.0.0.1:8030/api/v1/health/ready
```
