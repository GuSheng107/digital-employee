---
name: backend-dev-spec
description: 数字员工项目后端开发规范，涵盖 uv 依赖管理、统一响应信封、业务异常体系、API 路由分层。当 Agent 需要修改或新增后端代码（backend-auth / backend-data / backend-gateway / backend-share）时，必须遵循本规范。
---

# 技能：后端开发规范 (backend-dev-spec)

本规范适用于 `digital-employee` 仓库下所有后端服务：
- `backend-auth`：认证中心（双 token、RBAC、菜单与 Bot 权限）
- `backend-data`：数据中台（DB / Redis / Minio 读写）
- `backend-gateway`：网关（企微/飞书 Bot 信息管理）
- `backend-share`：共享包（`api-common`、`nacos-client`）

## 1. 依赖管理（uv）

### 1.1 强制使用 uv

- 所有后端服务必须使用 `uv` 管理依赖，禁止使用 `pip install` 或 `requirements.txt`。
- 每个服务有自己的 `pyproject.toml` 和 `uv.lock`。
- 共享包通过 `[tool.uv.sources]` 以本地路径方式引入。

### 1.2 版本锁定规则

**所有依赖必须使用精确版本号（`==`），禁止使用范围版本（`>=`、`~=`、`<`）。**

理由：
- 固定版本确保团队成员环境完全一致，避免"在我机器上能跑"的问题。
- 依赖升级必须通过显式 PR，便于 review 和回滚。
- 不考虑向后兼容性，规范优先于灵活性。

正确写法：

```toml
dependencies = [
    "fastapi==0.140.7",
    "uvicorn[standard]==0.51.0",
    "SQLAlchemy==2.0.51",
    "pydantic==2.13.4",
]
```

错误写法（禁止）：

```toml
dependencies = [
    "fastapi>=0.110,<1.0",      # 范围版本，禁止
    "SQLAlchemy>=2.0,<3.0",     # 范围版本，禁止
    "pydantic>=2.5",            # 范围版本，禁止
]
```

### 1.3 共享包引用

`backend-share` 下的 `api-common` 和 `nacos-client` 作为本地路径依赖引入，也必须锁定版本：

```toml
[tool.uv.sources]
api-common = { path = "../backend-share/api-common" }
nacos-client = { path = "../backend-share/nacos-client" }

[project.dependencies]
api-common = "==0.1.0"
nacos-client = "==0.1.0"
```

### 1.4 跨服务版本对齐

核心依赖（`fastapi`、`pydantic`、`SQLAlchemy`、`redis`、`loguru`、`python-dotenv`）在各服务中必须使用同一版本，避免因版本差异导致行为不一致。

## 2. 统一响应信封

### 2.1 响应结构

所有后端服务返回的 HTTP 响应体必须遵循同一信封：

```json
{
  "success": true,
  "message": "ok",
  "data": {}
}
```

错误响应：

```json
{
  "success": false,
  "message": "用户名或密码错误",
  "data": {
    "code": "INVALID_CREDENTIALS",
    "detail": ""
  }
}
```

### 2.2 字段语义

| 字段       | 类型    | 说明                                           |
|------------|---------|------------------------------------------------|
| `success`  | bool    | 业务是否成功，与 HTTP 状态码解耦                |
| `message`  | string  | 面向用户的提示文案，前端可直接展示              |
| `data`     | any     | 业务数据；错误响应中为 `{code, detail}`         |
| `data.code`| string  | 业务错误码，前端用于差异化处理（如 429 退避）   |
| `data.detail` | any  | 错误详情，用于排查问题，不直接展示给用户        |

### 2.3 code 字段归属

**业务错误码 `code` 必须放在 `data.code` 中，不得放在响应顶层。**

理由：
- 顶层 `success` 已经表达业务成败，`message` 表达文案，`data` 表达数据/错误详情。
- 成功响应的 `data` 是业务数据，错误响应的 `data` 是错误详情，结构一致。
- 前端拦截器统一从 `body.data.code` 提取错误码，无需区分成功/失败路径。

## 3. 业务异常体系

### 3.1 使用 ApiException

所有业务异常必须继承 `api_common.ApiException`，禁止在路由中直接 `raise HTTPException`。

`api_common` 已预定义常见异常子类，按 HTTP 状态码分组：

