# 后端服务说明

本目录是数字员工数据中台的 FastAPI 后端服务，负责统一封装 PostgreSQL、Redis、MinIO 和 DDL 建表能力。

## 技术栈

- Python 3.10+
- FastAPI
- Uvicorn
- SQLAlchemy 2.0
- psycopg2-binary
- redis-py
- python-dotenv
- MinIO Python SDK
- Pydantic
- pytest

## 安装依赖

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 配置环境变量

```bash
copy .env.example .env
```

然后按本机或服务器环境修改 `.env`。

注意：

- `.env.example` 只保存模板。
- `.env` 可以保存本地测试密码，但不要提交到 Git。
- 数据库、Redis、MinIO、DDL 连接配置都从 `.env` 读取。
- 代码里不硬编码账号、密码、IP、端口。

## 启动服务

本机启动：

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

服务器启动：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问：

- 根路径：`http://127.0.0.1:8000/`
- 健康检查：`http://127.0.0.1:8000/health`
- Swagger 文档：`http://127.0.0.1:8000/docs`

## 分层结构

```text
router -> service -> repository/client wrapper
```

说明：

- `api/routes/`：接口层，只处理请求和响应。
- `services/`：业务编排层。
- `repositories/`：数据库表访问层。
- `core/database.py`：PostgreSQL 连接封装。
- `core/redis_client.py`：Redis 客户端封装。
- `core/minio_client.py`：MinIO 客户端封装。
- `utils/response.py`：统一响应格式。

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
- `POST /api/v1/ddl/tables/preview`
- `POST /api/v1/ddl/tables`

## DDL 建表工具

当前 DDL 工具只支持 PostgreSQL 16 `CREATE TABLE`。

配置项：

```env
DDL_DATABASE_URL=postgresql+psycopg2://ddl_user:your_password@127.0.0.1:5432/digital_employee_core?sslmode=disable
DDL_ALLOWED_DATABASE=digital_employee_core
DDL_ALLOWED_SCHEMAS=public
DDL_EXECUTION_ENABLED=false
```

接口：

- `POST /api/v1/ddl/tables/preview`：根据结构化参数生成 DDL，不连接数据库。
- `POST /api/v1/ddl/tables`：重新校验结构化参数，重新生成 DDL，并在安全开关开启后执行建表。

执行限制：

- 默认关闭。
- 只允许 `APP_ENV=local/dev/test`。
- 必须配置独立 DDL 账号。
- 目标数据库必须匹配 `DDL_ALLOWED_DATABASE`。
- 目标 schema 必须在 `DDL_ALLOWED_SCHEMAS` 内。
- 不执行前端传入 SQL。

详细说明见 `../docs/ddl-tool/README.md`。

## 测试

```bash
python -m pytest tests/test_ddl_generator.py -q
```

当前自动测试覆盖：

- 合法 DDL 生成。
- 非法标识符拒绝。
- 重复字段拒绝。
- 默认值 SQL 注入拒绝。
- 预览不依赖数据库。
- 默认禁止执行。
