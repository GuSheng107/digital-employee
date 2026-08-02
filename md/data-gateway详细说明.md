# Data & Gateway (数据与网关) 详细说明文档

在数字员工 (Digital Employee) 系统中，**`backend-gateway` (消息与接入网关)** 与 **`backend-data` (数据平台与基础设施中台)** 共同构成了系统的 **数据与消息中枢 (Data & Gateway Pipeline)**。

本文档专门针对 `backend-gateway` 与 `backend-data` 的配合机制，详细阐述**数据从哪里来、经过什么转换、到哪里去、如何存储与流转**的全过程。

---

## 1. 架构定位与职责区分

| 模块名称 | 默认端口 | 职责定位 | 基础设施权限 | 典型数据动作 |
| :--- | :--- | :--- | :--- | :--- |
| **`backend-gateway`** | `8864` | 边缘接入网关、平台协议适配器 | **无** (无 DB / Redis / MQ / MinIO 直连权限) | IM 回调接收、消息归一化、下行消息长轮询 Relay、平台 API 发送 |
| **`backend-data`** | `8010` | 全局唯一基础设施与持久化数据中台 | **独占** (独占 Postgres, Redis, RabbitMQ, MinIO) | 数据持久化、消息队列拓扑管理、存储 URL 颁发、租约状态控制 |

---

## 2. 数据流向全景图 (Data Flow Map)

```mermaid
graph TD
    subgraph External [外部来源 / 终端]
        FS_PLATFORM[飞书开放平台 / 企微平台]
        CLIENT_UI[React 管理端前端 / 业务服务]
    end

    subgraph Gateway [backend-gateway :8864 接入网关]
        GW_WEBHOOK[Webhook 接口层]
        GW_NORM[Hub 消息归一化引擎]
        GW_RELAY[AMQP 原生异步消费者监听]
        GW_STORAGE[GatewayStorageClient]
        GW_MEM[(内存 Bot 凭证缓存)]
    end

    subgraph ShareSDK [backend-share / rabbitmq-client & data-client]
        SDK_MQ[rabbitmq-client AMQP 驱动]
        SDK_HTTP[data-client HTTP API Client]
    end

    subgraph DataPlatform [backend-data :8010 数据中台]
        DATA_BOT[Bot 元数据服务]
        DATA_OSS[Storage Service 对象存储服务]
        DATA_ID[Identity & Data 服务]
    end

    subgraph Infrastructure [物理基础设施]
        MQ_IN[(RabbitMQ: inbound_queue)]
        MQ_OUT[(RabbitMQ: outbound_queue)]
        PG_DB[(PostgreSQL 数据库)]
        MINIO_OSS[(MinIO 对象存储)]
    end

    %% 流向 A: 上行消息
    FS_PLATFORM -->|1. HTTP POST Webhook 事件| GW_WEBHOOK
    GW_WEBHOOK -->|2. 解密/验签| GW_NORM
    GW_NORM -->|3. 归一化 InboundMessage| SDK_MQ
    SDK_MQ -->|4. 原生 AMQP 协议直连发布| MQ_IN
    DATA_MB -->|6. 记录消息日志| PG_DB

    %% 流向 B: 下行消息
    GW_RELAY -->|7. GET /claim 长轮询请求租约| SDK_HTTP
    SDK_HTTP -->|8. 代理请求租约| DATA_MB
    DATA_MB <-->|9. 提取出站消息并锁定租约| REDIS_LEASE
    DATA_MB <-->|10. 从出站队列 Pop| MQ_OUT
    DATA_MB -->>|11. 返回 Message Payload + Receipt ID| SDK_HTTP
    SDK_HTTP -->>|12. 交付消息| GW_RELAY
    GW_RELAY -->|13. 调用平台 API 发送消息| FS_PLATFORM
    GW_RELAY -->|14. ACK / NACK 确认| SDK_HTTP
    SDK_HTTP -->|15. 更新租约与删除 MQ 消息| DATA_MB

    %% 流向 C: 机器凭证
    DATA_BOT <-->|读取密文凭证| PG_DB
    GW_MEM <-->|GET /api/v1/bot/credentials| SDK_HTTP
    SDK_HTTP <--> DATA_BOT

    %% 流向 D: 媒体文件
    GW_STORAGE -->|透传二进制流| SDK_HTTP
    SDK_HTTP -->|POST /api/v1/storage/upload| DATA_OSS
    DATA_OSS -->|写入文件| MINIO_OSS
```

