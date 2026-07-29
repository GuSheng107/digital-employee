-- =============================================================================
-- 2026-07-28 用户、角色、接口权限与菜单权限收敛
--
-- 执行方式：由数据库负责人在 CloudBeaver 中审阅并执行。
-- 目标：
--   1. vip_level=99 为超级管理员，66 为管理员。
--   2. 接口权限与 menus.permission 使用同一套规范权限码。
--   3. manager 通过显式权限授权；super_admin 由应用层提供全权限旁路。
--   4. 角色权限、角色菜单、用户直接权限与用户直接菜单结构完整。
--   5. 防止有效菜单出现同级重名或路由路径重复。
-- =============================================================================

BEGIN;

-- 用户直接授权表：角色权限之外的少量例外授权。
CREATE TABLE IF NOT EXISTS user_permissions (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, permission_id)
);

CREATE TABLE IF NOT EXISTS user_menus (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    menu_id BIGINT NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, menu_id)
);

COMMENT ON TABLE user_permissions IS '用户直接权限授权；最终权限与角色权限取并集';
COMMENT ON TABLE user_menus IS '用户直接菜单授权；最终菜单与角色菜单取并集';

-- 规范内置角色。
INSERT INTO roles (code, name, description, is_builtin)
VALUES
    ('user', '普通用户', '普通业务用户', TRUE),
    ('manager', '管理员', '通过显式权限码管理用户、角色、菜单与数据中台', TRUE),
    ('super_admin', '超级管理员', '系统最高权限身份，不进入通用角色管理', TRUE)
ON CONFLICT (code) DO UPDATE
SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    is_builtin = TRUE,
    deleted_at = NULL;

-- 规范权限目录：接口鉴权与菜单可见性共用这些 code。
INSERT INTO permissions (code, name, description, module)
VALUES
    ('user:profile:edit', '维护个人资料', '查看并维护当前登录用户自己的资料', 'user'),
    ('admin:user:manage', '用户管理', '查看、创建用户及重置用户密码', 'user'),
    ('admin:user:permission', '用户与角色授权', '分配用户角色、用户菜单及维护角色权限', 'access'),
    ('admin:invite_code:manage', '邀请码管理', '查看和创建注册邀请码', 'invite_code'),
    ('admin:menu:manage', '菜单管理', '查看、创建、编辑和删除菜单', 'menu'),
    ('admin:data_platform:dashboard', '数据中台概览', '查看数据中台运行与依赖状态', 'data_platform'),
    ('admin:data_platform:data_items', '数据项管理', '查询和维护 Data Items', 'data_platform'),
    ('admin:data_platform:config', '数据中台配置', '查看配置并执行依赖连通性测试', 'data_platform'),
    ('admin:bot:manage', '机器人管理', '查看、创建、更新和停用机器人接入配置', 'bot')
ON CONFLICT (code) DO UPDATE
SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    module = EXCLUDED.module;

-- 菜单入口绑定与接口一致的权限码。
UPDATE menus
SET permission = CASE id
    WHEN 1101 THEN 'user:profile:edit'
    WHEN 1102 THEN 'admin:user:manage'
    WHEN 1103 THEN 'admin:user:permission'
    WHEN 1104 THEN 'admin:invite_code:manage'
    WHEN 1201 THEN 'admin:menu:manage'
    WHEN 2001 THEN 'admin:data_platform:dashboard'
    WHEN 2002 THEN 'admin:data_platform:data_items'
    WHEN 2003 THEN 'admin:data_platform:config'
    ELSE permission
END
WHERE id IN (1101, 1102, 1103, 1104, 1201, 2001, 2002, 2003);

-- 统一清理存量空白权限值，避免空字符串被外键当作真实权限码。
UPDATE menus
SET permission = NULLIF(BTRIM(permission), '')
WHERE permission IS DISTINCT FROM NULLIF(BTRIM(permission), '');

-- 外键建立前给出明确的迁移诊断；不静默创建未知权限，避免拼写错误进入目录。
DO $$
DECLARE
    missing_codes TEXT;
BEGIN
    SELECT string_agg(code, ', ' ORDER BY code)
    INTO missing_codes
    FROM (
        SELECT DISTINCT menus.permission AS code
        FROM menus
        LEFT JOIN permissions
            ON permissions.code = menus.permission
        WHERE menus.permission IS NOT NULL
          AND permissions.id IS NULL
    ) AS missing_permissions;

    IF missing_codes IS NOT NULL THEN
        RAISE EXCEPTION
            'menus.permission 存在未登记权限码，请先补充 permissions：%',
            missing_codes
            USING ERRCODE = '23503';
    END IF;
