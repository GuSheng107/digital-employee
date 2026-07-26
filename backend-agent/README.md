# WeCom Bot Agent

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-green.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/Vue-3.5+-brightgreen.svg" alt="Vue">
  <img src="https://img.shields.io/badge/LangChain-Agent-orange.svg" alt="LangChain">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

<p align="center">
  <strong>让人回归创造</strong> · 让 AI 处理繁琐，让人类专注于创新
</p>

***

<p align="center">
  <i>企业微信 AI 机器人本地管控台 — 基于 FastAPI + Vue 3 + SQLite + LangChain Agent</i>
</p>

<p align="center">
  <a href="#-核心特性">核心特性</a>
  ·
  <a href="#-快速开始">快速开始</a>
  ·
  <a href="#-架构设计">架构设计</a>
  ·
  <a href="#-智能记忆系统">记忆系统</a>
  ·
  <a href="#-系统级-skills">Skills</a>
  ·
  <a href="#-配置指南">配置指南</a>
  ·
  <a href="#-api-文档">API 文档</a>
  ·
  <a href="./ARCHITECTURE.md">架构图</a>
</p>

<p align="center">
  <a href="http://192.168.7.102:8765/" target="_blank">🖥️ 在线体验</a>
  ·
  <a href="https://git.dianplus.cn/shanfan/wecom-bot-agent" target="_blank">📦 源码仓库</a>
</p>

> 💡 <b>在线体验</b>：局域网地址 <a href="http://192.168.7.102:8765/">http://192.168.7.102:8765/</a>，账号 <code>test</code> / 密码 <code>test123</code>

***

## 🌟 为什么选择 WeCom Bot Agent？

> **在信息爆炸的时代，你是否被繁琐的重复工作淹没？**
>
> WeCom Bot Agent 致力于将人类从机械性工作中解放出来——让 AI 处理消息、回答问题、执行任务，而你只需专注于真正重要的**创造**。

### 你能做什么

|    传统工作模式   | 使用 WeCom Bot Agent |
| :---------: | :----------------: |
| 手动回复每一条客户消息 |    AI 智能分流，自动回复    |
|  逐一查阅文档查找信息 |     对话式问答，即问即答     |
|   重复性的定时提醒  |    周期任务自动化执行    |
|   跨平台切换操作   |      一个对话搞定一切      |

***

## ✨ 核心特性

<div align="center">

| 特性            | 说明                                        |
| :------------ | :---------------------------------------- |
| 🧠 **智能记忆系统** | Agent-first + JSON 架构，智能决策由 Agent 完成，算法只做机械工作 |
| ⚡ **速查词检索** | Agent 生成 speed_lookup 速查词，评分权重最高，检索精准高效 |
| 🔄 **复盘与提升** | Agent 定期复盘记忆质量，仅收敛重复、冗余、碎片化或低价值条目，并提升收件箱条目到正确分类 |
| 🧹 **分层去重** | 按“显式记忆 > 文档记忆 > 会话记忆”预防和清理重复记忆 |
| 🏷️ **来源标注** | 回答仅标注文档显示名或管理员配置内容，会话来源不外显 |
| 📊 **使用审计** | 完整记录记忆检索流程；审查默认只读，写入需显式选择 `patch` 模式 |
| 👍 **反馈闭环** | 企业微信消息反馈（满意/不满意）自动入库，驱动记忆质量持续改进 |
| 🔒 **安全加密**   | Fernet AES128 加密存储 API Key，防止敏感信息泄露       |
| 📄 **智能解析**   | 支持 txt, md, json, csv, docx, doc 等多格式文档解析 |
| 🤖 **模型能力感知** | 自动识别模型能力，智能切换推理/对话/多模态模式                  |
| 🧩 **DashScope / Qwen 支持** | 支持 Qwen3.6/3.5/3 系列模型配置 |
| 🚀 **自由扩展**   | 上传 zip 包即可扩展 Skill，零代码增强 Agent 能力             |
| 🔧 **MCP 协议** | 动态发现 MCP 服务器工具，注入 Agent 提示词 |
| 🔮 **向量搜索探索** | 保留 sqlite-vec 扩展探索方向；核心检索默认使用 JSON + speed_lookup |
| 👥 **人工接管**   | 关键时刻人工介入，AI 与人工无缝切换                       |
| 📊 **用量追踪**   | Token 消耗透明化，成本可控                          |
| ⏰ **任务调度**    | 周期任务和一次性任务统一管理，支持详情页手动执行和完成通知       |
| 🌐 **局域网控制台** | Web 默认监听 `0.0.0.0`，同网设备可访问；后端已启用 CORS |
| 🌐 **跨平台**    | Windows / macOS / Linux 全支持               |

</div>

### 🤖 支持的模型生态

<div align="center">

