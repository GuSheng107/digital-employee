# Digital Employee — 把企业 IM 里的重复活交给数字员工

面向飞书 / 企业微信的数字员工平台。一套网关接消息、一套数据中台管基础设施、一套身份中心做认证、一套 React 管理端做编排。

支持平台：

- 飞书：`backend-gateway/src/platforms/feishu/`
- 企业微信：`backend-gateway/src/platforms/wechat/`

## 模块

| 模块 | 端口 | 技术栈 | 职责 |
| --- | --- | --- | --- |
| `backend-gateway/` | `8864` | Python 3.11+、FastAPI、平台 SDK | 飞书/企业微信协议适配、消息归一化、Test/Prod 路由和 Admin API |
| `backend-data/` | `8010` | Python 3.11+、FastAPI、PostgreSQL、Redis、MinIO、RabbitMQ | 仓库唯一基础设施访问服务，含身份数据、对象存储和可靠消息租约 |
| `backend-auth/` | `8020` | Python 3.11+、FastAPI | 登录、注册、密码策略、用户/角色/菜单/权限业务编排 |
| `frontend/` | `5173` | React 19、TypeScript、Ant Design 6、Vite 8 | 管理端前端，对接各后端服务 API |
| `backend-share/` | - | Python 3.11+ | 跨服务契约：`data-client`、`auth-utils`、`api-common`、`nacos-client` |

## 架构

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

- 数据库、Redis、MinIO、RabbitMQ 的驱动、连接和执行只在 `backend-data`。
- 其他服务通过 `backend-share/data-client` 使用数据与基础设施能力。
- 其他服务通过 `backend-share/auth-utils` 获取用户上下文和执行权限校验。
- 禁止跨服务导入对方的实现目录。

## 目录结构

```text
digital-employee/
├── backend-auth/        # 身份中心服务
├── backend-data/        # 数据平台后端服务
├── backend-gateway/     # 飞书消息网关
├── backend-share/       # 跨服务共享包
├── frontend/            # React + TypeScript 管理端
├── scripts/             # 启动与清理脚本（含一键启动 start-all.bat / start-all.sh）
└── Makefile             # 可选的统一开发命令
```

## 环境要求

