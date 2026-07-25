# DDL 测试说明

本文档说明 DDL 建表工具当前已经验证的内容，以及真实数据库集成测试需要哪些条件。

## 自动化单元测试

在 `backend` 目录执行：

```bash
python -m pytest tests/test_ddl_generator.py -q
```

当前覆盖：

- 合法 `CREATE TABLE` SQL 生成。
- 非法 schema、表名、字段名拒绝。
- 重复字段拒绝。
- 默认值 SQL 注入拒绝。
- 预览接口逻辑不依赖数据库连接。
- 执行接口默认关闭。

## 前端构建测试

在 `frontend` 目录执行：

```bash
npm run build
```

用于验证：

- Vue 页面语法正确。
- TypeScript 类型检查通过。
- Vite 可以正常打包。

## 手动 API 测试

启动后端：

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

调用预览接口：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ddl/tables/preview \
  -H "Content-Type: application/json" \
  -d @../docs/ddl-tool/examples/create-table-preview.json
```

预期结果：

```json
{
  "success": true,
  "message": "ok",
  "data": {
    "schema_name": "public",
    "table_name": "employee_profile",
    "execution_enabled": false
  }
}
```

调用执行接口：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ddl/tables \
  -H "Content-Type: application/json" \
  -d @../docs/ddl-tool/examples/create-table-preview.json
```

默认预期结果：

```json
{
  "success": false,
  "message": "DDL execution is disabled",
  "data": null
}
```

## 真实数据库集成测试状态

当前状态：`BLOCKED_EXTERNAL_CREDENTIAL`。

原因：

真实执行 `CREATE TABLE` 需要独立 DDL-only PostgreSQL 测试账号。该账号不能是业务账号，也不能是管理员账号。

需要提供：

- PostgreSQL 测试地址和端口。
- 测试数据库名。
- 允许执行的 schema。
- DDL-only 用户名。
- DDL-only 用户密码。
- 确认该用户只拥有必要权限。

## 真实建表测试步骤

准备 `.env`：

```env
APP_ENV=local
DDL_DATABASE_URL=postgresql+psycopg2://ddl_user:your_password@127.0.0.1:5432/digital_employee_core?sslmode=disable
DDL_ALLOWED_DATABASE=digital_employee_core
DDL_ALLOWED_SCHEMAS=public
DDL_EXECUTION_ENABLED=true
```

测试步骤：

1. 使用唯一表名，例如 `ddl_test_20260725_001`。
2. 调用 `/api/v1/ddl/tables/preview` 预览 SQL。
3. 确认 SQL 只包含 `CREATE TABLE` 和 `COMMENT`。
4. 调用 `/api/v1/ddl/tables` 执行。
5. 在 PostgreSQL 中确认表、字段、主键、注释已创建。
6. 再次调用同一请求，确认返回 `table already exists`。
7. 清理测试表前，需要操作人明确确认。

清理 SQL 示例：

```sql
DROP TABLE IF EXISTS public.ddl_test_20260725_001;
```

注意：清理动作不由本工具提供，必须由有权限的测试人员手动执行。
