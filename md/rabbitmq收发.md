# RabbitMQ 消息收发架构与代码示例指南

## 1. 概述与架构定位

在数字员工系统中，消息收发已全面重构升级为**原生 AMQP 协议直连**模式。通过共享模块 `backend-share/rabbitmq-client`（基于高性能 Python 异步驱动 `aio-pika` 封装），网关 (`backend-gateway`) 与后端的各微服务可以直接与 RabbitMQ 建立高性能异步连接，去除了原先中间 HTTP REST 代理层的延迟与吞吐瓶颈。

```mermaid
graph LR
    subgraph Gateway [backend-gateway]
        GW_PUB[发布上行消息 publish_inbound]
        GW_SUB[监听下行消息 start_outbound_consumer]
    end

    subgraph ShareSDK [backend-share/rabbitmq-client]
        CLIENT[RabbitMQClient (aio-pika)]
    end

    subgraph RabbitMQ [RabbitMQ Broker]
        EXCHANGE[Exchange: digital_employee.events]
        IN_Q[(Queue: inbound_queue)]
        OUT_Q[(Queue: outbound_queue)]
    end

    subgraph AgentServices [backend-agent / backend-data]
        AGENT_SUB[监听上行消息 consume_inbound]
        AGENT_PUB[发布回复消息 publish_outbound]
    end

    GW_PUB -->|1. AMQP 直连| EXCHANGE
    EXCHANGE -->|2. routing_key: inbound.message| IN_Q
    IN_Q -->|3. 监听消费| AGENT_SUB

    AGENT_PUB -->|4. AMQP 直连| EXCHANGE
    EXCHANGE -->|5. routing_key: outbound.message| OUT_Q
    OUT_Q -->|6. 监听消费并推送平台| GW_SUB
```

---

## 2. AMQP 拓扑与路由规则

| 元素类型 | 名称 | 类型 / 属性 | 说明 |
| :--- | :--- | :--- | :--- |
| **Exchange** | `digital_employee.events` | `Topic` (Durable) | 系统全局事件交换机 |
| **Inbound Queue** | `inbound_queue` | Durable | 上行（终端 -> 系统）入站消息队列，Routing Key: `inbound.message` |
| **Outbound Queue** | `outbound_queue` | Durable | 下行（系统 -> 终端）出站消息队列，Routing Key: `outbound.message` |

---

## 3. 配置加载与 Nacos 配置中心管理

系统统一采用 **Nacos 配置中心** 管理服务与连接凭证。在微服务启动阶段通过 `nacos-client`（调用 `NacosClient.from_env_optional().load_to_environ()`）从 Nacos 动态拉取最新的配置，并自动注入到环境变量供 `rabbitmq-client` 实时感知的。

### Nacos 配置项示例 (Data ID: `digital-employee-gateway.yaml` / `application.yaml`)

```yaml
# RabbitMQ AMQP 统一连接配置
RABBITMQ_URL: "amqp://guest:guest@127.0.0.1:5672/"
```

### 服务启动并自动注入 Nacos 配置流程

```python
import os
from nacos_client import NacosClient
from rabbitmq_client import get_rabbitmq_client

# 1. 优先从 Nacos 配置中心动态拉取最新配置并写入 os.environ
nacos_client = NacosClient.from_env_optional()
if nacos_client is not None:
    nacos_client.load_to_environ()

# 2. 初始化 RabbitMQ 客户端（将自动使用 Nacos 注入的 RABBITMQ_URL 环境变量）
mq_client = get_rabbitmq_client()
```

---

## 4. 核心收发代码示例

### 示例 1：网关上行消息发布 (Publish Inbound Message)
网关接收到飞书/企微的 Webhook IM 消息后，归一化消息并直接写入 `inbound_queue`：

