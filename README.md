# Digital Employee - 数字员工

多平台 AI 数字员工系统，支持企微、飞书、钉钉、微信公众号、Telegram 等多平台接入，提供智能对话、任务编排、多模态交互等能力。

## 贡献者

- [@GuSheng107](https://github.com/GuSheng107) - 项目发起人 & 主要维护者

## 项目架构

```
digital-employee/
├── backend-agent/      # Python/FastAPI - 数字员工核心（Agent 运行时、技能系统、记忆管理）
├── backend-gateway/    # Go - 多平台消息网关（参考用，后续将替换为 Python 自研）
├── frontend/           # Vue3 + Element Plus - 管理控制台（静态构建）
├── scripts/            # 启动脚本
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
- Node.js 18+（仅构建前端时需要）

### 安装

```bash
# 安装 backend-agent 依赖
cd backend-agent
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

或使用 Makefile：

```bash
make install-agent
```

### 启动

```bash
# 使用启动脚本（推荐）
scripts\start-web.cmd        # Windows
./scripts/start-web.sh       # macOS / Linux

# 或手动启动
cd backend-agent
.venv\Scripts\activate       # Windows
source .venv/bin/activate    # macOS / Linux
python main.py
```

启动后访问 http://localhost:8765

### 构建前端

前端为静态页面，由 backend-agent 直接托管，无需单独启动：

```bash
make build-frontend
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
- **Frontend**: Vue 3, Element Plus, Vite（静态构建）
- **Storage**: SQLite / PostgreSQL, Redis

## 贡献

我们欢迎所有形式的贡献 — 提交 bug 报告、提出功能建议、改进文档或贡献代码。

📖 请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解完整的协作流程。

> **注意**：`master` 分支已受保护，所有改动必须通过 Pull Request 流程合入。
> 当前要求：必须通过 PR、推送新 commit 后旧 review 自动失效、管理员不可绕过。

## 许可证

[MIT License](LICENSE)

## 致谢

- [wecom-bot-agent](https://github.com/GuSheng107/wecom-bot-agent) - 企微 AI 机器人核心
- [cc-connect](https://github.com/agent-api/cc-connect) - 多平台消息网关参考
