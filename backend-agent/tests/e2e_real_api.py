"""端到端真实接口测试。

用 fakeredis(async) 替代真实 Redis，但走完整的真实 HTTP 链路：
  uvicorn server (真实中间件 + 路由 + Redis token manager) ← requests HTTP

验证：
  1. Redis 强制必需（未配置时启动报错）
  2. trace_id 全链路（响应头 X-Trace-Id + 日志落库 trace_id）
  3. IP 白名单（空=放行，配置=拒绝未授权来源）
  4. user_type 注册标识（建表迁移 + CRUD + 登录返回）
  5. 双 Token 登录/会话/刷新/注销清除 token
  6. 游客模式登录
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# ── 在导入 web_server 之前 monkeypatch redis.asyncio.from_url → fakeredis ──
import fakeredis.aioredis  # noqa: E402
import redis.asyncio as aioredis  # noqa: E402

_orig_from_url = aioredis.from_url


def _fake_from_url(url, **kwargs):
    # 返回一个共享的 FakeRedis 实例（decode_responses 透传）
    return fakeredis.aioredis.FakeRedis(decode_responses=kwargs.get("decode_responses", False))


aioredis.from_url = _fake_from_url

import requests  # noqa: E402

from app.web_server import create_app  # noqa: E402
import uvicorn  # noqa: E402


def _make_config(project_root: Path, redis_url: str = "redis://127.0.0.1:6379/0", ip_allowlist=None):
    cfg_path = project_root / "config.yaml"
    auth_lines = [
        "auth:",
        "  internal_callers: {}",
    ]
    if ip_allowlist is not None:
        import json

        auth_lines.append("  external_ip_allowlist_enabled: true")
        auth_lines.append("  external_ip_allowlist: " + json.dumps(ip_allowlist))
    else:
        auth_lines.append("  external_ip_allowlist_enabled: false")
        auth_lines.append("  external_ip_allowlist: []")
    lines = [
        f"redis:\n  url: '{redis_url}'\n  at_ttl_seconds: 10800\n  rt_ttl_seconds: 604800",
        "  at_absolute_lifetime_seconds: 86400\n  rt_grace_seconds: 900",
        "\n".join(auth_lines),
    ]
    lines.append("guest_account:\n  enabled: true\n  username: guest\n  password: guest1234")
    lines.append("logging:\n  level: INFO")
    cfg_path.write_text("\n".join(lines), encoding="utf-8")


def _start_server(app, port):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _run():
        try:
            server.run()
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    # 等待端口就绪
    for _ in range(50):
        try:
            requests.get(f"http://127.0.0.1:{port}/api/auth/login", timeout=0.5)
            break
        except Exception:
            time.sleep(0.1)
    return server, t


def _wait_server(port):
    for _ in range(60):
        try:
            requests.get(f"http://127.0.0.1:{port}/", timeout=0.5)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main() -> int:
    failures = []

    def check(name, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            failures.append(name)

    # ── 1. Redis 强制必需 ──
    print("\n=== 1. Redis 强制必需 ===")
    tmp = Path(tempfile.mkdtemp())
    _make_config(tmp, redis_url="")  # 空 url
    try:
        create_app(tmp)
        check("空 redis.url 启动应报错", False, "未抛出 RuntimeError")
    except RuntimeError as e:
        check("空 redis.url 启动报错", "redis.url" in str(e).lower() or "redis" in str(e).lower(), str(e))

    # ── 启动主测试服务（fakeredis）──
    tmp2 = Path(tempfile.mkdtemp())
    _make_config(tmp2, redis_url="redis://127.0.0.1:6379/0", ip_allowlist=None)
    # get_guest_account_config() 用 get_yaml_config()（基于 cwd 的单例），
    # 需切到 tmp 目录使其读到测试 config.yaml
    orig_cwd = os.getcwd()
    os.chdir(tmp2)
    app = create_app(tmp2)
    port = 8799
    server, _thread = _start_server(app, port)
    assert _wait_server(port), "server 未启动"

    base = f"http://127.0.0.1:{port}"
    db_path = app.state.database_path

    # 重置 admin 密码为已知值（默认 hash 明文未知，直接重置以便登录测试）
    from app.db.auth_store import reset_console_user_password

    reset_console_user_password(db_path, username="admin", password="Admin1234")
    admin_pw = "Admin1234"

    # ── 2. trace_id 全链路 ──
    print("\n=== 2. trace_id 全链路 ===")
    # 未登录访问受保护接口 → 401，应带 X-Trace-Id 和 trace_id 字段
    r = requests.get(f"{base}/api/bots", timeout=5)
    check("未登录返回 401", r.status_code == 401, f"status={r.status_code}")
    x_trace = r.headers.get("X-Trace-Id", "")
    check("响应头 X-Trace-Id 存在", bool(x_trace), f"header={x_trace}")
    body = r.json()
    check("响应体 trace_id 存在", bool(body.get("trace_id")), f"body={body}")
    check("trace_id 头与体一致", x_trace == body.get("trace_id"))

    # 该 401 应落库 trace_id 关联的日志（auth_middleware + api_response 各一条）
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT trace_id, level, source, message FROM project_logs WHERE trace_id=? ORDER BY created_at",
        (x_trace,),
    ).fetchall()
    check("401 日志已落库且 trace_id 关联", len(rows) >= 1, f"rows={len(rows)}")
    if rows:
        # 至少一条 WARNING 级别（认证失败）
        has_warning = any(r["level"] == "WARNING" for r in rows)
        check("落库日志含 WARNING 级别", has_warning, f"levels={[r['level'] for r in rows]}")
        # 全链路：auth 中间件落库的日志 source 以 auth: 开头
        has_auth_log = any("auth" in r["source"] for r in rows)
        check("全链路 trace_id 串联 auth 日志", has_auth_log, f"sources={[r['source'] for r in rows]}")
    conn.close()

    # ── 3. IP 白名单 ──
    print("\n=== 3. IP 白名单 ===")
    # 当前服务 allowlist=None（空）→ 放行
    r = requests.get(f"{base}/api/bots", timeout=5)
    check("空白名单放行（返回 401 而非 403）", r.status_code == 401, f"status={r.status_code}")

    # 重启服务配置白名单 10.0.0.0/8（127.0.0.1 不在内）→ 应 403
    tmp3 = Path(tempfile.mkdtemp())
    _make_config(tmp3, ip_allowlist=["10.0.0.0/8"])
    app2 = create_app(tmp3)
    port2 = 8800
    _server2, _t2 = _start_server(app2, port2)
    assert _wait_server(port2), "server2 未启动"
    base2 = f"http://127.0.0.1:{port2}"
    r = requests.get(f"{base2}/api/bots", timeout=5)
    check("白名单拒绝未授权来源 → 403", r.status_code == 403, f"status={r.status_code}")
    check("403 响应带 trace_id", bool(r.json().get("trace_id")))
    check("403 消息=来源 IP 不在白名单内", "白名单" in r.json().get("message", ""))

    # ── 4. user_type 注册标识 ──
    print("\n=== 4. user_type 注册标识 ===")
    # 先用 admin 登录拿 token
    r = requests.post(f"{base}/api/auth/login", json={"username": "admin", "password": admin_pw}, timeout=5)
    check("admin 登录成功", r.status_code == 200 and r.json().get("access_token"), f"status={r.status_code} body={r.text[:200]}")
    admin_token = r.json().get("access_token")
    check("登录返回 user_type", r.json().get("user_type") == "registered", f"ut={r.json().get('user_type')}")

    H = {"Authorization": f"Bearer {admin_token}"}

    # 创建内部标识用户
    r = requests.post(
        f"{base}/api/auth/users",
        json={"username": "svc_internal", "password": "Pass1234", "display_name": "内部服务", "user_type": "internal"},
        headers=H,
        timeout=5,
    )
    check("创建 internal 用户成功", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    check("新建用户 user_type=internal", r.json().get("user", {}).get("user_type") == "internal", f"body={r.text[:200]}")

    # 列表应含 user_type
    r = requests.get(f"{base}/api/auth/users", headers=H, timeout=5)
    users = r.json().get("users", [])
    svc = next((u for u in users if u["username"] == "svc_internal"), None)
    check("用户列表含 user_type 字段", svc and svc.get("user_type") == "internal", f"svc={svc}")

    # 编辑为 external
    r = requests.put(f"{base}/api/auth/users/svc_internal", json={"user_type": "registered", "display_name": "外部"}, headers=H, timeout=5)
    check("编辑 user_type 成功", r.status_code == 200 and r.json().get("user", {}).get("user_type") == "registered", f"body={r.text[:200]}")

    # ── 5. 双 Token 登录/会话/刷新/注销清除 token ──
    print("\n=== 5. 双 Token 登录/会话/刷新/注销 ===")
    r = requests.post(f"{base}/api/auth/login", json={"username": "svc_internal", "password": "Pass1234"}, timeout=5)
    check("svc_internal 登录成功", r.status_code == 200 and r.json().get("access_token"), f"body={r.text[:200]}")
    at = r.json()["access_token"]
    rt = r.json()["refresh_token"]
    check("登录返回 access+refresh token", bool(at) and bool(rt))

    # /session 验证 token 有效
    r = requests.get(f"{base}/api/auth/session", headers={"Authorization": f"Bearer {at}"}, timeout=5)
    check("/session 有效", r.status_code == 200 and r.json().get("user", {}).get("username") == "svc_internal", f"body={r.text[:200]}")

    # 受保护接口带 token 可访问
    r = requests.get(f"{base}/api/bots", headers={"Authorization": f"Bearer {at}"}, timeout=5)
    check("带 token 访问受保护接口 200", r.status_code == 200, f"status={r.status_code}")

    # 刷新 token
    r = requests.post(f"{base}/api/auth/refresh", json={"refresh_token": rt}, timeout=5)
    check("refresh 换新 pair 成功", r.status_code == 200 and r.json().get("access_token"), f"body={r.text[:200]}")
    new_at = r.json()["access_token"]
    check("刷新后旧 access token 失效（grace 内仍可用，但新 token 不同）", new_at != at)

    # 注销 → 清除 token
    r = requests.post(f"{base}/api/auth/logout", headers={"Authorization": f"Bearer {new_at}"}, timeout=5)
    check("logout 成功", r.status_code == 200, f"body={r.text[:200]}")

    # 注销后旧 access token 应失效
    r = requests.get(f"{base}/api/auth/session", headers={"Authorization": f"Bearer {new_at}"}, timeout=5)
    check("注销后 token 失效 → 401", r.status_code == 401, f"status={r.status_code}")

    # 旧 refresh token 刷新应失败
    r = requests.post(f"{base}/api/auth/refresh", json={"refresh_token": rt}, timeout=5)
    check("注销后 refresh token 失效", r.status_code in (400, 401), f"status={r.status_code}")

    # ── 6. 游客模式 ──
    print("\n=== 6. 游客模式 ===")
    r = requests.post(f"{base}/api/auth/login", json={"username": "guest", "password": "guest1234"}, timeout=5)
    check("游客登录成功", r.status_code == 200 and r.json().get("access_token"), f"body={r.text[:200]}")
    g_at = r.json()["access_token"]
    g_user = r.json().get("user", {})
    check("游客 role=guest", g_user.get("role") == "guest", f"user={g_user}")
    check("游客 user_type=guest", g_user.get("user_type") == "guest")

    # 游客无操作权限（改密码应 403）
    r = requests.post(
        f"{base}/api/auth/password",
        json={"current_password": "x", "new_password": "y"},
        headers={"Authorization": f"Bearer {g_at}"},
        timeout=5,
    )
    check("游客改密码被拒 → 403", r.status_code == 403, f"status={r.status_code}")

    # admin 强制下线游客
    r = requests.post(f"{base}/api/auth/users/guest/kick", headers=H, timeout=5)
    check("强制下线游客成功", r.status_code == 200, f"body={r.text[:200]}")

    # 下线后游客 token 失效
    r = requests.get(f"{base}/api/auth/session", headers={"Authorization": f"Bearer {g_at}"}, timeout=5)
    check("下线后游客 token 失效 → 401", r.status_code == 401, f"status={r.status_code}")

    # ── 关闭服务 ──
    try:
        server.should_exit = True
    except Exception:
        pass
    os.chdir(orig_cwd)

    print("\n" + "=" * 50)
    if failures:
        print(f"❌ {len(failures)} 项失败: {failures}")
        return 1
    print("✅ 全部真实接口测试通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
