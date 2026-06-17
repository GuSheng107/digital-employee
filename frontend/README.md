**项目说明（wecom-bot-agent-web）**

简介
- **技术栈**：React + TypeScript + Vite，CSS Modules 用于组件样式隔离。

仓库结构（项目重要路径）
- 根目录：配置与构建相关文件（`package.json`、`vite.config.ts`、`tsconfig.json` 等）
- `src/`：源码目录
  - `main.tsx`：应用入口
  - `router.tsx`：路由配置
  - `components/`：通用组件
  - `Layout/`：项目布局（Header、Sider、Main）
  - `pages/`：页面视图（PageA、PageB 等）
  - `store/`：全局状态（例如 `user.ts`）
  - `utils/`：工具函数（例如 `request.ts`）

快速上手
- 安装依赖：
```bash
npm install
```
- 启动开发服务器：
```bash
npm run dev
```
- 生产构建：
```bash
npm run build
```

## 代码规范

禁止：
1. 禁止使用 `as` 逃脱类型检测
2. 函数除了 `void` 不显式声明返回类型外，需要显式声明返回类型
3. 禁用 `any`
4. 禁用 `eval` 和 `new Function`

命名规范
1. 文件夹与非组件文件：全小写 + 横杠 (kebab-case)
  在项目根目录以及 `src` 内部，除了存放组件的文件夹以外，其余所有文件夹、纯 JS/TS 脚本、样式文件，一律使用全小写加横杠。
  - 业务/普通文件夹示例：pages, components, hooks, utils, api, assets
  - 多单词文件夹示例：user-manage, system-config, page-a
  - 样式与普通文件示例：admin-layout.module.css, user-api.ts, auth-helper.ts
  理由：Windows 系统对文件名大小写不敏感，但部署的 Linux 服务器极度敏感。全小写横杠能彻底避免本地能跑、线上报错的“灵异事件”。

2. 组件命名：大驼峰/帕斯卡 (PascalCase)
  - 返回 TSX 结构的 React 组件，其文件/专属文件夹均采用首字母大写。
  - 方案 A（单文件组件）：组件文件名示例 `AdminLayout.tsx`，导出为 `export default function AdminLayout() { ... }`
  - 方案 B（文件夹包裹组件）：文件夹名 `PageA`，内部主文件 `index.tsx`，样式 `index.module.css`，组件名 `PageA`。引入示例：`import PageA from '@/pages/PageA'`。

3. 变量、常量与函数：语义化分工
  - 普通变量/对象/函数：小驼峰 (camelCase)。示例：`userInfo`, `loading`, `isCollapsed`。
  - 事件处理函数：以 `handle` 开头，例如 `handleMenuClick`、`handleSubmit`。
  - 副作用/请求函数：以动词开头，例如 `getUserList()`、`updateStatus()`。
  - 自定义 Hook：以 `use` 开头，例如 `useAuth()`、`useWindowSize()`。
  - 全局静态常量：全大写 + 下划线 (UPPER_CASE)，仅用于不可变常量，例如 `MAX_FILE_SIZE`、`API_TIMEOUT`。
  - TS 类型与接口：大驼峰 (PascalCase)，例如 `interface UserItem { id: number; name: string }`。