| 系列           | 模型                                               |
| :----------- | :----------------------------------------------- |
| **OpenAI**   | GPT-5 全系、GPT-4.1/4o/o 系列、o1/o3/o4-mini           |
| **Claude**   | Claude Opus 4.7/4.6/4.5、Sonnet 4.6/4.5、Haiku 4.5 |
| **Gemini**   | Gemini 3.1/3/2.5/2.0 全系（含 Ultra/Pro/Flash）       |
| **Qwen**     | Qwen3.6/3.5/3 全系、Qwen-VL Plus/Max                |
| **DeepSeek** | DeepSeek-V4 Pro/Flash、Chat、Reasoner              |
| **GLM**      | GLM-5.1/5/5-Turbo、GLM-4.6v/4.7                   |
| **MiniMax**  | MiniMax M2.7/M2.5/M2.1/M2 全系                     |
| **Kimi**     | Kimi K2.6/K2.5、Moonshot V1 全系                    |

</div>

***

## 🏗️ 架构设计

> 📖 **详细的架构图与数据流**：[ARCHITECTURE.md](./ARCHITECTURE.md) — 包含 Mermaid 系统架构图、核心数据流时序图、模块职责说明和完整目录结构

```
wecom-bot-agent/
│
├── main.py                     # 🚀 入口：Web 控制台 / Bot 子进程
│
├── agent_runtime/              # 🧠 LangChain Agent 运行时
│   ├── service.py              #    Agent 核心服务（LLM 调用、流式输出、上下文压缩、输出清洗）
│   ├── models.py               #    LLM 模型构建（多提供商）
│   ├── tools.py                #    运行时工具选择（Skill/MCP/内置工具）
│   ├── stream_orchestrator.py  #    流式输出编排（取消支持、进度追踪）
│   ├── skills_integration.py   #    Skills 注入 + 记忆子进程调度
│   ├── capabilities.py         #    模型能力自动检测（文本/图像/视频/文档/工具调用）
│   ├── commands.py             #    系统指令注册与分发
│   ├── prompts.py              #    系统提示词构建
│   └── provider_fields.py      #    提供商字段定义
│
├── app/                        # ⚙️ FastAPI 后端
│   ├── web_server.py           #    Uvicorn 启动 + SPA 挂载
│   ├── config_loader.py        #    配置数据类与加载校验
│   ├── routers/                #    API 路由
│   │   └── Bot/Agent/Chat/Skill/MCP/Task/Data/Feedback/Auth
│   ├── db/                     #    SQLite 数据层（配置/消息/任务/审计等表）
│   ├── task_runtime.py         #    任务运行时（记忆/文档/审查/清理）
│   ├── task_scheduler.py       #    定时任务调度器
│   ├── bot_process_manager.py  #    Bot 子进程生命周期管理
│   ├── watchdog.py             #    Bot 进程看门狗
│   ├── context_store.py        #    对话上下文管理与压缩
│   ├── chat_store.py           #    聊天记录存储
│   ├── event_logger.py         #    统一事件日志系统
│   ├── memory_schema.py        #    记忆 JSON Schema 定义
│   ├── memory_file_manager.py  #    记忆文件 CRUD + 搜索
│   ├── memory_index_manager.py #    记忆搜索索引管理
│   ├── memory_retrieval.py     #    记忆检索
│   ├── memory_update_builder.py#    记忆更新预览
│   ├── runtime_query_index.py  #    运行时强约束指令索引
│   ├── auth.py / auth_middleware.py # 认证与中间件
│   ├── crypto_utils.py         #    API Key 加密存储
│   ├── manual_reply_queue.py   #    人工回复队列
│   ├── skills_store.py         #    Skill 扫描与上下文构建
│   ├── yaml_config.py          #    YAML 配置加载
│   ├── logger.py               #    日志配置
│   └── document_text_extractor.py # 文档解析引擎
│
├── wecom_bot/                  # 💬 企微长连接 & 消息处理
│   ├── long_connection.py      #    WebSocket 长连接主类
│   ├── handlers/               #    事件处理器
│   │   ├── context.py          #      BotContext 依赖注入容器
│   │   ├── binding_manager.py  #      管理员绑定管理
│   │   ├── media_handler.py    #      媒体消息处理
│   │   └── manual_reply_handler.py # 人工回复处理
│   ├── reply.py                #    消息上下文提取与回复构建
│   └── frame_store.py          #    帧缓存（TTL 过期）
│
├── web/                        # 🎨 Vue 3 + Element Plus 前端
│   └── src/                    #    组件/视图/样式（集中式 CSS 管理）
│
└── .skills/                    # 🎯 Skills 技能目录
    └── system/                 #    系统级 Skills（4 个）
```

***

## 🚀 快速开始

### 📋 环境要求

- **Python** 3.10+
- **Node.js** 18+（仅构建前端时需要）
- 企业微信机器人凭证（bot\_id / secret）

### 📦 安装

<details>
<summary><b>💻 Windows</b></summary>

