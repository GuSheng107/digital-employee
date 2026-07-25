# Alembic

当前最小版本默认通过 `AUTO_CREATE_TABLES=true` 初始化 `data_items` 表。

后续进入正式迭代时，建议在这里接入 Alembic 迁移脚本，并关闭自动建表。
