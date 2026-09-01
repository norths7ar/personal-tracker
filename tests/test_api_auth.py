import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import create_app
from api.security import create_session_token, get_auth_config, session_is_valid


class ApiAuthenticationTest(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "AUTH_ENABLED": "true",
                "APP_PASSWORD": "correct horse",
                "APP_SESSION_SECRET": "test-only-signing-secret",
                "COOKIE_SECURE": "false",
                "APP_SESSION_SECONDS": "3600",
            },
        )
        self.environment.start()
        self.init_db = patch("api.main.init_db")
        self.init_db.start()
        self.client_context = TestClient(create_app())
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.init_db.stop()
        self.environment.stop()

    def test_login_cookie_protects_current_user_endpoint(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(
            self.client.post("/api/auth/login", json={"password": "wrong"}).status_code,
            401,
        )

        response = self.client.post(
            "/api/auth/login", json={"password": "correct horse"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=strict", response.headers["set-cookie"])
        self.assertEqual(
            self.client.get("/api/auth/me").json(), {"authenticated": True}
        )

        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_tampered_and_expired_tokens_are_rejected(self):
        config = get_auth_config()
        token = create_session_token(config, now=100)

        self.assertTrue(session_is_valid(token, config, now=101))
        self.assertFalse(session_is_valid(token + "x", config, now=101))
        self.assertFalse(session_is_valid(token, config, now=3700))

    def test_health_check_does_not_require_authentication(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_favicon_is_served_as_svg_instead_of_spa_html(self):
        response = self.client.get("/favicon.svg")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("image/svg+xml"))
        self.assertIn(b"<svg", response.content)


if __name__ == "__main__":
    unittest.main()
