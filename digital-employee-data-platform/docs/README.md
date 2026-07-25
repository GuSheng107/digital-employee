# 项目文档索引

这里是数字员工数据中台的项目文档入口，方便团队成员快速了解项目、启动服务、使用接口和查看 DDL 建表工具说明。

## 推荐阅读顺序

1. 先看根目录 `README.md`，了解项目定位、启动方式和整体接口。
2. 再看 `backend/README.md`，了解后端结构、配置项和测试命令。
3. 如果要使用可视化建表能力，再看 `docs/ddl-tool/README.md`。

## DDL 建表工具文档

- `docs/ddl-tool/README.md`：DDL 工具总览。
- `docs/ddl-tool/api.md`：接口说明和请求示例。
- `docs/ddl-tool/security.md`：安全边界、账号隔离和执行限制。
- `docs/ddl-tool/testing.md`：单元测试、前端构建测试和真实数据库集成测试说明。
- `docs/ddl-tool/integration-guide.md`：后续迁移到主项目或其他项目的集成指南。
- `docs/ddl-tool/postgresql-role-example.sql`：PostgreSQL DDL-only 账号授权示例。

## 当前重点结论

- DDL 预览接口不连接数据库。
- DDL 执行接口默认关闭。
- 执行接口不接受 SQL 字符串，只接受结构化表定义。
- 后端会重新校验结构化参数并重新生成 SQL。
- 真实建表需要独立 DDL-only PostgreSQL 账号。
- 生产环境不允许执行 DDL。
