# Preflight

本文件用于 `frontend-dev-spec` 激活后的最小预检。

## 必查文件

依次确认以下文件是否存在：

1. `frontend/docs/frontend-development-spec.md`
2. `frontend/README.md`
3. `frontend/package.json`
4. `frontend/eslint.config.js`
5. `frontend/tsconfig.json`

## 读取顺序

1. 优先读取 `frontend/docs/frontend-development-spec.md`
2. 再读取 `frontend/README.md`
3. 再读取 `frontend/package.json`、`frontend/eslint.config.js`、`frontend/tsconfig.json`
4. 最后读取 `frontend/src` 下的代表性页面、组件、请求、store、路由文件

## 降级策略

### 缺少规范文档

如果 `frontend/docs/frontend-development-spec.md` 不存在：

1. 回退到 `frontend/README.md`
2. 再结合 `frontend/package.json`、`frontend/eslint.config.js`、`frontend/tsconfig.json`
3. 再从 `frontend/src` 的现有代码模式提炼规则
4. 在回答中明确说明：
   - 规范主文档缺失
   - 当前结论主要基于 README、配置文件和现有代码

### 缺少 README

如果 `frontend/README.md` 不存在：

1. 继续使用规范文档和配置文件
2. 在回答中标明项目说明来源收缩

### 缺少配置文件

如果 `frontend/package.json`、`frontend/eslint.config.js`、`frontend/tsconfig.json` 中有缺失：

1. 只按已知规则输出
2. 不自行假设 lint 规则、构建脚本或 TS 编译约束
3. 若相关结论依赖缺失配置，需在回答中显式标注“无法确认”

## 代表性路径

在当前仓库中，预检完成后可优先参考以下路径：

- `frontend/src/router.tsx`
- `frontend/src/utils/request.ts`
- `frontend/src/store/user.ts`
- `frontend/src/components/Layout/index.tsx`
- `frontend/src/pages/PageA/index.tsx`
- `frontend/src/pages/PageB/index.tsx`

## 输出要求

预检阶段本身不需要长篇输出，但后续回答必须做到：

1. 规则来源可解释
2. 缺失项有降级说明
3. 不用未知配置替代事实
