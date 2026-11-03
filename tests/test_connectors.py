"""GitHub / Hacker News connectors: they must run, and must not fabricate contact data."""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from utils import live_search

GITHUB = {"items": [
    {"id": 1, "html_url": "https://github.com/acme/vec", "homepage": "https://acme.test",
     "description": "Vector DB", "owner": {"login": "acme", "type": "Organization", "html_url": "https://github.com/acme"}},
    {"id": 2, "html_url": "https://github.com/acme/other", "owner": {"login": "Acme"}},
    {"id": 3, "html_url": "https://github.com/solo/tool", "owner": {"login": "solo", "type": "User"}},
]}
HN = {"hits": [
    {"objectID": "10", "title": "Show HN: Fooly – AI notes", "url": "https://fooly.test/app", "author": "alice"},
    {"objectID": "11", "title": "Show HN: Duplicate host", "url": "https://fooly.test/other", "author": "bob"},
    {"objectID": "12", "title": "Show HN: No url", "author": "carol"},
    {"objectID": "13", "title": "Show HN: Internal", "url": "https://news.ycombinator.com/item?id=1"},
]}
FORBIDDEN_FABRICATIONS = ("company_size", "pain_points")


class ConnectorTests(unittest.TestCase):
    def test_quote_plus_is_available_at_module_level(self):
        self.assertTrue(callable(live_search.quote_plus))

    def test_github_leads_have_no_invented_contacts(self):
        with patch.object(live_search, "_request_json", AsyncMock(return_value=GITHUB)):
            leads = asyncio.run(live_search.fetch_github_tech_leads("vector database", "India", 5))
        self.assertEqual([lead["company_name"] for lead in leads], ["acme", "solo"])  # case-insensitive owner dedupe
        for lead in leads:
            self.assertEqual(lead["contact_email"], "")
            self.assertEqual(lead["contact_name"], "")
            self.assertEqual(lead["location"], "")
            self.assertFalse(lead["contact_verified"])
            for field in FORBIDDEN_FABRICATIONS:
                self.assertNotIn(field, lead)
        self.assertEqual(leads[0]["website"], "https://acme.test")

    def test_hacker_news_leads_have_no_invented_contacts(self):
        with patch.object(live_search, "_request_json", AsyncMock(return_value=HN)):
            leads = asyncio.run(live_search.fetch_hacker_news_leads("ai", 5))
        self.assertEqual(len(leads), 1)
        lead = leads[0]
        self.assertEqual(lead["company_name"], "Fooly")
        self.assertEqual(lead["contact_email"], "")
        self.assertEqual(lead["contact_name"], "")
        self.assertEqual(lead["location"], "")
        for field in FORBIDDEN_FABRICATIONS:
            self.assertNotIn(field, lead)

    def test_provider_errors_surface_as_provider_request_error(self):
        boom = AsyncMock(side_effect=live_search.ProviderRequestError("api.github.com", "provider_rate_limit_exceeded", 429))
        with patch.object(live_search, "_request_json", boom):
            with self.assertRaises(live_search.ProviderRequestError):
                asyncio.run(live_search.fetch_github_tech_leads("x", "", 3))


if __name__ == "__main__":
    unittest.main()
