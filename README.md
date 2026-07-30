# Digital Employee - 数字员工

Digital Employee 是一个面向企业 IM 场景的数字员工项目。仓库当前包含一套飞书消息网关、一套数据中台服务、一套正在搭建的身份认证服务，以及一套 React 管理端前端。

## 当前实现


| 模块                 | 默认端口   | 技术栈                                                  | 当前职责与状态                                                      |
| ------------------ | ------ | ---------------------------------------------------- | ------------------------------------------------------------ |
| `backend-gateway/` | `8864` | Python 3.11+、FastAPI、平台 SDK                          | 飞书/企业微信协议适配、消息归一化、Test/Prod 路由和 Admin API                    |
| `backend-data/`    | `8010` | Python 3.11+、FastAPI、PostgreSQL、Redis、MinIO、RabbitMQ | 全仓库唯一基础设施访问服务，含身份数据、对象存储和可靠消息租约                              |
| `backend-auth/`    | `8020` | Python 3.11+、FastAPI                                 | 登录、注册、密码策略、用户/角色/菜单/权限业务编排                                   |
| `frontend/`        | `5173` | React 19、TypeScript、Ant Design 6、Vite 8              | 管理端前端，对接各后端服务的 API                                           |
| `backend-share/`   | -      | Python 3.11+                                         | 跨服务契约：`data-client`、`auth-utils`、`api-common`、`nacos-client` |


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


