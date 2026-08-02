-- 用途：为数字员工 Agent 管理功能补充权限点。
-- 影响：向 permissions 表插入 admin:agent:manage 权限码。
-- 执行：由数据库负责人通过 CloudBeaver 在 core 数据库手工执行一次。
-- 幂等：按权限码定位记录，重复执行不会创建重复数据。
-- 依赖：先于菜单创建脚本执行；若菜单 component 引用了此权限码，
--       需要权限码已存在，否则 menu_service._validate_permission_code 会拒绝。

BEGIN;

INSERT INTO permissions (code, name, description, module)
VALUES (
    'admin:agent:manage',
    'Agent管理',
    '管理数字员工 Agent 的生命周期与运行状态',
    'agent'
)
ON CONFLICT (code) DO UPDATE
SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    module = EXCLUDED.module;

COMMIT;
