# Backend Auth

数字员工身份与授权服务，负责登录、注册、密码策略、token 生成，以及
用户/角色/权限/菜单接口的业务编排。

## 架构边界

`backend-auth` 不安装也不直接使用 PostgreSQL、Redis、MinIO 或 MQ 驱动：

```text
backend-auth
  -> backend-share/data-client
  -> backend-data
  -> PostgreSQL / Redis / MinIO / RabbitMQ
```

其他业务服务获取用户上下文和执行权限校验时统一使用：

```text
business service
  -> backend-share/auth-utils
  -> backend-auth /api/v1/auth/me
```

禁止跨服务导入实现目录，服务间只通过 `backend-share` 的公开契约调用。

## 登录与授权

- access/refresh token 均为 opaque token，不在客户端携带可篡改的权限数据。
- Redis token 状态由 `backend-data` 统一读写。
- 同账号后登录会原子撤销旧 token 对；旧端下次请求返回 401，前端刷新失败后
  清理会话并跳转登录页。
- 管理员重置密码后由 Redis 保存强制改密标志；用户只可进入个人信息页，
  主动设置合规密码后解除限制。
- `super_admin` 拥有最高权限旁路；`manager` 必须持有明确权限码。

## 开发

```bash
uv sync
uv run ruff check app tests
uv run pytest -q
uv run uvicorn app.main:app --host 127.0.0.1 --port 8020
```

配置模板见 `.env.example`。本服务只需要 `backend-data` 的服务地址/API Key、
token 生成策略、手机号默认地区等配置，不应出现基础设施连接凭证。

数据库结构和幂等迁移 SQL 位于 `docs/`，由数据库负责人审阅后执行。