```python
import asyncio
from rabbitmq_client import get_rabbitmq_client

async def handle_feishu_webhook(bot_id: str, raw_payload: str):
    # 1. 获取全局共享的 RabbitMQ 客户端
    mq_client = get_rabbitmq_client()
    
    # 2. 建立/确认拓扑结构
    await mq_client.ensure_topology()
    
    # 3. 将上行消息发布入队列（自动绑定当前分布式 TraceContext 链路追踪）
    result = await mq_client.publish_inbound(
        platform="feishu",
        bot_id=bot_id,
        payload=raw_payload,
    )
    print(f"上行消息发布成功: {result}")

# 运行示例
# asyncio.run(handle_feishu_webhook("bot_123", '{"text": "你好"}'))
```

---

### 示例 2：后端 Agent 监听上行消息 (Consume Inbound Message)
业务微服务（如 `backend-agent` 或 `backend-data`）持续监听 `inbound_queue`，接收用户输入并触发大模型或业务处理：

```python
import asyncio
from rabbitmq_client import get_rabbitmq_client

async def process_inbound_message(payload: str) -> bool:
    """上行消息处理回调逻辑。
    
    Returns:
        bool: 返回 True 自动向 RabbitMQ 发送 ACK；返回 False 表示处理失败发送 NACK 归还队列重试。
    """
    try:
        print(f"[Agent] 收到用户上行消息: {payload}")
        # 执行业务逻辑/LLM 推理...
        return True  # 确认处理成功
    except Exception as exc:
        print(f"[Agent] 处理失败: {exc}")
        return False  # 触发 NACK 重试

async def main():
    mq_client = get_rabbitmq_client()
    await mq_client.ensure_topology()
    
    print("[Agent] 启动入站消息监听中...")
    # 使用 aio-pika 的异步迭代器持续监听 inbound_queue
    assert mq_client._inbound_queue is not None
    async with mq_client._inbound_queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process(requeue=True):
                raw_body = message.body.decode("utf-8")
                success = await process_inbound_message(raw_body)
                if success:
                    await message.ack()
                else:
                    await message.nack(requeue=True)

if __name__ == "__main__":
    # asyncio.run(main())
    pass
```

---

### 示例 3：后端 Agent 发布下行回复消息 (Publish Outbound Message)
Agent 大模型生成回复后，将回复消息写入 `outbound_queue`：

```python
import asyncio
import json
import aio_pika
from rabbitmq_client import get_rabbitmq_client, EXCHANGE_NAME, OUTBOUND_ROUTING_KEY

async def publish_outbound_reply(bot_id: str, platform: str, reply_text: str):
    mq_client = get_rabbitmq_client()
    await mq_client.ensure_topology()
    
    assert mq_client._exchange is not None
    
    # 构造标准下行回复 Payload
    outbound_payload = {
        "bot_id": bot_id,
        "platform": platform,
        "content": reply_text,
    }
    
    amqp_message = aio_pika.Message(
        body=json.dumps(outbound_payload, ensure_ascii=False).encode("utf-8"),
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        content_type="application/json",
    )
    
    # 直接发布到 Topic Exchange，路由键为 outbound.message
    await mq_client._exchange.publish(amqp_message, routing_key=OUTBOUND_ROUTING_KEY)
    print(f"[Agent] 下行回复已成功写入 outbound_queue")

# 运行示例
# asyncio.run(publish_outbound_reply("bot_123", "feishu", "这是机器人的自动回复"))
```

---

### 示例 4：网关消费下行消息推送到开放平台 (Consume Outbound Message)
网关异步监听出站队列，将消息推送到飞书/企微开放平台 API，并根据推送结果返回 ACK/NACK：

