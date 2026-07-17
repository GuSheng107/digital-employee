from __future__ import annotations

import hashlib
import hmac
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.auth import DualTokenError
from app.auth_middleware import install_auth_middleware


def _signature(secret: str, method: str, path: str, timestamp: int) -> str:
    message = f"{method.upper()}\n{path}\n{timestamp}"
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


class _YamlConfigStub:
    def __init__(self, data: dict) -> None:
        self._data = data

    def as_dict(self) -> dict:
        return self._data


def _app() -> FastAPI:
    app = FastAPI()
    app.state.project_root = Path(tempfile.mkdtemp())
    app.state.database_path = app.state.project_root / "test.db"
    install_auth_middleware(app)

    @app.post("/api/auth/login")
    async def login() -> dict:
        return {"ok": True}

    @app.get("/api/private")
    async def private(request: Request) -> dict:
        return {
            "source": getattr(request.state, "auth_source", ""),
            "caller_id": getattr(request.state, "caller_id", None),
            "username": getattr(request.state, "auth_user", {}).get("username"),
        }

    @app.get("/api/status")
    async def status(request: Request) -> dict:
        return {
            "source": getattr(request.state, "auth_source", ""),
            "role": getattr(request.state, "auth_user", {}).get("role"),
            "user_type": getattr(request.state, "auth_user", {}).get("user_type"),
        }

    return app


