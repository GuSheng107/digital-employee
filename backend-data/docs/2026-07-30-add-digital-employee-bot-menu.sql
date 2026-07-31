-- 用途：为数字员工 Bot 管理功能补充权限点和两级菜单。
-- 影响：更新 permissions，并新增或校正 menus 中的“数字员工 / Bot管理”记录。
-- 执行：由数据库负责人通过 CloudBeaver 在 core 数据库手工执行一次。
-- 幂等：按权限码和菜单路由定位记录，重复执行不会创建重复数据。

BEGIN;

INSERT INTO permissions (code, name, description, module)
VALUES (
    'bot:manage',
    '机器人管理',
    '查看、创建、更新和停用机器人接入配置',
    'bot'
)
ON CONFLICT (code) DO UPDATE
SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    module = EXCLUDED.module;

DO $$
DECLARE
    digital_employee_menu_id BIGINT;
    bot_management_menu_id BIGINT;
BEGIN
    SELECT id
    INTO digital_employee_menu_id
    FROM menus
    WHERE path = '/digital-employee'
    ORDER BY (deleted_at IS NULL) DESC, id
    LIMIT 1;

    IF digital_employee_menu_id IS NULL THEN
        INSERT INTO menus (
            parent_id,
            menu_type,
            title,
            path,
            component,
            icon,
            permission,
            sort,
            visible
        )
        VALUES (
            0,
            1,
            '数字员工',
            '/digital-employee',
            NULL,
            'TeamOutlined',
            NULL,
            10,
            TRUE
        )
        RETURNING id INTO digital_employee_menu_id;
    ELSE
        UPDATE menus
        SET
            parent_id = 0,
            menu_type = 1,
            title = '数字员工',
            component = NULL,
            icon = 'TeamOutlined',
            permission = NULL,
            sort = 10,
            visible = TRUE,
            updated_at = NOW(),
            deleted_at = NULL
        WHERE id = digital_employee_menu_id;
    END IF;

    SELECT id
    INTO bot_management_menu_id
    FROM menus
    WHERE path = '/digital-employee/bots'
    ORDER BY (deleted_at IS NULL) DESC, id
    LIMIT 1;

    IF bot_management_menu_id IS NULL THEN
        INSERT INTO menus (
            parent_id,
            menu_type,
            title,
            path,
            component,
            icon,
            permission,
            sort,
            visible
        )
        VALUES (
            digital_employee_menu_id,
            2,
            'Bot管理',
            '/digital-employee/bots',
            'digital-employee/bot',
            'RobotOutlined',
            'bot:manage',
            10,
            TRUE
        );
    ELSE
        UPDATE menus
        SET
            parent_id = digital_employee_menu_id,
            menu_type = 2,
            title = 'Bot管理',
            component = 'digital-employee/bot',
            icon = 'RobotOutlined',
            permission = 'bot:manage',
            sort = 10,
            visible = TRUE,
            updated_at = NOW(),
            deleted_at = NULL
        WHERE id = bot_management_menu_id;
    END IF;
END
$$;

COMMIT;
