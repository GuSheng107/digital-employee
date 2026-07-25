# DDL API 文档

DDL 工具提供两组路径：

- 项目标准路径：`/api/v1/ddl/tables/preview`、`/api/v1/ddl/tables`
- 兼容路径：`/api/ddl/tables/preview`、`/api/ddl/tables`

推荐新代码使用 `/api/v1` 路径。

## 预览 DDL

`POST /api/v1/ddl/tables/preview`

作用：

- 校验结构化表定义。
- 生成 PostgreSQL 16 `CREATE TABLE` SQL。
- 不连接数据库。
- 不产生任何副作用。

请求示例：

```json
{
  "schema_name": "public",
  "table_name": "employee_profile",
  "table_comment": "employee profile table",
  "columns": [
    {
      "name": "id",
      "type": "uuid",
      "nullable": false,
      "primary_key": true,
      "default": "gen_random_uuid()",
      "comment": "primary key"
    },
    {
      "name": "name",
      "type": "varchar",
      "length": 100,
      "nullable": false,
      "primary_key": false,
      "default": "unknown",
      "comment": "display name"
    }
  ]
}
```

响应示例：

```json
{
  "success": true,
  "message": "ok",
  "data": {
    "schema_name": "public",
    "table_name": "employee_profile",
    "table_identifier": "\"public\".\"employee_profile\"",
    "ddl": "CREATE TABLE ...",
    "execution_enabled": false
  }
}
```

## 执行建表

`POST /api/v1/ddl/tables`

作用：

- 接收结构化表定义。
- 重新校验参数。
- 重新生成 DDL。
- 检查目标表是否已经存在。
- 在安全条件满足时执行 `CREATE TABLE`。

注意：

- 这个接口不接收 SQL 字符串。
- 即使前端已经预览过，执行时后端仍然会重新生成 SQL。
- 执行默认关闭。

允许执行的条件：

- `APP_ENV` 必须是 `local`、`dev` 或 `test`。
- `DDL_EXECUTION_ENABLED=true`。
- `DDL_DATABASE_URL` 已配置。
- `DDL_DATABASE_URL` 中的数据库名等于 `DDL_ALLOWED_DATABASE`。
- `schema_name` 在 `DDL_ALLOWED_SCHEMAS` 白名单内。

错误示例：

```json
{
  "success": false,
  "message": "DDL execution is disabled",
  "data": null
}
```

```json
{
  "success": false,
  "message": "table already exists",
  "data": null
}
```

## 字段规则

### 标识符规则

以下字段必须符合正则：

```text
^[A-Za-z_][A-Za-z0-9_]{0,62}$
```

适用字段：

- `schema_name`
- `table_name`
- column `name`

### 支持的字段类型

- `smallint`
- `integer`
- `bigint`
- `numeric`
- `boolean`
- `varchar`
- `text`
- `date`
- `timestamp`
- `timestamptz`
- `json`
- `jsonb`
- `uuid`

### 长度和精度

- `varchar.length`：`1..10000`
- `numeric.precision`：`1..1000`
- `numeric.scale`：`0..precision`
- 其他类型不能传 `length`、`precision`、`scale`

### 默认值规则

- 整数类型只接受整数。
- `numeric` 只接受数字。
- `boolean` 只接受布尔值。
- `varchar` 和 `text` 接受字符串字面量。
- `uuid` 接受 UUID 字符串，或 `gen_random_uuid()`、`uuid_generate_v4()`。
- `timestamp` 和 `timestamptz` 接受 ISO 时间字符串，或 `now()`、`current_timestamp`。
- `date` 接受 ISO 日期字符串，或 `current_date`。
- `json` 和 `jsonb` 接受合法 JSON 值。

## 最小请求示例

```json
{
  "schema_name": "public",
  "table_name": "demo_table",
  "table_comment": "demo table",
  "columns": [
    {
      "name": "id",
      "type": "uuid",
      "nullable": false,
      "primary_key": true,
      "default": "gen_random_uuid()",
      "comment": "primary key"
    }
  ]
}
```
