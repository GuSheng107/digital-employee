# DDL 安全说明

DDL 建表工具涉及数据库结构变更，必须按“默认关闭、最小权限、后端生成 SQL”的原则设计和使用。

## 账号隔离

系统至少区分两类数据库账号：

- APP 业务账号：用于普通业务接口读写。
- DDL 专用账号：只用于受控建表。

禁止：

- 使用 PostgreSQL 管理员账号执行 DDL。
- 复用 APP 业务账号执行 DDL。
- 给 DDL 账号授予 `SUPERUSER`、`CREATEDB`、`CREATEROLE`、`BYPASSRLS`。
- 给 DDL 账号授予不必要的数据库所有权。

建议：

- DDL 账号只授予目标数据库连接权限。
- DDL 账号只授予白名单 schema 的 `USAGE` 和 `CREATE` 权限。
- DDL 账号只用于开发、测试或受控环境。

## 配置项

必需配置：

```env
APP_ENV=local
DDL_DATABASE_URL=postgresql+psycopg2://ddl_user:your_password@127.0.0.1:5432/digital_employee_core?sslmode=disable
DDL_ALLOWED_DATABASE=digital_employee_core
DDL_ALLOWED_SCHEMAS=public
DDL_EXECUTION_ENABLED=false
```

说明：

- 不要提交真实密码。
- 不要提交生产连接串。
- `DDL_EXECUTION_ENABLED` 默认必须为 `false`。
- 生产环境即使误开开关，也会因为 `APP_ENV` 不允许而拒绝执行。

## 生产保护

执行接口只允许以下环境：

- `local`
- `dev`
- `test`

其他环境统一拒绝执行。

如果 `APP_ENV=prod`、`production` 或未识别值，执行接口会失败关闭。

## SQL 注入防护

本工具不提供自由 SQL 输入框。

防护措施：

- 前端只提交结构化 JSON。
- 执行接口不接受 SQL 文本。
- 后端重新校验结构化参数。
- 后端重新生成 DDL。
- schema、表名、字段名使用正则校验。
- 字段类型来自后端白名单。
- 默认值按字段类型校验。
- 注释使用 SQL 字面量转义。
- 标识符生成时统一加双引号。

## 执行前检查

执行建表前，后端会检查：

- 当前环境是否允许执行。
- DDL 执行开关是否开启。
- `DDL_DATABASE_URL` 是否存在。
- URL 中的数据库名是否等于 `DDL_ALLOWED_DATABASE`。
- schema 是否在 `DDL_ALLOWED_SCHEMAS` 内。
- 目标表是否已经存在。

## 审计日志

执行接口会记录必要审计信息：

- 事件名称。
- 当前环境。
- 目标数据库标识。
- schema。
- table。
- 客户端 IP。
- 执行结果。
- 耗时。
- 简短错误类型。

日志中不应出现：

- 数据库密码。
- token。
- 完整带密码连接串。
- 其他敏感凭据。
