-- =============================================================================
-- backend-auth 种子数据：管理员用户 / 角色 / 权限 / 菜单 / 关联
-- 库: db_data  (app_usr 需有该库的 DML 权限)
-- 幂等: 可重复执行，基于 username / code / id 判断是否存在
-- 执行顺序: schema.sql → seed-menus-roles.sql
-- =============================================================================

-- ── 0. 管理员用户（admin / root666，vip_level=99 永不过期） ──────────────────
-- password_hash 由 bcrypt(gensalt(12)) 生成，对应明文 'root666'
-- 生产环境请立即通过个人信息页修改密码
INSERT INTO users (
    username, password_hash, nickname, status,
    is_vip, vip_level, vip_expires_at
)
SELECT
    'admin',
    '$2b$12$jKfbNYofvTMkdwYyZv19YesckVWNLOwxlTgZ2T.JRfuOszbczHe8O',
    '系统管理员',
    1,
    TRUE,
    99,
    NULL   -- NULL=永久
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin');

-- ── 1. 角色 ────────────────────────────────────────────────────────────────
-- viewer 角色（普通用户，仅可见个人信息）
INSERT INTO roles (code, name, description, is_builtin)
SELECT 'viewer', '普通用户', '仅可查看个人信息', TRUE
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE code = 'viewer');

-- 确认 admin 角色存在（与 admin 用户配套）
INSERT INTO roles (code, name, description, is_builtin)
SELECT 'admin', '管理员', '系统管理员，拥有全部权限', TRUE
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE code = 'admin');

-- 确保 admin 用户(id=1) 关联 admin 角色
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.username = 'admin' AND r.code = 'admin'
  AND NOT EXISTS (
    SELECT 1 FROM user_roles ur WHERE ur.user_id = u.id AND ur.role_id = r.id
  );


-- ── 2. 权限点 ───────────────────────────────────────────────────────────────
INSERT INTO permissions (code, name, description, module)
SELECT 'user:read', '查看用户', '查看用户列表与详情', 'user'
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'user:read');

INSERT INTO permissions (code, name, description, module)
SELECT 'user:write', '管理用户', '创建/编辑用户', 'user'
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'user:write');

INSERT INTO permissions (code, name, description, module)
SELECT 'role:read', '查看角色', '查看角色列表', 'role'
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'role:read');

INSERT INTO permissions (code, name, description, module)
SELECT 'role:write', '管理角色', '分配角色与菜单权限', 'role'
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'role:write');

INSERT INTO permissions (code, name, description, module)
SELECT 'invite_code:read', '查看邀请码', '查看邀请码列表', 'invite_code'
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'invite_code:read');

INSERT INTO permissions (code, name, description, module)
SELECT 'invite_code:write', '创建邀请码', '创建新的邀请码', 'invite_code'
WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = 'invite_code:write');


-- ── 3. 菜单（三级层级） ───────────────────────────────────────────────────────
-- 一级目录：系统设置
INSERT INTO menus (id, parent_id, menu_type, title, path, component, icon, permission, sort, visible)
SELECT 1000, 0, 1, '系统设置', '/system', NULL, 'SettingOutlined', NULL, 100, TRUE
WHERE NOT EXISTS (SELECT 1 FROM menus WHERE id = 1000);

-- 二级目录：用户
INSERT INTO menus (id, parent_id, menu_type, title, path, component, icon, permission, sort, visible)
SELECT 1100, 1000, 1, '用户', '/system/user', NULL, 'UserOutlined', NULL, 10, TRUE
WHERE NOT EXISTS (SELECT 1 FROM menus WHERE id = 1100);

-- 三级菜单：个人信息
INSERT INTO menus (id, parent_id, menu_type, title, path, component, icon, permission, sort, visible)
SELECT 1101, 1100, 2, '个人信息', '/system/user/profile', 'system/user/profile', 'ProfileOutlined', NULL, 10, TRUE
WHERE NOT EXISTS (SELECT 1 FROM menus WHERE id = 1101);

-- 三级菜单：用户注册
INSERT INTO menus (id, parent_id, menu_type, title, path, component, icon, permission, sort, visible)
SELECT 1102, 1100, 2, '用户注册', '/system/user/register', 'system/user/register', 'UserAddOutlined', 'user:write', 20, TRUE
WHERE NOT EXISTS (SELECT 1 FROM menus WHERE id = 1102);

-- 三级菜单：用户权限
INSERT INTO menus (id, parent_id, menu_type, title, path, component, icon, permission, sort, visible)
SELECT 1103, 1100, 2, '用户权限', '/system/user/permission', 'system/user/permission', 'SafetyOutlined', 'role:write', 30, TRUE
WHERE NOT EXISTS (SELECT 1 FROM menus WHERE id = 1103);

-- 三级菜单：邀请码
INSERT INTO menus (id, parent_id, menu_type, title, path, component, icon, permission, sort, visible)
SELECT 1104, 1100, 2, '邀请码', '/system/user/invite-code', 'system/user/invite-code', 'GiftOutlined', 'invite_code:write', 40, TRUE
WHERE NOT EXISTS (SELECT 1 FROM menus WHERE id = 1104);

-- 重置序列，避免后续自增 id 与固定 id 冲突
SELECT setval(pg_get_serial_sequence('menus', 'id'),
  GREATEST((SELECT MAX(id) FROM menus), 1000), true);


-- ── 4. 角色-菜单关联 ────────────────────────────────────────────────────────
-- admin 关联所有菜单（系统设置层级 + 数据中台等已有菜单）
INSERT INTO role_menus (role_id, menu_id)
SELECT r.id, m.id
FROM roles r, menus m
WHERE r.code = 'admin'
  AND m.deleted_at IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM role_menus rm WHERE rm.role_id = r.id AND rm.menu_id = m.id
  );

-- viewer 关联个人信息菜单
INSERT INTO role_menus (role_id, menu_id)
SELECT r.id, m.id
FROM roles r, menus m
WHERE r.code = 'viewer' AND m.id = 1101
  AND NOT EXISTS (
    SELECT 1 FROM role_menus rm WHERE rm.role_id = r.id AND rm.menu_id = m.id
  );


-- ── 5. 角色-权限关联 ────────────────────────────────────────────────────────
-- admin 关联所有权限
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.code = 'admin'
  AND NOT EXISTS (
    SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id
  );

-- viewer 关联 user:read（仅可查看个人信息）
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.code = 'viewer' AND p.code = 'user:read'
  AND NOT EXISTS (
    SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id
  );


-- ── 6. 验证查询 ─────────────────────────────────────────────────────────────
-- 执行后可运行以下查询验证数据是否正确插入：
--
-- SELECT id, code, name, is_builtin FROM roles WHERE deleted_at IS NULL;
-- SELECT id, code, name, module FROM permissions ORDER BY module, code;
-- SELECT id, parent_id, menu_type, title, path, icon, permission, sort
--   FROM menus WHERE id BETWEEN 1000 AND 1999 ORDER BY parent_id, sort;
-- SELECT r.code AS role_code, m.title AS menu_title
--   FROM role_menus rm
--   JOIN roles r ON r.id = rm.role_id
--   JOIN menus m ON m.id = rm.menu_id
--   WHERE m.id BETWEEN 1000 AND 1999
--   ORDER BY r.code, m.id;
-- SELECT r.code AS role_code, p.code AS permission_code
--   FROM role_permissions rp
--   JOIN roles r ON r.id = rp.role_id
--   JOIN permissions p ON p.id = rp.permission_id
--   ORDER BY r.code, p.code;
