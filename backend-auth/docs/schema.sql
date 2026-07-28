-- =============================================================================
-- backend-auth 表结构初始化脚本
-- 库: db_data  (app_usr 需有该库的 DDL 权限)
-- 字符集: UTF-8  |  时区: UTC (TIMESTAMPTZ)
-- =============================================================================

-- 0. 幂等: 先清旧表(开发期, 生产慎用)
DROP TABLE IF EXISTS bot_agents CASCADE;
DROP TABLE IF EXISTS bot_call_permissions CASCADE;
DROP TABLE IF EXISTS user_bots CASCADE;
DROP TABLE IF EXISTS agents CASCADE;
DROP TABLE IF EXISTS bots CASCADE;
DROP TABLE IF EXISTS role_menus CASCADE;
DROP TABLE IF EXISTS menus CASCADE;
DROP TABLE IF EXISTS role_permissions CASCADE;
DROP TABLE IF EXISTS user_roles CASCADE;
DROP TABLE IF EXISTS permissions CASCADE;
DROP TABLE IF EXISTS roles CASCADE;
DROP TABLE IF EXISTS users CASCADE;

-- =============================================================================
-- 1. 用户与认证
-- =============================================================================
CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(64)  NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    email           VARCHAR(128) UNIQUE,
    phone           VARCHAR(32),
    nickname        VARCHAR(64),
    avatar_url      VARCHAR(512),
    status          SMALLINT     NOT NULL DEFAULT 1,   -- 1=启用 0=禁用
    is_vip          BOOLEAN      NOT NULL DEFAULT FALSE,
    vip_expires_at  TIMESTAMPTZ,                        -- NULL=永久
    vip_level       SMALLINT     DEFAULT 0,             -- 0=普通 1/2/3=金/钻
    last_login_at   TIMESTAMPTZ,
    last_login_ip   VARCHAR(64),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ
);
CREATE INDEX idx_users_status ON users(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_vip    ON users(is_vip, vip_expires_at) WHERE deleted_at IS NULL;
COMMENT ON TABLE  users IS '用户账号表';
COMMENT ON COLUMN users.is_vip         IS 'VIP 标记';
COMMENT ON COLUMN users.vip_expires_at IS 'VIP 过期时间, NULL=永久';
COMMENT ON COLUMN users.vip_level      IS 'VIP 等级: 0=普通 1=金 2=钻 3=至尊';

-- =============================================================================
-- 2. RBAC 权限
-- =============================================================================
CREATE TABLE roles (
    id           BIGSERIAL PRIMARY KEY,
    code         VARCHAR(64)  NOT NULL UNIQUE,   -- admin/operator/viewer/vip
    name         VARCHAR(64)  NOT NULL,
    description  VARCHAR(255) DEFAULT '',
    is_builtin   BOOLEAN      DEFAULT FALSE,     -- 内置角色不可删
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);
COMMENT ON TABLE roles IS '角色表';

CREATE TABLE permissions (
    id           BIGSERIAL PRIMARY KEY,
    code         VARCHAR(128) NOT NULL UNIQUE,   -- agent:read / bot:write
    name         VARCHAR(64)  NOT NULL,
    description  VARCHAR(255) DEFAULT '',
    module       VARCHAR(32),                    -- 所属模块(分组用)
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE permissions IS '权限点表';

CREATE TABLE user_roles (
    user_id  BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id  BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);
COMMENT ON TABLE user_roles IS '用户-角色关联';

CREATE TABLE role_permissions (
    role_id       BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);
COMMENT ON TABLE role_permissions IS '角色-权限关联';

-- =============================================================================
-- 3. 前端菜单
-- =============================================================================
CREATE TABLE menus (
    id           BIGSERIAL PRIMARY KEY,
    parent_id    BIGINT       DEFAULT 0,      -- 0=顶级
    menu_type    SMALLINT     NOT NULL,        -- 1=目录 2=菜单 3=按钮
    title        VARCHAR(64)  NOT NULL,
    path         VARCHAR(255),
    component    VARCHAR(255),                 -- 前端组件路径
    icon         VARCHAR(64),
    permission   VARCHAR(128),                 -- 所需权限码(空=仅登录可见)
    sort         INT          DEFAULT 0,
    visible      BOOLEAN      DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);
CREATE INDEX idx_menus_parent ON menus(parent_id) WHERE deleted_at IS NULL;
COMMENT ON TABLE  menus IS '前端菜单表(树形)';
COMMENT ON COLUMN menus.menu_type IS '1=目录 2=菜单 3=按钮';

CREATE TABLE role_menus (
    role_id  BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    menu_id  BIGINT NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, menu_id)
);
COMMENT ON TABLE role_menus IS '角色-菜单关联';

-- =============================================================================
-- 4. Bot 管理
-- =============================================================================
CREATE TABLE bots (
    id            BIGSERIAL PRIMARY KEY,
    bot_id        VARCHAR(64)  NOT NULL UNIQUE,  -- 业务唯一标识(gateway 用)
    name          VARCHAR(128) NOT NULL,
    platform      VARCHAR(32)  NOT NULL,         -- feishu/wecom
    app_id        VARCHAR(128),
    -- app_secret 不存 PG, 存 Nacos; PG 只存引用 key
    app_secret_ref VARCHAR(128),                 -- Nacos dataId 或 key 名
    parent_bot_id BIGINT       DEFAULT NULL REFERENCES bots(id),  -- 树形:上级 Bot
    mode          VARCHAR(16)  DEFAULT 'test',   -- test/prod
    status        SMALLINT     DEFAULT 1,
    created_by    BIGINT,                        -- 创建者 user_id
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at    TIMESTAMPTZ
);
CREATE INDEX idx_bots_parent ON bots(parent_bot_id) WHERE deleted_at IS NULL;
COMMENT ON TABLE  bots IS 'Bot 定义表';
COMMENT ON COLUMN bots.parent_bot_id IS '上级 Bot, 树形结构表达部门隶属';
COMMENT ON COLUMN bots.app_secret_ref IS 'app_secret 不存 PG, 存 Nacos, 此处存引用 key';

-- Bot 额外调用授权(跨部门/树形外补充授权)
CREATE TABLE bot_call_permissions (
    id             BIGSERIAL PRIMARY KEY,
    caller_bot_id  BIGINT      NOT NULL REFERENCES bots(id) ON DELETE CASCADE,  -- 调用方
    target_bot_id  BIGINT      NOT NULL REFERENCES bots(id) ON DELETE CASCADE,  -- 被调用方
    permission     VARCHAR(64) NOT NULL,   -- call_agent / route_message
    granted_by     BIGINT,                 -- 授权人 user_id
    expires_at     TIMESTAMPTZ,            -- NULL=永久
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (caller_bot_id, target_bot_id, permission)
);
CREATE INDEX idx_bot_call_caller ON bot_call_permissions(caller_bot_id);
COMMENT ON TABLE bot_call_permissions IS 'Bot 额外调用授权(树形外补充)';

CREATE TABLE user_bots (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id  BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, bot_id)
);
COMMENT ON TABLE user_bots IS '用户-Bot 关联';

-- =============================================================================
-- 5. Agent 可见性
-- =============================================================================
CREATE TABLE agents (
    id           BIGSERIAL PRIMARY KEY,
    agent_id     VARCHAR(64)  NOT NULL UNIQUE,
    name         VARCHAR(128) NOT NULL,
    description  VARCHAR(255) DEFAULT '',
    endpoint     VARCHAR(255),                -- agent 服务地址
    status       SMALLINT     DEFAULT 1,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ
);
COMMENT ON TABLE agents IS 'Agent 定义表';

CREATE TABLE bot_agents (
    bot_id   BIGINT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    agent_id BIGINT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    PRIMARY KEY (bot_id, agent_id)
);
COMMENT ON TABLE bot_agents IS 'Bot→Agent 可见性映射';

-- =============================================================================
-- 6. updated_at 自动更新触发器(所有有 updated_at 的表)
-- =============================================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_menus_updated BEFORE UPDATE ON menus
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_bots_updated BEFORE UPDATE ON bots
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_agents_updated BEFORE UPDATE ON agents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
