---
name: "frontend-dev-spec"
description: "用于当前仓库的前端开发、重构和评审规范治理。当用户想新增页面/组件/接口/store、搭页面目录、按规范开发、整理历史前端代码、统一目录命名、治理请求或状态边界、review 前端改动/PR/diff/目录拆分时使用。适用于 React TypeScript Vite CSS Modules Ant Design Axios Zustand 的仓库约束场景。不用于从零生成整站 UI、纯设计美化或纯文档协作。"
---

# Frontend Dev Spec

## Goal

本 skill 用于当前仓库的前端规范治理，只处理三类任务：

1. 开发模式：新增页面、组件、接口、局部状态或页面模块目录。
2. 重构模式：整理历史页面、统一目录命名、收拢请求和状态边界。
3. 评审模式：review 前端改动、PR、diff 或目录重构结果。

本 skill 的职责是：

- 对齐当前仓库真实规则，而不是输出通用前端建议。
- 在需要时按模式加载对应规则，避免一次性注入全部知识。
- 明确页面私有能力和全局公共能力的边界。
- 在新增、重构、评审三个阶段保持同一套治理标准。

## Repository Binding

当前绑定仓库事实如下：

- 前端项目路径：`frontend/`
- 规范主文档：`frontend/docs/frontend-development-spec.md`
- 项目说明：`frontend/README.md`
- 真实配置文件：
  - `frontend/package.json`
  - `frontend/eslint.config.js`
  - `frontend/tsconfig.json`

默认技术栈与治理方式：

- `React + TypeScript + Vite + CSS Modules + Ant Design + Axios + Zustand`
- “页面模块优先 + 全局公共抽离”

如需仓库绑定细节、迁移期说明和代表性路径，读取：

- `references/repository-binding.md`

## Global Rules

无论处于哪种模式，都必须遵守以下全局规则：

1. 最高优先级规则来源始终是 `frontend/docs/frontend-development-spec.md`。
2. 新增代码优先按规范文档执行，不被历史写法绑架。
3. 历史代码按“低风险、高收益、渐进收敛”处理，不鼓励一次性大重构。
4. 页面私有能力优先留在页面目录，确认跨页面复用后再上移全局。
5. 业务目录、普通目录、工具目录优先使用 `kebab-case`；返回 TSX 的组件文件使用 `PascalCase`。
6. 请求统一复用基础请求封装，不重复创建底层请求能力。
7. 输出必须贴合仓库现实，不输出脱离项目的空泛规范。

## Migration Rule

当前仓库处于“规范目标”和“历史现状”并存的迁移期，执行时按以下裁决：

1. 新增代码：按 `frontend/docs/frontend-development-spec.md` 执行。
2. 历史代码重构：以逐步向规范靠拢为目标，优先低风险调整。
3. 改动评审：
   - 对新增不规范直接指出。
   - 对历史债务要判断是否被本次改动扩大。

## Preflight

激活本 skill 后，优先读取：

- `references/preflight.md`

按其中清单确认以下文件是否存在并可作为规则来源：

- `frontend/docs/frontend-development-spec.md`
- `frontend/README.md`
- `frontend/package.json`
- `frontend/eslint.config.js`
- `frontend/tsconfig.json`

如果预检发现缺失，必须按 `references/preflight.md` 的降级策略处理，不能自行臆造配置。

## Mode Selection

### 显式模式

若用户明确说明模式，直接采用：

- 开发模式
- 重构模式
- 评审模式

### 自动判断

若用户未显式说明，按语义判断：

1. 出现“新增、开发、新建、实现、搭目录、按规范开发、写组件、写页面、标准模板”等表达，进入开发模式。
2. 出现“重构、整理、迁移、统一、规范化、拆分、治理历史代码、收拢散落逻辑”等表达，进入重构模式。
3. 出现“review、评审、检查改动、看 PR、看看 diff、检查目录拆分、检查风险”等表达，进入评审模式。

### 歧义处理

若无法稳妥判断模式，只追问一句：

“这次更偏向开发模式、重构模式，还是评审模式？”

## Read Routing

`SKILL.md` 只负责路由和全局规则。进入不同模式后，按需读取对应模块。

### 开发模式路由

先读取：

- `references/development-mode.md`
- `references/repository-binding.md`

如果用户明确需要页面模板、目录骨架或“标准页面模块”：

- 简单页面或普通列表页：读取 `templates/page-module-minimal/README.md`
- 复杂页面或需要局部状态编排：读取 `templates/page-module-full/README.md`

预期产出：

- 推荐目录结构
- 命名建议
- 页面私有 / 全局公共边界判断
- 应选用的模板层级
- 注意事项与自检清单

### 重构模式路由

读取：

- `references/refactor-mode.md`
- `references/repository-binding.md`

仅当用户明确要求按模板靠拢时，再读取：

- `templates/page-module-minimal/README.md` 或 `templates/page-module-full/README.md`

预期产出：

- 问题清单
- 优先级排序
- 分步重构方案
- 目标结构建议
- 风险说明与建议的提交拆分

### 评审模式路由

读取：

- `references/review-mode.md`
- `references/repository-binding.md`

默认不读取模板目录。仅当评审目标是“是否符合标准页面模块模板”时，才补充读取模板说明。

预期产出：

1. Findings
2. Open Questions / Assumptions
3. 简短总结

## Output Floor

无论哪种模式，输出都至少满足以下要求：

1. 明确本次采用的模式。
2. 结论必须指向当前仓库，不得只讲泛泛原则。
3. 对关键边界要说明“为什么这样更适合当前仓库”。
4. 涉及新增或重构时，要说明页面私有能力和全局共享能力的归属。
5. 涉及 review 时，要先讲 findings，再给总结。

## Failure Handling

若执行中遇到以下情况，按对应方式处理：

1. 规范文档缺失：
   - 回退到 `frontend/README.md`、`frontend/package.json`、`frontend/eslint.config.js`、`frontend/tsconfig.json` 与现有源码模式。
   - 在回答中标明规则来源收缩。

2. 规范文档与历史代码冲突：
   - 开发模式以规范文档为准。
   - 重构模式以渐进收敛为准。
   - 评审模式区分新增问题与历史债务。

3. 用户需求超出本 skill 边界：
   - 从零生成整站或纯 UI 设计：应交给 `web-dev` 或 `frontend-design`
   - 纯文档写作：应交给 `doc-coauthoring`

## Deliverables

按模式不同，至少交付以下之一：

1. 开发模式：
   - 推荐目录
   - 命名建议
   - 模板选择
   - 自检清单

2. 重构模式：
   - 问题清单
   - 优先级
   - 分步方案
   - 风险说明

3. 评审模式：
   - Findings
   - 修改建议
   - 残余风险

## Asset Map

本 skill 的工程化资产分工如下：

- `SKILL.md`：入口、路由、全局规则
- `references/`：三种模式细节、预检、仓库绑定说明
- `templates/`：页面模块模板
- `evals/`：触发测试、输出回归、历史问题记录

执行时优先按需读取，不要一次性加载全部文件。
