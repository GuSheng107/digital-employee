# Backend Gateway

企业 IM 机器人流量网关，负责飞书/企业微信协议适配、消息归一化与平台回发。

## 架构边界

网关不持有 PostgreSQL、Redis、MinIO 或 RabbitMQ 驱动与凭证：

```text
platform adapter
  -> backend-share/data-client
  -> backend-data
  -> MinIO / RabbitMQ / Redis relay
```

- 多媒体上传和下载通过 `data-client` 委托 `backend-data`。
- 生产消息发布、拓扑声明和消费都在 `backend-data` 执行。
- 出站消息先由 `backend-data` 转存 Redis，再以 ACK/NACK 租约交付网关；
  超时会重投，超过上限进入有界死信列表。
- `/api/v1/admin/*` 通过 `backend-share/auth-utils` 获取用户上下文，并校验
  `bot:manage`，不使用网关自建鉴权。

## 双模式

- `test`：网关内存异步模拟。
- `prod`：调用 `data-client` 发布标准消息，由 `backend-data` 管理消息基础设施。

## 开发

```bash
uv sync
uv run ruff check src tests
uv run pytest -q
uv run uvicorn src.main:app --host 127.0.0.1 --port 8864
```

复制 `.env.example` 为 `.env` 后，只配置 share 服务地址、服务 API Key、
Nacos 和网关运行参数。RabbitMQ/MinIO 配置只属于 `backend-data`。

管理接口：

- `GET /api/v1/health`
- `GET /api/v1/admin/bots`
- `POST /api/v1/admin/bots`
- `DELETE /api/v1/admin/bots/{bot_id}`