```powershell
# 创建虚拟环境
python -m venv .venv

# 安装依赖（使用国内镜像源）
.\.venv\Scripts\python.exe -m pip install . -i https://pypi.tuna.tsinghua.edu.cn/simple

# 构建前端
cd web
npm install --registry=https://registry.npmmirror.com
npm run build
cd ..
```

</details>

<details>
<summary><b>🍎 macOS / Linux</b></summary>

```bash
# 创建虚拟环境
python3 -m venv .venv

# 安装依赖（使用国内镜像源）
.venv/bin/python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple .

# 构建前端
cd web
npm install --registry=https://registry.npmmirror.com
npm run build
cd ..
```

</details>

### 🇨🇳 国内镜像源说明

| 类型 | 镜像源 | 地址 |
|------|--------|------|
| **PyPI** | 清华大学 | `https://pypi.tuna.tsinghua.edu.cn/simple` |
| **PyPI** | 阿里云 | `https://mirrors.aliyun.com/pypi/simple/` |
| **npm** | npmmirror | `https://registry.npmmirror.com` |

### ▶️ 启动

<details>
<summary><b>💻 Windows</b></summary>

```bat
..\scripts\backend-agent\start.cmd
```

或手动启动：

```powershell
.\.venv\Scripts\python.exe .\main.py
```

</details>

<details>
<summary><b>🍎 macOS / Linux</b></summary>

```bash
bash ../scripts/backend-agent/start.sh
```

或手动启动：

```bash
.venv/bin/python main.py
```

</details>

> 🎉 启动后自动打开本机浏览器访问 `http://localhost:8765`。服务默认监听 `0.0.0.0`，同一局域网设备可访问 `http://<本机局域网IP>:8765`。启动脚本会打印 Local access 和 LAN access 两个地址。

### 🌐 局域网访问与跨域

- 默认 `--host 0.0.0.0`，控制台可被同一局域网内设备访问。
- 控制台默认启用登录页，首次启动会在数据库 schema 初始化时创建管理员账号：`admin` / `shanfan123`。登录 session 有效期为 24 小时，同一账号仅保留最近一次登录的 session；过期或被新登录挤下线后前端回到登录页，后端服务和 Bot 进程不会被停止。
- 管理员固定只有 `admin` 一个账号，可添加普通用户、编辑显示名、重置密码、删除普通用户和强制下线在线用户；普通用户可以登录使用控制台，并修改自己的密码，但不能修改账号名。密码要求同时包含英文字母和数字。
- 支持显式开启游客账号登录（在 `config.yaml` 中设置 `guest_account.enabled: true` 并配置账密）。游客仅可查看页面，所有操作类 API（如 Bot 启停、Agent 配置、技能上传、任务触发等）均会返回无权限提示。游客无单点登录限制，但 session 同样 24 小时有效；关闭或改名游客账号后，已签发游客 session 会立即失效。管理员可在用户管理中对游客账号执行"下线"操作，这会同时使所有游客会话失效。
- 若只允许本机访问，可手动指定 `--host 127.0.0.1`。
- FastAPI 后端已启用 CORS，允许前后端分离、局域网 IP、localhost 等来源访问 API。


### ⚡ 命令行参数

| 参数               | 默认值         | 说明                  |
| :--------------- | :---------- | :------------------ |
| `--host`         | `0.0.0.0` | Web 服务监听地址；默认支持局域网访问 |
| `--port`         | `8765`      | Web 服务端口            |
| `--no-browser`   | —           | 不自动打开浏览器            |
| `--run-bot`      | —           | 以 Bot 子进程模式运行       |
| `--bot-key`      | —           | Bot 配置键（多 Bot 模式）   |
| `--project-root` | `.`         | 项目根目录               |
| `--parent-pid`   | `0`         | 父进程 PID，用于子进程生命周期管理 |

***

## 📋 系统指令

在企业微信对话中，绑定用户可使用以下系统指令（以 `/` 开头）：

| 指令       | 别名          | 说明                             |
| :------- | :---------- | :----------------------------- |
| `/查看状态`  | `/status`   | 查看 Bot 运行状态、绑定用户、运行时长、活跃会话数    |
| `/查看消耗`  | `/usage`    | 查看 Token 消耗统计                  |
| `/记忆生成`  | `/memory`   | 将文本内容提炼写入长期记忆                  |
| `/关闭Bot` | `/closebot` | 关闭当前 Bot，向活跃会话发送通知后退出          |
| `/结束服务`  | `/shutdown` | 结束所有 Bot 并关闭系统服务（需 `/ok` 二次确认） |
| `/ok`    | —           | 确认执行待确认操作                      |

> 💡 **无需** **`/`** **前缀的指令**：`转人工`、`转接人工`、`人工客服`、`转客服`、`找人工` — 任何用户均可触发，转接人工客服并暂停 AI 自动回复。

> ⚠️ 系统指令仅对已绑定的 Bot 生效。绑定方法：在企业微信中向机器人发送 `connect mycom`。