END;
$$;

-- 菜单引用的权限码必须存在于权限目录。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_menus_permission_code'
          AND conrelid = 'menus'::REGCLASS
    ) THEN
        ALTER TABLE menus
            ADD CONSTRAINT fk_menus_permission_code
            FOREIGN KEY (permission)
            REFERENCES permissions(code)
            ON UPDATE CASCADE
            ON DELETE RESTRICT;
    END IF;
END;
$$;

-- menu_type 只允许目录、页面、动作权限节点。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_menus_type'
          AND conrelid = 'menus'::REGCLASS
    ) THEN
        ALTER TABLE menus
            ADD CONSTRAINT chk_menus_type
            CHECK (menu_type IN (1, 2, 3));
    END IF;
END;
$$;

-- VIP 身份值约束：0-9 为普通 VIP，66 管理员，99 超级管理员。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_users_vip_level'
          AND conrelid = 'users'::REGCLASS
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT chk_users_vip_level
            CHECK (
                vip_level IS NULL
                OR vip_level BETWEEN 0 AND 9
                OR vip_level IN (66, 99)
            );
    END IF;
END;
$$;

-- 有效菜单不允许同级重名，非空路由路径全局唯一。
CREATE UNIQUE INDEX IF NOT EXISTS uq_menus_active_sibling_title
    ON menus (parent_id, title)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_menus_active_path
    ON menus (path)
    WHERE deleted_at IS NULL
      AND NULLIF(BTRIM(path), '') IS NOT NULL;

-- 普通用户也拥有自助资料权限和对应菜单；管理员角色在后续步骤获得全部菜单。
INSERT INTO role_permissions (role_id, permission_id)
SELECT role.id, permission.id
FROM roles AS role
JOIN permissions AS permission
    ON permission.code = 'user:profile:edit'
WHERE role.code IN ('user', 'manager', 'super_admin')
ON CONFLICT (role_id, permission_id) DO NOTHING;

INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id
FROM roles AS role
JOIN menus AS menu
    ON menu.id = 1101
WHERE role.code = 'user'
  AND menu.deleted_at IS NULL
ON CONFLICT (role_id, menu_id) DO NOTHING;

-- manager 与 super_admin 均获得全部当前管理端权限。
INSERT INTO role_permissions (role_id, permission_id)
SELECT role.id, permission.id
FROM roles AS role
CROSS JOIN permissions AS permission
WHERE role.code IN ('manager', 'super_admin')
  AND permission.code LIKE 'admin:%'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- 两类管理员均关联全部当前有效菜单；super_admin 虽不在管理页显示，
-- 仍保留完整关联以便审计。
INSERT INTO role_menus (role_id, menu_id)
SELECT role.id, menu.id
FROM roles AS role
CROSS JOIN menus AS menu
WHERE role.code IN ('manager', 'super_admin')
  AND menu.deleted_at IS NULL
ON CONFLICT (role_id, menu_id) DO NOTHING;

-- 先标记普通管理员，再标记超级管理员，确保同时拥有两角色时 99 优先。
UPDATE users AS user_account
SET
    is_vip = TRUE,
    vip_level = 66,
    vip_expires_at = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE EXISTS (
    SELECT 1
    FROM user_roles
    JOIN roles ON roles.id = user_roles.role_id
    WHERE user_roles.user_id = user_account.id
      AND roles.code = 'manager'
);

UPDATE users AS user_account
SET
    is_vip = TRUE,
    vip_level = 99,
    vip_expires_at = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE EXISTS (
    SELECT 1
    FROM user_roles
    JOIN roles ON roles.id = user_roles.role_id
    WHERE user_roles.user_id = user_account.id
      AND roles.code = 'super_admin'
);

COMMIT;

-- 执行后核验：
-- SELECT code, name, module FROM permissions WHERE code LIKE 'admin:%' ORDER BY code;
-- SELECT code, name, is_builtin FROM roles WHERE deleted_at IS NULL ORDER BY id;
-- SELECT id, parent_id, title, path, permission FROM menus
-- WHERE deleted_at IS NULL ORDER BY parent_id, sort, id;
