"""Agent behaviour: retry policy, outreach guard, researcher source handling."""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from agents.email_outreach import EmailOutreachAgent, _single_line
from agents.lead_researcher import LeadResearcherAgent
from core.base_agent import BaseAgent
from core.task import Task


class _Flaky(BaseAgent):
    def __init__(self, error):
        super().__init__(name="flaky", max_retries=3, retry_delay=0)
        self.error = error
        self.calls = 0

    def get_capabilities(self):
        return ["x"]

    async def process_task(self, task):
        self.calls += 1
        raise self.error


class RetryPolicyTests(unittest.TestCase):
    def test_programming_and_validation_errors_are_not_retried(self):
        for error in (NameError("quote_plus"), ValueError("bad input"), KeyError("k")):
            agent = _Flaky(error)
            result = asyncio.run(agent.run_task(Task("x", {})))
            self.assertTrue(result.is_failure)
            self.assertEqual(agent.calls, 1, type(error).__name__)

    def test_transient_errors_are_retried(self):
        agent = _Flaky(RuntimeError("temporary"))
        result = asyncio.run(agent.run_task(Task("x", {})))
        self.assertTrue(result.is_failure)
        self.assertEqual(agent.calls, 3)


class OutreachGuardTests(unittest.TestCase):
    def _items(self, enabled):
        return [{"lead": "Acme", "contact_email": "a@acme.test", "best_content": {"subject": "s", "body": "b"},
                 "lead_data": {"outreach_enabled": enabled}}]

    def test_only_verified_leads_are_sent(self):
        agent = EmailOutreachAgent(dry_run=True, rate_limit_delay=0)
        sent = asyncio.run(agent.send_emails({"content_items": self._items(True)}))
        blocked = asyncio.run(agent.send_emails({"content_items": self._items(False)}))
        missing = asyncio.run(agent.send_emails({"content_items": [{**self._items(True)[0], "lead_data": {}}]}))
        self.assertEqual((sent["sent"], blocked["sent"], missing["sent"]), (1, 0, 0))
        self.assertEqual((blocked["skipped"], missing["skipped"]), (1, 1))

    def test_header_injection_is_neutralised(self):
        self.assertNotIn("\n", _single_line("Hi\r\nBcc: victim@example.test"))


class ResearcherTests(unittest.TestCase):
    def _run(self, payload):
        agent = LeadResearcherAgent()
        return asyncio.run(agent.research_leads(payload))

    def test_zero_api_source_ignores_city_filter_instead_of_dropping_everything(self):
        records = [{"company_name": "acme", "website": "https://acme.test", "source_id": "gh:1", "location": ""}]
        scope = {"city": "Pune", "state": "Maharashtra", "country": "India", "state_code": "MH", "country_code": "IN"}
        with patch("agents.lead_researcher.fetch_github_tech_leads", AsyncMock(return_value=records)):
            result = self._run({"target_industry": "vector database", "platform": "github",
                                "target_location": "Pune", "target_location_scope": scope, "max_leads": 3})
        self.assertEqual(result["total"], 1)
        self.assertFalse(result["location_filter_applied"])
        self.assertIn("city filter was not applied", result["message"])

    def test_bare_domain_selects_website_extractor_without_guessing_a_tld(self):
        with patch("agents.lead_researcher.scrape_domain_leads", AsyncMock(return_value=[])) as scrape:
            result = self._run({"target_industry": "acme.com", "platform": "apollo"})
        self.assertEqual(scrape.call_args.kwargs["domain_or_url"], "acme.com")
        self.assertEqual(result["source_status"], "no_results")

    def test_website_extractor_without_a_domain_is_a_clear_error(self):
        with self.assertRaises(ValueError):
            self._run({"target_industry": "stripe", "platform": "domain_scraper"})

    def test_private_hostname_is_reported_not_crashed(self):
        result = self._run({"target_industry": "intranet.local", "platform": "domain_scraper"})
        self.assertEqual(result["source_status"], "invalid_target")
        self.assertEqual(result["leads"], [])

    def test_ip_literal_targets_are_rejected_outright(self):
        with self.assertRaises(ValueError):
            self._run({"target_industry": "http://169.254.169.254/latest", "platform": "domain_scraper"})

    def test_unknown_platform_is_rejected(self):
        with self.assertRaises(ValueError):
            self._run({"target_industry": "x", "platform": "myspace"})


if __name__ == "__main__":
    unittest.main()
