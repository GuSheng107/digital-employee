# DDL 建表工具总览

本目录记录“PostgreSQL 16 可视化建表工具”的设计、接口、安全策略、测试方式和后续集成方式。

当前阶段只实现 `CREATE TABLE`，用于让开发或运维人员通过结构化表单生成 PostgreSQL 16 建表语句，并在安全开关开启后由后端受控执行。

## 当前支持范围

已实现：

- 根据结构化表定义生成 `CREATE TABLE` SQL。
- 预览接口不连接数据库，没有副作用。
- 执行接口重新校验结构化参数，并由后端重新生成 SQL。
- 支持表注释和字段注释。
- 支持字段类型、长度、精度、小数位、是否可空、主键、默认值。
- 使用独立 DDL 数据库连接。
- 前端提供最小可用的可视化建表页面。

未实现：

- 自由 SQL 编辑器。
- `ALTER TABLE`。
- `DROP TABLE`。
- `TRUNCATE`。
- `DELETE`。
- `CREATE DATABASE`。
- 创建 schema。
- 生产环境 DDL 执行。

## 架构流程

```text
前端 DDL 建表页面
  -> 后端 DDL Router
  -> DdlService
  -> ddl_generator 生成 SQL
  -> 如果执行开关开启，再通过 DDL 专用数据库连接执行
```

## 相关文件

后端：

- `backend/app/api/routes/ddl.py`
- `backend/app/schemas/ddl.py`
- `backend/app/services/ddl_generator.py`
- `backend/app/services/ddl_service.py`
- `backend/app/core/config.py`
- `backend/app/core/database.py`

前端：

- `frontend/src/api/ddl.ts`
- `frontend/src/views/DdlTables.vue`
- `frontend/src/App.vue`

文档：

- `docs/ddl-tool/api.md`
- `docs/ddl-tool/security.md`
- `docs/ddl-tool/testing.md`
- `docs/ddl-tool/integration-guide.md`
- `docs/ddl-tool/postgresql-role-example.sql`

## 启动方式

后端：

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

前端：

```bash
cd frontend
npm run dev
```

访问：

- Swagger：`http://127.0.0.1:8000/docs`
- 前端页面：`http://127.0.0.1:5174`

## 环境变量

DDL 工具使用以下配置：

```env
DDL_DATABASE_URL=postgresql+psycopg2://ddl_user:your_password@127.0.0.1:5432/digital_employee_core?sslmode=disable
DDL_ALLOWED_DATABASE=digital_employee_core
DDL_ALLOWED_SCHEMAS=public
DDL_EXECUTION_ENABLED=false
APP_ENV=local
```

说明：

- `DDL_DATABASE_URL`：DDL 专用账号连接串。
- `DDL_ALLOWED_DATABASE`：允许执行 DDL 的数据库名。
- `DDL_ALLOWED_SCHEMAS`：允许执行 DDL 的 schema 白名单，多个值用英文逗号分隔。
- `DDL_EXECUTION_ENABLED`：是否允许执行 DDL，默认必须是 `false`。
- `APP_ENV`：只有 `local`、`dev`、`test` 允许执行。

## 最重要的安全原则

- 前端只提交结构化 JSON，不提交 SQL。
- 后端不执行前端传来的 SQL。
- 后端会重新校验字段和表定义，然后重新生成 DDL。
- 执行默认关闭。
- 生产环境拒绝执行。
- DDL 账号必须是独立账号，只授予必要权限。

## 当前测试状态

已完成：

- 单元测试。
- DDL 预览接口真实 HTTP 验证。
- 默认禁止执行验证。
- 前端构建验证。

未完成：

- 真实 PostgreSQL 建表集成测试。

原因：

- 需要提供独立 DDL-only PostgreSQL 测试账号。

当前状态标记为：`BLOCKED_EXTERNAL_CREDENTIAL`。
