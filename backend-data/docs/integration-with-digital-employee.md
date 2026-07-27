# 与数字员工主项目集成说明

数据中台作为主项目中的独立服务目录存在：

```text
digital-employee/
  backend-data/
```

## 运行方式

主项目 `backend-gateway` 默认使用 `8864`，数据中台默认使用 `8010`。

推荐本地启动顺序：

```bash
# 1. 启动主项目 Gateway
cd backend-gateway
uv run python -m src.main

# 2. 启动数据中台
./scripts/data-platform/start.sh
```

## 调用方式

主项目通过 HTTP 调用数据中台：

```text
backend-gateway
  -> http://127.0.0.1:8010/api/v1/...
  -> backend-data
  -> PostgreSQL / Redis / MinIO
```

## 推荐配置

主项目中可以增加一个数据中台地址配置：

```env
DATA_PLATFORM_BASE_URL=http://127.0.0.1:8010
```

具体配置方式按主项目 Gateway 现有配置体系接入。

## 接口示例

健康检查：

```bash
curl http://127.0.0.1:8010/health
```

依赖检查：

```bash
curl http://127.0.0.1:8010/api/v1/health/dependencies
```

查询测试数据：

```bash
curl http://127.0.0.1:8010/api/v1/data-items
```

## 合并注意事项

- 不直接提交 `master`。
- 不提交真实 `.env`。
- 不提交密码、日志、缓存、虚拟环境、构建产物。
- 数据中台不应和主项目 Gateway 共用 `8864` 端口。
- 数据库账号必须是受限业务账号，不得使用 PostgreSQL 管理员账号。