***

## 🧠 智能记忆系统

项目实现了完整的 **Agent-first + JSON 智能记忆管理系统**，所有智能决策（速查词、索引、审查、修复、复盘收敛、提升）由 AI Agent 完成，算法只做机械工作（文件 I/O、锁、序列化）。当前记忆底座以 `.memory/*.json`、`.memory/timeline/*.json`、`.memory/documents/*.json` 为唯一存储模型，系统 Skill 文档和运行时代码均按 JSON schema 对齐。

> 📖 **详细文档**：[MEMORY_SYSTEM.md](./MEMORY_SYSTEM.md) — 包含完整的架构设计、API 参考和最佳实践

最新链路约束：

- 写入和审核都按 `显式记忆 > 文档记忆 > 会话记忆` 做跨源去重，避免会话记忆重复沉淀已有文档或管理员配置内容。
- 文档重复上传或分片更新使用 `mode=update` 清理同 `source_id` 旧条目后再写入。
- 记忆允许持续增长；定期会话记忆审核和文档记忆审核以自我复盘和提升为目标，只有重复、冗余、碎片化、低价值或可安全缩短的内容才会被收敛。
- Memory Pack 和回答来源只显示 `来源：文档《文档显示名》` 或 `来源：管理员配置内容`；会话记忆来源不外显。
- 数据管理页“记忆量”卡片来自 `/api/data/overview`：上传文档数、已转换消息数、`completed` 记忆更新次数和 `completed` 文档提取次数。

### 🏛️ 核心架构

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                                     Agent Runtime                                      │
├───────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                         │
│   ┌──────────────┐   ┌───────────────┐   ┌──────────────────┐                        │
│   │  memory-     │   │  memory-      │   │  memory-         │                        │
│   │  creator     │──▶│  reader       │──▶│  reviewer        │                        │
│   │  📝 写入     │   │  📖 读取       │   │  🔍 审核+复盘+提升 │                        │
│   └──────┬───────┘   └───────┬───────┘   └────────┬─────────┘                        │
│          │                   │                     │                                   │
│          ▼                   │                     │                                   │
│   ╔═══════════════════════════════════════════════════════════════════════════════╗    │
│   ║                         .memory/ 记忆目录（JSON）                              ║    │
│   ╠═══════════════════════════════════════════════════════════════════════════════╣    │
│   ║  ├── explicit.json    # 显式记忆（权重 10.0）                                ║    │
│   ║  ├── work.json        # 工作笔记（权重 8.0）                                 ║    │
│   ║  ├── profile.json     # 用户画像（权重 6.0）                                 ║    │
│   ║  ├── documents/       # 文档记忆（权重 5.0）                                 ║    │
│   ║  ├── timeline/        # 时间线记忆（权重 4.0）                                ║    │
│   ║  ├── rules.json       # 记忆规则（权重 3.0）                                 ║    │
│   ║  ├── inbox.json       # 收件箱（权重 2.0）                                   ║    │
│   ║  └── changelog.json   # 变更日志（权重 1.0）                                 ║    │
│   ╚═══════════════════════════════════════════════════════════════════════════════╝    │
│                                                                                         │
│   ┌───────────────────────────────────────────────────────────────────────────────┐   │
│   │                    app/ 记忆管理模块                                           │   │
│   │  ├── memory_schema.py              # JSON Schema 定义 + 读写工具              │   │
│   │  ├── memory_file_manager.py        # 记忆文件 CRUD + 搜索                     │   │
│   │  ├── memory_update_builder.py      # 记忆更新预览                              │   │
│   │  ├── runtime_query_index.py        # 运行时强约束指令索引（权重 12.0）          │   │
│   │  └── db/memory_usage_audit_store.py # 记忆使用审计                            │   │
│   └───────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                         │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

### 💾 记忆存储格式

每条记忆是结构化的 `MemoryItem` JSON 对象，包含 `id`、`content`、`content_type`、`speed_lookup`、`retrieval`、`source`、`priority` 等字段。Agent 在创建时一并生成速查词和检索提示，无需额外索引。

| 文件 · 优先级 | 权重 | 职责 | 来源限制 |
|:------------|:---:|:-----|:---------|
| **explicit.json** ⭐ | 10.0 | 用户明确要求记住的内容 | 仅 chat / explicit |
| **work.json** | 8.0 | 工作目标、约束、决策、架构笔记 | chat + document |
| **profile.json** | 6.0 | 稳定的长期用户偏好与沟通习惯 | 仅 chat |
| **documents/{id}.json** | 5.0 | 单个文档提炼的结构化摘要 | 仅 document |
| **timeline/YYYY-MM.json** | 4.0 | 按月聚合的聊天与文档事件 | chat + document |
| **rules.json** | 3.0 | 记忆使用规则 | 自动生成 |
| **inbox.json** | 2.0 | 不确定或冲突的记忆候选项 | 待审核 |
| **changelog.json** | 1.0 | 所有写入操作的变更日志 | 仅系统 |

