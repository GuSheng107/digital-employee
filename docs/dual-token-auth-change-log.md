# Dual Token Auth Change Log

Date: 2026-06-21

Plan: `docs/superpowers/plans/2026-06-21-dual-token-auth.md`

## Scope

This pass completed the missing internal/external request distinction on top of the existing Redis access/refresh token draft.

The working tree already contained dual-token draft changes before this pass in:

- `backend-agent/app/auth.py`
- `backend-agent/app/redis_token_manager.py`
- `backend-agent/app/routers/auth.py`
- `backend-agent/app/web_server.py`
- `frontend/src/composables/useAuthSession.js`

This pass intentionally kept those drafts intact and made surgical changes around the missing internal caller path, request identity state, tests, and one frontend refresh retry bug.

## Changes Made In This Pass

| File | Change |
|------|--------|
| `docs/superpowers/plans/2026-06-21-dual-token-auth.md` | Added explicit implementation plan and success criteria. |
| `backend-agent/app/yaml_config.py` | Added default `auth.internal_callers = {}`. |
| `backend-agent/app/internal_auth.py` | Added internal caller verification for `X-Caller-ID`, `X-Caller-Timestamp`, `X-Caller-Signature`, timestamp skew, HMAC, and optional IP allowlist. |
| `backend-agent/app/auth_middleware.py` | Added internal auth branch before Bearer token auth. Added `request.state.auth_source` and `request.state.caller_id` for internal, Redis external, and legacy external paths. |
| `backend-agent/tests/conftest.py` | Added backend import path setup for tests. |
| `backend-agent/tests/test_internal_auth.py` | Added tests for valid internal auth, absent internal headers, unknown caller, bad signature, expired timestamp, and IP allowlist rejection. |
| `backend-agent/tests/test_auth_middleware.py` | Added middleware tests for public path skip, internal state, invalid internal auth, missing external token, and external Redis state. |
| `backend-agent/tests/test_redis_token_manager.py` | Added Redis token behavior tests using a focused fake Redis client. |
| `frontend/src/api/http.js` | Fixed concurrent refresh wait path to return the actual refresh result instead of always returning `true`. |
| `frontend/src/api/http.js` | Added refresh-and-retry support to `fetchWithAuth()` and stopped appending tokens to URLs. |
| `frontend/src/views/ControlView.vue` | Replaced `EventSource(url?session_token=...)` with `fetchWithAuth()` streaming SSE parsing so AI status stream uses Bearer headers. |
| `frontend/src/api/system.js` | Replaced document download URL generation with `downloadDocumentBlob()` using `fetchWithAuth()`. |
| `frontend/src/api/runtime.js` | Re-exported `downloadDocumentBlob()`. |
| `frontend/src/views/SystemSettingsView.vue` | Switched document download to Blob object URLs after authenticated fetch. |
| `frontend/src/components/chat/MessageBubble.vue` | Switched chat media/file attachment URLs to authenticated Blob object URLs and repaired corrupted display strings that broke Vue compilation after UTF-8 rewrite. |
| `backend-agent/web/src/api/http.js` | Mirrored frontend Bearer-only and refresh/retry changes for the backend-served web source. |
| `backend-agent/web/src/views/ControlView.vue` | Mirrored authenticated SSE stream changes. |
| `backend-agent/web/src/api/system.js` | Mirrored authenticated document download changes. |
| `backend-agent/web/src/api/runtime.js` | Mirrored `downloadDocumentBlob()` export. |
| `backend-agent/web/src/views/SystemSettingsView.vue` | Mirrored Blob download changes. |
| `backend-agent/web/src/components/chat/MessageBubble.vue` | Mirrored authenticated attachment Blob URL changes and display string fixes. |
| `backend-agent/app/web_server.py` | Clears the global dual-token manager when dual-token auth is disabled to avoid stale same-process state. |

## Behavior Before / After

| Area | Before | After |
|------|--------|-------|
| Internal OAS calls | No dedicated internal caller path in middleware. | Valid `X-Caller-*` headers can authenticate as internal without user token. |
| Request source visibility | Routes could see `auth_user`, but not whether request was internal or external. | Middleware sets `request.state.auth_source = "internal"` or `"external"`. |
| Caller identity | No `caller_id` context. | Internal requests set `request.state.caller_id`; external requests set it to `None`. |
| External user auth | Existing Redis access/refresh draft handled Bearer tokens. | Preserved. Successful Redis auth now explicitly marks source as external. |
| Legacy auth fallback | Existing HMAC session fallback. | Preserved when dual token manager is absent and marked as external. |
| Frontend concurrent refresh | Waiting requests treated refresh as successful even if it failed. | Waiting requests now receive the actual refresh result. |
| URL token auth | `session_token` query parameter could authenticate API requests. | Removed from middleware; URL helper no longer appends tokens. Headerless flows were converted to authenticated fetch where covered by this pass. |
| `fetchWithAuth()` 401 handling | Returned 401 and triggered auth failure without refresh retry. | Tries refresh once, then retries the original fetch before reporting auth failure. |
| Chat media/file attachments | Browser elements loaded `/api/...` URLs directly, relying on query-token URLs. | API media/file URLs are fetched with Bearer headers and converted to object URLs. |