class AuthMiddlewareTest(unittest.TestCase):
    def setUp(self) -> None:
        # 认证失败路径会落库一条日志，测试中统一打桩避免依赖真实 SQLite
        self._log_patch = patch("app.auth_middleware.insert_project_log")
        self._log_patch.start()

    def tearDown(self) -> None:
        self._log_patch.stop()

    def test_public_login_path_skips_auth(self) -> None:
        response = TestClient(_app()).post("/api/auth/login")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_internal_auth_sets_internal_state(self) -> None:
        ts = int(time.time())
        config = {
            "auth": {
                "internal_callers": {
                    "oas-backend": {
                        "shared_secret": "internal-secret",
                        "ip_allowlist": [],
                    }
                }
            }
        }
        with patch("app.auth_middleware.get_yaml_config", return_value=_YamlConfigStub(config)):
            response = TestClient(_app()).get(
                "/api/private",
                headers={
                    "X-Caller-ID": "oas-backend",
                    "X-Caller-Timestamp": str(ts),
                    "X-Caller-Signature": _signature("internal-secret", "GET", "/api/private", ts),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "internal")
        self.assertEqual(response.json()["caller_id"], "oas-backend")
        self.assertEqual(response.json()["username"], "internal:oas-backend")

    def test_invalid_internal_auth_returns_403(self) -> None:
        config = {
            "auth": {
                "internal_callers": {
                    "oas-backend": {
                        "shared_secret": "internal-secret",
                        "ip_allowlist": [],
                    }
                }
            }
        }
        with patch("app.auth_middleware.get_yaml_config", return_value=_YamlConfigStub(config)):
            response = TestClient(_app()).get(
                "/api/private",
                headers={
                    "X-Caller-ID": "oas-backend",
                    "X-Caller-Timestamp": str(int(time.time())),
                    "X-Caller-Signature": "bad-signature",
                },
            )

        self.assertEqual(response.status_code, 403)

    def test_incomplete_internal_headers_return_403(self) -> None:
        with patch("app.auth_middleware.get_yaml_config", return_value=_YamlConfigStub({"auth": {}})):
            response = TestClient(_app()).get(
                "/api/private",
                headers={"X-Caller-ID": "oas-backend"},
            )

        self.assertEqual(response.status_code, 403)

    def test_missing_external_token_returns_401(self) -> None:
        with patch("app.auth_middleware.get_yaml_config", return_value=_YamlConfigStub({"auth": {}})):
            response = TestClient(_app()).get("/api/private")

        self.assertEqual(response.status_code, 401)

    def test_ip_allowlist_rejects_unlisted_source(self) -> None:
        config = {"auth": {"external_ip_allowlist_enabled": True, "external_ip_allowlist": ["10.0.0.0/8"]}}
        with patch("app.auth_middleware.get_yaml_config", return_value=_YamlConfigStub(config)):
            response = TestClient(_app()).get(
                "/api/private",
                headers={"Authorization": "Bearer ccx_at_unit"},
            )
        self.assertEqual(response.status_code, 403)

    def test_ip_allowlist_empty_allows_all(self) -> None:
        token_user = SimpleNamespace(username="alice", role="admin")

        async def _validate_access_token(_token: str):
            return token_user

        with (
            patch("app.auth_middleware.get_yaml_config", return_value=_YamlConfigStub({"auth": {"external_ip_allowlist_enabled": False}})),
            patch("app.auth_middleware.get_dual_token_manager", return_value=object()),
            patch("app.auth_middleware.validate_access_token", side_effect=_validate_access_token),
            patch("app.auth_middleware.get_console_user", return_value={"username": "alice", "display_name": "Alice", "role": "admin", "user_type": "registered", "is_active": True}),
        ):
            response = TestClient(_app()).get(
                "/api/private",
                headers={"Authorization": "Bearer ccx_at_unit"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "alice")

    def test_query_session_token_does_not_authenticate(self) -> None:
        async def _validate_access_token(_token: str):
            return SimpleNamespace(username="alice", role="admin")

        with (
            patch("app.auth_middleware.get_yaml_config", return_value=_YamlConfigStub({"auth": {}})),
            patch("app.auth_middleware.get_dual_token_manager", return_value=object()),
            patch("app.auth_middleware.validate_access_token", side_effect=_validate_access_token) as validate,
        ):
            response = TestClient(_app()).get("/api/private?session_token=ccx_at_unit")

        self.assertEqual(response.status_code, 401)
        validate.assert_not_called()

    def test_external_redis_token_sets_external_state(self) -> None:
        token_user = SimpleNamespace(username="alice", role="admin")

        async def _validate_access_token(_token: str):
            return token_user

        with (
            patch("app.auth_middleware.get_yaml_config", return_value=_YamlConfigStub({"auth": {}})),
            patch("app.auth_middleware.get_dual_token_manager", return_value=object()),
            patch("app.auth_middleware.validate_access_token", side_effect=_validate_access_token),
            patch("app.auth_middleware.get_console_user", return_value={"username": "alice", "display_name": "Alice", "role": "admin", "user_type": "registered", "is_active": True}),
        ):
            response = TestClient(_app()).get(
                "/api/private",
                headers={"Authorization": "Bearer ccx_at_unit"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "external")
        self.assertIsNone(response.json()["caller_id"])
        self.assertEqual(response.json()["username"], "alice")

    def test_external_token_for_deleted_user_is_rejected(self) -> None:
        token_user = SimpleNamespace(username="deleted-user", role="user")

        async def _validate_access_token(_token: str):
            return token_user

        with (
            patch("app.auth_middleware.get_yaml_config", return_value=_YamlConfigStub({"auth": {}})),
            patch("app.auth_middleware.get_dual_token_manager", return_value=object()),
            patch("app.auth_middleware.validate_access_token", side_effect=_validate_access_token),
            patch("app.auth_middleware.get_console_user", return_value=None),
        ):
            response = TestClient(_app()).get(
                "/api/private",
                headers={"Authorization": "Bearer ccx_at_deleted"},
            )

        self.assertEqual(response.status_code, 401)

    def test_guest_can_access_seeded_read_route(self) -> None:
        token_user = SimpleNamespace(username="guest", role="guest")

        async def _validate_access_token(_token: str):
            return token_user

        with (
            patch("app.auth_middleware.get_yaml_config", return_value=_YamlConfigStub({"auth": {}})),
            patch("app.auth_middleware.get_dual_token_manager", return_value=object()),
            patch("app.auth_middleware.validate_access_token", side_effect=_validate_access_token),
        ):
            response = TestClient(_app()).get(
                "/api/status",
                headers={"Authorization": "Bearer ccx_at_guest"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "guest")
        self.assertEqual(response.json()["user_type"], "guest")

    def test_guest_cannot_access_unseeded_route(self) -> None:
        token_user = SimpleNamespace(username="guest", role="guest")

        async def _validate_access_token(_token: str):
            return token_user

        with (
            patch("app.auth_middleware.get_yaml_config", return_value=_YamlConfigStub({"auth": {}})),
            patch("app.auth_middleware.get_dual_token_manager", return_value=object()),
            patch("app.auth_middleware.validate_access_token", side_effect=_validate_access_token),
        ):
            response = TestClient(_app()).get(
                "/api/private",
                headers={"Authorization": "Bearer ccx_at_guest"},
            )

        self.assertEqual(response.status_code, 403)

    def test_dual_manager_failure_does_not_fallback_to_legacy_hmac(self) -> None:
        async def _validate_access_token(_token: str):
            raise DualTokenError("bad token")

        with (
            patch("app.auth_middleware.get_yaml_config", return_value=_YamlConfigStub({"auth": {}})),
            patch("app.auth_middleware.get_dual_token_manager", return_value=object()),
            patch("app.auth_middleware.validate_access_token", side_effect=_validate_access_token),
        ):
            response = TestClient(_app()).get(
                "/api/private",
                headers={"Authorization": "Bearer ccx_at_bad"},
            )

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
