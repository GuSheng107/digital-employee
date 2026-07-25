# 数字员工数据中台服务

`digital-employee-data-platform` 是一个独立运行的数据中台服务，用于统一封装数字员工项目里的 PostgreSQL、Redis、MinIO 访问能力。其他业务项目原则上不直接操作数据库、缓存和对象存储，而是通过本服务提供的 API 访问。

## 项目定位

- 后端：FastAPI，默认端口 `8000`。
- 前端：Vue 3 + Vite + Element Plus，默认端口 `5174`。
- 数据库：PostgreSQL 普通业务库和向量库连接预留。
- 缓存：Redis。
- 对象存储：MinIO。
- DDL 工具：提供 PostgreSQL 16 `CREATE TABLE` 的可视化预览和受控执行能力。

## 目录结构

```text
backend/              后端服务
frontend/             前端管理页面
docs/ddl-tool/        DDL 建表工具文档
README.md             团队总览文档
```

## 快速启动

### 1. 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

访问：

- 服务根路径：`http://127.0.0.1:8000/`
- 健康检查：`http://127.0.0.1:8000/health`
- Swagger 文档：`http://127.0.0.1:8000/docs`

### 2. 启动前端

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

访问：

- 前端页面：`http://127.0.0.1:5174`

如果部署在服务器并希望局域网或公网访问，后端可以使用：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

前端 `.env` 中的 API 地址示例：

```env
VITE_API_BASE_URL=http://101.37.69.110:8000
```

## 环境变量说明

后端配置集中在 `backend/.env`，模板见 `backend/.env.example`。模板文件只放占位值，不应写入真实生产密码。

核心配置包括：

```env
APP_ENV=local
APP_HOST=127.0.0.1
APP_PORT=8000
API_PREFIX=/api/v1

CORE_DB_HOST=127.0.0.1
CORE_DB_PORT=5432
CORE_DB_NAME=digital_employee_core
CORE_DB_USER=postgres
CORE_DB_PASSWORD=your_password

VECTOR_DB_HOST=127.0.0.1
VECTOR_DB_PORT=5432
VECTOR_DB_NAME=digital_employee_vector
VECTOR_DB_USER=postgres
VECTOR_DB_PASSWORD=your_password

REDIS_HOST=127.0.0.1
REDIS_PORT=6379

MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_DEFAULT_BUCKET=digital-employee
```

DDL 建表工具额外配置：

```env
DDL_DATABASE_URL=postgresql+psycopg2://ddl_user:your_password@127.0.0.1:5432/digital_employee_core?sslmode=disable
DDL_ALLOWED_DATABASE=digital_employee_core
DDL_ALLOWED_SCHEMAS=public
DDL_EXECUTION_ENABLED=false
```

默认情况下 `DDL_EXECUTION_ENABLED=false`，只能预览 DDL，不会执行建表。

## 主要功能

- Dashboard：查看后端、PostgreSQL、Redis、MinIO 状态。
- System Config：查看脱敏配置，手动测试连接。
- Data Items：通过 `data_items` 表验证数据库 CRUD 链路。
- Storage：通过 API 验证 MinIO bucket 和测试对象读写。
- Cache：通过 API 验证 Redis 测试 key 读写。
- DDL 建表工具：结构化填写表定义，生成 PostgreSQL 16 `CREATE TABLE` SQL，并在安全开关开启后受控执行。

## 关键接口

- `GET /`
- `GET /health`
- `GET /api/v1/health/dependencies`
- `GET /api/v1/system/config`
- `POST /api/v1/system/test-connections`
- `POST /api/v1/data-items`
- `GET /api/v1/data-items`
- `PUT /api/v1/data-items/{item_id}`
- `DELETE /api/v1/data-items/{item_id}`
- `POST /api/v1/cache/test`
- `GET /api/v1/cache/test`
- `POST /api/v1/storage/buckets/ensure`
- `GET /api/v1/storage/buckets`
- `POST /api/v1/storage/test-object`
- `GET /api/v1/storage/test-object`
- `POST /api/v1/ddl/tables/preview`
- `POST /api/v1/ddl/tables`

## DDL 建表工具说明

DDL 工具当前只支持 PostgreSQL 16 的 `CREATE TABLE`。

安全约束：

- 不提供自由 SQL 编辑器。
- 不支持 `ALTER`、`DROP`、`TRUNCATE`、`DELETE`。
- 预览接口不连接数据库。
- 执行接口不接收前端 SQL，只接收结构化表定义。
- 后端会重新校验结构化参数并重新生成 SQL。
- 执行默认关闭。
- 仅允许 `APP_ENV=local/dev/test`。
- 必须使用独立 DDL 账号，不能使用业务账号或管理员账号。
- `DDL_DATABASE_URL` 中的数据库名必须等于 `DDL_ALLOWED_DATABASE`。
- schema 必须在 `DDL_ALLOWED_SCHEMAS` 白名单内。

详细文档见：

- [DDL 工具总览](docs/ddl-tool/README.md)
- [DDL API 文档](docs/ddl-tool/api.md)
- [DDL 安全说明](docs/ddl-tool/security.md)
- [DDL 测试说明](docs/ddl-tool/testing.md)
- [DDL 集成指南](docs/ddl-tool/integration-guide.md)

## 返回格式

接口统一返回：

```json
{
  "success": true,
  "message": "ok",
  "data": {}
}
```

失败时：

```json
{
  "success": false,
  "message": "错误说明",
  "data": null
}
```

## 与原数字员工项目的交互方式

原业务项目不直接连接 PostgreSQL、Redis、MinIO，而是通过本数据中台调用统一 API：

```text
业务项目
  -> HTTP API
  -> digital-employee-data-platform
  -> PostgreSQL / Redis / MinIO
```

这样可以把数据访问、连接配置、权限控制、审计日志和后续扩展集中在一个服务内维护。

## 测试命令

后端单元测试：

```bash
cd backend
python -m pytest tests/test_ddl_generator.py -q
```

前端构建验证：

```bash
cd frontend
npm run build
```
