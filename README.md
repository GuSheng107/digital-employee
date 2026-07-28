# Digital Employee - 数字员工

Digital Employee 是一个面向企业 IM 场景的数字员工项目。仓库当前包含一套飞书消息网关、一套数据中台服务、一套正在搭建的身份认证服务，以及一套 React 管理端前端。

## 当前实现

| 模块 | 默认端口 | 技术栈 | 当前职责与状态 |
| --- | --- | --- | --- |
| `backend-gateway/` | `8864` | Python 3.11+、FastAPI、lark-oapi、RabbitMQ、MinIO | 飞书多 Bot 长连接、消息归一化、多模态转存、Test/Prod 双模式路由和 Admin API |
| `backend-data/` | `8010` | Python 3.11+、FastAPI、Uvicorn、Redis、MinIO、PostgreSQL | 数据中台后端服务、数据项管理与状态检查 |
| `backend-auth/` | `8020`（规划） | Python 3.11+、FastAPI、PostgreSQL、Redis | 身份中心：用户登录、双 token 鉴权、用户/角色/权限/菜单/Bot 权限管理（搭建中） |
| `frontend/` | `5173` | React 19、TypeScript、Ant Design 6、Vite 8 | 管理端前端，对接各后端服务的 API |
| `backend-share/` | - | Python 3.11+ | 跨服务共享包，含 Nacos 配置中心客户端（`nacos-client`） |

当前可确认的平台实现：

- 飞书：由 `backend-gateway/src/platforms/feishu/` 接入。
- 其他平台：当前代码中没有可运行的适配器。

## 架构现状

```text
飞书 <-> backend-gateway <-> MinIO（多模态文件）
                    |
          test: 内存 Mock 回显
          prod: RabbitMQ 入站/出站队列
                    |
          Agent 侧 MQ 消费者尚未在本仓库实现

backend-data  <-> PostgreSQL / Redis / MinIO  （数据中台）
backend-auth  <-> PostgreSQL / Redis          （身份中心，搭建中）

所有后端服务通过 backend-share/nacos-client 从 Nacos 配置中心
拉取基础设施连接信息（DB/Redis/MinIO/RabbitMQ）。
```

## 目录结构

```text
digital-employee/
├── backend-auth/        # 身份中心服务（搭建中）
├── backend-data/        # 数据平台后端服务
├── backend-gateway/     # Python 飞书消息网关
├── backend-share/       # 跨服务共享包（nacos-client 等）
├── frontend/            # React + TypeScript 管理端
├── scripts/             # 各模块运维、启动与清理脚本（含一键启动脚本 start-all.bat / start-all.sh）
└── Makefile             # 可选的统一开发命令
```

## 服务端口一览

| 模块 / 服务 | 默认端口 | 协议 / 类型 | 说明及常用地址 |
| --- | --- | --- | --- |
| **`backend-gateway`** | `8864` | HTTP | 飞书消息网关 API (<http://localhost:8864>)，健康检查为 `GET /api/v1/health` |
| **`backend-data`** | `8010` | HTTP | 数据平台后端 API (<http://127.0.0.1:8010>)，Swagger 文档 (<http://127.0.0.1:8010/docs>) |
| **`backend-auth`** | `8020` | HTTP | 身份中心 API（搭建中） |
| **`frontend`** | `5173` | HTTP | React 前端 Vite 开发服务器 (<http://localhost:5173>) |

基础设施（部署在服务器，通过 Nacos 配置中心下发连接信息）：

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| Nacos | `18848` | 配置中心 API（Web 控制台 `18838`） |
| PostgreSQL | `15432` | 主数据库（`db_data` / `db_rag` 两个库） |
| Redis | `16379` | 缓存 + token 存储 |
| MinIO | `19000` | 对象存储 API（控制台 `19001`） |
| RabbitMQ | `25672` | AMQP（管理界面 `15670`） |

## 环境要求

- `backend-gateway` / `backend-data` / `backend-auth`：Python 3.11+、[uv](https://docs.astral.sh/uv/)
- `frontend`：`package.json` 当前声明 Node.js 22.14.x
- 前端依赖安装：npm

## 快速启动（开箱即用）

所有后端服务的 `.env` 配置已默认指向 prod 环境 Nacos（`106.54.60.80`，受限账号 `test`），新成员克隆代码后直接运行启动脚本即可。

### Windows

```powershell
# 一键启动所有服务（会自动复制 .env.example -> .env）
scripts\start-all.bat

# 或单独启动某个服务
scripts\backend-gateway\start.bat
scripts\data-platform\start.bat
scripts\frontend\start-web.bat
```

### Linux / macOS

```bash
# 一键启动所有服务
./scripts/start-all.sh

# 或单独启动某个服务
./scripts/backend-gateway/start.sh
./scripts/data-platform/start.sh
./scripts/frontend/start-web.sh
```

启动脚本会自动：
1. 复制 `.env.example` → `.env`（首次启动）
2. 安装前端依赖（首次启动）
3. 启动服务并打印健康检查地址

> **注意**：启动脚本需要 `uv` 在 PATH 中。Windows 安装 uv：`pip install uv`；其他平台见 [uv 官方文档](https://docs.astral.sh/uv/)。

### 手动启动单个服务

```powershell
# backend-gateway
cd backend-gateway
uv sync
Copy-Item .env.example .env
Copy-Item config\bot.template.json config\bot.json
uv run uvicorn src.main:app --host 0.0.0.0 --port 8864

# backend-data
cd backend-data\backend
uv sync
Copy-Item .env.example .env
uv run uvicorn app.main:app --host 0.0.0.0 --port 8010

# frontend
cd frontend
npm ci
npm run dev
```

## 配置中心（Nacos）

所有后端服务启动时通过 `backend-share/nacos-client` 从 Nacos 拉取共享基础设施配置（DB/Redis/MinIO/RabbitMQ 连接信息），优先级高于本地 `.env`。

- Nacos 凭证（`NACOS_*` 系列环境变量）只从环境变量读取，不入库不入 Nacos，避免循环依赖。
- 配置 `dataId` 默认为 `${NACOS_NAMESPACE}.yaml`（即 `prod.yaml` / `dev.yaml`），`DEFAULT_GROUP`。
- Nacos 不可达时静默降级到本地 `.env`，仅打日志，不阻塞启动。

## Makefile

安装了 GNU Make 的环境可以使用以下统一命令：

```text
make install          # 安装 Gateway、Data 和前端依赖
make infra-up         # 启动 RabbitMQ 与 MinIO
make dev-gateway      # 启动 backend-gateway
make dev-frontend     # 启动 React 管理端开发服务器
make build            # 构建前端
make check            # 运行现有测试、lint 和构建检查
```

Windows 环境不要求安装 Make，可直接执行上文的启动脚本。

## 验证

```powershell
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
