# Backend Agent Runtime

Agent Runtime：一期完成单 Agent 模型调用、LiteLLM 模型网关、显式绑定的 stdio MCP 与本地 Skill；二期加入 SQLite 会话持久化。

## 启动

```powershell
cd backend-agent
Copy-Item .env.example .env
# .env 与 pyproject.toml 同级，不放进 .venv；在其中配置 MODEL_API_KEY、MODEL_NAME 和可选的 MODEL_API_BASE
uv sync
uv run uvicorn app.main:app --reload --port 8766
```

访问调试页 `http://127.0.0.1:8766/debug/`。默认 Agent 是 `weather-agent`；它绑定了本地 FastMCP 天气服务和天气回答 Skill。

## API 文档

服务启动后可直接打开 FastAPI 生成的接口文档：

- Swagger UI：`http://127.0.0.1:8766/docs`
- ReDoc：`http://127.0.0.1:8766/redoc`
- OpenAPI JSON：`http://127.0.0.1:8766/openapi.json`

Swagger UI 可直接查看请求参数、响应结构并发送测试请求；OpenAPI JSON 可供前端生成 API Client 或在 CI 中校验接口契约。流式 Agent 接口使用 SSE，事件类型包括 `run.started`、`tools.bound`、`model.started`、`tool.started`、`tool.completed`、`run.completed` 和 `run.failed`。

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
- `GET /v1/sessions?user_id=...`：按用户查看会话摘要，供调试页选择历史会话。
- `GET /v1/sessions/{session_id}`：查看已持久化的会话、轮次和消息。

长期 Memory、自动工具筛选、多 Agent、审批、Redis 和工作流不在当前运行路径中。会话的 `user_id` / `user_role` 字段已预留，但 auth 尚未接入，当前不参与权限判断。文档入口见 [AGENTS.md](AGENTS.md)；模块边界见 [docs/00-概览/架构总览与模块边界.md](docs/00-概览/架构总览与模块边界.md)，当前进度与下一步见 [docs/00-概览/当前状态与路线图.md](docs/00-概览/当前状态与路线图.md)。
