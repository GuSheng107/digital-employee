# 数字员工数据中台服务

`backend-data` 是数字员工主项目旁路部署的数据访问服务。它只连接已经存在的 PostgreSQL 数据库和数据表，封装必要的数据查询、写入、缓存和对象存储接口。

数据库结构管理不由本服务负责。建库、建表、字段调整、索引调整等结构变更统一由服务器独立部署的 CloudBeaver Community 完成。

## 职责边界

本服务负责：

- 连接已有 PostgreSQL 普通业务库。
- 连接已有 PostgreSQL 向量库，当前阶段先做健康检查预留。
- 连接 Redis，封装必要缓存读写能力。
- 连接 MinIO，封装 bucket 和对象读写能力。
- 基于已有表结构提供 API，例如 `data_items` CRUD。
- 提供健康检查、脱敏配置查看、连接测试接口。

本服务不负责：

- 创建数据库。
- 创建数据表。
- 修改表结构。
- 删除表结构。
- 执行任意 SQL。
- 提供可视化建表页面。
- 替代 CloudBeaver 做数据库结构管理。

## 技术栈

- 后端：Python 3.10+、FastAPI、Uvicorn、SQLAlchemy 2.0、psycopg2-binary、redis-py、python-dotenv、MinIO SDK、Pydantic
- 前端：由主项目 `frontend/` 统一管理，使用 React + TypeScript + Ant Design
- 默认后端端口：`8010`

后端端口从 `8000` 调整为 `8010`，避免和主项目 `backend-gateway` 默认端口冲突。

## 目录结构

```text
backend/              后端服务
scripts/              Linux 启动、停止、状态检查脚本
docs/                 运维、CloudBeaver、主项目集成文档
```

## 快速启动

### 后端

```bash
cd backend-data/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

也可以使用 Linux 脚本：

```bash
cd backend-data
chmod +x scripts/*.sh
./scripts/start.sh
./scripts/status.sh
./scripts/stop.sh
```

### 前端

前端代码已并入主项目 `frontend/`，请参考主项目 `frontend/README.md` 启动开发环境。开发环境下数据中台 API 通过 Vite dev server 代理自动转发到 `http://127.0.0.1:8010`。

访问地址：

- 后端根路径：`http://127.0.0.1:8010/`
- 后端健康检查：`http://127.0.0.1:8010/health`
- 后端 Swagger 文档：`http://127.0.0.1:8010/docs`
- 前端页面：通过主项目 `frontend/` 访问，路径为 `/data-platform/dashboard`、`/data-platform/data-items`、`/data-platform/system-config`

## 配置说明

后端配置文件：

```text
backend/.env
```

模板文件：

```text
backend/.env.example
```

重要原则：

- `.env.example` 只能放模板值。
- `.env` 不提交 Git。
- 生产、测试、开发密码不得写入代码、脚本、README。
- PostgreSQL 必须使用受限业务账号，不得使用 `postgres` 管理员账号。

核心配置示例：

```env
APP_ENV=local
APP_HOST=127.0.0.1
APP_PORT=8010
API_PREFIX=/api/v1

CORE_DB_HOST=127.0.0.1
CORE_DB_PORT=5432
CORE_DB_NAME=digital_employee_core
CORE_DB_USER=digital_employee_app
CORE_DB_PASSWORD=your_password

VECTOR_DB_HOST=127.0.0.1
VECTOR_DB_PORT=5432
VECTOR_DB_NAME=digital_employee_vector
VECTOR_DB_USER=digital_employee_app
VECTOR_DB_PASSWORD=your_password

REDIS_HOST=127.0.0.1
REDIS_PORT=6379

MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=minio_access_key
MINIO_SECRET_KEY=minio_secret_key
MINIO_DEFAULT_BUCKET=digital-employee
```

前端配置（在主项目 `frontend/` 下）：

```env
VITE_DATA_PLATFORM_API_BASE_URL=/data-platform-api
```

开发环境默认通过 Vite dev server 代理转发到 `http://127.0.0.1:8010`，无需手动配置。

## 主要接口

- `GET /`
- `GET /health`
- `GET /api/v1/health/dependencies`
- `GET /api/v1/system/config`
- `POST /api/v1/system/test-connections`
- `POST /api/v1/data-items`
- `GET /api/v1/data-items`
- `GET /api/v1/data-items/{item_id}`
- `PUT /api/v1/data-items/{item_id}`
- `DELETE /api/v1/data-items/{item_id}`
- `POST /api/v1/cache/test`
- `GET /api/v1/cache/test`
- `POST /api/v1/storage/buckets/ensure`
- `GET /api/v1/storage/buckets`
- `POST /api/v1/storage/test-object`
- `GET /api/v1/storage/test-object`

## 与主项目交互方式

```text
digital-employee 主项目
  -> HTTP API
  -> backend-data
  -> PostgreSQL / Redis / MinIO
```

本服务保持独立进程和独立端口，避免直接侵入主项目 `backend-gateway`。

## 文档

- `docs/operations.md`：启动、停止、状态检查、日志和故障排查。
- `docs/cloudbeaver-structure-management.md`：CloudBeaver 结构管理边界。
- `docs/integration-with-digital-employee.md`：主项目集成说明。

## 测试

后端：

```bash
cd backend
python -m pytest tests -q
```
