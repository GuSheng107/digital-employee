# Backend Agent

数字员工 Agent 运行时服务。一期完成单 Agent 模型调用、LiteLLM 模型网关、显式绑定的 stdio MCP 与本地 Skill；二期加入 SQLite 会话持久化。本服务同时接入 Nacos 配置、统一响应、全局异常处理、健康/就绪检查、链路追踪和幂等生命周期管理，并提供 Windows 优雅启停脚本。

## 环境要求

- Python 3.11+
- uv
- 可用的 Nacos 配置中心

## 本地启动

先从示例创建本地配置并填写 Nacos 凭证：

```powershell
Copy-Item .env.example .env
```

`.env` 还可配置模型相关变量：`MODEL_API_KEY`、`MODEL_NAME` 和可选的 `MODEL_API_BASE`、`MODEL_TIMEOUT_SECONDS`、`MAX_TOOL_ROUNDS`。

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

日志写入 `logs/agent.log`，运行信息写入 `.runtime/agent.json`，Agent Trace 写入 `var/traces/`，会话持久化到 `var/sessions.sqlite3`。

## 接口

健康检查与就绪检查：

```text
GET http://127.0.0.1:8030/api/v1/health
GET http://127.0.0.1:8030/api/v1/health/ready
GET http://127.0.0.1:8030/api/v1/health/info
```

Agent 运行时业务接口（挂在 `/api/v1` 前缀下）：

- `POST /api/v1/agents/{agent_id}/test`：运行完整模型-工具循环。
- `POST /api/v1/agents/{agent_id}/stream`：SSE 生命周期事件流。
- `POST /api/v1/model/test`：最小模型连通性检查。
- `GET /api/v1/agents`、`GET /api/v1/traces/{trace_id}`：查看配置和本地 JSONL trace。
- `GET /api/v1/sessions?user_id=...`：按用户查看会话摘要，供调试页选择历史会话。
- `GET /api/v1/sessions/{session_id}`：查看已持久化的会话、轮次和消息。

服务启动后可直接打开 FastAPI 生成的接口文档：

- Swagger UI：`http://127.0.0.1:8030/docs`
- ReDoc：`http://127.0.0.1:8030/redoc`
- OpenAPI JSON：`http://127.0.0.1:8030/openapi.json`

调试页位于 `/debug/`。默认 Agent 是 `weather-agent`；它绑定了本地 FastMCP 天气服务和天气回答 Skill。流式 Agent 接口使用 SSE，事件类型包括 `run.started`、`tools.bound`、`model.started`、`tool.started`、`tool.completed`、`run.completed` 和 `run.failed`。

## 验证

```powershell
uv run ruff check app scripts tests
uv run mypy app scripts
uv run pytest -q
```

配置真实模型后，调用：

```powershell
Invoke-RestMethod http://127.0.0.1:8030/api/v1/agents/weather-agent/test -Method Post -ContentType 'application/json' -Body '{"message":"北京今天天气怎样"}'
```

模型连通性检查不挂 MCP：

```powershell
Invoke-RestMethod http://127.0.0.1:8030/api/v1/model/test -Method Post
```

不要把 API Key 写入 Agent 定义、日志或 Git；只通过 `.env` / 环境变量提供。

## 范围与边界

长期 Memory、自动工具筛选、多 Agent、审批、Redis 和工作流不在当前运行路径中。会话的 `user_id` / `user_role` 字段已预留，但 auth 尚未接入，当前不参与权限判断。本 PR 仅修改 `backend-agent/**`。文档入口见 [AGENTS.md](AGENTS.md)；模块边界见 [docs/00-概览/架构总览与模块边界.md](docs/00-概览/架构总览与模块边界.md)，当前进度与下一步见 [docs/00-概览/当前状态与路线图.md](docs/00-概览/当前状态与路线图.md)。