---

## 3. 五大核心数据流向详解 (From Where to Where)

### 3.1 流向一：IM 上行消息流 (Inbound Data Pipeline)
*即：终端用户在飞书/企微发送消息给机器人，消息如何进入系统。*

- **数据从哪里来**：外部 IM 平台（飞书/企业微信服务器）推送到网关公网/内网地址。
- **数据流转路径**：
  1. `IM 平台` $\xrightarrow{\text{HTTP POST Event}}$ `backend-gateway` (`/api/v1/feishu/webhook` 或 `/api/v1/wechat/webhook`)。
  2. `backend-gateway` 校验签名（Signature Verification）、解密 JSON Payload。
  3. 网关 `Hub` 将飞书/企微特有的 JSON 格式提取归一化为标准的 `InboundMessage` 数据结构（包含 `message_id`, `sender_id`, `content_type`, `content` 等）。
  4. 网关调用 `backend-share/data-client` 的 `publish_inbound_message()` 方法。
  5. `data-client` 附带内部安全头 `X-Service-API-Key` 与链路追踪 `X-Trace-Id`，请求 `backend-data` 的 `POST /api/v1/infrastructure/message-broker/inbound` 接口。
  6. `backend-data` 接收数据，将消息投递至 `RabbitMQ` 的 `inbound_queue` 交换机/队列，并在 `PostgreSQL` 中持久化记录该条消息历史状态。
- **数据最终去向**：`RabbitMQ (inbound_queue)` 与 `PostgreSQL (message_logs)`，等待后端的 Agent 执行引擎或业务逻辑订阅处理。

---

### 3.2 流向二：IM 下行消息推送流 (Outbound Data Pipeline)
*即：系统/Agent 处理完业务后需要回复文本/卡片给 IM 终端用户。*

- **数据从哪里来**：后台 Agent / 业务系统将需推送到 IM 的回复生成，写入 `backend-data` 托管的 `RabbitMQ` 下行队列 (`outbound_queue`)。
- **数据流转路径**：
  1. `backend-gateway` 启动后台长轮询任务 `_outbound_relay_loop`。
  2. 轮询任务通过 `data-client` 向 `backend-data` 的 `GET /api/v1/infrastructure/message-broker/outbound/claim` 发起带超时（默认 20s）的 HTTP 租约请求。
  3. `backend-data` 从 RabbitMQ `outbound_queue` 弹出一条待发送消息，并在 `Redis` 中建立一个带超时机制的**租约锁 (Lease)**，生成唯一的 `receipt_id`。
  4. `backend-data` 将消息 Payload 和 `receipt_id` 返回给 `backend-gateway`。
  5. `backend-gateway` 的 `Hub` 根据消息中的 `bot_id` 与 `platform_type` 选择对应的飞书/企微客户端 SDK，调用平台 API 发送给终端用户。
  6. **反馈确认回路**：
     - 若发送**成功**：网关调用 `data-client.acknowledge(receipt_id)` $\to$ `backend-data` $\to$ 在 Redis 删除租约锁并从 RabbitMQ 物理确认 (ACK)。
     - 若发送**失败**：网关调用 `data-client.reject(receipt_id)` $\to$ `backend-data` $\to$ 在 Redis 释放租约锁以便重试或送入死信队列 (NACK)。
- **数据最终去向**：飞书/企业微信终端用户的聊天窗口。

---

### 3.3 流向三：机器人凭证与配置流 (Bot Config & Lifetime Pipeline)
*即：机器人的 AppID、AppSecret、Webhook Key 等敏感凭证从哪里加载。*

