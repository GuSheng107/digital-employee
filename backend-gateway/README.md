# Backend Gateway (BOT 消息侧服务器)

本项目为智能机器人系统的流量网关与协议转换层。系统经历了架构演进，目前三期工程已正式接入 RabbitMQ，并实现了单网关节点下的**全协程纯异步双模路由调度**机制。

## 核心设计与技术选型

1. **全异步并发模型**：网关核心流转层全面采用 `async/await` 协程架构，下线了原有的同步线程池，以提供更卓越的并发调度能力。
2. **双模式路由机制（Test/Prod）**：
   * **Test 模式**：消息不进入 MQ，直接通过 `asyncio.create_task` 挂载至后台，由 `_mock_agent_process` 协程进行非阻塞本地模拟。
   * **Prod 模式**：网关作为生产者，携带路由键（如 `msg.inbound.feishu.bot_001`）安全地将消息投递至 `bot.topic.exchange` 交换机。
3. **MQ 拓扑自治**：基于 `aio-pika`，网关在启动时自动声明交换机、队列并完成绑定关系，无需手动维护 RabbitMQ 拓扑。
4. **连接保活与保全**：支持心跳检测、网络抖动下的指数退避重连机制、及 Watchdog 定期保活。在同步 SDK 线程与异步中枢的边界采用 `asyncio.run_coroutine_threadsafe` + `Future.result(timeout=3)` 显式捕获发布异常，杜绝消息静默丢失。

## 运行环境

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) 现代依赖管理工具
- **RabbitMQ 3.x+**（本地开发联调需启动 RabbitMQ 服务）

## 快速上手

### 1. 安装依赖

使用 `uv` 自动创建虚拟环境并同步依赖：
```bash
python -m uv sync
```

### 2. 配置文件说明

本地开发调试需要从模板复制配置文件和环境变量：
```bash
cp config/bot.template.json config/bot.json
cp .env.example .env
```
* 在 `config/bot.json` 中填入你的飞书机器人凭证，并可配置 `"mode": "test"` 或 `"prod"`。
* 在 `.env` 中填入正确的 `RABBITMQ_URL` 连接地址。

### 3. 运行网关

```bash
.venv\Scripts\python -m src.main
```

运行后，管理端控制台会在 `http://127.0.0.1:8000` 启动，并在启动时完成 RabbitMQ 拓扑的声明与自动绑定。

## RabbitMQ 拓扑设计

| 组件类别 | 实际组件名称 (Name) | 绑定路由键 (Binding Key) | 职责说明 |
| --- | --- | --- | --- |
| **交换机 (Exchange)** | `bot.topic.exchange` | *(不适用)* | 核心 Topic 交换机。 |
| **入站队列 (Queue)** | `q_inbound_to_agent` | `msg.inbound.#` | 存储待后端 Agent 服务消费的指令。 |
| **出站队列 (Queue)** | `q_outbound_to_gateway` | `msg.outbound.#` | 监听并接收由 Agent 发回、待网关分发回客户端的回复。 |

## Admin HTTP API 接口说明

- **健康状态与活跃 Bot 查询**
  - 请求：`GET /api/v1/health`
- **获取所有运行 Bot 详情**
  - 请求：`GET /api/v1/admin/bots`
- **动态更新/注入 Bot 凭证**
  - 请求：`POST /api/v1/admin/bots`
  - Body:
    ```json
    {
      "bot_id": "test_bot",
      "platform": "feishu",
      "mode": "test",  // 新增：test 或 prod
      "app_id": "cli_xxx",
      "app_secret": "sec_xxx"
    }
    ```
- **删除 Bot 实例**
  - 请求：`DELETE /api/v1/admin/bots/{bot_id}`
