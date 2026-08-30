# Backend Agent Runtime

一期最小可用 Agent Runtime：单 Agent 模型调用、LiteLLM 模型网关、显式绑定的 stdio MCP 与本地 Skill。

## 启动

```powershell
cd backend-agent
Copy-Item .env.example .env
# .env 与 pyproject.toml 同级，不放进 .venv；在其中配置 MODEL_API_KEY、MODEL_NAME 和可选的 MODEL_API_BASE
uv sync
uv run uvicorn app.main:app --reload --port 8766
```

访问 `http://127.0.0.1:8766/docs` 或调试页 `http://127.0.0.1:8766/debug/`。默认 Agent 是 `weather-agent`；它绑定了本地 FastMCP 天气服务和天气回答 Skill。

## 快速验证

先在另一个终端运行不依赖模型密钥的测试：

```powershell
cd backend-agent
uv run pytest
```

配置真实模型后，调用：

```powershell
Invoke-RestMethod http://127.0.0.1:8766/v1/agents/weather-agent/test -Method Post -ContentType 'application/json' -Body '{"message":"北京今天天气怎样"}'
```

模型连通性检查不挂 MCP：

```powershell
Invoke-RestMethod http://127.0.0.1:8766/v1/model/test -Method Post
```

不要把 API Key 写入 Agent 定义、日志或 Git；只通过 `.env` / 环境变量提供。

## 一期范围

- `POST /v1/agents/{agent_id}/test`：运行完整模型-工具循环。
- `POST /v1/agents/{agent_id}/stream`：SSE 生命周期事件流。
- `POST /v1/model/test`：最小模型连通性检查。
- `GET /v1/agents`、`GET /v1/traces/{trace_id}`：查看配置和本地 JSONL trace。

长期 Memory、自动工具筛选、多 Agent、审批、Redis 和工作流不在本期运行路径中。文档入口见 [AGENTS.md](AGENTS.md)；模块边界见 [docs/00-概览/架构总览与模块边界.md](docs/00-概览/架构总览与模块边界.md)，当前进度与下一步见 [docs/00-概览/当前状态与路线图.md](docs/00-概览/当前状态与路线图.md)。