| 异常类                       | code                       | HTTP |
|------------------------------|----------------------------|------|
| `ValidationError`            | `VALIDATION_FAILED`        | 422  |
| `InvalidCredentialsError`    | `INVALID_CREDENTIALS`      | 401  |
| `UserDisabledError`          | `USER_DISABLED`            | 401  |
| `ResourceNotFoundError`      | `RESOURCE_NOT_FOUND`       | 404  |
| `DuplicateResourceError`     | `DUPLICATE_RESOURCE`       | 409  |
| `TokenExpiredError`          | `TOKEN_EXPIRED`            | 401  |
| `TokenInvalidError`          | `TOKEN_INVALID`            | 401  |
| `PermissionDeniedError`      | `PERMISSION_DENIED`        | 403  |
| `RateLimitExceededError`     | `RATE_LIMIT_EXCEEDED`      | 429  |
| `QuotaExceededError`         | `QUOTA_EXCEEDED`           | 429  |
| `BillingRequiredError`       | `BILLING_REQUIRED`         | 402  |
| `ModelUnavailableError`      | `MODEL_UNAVAILABLE`        | 503  |
| `ContextLengthExceededError` | `CONTEXT_LENGTH_EXCEEDED`  | 413  |
| `ContentFilteredError`       | `CONTENT_FILTERED`         | 400  |
| `GenerationFailedError`      | `GENERATION_FAILED`        | 502  |
| `EmbeddingFailedError`       | `EMBEDDING_FAILED`         | 502  |
| `VectorStoreError`           | `VECTOR_STORE_ERROR`       | 500  |
| `InternalError`              | `INTERNAL_ERROR`           | 500  |
| `DependencyUnavailableError` | `DEPENDENCY_UNAVAILABLE`   | 503  |
| `ServiceUnavailableError`    | `SERVICE_UNAVAILABLE`      | 503  |

### 3.2 路由层异常处理

**路由层禁止 try/except 转换业务异常。** 业务异常直接 raise，由全局异常处理器统一转换为响应信封。

正确写法：

```python
from api_common import InvalidCredentialsError

@router.post("/login")
def login(payload: LoginRequest, service: AuthService = Depends(get_auth_service)) -> dict:
    token_pair = service.login(payload.username, payload.password)
    return success_response(token_pair.model_dump())
```

错误写法（禁止）：

```python
@router.post("/login")
def login(payload: LoginRequest, service: AuthService = Depends(get_auth_service)) -> dict:
    try:
        token_pair = service.login(payload.username, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc  # 禁止
    return success_response(token_pair.model_dump())
```

### 3.3 全局异常处理器

每个服务必须在 `app/main.py` 注册以下异常处理器：

1. `ApiException` 处理器：调用 `exc.to_response()`，按 `exc.http_status` 设置响应状态码。
2. `HTTPException` 处理器：兜底处理第三方依赖抛出的 HTTPException，code 用 `HTTP_{status}` 标识。
3. `RequestValidationError` 处理器：返回 422，code 为 `VALIDATION_FAILED`，detail 为校验错误列表。
4. `Exception` 兜底处理器：返回 500，code 为 `INTERNAL_ERROR`，对外脱敏。

### 3.4 自定义业务异常

服务可定义自己的业务异常子类，但必须继承 `api_common.ApiException`：

```python
from api_common import ApiException, ErrorCode

class BotNotFoundError(ApiException):
    code = "BOT_NOT_FOUND"
    message = "bot not found"
    http_status = 404
```

## 4. API 路由分层

### 4.1 目录结构

```
app/
  api/
    routes/          # 路由层，只做请求解析与响应组装
      auth.py
      health.py
    deps.py          # FastAPI 依赖（认证、数据库会话等）
    router.py        # 聚合所有 routes
  services/          # 业务编排层
    auth_service.py
  models/            # SQLAlchemy ORM 模型
  schemas/           # Pydantic 请求/响应模型
  core/              # 基础设施（config、database、redis_client、security）
  main.py            # FastAPI 应用入口
```

### 4.2 职责边界

- **路由层（routes）**：只做请求解析、依赖注入、响应组装。不写业务逻辑，不直接操作数据库。
- **服务层（services）**：业务编排，操作数据库与 Redis。抛出业务异常。
- **模型层（models）**：纯 ORM 定义，不含业务逻辑。
- **Schema 层（schemas）**：Pydantic 模型，用于请求校验与响应序列化。

### 4.3 响应构造

路由函数返回 `dict`（由 `success_response` / `fail_response` 构造），并声明 `response_model=ApiResponse`，便于 OpenAPI 文档生成：

```python
from api_common import ApiResponse, success_response

@router.get("/me", response_model=ApiResponse)
def me(current_user: UserInfo = Depends(get_current_user)) -> dict:
    return success_response(current_user.model_dump())
```

## 5. 代码检查

提交前必须通过 `ruff check`：

```bash
cd backend-auth
uv run ruff check app
```

`pyproject.toml` 中的 ruff 配置：

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]
ignore = [
    "E501",    # 行宽由 line-length 控制
    "B008",    # FastAPI 推荐在默认参数中使用 Depends()
    "RUF002",  # docstring 中的中文全角标点
    "RUF003",  # 注释中的中文全角标点
    "RUF006",  # 字典字面量中的中文全角标点
]
```

## 6. 规范检查清单

提交后端代码前，确认以下事项：

- [ ] 所有依赖使用精确版本号（`==`），无范围版本
- [ ] 核心依赖版本跨服务对齐
- [ ] 响应体遵循统一信封 `{success, message, data}`
- [ ] 错误响应的 `code` 放在 `data.code` 中
- [ ] 业务异常继承 `api_common.ApiException`，路由层无 try/except
- [ ] 全局异常处理器已注册（ApiException / HTTPException / RequestValidationError / Exception）
- [ ] 路由层只做请求解析与响应组装，业务逻辑在 service 层
- [ ] `uv run ruff check` 通过
- [ ] 注释与 docstring 使用中文，节关键字（Args/Returns/Raises）保持英文
