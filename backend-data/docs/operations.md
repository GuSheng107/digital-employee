# 运维说明

## 启动

```bash
chmod +x scripts/data-platform/*.sh
./scripts/data-platform/start.sh
```

脚本会读取 `backend/.env` 中的 `APP_HOST` 和 `APP_PORT`，默认端口为 `8010`。

## 停止

```bash
./scripts/data-platform/stop.sh
```

## 状态检查

```bash
./scripts/data-platform/status.sh
```

状态脚本会检查进程 PID，并调用：

```text
http://<APP_HOST>:<APP_PORT>/health
```

## 日志位置

```text
logs/backend.log
```

日志目录由启动脚本自动创建，不提交 Git。

## 常用健康检查

```bash
curl http://127.0.0.1:8010/health
curl http://127.0.0.1:8010/api/v1/health/dependencies
```

## 故障排查

### 端口被占用

确认是否已有主项目 Gateway 或其他服务占用端口。数据中台默认使用 `8010`，主项目 Gateway 通常使用 `8000`。

### PostgreSQL 连接失败

检查：

- `CORE_DB_HOST`
- `CORE_DB_PORT`
- `CORE_DB_NAME`
- `CORE_DB_USER`
- `CORE_DB_PASSWORD`
- 数据库防火墙和白名单
- 账号是否是受限业务账号

### 表不存在

数据中台不会自动建表。请通过 CloudBeaver Community 创建或调整表结构。

### Redis 写入失败

如果出现 `MISCONF`，通常是 Redis 服务器 RDB 持久化失败导致禁止写入，需要检查 Redis 服务端磁盘和持久化配置。

### MinIO 访问失败

检查：

- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`
- bucket 是否存在
- 服务端网络和防火墙
