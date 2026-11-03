import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

import api_v1
from api_v1 import KeyCreateRequest, SearchRequest, _hash_api_key

KEY = "fili_live_" + "a" * 40
KEY_ID = "11111111-1111-1111-1111-111111111111"
PROSPECT_ID = "22222222-2222-2222-2222-222222222222"


class FakeDb:
    """Minimal stand-in for Supabase REST: records writes and serves canned reads."""

    def __init__(self, scopes=("prospects:read", "prospects:write", "usage:read")):
        self.calls = []
        self.scopes = list(scopes)
        self.usage_rows = []
        self.active_keys = []
        self.prospects = []
        self.revoke_rows = [{"id": KEY_ID}]

    def __call__(self, method, table, *, params=None, payload=None, prefer=None):
        self.calls.append((method, table, params, payload))
        if table == "fili_api_keys" and method == "GET":
            if params and "key_hash" in params:
                return [{"id": KEY_ID, "owner_uid": "u1", "scopes": self.scopes, "last_used_at": None}], None
            return self.active_keys, None
        if table == "fili_api_keys" and method == "PATCH":
            return self.revoke_rows, None
        if table == "fili_api_usage" and method == "GET":
            offset = int((params or {}).get("offset", 0))
            limit = int((params or {}).get("limit", 1000))
            return self.usage_rows[offset:offset + limit], None
        if table == "fili_prospects" and method == "GET":
            return self.prospects, None
        if table == "fili_prospects" and method == "POST":
            return [{"id": PROSPECT_ID, "source_id": r["source_id"], "payload": r["payload"]} for r in payload], None
        return [], None

    def usage_posts(self):
        return [c[3] for c in self.calls if c[1] == "fili_api_usage" and c[0] == "POST"]


class FiliApiContractTests(unittest.TestCase):
    def test_api_key_hash_is_stable_and_one_way_shape(self):
        digest = _hash_api_key(KEY)
        self.assertEqual(len(digest), 64)
        self.assertEqual(digest, _hash_api_key(KEY))
        self.assertNotEqual(digest, KEY)

    def test_search_request_trims_text_and_bounds_limit(self):
        request = SearchRequest(industry="  SaaS companies ", location=" India ", limit=25)
        self.assertEqual((request.industry, request.location, request.limit), ("SaaS companies", "India", 25))

    def test_search_rejects_excessive_limit_and_empty_sources(self):
        with self.assertRaises(ValidationError):
            SearchRequest(industry="SaaS", limit=101)
        with self.assertRaises(ValidationError):
            SearchRequest(industry="SaaS", sources=[])

    def test_key_scopes_are_allowlisted_and_non_empty(self):
        request = KeyCreateRequest(name="Production", scopes=["prospects:read", "usage:read"])
        self.assertEqual(set(request.scopes), {"prospects:read", "usage:read"})
        with self.assertRaises(ValidationError):
            KeyCreateRequest(name="Bad", scopes=["admin:*"])
        with self.assertRaises(ValidationError):
            KeyCreateRequest(name="Empty", scopes=[])


class ApiBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "k",
            "FIREBASE_PROJECT_ID": "p", "FILI_API_RATE_LIMIT_PER_MINUTE": "3",
        })
        self.env.start()
        api_v1._rate_events.clear()
        self.db = FakeDb()
        self.patch = patch.object(api_v1, "_supabase_request", self.db)
        self.patch.start()
        self.client = TestClient(api_v1.app, raise_server_exceptions=False)
        self.auth = {"Authorization": f"Bearer {KEY}"}

    def tearDown(self):
        self.patch.stop()
        self.env.stop()

    def test_usage_is_logged_with_real_route_and_status(self):
        self.assertEqual(self.client.get(f"/v1/prospects/{PROSPECT_ID}", headers=self.auth).status_code, 404)
        self.assertEqual(self.client.get("/v1/usage", headers=self.auth).status_code, 200)
        rows = [(r["route"], r["status_code"]) for r in self.db.usage_posts()]
        self.assertIn(("GET /v1/prospects/{prospect_id}", 404), rows)
        self.assertIn(("GET /v1/usage", 200), rows)

    def test_missing_scope_is_403_and_logged_as_failure(self):
        self.db.scopes = ["usage:read"]
        response = self.client.get(f"/v1/prospects/{PROSPECT_ID}", headers=self.auth)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.db.usage_posts()[-1]["status_code"], 403)

    def test_non_uuid_ids_are_422_not_503(self):
        self.assertEqual(self.client.get("/v1/prospects/not-a-uuid", headers=self.auth).status_code, 422)
        self.assertEqual(self.client.post("/v1/prospects/research?prospect_id=short", headers=self.auth).status_code, 422)

    def test_rate_limit_is_in_memory_and_returns_retry_after(self):
        codes = [self.client.get(f"/v1/prospects/{PROSPECT_ID}", headers=self.auth).status_code for _ in range(5)]
        self.assertEqual(codes, [404, 404, 404, 429, 429])
        limited = self.client.get(f"/v1/prospects/{PROSPECT_ID}", headers=self.auth)
        self.assertIn("retry-after", limited.headers)
        # Rate limiting must not cost a database read per request.
        reads = [c for c in self.db.calls if c[1] == "fili_api_usage" and c[0] == "GET"]
        self.assertEqual(reads, [])

    def test_invalid_api_key_is_401(self):
        self.assertEqual(self.client.get("/v1/usage", headers={"Authorization": "Bearer nope"}).status_code, 401)
        self.assertEqual(self.client.get("/v1/usage").status_code, 401)

    def test_usage_summary_pages_past_the_rest_row_cap(self):
        self.db.usage_rows = [
            {"id": i, "route": "GET /v1/usage" if i % 2 else "POST /v1/prospects/search",
             "status_code": 200 if i % 10 else 429, "created_at": datetime.now(timezone.utc).isoformat()}
            for i in range(2500)
        ]
        body = self.client.get("/v1/usage", headers=self.auth).json()
        self.assertEqual(body["requests"], 2500)
        self.assertEqual(body["failed"], 250)
        self.assertEqual(sum(body["by_route"].values()), 2500)
        self.assertFalse(body["truncated"])

    def test_search_without_provider_keys_reports_not_configured(self):
        with patch.object(api_v1, "get_apollo_key", return_value=""), patch.object(api_v1, "get_serpapi_key", return_value=""):
            response = self.client.post("/v1/prospects/search", headers=self.auth, json={"industry": "SaaS"})
        self.assertEqual(response.status_code, 200)
        meta = response.json()["meta"]
        self.assertEqual(meta["providers_queried"], [])
        self.assertEqual({e["error"] for e in meta["provider_errors"]}, {"provider_not_configured"})

    def test_daily_search_quota_blocks_with_429(self):
        with patch.dict(os.environ, {"FILI_API_DAILY_SEARCH_LIMIT": "2"}):
            self.db.usage_rows = [{"id": 1}, {"id": 2}]
            response = self.client.post("/v1/prospects/search", headers=self.auth, json={"industry": "SaaS"})
        self.assertEqual(response.status_code, 429)
        self.assertIn("quota", response.json()["error"].lower())

    def test_search_leads_are_normalized_and_outreach_disabled(self):
        raw = [{"company_name": "Acme", "website": "https://acme.test", "source_id": "a1",
                "contact_email": "x@acme.test", "contact_verified": False, "platform": "Apollo.io"}]

        async def fake_apollo(*args, **kwargs):
            return raw
        with patch.object(api_v1, "get_apollo_key", return_value="k"), patch.object(api_v1, "fetch_apollo_leads", fake_apollo):
            response = self.client.post("/v1/prospects/search", headers=self.auth,
                                        json={"industry": "SaaS", "sources": ["apollo"]})
        data = response.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], PROSPECT_ID)
        self.assertFalse(data[0]["outreach_enabled"])
        self.assertIn("discovery_quality_score", data[0])

    def test_unexpected_errors_do_not_leak_details(self):
        with patch.object(api_v1, "_usage_summary", side_effect=RuntimeError("secret-db-password")):
            response = self.client.get("/v1/usage", headers=self.auth)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret", response.text)


class KeyLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "k",
                                           "FIREBASE_PROJECT_ID": "p", "FILI_API_MAX_ACTIVE_KEYS": "2"})
        self.env.start()
        self.db = FakeDb()
        self.patches = [
            patch.object(api_v1, "_supabase_request", self.db),
            patch.object(api_v1, "_verify_firebase_token", return_value={"uid": "u1", "email_verified": True}),
        ]
        for p in self.patches:
            p.start()
        self.client = TestClient(api_v1.app, raise_server_exceptions=False)
        self.auth = {"Authorization": "Bearer firebase-token"}

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.env.stop()

    def test_key_creation_is_capped(self):
        self.db.active_keys = [{"id": "a"}, {"id": "b"}]
        response = self.client.post("/v1/keys", headers=self.auth, json={"name": "Another"})
        self.assertEqual(response.status_code, 409)

    def test_key_creation_returns_secret_once_and_stores_only_hash(self):
        response = self.client.post("/v1/keys", headers=self.auth, json={"name": "Prod"})
        self.assertEqual(response.status_code, 201)
        secret = response.json()["key"]
        stored = [c[3] for c in self.db.calls if c[1] == "fili_api_keys" and c[0] == "POST"][0]
        self.assertEqual(stored["key_hash"], _hash_api_key(secret))
        self.assertNotIn(secret, str(stored))

    def test_revoking_unknown_key_is_404(self):
        self.db.revoke_rows = []
        response = self.client.delete(f"/v1/keys/{KEY_ID}", headers=self.auth)
        self.assertEqual(response.status_code, 404)

    def test_revoking_own_key_succeeds(self):
        self.assertEqual(self.client.delete(f"/v1/keys/{KEY_ID}", headers=self.auth).json(), {"success": True})


if __name__ == "__main__":
    unittest.main()
