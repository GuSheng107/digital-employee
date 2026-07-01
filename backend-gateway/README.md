# Backend Gateway (BOT 消息侧服务器) - 一期

本项目为智能机器人系统的流量网关与协议转换层，一期实现了飞书长连接（WebSocket）的多实例并发接收与回复。

## 核心设计与技术选型

1. **并发模型**：主线程采用 FastAPI（asyncio）提供管理 API；各 Bot 实例在独立系统子线程（`threading`）中维护阻塞的长连接。
2. **连接保活**：支持心跳检测、网络抖动下的指数退避重连机制、及 Watchdog 定期保活守护进程。
3. **安全隔离**：敏感凭证不入库、不硬编码，通过 `.env` 或 `bot.json`（已加入 `.gitignore`）管理。

## 运行环境

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) 现代依赖管理工具

## 快速上手

### 1. 安装依赖

使用 `uv` 自动创建虚拟环境并同步依赖：
```bash
python -m uv sync
```

### 2. 配置文件说明

本地开发调试需要从模板复制配置文件：
```bash
cp config/bot.template.json config/bot.json
```
在 `config/bot.json` 中填入你的飞书 `app_id` 和 `app_secret`。

### 3. 运行网关

```bash
.venv\Scripts\python -m src.main
```

运行后，管理端控制台会在 `http://127.0.0.1:8000` 启动。

### 4. Admin HTTP API 接口说明

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
      "app_id": "cli_xxx",
      "app_secret": "sec_xxx"
    }
    ```
- **删除 Bot 实例**
  - 请求：`DELETE /api/v1/admin/bots/{bot_id}`
