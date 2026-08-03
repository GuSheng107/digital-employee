# page-module-minimal template

## 用途

这是当前仓库推荐的轻量页面模块参考模板，适用于：

- 普通页面
- 简单列表页
- 不需要局部 Zustand 的页面
- 仅需页面主组件和样式文件即可起步的场景

该模板基于当前仓库约束设计：

- `React + TypeScript + Vite`
- `CSS Modules`
- `Ant Design`
- `Axios`
- 页面模块优先 + 全局公共抽离

## 什么时候选它

满足以下任一条件时，优先选择 `page-module-minimal`：

1. 页面状态主要由本地 `useState` 驱动
2. 当前页面还不需要 `store/`
3. 查询区、表格区和页面编排可以留在同一主组件中
4. 你还不确定页面复杂度是否值得上完整模板

如果页面已经存在明显的局部状态编排、复杂列定义或多个局部模块协作，再切换到 `templates/page-module-full/`。

## 目录结构

```text
page-module-minimal/
  README.md
  UserManage.tsx
  index.module.css
```

## 必选与可选

- 必选：`UserManage.tsx`、`index.module.css`
- 按需：`components/`、`api/`、`types/`

## 如何改造成你的业务

1. 将 `user-manage` 替换为你的业务名称，例如 `employee-roster`
2. 将 `UserManage` 替换为你的页面组件名，例如 `EmployeeRoster`
3. 将模板文件复制到真实页面目录，例如 `frontend/src/pages/employee-roster/`
4. 若页面出现私有组件，再增加 `components/`
5. 若页面出现独立请求逻辑，再增加 `api/` 和 `types/`
6. 若页面内多个组件开始共享状态，再评估是否升级到 `page-module-full`

## 使用原则

1. 先用最小结构完成页面，再按复杂度增长拆分。
2. 若新增样式文件，优先使用 `index.module.css`，不要使用 `PascalCase.module.css`。
3. 请求统一复用全局 `src/utils/request.ts`。
4. 组件文件使用 `PascalCase`，目录和非组件文件使用 `kebab-case`。
5. 不为了“看起来规范”而预先创建 `store/`、`hooks/`、`constants/`。
