"""Dashboard server: per-user isolation, auth identity, platform whitelist and limits."""

import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import AsyncMock, patch

import dashboard


def call(base, path, method="GET", body=None, headers=None):
    request = urllib.request.Request(base + path, method=method, headers=headers or {},
                                     data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers)


class DashboardServerTests(unittest.TestCase):
    TOKEN = "t" * 32

    @classmethod
    def setUpClass(cls):
        cls.env = patch.dict(os.environ, {"FILI_API_TOKEN": cls.TOKEN, "FILI_CAMPAIGNS_PER_HOUR": "50"})
        cls.env.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.DashboardHandler)
        cls.server.daemon_threads = True
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.env.stop()

    def setUp(self):
        dashboard._USER_STATE.clear()
        dashboard._RATE_EVENTS.clear()

    def headers(self, user="alice", token=None):
        result = {"Authorization": f"Bearer {token or self.TOKEN}", "Content-Type": "application/json"}
        if user:
            result["X-Fili-User"] = user
        return result

    def test_requests_without_token_are_rejected(self):
        status, _, _ = call(self.base, "/api/status")
        self.assertEqual(status, 401)
        status, _, _ = call(self.base, "/api/status", headers=self.headers(token="wrong" * 8))
        self.assertEqual(status, 401)

    def test_user_identity_is_required_for_user_scoped_routes(self):
        status, _, _ = call(self.base, "/api/export.csv", headers=self.headers(user=None))
        self.assertEqual(status, 400)
        status, _, _ = call(self.base, "/api/run-campaign", "POST", {"target": "x"}, self.headers(user="bad user!"))
        self.assertEqual(status, 400)

    def test_exports_never_cross_users(self):
        dashboard.user_state("alice")["latest_leads"] = [{"company_name": "AliceCo"}]
        status, body, _ = call(self.base, "/api/export.csv", headers=self.headers("alice"))
        self.assertEqual(status, 200)
        self.assertIn(b"AliceCo", body)
        status, _, _ = call(self.base, "/api/export.csv", headers=self.headers("bob"))
        self.assertEqual(status, 409)  # bob has nothing, and cannot see alice's leads

    def test_platform_whitelist_includes_zero_api_sources_and_rejects_unknown(self):
        for platform in ("github", "hacker_news", "domain_scraper"):
            self.assertIn(platform, dashboard.ALLOWED_PLATFORMS)
        status, _, _ = call(self.base, "/api/run-campaign", "POST",
                            {"target": "x", "platform": "myspace", "campaign_name": "c", "location": "India"}, self.headers())
        self.assertEqual(status, 400)

    def test_campaign_runs_without_city_scope_and_stores_per_user(self):
        result = {"success": True, "leads": [{"company_name": "Acme"}]}
        with patch.object(dashboard, "execute_campaign", AsyncMock(return_value=result)) as run:
            status, body, _ = call(self.base, "/api/run-campaign", "POST",
                                   {"target": "acme.com", "platform": "domain_scraper", "campaign_name": "c", "location": "Global"},
                                   self.headers("alice"))
        self.assertEqual(status, 200, body)
        self.assertEqual(run.call_args.args[-2:], (None, "alice"))

    def test_partial_location_scope_is_rejected(self):
        status, _, _ = call(self.base, "/api/run-campaign", "POST",
                            {"target": "x", "platform": "apollo", "campaign_name": "c",
                             "location_scope": {"country": "India", "city": "Pune"}}, self.headers())
        self.assertEqual(status, 400)

    def test_concurrent_campaign_for_same_user_is_409(self):
        with dashboard.campaign_slot("alice"):
            status, _, _ = call(self.base, "/api/run-campaign", "POST",
                                {"target": "x", "platform": "apollo", "campaign_name": "c", "location": "India"},
                                self.headers("alice"))
        self.assertEqual(status, 409)

    def test_campaign_rate_limit_returns_429_with_retry_after(self):
        with patch.dict(os.environ, {"FILI_CAMPAIGNS_PER_HOUR": "1"}), \
             patch.object(dashboard, "execute_campaign", AsyncMock(return_value={"success": True, "leads": []})):
            body = {"target": "x", "platform": "apollo", "campaign_name": "c", "location": "India"}
            first, _, _ = call(self.base, "/api/run-campaign", "POST", body, self.headers("carol"))
            second, _, headers = call(self.base, "/api/run-campaign", "POST", body, self.headers("carol"))
        self.assertEqual((first, second), (200, 429))
        self.assertIn("Retry-After", headers)

    def test_rate_limiter_window(self):
        self.assertEqual(dashboard.rate_limited("u", "b", 2), 0)
        self.assertEqual(dashboard.rate_limited("u", "b", 2), 0)
        self.assertGreater(dashboard.rate_limited("u", "b", 2), 0)
        self.assertEqual(dashboard.rate_limited("other", "b", 2), 0)


class LocalModeTests(unittest.TestCase):
    def test_without_token_the_single_local_owner_is_used(self):
        with patch.dict(os.environ, {"FILI_API_TOKEN": ""}):
            handler = dashboard.DashboardHandler.__new__(dashboard.DashboardHandler)
            handler.headers = {}
            self.assertEqual(handler._owner(), dashboard.LOCAL_OWNER)


if __name__ == "__main__":
    unittest.main()
