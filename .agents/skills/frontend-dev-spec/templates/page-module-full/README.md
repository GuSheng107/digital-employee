# page-module-full template

## 用途

这是当前仓库推荐的完整页面模块参考模板，适用于：

- 中后台列表页
- 带查询表单的业务页面
- 需要局部 `api`、`types`、`store`、`hooks`、`components` 协作的页面模块
- 需要局部 Zustand 或明显页面编排逻辑的复杂页面

该模板基于当前仓库约束设计：

- `React + TypeScript + Vite`
- `CSS Modules`
- `Ant Design`
- `Axios`
- `Zustand`
- 页面模块优先 + 全局公共抽离

注意：

- 该目录用于提供参考代码骨架，不是可独立运行的子项目。
- 正确使用方式是将模板文件按需复制到真实前端工程中，例如 `frontend/src/pages/<page-name>/`。
- 模板中的 `@/utils/request`、`antd`、`zustand` 等依赖，默认依附真实前端工程环境解析。

## 什么时候选它

满足以下任一条件时，优先选择 `page-module-full`：

1. 页面逻辑较重，需要拆查询、表格、列定义、常量等局部模块
2. 需要用局部 `store/` 编排页面查询条件、分页、选中态等状态
3. 页面后续大概率会继续扩展，而不是一次性简单页面

如果只是普通页面或简单列表页，更适合先使用 `templates/page-module-minimal/`。

## 目录结构

```text
page-module-full/
  README.md
  UserManage.tsx
  index.module.css
  api/
    user-manage-api.ts
  components/
    UserManageSearchForm.tsx
    UserManageTable.tsx
  constants/
    user-manage-constants.ts
  hooks/
    use-user-manage-columns.ts
  store/
    use-user-manage-store.ts
  types/
    user-manage.ts
```

## 必选与可选

- 必选：`UserManage.tsx`、`index.module.css`
- 常用：`api/`、`types/`、`components/`
- 增强：`hooks/`、`store/`、`constants/`

## 如何改造成你的业务

1. 将 `user-manage` 替换为你的业务名称，例如 `employee-roster`
2. 将 `UserManage` 替换为你的页面组件名，例如 `EmployeeRoster`
3. 将模板文件复制到真实页面目录，例如 `frontend/src/pages/employee-roster/`
4. 替换 `types/user-manage.ts` 中的字段定义
5. 替换 `api/user-manage-api.ts` 中的接口路径
6. 根据实际场景删掉不需要的 `store/`、`hooks/`、`constants/`
7. 如果页面复杂度不足以支撑这套结构，回退到 `page-module-minimal`

## 使用原则

1. 只在当前页面使用的能力优先放在页面目录内。
2. 两个及以上页面复用时，再上移到全局 `src/components`、`src/api`、`src/store`、`src/hooks`、`src/types`。
3. 请求统一复用全局 `src/utils/request.ts`。
4. 组件文件使用 `PascalCase`，目录和非组件文件使用 `kebab-case`。
5. 不要因为模板完整就默认创建所有目录，仍然按实际复杂度删减。
