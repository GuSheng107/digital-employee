# 前端开发规范 v1

## 1. 文档目标与适用范围

本规范适用于 `digital-employee-frontend` 前端仓库的日常开发、协作评审与开源贡献。

目标如下：

- 统一代码风格，降低团队成员之间的理解和沟通成本。
- 提升代码可读性、可维护性和可扩展性。
- 减少因命名混乱、职责不清、类型失控导致的线上问题。
- 为后续引入自动化检查、代码审查和开源协作提供统一标准。

本规范优先于个人编码习惯。未覆盖的场景，遵循以下原则：

1. 优先保证可读性。
2. 优先保持项目内一致性。
3. 优先复用已有实现和已有模式。
4. 优先选择易于维护、易于 review 的写法。

## 2. 技术栈与工程约定

当前项目统一采用以下技术栈：

- `React`
- `TypeScript`
- `Vite`
- `CSS Modules`
- `Ant Design`
- `Axios`
- `Zustand`

工程约定如下：

1. 新增功能应优先复用现有技术栈，不随意引入与现有体系重复的库。
2. 页面样式优先使用 `CSS Modules`，避免新增无边界的全局样式。
3. 网络请求统一通过基础封装层发起，页面模块可以维护自己的业务接口文件，但不重复创建底层请求能力。
4. 类型系统是第一道质量防线，禁止通过绕过类型检查来换取短期开发速度。

## 3. 项目目录规范

### 3.1 目录职责

`src` 目录下采用“页面模块优先 + 全局公共抽离”的混合组织方式：

- `assets`：静态资源，如图片、图标、字体。
- `components`：跨页面复用的公共组件，包括通用组件和布局组件。
- `pages`：页面级业务模块，按业务页面拆分。
- `store`：跨页面共享的全局状态管理。
- `api`：跨页面复用的接口能力与业务接口封装。
- `hooks`：跨页面复用的自定义 Hook。
- `types`：跨页面复用的公共类型。
- `utils`：通用工具与基础能力封装。
- `router.tsx`：路由入口与路由组织。
- `main.tsx`：应用启动入口。

新增目录或文件时，需要先判断其职责归属，避免以下问题：

- 页面私有逻辑被过早抽到全局，导致目录分散、理解成本升高。
- 跨页面共享能力长期滞留在单个页面目录，导致复用边界混乱。
- 通用工具和业务工具混放。
- 全局状态与页面状态边界不清。

### 3.2 目录命名规则

统一规则如下：

1. 业务目录、普通目录、工具目录统一使用 `kebab-case`。
2. 非组件文件统一使用 `kebab-case`。
3. 返回 TSX 结构的组件文件使用 `PascalCase`。
4. 组件目录不再使用 `PascalCase`，统一改为 `kebab-case`。

示例：

```text
src/
  components/
    layout/
      Layout.tsx
      HeaderBar.tsx
      MainContent.tsx
      SiderMenu.tsx
      index.module.css
    user-card/
      UserCard.tsx
      index.module.css
  pages/
    user-manage/
      components/
        UserManageTable.tsx
        UserManageSearchForm.tsx
      hooks/
        use-user-manage-columns.ts
      api/
        user-manage-api.ts
      store/
        use-user-manage-store.ts
      types/
        user-manage.ts
      constants/
        user-manage-constants.ts
      UserManage.tsx
      index.module.css
  api/
    auth-api.ts
  store/
    user-store.ts
  utils/
    request.ts
    auth-helper.ts
```

说明：

- 目录表达“业务归属”或“职责归属”，所以使用 `kebab-case`。
- 组件文件表达“组件实体”，所以使用 `PascalCase`。
- 页面模块允许就近维护私有的 `api`、`store`、`types`、`hooks`、`components`。
- 只有在两个及以上页面复用时，才将能力上移到全局公共目录。

### 3.3 文件组织原则

1. 单个目录只表达一个主要职责。
2. 页面目录可以收拢当前页面直接相关的组件、样式、类型、请求、局部状态与常量。
3. 只被当前页面使用的能力，优先放在页面目录内维护。
4. 多页面复用的能力应上移到 `components`、`api`、`hooks`、`store`、`types` 或 `utils`。
5. 若某个页面目录文件数量持续增长，应根据职责拆出子目录，而不是堆叠在同一级。

## 4. 命名规范

### 4.1 通用命名

- 目录名：`kebab-case`
- 普通文件名：`kebab-case`
- 组件文件名：`PascalCase`
- 变量名：`camelCase`
- 函数名：`camelCase`
- 事件处理函数：`handleXxx`
- 布尔变量：`isXxx`、`hasXxx`、`canXxx`
- 常量：`UPPER_CASE`
- 类型、接口、枚举：`PascalCase`
- 自定义 Hook：`useXxx`

