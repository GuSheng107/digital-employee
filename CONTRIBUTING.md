# 贡献指南

感谢你对 Digital Employee 项目的关注！以下是参与贡献的流程。

## 分支保护规则（master）

`master` 分支已启用 GitHub 分支保护，当前配置如下：

- ✅ **Require a pull request before merging** — 必须通过 PR 合入
- ✅ **Dismiss stale pull request approvals when new commits are pushed** — 推送新 commit 后旧 review 自动失效
- ✅ **Require linear history** — 不允许 merge commit，必须 rebase 或 squash
- ✅ **Lock branch** — master 只读，禁止直接推送
- ✅ **Do not allow bypassing the above settings** — 管理员也需遵守
- ❌ Require approvals — 不强制 review（团队小，自审即可）
- ❌ Require status checks — 暂未启用 CI
- ❌ Allow force pushes — 禁止强制推送
- ❌ Allow deletions — 禁止删除 master

## 开发环境搭建

### 1. Backend Agent（Python）

```bash
cd backend-agent
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

### 2. Frontend（构建时需要）

```bash
cd frontend
npm install
npm run build    # 构建静态文件，由 backend-agent 托管
```

### 3. Backend Gateway（Go，参考用）

```bash
cd backend-gateway/cmd/cc-connect
go build .
```

## 协作流程

### 1. 创建功能分支

```bash
git checkout master
git pull origin master
git checkout -b feat/<name>     # 或 fix/、chore/、docs/
```

分支命名规范：
- `feat/xxx` - 新功能
- `fix/xxx` - 修复
- `chore/xxx` - 杂项（重构、依赖更新等）
- `docs/xxx` - 文档
- `refactor/xxx` - 重构

### 2. 开发 & 提交

```bash
# 频繁小提交
git add <specific-files>
git commit -m "type(scope): description"
```

提交规范：

```
type(scope): description
```

- **type**: feat | fix | refactor | docs | test | chore | ci
- **scope**: agent | gateway | frontend | platform | config | core

示例：
- `feat(platform): add feishu websocket adapter`
- `fix(agent): resolve memory leak in long connection`
- `docs: update README with platform support table`

### 3. 推送 & 创建 PR

```bash
git push -u origin feat/<name>
```

在 GitHub 上创建 Pull Request，**目标分支必须指向 `master`**。

### 4. 保持 Linear History

由于启用了 linear history，PR 合入前需要保持线性提交历史：

```bash
# 推送前先 rebase master
git fetch origin master
git rebase origin/master
git push --force-with-lease
```

合入 PR 时建议使用 **Squash and merge** 或 **Rebase and merge**，不要使用普通 merge。

### 5. Code Review

- PR 作者自行 review
- 确认无误后合入 master
- 启用 require approval 时需等待他人 review

### 6. 清理

```bash
git checkout master
git pull origin master
git branch -d feat/<name>
git push origin --delete feat/<name>
```

## 紧急情况

master 已禁止 force push。如需重写历史（如修复泄露的密钥），请：

1. 临时在 GitHub Settings → Branches 启用 "Allow force pushes"
2. 完成 force push 后立即关闭
3. 通知所有协作者重新拉取

## 代码规范

详见 `.ai-memory/code-style.md`

## 测试要求

- 每个新功能必须有对应测试
- 数据库变更使用一次性脚本，不使用迁移工具
- 每步必须测试通过才标记完成
