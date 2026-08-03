# Repository Binding

本文件描述 `frontend-dev-spec` 当前绑定仓库的真实情况，供开发、重构、评审三种模式引用。

## 绑定范围

- 前端项目根目录：`frontend/`
- 规范主文档：`frontend/docs/frontend-development-spec.md`
- 项目说明：`frontend/README.md`
- 配置文件：
  - `frontend/package.json`
  - `frontend/eslint.config.js`
  - `frontend/tsconfig.json`

## 技术栈事实

根据已存在文件，当前前端项目采用：

- `React`
- `TypeScript`
- `Vite`
- `CSS Modules`
- `Ant Design`
- `Axios`
- `Zustand`

## 规范目标

`frontend/docs/frontend-development-spec.md` 明确了以下目标：

1. 目录治理采用“页面模块优先 + 全局公共抽离”
2. 业务目录、普通目录、工具目录使用 `kebab-case`
3. 返回 TSX 的组件文件使用 `PascalCase`
4. 页面私有能力可维护在页面目录内
5. 请求统一复用基础请求封装

## 历史现状

当前 `frontend/src` 中仍能观察到历史命名风格：

- `frontend/src/components/Layout/`
- `frontend/src/pages/PageA/`
- `frontend/src/pages/PageB/`
- `frontend/src/store/user.ts`

这说明仓库处于迁移阶段，而不是已经完全收敛到规范目标。

## 模式裁决

### 开发模式

新增代码按规范文档执行，不沿用历史命名作为新增代码的默认依据。

### 重构模式

对历史代码优先给出渐进式治理方案：

1. 先收拢目录职责
2. 再统一命名
3. 再处理请求与状态边界
4. 不鼓励一次性全量迁移

### 评审模式

评审时要区分两类问题：

1. 新增问题：本次改动引入的不规范，应直接指出
2. 历史债务：本来就存在的不一致，应判断是否被本次改动扩大

## 代表性路径

### 全局公共能力

- `frontend/src/components/Layout/index.tsx`
- `frontend/src/components/Layout/components/HeaderBar.tsx`
- `frontend/src/components/Layout/components/MainContent.tsx`
- `frontend/src/components/Layout/components/SiderMenu.tsx`
- `frontend/src/store/user.ts`
- `frontend/src/utils/request.ts`
- `frontend/src/router.tsx`

### 页面级能力

- `frontend/src/pages/PageA/index.tsx`
- `frontend/src/pages/PageA/index.module.css`
- `frontend/src/pages/PageB/index.tsx`
- `frontend/src/pages/PageB/index.module.css`

## 使用要求

模式模块引用本文件时，必须做到：

1. 结论优先对齐规范目标
2. 建议能够解释与历史现状的关系
3. 不把历史写法误判为新增代码的推荐写法