### 🔄 记忆生命周期

```
┌──────────┐    ┌──────────────────┐    ┌──────────────────┐
│ 用户对话  │───▶│  memory-creator  │───▶│   .memory/       │
│ 文档输入  │    │     📝 创建       │    │   JSON 写入      │
└──────────┘    └──────────────────┘    └────────┬─────────┘
                                                │
                        ┌───────────────────────┘
                        ▼
               ┌──────────────────┐
               │   inbox.json     │  ←── 低置信度/冲突记忆
               └────────┬─────────┘
                        │
                        ▼  memory-reviewer promote
               ┌──────────────────┐
               │   提升 (promote)  │  ←── Agent 决定正确归属
               └────────┬─────────┘
                        │
             ┌──────────┼──────────┐
             ▼          ▼          ▼
    ┌──────────────┐ ┌────────┐ ┌────────┐
    │explicit.json │ │work.   │ │profile.│
    └──────┬───────┘ │json    │ │json    │
           │         └───┬────┘ └────────┘
           ▼             │
    ┌──────────────────────────┐
    │  复盘收敛 (review)        │  ←── 定期审核/必要时触发
    │  merge / shorten /       │
    │  archive / delete        │
    └──────────┬───────────────┘
               ▼
    ┌──────────────────┐
    │ timeline/         │  ←── archive 归档目标
    │ YYYY-MM.json      │
    └──────────────────┘
```

### ⚡ 速查词（speed_lookup）

Agent 在创建记忆时生成管道符分隔的速查词（如 `"聚水潭|库存|推送|erp"`），存储在 `speed_lookup` 字段中。检索评分时速查词权重最高：

| 匹配方式 | speed_lookup | retrieval | content |
|:--------:|:-----------:|:---------:|:-------:|
| 精确匹配 | **+10.0** | +5.0 | — |
| 包含匹配 | **+5.0** | +2.0 | +3.0 |

### 📊 Token 预算分配

记忆包读取采用**弹性预算扩展机制**：先以基础预算（compact/default/expanded）尝试选取，若文档记忆因预算限制被截断，且配置了扩展预算（`token_budget_expanded`），则自动扩展到更大的预算重新选取所有记忆。

| 模式 | 上限 | rules | explicit | work | profile | timeline | document | inbox |
|:-----|:----:|:------:|:--------:|:----:|:-------:|:--------:|:--------:|:-----:|
| **compact** | 1500 | 60 | 300 | 360 | 150 | 120 | 360 | 150 |
| **default** | 4000 | 120 | 720 | 960 | 320 | 400 | 1200 | 280 |
| **expanded** | 8000 | 200 | 960 | 1600 | 560 | 800 | 3200 | 680 |

**弹性预算扩展流程：**
1. 第一轮选取：使用基础预算按优先级顺序（explicit > work > profile > rules > timeline > documents > inbox > changelog）选取记忆条目
2. 检测截断：若文档记忆有匹配条目但因预算限制被截断
3. 第二轮选取：清空已选内容，使用扩展预算重新进行完整选取

相关记忆因总预算或分区预算未能进入 Memory Pack 时，reader 会把 `needs_more_memory` 置为 `true`，并在 `reason` 中说明有多少条相关记忆被预算截断；这类情况会进入审计和 reviewer 复盘，不会被误判为“没有匹配记忆”。

### 🛠️ 记忆文件管理器 (MemoryFileManager)

提供记忆文件的 CRUD 操作和搜索：

```python
from app.memory_file_manager import MemoryFileManager
from app.memory_schema import MemoryItem

mgr = MemoryFileManager(".memory")
mgr.init_memory_dir()
items = mgr.get_items("explicit")
added = mgr.add_item("explicit", MemoryItem(content="新记忆", speed_lookup="关键词1|关键词2"))
results = mgr.search_items("部署约束")
```

**特性：**
- ✅ 原子写入（tmpfile + os.replace）
- ✅ 目录锁防止并发冲突
- ✅ speed_lookup 速查词搜索
- ✅ changelog 自动记录

### 📊 记忆使用审计 (memory_usage_audit_store.py)

记录每次记忆检索的完整流程，便于分析和调试：

```python
from app.db.memory_usage_audit_store import (
    upsert_memory_usage_audit,
    list_recent_memory_usage_audits
)
```

**审计数据包含：**
- 用户查询与记忆包
- 选择/忽略的文件和章节
- Token 使用量预估
- 置信度和需要更多记忆标记
- 完整原因说明
- 最终答案和 Token 统计

### ⚠️ 硬性约束

| 规则 | 说明 |
|:-----|:-----|
| ❌ 文档 **禁止** 写入 `explicit.json` / `profile.json` | 只能从 chat 输入 |
| ❌ `changelog.json` 不可编辑 | 仅系统写入 |
| ✅ 冲突记忆放入 `inbox.json` | 待 Agent 审核提升 |

