# Backend Auth

数字员工身份中心服务：用户登录、双 token 鉴权、用户/角色/权限/菜单/Bot 权限管理。

## 技术栈

- Python 3.11+、[uv](https://docs.astral.sh/uv/)
- FastAPI、Uvicorn
- PostgreSQL（共用 `db_data` 库）
- Redis（双 token 存储 + 缓存）
- [backend-share/nacos-client](../backend-share/nacos-client)（配置中心）

## 鉴权方案

**双 token + Redis 存储（不使用 JWT）**

- `access_token`：短 TTL（默认 30 分钟），用于业务接口鉴权。
- `refresh_token`：长 TTL（默认 7 天），用于换取新的 access_token。
- Token 为 opaque 字符串（`secrets.token_urlsafe`），所有状态保存在 Redis，支持主动失效。
- 各服务本地查 Redis 验证 token，去中心化鉴权，不依赖 auth 服务在线。

Redis key 设计：

```
auth:access:{token}    -> user_id      (TTL = access_token_ttl)
auth:refresh:{token}   -> user_id      (TTL = refresh_token_ttl)
auth:user:{uid}:tokens -> set[token]   (用户活跃 token 集合，用于全量登出)
```

## 目录结构

```text
backend-auth/
├── app/
│   ├── api/            # 路由与依赖
│   ├── core/           # 配置、数据库、Redis、安全工具
│   ├── models/         # SQLAlchemy ORM 模型
│   ├── schemas/        # Pydantic 请求/响应模型
│   ├── services/       # 业务编排层
│   ├── utils/          # 通用工具
│   └── main.py         # FastAPI 启动入口
├── docs/
│   └── schema.sql      # 数据库表结构初始化脚本
├── tests/
├── .env.example
└── pyproject.toml
```

## 快速启动

```bash
# 1. 安装依赖
uv sync

# 2. 复制配置
cp .env.example .env

# 3. 启动服务（默认端口 8020）
uv run uvicorn app.main:app --host 0.0.0.0 --port 8020
```

健康检查：`GET http://localhost:8020/api/v1/health`

Swagger 文档：`http://localhost:8020/docs`（生产环境关闭）

## 数据库初始化

执行一次 `docs/schema.sql` 建表（幂等）：

```bash
docker exec -i dk-pg16 psql -U postgres -d db_data < backend-auth/docs/schema.sql
```
