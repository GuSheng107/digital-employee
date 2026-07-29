-- =============================================================================
-- 2026-07-29 身份域增量：机器人接口权限与管理身份 VIP 语义修正
--
-- 适用场景：已执行 20260728-enterprise-access-control.sql 的开发数据库。
-- 本脚本幂等，可重复执行。
-- 执行账号：需为 users/roles/permissions/menus 表 owner（包含 ALTER TABLE）。
-- =============================================================================

BEGIN;

INSERT INTO permissions (code, name, description, module)
VALUES (
    'admin:bot:manage',
    '机器人管理',
    '查看、创建、更新和停用机器人接入配置',
    'bot'
)
ON CONFLICT (code) DO UPDATE
SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    module = EXCLUDED.module;

INSERT INTO role_permissions (role_id, permission_id)
SELECT role.id, permission.id
FROM roles AS role
JOIN permissions AS permission
    ON permission.code = 'admin:bot:manage'
WHERE role.code IN ('manager', 'super_admin')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- 已部署环境中的旧菜单标题同步为本迭代统一名称。
UPDATE menus
SET
    title = '用户管理',
    updated_at = CURRENT_TIMESTAMP
WHERE path = '/system/user/register'
  AND title <> '用户管理';

-- 归一化历史可空字段，使真实表约束与 ORM/接口契约一致。
UPDATE users
SET
    vip_level = COALESCE(vip_level, 0),
    is_vip = CASE
        WHEN COALESCE(vip_level, 0) = 0 THEN FALSE
        ELSE is_vip
    END,
    vip_expires_at = CASE
        WHEN COALESCE(vip_level, 0) = 0 THEN NULL
        ELSE vip_expires_at
    END
WHERE vip_level IS NULL;

UPDATE roles
SET
    description = COALESCE(description, ''),
    is_builtin = COALESCE(is_builtin, FALSE)
WHERE description IS NULL OR is_builtin IS NULL;

UPDATE permissions
SET description = COALESCE(description, '')
WHERE description IS NULL;

UPDATE menus
SET
    parent_id = COALESCE(parent_id, 0),
    sort = COALESCE(sort, 0),
    visible = COALESCE(visible, TRUE)
WHERE parent_id IS NULL OR sort IS NULL OR visible IS NULL;

ALTER TABLE users
    ALTER COLUMN vip_level SET DEFAULT 0,
    ALTER COLUMN vip_level SET NOT NULL;

ALTER TABLE roles
    ALTER COLUMN description SET DEFAULT '',
    ALTER COLUMN description SET NOT NULL,
    ALTER COLUMN is_builtin SET DEFAULT FALSE,
    ALTER COLUMN is_builtin SET NOT NULL;

ALTER TABLE permissions
    ALTER COLUMN description SET DEFAULT '',
    ALTER COLUMN description SET NOT NULL;

ALTER TABLE menus
    ALTER COLUMN parent_id SET DEFAULT 0,
    ALTER COLUMN parent_id SET NOT NULL,
    ALTER COLUMN sort SET DEFAULT 0,
    ALTER COLUMN sort SET NOT NULL,
    ALTER COLUMN visible SET DEFAULT TRUE,
    ALTER COLUMN visible SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_normalized
    ON users (LOWER(email))
    WHERE email IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_users_status'
          AND conrelid = 'users'::REGCLASS
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT chk_users_status
            CHECK (status IN (0, 1));
    END IF;
END;
$$;

-- 66/99 是永久有效的管理身份等级；业务 VIP 仍限制在 VIP1-VIP9。
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

UPDATE users AS user_account
SET
    is_vip = FALSE,
    vip_level = 0,
    vip_expires_at = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE user_account.vip_level IN (66, 99)
  AND NOT EXISTS (
      SELECT 1
      FROM user_roles
      JOIN roles ON roles.id = user_roles.role_id
      WHERE user_roles.user_id = user_account.id
        AND (
            (user_account.vip_level = 66 AND roles.code = 'manager')
            OR (user_account.vip_level = 99 AND roles.code = 'super_admin')
        )
  );

-- 业务 VIP 必须同时具备开关、VIP1-VIP9 与过期时间；不完整历史数据降级为普通用户。
UPDATE users
SET
    is_vip = FALSE,
    vip_level = 0,
    vip_expires_at = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE vip_level BETWEEN 1 AND 9
  AND vip_expires_at IS NULL;

UPDATE users
SET
    is_vip = TRUE,
    updated_at = CURRENT_TIMESTAMP
WHERE vip_level BETWEEN 1 AND 9
  AND vip_expires_at IS NOT NULL
  AND NOT is_vip;

UPDATE users
SET
    is_vip = FALSE,
    vip_expires_at = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE vip_level = 0
  AND (is_vip OR vip_expires_at IS NOT NULL);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_users_vip_consistency'
          AND conrelid = 'users'::REGCLASS
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT chk_users_vip_consistency
            CHECK (
                (
                    NOT is_vip
                    AND vip_level = 0
                    AND vip_expires_at IS NULL
                )
                OR (
                    is_vip
                    AND vip_level BETWEEN 1 AND 9
                    AND vip_expires_at IS NOT NULL
                )
                OR (
                    is_vip
                    AND vip_level IN (66, 99)
                    AND vip_expires_at IS NULL
                )
            );
    END IF;
END;
$$;

COMMIT;

-- 核验：
-- SELECT code, name FROM permissions WHERE code = 'admin:bot:manage';
-- SELECT username, is_vip, vip_level, vip_expires_at
-- FROM users
-- WHERE vip_level IN (66, 99)
-- ORDER BY vip_level, username;