### 4.2 语义化要求

命名必须表达真实业务含义，禁止出现以下低信息量命名：

- `data`
- `list`
- `item`
- `info`
- `temp`
- `res`
- `obj`

允许使用上述词汇作为局部上下文的一部分，但必须补足业务语义，例如：

- `userList`
- `menuItem`
- `requestErrorInfo`
- `pageData`

页面模块内的私有组件可以基于当前业务上下文命名，但同一目录下必须保持统一风格。若该组件未来可能被多个页面复用，则命名应补足业务语义，避免脱离目录上下文后难以理解。

### 4.3 事件与动作函数命名

约定如下：

- 用户交互处理函数使用 `handle` 前缀，例如 `handleSubmit`。
- 请求函数使用动词开头，例如 `getUserList`、`updateUserStatus`。
- 格式化函数使用语义动词，例如 `formatUserName`、`buildMenuItems`。
- 判断函数使用 `is`、`has`、`can` 前缀，例如 `hasPermission`。

## 5. 页面与组件开发规范

### 5.1 页面组件规范

页面组件是路由的承接者，应遵循以下原则：

1. 页面组件负责页面级编排，不承载过多通用逻辑。
2. 页面组件内部可以组合业务组件，但不应堆积大量基础工具函数。
3. 页面文件应聚焦页面初始化、状态编排、数据获取与视图组织。
4. 页面私有逻辑优先抽离为同目录下的 `components`、`hooks`、`api`、`store`、`types`。
5. 页面内可复用的片段先在当前页面模块内沉淀，确认跨页面复用后再上移到全局公共目录。

### 5.2 通用组件规范

通用组件应满足以下要求：

1. 组件职责单一，输入输出边界清晰。
2. Props 命名语义化，不暴露与内部实现强耦合的命名。
3. 能通过 Props 控制的行为，不依赖隐式外部状态。
4. 不在通用组件中写死具体业务文案、权限逻辑或接口逻辑。

### 5.3 组件拆分原则

出现以下情况时，应考虑拆分组件：

1. 单个组件承担多个明显不同的业务职责。
2. JSX 结构过长，已经影响阅读和 review。
3. 同一片段在多个页面或多个位置复用。
4. 状态、事件和渲染逻辑已经难以在同一文件中维护。

### 5.4 导出规则

建议如下：

1. 页面主组件使用默认导出。
2. 目录内只有一个主组件时，组件文件使用默认导出。
3. 工具函数、常量、类型定义优先使用命名导出。
4. 避免一个文件同时导出多个职责不同的 React 组件。

## 6. TypeScript 规范

### 6.1 基础约束

以下规则为强制要求：

1. 禁止使用 `any`。
2. 禁止使用 `as` 逃避类型检查。
3. 除 `void` 场景外，函数必须显式声明返回类型。
4. 禁止使用 `eval` 和 `new Function`。

### 6.2 类型设计原则

1. 类型命名必须具备业务语义，不使用模糊命名。
2. 公共类型应抽离复用，避免在多个文件中复制粘贴同样的结构。
3. 当结构描述对象能力时优先考虑 `interface`，当表达联合类型、工具类型或复杂组合类型时使用 `type`。
4. 不通过宽松类型掩盖真实的数据边界问题。

### 6.3 函数与数据边界

1. 所有请求函数必须为入参和返回值定义明确类型。
2. 组件 Props 必须显式定义类型。
3. 状态结构必须具备类型定义，尤其是全局状态和接口返回数据。
4. 不把后端返回结果直接透传到页面，必要时进行结构整理和字段收敛。

### 6.4 推荐写法

```ts
interface UserInfo {
  id: string;
  username: string;
  avatar: string;
}

interface GetUserListParams {
  keyword?: string;
}

function formatUserName(username: string): string {
  return username.trim();
}
```

### 6.5 不推荐写法

```ts
function formatUserName(username: any) {
  return (username as string).trim();
}
```

## 7. 样式规范

### 7.1 基本原则

1. 组件样式优先使用 `CSS Modules`。
2. 样式文件与组件或页面就近放置。
3. 样式命名应体现结构或语义，避免无意义缩写。
4. 尽量避免直接写大量内联样式。

### 7.2 样式文件命名

统一使用：

- `index.module.css`
- 或使用具备业务语义的 `kebab-case.module.css`

示例：

- `index.module.css`
- `user-manage.module.css`
- `user-card.module.css`

约束如下：

1. 推荐优先使用 `index.module.css`，便于页面模块和组件目录内就近维护。
2. 若不使用 `index.module.css`，则样式文件名必须采用具备业务语义的 `kebab-case.module.css`。
3. 不使用与 `PascalCase` 组件文件完全同名的样式文件，例如 `UserManage.module.css`。

