import unittest
from unittest.mock import AsyncMock, patch

from utils.lead_quality import (
    deduplicate_leads,
    match_selected_location,
    normalize_discovered_lead,
)
from utils.live_search import fetch_apollo_leads


class LeadQualityTests(unittest.TestCase):
    def setUp(self):
        self.scope = {
            "city": "New York",
            "state": "New York",
            "state_code": "NY",
            "country": "United States",
            "country_code": "US",
        }

    def test_city_match_uses_full_address_component(self):
        self.assertTrue(match_selected_location(
            "350 Fifth Avenue, New York, NY 10118, United States",
            self.scope,
        )[0])
        wrong_city_scope = {**self.scope, "city": "York"}
        self.assertFalse(match_selected_location(
            "350 Fifth Avenue, New York, NY 10118, United States",
            wrong_city_scope,
        )[0])

    def test_wrong_state_is_rejected(self):
        address = "New York, California, United States"
        self.assertFalse(match_selected_location(address, self.scope)[0])


    def test_explicit_wrong_country_is_rejected(self):
        address = "Austin, Texas, USA"
        self.assertFalse(match_selected_location(address, {
            "city": "Austin",
            "state": "Texas",
            "state_code": "TX",
            "country": "India",
            "country_code": "IN",
        })[0])

    def test_missing_location_is_not_verified(self):
        self.assertEqual(
            match_selected_location("", self.scope)[1],
            "insufficient_location_evidence",
        )

    def test_normalization_never_invents_contact_details(self):
        lead = normalize_discovered_lead(
            {
                "company_name": "Acme Technologies",
                "website": "acme.example",
                "location": "New York, New York, United States",
                "source_id": "org_123",
            },
            provider="Example Provider",
            target_industry="Software",
            location_scope=self.scope,
        )
        self.assertEqual(lead["contact_email"], "")
        self.assertEqual(lead["phone"], "")
        self.assertEqual(lead["contact_name"], "")
        self.assertFalse(lead["contact_verified"])
        self.assertFalse(lead["outreach_enabled"])
        self.assertTrue(lead["location_verified"])
        self.assertIn("selected_city_and_state_match", lead["quality_signals"])

    def test_placeholder_contact_data_is_removed(self):
        lead = normalize_discovered_lead(
            {
                "company_name": "Acme",
                "contact_email": "info@acme.example",
                "phone": "+1-555-0199",
            },
            provider="Example Provider",
            target_industry="Software",
        )
        self.assertEqual(lead["contact_email"], "info@acme.example")
        self.assertEqual(lead["phone"], "")
        self.assertFalse(lead["outreach_enabled"])

    def test_deduplication_prefers_source_identity_and_domain(self):
        leads = [
            {"company_name": "Acme", "platform": "Maps", "source_id": "place_1", "website": "https://acme.example"},
            {"company_name": "Acme Ltd", "platform": "Maps", "source_id": "place_1", "website": "https://acme.example"},
            {"company_name": "Other Company", "platform": "Maps", "source_id": "place_2", "website": "https://other.example"},
        ]
        self.assertEqual(len(deduplicate_leads(leads)), 2)


class ApolloConnectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_endpoint_and_no_guessed_contacts(self):
        payload = {
            "organizations": [{
                "id": "org_1",
                "name": "Example Ltd",
                "primary_domain": "example.test",
                "city": "Austin",
                "state": "Texas",
                "country": "United States",
            }]
        }
        with patch("utils.live_search._request_json", new=AsyncMock(return_value=payload)) as request:
            results = await fetch_apollo_leads(
                industry="SaaS",
                location="Austin, Texas, United States",
                max_leads=5,
                api_key="test-key",
            )
        self.assertEqual(len(results), 1)
        self.assertTrue(request.call_args.args[1].endswith("/api/v1/mixed_companies/search"))
        self.assertEqual(results[0]["contact_email"], "")
        self.assertEqual(results[0]["phone"], "")
        self.assertFalse(results[0]["contact_verified"])


if __name__ == "__main__":
    unittest.main()
