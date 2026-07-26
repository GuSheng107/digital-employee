# 项目文档索引

这里是数字员工数据中台的文档入口。

推荐阅读：

1. `../README.md`：项目定位、启动方式和接口清单。
2. `operations.md`：Linux 启停脚本、日志和故障排查。
3. `cloudbeaver-structure-management.md`：数据库结构管理边界。
4. `integration-with-digital-employee.md`：与数字员工主项目的集成方式。

核心原则：

- 数据中台只连接已有数据库和已有表。
- 数据库结构由 CloudBeaver Community 管理。
- 数据中台不提供 DDL、建表页面或任意 SQL 执行能力。
- PostgreSQL 必须使用受限业务账号。