## Internal Caller Config Example

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

## Internal Caller Signature

```text
X-Caller-ID: oas-backend
X-Caller-Timestamp: 1782038400
X-Caller-Signature: hex(hmac_sha256(shared_secret, METHOD + "\n" + PATH + "\n" + TIMESTAMP))
```

## Plan Comparison

| Plan Item | Status | Evidence |
|-----------|--------|----------|
| External requests use `Authorization: Bearer <ccx_at_...>` | Done | `frontend/src/api/http.js` sends Bearer tokens; middleware no longer accepts `session_token` query auth. |
| Login returns access/refresh token pair | Existing draft preserved | Existing `backend-agent/app/routers/auth.py` dual-token login path remains in place. |
| Tokens are opaque Redis sessions, not JWT | Existing draft preserved | Existing `backend-agent/app/redis_token_manager.py` uses `ccx_at_` / `ccx_rt_` opaque tokens and Redis hashes. |
| Access token validation refreshes sliding TTL | Verified | `backend-agent/tests/test_redis_token_manager.py::test_validate_access_token_refreshes_expiry`. |
| Refresh token rotates token pair | Verified | `backend-agent/tests/test_redis_token_manager.py::test_refresh_token_rotates_pair`. |
| Internal OAS requests can bypass user token with caller headers | Done | `backend-agent/app/internal_auth.py` and middleware internal branch. |
| Backend distinguishes internal/external | Done | `request.state.auth_source` and `request.state.caller_id` set in middleware. |
| No cookies | Done | No cookie usage added; frontend continues Bearer headers/sessionStorage. |
| Route-level permissions are not implemented | Done | No route permission map added. |
| Change log written | Done | This file. |
| Subagent review | Done | Initial reviewer found Important issues; fixes are summarized below. |

## Verification Results

Completed:

```text
python -m compileall backend-agent\app
```

Result: passed after implementation.

```text
python -m unittest backend-agent.tests.test_internal_auth backend-agent.tests.test_auth_middleware backend-agent.tests.test_redis_token_manager -v
```

Result: 14 tests passed.

After reviewer fixes:

```text
python -m unittest backend-agent.tests.test_internal_auth backend-agent.tests.test_auth_middleware backend-agent.tests.test_redis_token_manager -v
```

Result: 17 tests passed.

```text
cd frontend
npm ci
npm run build
```

Result: dependency install succeeded; frontend production build passed. Vite emitted a non-fatal warning that `frontend/src/api/auth.js` is both dynamically and statically imported.

```text
cd backend-agent\web
npm run build
```

Result: backend-served web source build passed.

Final verification after fixing reviewer findings and chat attachment URL handling:

```text
python -m compileall backend-agent\app
python -m unittest backend-agent.tests.test_internal_auth backend-agent.tests.test_auth_middleware backend-agent.tests.test_redis_token_manager -v
cd frontend && npm run build
cd backend-agent\web && npm run build
```

Result: backend compile passed; 17 auth tests passed; both frontend builds passed. The frontend build still emits the existing non-fatal Vite warning about `frontend/src/api/auth.js` being both dynamically and statically imported.

Blocked / not run yet:

```text
python -m pytest ...
```

Result: blocked because the current Python environment does not have `pytest` installed.

Remaining:

- Final summary only.

## Non-Goals

- No route-level permission matrix in this iteration.
- No JWT.
- No Cookie auth.
- No body hash in internal HMAC signature.
- No rewrite of existing access/refresh token draft.

## Subagent Review Summary

Initial subagent audit found no Critical issues and four Important gaps:

1. `fetchWithAuth()` did not refresh-and-retry on 401.
2. `session_token` query authentication conflicted with Bearer-only requirements.
3. `web_server.py` did not clear the global dual-token manager when dual-token auth was disabled.
4. Tests were missing regressions for query-token rejection and no legacy fallback when Redis manager exists.

Fixes applied:

- `fetchWithAuth()` now attempts token refresh and retries once before reporting auth failure.
- Middleware no longer reads `session_token` query parameters.
- `urlWithAuthToken()` no longer appends token values to URLs.
- AI status SSE stream now uses `fetchWithAuth()` and parses the stream from `ReadableStream`.
- Document download now uses authenticated `fetchWithAuth()` and Blob object URLs.
- Chat message media/file attachments now use authenticated `fetchWithAuth()` and Blob object URLs.
- `web_server.py` now calls `set_dual_token_manager(None)` in the disabled branch.
- Added middleware regression tests for incomplete internal headers, query token rejection, and no legacy HMAC fallback when the Redis manager exists.

Final subagent review:

- Critical findings: none.
- Important findings: none.
- Minor finding: `auth_middleware.py` docstring was stale. Fixed by updating the middleware priority description.
- Final assessment: acceptable; plan success criteria are met at code level.