| 模块 / 服务           | 默认端口   | 协议 / 类型 | 说明及常用地址                                                                                |
| ----------------- | ------ | ------- | -------------------------------------------------------------------------------------- |
| `backend-gateway` | `8864` | HTTP    | 飞书消息网关 API ([http://localhost:8864](http://localhost:8864))，健康检查为 `GET /api/v1/health` |
| `backend-data`    | `8010` | HTTP    | 数据平台后端 API ([http://127.0.0.1:8010](http://127.0.0.1:8010))；production 模式不暴露接口文档       |
| `backend-auth`    | `8020` | HTTP    | 身份中心 API                                                                               |
| `frontend`        | `5173` | HTTP    | React 前端 Vite 开发服务器 ([http://localhost:5173](http://localhost:5173))                   |


基础设施地址与凭证只配置给 `backend-data`，并通过部署环境或 Nacos 下发，
不在仓库文档中记录实际服务器地址。

## 环境要求


| 工具                               | 版本要求                                                  | 用途                                                  |
| -------------------------------- | ----------------------------------------------------- | --------------------------------------------------- |
| Python                           | 3.11+                                                 | `backend-gateway` / `backend-data` / `backend-auth` |
| [uv](https://docs.astral.sh/uv/) | 当前稳定版                                                 | 后端依赖安装与启动（必须在 PATH 中）                               |
| Node.js                          | **22.14.x**（以 `frontend/package.json` 的 `engines` 为准） | 前端构建与 preview                                       |
| npm                              | 随 Node 安装                                             | 前端依赖                                                |
| Docker Compose                   | 可选                                                    | 仅本地兜底时启动 RabbitMQ / MinIO（`make infra-up`）          |

> 用 Node 18/20 安装前端依赖时，Vite 8 / Rolldown 的可选原生包常被静默跳过，随后 `npm run build` 会报 `@rolldown/binding-*` 缺失。请先 `node -v` 确认为 `22.14.x`。

## 快速启动（开箱即用）

一键脚本**只启动应用进程**，**不会**自动拉起 Postgres / Redis / RabbitMQ / MinIO / Nacos。
启动结束后还会探活 `backend-data` 的基础设施依赖与消息中间件拓扑；依赖不可达时整次启动会失败并清理已起进程。

因此「开箱即用」的完整顺序是：**装好工具 → 配好基础设施入口 → 再跑一键启动**。

### 1. 准备基础设施（二选一）

#### 方式 A：连团队 Nacos（推荐）

`.env.example` 里的 `NACOS_*` 是占位值（本机 `127.0.0.1:8848`、账号密码为空）。
Nacos 不可达或缺凭证时会**静默降级**到本地 `.env`，但本地兜底里的 DB / Redis 等密码通常也是空的，最终仍会在依赖验收阶段失败。

首次启动前，向团队获取 Nacos 地址与账号，写入至少 `backend-data/backend/.env`（建议 gateway / auth 一并对齐）：

```text
NACOS_SERVER_ADDR=<host:port>
NACOS_USERNAME=<账号>
NACOS_PASSWORD=<密码>
NACOS_NAMESPACE=prod
```

- 配置 `dataId` 默认为 `${NACOS_NAMESPACE}.yaml`（即 `prod.yaml`），`DEFAULT_GROUP`。
- 基础设施真实地址与凭证由 Nacos 下发，不在仓库文档中记录。
- 更细的约定见下文「配置中心（Nacos）」与 [CONTRIBUTING.md](CONTRIBUTING.md)。

#### 方式 B：纯本地兜底

1. 自行准备 Postgres、Redis，并按需启动 compose 中的 RabbitMQ / MinIO：

```bash
make infra-up
# 或：docker compose up -d
```

2. 在 `backend-data/backend/.env` 填齐本地回退项（`CORE_DB_*`、`REDIS_*`、`MINIO_*`、`RABBITMQ_URL` 等）。
   注意：根目录 `docker-compose.yml` **只包含** RabbitMQ 与 MinIO，**不包含** Postgres / Redis；端口也以你的 `.env` 为准（MinIO 默认映射到主机 `19000`）。
3. 若不走 Nacos，可将各服务 `.env` 中的 `NACOS_SERVER_ADDR=` 留空，避免无意义的拉取尝试。

### 2. 一键启动应用

各服务首次启动时会从 `.env.example` 复制出本地 `.env`（若尚不存在）。模板只提供非敏感占位值。

#### Windows

```powershell
# 确认工具版本
python --version
uv --version
node -v   # 应为 v22.14.x

# 一键启动所有服务
scripts\start-all.bat

# 或单独启动某个服务（不会做 start-all 那套依赖同步 / API Key 注入 / 验收）
scripts\data-platform\start.bat
scripts\backend-auth\start.bat
scripts\backend-gateway\start.bat
scripts\frontend\start-web.bat
```

#### Linux / macOS

```bash
# 确认工具版本
python3 --version
uv --version
node -v   # 应为 v22.14.x

# 一键启动所有服务
./scripts/start-all.sh

# 或单独启动某个服务（不会做 start-all 那套依赖同步 / API Key 注入 / 验收）
./scripts/data-platform/start.sh
./scripts/backend-auth/start.sh
./scripts/backend-gateway/start.sh
./scripts/frontend/start-web.sh
```

`start-all` 会自动：

1. 复制 `.env.example` → `.env`，并创建 `backend-gateway/config/bot.json`（首次启动）
2. 当 `backend-data` 的 `API_KEY` 为空时生成强随机密钥并持久化到本地 `.env`
3. 对三个后端执行 `uv sync --locked`；若 `frontend/node_modules` **不存在** 则 `npm ci`，再 `npm run build`
4. 清理 `8010`、`8020`、`8864`、`5173` 上的旧项目进程
5. 按 `backend-data` → `backend-auth` → `backend-gateway` → `frontend preview` 顺序启动
6. 将同一份 `API_KEY` 注入 auth / gateway 进程环境，并验收基础设施依赖与消息拓扑
7. 任一服务或依赖未就绪时结束本次启动并清理已启动进程

成功后可访问：

| 服务 | 地址 |
| --- | --- |
| Frontend preview | <http://127.0.0.1:5173> |
| backend-auth | <http://127.0.0.1:8020/api/v1/health> |
| backend-data | <http://127.0.0.1:8010/api/v1/health> |
| backend-gateway | <http://127.0.0.1:8864/api/v1/health> |

体验账号：`test` / 密码：`test`

> 启动脚本需要 `uv` 在 PATH 中。Windows 安装 uv：`pip install uv`；其他平台见 [uv 官方文档](https://docs.astral.sh/uv/)。
>
> `start-all` 会把服务放到独立进程会话中，脚本退出后 **Ctrl+C 无法停止服务**。停止请执行：
> `python scripts/kill-port.py`（或指定 `8010 8020 8864 5173`）。

### 3. 常见启动失败

| 现象 | 常见原因 | 处理 |
| --- | --- | --- |
| `Backend Data dependencies` / RabbitMQ / Redis 验收失败 | 未连上 Nacos，且本机基础设施未起或 `.env` 密码为空 | 按上文补齐 Nacos，或本地起依赖并填 `.env` |
| `uv sync --locked` 失败 | `uv.lock` 与 `pyproject.toml` 不一致 | 在对应后端目录执行 `uv lock` 后再启动；若是别人改坏的锁文件，应提 PR 修复而不是长期本地绕过 |
| `@rolldown/binding-*` 缺失 / Vite 要求 Node 20.19+ | Node 版本不对，或半残 `node_modules` | 切换到 Node `22.14.x` 后删除 `frontend/node_modules` 再 `npm ci`（`start-all` 只在目录不存在时安装） |
| 单独脚本启动后 auth/gateway 调 data 401 | 服务间 API Key 未对齐 | 优先用 `start-all`；或手动让 `BACKEND_DATA_API_KEY` 等于 `backend-data` 的 `API_KEY` |
| 未找到 `uv` / `npm` | 工具未安装或不在 PATH | 先满足「环境要求」再启动 |
| Ctrl+C 停不掉服务 | 子进程已脱离终端会话 | 使用 `python scripts/kill-port.py` |

### 手动启动单个服务

适合调试单个进程；仍需先满足上文的基础设施与 Node / uv 要求，并自行对齐 `API_KEY`。

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

# frontend（请先确认 node -v 为 22.14.x）
cd ..\frontend
npm ci
npm run build
npm run preview -- --host 127.0.0.1 --port 5173
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
