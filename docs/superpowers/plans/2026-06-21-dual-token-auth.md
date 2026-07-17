# 双 Token 认证实现计划 (Dual Token Auth Implementation Plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标:** 完成 `backend-agent` 的双 Token 认证机制：外部浏览器/API 调用方使用 Redis-backed Bearer `access_token` / `refresh_token`，可信内部 OAS 调用方通过独立的 `X-Caller-*` header 流程识别和放行。

**架构:** 保留现有 FastAPI middleware 边界和 Redis opaque-token manager。新增一个聚焦的 internal-auth verifier，用于校验 `X-Caller-*` headers；然后让 `auth_middleware.py` 先尝试 internal auth，再尝试 external Bearer auth。请求身份写入 `request.state.auth_source`、`request.state.caller_id`，并继续维护现有 `request.state.auth_user` contract。

**技术栈:** Python 3.10+, FastAPI, Redis async client, YAML config, Vue frontend fetch wrappers, Markdown docs.

---

## 执行层约定

- 中文用于说明目标、原因、边界、风险和验收。
- 英文保留给执行层标识：file paths、function names、class names、test names、headers、config keys、state fields、commands、code snippets。
- 不翻译这些执行标识：`Authorization`、`Bearer`、`access_token`、`refresh_token`、`X-Caller-ID`、`X-Caller-Timestamp`、`X-Caller-Signature`、`request.state.auth_source`、`request.state.caller_id`、`request.state.auth_user`。
- 本计划不实现 route-level permissions，不引入 cookies，不把 Redis opaque tokens 改成 JWT。

## 成功标准

- 外部请求使用 `Authorization: Bearer <ccx_at_...>` 完成认证。
- 登录接口返回 `access_token`、`refresh_token`、`expires_in` 和 `token_type`。
- `access_token` 是 Redis 中保存的 opaque session token，不是 JWT。
- 校验 `access_token` 成功时刷新 sliding TTL。
- `refresh_token` 可以轮换新的 token pair。
- 内部 OAS 请求在 `X-Caller-*` headers 有效时，可以不携带用户登录 token 访问受保护 API。
- 后端可以通过 `request.state.auth_source == "internal"` 和 `"external"` 区分请求来源。
- 不引入 cookies。
- 本轮不实现 route-level permissions。
- 实现完成后写入 `docs/dual-token-auth-change-log.md`。
- 最终由 subagent 对照本计划、change log 和 final git diff 做审查。

## 文件结构

- Modify `backend-agent/app/yaml_config.py`
  - 增加 `auth.internal_callers` 默认配置。
- Create `backend-agent/app/internal_auth.py`
  - 校验 internal caller ID、timestamp、signature 和 IP allowlist。
- Modify `backend-agent/app/auth_middleware.py`
  - 在 external Bearer auth 之前先尝试 internal auth。
  - 统一填充 request identity state。
- Modify `backend-agent/app/redis_token_manager.py`
  - 保持 access/refresh token 行为聚焦，只在测试暴露缺口时补齐 sliding TTL 或 rotation 行为。
- Modify `backend-agent/app/routers/auth.py`
  - 保持 login/refresh/logout 与 Bearer access/refresh token flow 兼容。
- Inspect/modify frontend files only if existing behavior is incomplete:
  - `frontend/src/api/http.js`
  - `frontend/src/composables/useAuthSession.js`
- Create tests under `backend-agent/tests/`。
- Create `docs/dual-token-auth-change-log.md` after implementation。

## Internal Caller Protocol

Headers:

```text
X-Caller-ID: oas-backend
X-Caller-Timestamp: 1782038400
X-Caller-Signature: hex(hmac_sha256(shared_secret, METHOD + "\n" + PATH + "\n" + TIMESTAMP))
```

Validation:

