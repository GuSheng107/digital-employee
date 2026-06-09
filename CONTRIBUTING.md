# 贡献指南

首先，感谢你抽出时间为本项目做出贡献！🎉

以下内容是参与 Digital Employee 项目的协作指南。这些大多是建议而非强制规则，请根据实际情况灵活判断，也欢迎通过 PR 对本文档提出改进建议。

> 📖 **速览** — Fork → 创建分支 → 提交 → 推送 → 发起 Pull Request。提交到 `master`
> 的 PR 需通过 review，并使用 **Squash and merge** 或 **Rebase and merge** 合入。

---

## 目录

- [行为准则](#行为准则)
- [如何贡献](#如何贡献)
  - [反馈 Bug](#反馈-bug)
  - [建议新功能](#建议新功能)
  - [首次代码贡献](#首次代码贡献)
  - [Pull Request 流程](#pull-request-流程)
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

🔀 **完整流程：**

1. **Fork** 仓库（外部贡献者），或在有写权限时创建功能分支。
2. 从 `master` **创建分支**（参见 [分支命名](#分支命名)）。
3. **进行修改**，遵循 [项目约定](#项目约定)。
4. **编写或更新测试**。所有 PR 必须通过现有测试。
5. **本地运行 lint 和测试** 后再推送。
6. 用清晰的 message **提交**（参见 [提交信息](#提交信息)）。
7. **推送** 分支到 origin。
8. 发起指向 `master` 的 **Pull Request**。
9. 填写 **PR 模板** — 说明改了什么、为什么、怎么改的。
10. 通过推送新 commit **响应 review 反馈**（rebase 后需 force-push）。
11. 等待 **CI 通过** 并至少获得一次 review 批准。
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

---

## 开发环境搭建

### 前置依赖

| 工具   | 版本要求 | 用途                          |
|--------|----------|-------------------------------|
| Python | 3.10+    | Backend Agent                 |
| Node   | 18+      | 前端构建（静态）              |
| Go     | 1.21+    | Backend Gateway（仅参考）     |

### 克隆与安装

```bash
git clone https://github.com/GuSheng107/digital-employee.git
cd digital-employee

# Backend Agent
cd backend-agent
python -m venv .venv
source .venv/bin/activate   # Windows 用 .venv\Scripts\activate
pip install -e ".[dev]"
cd ..

# 前端（仅在构建时需要）
cd frontend
npm install
npm run build               # 输出到 backend-agent 的 web 目录
cd ..

# 或使用 Make（Linux/macOS）
make install-agent
make build-frontend
```

### 启动项目

```bash
# Linux / macOS
./scripts/start-web.sh

# Windows
scripts\start-web.cmd
```

Web 控制台将在 <http://localhost:8765> 启动。

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

完整规范见 [`.ai-memory/code-style.md`](./.ai-memory/code-style.md)。

简要总结：

- **Python**：`black` + `isort` + type hints；遵循 PEP 8；snake_case；公开 API 必须有 docstring
- **Vue/JS**：ESLint + Prettier；2 空格缩进；单引号；无分号
- **Go**（gateway）：`gofmt` + `golangci-lint`；显式错误处理

### 测试要求

- ✅ 每个新功能 **必须** 包含测试
- ✅ 每个 bug 修复 **必须** 包含回归测试
- ✅ 提交 PR 前测试必须在本地通过
- ✅ 关注行为覆盖，不追求覆盖率数字
- ❌ 不要通过禁用或跳过已有测试来让改动通过

提交前运行测试套件：

```bash
cd backend-agent
.venv/Scripts/activate   # 或 source .venv/bin/activate
python -m pytest
```

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

`master` 分支已配置以下保护规则：

| 规则                                       | 状态 |
|--------------------------------------------|------|
| Require a pull request before merging      | ✅    |
| Dismiss stale pull request approvals       | ✅    |
| Require approvals                          | ❌（0 人 — 自审即可） |
| Require status checks to pass              | ❌（暂未启用 CI） |
| Require linear history                     | ❌    |
| Lock branch                                | ❌    |
| Do not allow bypassing the above settings  | ✅    |
| Allow force pushes                         | ❌    |
| Allow deletions                            | ❌    |

**影响：**

- 所有 `master` 的变更都必须走 PR 流程
- 管理员 **无法绕过** 上述规则
- 禁止向 `master` force-push
- `master` 不可被删除
- 推送新 commit 后旧的 review 自动失效

> ℹ️ 后续接入 GitHub Actions 后，将启用 status checks。

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