### 7.3 样式边界

1. 全局样式仅用于重置、主题级基础能力和全局通用规则。
2. 页面私有样式不得泄漏到其他模块。
3. 不允许通过过深选择器或覆盖第三方样式来堆积技术债。
4. 样式调整优先通过结构和类名解决，而不是依赖 `!important`。

## 8. 接口请求与数据处理规范

### 8.1 请求入口

项目请求应统一通过基础请求封装发起，例如 `src/utils/request.ts`。

强制要求如下：

1. 页面和组件中不直接创建新的请求实例。
2. 不在多个文件中重复实现相同的鉴权、超时、错误提示逻辑。
3. 不在页面 JSX 附近直接堆积请求细节。
4. 页面模块可以维护自己的业务接口文件，但底层统一复用全局请求封装。

### 8.2 请求组织原则

接口组织采用“页面私有优先、跨页面上移”的原则，例如：

```text
src/
  pages/
    user-manage/
      api/
        user-manage-api.ts
  api/
    auth-api.ts
    user-api.ts
```

规则如下：

1. 接口定义与页面展示解耦。
2. 只服务当前页面的接口，优先放在对应页面目录内维护。
3. 请求参数类型、响应类型和请求函数放在同一业务域内维护。
4. 页面只调用业务接口函数，不直接处理底层请求细节。
5. 当接口被两个及以上页面复用时，再上移到全局 `src/api`。

### 8.3 错误处理原则

1. 通用错误交给请求层统一处理。
2. 页面只处理当前页面确实需要感知的业务异常。
3. 不重复弹出同一类错误提示。
4. 异常分支必须能被用户理解和恢复。

### 8.4 数据处理原则

1. 接口原始数据进入页面前，必要时做格式整理。
2. 避免在 JSX 中写复杂的数据转换表达式。
3. 列表页必须考虑加载态、空态和异常态。
4. 涉及权限、登录态、关键业务状态时，必须明确边界处理。

## 9. 状态管理规范

本项目当前使用 `Zustand`，规范只定义原则，不约束复杂设计模式。

### 9.1 使用边界

1. 只在多个页面或多个模块共享时使用全局状态。
2. 当前页面独占但需要在页面内多个子组件共享的状态，可以放在页面模块自己的局部 store 中。
3. 页面内部一次性状态优先放在组件内部，而不是放进全局 store。
4. 与 URL 强相关的状态优先通过路由参数或查询参数表达。
5. 与视图局部交互强相关的状态不进入全局状态。

### 9.2 Store 设计原则

1. 一个 store 应聚焦一个明确领域。
2. 全局 store 只保留跨页面共享的数据和动作，页面私有状态优先保留在页面模块内部。
3. action 命名必须体现业务动作，例如 `setUserInfo`、`clearUserInfo`。
4. 不把临时计算结果、展示用中间值长期保存在 store 中。

## 10. 路由与页面组织规范

1. 路由文件负责页面映射和基础跳转，不堆积页面业务逻辑。
2. 页面目录名采用 `kebab-case`，页面主组件文件采用 `PascalCase`。
3. 路由 path 使用小写语义化路径，例如 `page-b`、`user-manage`。
4. 兜底路由、权限路由和重定向逻辑必须集中管理，避免分散在多个页面内。

## 11. 代码质量与自检要求

提交前至少完成以下自检：

1. 代码能通过 TypeScript 类型检查。
2. 代码能通过 ESLint 检查。
3. 不包含调试代码、无用注释、无用依赖和无用导入。
4. 不新增明显重复代码。
5. 新增逻辑与现有目录职责、命名规范保持一致。
6. 修改请求、状态、路由时，确认未破坏既有行为边界。

自检重点：

- 是否引入了 `any`。
- 是否通过 `as` 粗暴绕过类型问题。
- 是否在页面中堆积请求和转换逻辑。
- 是否出现职责不清的组件和文件。

## 12. Git 与 PR 协作规范

### 12.1 分支命名建议

建议使用以下格式：

- `feat/xxx`
- `fix/xxx`
- `refactor/xxx`
- `docs/xxx`
- `chore/xxx`

示例：

- `feat/user-manage-page`
- `fix/login-timeout-handle`
- `docs/frontend-development-spec`

### 12.2 Commit Message 规范

提交信息建议采用 Conventional Commits：

```text
type(scope): subject
```

常用类型：

- `feat`：新增功能
- `fix`：修复问题
- `refactor`：重构
- `style`：不影响逻辑的格式或样式调整
- `docs`：文档修改
- `test`：测试相关
- `chore`：构建、依赖、配置等杂项调整

示例：

```text
feat(user): add user info dropdown
fix(request): handle 401 logout flow
refactor(layout): split sider and header components
docs(spec): add frontend development specification
```

