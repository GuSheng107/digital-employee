# Digital Employee - 数字员工

Digital Employee 是一个面向企业 IM 场景的数字员工项目。仓库当前包含一套飞书消息网关、一套数据中台服务、一套正在搭建的身份认证服务，以及一套 React 管理端前端。

## 当前实现

| 模块 | 默认端口 | 技术栈 | 当前职责与状态 |
| --- | --- | --- | --- |
| `backend-gateway/` | `8864` | Python 3.11+、FastAPI、平台 SDK | 飞书/企业微信协议适配、消息归一化、Test/Prod 路由和 Admin API |
| `backend-data/` | `8010` | Python 3.11+、FastAPI、PostgreSQL、Redis、MinIO、RabbitMQ | 全仓库唯一基础设施访问服务，含身份数据、对象存储和可靠消息租约 |
| `backend-auth/` | `8020` | Python 3.11+、FastAPI | 登录、注册、密码策略、用户/角色/菜单/权限业务编排 |
| `frontend/` | `5173` | React 19、TypeScript、Ant Design 6、Vite 8 | 管理端前端，对接各后端服务的 API |
| `backend-share/` | - | Python 3.11+ | 跨服务契约：`data-client`、`auth-utils`、`api-common`、`nacos-client` |

当前可确认的平台实现：

- 飞书：由 `backend-gateway/src/platforms/feishu/` 接入。
- 企业微信：由 `backend-gateway/src/platforms/wechat/` 接入。

## 架构现状

```text
飞书 / 企业微信
       |
backend-gateway
       |  backend-share/data-client
       v
backend-data <-> PostgreSQL / Redis / MinIO / RabbitMQ
       ^
       |  backend-share/data-client
backend-auth

其他服务 --backend-share/auth-utils--> backend-auth
```

硬边界：

- 数据库、Redis、MinIO、RabbitMQ 的驱动、连接和执行只允许出现在
  `backend-data`。
- 其他服务只能通过 `backend-share/data-client` 使用数据与基础设施能力。
- 其他服务只能通过 `backend-share/auth-utils` 获取用户上下文和执行权限校验。
- 禁止跨服务导入对方的实现目录。

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
| **`backend-auth`** | `8020` | HTTP | 身份中心 API |
| **`frontend`** | `5173` | HTTP | React 前端 Vite 开发服务器 (<http://localhost:5173>) |

基础设施地址与凭证只配置给 `backend-data`，并通过部署环境或 Nacos 下发，
不在仓库文档中记录实际服务器地址。

## 环境要求

- `backend-gateway` / `backend-data` / `backend-auth`：Python 3.11+、[uv](https://docs.astral.sh/uv/)
- `frontend`：`package.json` 当前声明 Node.js 22.14.x
- 前端依赖安装：npm

## 快速启动（开箱即用）

各服务从 `.env.example` 创建本地 `.env`。模板只提供本机占位值，不包含
任何生产、测试或开发环境凭证。

### Windows

```powershell
# 一键启动所有服务（会自动复制 .env.example -> .env）
scripts\start-all.bat

# 或单独启动某个服务
scripts\data-platform\start.bat
scripts\backend-auth\start.bat
scripts\backend-gateway\start.bat
scripts\frontend\start-web.bat
```

### Linux / macOS

```bash
# 一键启动所有服务
./scripts/start-all.sh

# 或单独启动某个服务
./scripts/data-platform/start.sh
./scripts/backend-auth/start.sh
./scripts/backend-gateway/start.sh
./scripts/frontend/start-web.sh
```

启动脚本会自动：
1. 复制 `.env.example` → `.env`（首次启动）
2. 清理 `8010`、`8020`、`8864`、`5173` 上的旧项目进程
3. 按 `backend-data` → `backend-auth` → `backend-gateway` → `frontend` 顺序启动
4. 注入统一的服务间 API Key，并验证基础设施依赖与消息中间件拓扑
5. 任一服务或依赖未就绪时结束本次启动并清理已启动进程

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

# backend-auth
cd ..\..\backend-auth
uv sync
Copy-Item .env.example .env
uv run uvicorn app.main:app --host 0.0.0.0 --port 8020

# frontend
cd ..\frontend
npm ci
npm run dev
```

## 配置中心（Nacos）

`backend-data` 可通过 `backend-share/nacos-client` 拉取基础设施配置，
其他服务只拉取自身运行配置及 share 服务地址。

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