### 📚 相关文档

| 文档 | 说明 |
|:-----|:-----|
| [MEMORY_SYSTEM.md](./MEMORY_SYSTEM.md) | 完整架构设计与 API 参考 |
| `app/memory_schema.py` | JSON Schema 定义 + 读写工具 |
| `.skills/system/memory-creator/` | 记忆创建 Skill 源码 |
| `.skills/system/memory-reader/` | 记忆读取 Skill 源码 |
| `.skills/system/memory-reviewer/` | 记忆审核 Skill 源码 |
| `app/memory_file_manager.py` | 记忆文件管理模块 |
| `app/runtime_query_index.py` | 运行时强约束指令索引 |

**当前稳定性**：记忆写入、reader 召回、Memory Pack 注入和 reviewer 只读审查已形成闭环；查询扩展改为一次调用、结果复用于工具选择和记忆读取；feedback_repair_chain 提示词中 JSON 花括号已双写转义；所有 LLM 链路（查询扩展、记忆创建、审核、反馈修复）均增加 Token 提取和字符估算回退；正反馈仅用于优先提取，不再生成非法 Issue；负反馈根因审核失败时不再标记"已审核"；流式早期失败补充记忆使用审计。生产写入验证会使用唯一 `audit-prod-<timestamp>` 条目，验证后立即清理。剩余主要风险来自模型服务可用性、空 `profile.json` 数据缺口，以及审计样本不足时 `conversation_usage` 的统计意义有限。

---

## 🎯 System Skills

项目内置 **4 个系统级 Skill**，位于 `.skills/system/`，提供记忆管理与人工通知能力。

### 💭 memory-creator（记忆创建）

将对话问答或文档文本转化为结构化的 JSON 记忆文件，写入 `.memory/` 目录。Agent 强制返回规定 JSON schema，每条提取结果包含 `content`、`content_type`、`speed_lookup`、`retrieval` 字段。

**三种提取管道：**

| 管道 | 触发方式 | 目标文件 |
|:-----|:---------|:---------|
| **chat_summary_chain** | 自动/会话总结 | explicit.json, profile.json, work.json, inbox.json, timeline/ |
| **explicit_memory_chain** | `/记忆生成` 指令 | explicit.json, profile.json, work.json, timeline/ |
| **document_chunk_chain** | 文档上传 | documents/{id}.json, work.json |

### 📖 memory-reader（记忆读取）

读取 `.memory/` 目录中的 JSON 记忆文件，根据当前用户请求选择最相关的记忆，构建聚焦但更充分的 Memory Pack 注入 Agent 上下文。评分以 speed_lookup 权重最高（精确匹配 +10.0）。Memory Pack 按真实 `file_key` 分组，跨主文件、timeline、documents 去重，并返回 `confidence`、`reason`、`selected_files`、`omitted_files`、`needs_more_memory` 供审计记录使用；如果相关记忆因预算未纳入，`reason` 会明确说明预算截断数量。

| 模式 | Token 上限 | 适用场景 |
|:-----|:---------:|:---------|
| compact | 1500 | 包含显式记忆、关键约束和直接相关的文档/时间线事实 |
| default | 4000 | 包含显式记忆、工作记忆、用户偏好、相关时间线和文档记忆 |
| expanded | 8000 | 额外包含更完整的相关文档、时间线和工作笔记上下文 |

### 🔍 memory-reviewer（记忆审核）

审核 `.memory/` 中的 JSON 记忆文件和 Memory Pack 的质量，检测重复、冲突、过期、放置错误、冗长/重复、碎片化等问题。默认 `review` 模式只读；`dry_run` 只预演补丁；`patch` 会自动应用生成的安全补丁，底层补丁应用器会跳过删除 `explicit` 的补丁。`--skip-report` 可用于无报告、无写入的健康检查。

| 类型 | 说明 |
|:-----|:-----|
| `memory_files` | 审核记忆文件质量 |
| `memory_pack` | 审核 Memory Pack 是否遗漏重要记忆 |
| `user_feedback` | 将用户纠正转化为修复补丁 |
| `conversation_usage` | 基于审计样本分析记忆使用效率 |
| `scheduled_cleanup` | 复盘时间线、合并重复、收敛冗余或碎片化内容并建议清理 |

**CLI 示例：**

```powershell
# 只读审查，不写报告、不写记忆文件
.\.venv\Scripts\python.exe .skills\system\memory-reviewer\script\review.py --review-type memory_files --memory-dir .memory --mode review --skip-report

# 预演补丁
.\.venv\Scripts\python.exe .skills\system\memory-reviewer\script\review.py --review-type memory_files --memory-dir .memory --mode dry_run

# 应用生成的安全补丁；删除 explicit 的补丁会被底层保护跳过
.\.venv\Scripts\python.exe .skills\system\memory-reviewer\script\review.py --review-type memory_files --memory-dir .memory --mode patch
```

