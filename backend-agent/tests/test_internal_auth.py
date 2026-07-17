from __future__ import annotations

import hashlib
import hmac
import unittest


from app.internal_auth import InternalAuthError, verify_internal_request


def _signature(secret: str, method: str, path: str, timestamp: int) -> str:
    message = f"{method.upper()}\n{path}\n{timestamp}"
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _config() -> dict:
    return {
        "internal_callers": {
            "oas-backend": {
                "shared_secret": "unit-test-secret",
                "ip_allowlist": ["127.0.0.1/32", "10.0.0.0/8"],
                "description": "OAS backend",
            }
        }
    }


class InternalAuthTest(unittest.TestCase):
    def test_valid_internal_signature_is_accepted(self) -> None:
        ts = 1_782_038_400
        caller_id = verify_internal_request(
            config=_config(),
            method="POST",
            path="/api/tasks",
            headers={
                "X-Caller-ID": "oas-backend",
                "X-Caller-Timestamp": str(ts),
                "X-Caller-Signature": _signature("unit-test-secret", "POST", "/api/tasks", ts),
            },
            client_host="127.0.0.1",
            now=ts,
        )
        self.assertEqual(caller_id, "oas-backend")

    def test_no_internal_headers_returns_none(self) -> None:
        self.assertIsNone(
            verify_internal_request(
                config=_config(),
                method="GET",
                path="/api/tasks",
                headers={},
                client_host="127.0.0.1",
                now=1_782_038_400,
            )
        )

    def test_unknown_caller_is_rejected(self) -> None:
        ts = 1_782_038_400
        with self.assertRaises(InternalAuthError):
            verify_internal_request(
                config=_config(),
                method="GET",
                path="/api/tasks",
                headers={
                    "X-Caller-ID": "unknown",
                    "X-Caller-Timestamp": str(ts),
                    "X-Caller-Signature": _signature("unit-test-secret", "GET", "/api/tasks", ts),
                },
                client_host="127.0.0.1",
                now=ts,
            )

    def test_bad_signature_is_rejected(self) -> None:
        ts = 1_782_038_400
        with self.assertRaises(InternalAuthError):
            verify_internal_request(
                config=_config(),
                method="GET",
                path="/api/tasks",
                headers={
                    "X-Caller-ID": "oas-backend",
                    "X-Caller-Timestamp": str(ts),
                    "X-Caller-Signature": "bad-signature",
                },
                client_host="127.0.0.1",
                now=ts,
            )

    def test_expired_timestamp_is_rejected(self) -> None:
        ts = 1_782_038_400
        with self.assertRaises(InternalAuthError):
            verify_internal_request(
                config=_config(),
                method="GET",
                path="/api/tasks",
                headers={
                    "X-Caller-ID": "oas-backend",
                    "X-Caller-Timestamp": str(ts),
                    "X-Caller-Signature": _signature("unit-test-secret", "GET", "/api/tasks", ts),
                },
                client_host="127.0.0.1",
                now=ts + 301,
            )

    def test_ip_allowlist_blocks_unlisted_ip(self) -> None:
        ts = 1_782_038_400
        with self.assertRaises(InternalAuthError):
            verify_internal_request(
                config=_config(),
                method="GET",
                path="/api/tasks",
                headers={
                    "X-Caller-ID": "oas-backend",
                    "X-Caller-Timestamp": str(ts),
                    "X-Caller-Signature": _signature("unit-test-secret", "GET", "/api/tasks", ts),
                },
                client_host="192.168.1.10",
                now=ts,
            )


if __name__ == "__main__":
    unittest.main()
