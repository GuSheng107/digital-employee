# Development Mode

用于新增页面、组件、接口、状态管理或目录结构时的详细规则。

## 适用场景

当用户表达以下意图时使用本模式：

- 新增页面模块
- 新增组件
- 新增接口文件
- 新增页面私有 store
- 设计新目录结构
- 想要标准页面模块模板

## 必做判断

1. 当前任务属于页面、组件、接口、store、hook、样式中的哪一类
2. 该能力是页面私有能力还是跨页面共享能力
3. 当前页面是简单页面还是复杂页面
4. 是否需要模板，若需要，应选择 minimal 还是 full

## 边界判断

### 页面私有能力

满足以下条件时，优先留在页面目录：

1. 只服务当前页面
2. 与当前页面业务字段强耦合
3. 尚未在两个及以上页面复用

常见落点：

- `components/`
- `api/`
- `types/`
- `hooks/`
- `store/`
- `constants/`

### 全局公共能力

满足以下条件时，才建议上移到全局：

1. 两个及以上页面复用
2. 已抽象出稳定接口
3. 不再绑定单页业务语义

常见落点：

- `src/components`
- `src/api`
- `src/store`
- `src/hooks`
- `src/types`
- `src/utils`

## 模板选择

### 选择 `page-module-minimal`

满足以下任一情况时，优先用 minimal：

1. 普通页面或简单列表页
2. 不需要局部 Zustand
3. 状态主要由页面本地 `useState` 控制
4. 不需要额外 hooks/constants 拆分
5. 页面还不需要独立 `api/`、`types/` 目录即可起步

### 选择 `page-module-full`

满足以下任一情况时，优先用 full：

1. 页面逻辑较重
2. 需要局部 store 编排
3. 列表列定义、常量、查询状态需要独立拆分
4. 页面目录下会有明显的局部模块协作

## 推荐输出结构

开发模式输出至少包含：

1. 需求理解
2. 推荐目录结构
3. 命名建议
4. 页面私有 / 全局公共边界判断
5. 模板选择
6. 注意事项
7. 自检清单

## 注意事项

1. 请求统一复用 `frontend/src/utils/request.ts`
2. 样式优先 `CSS Modules`
3. 禁止使用 `any`
4. 禁止使用 `as` 逃避类型检查
5. 函数返回值按仓库规范显式声明类型
6. 不为了“看起来规范”而强行增加 `store/`、`hooks/`、`constants/`
7. 新增代码不要沿用 `PageA`、`Layout` 这类历史命名
8. 样式文件优先使用 `index.module.css`，不要使用 `PascalCase.module.css`
9. 列表页方案至少要考虑加载态、空态和异常态

## 模板引用契约

### 当用户要“标准页面模块模板”

1. 先判断页面复杂度
2. 再读取：
   - `templates/page-module-minimal/README.md` 或
   - `templates/page-module-full/README.md`
3. 输出中明确说明：
   - 为什么选这个模板
   - 哪些目录是必选
   - 哪些目录是按需建立
   - 如果是 minimal，默认先从 `XxxPage.tsx + index.module.css` 起步，`api/`、`types/` 在出现独立请求逻辑时再补