- **数据从哪里来**：管理员在前端配置并在 `PostgreSQL` 的 **`bots`** 表中加密存储。
  - **核心表名**：**`bots`** 表（底层 ORM 模型定义于 `backend-data/backend/app/models/bot.py` 的 `Bot` 类）。
  - **关联扩展表**：`bot_call_permissions`（Bot 跨部门/跨层级额外授权表）、`user_bots`（用户与 Bot 权限关联表）。

#### 📌 `bots` 数据表物理结构与 DDL 定义

```sql
CREATE TABLE IF NOT EXISTS bots (
    id BIGSERIAL PRIMARY KEY,                          -- 物理主键 ID
    bot_id VARCHAR(64) NOT NULL,                        -- 业务唯一标识 (Gateway 识别用)
    name VARCHAR(128) NOT NULL,                         -- 机器人显示名称
    platform VARCHAR(32) NOT NULL,                      -- 接入平台类型 (feishu / wechat)
    app_id VARCHAR(128),                                -- 平台分配的 AppID / Key
    app_secret TEXT,                                    -- 平台应用密钥 (带 enc:v1: 前缀加密)
    parent_bot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL, -- 父级 Bot ID (支持树形结构)
    mode VARCHAR(16) DEFAULT 'test',                    -- 运行模式 (test / prod)
    status SMALLINT DEFAULT 1,                          -- 状态 (1: 启用/活跃, 0: 停用)
    created_by BIGINT,                                  -- 创建人用户 ID
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),      -- 创建时间
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),      -- 更新时间
    deleted_at TIMESTAMPTZ                              -- 软删除标记 (NULL 表示未删除)
);

-- 部分唯一索引：仅对未软删除行约束 bot_id 唯一，允许软删除后重建同名 bot_id
CREATE UNIQUE INDEX IF NOT EXISTS uq_bots_bot_id_active 
ON bots (bot_id) 
WHERE deleted_at IS NULL;
```

#### 📌 `bots` 字段全属性对照表

| 字段名称 | 物理数据类型 | 是否必填 | 默认值 | 详细说明 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `BIGINT` / `BIGSERIAL` | **是** | 自增 | 表自增主键 |
| `bot_id` | `VARCHAR(64)` | **是** | - | 网关与其交互的业务逻辑唯一标识 (如 `feishu-robot-main`) |
| `name` | `VARCHAR(128)` | **是** | - | 机器人展示名称 (如 `HR 审批助手`) |
| `platform` | `VARCHAR(32)` | **是** | - | 平台协议分类 (例如 `feishu`, `wechat`) |
| `app_id` | `VARCHAR(128)` | 否 | `NULL` | 飞书/企微开放平台分配的 `App ID` |
| `app_secret` | `TEXT` | 否 | `NULL` | 平台应用 Secret（**密文存储**，前缀 `enc:v1:`） |
| `parent_bot_id` | `BIGINT` | 否 | `NULL` | 外键指向 `bots.id`，表达 Bot 间的组织继承与树形归属关系 |
| `mode` | `VARCHAR(16)` | 否 | `'test'` | 环境隔离模式 (`test` 测试环境, `prod` 生产环境) |
| `status` | `SMALLINT` | 否 | `1` | 运行状态 (`1`: 启用/活跃状态，`0`: 停用) |
| `created_by` | `BIGINT` | 否 | `NULL` | 创建该机器人的用户主键 ID |
| `created_at` | `TIMESTAMPTZ` | **是** | `NOW()` | 记录创建时间戳 (带时区) |
| `updated_at` | `TIMESTAMPTZ` | **是** | `NOW()` | 记录修改更新时间戳 (带时区) |
| `deleted_at` | `TIMESTAMPTZ` | 否 | `NULL` | 软删除标记 (非空时表示该条记录已删除) |