| 工具 | 版本 | 用途 |
| --- | --- | --- |
| Python | 3.11+ | `backend-gateway` / `backend-data` / `backend-auth` |
| [uv](https://docs.astral.sh/uv/) | 当前稳定版 | 后端依赖安装与启动 |
| Node.js | 22.14.x | 前端构建与 preview |
| npm | 随 Node 安装 | 前端依赖 |
| Docker Compose | 可选 | 本地兜底 RabbitMQ / MinIO（`make infra-up`） |

## 快速启动

一键脚本只启动应用进程，不拉起 Postgres / Redis / RabbitMQ / MinIO / Nacos。启动结束后会探活 `backend-data` 的基础设施依赖与消息拓扑；依赖不可达时整次启动失败并清理已起进程。

完整顺序：装好工具 → 配好基础设施入口 → 跑一键启动。

### 1. 准备基础设施（二选一）

#### 方式 A：连团队 Nacos（推荐）

`.env.example` 里的 `NACOS_*` 是占位值。Nacos 不可达或缺凭证时静默降级到本地 `.env`，但本地兜底里的 DB / Redis 等密码通常也是空的，最终仍会在依赖验收阶段失败。

首次启动前向团队获取 Nacos 地址与账号，写入 `backend-data/backend/.env`（建议 gateway / auth 一并对齐）：

```text
NACOS_SERVER_ADDR=<host:port>
NACOS_USERNAME=<账号>
NACOS_PASSWORD=<密码>
NACOS_NAMESPACE=prod
```

- `dataId` 默认 `${NACOS_NAMESPACE}.yaml`（即 `prod.yaml`），`DEFAULT_GROUP`。
- 基础设施真实地址与凭证由 Nacos 下发，不入仓库文档。

#### 方式 B：纯本地兜底

1. 准备 Postgres、Redis，按需启动 RabbitMQ / MinIO：

```bash
make infra-up
# 或：docker compose up -d
```

2. 在 `backend-data/backend/.env` 填齐本地回退项（`CORE_DB_*`、`REDIS_*`、`MINIO_*`、`RABBITMQ_URL` 等）。
   根目录 `docker-compose.yml` 只含 RabbitMQ 与 MinIO，不含 Postgres / Redis；端口以 `.env` 为准（MinIO 默认映射主机 `19000`）。
3. 不走 Nacos 时把各服务 `.env` 的 `NACOS_SERVER_ADDR=` 留空，避免无意义拉取。

### 2. 一键启动应用

各服务首次启动会从 `.env.example` 复制出本地 `.env`（若尚不存在）。模板只提供非敏感占位值。

#### Windows

```powershell
python --version
uv --version
node -v   # 应为 v22.14.x

scripts\start-all.bat
```

#### Linux / macOS

```bash
python3 --version
uv --version
node -v   # 应为 v22.14.x

./scripts/start-all.sh
```

`start-all` 自动完成：

1. 复制 `.env.example` → `.env`（首次启动）
2. `backend-data` 的 `API_KEY` 为空时生成强随机密钥并写入本地 `.env`
3. 三个后端执行 `uv sync --locked`；`frontend/node_modules` 不存在则 `npm ci`，再 `npm run build`
4. 清理 `8010`、`8020`、`8864`、`5173` 上的旧进程
5. 按 `backend-data` → `backend-auth` → `backend-gateway` → `frontend preview` 顺序启动
6. 同一份 `API_KEY` 注入 auth / gateway 进程环境，验收基础设施依赖与消息拓扑
7. 任一服务或依赖未就绪时结束启动并清理已起进程

启动成功后访问：

| 服务 | 地址 |
| --- | --- |
| Frontend | http://127.0.0.1:5173 |
| backend-auth | http://127.0.0.1:8020/api/v1/health |
| backend-data | http://127.0.0.1:8010/api/v1/health |
| backend-gateway | http://127.0.0.1:8864/api/v1/health |

体验账号：`youke` / 密码：`youkezhanghao@2026`

> `start-all` 把服务放到独立进程会话，脚本退出后 Ctrl+C 无法停止服务。停止执行：`python scripts/kill-port.py`（或指定 `8010 8020 8864 5173`）。

### 手动启动单个服务

调试单进程用；仍需先满足基础设施与 Node / uv 要求，并自行对齐 `API_KEY`。

```powershell
# backend-gateway
cd backend-gateway
uv sync
Copy-Item .env.example .env
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

# frontend（确认 node -v 为 22.14.x）
cd ..\frontend
npm ci
npm run build
npm run preview -- --host 127.0.0.1 --port 5173
```

## 配置中心（Nacos）

`backend-data` 通过 `backend-share/nacos-client` 拉取基础设施配置，其他服务只拉取自身运行配置及 share 服务地址。

- Nacos 凭证（`NACOS_*`）只从环境变量读取，不入库不入 Nacos，避免循环依赖。
- `dataId` 默认 `${NACOS_NAMESPACE}.yaml`（`prod.yaml` / `dev.yaml`），`DEFAULT_GROUP`。
- Nacos 不可达时静默降级到本地 `.env`，仅打日志，不阻塞启动。

## Makefile

装有 GNU Make 的环境可使用：

```text
make install          # 安装 Gateway、Data 和前端依赖
make infra-up         # 启动 RabbitMQ 与 MinIO
make dev-gateway      # 启动 backend-gateway
make dev-frontend     # 启动 React 管理端开发服务器
make build            # 构建前端
make check            # 运行现有测试、lint 和构建检查
```

Windows 不要求安装 Make，直接执行上文启动脚本。

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

所有进入 `master` 的改动都通过 Pull Request 合入。分支命名、提交格式、测试与 Review 要求见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 致谢

感谢 [linux.do](https://linux.do) 社区的开发者们在项目搭建过程中提供的交流与帮助。

## 许可证

[GNU Affero General Public License v3.0](LICENSE)（AGPL-3.0）。本项目保持开源，但任何对网络用户提供的修改版本也必须以 AGPL-3.0 公开全部源代码，以此阻止他人闭源拿本项目对外提供 SaaS / 商业服务。
