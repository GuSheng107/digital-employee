-- data_items 结构初始化脚本
--
-- 执行边界：由数据库负责人通过 CloudBeaver 审核并执行；backend-data
-- 服务本身不会在启动时自动建表或执行 DDL。

CREATE TABLE IF NOT EXISTS data_items (
    id UUID PRIMARY KEY,
    namespace VARCHAR(100) NOT NULL,
    item_key VARCHAR(200) NOT NULL,
    item_value JSONB NOT NULL DEFAULT '{}'::JSONB,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_data_items_namespace
    ON data_items (namespace);

CREATE INDEX IF NOT EXISTS ix_data_items_item_key
    ON data_items (item_key);

CREATE INDEX IF NOT EXISTS ix_data_items_deleted_at
    ON data_items (deleted_at);
