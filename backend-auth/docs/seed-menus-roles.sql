-- =============================================================================
-- backend-auth 开发种子：超级管理员、规范角色、权限码、系统菜单与关联
-- 执行顺序：schema.sql → seed-menus-roles.sql
-- 幂等：可重复执行；固定菜单 ID 与现有前端路由保持一致。
-- =============================================================================

BEGIN;

-- ── 1. 规范内置角色 ───────────────────────────────────────────────────────
INSERT INTO roles (code, name, description, is_builtin)
VALUES
    ('user', '普通用户', '普通业务用户', TRUE),
    ('manager', '管理员', '通过显式权限码维护用户与系统配置', TRUE),
    ('super_admin', '超级管理员', '系统最高权限身份，不进入通用角色管理', TRUE)
ON CONFLICT (code) DO UPDATE
SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_builtin = TRUE,
    deleted_at = NULL;

-- ── 2. 规范权限目录 ───────────────────────────────────────────────────────
INSERT INTO permissions (code, name, description, module)
VALUES
    ('user:profile:edit', '维护个人资料', '查看并维护当前用户自己的资料', 'user'),
    ('admin:user:manage', '用户管理', '查看、创建、启停用户及重置密码', 'user'),
    ('admin:user:permission', '用户与角色授权', '分配用户角色、菜单与权限', 'access'),
    ('admin:invite_code:manage', '邀请码管理', '查看和创建注册邀请码', 'invite_code'),
    ('admin:menu:manage', '菜单管理', '查看、创建、编辑和删除菜单', 'menu'),
    ('admin:data_platform:dashboard', '数据中台概览', '查看数据中台状态', 'data_platform'),
    ('admin:data_platform:data_items', '数据项管理', '查询和维护数据项', 'data_platform'),
    ('admin:data_platform:config', '数据中台配置', '维护数据中台配置', 'data_platform'),
    ('admin:bot:manage', '机器人管理', '维护机器人接入配置', 'bot')
ON CONFLICT (code) DO UPDATE
SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    module = EXCLUDED.module;

-- ── 3. 超级管理员账号 ─────────────────────────────────────────────────────
-- 开发初始密码：root666。首次部署后应立即通过个人信息页修改。
INSERT INTO users (
    username,
    password_hash,
    nickname,
    status,
    is_vip,
    vip_level,
    vip_expires_at
)
VALUES (
    'admin',
    '$2b$12$jKfbNYofvTMkdwYyZv19YesckVWNLOwxlTgZ2T.JRfuOszbczHe8O',
    '系统管理员',
    1,
    TRUE,
    99,
    NULL
)
ON CONFLICT (username) DO UPDATE
SET
    status = 1,
    is_vip = TRUE,
    vip_level = 99,
    vip_expires_at = NULL,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO user_roles (user_id, role_id)
SELECT user_account.id, role.id
FROM users AS user_account
JOIN roles AS role ON role.code = 'super_admin'
WHERE user_account.username = 'admin'
ON CONFLICT (user_id, role_id) DO NOTHING;

-- ── 4. 系统设置菜单 ───────────────────────────────────────────────────────
INSERT INTO menus (
    id, parent_id, menu_type, title, path, component,
    icon, permission, sort, visible
)
VALUES
    (1000, 0, 1, '系统设置', '/system', NULL,
        'SettingOutlined', NULL, 100, TRUE),
    (1100, 1000, 1, '用户', '/system/user', NULL,
        'UserOutlined', NULL, 10, TRUE),
    (1101, 1100, 2, '个人信息', '/system/user/profile', 'system/user/profile',
        'ProfileOutlined', 'user:profile:edit', 10, TRUE),
    (1102, 1100, 2, '用户管理', '/system/user/register', 'system/user/register',
        'UserAddOutlined', 'admin:user:manage', 20, TRUE),
    (1103, 1100, 2, '用户权限', '/system/user/permission', 'system/user/permission',
        'SafetyOutlined', 'admin:user:permission', 30, TRUE),
    (1104, 1100, 2, '邀请码管理', '/system/user/invite-code', 'system/user/invite-code',
        'GiftOutlined', 'admin:invite_code:manage', 40, TRUE),
    (1200, 1000, 1, '系统', '/system/system', NULL,
        'ToolOutlined', NULL, 50, TRUE),
    (1201, 1200, 2, '菜单管理', '/system/menu', 'system/menu',
        'MenuOutlined', 'admin:menu:manage', 10, TRUE)
ON CONFLICT (id) DO UPDATE
SET
    parent_id = EXCLUDED.parent_id,
    menu_type = EXCLUDED.menu_type,
    title = EXCLUDED.title,
    path = EXCLUDED.path,
    component = EXCLUDED.component,
    icon = EXCLUDED.icon,
    permission = EXCLUDED.permission,
    sort = EXCLUDED.sort,
    visible = EXCLUDED.visible,
    deleted_at = NULL;

SELECT setval(
    pg_get_serial_sequence('menus', 'id'),
    GREATEST((SELECT COALESCE(MAX(id), 1) FROM menus), 1201),
    TRUE
);

-- ── 5. 角色菜单与权限 ─────────────────────────────────────────────────────
INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id
FROM roles AS role
JOIN menus AS menu ON menu.id IN (1000, 1100, 1101)
WHERE role.code = 'user'
  AND menu.deleted_at IS NULL
ON CONFLICT (role_id, menu_id) DO NOTHING;

INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id
FROM roles AS role
CROSS JOIN menus AS menu
WHERE role.code IN ('manager', 'super_admin')
  AND menu.deleted_at IS NULL
ON CONFLICT (role_id, menu_id) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT role.id, permission.id
FROM roles AS role
JOIN permissions AS permission
    ON permission.code = 'user:profile:edit'
WHERE role.code = 'user'
ON CONFLICT (role_id, permission_id) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT role.id, permission.id
FROM roles AS role
CROSS JOIN permissions AS permission
WHERE role.code IN ('manager', 'super_admin')
ON CONFLICT (role_id, permission_id) DO NOTHING;

COMMIT;

-- 核验：
-- SELECT code, name FROM roles WHERE deleted_at IS NULL ORDER BY id;
-- SELECT code, name, module FROM permissions ORDER BY module, code;
-- SELECT id, parent_id, title, path, permission
-- FROM menus WHERE deleted_at IS NULL ORDER BY parent_id, sort, id;