要求如下：

1. 提交信息必须能说明本次变更做了什么。
2. 不使用 `update`、`modify`、`fix bug` 这类低信息量描述。
3. 一个 commit 应只做一类相对独立的改动。

### 12.3 PR 模板要求

每个 PR 至少应包含以下信息：

1. 变更背景：为什么做这次修改。
2. 变更内容：改了哪些核心点。
3. 影响范围：页面、组件、接口、状态、路由、样式等。
4. 自检结果：已完成的检查项。
5. 风险说明：可能影响的边界和回滚关注点。

推荐 PR 模板：

```md
## 背景

说明本次修改的业务背景或问题来源。

## 变更内容

- 变更点 1
- 变更点 2

## 影响范围

- 页面：
- 组件：
- 接口：
- 状态：
- 路由：

## 自检

- [ ] 已检查命名与目录规范
- [ ] 已检查类型定义与返回值
- [ ] 已检查请求与异常处理
- [ ] 已检查无调试代码和无用代码

## 风险与备注

说明已知风险、依赖条件或后续事项。
```

## 13. 附录：推荐与反例

### 13.1 推荐目录示例

```text
src/
  components/
    user-card/
      UserCard.tsx
      index.module.css
  pages/
    user-manage/
      components/
        UserManageSearchForm.tsx
        UserManageTable.tsx
      hooks/
        use-user-manage-columns.ts
      api/
        user-manage-api.ts
      store/
        use-user-manage-store.ts
      types/
        user-manage.ts
      constants/
        user-manage-constants.ts
      UserManage.tsx
      index.module.css
  api/
    auth-api.ts
  store/
    user-store.ts
```

### 13.2 标准页面模块模板

新增页面模块时，推荐以如下目录作为默认模板：

```text
src/
  pages/
    xxx-page/
      components/
        XxxPageSearchForm.tsx
        XxxPageTable.tsx
      hooks/
        use-xxx-page-columns.ts
      api/
        xxx-page-api.ts
      store/
        use-xxx-page-store.ts
      types/
        xxx-page.ts
      constants/
        xxx-page-constants.ts
      XxxPage.tsx
      index.module.css
```

目录说明：

- `XxxPage.tsx`：页面主组件，负责页面编排、数据请求入口、状态组合与视图组织。
- `components/`：当前页面私有组件，只服务当前页面。
- `hooks/`：当前页面私有 Hook，封装列表列配置、表单逻辑、页面交互逻辑等。
- `api/`：当前页面私有接口函数，底层统一复用全局请求封装。
- `store/`：当前页面私有局部状态，仅在页面内多个组件共享时使用。
- `types/`：当前页面私有类型定义。
- `constants/`：当前页面私有常量、枚举映射或配置项。
- `index.module.css`：页面主样式文件。

使用规则：

1. `XxxPage.tsx` 和 `index.module.css` 为默认必选项。
2. `components/`、`api/`、`types/` 为常用目录，复杂页面默认建议建立。
3. `hooks/`、`store/`、`constants/` 为按需目录，没有对应职责时可以不创建。
4. 页面目录内只放当前页面私有内容，跨页面复用能力必须上移到全局目录。
5. 页面模块内命名保持统一，目录使用 `kebab-case`，组件文件使用 `PascalCase`。

精简版模板：

适用于简单页面或纯展示页面：

```text
src/
  pages/
    xxx-page/
      XxxPage.tsx
      index.module.css
```

扩展规则：

1. 当页面开始出现私有交互组件时，新增 `components/`。
2. 当页面出现独立请求逻辑时，新增 `api/` 和 `types/`。
3. 当页面内多个组件共享状态时，再新增 `store/`。
4. 当页面逻辑开始复用或变复杂时，再新增 `hooks/` 和 `constants/`。

### 13.3 不推荐示例

不推荐以下情况：

1. 目录名和组件名混用大小写规则。
2. 页面文件直接编写请求实例和鉴权逻辑。
3. 使用 `any` 和 `as` 掩盖类型问题。
4. 明明只在单个页面使用，却过早抽成全局 `api`、`store` 或 `components`。
5. 全局状态承载页面临时交互状态。
6. 组件既负责请求、状态编排，又负责大段视图渲染，职责过重。

## 14. 执行与演进

本规范为 `v1`，优先解决当前项目中最容易产生不一致和技术债的问题。

执行建议如下：

1. 新增代码必须遵守本规范。
2. 旧代码不强制一次性全部重构，但新增修改时应逐步向规范靠拢。
3. 能通过工具自动校验的规则，后续逐步下沉到 `ESLint`、`TypeScript` 和 PR 检查中。
4. 规范每隔一段时间结合实际协作问题进行修订，而不是长期停留在纸面。
