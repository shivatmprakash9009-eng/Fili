import unittest

from fastapi.testclient import TestClient

from api_v1 import app


class FiliCorsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_allows_production_dashboard_origin(self):
        response = self.client.get(
            "/v1/health",
            headers={"Origin": "https://fili-nine.vercel.app"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "https://fili-nine.vercel.app",
        )
        self.assertEqual(response.headers.get("access-control-allow-credentials"), None)

    def test_preflight_allows_authorization_header(self):
        response = self.client.options(
            "/v1/usage",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://localhost:8000",
        )
        self.assertIn("GET", response.headers.get("access-control-allow-methods", ""))
        self.assertIn("authorization", response.headers.get("access-control-allow-headers", "").lower())

    def test_preflight_allows_post_and_delete_methods(self):
        for method in ("POST", "DELETE"):
            with self.subTest(method=method):
                response = self.client.options(
                    "/v1/prospects/search",
                    headers={
                        "Origin": "http://127.0.0.1:8000",
                        "Access-Control-Request-Method": method,
                        "Access-Control-Request-Headers": "authorization,content-type",
                    },
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.headers.get("access-control-allow-origin"),
                    "http://127.0.0.1:8000",
                )

    def test_untrusted_origin_is_not_reflected(self):
        response = self.client.get(
            "/v1/health",
            headers={"Origin": "https://attacker.example"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_opaque_null_origin_is_not_allowed(self):
        response = self.client.get(
            "/v1/health",
            headers={"Origin": "null"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("access-control-allow-origin", response.headers)


if __name__ == "__main__":
    unittest.main()