- `caller_id` 必须存在于 `auth.internal_callers`。
- `X-Caller-Timestamp` 必须在 server time 前后 300 秒内。
- HMAC 必须使用 `hmac.compare_digest` 做常量时间比较。
- 配置了 `ip_allowlist` 时，caller IP 必须命中 allowlist。
- internal auth 成功后设置：

```python
request.state.auth_source = "internal"
request.state.caller_id = caller_id
request.state.auth_user = {
    "username": f"internal:{caller_id}",
    "display_name": f"internal:{caller_id}",
    "role": "internal",
    "is_active": True,
}
```

## Task 1: Add Internal Caller Config Defaults

**目的:** 让 YAML config 有稳定的 `auth.internal_callers` 默认入口，避免 middleware 或 verifier 读取配置时遇到缺失 key。

**Files:**
- Modify: `backend-agent/app/yaml_config.py`

- [ ] **Step 1: Add default config**

在现有 `auth` defaults 下增加：

```python
"internal_callers": {},
```

用户配置示例：

```yaml
auth:
  dual_token_enabled: true
  internal_callers:
    oas-backend:
      shared_secret: "replace-with-long-random-secret"
      ip_allowlist:
        - "127.0.0.1/32"
        - "10.0.0.0/8"
      description: "OAS backend service"
```

- [ ] **Step 2: Verify syntax**

Run:

```powershell
python -m compileall backend-agent\app\yaml_config.py
```

Expected: command exits `0`.

## Task 2: Implement Internal Auth Verifier

**目的:** 把 internal caller 的 header 校验集中到独立模块，避免把 HMAC、timestamp、IP allowlist 逻辑散落在 middleware 中。

**Files:**
- Create: `backend-agent/app/internal_auth.py`
- Test: `backend-agent/tests/test_internal_auth.py`

- [ ] **Step 1: Write tests**

Create tests:

```python
def test_valid_internal_signature_is_accepted()
def test_unknown_caller_is_rejected()
def test_bad_signature_is_rejected()
def test_expired_timestamp_is_rejected()
def test_ip_allowlist_blocks_unlisted_ip()
```

- [ ] **Step 2: Implement module**

Implement:

```python
class InternalAuthError(Exception):
    def __init__(self, message: str, status_code: int = 403) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def verify_internal_request(*, config: dict, method: str, path: str, headers: Mapping[str, str], client_host: str | None, now: int | None = None) -> str | None:
    ...
```

Return contract:

- 没有任何 internal caller headers 时返回 `None`。
- internal auth 成功时返回 `caller_id`。
- 只要出现部分或完整 internal headers 但校验失败，就 raise `InternalAuthError`。

- [ ] **Step 3: Run tests**

Run:

```powershell
python -m pytest backend-agent\tests\test_internal_auth.py -q
```

Expected: all tests pass.

## Task 3: Integrate Internal/External Identity in Middleware

**目的:** 在同一个 FastAPI middleware 边界内完成 internal 和 external 两条认证路径，并保证下游 routes 能稳定读取身份来源。

**Files:**
- Modify: `backend-agent/app/auth_middleware.py`
- Test: `backend-agent/tests/test_auth_middleware.py`

- [ ] **Step 1: Add middleware tests**

Cover:

```python
def test_public_login_path_skips_auth()
def test_internal_auth_sets_internal_state()
def test_invalid_internal_auth_returns_403()
def test_missing_external_token_returns_401()
```

- [ ] **Step 2: Update middleware flow**

认证顺序必须是：

1. Skip `OPTIONS`, non-`/api`, and public auth paths.
2. Try internal auth via `verify_internal_request`.
3. If no internal headers, require external Bearer token.
4. Validate external token with Redis manager when enabled.
5. Fallback to legacy HMAC session token only when dual token manager is absent.

- [ ] **Step 3: Preserve state contract**

External Redis token success sets:

```python
request.state.auth_source = "external"
request.state.caller_id = None
request.state.auth_user = user
```

