# DDL 工具集成指南

本文档说明如果后续要把 DDL 建表工具迁移或集成到其他数字员工主项目中，需要保留哪些设计约束，以及哪些文件可以复用。

## 集成目标

目标是在主项目中提供同样的能力：

- 用户通过页面填写表结构。
- 后端根据结构化参数生成 PostgreSQL 16 `CREATE TABLE`。
- 预览不连接数据库。
- 执行时后端重新校验并重新生成 SQL。
- 执行只允许在开发或测试环境开启。
- 使用独立 DDL 数据库账号。

## 依赖要求

后端：

- FastAPI 或等价 Web 框架。
- Pydantic 或等价参数校验能力。
- SQLAlchemy 或等价数据库连接能力。
- psycopg2-binary。
- 日志组件。

前端：

- Vue 3。
- Element Plus。
- Axios 或项目内统一请求封装。

## 配置契约

建议保持以下语义配置名，即使主项目使用 Nacos 或其他配置中心，也建议映射到同名语义：

```env
APP_ENV=local|dev|test|prod
DDL_DATABASE_URL=<ddl-only connection>
DDL_ALLOWED_DATABASE=<allowed database>
DDL_ALLOWED_SCHEMAS=public
DDL_EXECUTION_ENABLED=false
```

如果使用 Nacos：

- 可以把这些配置放入主项目对应 Data ID。
- 密码建议使用密文或由密钥管理服务注入。
- 业务数据库连接和 DDL 数据库连接必须分开。

## 可以直接迁移的文件

- `backend/app/schemas/ddl.py`
- `backend/app/services/ddl_generator.py`
- `docs/ddl-tool/*`

这些文件相对独立，主要依赖 Pydantic 和标准库。

## 需要适配的文件

- `backend/app/services/ddl_service.py`
- `backend/app/api/routes/ddl.py`
- `backend/app/core/config.py`
- `backend/app/core/database.py`
- `frontend/src/api/ddl.ts`
- `frontend/src/views/DdlTables.vue`
- `frontend/src/App.vue`

原因：

- 主项目可能有自己的登录鉴权。
- 主项目可能有自己的统一响应格式。
- 主项目可能有自己的异常码。
- 主项目可能有自己的数据库连接工厂。
- 主项目可能使用菜单权限或路由权限。

## 主项目适配点

必须确认：

- 用户身份和权限校验。
- 只有指定角色可以使用执行建表功能。
- 统一响应格式。
- 统一异常处理。
- 日志和 traceId。
- 配置读取方式。
- DDL-only 数据库连接池。
- 前端菜单权限。
- 前端路由权限。

## 推荐迁移顺序

1. 迁移 schema 和 DDL 生成器。
2. 添加配置项。
3. 添加 DDL-only 数据库连接工厂。
4. 接入 service 和 route。
5. 接入登录鉴权和权限控制。
6. 接入审计日志和 traceId。
7. 在前端添加页面和菜单。
8. 跑单元测试。
9. 使用 DDL-only 测试账号跑集成测试。

## 回滚方式

如果上线后需要回滚：

1. 删除或禁用 DDL 路由注册。
2. 关闭前端菜单入口。
3. 设置 `DDL_EXECUTION_ENABLED=false`。
4. 如功能完全下线，撤销 DDL 账号权限。

## 冲突检查

集成前要确认：

- 不复用已有自由 SQL 执行器。
- DDL 账号不和 APP 账号共用连接池。
- 生产环境始终拒绝执行。
- 生成 SQL 只来自结构化参数。
- 不允许前端提交 SQL 文本。
- 不允许绕过 schema 白名单。

## 验收矩阵

| 场景 | 预期结果 |
| --- | --- |
| 数据中台独立预览 DDL | 通过 |
| 数据中台使用 DDL 账号执行建表 | 通过 |
| 主项目 API 预览 DDL | 通过 |
| 主项目权限拦截 | 通过 |
| 生产环境执行 DDL | 拒绝 |
| 非白名单 schema | 拒绝 |
| 关闭菜单和路由回滚 | 通过 |