### 📢 notify-me（人工通知）

> **核心原则：宁可通知也不编造**

**触发场景：**

- 无法给出可靠回答，存在编造风险
- 超出 Agent 能力范围
- 工具调用失败或数据异常
- 涉及需要人工确认的敏感操作

### 👍 用户反馈闭环体系

企业微信用户可对 Bot 回复进行"满意/不满意"反馈，系统完整收集并分析反馈数据，形成质量改进闭环：

**反馈收集：**
- 企业微信消息反馈事件自动解析（支持 `feedback_event` / `feedback` 多种 payload 格式）
- 反馈结果：`useful`（满意）/ `useless`（不满意）
- 无用反馈支持原因收集：与问题无关、内容不完整、内容有错误、数据分析错误

**反馈存储：**
- `message_feedbacks` 表存储完整反馈记录
- `feedback_alert_log` 表记录告警历史
- 支持按会话、Bot、时间维度查询

**反馈分析（Web 控制台）：**
- **统计概览**：总反馈数、有效/无效数量、满意度百分比
- **消息维度**：按消息聚合查看反馈状态（有效/无效/有争议）
- **无用反馈详情**：问题、回复、反馈原因、用户信息
- **告警记录**：查看历史告警通知

**告警机制：**
- 配置项：`config.yaml` 中 `feedback_alert` 节点
- 触发条件：指定时间窗口内无用反馈数超过阈值
- 通知方式：Markdown 消息通知绑定管理员
- 防重复：冷却时间内不重复告警

**记忆闭环：**
- 反馈数据自动进入 `memory-reviewer` 的审查样本
- `useless` 反馈标记为 `needs_more_memory`，驱动记忆质量改进
- `useful` 反馈作为正面参考，优化记忆召回策略

***

## ⏰ 定时任务系统

系统内置周期任务和一次性任务，统一存储在 `scheduled_tasks` 表，由任务调度器按 `interval_days`、执行时间和任务状态驱动：

| 任务 | handler_name | 说明 |
|:-----|:-------------|:-----|
| 记忆更新 | `memory_update` | 从聊天记录提取记忆，写入 .memory/ |
| 文档记忆提取 | `document_memory_extraction` | 从上传文档提取结构化记忆 |
| 会话记忆审查 | `self_review_chat_memory` | 审核会话记忆质量，默认只读报告 |
| 文档记忆审查 | `self_review_document_memory` | 审核文档记忆质量，默认只读报告 |
| 显式记忆 | `explicit_memory` | `/记忆生成` 指令或显式记忆任务 |
| 数据库清理 | `database_cleanup` | 清理过期日志和临时数据 |
| Bot 任务 | `bot_task` | Agent + Skill + MCP 通用任务 |

**任务完成后通知**：记忆更新、文档提取、会话审查、文档审查支持配置 `通知Bot`，任务完成后通过选定 Bot 发送结果摘要；显式记忆和 Bot 任务通过执行 Bot 通知结果。未配置通知 Bot 的平台 Agent 任务只记录任务状态和项目日志。

**手动触发**：在任务列表页点击"详情"进入详情面板，可查看任务完整参数、上次执行结果、通知 Bot，并立即执行。系统底层任务（记忆/文档/审查）会弹出提示："该任务耗时较久，请耐心等待。"

***

## ⚙️ 配置指南

### 🔑 首次使用

1. 启动 Web 控制台
2. 在浏览器中配置 **Bot 凭证**（bot\_id / secret）
3. 配置 **Agent API 密钥**（选择提供商并填入 key）
4. 在企业微信中向机器人发送 `connect mycom` 完成绑定
5. 绑定成功且 Agent API 测试通过后，Bot 自动启用

### 🌐 支持的 Agent 提供商

| 提供商             | 类型标识                | 说明                                  |
| :-------------- | :------------------ | :---------------------------------- |
| OpenAI          | `openai`            | GPT-5/GPT-4.1/4o/o 系列、o1/o3/o4-mini |
| Claude          | `claude`            | Claude Opus/Sonnet/Haiku 4.x 全系     |
| Gemini          | `gemini`            | Gemini 3.1/3/2.5/2.0 全系             |
| Qwen DashScope  | `dashscope`         | Qwen3.6/3.5/3 系列、Qwen-VL Plus/Max       |
| DeepSeek        | `deepseek`          | DeepSeek-V4/Chat/Reasoner           |
| GLM (智谱)        | `zhipu`             | GLM-5.1/5/4.7 全系                    |
| MiniMax         | `minimax`           | MiniMax M2.7/M2.5 全系                |
| Kimi (Moonshot) | `moonshot`          | Kimi K2.6/K2.5、Moonshot V1          |
| Ollama / 本地模型   | `openai_compatible` | 自定义 base\_url                       |
| 自定义             | `openai_compatible` | 任意 OpenAI 兼容接口                      |

### 🎯 Skills 技能系统