Legacy HMAC success also sets `auth_source = "external"`。

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest backend-agent\tests\test_auth_middleware.py -q
```

Expected: all tests pass.

## Task 4: Verify Redis Token Sliding Behavior

**目的:** 验证 Redis token manager 已经满足 opaque access token、sliding TTL、refresh rotation 和 revoke 语义；只在测试暴露行为缺口时修改实现。

**Files:**
- Modify only if needed: `backend-agent/app/redis_token_manager.py`
- Test: `backend-agent/tests/test_redis_token_manager.py`

- [ ] **Step 1: Add focused fake Redis tests**

Cover:

```python
async def test_validate_access_token_refreshes_expiry()
async def test_refresh_token_rotates_pair()
async def test_revoked_access_token_is_rejected()
```

- [ ] **Step 2: Keep implementation minimal**

Only change Redis token manager if tests expose behavior gaps. Do not rewrite token format, Redis key names, or refresh flow unless required by tests.

- [ ] **Step 3: Run tests**

Run:

```powershell
python -m pytest backend-agent\tests\test_redis_token_manager.py -q
```

Expected: all tests pass.

## Task 5: Frontend Compatibility Check

**目的:** 确认前端仍按 Bearer token 方式请求 API，并且 `401` 后可以使用 `refresh_token` 获取新 token pair 后重试原请求。

**Files:**
- Inspect/modify only if needed:
  - `frontend/src/api/http.js`
  - `frontend/src/composables/useAuthSession.js`

- [ ] **Step 1: Confirm Bearer usage**

Ensure API calls use:

```javascript
Authorization: `Bearer ${accessToken}`
```

- [ ] **Step 2: Confirm refresh retry**

Ensure a `401` response triggers `/api/auth/refresh`, stores new tokens, and retries the request.

- [ ] **Step 3: Run frontend build**

Run:

```powershell
cd frontend
npm run build
```

Expected: build exits `0`.

## Task 6: Write Change Log

**目的:** 实现结束后留下可审计记录，说明实际改了什么、为什么改、如何验证，以及哪些明确不在本轮范围内。

**Files:**
- Create: `docs/dual-token-auth-change-log.md`

- [ ] **Step 1: Document changes**

Include:

- Files changed.
- Behavior before/after.
- Config example.
- Verification results.
- Known non-goals: route-level permissions, cookies, JWT.

- [ ] **Step 2: Compare implementation against this plan**

Add a table:

```markdown
| Plan Item | Status | Evidence |
|-----------|--------|----------|
```

## Task 7: Final Verification

**目的:** 用实际命令证明后端语法、后端测试和前端构建状态，而不是只凭代码阅读宣布完成。

- [ ] **Step 1: Compile backend**

Run:

```powershell
python -m compileall backend-agent\app
```

Expected: exits `0`.

- [ ] **Step 2: Run backend tests**

Run:

```powershell
python -m pytest backend-agent\tests -q
```

Expected: exits `0`.

- [ ] **Step 3: Run frontend build**

Run:

```powershell
cd frontend
npm run build
```

Expected: exits `0`, unless dependencies are missing. If missing, record the exact blocker in the change log.

## Task 8: Subagent Audit

**目的:** 让独立 reviewer 对照计划、change log 和 final git diff 做一次偏差审查，防止实现超范围、漏项或引入安全回归。

- [ ] **Step 1: Dispatch reviewer subagent**

Ask the reviewer to inspect:

- This plan file.
- `docs/dual-token-auth-change-log.md`.
- The final git diff.

Reviewer must answer:

- Does implementation match the plan?
- Are there extra changes not justified by the plan?
- Are internal and external auth paths distinguishable?
- Are tests meaningful?
- Are there security regressions?

- [ ] **Step 2: Fix Critical/Important findings**

If reviewer reports Critical or Important issues, fix them and rerun verification.

- [ ] **Step 3: Record review result**

Append reviewer summary to `docs/dual-token-auth-change-log.md`.