```python
import asyncio
from rabbitmq_client import get_rabbitmq_client

async def send_to_open_platform(payload: str) -> bool:
    """网关推送给第三方开放平台的真正发信回调。
    
    Returns:
        bool: 返回 True 自动 ACK，返回 False 自动 NACK 重新入队。
    """
    print(f"[Gateway] 收到下行消息，准备推送到第三方开放平台: {payload}")
    # 调用飞书/企微 SDK 发送 HTTP 消息...
    push_success = True
    return push_success

async def start_gateway_outbound_listener():
    mq_client = get_rabbitmq_client()
    
    # 启动异步 AMQP 监听消费者（SDK 内部自动处理异常捕获、TraceContext 还原与 ACK/NACK）
    await mq_client.start_outbound_consumer(send_to_open_platform)

if __name__ == "__main__":
    # asyncio.run(start_gateway_outbound_listener())
    pass
```

---

## 5. backend-gateway 收发消息 JSON 现场报文示例 (StandardMessage)

网关与后端微服务之间统一采用归一化的 `StandardMessage` 消息协议模型进行交互：

### A. backend-gateway 发送的消息 (上行入站消息 / Inbound)

网关收到飞书/企微 Webhook 后归一化，写入 `inbound_queue` 发给后端 Agent：

#### 例子 1：单聊文本消息上行
```json
{
  "message_id": "om_5a8799a4c3e8784d12345678",
  "platform": "feishu",
  "bot_id": "bot_hr_assistant_01",
  "chat_type": "p2p",
  "session_id": "ou_382947192837192",
  "sender_id": "ou_382947192837192",
  "content": [
    {
      "msg_type": "text",
      "text": "帮我查一下这个月的年假剩余天数"
    }
  ]
}
```

#### 例子 2：群聊多模态（文本 + 图片附件）上行
```json
{
  "message_id": "om_7c992019ab123456",
  "platform": "wechat",
  "bot_id": "bot_finance_01",
  "chat_type": "group",
  "session_id": "oc_group_88392019",
  "sender_id": "user_102",
  "content": [
    {
      "msg_type": "text",
      "text": "请审批这张发票报销"
    },
    {
      "msg_type": "image",
      "file_url": "http://127.0.0.1:8010/api/v1/storage/raw/invoice_2026.png",
      "file_name": "invoice_2026.png"
    }
  ]
}
```

---

### B. backend-gateway 接收的消息 (下行出站消息 / Outbound)

后端 Agent 大模型处理完生成回复，写入 `outbound_queue`，网关消费并推送到飞书/企微终端平台：

#### 例子 1：Agent 文本回复下行
```json
{
  "message_id": "om_5a8799a4c3e8784d12345678",
  "platform": "feishu",
  "bot_id": "bot_hr_assistant_01",
  "chat_type": "p2p",
  "session_id": "ou_382947192837192",
  "sender_id": "bot_hr_assistant_01",
  "content": [
    {
      "msg_type": "text",
      "text": "您好！查询到您本年度尚有 5 天带薪年假未休。如有请假需求，可在 HR 门户提交申请。"
    }
  ]
}
```

#### 例子 2：Agent 交互卡片回复下行
```json
{
  "message_id": "om_992817204918234",
  "platform": "feishu",
  "bot_id": "bot_it_support_01",
  "chat_type": "p2p",
  "session_id": "ou_7712391023910",
  "sender_id": "bot_it_support_01",
  "content": [
    {
      "msg_type": "card",
      "card_data": {
        "title": "IT 运维工单提交成功",
        "description": "已成功为您创建故障报修工单 #20260801",
        "status": "processing",
        "actions": [
          { "label": "查看工单进度", "value": "check_status" }
        ]
      }
    }
  ]
}
```

---

## 6. 分布式链路追踪 (TraceContext) 集成规范

`backend-share/rabbitmq-client` 已内置自动关联 `observability` 的链路追踪能力：

1. **发布时自动注入**：`publish_inbound` 会自动提取当前线程/协程的 `TraceContext`，并将 `X-Trace-Id` 与 `X-Span-Id` 写入 AMQP 消息 Header 和 Payload。
2. **消费时自动还原**：`start_outbound_consumer` 收到消息后，会自动从 Header 中解析 `TraceContext` 并绑定到当前消费协程上下文，确保应用全链路日志可追踪查询。
