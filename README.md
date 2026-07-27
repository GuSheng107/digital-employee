# Digital Employee - 数字员工

Digital Employee 是一个面向企业 IM 场景的数字员工项目。仓库当前包含一套可独立运行的企业微信 Agent 服务、一套正在重写的飞书消息网关，以及一套 React 管理端前端。

## 当前实现

| 模块 | 默认端口 | 技术栈 | 当前职责与状态 |
| --- | --- | --- | --- |
| `backend-agent/` | `8765` | Python 3.10+、FastAPI、LangChain、SQLite | 企业微信长连接、Agent 运行时、Skills/MCP、记忆、任务、日志和管理 API |
| `backend-gateway/` | `8864` | Python 3.11+、FastAPI、lark-oapi、RabbitMQ、MinIO | 飞书多 Bot 长连接、消息归一化、多模态转存、Test/Prod 双模式路由和 Admin API |
| `backend-data/` | `8010` | Python 3.11+、FastAPI、Uvicorn、Redis、MinIO | 数据中台后端服务、数据项管理与状态检查 |
| `frontend/` | `5173` | React 19、TypeScript、Ant Design 6、Vite 8 | 管理端前端，对接 `backend-agent` / `backend-data` 的 API |

当前可确认的平台实现：

- 企业微信：由 `backend-agent/wecom_bot/` 直接接入并调用 Agent Runtime。
- 飞书：由 `backend-gateway/src/platforms/feishu/` 接入。
- 其他平台：当前代码中没有可运行的适配器。

## 架构现状

```text
企业微信 <-> backend-agent/wecom_bot
                    |
                    v
             Agent Runtime
          Skills / MCP / Memory
                    |
                 SQLite

飞书 <-> backend-gateway <-> MinIO（多模态文件）
                    |
          test: 内存 Mock 回显
          prod: RabbitMQ 入站/出站队列
                    |
          Agent 侧 MQ 消费者尚未在本仓库实现
```

`backend-agent` 与 `backend-gateway` 目前是两个独立服务。网关的生产模式会把标准消息发布到 RabbitMQ，但 `backend-agent` 尚未实现对应的 MQ 消费与回复发布链路，因此生产模式还不能在本仓库内完成端到端闭环。

## 目录结构

```text
digital-employee/
├── backend-agent/       # 企业微信 Agent 服务（仅 API）
├── backend-gateway/     # Python 飞书消息网关
├── backend-data/        # 数据平台后端服务
├── frontend/            # React + TypeScript 新管理端脚手架
├── scripts/             # 各模块运维、启动与清理脚本（含一键启动脚本 start-all.bat / start-all.sh）
├── docker-compose.yml   # RabbitMQ、MinIO 本地依赖
└── Makefile             # 可选的统一开发命令
```

## 服务端口一览

| 模块 / 服务 | 默认端口 | 协议 / 类型 | 说明及常用地址 |
| --- | --- | --- | --- |
| **`backend-agent`** | `8765` | HTTP | 企微 Agent 后端 API (<http://localhost:8765>)，OpenAPI 文档 (<http://localhost:8765/docs>) |
| **`backend-gateway`** | `8864` | HTTP | 飞书消息网关 API (<http://localhost:8864>)，健康检查为 `GET /api/v1/health` |
| **`backend-data`** | `8010` | HTTP | 数据平台后端 API (<http://127.0.0.1:8010>)，Swagger 文档 (<http://127.0.0.1:8010/docs>) |
| **`frontend`** | `5173` | HTTP | React 前端 Vite 开发服务器 (<http://localhost:5173>) |
| **RabbitMQ AMQP** | `5672` | AMQP | 消息队列核心服务端口 |
| **RabbitMQ Console** | `15672` | HTTP | RabbitMQ Web 管理控制台 (<http://localhost:15672>) |
| **MinIO API** | `19000` / `9000` | HTTP | MinIO 对象存储 API 服务端口 |
| **MinIO Console** | `19001` / `9001` | HTTP | MinIO Web 管理控制台 (<http://localhost:19001>) |

## 环境要求

- `backend-agent`：Python 3.10+
- `backend-gateway`：Python 3.11+、[uv](https://docs.astral.sh/uv/)
- `frontend`：`package.json` 当前声明 Node.js 22.14.x
- 前端依赖安装：npm
- 网关联调：RabbitMQ；处理图片、音频、视频或文件时还需要 MinIO
- 可选：Docker Compose，用于启动 RabbitMQ 和 MinIO

## 启动 backend-agent

在 `backend-agent` 中创建虚拟环境并安装依赖：

```powershell
cd backend-agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . pytest
```

启动服务：

```powershell
.\.venv\Scripts\python.exe .\main.py
```

也可以在仓库根目录运行 `scripts\backend-agent\start.bat`。默认访问地址为 <http://localhost:8765>，OpenAPI 文档位于 <http://localhost:8765/docs>。`backend-agent` 仅暴露 API，管理端前端位于仓库根目录的 `frontend/`，参见下文 [新 React 管理端](#新-react-管理端)。

## 启动 backend-gateway

先在仓库根目录启动代码当前使用的基础依赖：

```powershell
docker compose up -d
```

RabbitMQ 管理端默认位于 <http://localhost:15672>，账号和密码均可通过 Compose 环境变量覆盖。MinIO API 默认映射到 `19000`，控制台默认映射到 `19001`。

安装并配置网关：

```powershell
cd backend-gateway
python -m pip install uv
uv sync
Copy-Item .env.example .env
Copy-Item config\bot.template.json config\bot.json
uv run python -m src.main
```

在 `.env` 中设置 RabbitMQ、MinIO 连接信息，并在 `config/bot.json` 中填写飞书应用凭证。网关默认监听 <http://localhost:8864>，健康检查为 `GET /api/v1/health`。

即使 Bot 使用 `test` 模式，网关启动阶段仍会连接 RabbitMQ；媒体消息只有在实际收发时才会访问 MinIO。

## React 管理端

根目录下的 `frontend/` 是仓库统一的管理端前端，对接 `backend-agent` 与 `backend-data` 的 API：

```powershell
cd frontend
npm ci
npm run dev
```

也可以直接在根目录运行快捷脚本 `scripts/frontend/start-web.bat`（或 `./scripts/frontend/start-web.sh`）快速启动前端开发服务器（<http://localhost:5173>）。

可通过 `VITE_API_BASE_URL` 指定后端 API 前缀。生产构建命令为 `npm run build`。

## Makefile

安装了 GNU Make 的环境可以使用以下统一命令：

```text
make install          # 安装 Agent、Gateway 和前端依赖
make infra-up         # 启动 RabbitMQ 与 MinIO
make dev-agent        # 启动 backend-agent
make dev-gateway      # 启动 backend-gateway
make dev-frontend     # 启动 React 管理端开发服务器
make build            # 构建前端
make check            # 运行现有测试、lint 和构建检查
```

Windows 环境不要求安装 Make，可直接执行上文的 PowerShell 命令或 `scripts\frontend\start-web.bat`。

## 验证

```powershell
# backend-agent 测试
.\backend-agent\.venv\Scripts\python.exe -m pytest backend-agent\tests

# backend-gateway lint
cd backend-gateway
uv run ruff check src

# React 管理端
cd ..\frontend
npm run lint
npm run build
```

## 贡献

所有进入 `master` 的改动都应通过 Pull Request 合入。分支命名、提交格式、测试与 Review 要求见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[MIT License](LICENSE)
