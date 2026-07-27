# 后端服务说明

本目录是数字员工数据中台的 FastAPI 后端服务。

后端只连接已有 PostgreSQL 数据库和已有数据表，不创建、不删除、不修改数据库结构。数据库结构管理由 CloudBeaver Community 负责。

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
uv sync
```

## 配置

```bash
cp .env.example .env
```

配置原则：

- 不提交 `.env`。
- 不在代码中硬编码账号、密码、IP、端口。
- PostgreSQL 使用受限业务账号，不使用管理员账号。
- `.env.example` 只保留模板值。

## 启动

默认端口为 `8010`。

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

访问：

- `http://127.0.0.1:8010/`
- `http://127.0.0.1:8010/health`
- `http://127.0.0.1:8010/docs`

## 分层结构

```text
router -> service -> repository/client wrapper
```

- `api/routes/`：接口层。
- `services/`：业务编排层。
- `repositories/`：已有表的数据访问层。
- `core/database.py`：PostgreSQL 连接封装。
- `core/redis_client.py`：Redis 客户端封装。
- `core/minio_client.py`：MinIO 客户端封装。
- `utils/response.py`：统一响应格式。

## 数据库结构边界

后端不会执行：

- `CREATE DATABASE`
- `CREATE TABLE`
- `ALTER TABLE`
- `DROP TABLE`
- `TRUNCATE`
- 任意 SQL 执行
- SQLAlchemy `create_all()`

如果接口依赖的表不存在，应先通过 CloudBeaver Community 创建或调整表结构。

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

## 测试

```bash
uv run pytest tests -q
```
