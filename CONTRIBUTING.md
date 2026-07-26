# 贡献指南

首先，感谢你抽出时间为本项目做出贡献！🎉

以下内容是参与 Digital Employee 项目的协作指南。这些大多是建议而非强制规则，请根据实际情况灵活判断，也欢迎通过 PR 对本文档提出改进建议。

> 📖 **速览** — 核心成员作为 Collaborators 直接创建功能分支；外部贡献者先 Fork。
> 所有提交到 `master` 的改动都必须发起 Pull Request，通过 review 后使用
> **Squash and merge** 或 **Rebase and merge** 合入。

---

## 目录

- [行为准则](#行为准则)
- [如何贡献](#如何贡献)
  - [反馈 Bug](#反馈-bug)
  - [建议新功能](#建议新功能)
  - [首次代码贡献](#首次代码贡献)
  - [Pull Request 流程](#pull-request-流程)
  - [CI / Review 规则](#ci--review-规则)
- [开发环境搭建](#开发环境搭建)
- [项目约定](#项目约定)
  - [分支命名](#分支命名)
  - [提交信息](#提交信息)
  - [代码规范](#代码规范)
  - [测试要求](#测试要求)
  - [数据库变更](#数据库变更)
- [分支保护规则（master）](#分支保护规则master)
- [发布流程](#发布流程)

---

## 行为准则

本项目及所有参与者承诺为每一位贡献者提供友善、无骚扰的协作环境，
不论年龄、体型、残疾、族裔、性别特征、性别认同与表达、经验水平、
教育程度、社会经济地位、国籍、个人形象、种族、宗教或性取向。

请保持礼貌与善意。讨论可以，分歧可以，但不接受不尊重他人的行为。

---

## 如何贡献

### 反馈 Bug

🐛 **在提交 bug 报告之前：**

- 确认你正在使用最新的 `master` 分支代码
- 搜索 [issue 列表](../../issues) 看看是否已经有人报告过
- 收集相关信息：操作系统、Python/Node 版本、错误堆栈、复现步骤

📝 **提交 bug 报告时请包含：**

- 清晰、描述性的标题
- 精确的复现步骤
- 期望行为 vs 实际行为
- 截图或日志（如适用）
- 环境信息（OS、版本、配置）

> ⚠️ **安全漏洞** 严禁通过公开 issue 报告，请直接私下联系维护者。

### 建议新功能

💡 功能建议通过 GitHub issue 跟踪。提交时：

- 使用清晰、描述性的标题
- 详细描述期望的行为
- 解释 **为什么** 这个功能有用
- 列出你已经考虑过的替代方案

### 首次代码贡献

🌱 适合新手的 issue 会打上 `good first issue` 标签，这些任务范围明确，
能帮助新贡献者熟悉代码库。

不确定从哪里开始？查找以下标签的 issue：
- `good first issue` — 范围小、定义清晰的小任务
- `help wanted` — 需要更多关注的任务
- `documentation` — 文档改进

### Pull Request 流程

核心成员会加入仓库 Collaborators，可以直接在原仓库创建功能分支；外部贡献者仍然使用 Fork + PR 的方式参与。

🔀 **完整流程：**

1. 核心成员在原仓库创建功能分支；外部贡献者先 **Fork** 仓库。
2. 从最新 `master` **创建分支**（参见 [分支命名](#分支命名)）。
3. **进行修改**，保持 PR 小而专一，避免一个 PR 同时混入多类改动。
4. **编写或更新测试**。如果暂时无法补测试，需要在 PR 描述里说明原因。
5. **本地运行 lint 和测试** 后再推送。
6. 用清晰的 message **提交**（参见 [提交信息](#提交信息)）。
7. **推送** 分支到远端。
8. 发起指向 `master` 的 **Pull Request**。
9. 填写 **PR 说明**：改了什么、为什么改、怎么验证、是否有风险。
10. 根据 review 反馈继续推送新 commit。
11. 等待 **CI 通过**（接入后）并至少获得一次 review 批准。
12. 批准后，PR 通过 **Squash and merge** 或 **Rebase and merge** 合入。

📋 **PR 自检清单**（reviewer 会按此检查）：

- [ ] 我的代码遵循项目代码规范
- [ ] 我对自己的代码进行了 self-review
- [ ] 我已在难以理解的地方添加了注释
- [ ] 我已相应更新了文档
- [ ] 我的改动没有产生新的 warning
- [ ] 我已添加能证明功能/修复有效的测试
- [ ] 新增和现有的单元测试在本地全部通过
- [ ] 任何依赖的改动已经合并并发布

💡 **提交高质量 PR 的建议：**

- 保持 PR **小而专一** — 一个 PR 只做一类逻辑修改
- 使用符合 `type(scope): description` 格式的 **描述性标题**
- 用 `Fixes #123` 或 `Closes #456` 关联相关 issue
- UI/视觉类改动添加 **截图**
- 积极 **响应 review 反馈** — 超过 2 周无响应可能被关闭

### CI / Review 规则

现阶段先把 PR + Review 流程跑顺，CI 接入后再把 status checks 设为强制。

**Review 规则：**

- 所有进入 `master` 的改动都走 PR。
- Collaborators 也不要直接 push 到 `master`。
- 默认至少需要 1 个 reviewer 批准。
- PR 有未解决评论时，不合并。
- review 后如果又推送了新 commit，旧 approval 会失效，需要重新确认。
- 大功能先拆小 PR；如果拆不开，先写清楚设计说明和风险。

**CI 规则：**

- CI 接入前，PR 作者负责在本地说明测试结果。
- CI 接入后，PR 合并前必须通过 required status checks。
- 第一批 required checks 建议包括：
  - 后端测试
  - 前端构建 / 测试
  - lint
  - 依赖 pin 检查
- CD 暂时不作为合并前置条件，等项目有稳定发布流程后再考虑。

---

## 开发环境搭建

### 前置依赖

| 工具 | 版本要求 | 用途 |
|------|----------|------|
| Python | 3.10+ | Backend Agent |
| Python | 3.11+ | Backend Gateway |
| Node.js | 22.14.x | 根目录 React 前端（以 `frontend/package.json` 为准） |
| uv | 当前稳定版 | Backend Gateway 依赖与命令管理 |
| Docker Compose | 可选 | 启动 RabbitMQ 与 MinIO 本地依赖 |

### 克隆与安装

```bash
git clone https://github.com/GuSheng107/digital-employee.git
cd digital-employee

# Backend Agent
cd backend-agent
python -m venv .venv
source .venv/bin/activate   # Windows 用 .venv\Scripts\activate
pip install -e . pytest
cd ..

# Backend Gateway
cd backend-gateway
python -m pip install uv
python -m uv sync
cp .env.example .env
cp config/bot.template.json config/bot.json
cd ..

# React 管理端
cd frontend
npm ci
npm run build
cd ..

# 或在已安装 GNU Make 的环境使用统一命令
make install
make build
```

### 启动项目

```bash
# 启动 Backend Agent（Linux / macOS）
./scripts/backend-agent/start.sh

# 启动 Backend Agent（Windows）
scripts\backend-agent\start.bat

# 启动代码当前依赖的 RabbitMQ 与 MinIO
docker compose up -d

# 启动 Backend Gateway（另开终端）
cd backend-gateway
uv run python -m src.main

# 启动 React 新管理端开发服务器（另开终端，Linux / macOS）
./scripts/start-web.sh

# 或（Windows）
scripts\start-web.bat
```

Backend Agent 默认监听 <http://localhost:8765>（仅暴露 API），Backend Gateway 默认监听 <http://localhost:8864>。管理端前端位于根目录 `frontend/`，启动方式见上文的 `scripts/start-web.sh` / `scripts\start-web.bat`。

---

## 项目约定

### 分支命名

使用以下前缀，保持简短且具描述性（前缀后用 kebab-case）。

| 前缀         | 用途                          | 示例                              |
|--------------|-------------------------------|-----------------------------------|
| `feat/`      | 新功能                        | `feat/add-feishu-adapter`         |
| `fix/`       | Bug 修复                      | `fix/memory-leak-on-disconnect`   |
| `refactor/`  | 重构（不改行为）              | `refactor/extract-platform-base`  |
| `docs/`      | 仅文档                        | `docs/improve-contributing`       |
| `test/`      | 添加或改进测试                | `test/add-platform-conn-tests`    |
| `chore/`     | 工具、依赖、CI 等杂项         | `chore/bump-fastapi-version`      |
| `perf/`      | 性能优化                      | `perf/optimize-message-queue`     |
| `hotfix/`    | 紧急生产修复                  | `hotfix/fix-token-refresh`        |

> ❌ 避免：`patch`、`temp`、`wip`、`my-changes` 等无前缀或含义不明的名字。

### 提交信息

遵循 **Conventional Commits** 规范（可带 scope），便于自动生成变更日志。

**格式：**

```
<type>(<scope>): <subject>

<body>

<footer>
```

**type：** `feat` · `fix` · `refactor` · `docs` · `test` · `chore` · `perf` · `ci` · `build` · `style`

**scope（本项目）：** `agent` · `gateway` · `frontend` · `platform` · `config` · `core` · `db`

**subject 规则：**

- 使用祈使语气：写 "add feature" 而非 "added feature"
- 全小写，结尾不要句号
- ≤72 字符
- subject 中不要使用 emoji

**示例：**

```text
feat(platform): add feishu websocket adapter
fix(agent): resolve memory leak in long connection
refactor(gateway): extract PlatformBase from wecom_bot
docs: update README with platform support table
chore(deps): bump fastapi to 0.115.0
```

**破坏性变更** 必须在 footer 中注明：

```
feat(platform)!: replace webhook with grpc transport

BREAKING CHANGE: webhook platform configs must be migrated to grpc
```

### 代码规范

简要总结：

- **Python**：遵循 PEP 8；snake_case；公共 API 使用 type hints 与 docstring；Gateway 使用 Ruff 检查
- **React/TypeScript**：遵循 `frontend/docs/frontend-development-spec.md`，使用 ESLint、CSS Modules 和严格类型约束

### 测试要求

- ✅ 每个新功能 **必须** 包含测试
- ✅ 每个 bug 修复 **必须** 包含回归测试
- ✅ 提交 PR 前测试必须在本地通过
- ✅ 关注行为覆盖，不追求覆盖率数字
- ❌ 不要通过禁用或跳过已有测试来让改动通过

提交前按改动范围运行对应检查：

```bash
# Backend Agent
backend-agent/.venv/Scripts/python.exe -m pytest backend-agent/tests

# Backend Gateway
cd backend-gateway
uv run ruff check src

# React 管理端
cd ../frontend
npm run lint
npm run build
```

也可以在已安装 GNU Make 的环境运行 `make check`。Gateway 当前没有提交自动化测试；修改其行为时应随功能补充测试，而不是把 Ruff 当作测试替代品。

### 数据库变更

我们 **不使用** 任何数据库迁移框架（不用 Alembic）。

当你需要修改数据库表结构时：

1. 在 `backend-agent/scripts/db_migrations/` 下编写 **一次性脚本**
2. 脚本必须 **幂等**（重复运行不报错）
3. 脚本必须有 **注释文档**（开头说明用途和影响）
4. **不保留** 旧数据结构，倾向一次性切换
5. 脚本部署时运行一次，验证后删除

---

## 分支保护规则（master）

`master` 分支建议采用以下保护规则：

| 规则                                       | 状态 |
|--------------------------------------------|------|
| Require a pull request before merging      | ✅    |
| Dismiss stale pull request approvals       | ✅    |
| Require approvals                          | ✅（建议 1 人） |
| Require conversation resolution            | ✅    |
| Require status checks to pass              | ⏳（CI 接入后开启） |
| Require linear history                     | ✅（配合 Squash / Rebase merge） |
| Lock branch                                | ❌    |
| Do not allow bypassing the above settings  | ✅    |
| Allow force pushes                         | ❌    |
| Allow deletions                            | ❌    |

**影响：**

- 所有 `master` 的变更都必须走 PR 流程
- 管理员也不绕过上述规则
- 禁止向 `master` force-push
- `master` 不可被删除
- 推送新 commit 后旧的 review 自动失效

> ℹ️ 后续接入 GitHub Actions 后，再把 status checks 加入 required checks。

---

## 发布流程

计划流程：

1. 在 `pyproject.toml` 和 `package.json` 中升级版本号
2. 更新 `CHANGELOG.md`（从 conventional commit 自动生成）
3. 打 tag：`git tag -a vX.Y.Z -m "Release vX.Y.Z"`
4. 推送 tag：`git push --tags`
5. 在 GitHub 上根据 tag 起草 Release Notes

---

## 有疑问？

- 🐛 Bug 与功能请求请提交 [Issue](../../issues)
- 📧 敏感事项请联系维护者

**感谢你的贡献！** 🙌
