# frontend-dev-spec

## 这是什么

`frontend-dev-spec` 是当前仓库的前端规范治理 skill。

它不是通用前端建议生成器，而是绑定当前 `frontend/` 子项目，围绕以下三类任务提供稳定输出：

1. 开发模式：新增页面、组件、接口、局部状态或页面模块目录
2. 重构模式：整理历史页面、统一目录命名、收拢请求和状态边界
3. 评审模式：review 前端改动、PR、diff 或目录拆分结果

## 绑定范围

当前 skill 绑定以下真实路径：

- 前端项目目录：`frontend/`
- 规范主文档：`frontend/docs/frontend-development-spec.md`
- 项目说明：`frontend/README.md`
- 配置文件：
  - `frontend/package.json`
  - `frontend/eslint.config.js`
  - `frontend/tsconfig.json`

默认按以下技术栈理解当前前端项目：

- `React`
- `TypeScript`
- `Vite`
- `CSS Modules`
- `Ant Design`
- `Axios`
- `Zustand`

## 什么时候用

以下场景优先使用这个 skill：

- 想按规范新增一个页面模块
- 不确定组件、请求、store、types 该放哪里
- 想整理历史页面、统一目录结构、治理请求和状态边界
- 想 review 一次前端改动是否符合当前仓库规范
- 想拿到标准页面模块模板或整改清单

以下场景不适合使用这个 skill：

- 从零生成整站或完整 Web 应用
- 纯 UI 美化或设计稿生成
- 纯文档写作

## 三种模式

### 开发模式

适合：

- 新增页面
- 新增组件
- 新增接口
- 设计目录结构

典型输出：

- 推荐目录结构
- 命名建议
- 页面私有 / 全局公共边界判断
- 模板选择
- 自检清单

### 重构模式

适合：

- 整理历史代码
- 统一目录结构
- 拆分大组件
- 治理请求散落
- 治理 store 越界

典型输出：

- 问题清单
- 优先级排序
- 分步重构方案
- 风险说明

### 评审模式

适合：

- review 前端改动
- 检查 PR
- 检查 diff
- 检查目录拆分和状态设计

典型输出：

1. Findings
2. Open Questions / Assumptions
3. 简短总结

## 工程化资产

当前 skill 的资产分层如下：

### 入口

- `SKILL.md`
  - 只保留入口、路由、全局规则和输出下限

### 规则模块

- `references/preflight.md`
  - 预检当前仓库的规范文档、README 和配置文件
- `references/repository-binding.md`
  - 说明仓库真实绑定信息、迁移期事实和代表性路径
- `references/development-mode.md`
  - 开发模式详细规则
- `references/refactor-mode.md`
  - 重构模式详细规则
- `references/review-mode.md`
  - 评审模式详细规则

### 模板

- `templates/page-module-minimal/`
  - 适合普通页面和简单列表页
  - 不默认引入局部 store
- `templates/page-module-full/`
  - 适合复杂页面和局部状态编排场景
  - 包含 `components/`、`api/`、`types/`、`hooks/`、`store/`、`constants/`

### 回归资产

- `evals/trigger-cases.md`
  - 触发样例和误触发样例
- `evals/golden-outputs.md`
  - 三种模式的标准输出结构样例
- `evals/regressions.md`
  - 后续记录误触发、漏触发和输出跑偏案例

## 模板怎么选

优先规则：

1. 简单页面先用 `page-module-minimal`
2. 页面复杂度上升，再升级到 `page-module-full`

### 选择 `page-module-minimal`

适合：

- 普通页面
- 简单列表页
- 状态主要由本地 `useState` 驱动
- 不需要局部 Zustand

### 选择 `page-module-full`

适合：

- 页面逻辑较重
- 需要局部 store 编排
- 需要拆查询、表格、列定义、常量等局部模块

## 迁移期说明

当前仓库同时存在“规范目标”和“历史现状”：

- 规范目标要求目录使用 `kebab-case`
- 历史代码里仍存在 `Layout`、`PageA`、`PageB` 这类旧命名

因此执行时按以下原则处理：

1. 新增代码按规范文档输出
2. 重构历史代码按渐进式治理输出
3. 评审时区分“新增问题”和“历史债务”

## 最佳提问方式

为了让输出更稳定，提问时最好带上：

- 当前是开发、重构还是评审
- 涉及的页面或模块名
- 相关目录或文件路径
- 你最在意的问题，例如目录、命名、请求、store、类型或 review 风险

示例：

- “开发模式，帮我在 `src/pages` 下新增一个 `user-manage` 页面模块”
- “重构模式，帮我整理这个页面目录，目标是贴近规范文档”
- “评审模式，帮我检查这次改动是否偏离当前仓库规范”