- **数据流转与解密路径**：
  1. 管理员在前端修改 Bot 配置 $\to$ 请求 `backend-auth` $\to$ 通过 `data-client` 持久化到 `backend-data` 的 `PostgreSQL` **`bots`** 表中（`app_secret` 经过 `secret_crypto.encrypt` 加密后落库）。
  2. `backend-gateway` 启动时（或接收到热重载指令时），调用 `BotManager.load_from_database()`。
  3. 网关通过 `data-client` 请求 `backend-data` 专门面向内部服务暴露的 `GET /api/v1/bots/active` 接口。
  4. `backend-data` 的 `BotService` 从 **`bots`** 表过滤查询 `deleted_at IS NULL AND status = 1` 的记录，并调用 `secret_crypto.decrypt()` 将 `app_secret` 解密还原为明文。
  5. `backend-gateway` 接收到 JSON 列表，将凭证加载至本地内存 `BotManager` 中，初始化飞书 SDK (`FeishuBot`) 或企微 SDK (`WeChatBot`) 实例，注册事件监听器。
- **数据最终去向**：`backend-gateway` 的内存变量（进程生命周期）。

---

### 3.4 流向四：多媒体文件与对象存储流 (Media & Storage Pipeline)
*即：消息中的图片、文件、语音等二进制数据如何传输与存储。*

- **数据从哪里来**：IM 平台接收到的图片/文件字节流，或前端上传的素材文件。
- **数据流转路径**：
  1. 网关 `GatewayStorageClient` 收到文件字节流（`BytesIO`）。
  2. 网关做本地尺寸与安全检查后，不自行连接存储，而是通过 `data-client.upload_object()` 建立 `multipart/form-data` 请求发给 `backend-data` 的 `/api/v1/storage/upload`。
  3. `backend-data` 的 `StorageService` 负责连接 `MinIO` 对象存储，创建 Bucket 并写入 Object。
  4. `MinIO` 写入成功后返回对象 Key，`backend-data` 生成带有防盗链/签名的可访问 `file_url`。
  5. `file_url` 层层返回给 `backend-gateway` 或前端。
- **数据最终去向**：`MinIO` 对象存储服务器，外部通过受控的 `file_url` 进行访问。

---

### 3.5 流向五：分布式链路追踪与日志流 (Observability Data Pipeline)
*即：一次请求从前端到网关再到后端，日志与 Trace 如何串联。*

- **数据从哪里来**：客户端/前端发起的原始 HTTP 请求或 IM Webhook 触发。
- **数据流转路径**：
  1. 请求进入系统时，若无 `X-Trace-Id`，网关/前端自动生成标准 `UUID4` 作为 `Trace ID`。
  2. `backend-gateway` 使用 `TraceMiddleware` 将 `TraceContext(trace_id, span_id)` 绑定到当前 Python 协程上下文（`ContextVar`）。
  3. 网关通过 `data-client` 向 `backend-data` 传输消息或发起 HTTP 请求时，自动在 Header 或 MQ 载荷中带上 `X-Trace-Id` 与 `X-Span-Id`。
  4. `backend-data` 接收后继承该 Trace 上下文，并将日志/操作指标写入 `PostgreSQL` / `Redis` 统一的 Observability 表中。
- **数据最终去向**：`backend-data` 的日志与链路分析引擎。

---

## 4. 总结与流向对比表

| 数据类型 | 数据源头 (From) | 中转站 (Through) | 终点站 (To) | 传输协议 / 载体 |
| :--- | :--- | :--- | :--- | :--- |
| **IM 上行消息** | 飞书/企微 Webhook | `backend-gateway` 归一化 | `RabbitMQ` (inbound_queue) + `PostgreSQL` | HTTP POST $\to$ REST API $\to$ AMQP |
| **IM 下行消息** | 后端 Agent / 业务逻辑 | `RabbitMQ` $\to$ `backend-data` $\to$ `backend-gateway` | 飞书/企微 终生用户窗口 | REST Claim 租约 $\to$ IM OpenAPI |
| **Bot 配置凭证** | PostgreSQL 数据库 | `backend-data` 解密 $\to$ `data-client` | `backend-gateway` 内存管理器 | HTTP REST (API Key 加密传输) |
| **富媒体文件** | 飞书/企微/前端 | `GatewayStorageClient` 流式透传 | `MinIO` 对象存储 | HTTP Multipart $\to$ MinIO S3 API |
| **链路 Trace ID** | 前端 / 网关生成 | 请求 Header / MQ Payload 上下文 | `backend-data` 追踪中心 | HTTP Header (`X-Trace-Id`) |
