# Digital Employee - 数字员工

多平台 AI 数字员工系统，支持企微、飞书、钉钉、微信公众号、Telegram 等多平台接入，提供智能对话、任务编排、多模态交互等能力。

## 项目架构

```
digital-employee/
├── backend-agent/      # Python/FastAPI - 数字员工核心（Agent 运行时、技能系统、记忆管理）
├── backend-gateway/    # Go - 多平台消息网关（参考用，后续将替换为 Python 自研）
├── frontend/           # Vue3 + Element Plus - 管理控制台
├── scripts/            # 开发启动脚本
├── docker-compose.yml  # 一键启动
└── Makefile            # 统一构建入口
```

## 核心模块

- **Agent Runtime**: 支持 single/routing/pipeline/fan_out/review 多种编排模式
- **Platform Gateway**: 统一平台接口，抽象 PlatformBase 基类（WEBHOOK/WEBSOCKET/LONG_POLL/STREAM）
- **Skills System**: 可扩展技能框架，支持 MCP 协议
- **Memory System**: 多层记忆管理（短期/长期/文档）
- **Multi-modal**: 支持图片、文件、音频收发

## 快速开始

### 环境要求

- Python 3.10+
- Go 1.21+（仅 gateway）
- Node.js 18+
- Redis 7+

### 安装

```bash
# 安装所有依赖
make install

# 或分别安装
cd backend-agent && pip install -e ".[dev]"
cd frontend && npm install
```

### 开发

```bash
# 一键启动所有服务
make dev

# 或分别启动
make dev-agent     # Backend Agent :8000
make dev-gateway   # Backend Gateway :8080
make dev-frontend  # Frontend :3000
```

Windows 用户可使用：
```cmd
scripts\dev.bat
```

### Docker

```bash
docker compose up --build
```

## 平台支持

| 平台 | 连接方式 | 状态 |
|------|---------|------|
| 企业微信 | WebSocket 长连接 | ✅ 已实现 |
| 飞书 | WebSocket | 🔲 规划中 |
| 钉钉 | Stream 长连接 | 🔲 规划中 |
| 微信公众号 | HTTP 长轮询 | 🔲 规划中 |
| Telegram | Webhook | 🔲 规划中 |

## 技术栈

- **Backend Agent**: Python 3.10, FastAPI, SQLAlchemy, LangChain
- **Backend Gateway**: Go (参考), 计划迁移至 Python 自研
- **Frontend**: Vue 3, Element Plus, Vite
- **Storage**: SQLite / PostgreSQL, Redis

## 贡献

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解协作流程。

## 许可证

[MIT License](LICENSE)

## 致谢

- [wecom-bot-agent](https://github.com/GuSheng107/wecom-bot-agent) - 企微 AI 机器人核心
- [cc-connect](https://github.com/agent-api/cc-connect) - 多平台消息网关参考