- Skills 存放在 `.skills/` 目录下
- 控制台支持上传 zip 包、重新扫描、启用/禁用
- 启用的 Skills 自动注入 Agent 提示词

### 🔧 MCP 工具协议

- MCP 工具从配置的 MCP 服务器动态发现
- 工具列表在控制台实时展示
- MCP 提示词引导仅在启用且存在服务器配置时注入
- 支持 stdio / streamable-http 两种传输方式
- stdio 类型支持 `env` 环境变量，用于传递认证 Token 等敏感信息

**MCP 服务器配置格式：**

```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "@example/mcp-server@latest"],
      "env": {
        "API_TOKEN": "your-token-here"
      }
    }
  }
}
```

***

## 💾 数据存储

所有运行时数据存储在 SQLite 中，无需外部数据库服务。

| 数据           | 存储位置                                      |
| :----------- | :---------------------------------------- |
| 数据库文件        | `data/ai_database.db`                     |
| 加密密钥文件       | `data/.encryption_key`（Fernet AES128 加密）  |
| Agent 提供商配置  | SQLite `agent_provider_config` 表          |
| AI 工作项       | SQLite `ai_work_items` 表                  |
| Bot 配置       | SQLite `bot_config` 表                     |
| Bot-MCP 映射   | SQLite `bot_mcp_mapping` 表                |
| Bot-Skill 映射 | SQLite `bot_skill_mapping` 表              |
| 对话消息         | SQLite `chat_messages` 表                  |
| 上下文压缩摘要      | SQLite `conversation_context_summaries` 表 |
| 对话           | SQLite `conversations` 表                  |
| 人工回复队列       | SQLite `manual_reply_commands` 表          |
| MCP 服务器配置    | SQLite `mcp_server_config` 表              |
| MCP 工具目录     | SQLite `mcp_tool_catalog` 表               |
| 项目日志         | SQLite `project_logs` 表                   |
| 定时任务         | SQLite `scheduled_tasks` 表                |
| Skill 配置     | SQLite `skill_config` 表                   |
| LLM 请求槽位     | SQLite `llm_request_slots` 表              |
| 记忆使用审计       | SQLite `memory_usage_audits` 表            |
| Token 用量     | SQLite `token_usage` 表                    |
| 上传文档         | SQLite `uploaded_documents` 表             |
| 用户档案         | SQLite `user_profile` 表                   |
| 消息反馈         | SQLite `message_feedbacks` 表              |
| 反馈告警记录       | SQLite `feedback_alert_log` 表             |

> ⚠️ `data/` 目录已加入 `.gitignore`，不会提交到仓库

数据管理页的“记忆量”卡片来自 `/api/data/overview`：

| 卡片 | 统计口径 |
|:-----|:---------|
| 上传文档数 | `uploaded_documents` 总数 |
| 已转换记录数 | `chat_messages.convert_status = 'converted'` |
| 记忆更新次数 | `scheduled_tasks.handler_name = 'memory_update'` 且 `last_run_status = 'completed'` |
| 文档提取次数 | `scheduled_tasks.handler_name = 'document_memory_extraction'` 且 `last_run_status = 'completed'` |

Token 用量卡片来自 `/api/data/token-usage`：累计记录数为 `token_usage` 总行数，平均/最高单次调用分别对应 `AVG(total_tokens)` 和 `MAX(total_tokens)`，用于快速发现异常大调用。

***

## ⚙️ 运行机制

- Web 控制台不会自动启动任何 Bot
- Web 控制台默认监听 `0.0.0.0:8765`，启动脚本会打印本机和局域网访问地址
- API 已启用 CORS，方便从 localhost、局域网 IP 或独立前端调试访问
- 多 Bot 并行运行，每个 Bot 由 `main.py --run-bot --bot-key <key>` 启动为子进程
- AI 自动回复默认关闭，避免意外 API 消耗
- Bot 仅在绑定成功且 Agent API 测试通过后视为启用
- 上下文压缩基于字符计数：超过阈值自动压缩为摘要
- 支持为任务配置通知 Bot，任务完成后发送执行结果摘要
- 平台 Agent 超时上限 1800 秒（30 分钟），用于耗时较久的记忆任务

***

## 📚 API 文档

项目提供完整的 OpenAPI 3.1 规范文档，可通过 Swagger UI 在线访问：

| 文档类型 | 地址 |
|:--------|:-----|
| **Swagger UI** | `http://<服务器IP>:8765/docs` |
| **OpenAPI JSON** | `http://<服务器IP>:8765/openapi.json` |

> 💡 启动服务后，访问 `http://localhost:8765/docs` 可查看交互式 API 文档（需先登录控制台）。

***

## 📄 License

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License">
</p>

<p align="center">
  MIT License · 自由使用 · 欢迎贡献
</p>

***

<p align="center">
  <strong>让人回归创造</strong> — 让 AI 成为你的助手，而不是你的替代品
</p>
