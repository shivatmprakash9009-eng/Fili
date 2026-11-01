"""Unit & Integration Tests for the Multi-Agent System."""

import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from core.task import Task, TaskPriority, TaskStatus
from core.message_bus import MessageBus, MessageType
from core.orchestrator import Orchestrator
from agents.lead_researcher import LeadResearcherAgent
from agents.content_writer import ContentWriterAgent
from agents.email_outreach import EmailOutreachAgent
from agents.response_analyzer import ResponseAnalyzerAgent, ResponseCategory
from agents.reporting import ReportingAgent


class TestMultiAgentSystem(unittest.IsolatedAsyncioTestCase):
    """Test suite covering core orchestration and specialized agents."""

    async def asyncSetUp(self):
        self.message_bus = MessageBus()
        self.orchestrator = Orchestrator(message_bus=self.message_bus)

        self.lead_researcher = LeadResearcherAgent()
        self.content_writer = ContentWriterAgent(sender_name="Test Sender")
        self.email_outreach = EmailOutreachAgent(dry_run=True, daily_limit=10)
        self.response_analyzer = ResponseAnalyzerAgent()
        self.reporting = ReportingAgent()

        for agent in [
            self.lead_researcher,
            self.content_writer,
            self.email_outreach,
            self.response_analyzer,
            self.reporting,
        ]:
            self.orchestrator.register_agent(agent)

        await self.orchestrator.initialize_all()

    async def asyncTearDown(self):
        await self.orchestrator.shutdown_all()

    async def test_message_bus_pub_sub(self):
        received_messages = []

        async def subscriber(msg):
            received_messages.append(msg)

        await self.message_bus.subscribe("test.topic", subscriber)
        await self.message_bus.publish("test.topic", {"hello": "world"}, sender="test_suite")

        self.assertEqual(len(received_messages), 1)
        self.assertEqual(received_messages[0].data["hello"], "world")
        self.assertEqual(received_messages[0].sender, "test_suite")

    async def test_lead_researcher(self):
        task = Task(
            task_type="research_leads",
            payload={"target_industry": "SaaS", "target_location": "USA", "max_leads": 3},
        )
        provider_records = [
            {
                "company_name": f"Example {index}",
                "website": f"https://example{index}.test",
                "source_id": f"org_{index}",
                "contact_name": f"Contact {index}",
                "contact_email": f"contact{index}@example.test",
                "contact_verified": True,
            }
            for index in range(3)
        ]
        with patch("agents.lead_researcher.get_apollo_key", return_value="test-key"), patch(
            "agents.lead_researcher.fetch_apollo_leads",
            new=AsyncMock(return_value=provider_records),
        ):
            result = await self.orchestrator.execute_task(task)
        self.assertTrue(result.is_success)
        leads = result.data.get("leads", [])
        self.assertEqual(len(leads), 3)
        self.assertIn("company_name", leads[0])
        self.assertIn("contact_email", leads[0])
        self.assertTrue(leads[0]["outreach_enabled"])
        self.assertGreater(leads[0]["discovery_quality_score"], 0)
        self.assertIsNone(leads[0]["relevance_score"])

    async def test_content_writer_variants(self):
        sample_lead = {
            "company_name": "Acme Corp",
            "contact_name": "Alice Smith",
            "contact_title": "CTO",
            "contact_email": "alice@acme.com",
            "industry": "FinTech",
            "pain_points": ["slow compliance checks"],
        }
        task = Task(
            task_type="generate_content",
            payload={"leads": [sample_lead], "variants": 2, "template_type": "cold_email"},
        )
        result = await self.orchestrator.execute_task(task)
        self.assertTrue(result.is_success)
        items = result.data.get("content_items", [])
        self.assertEqual(len(items), 1)
        self.assertEqual(len(items[0]["variants"]), 2)
        self.assertIn("best_content", items[0])

    async def test_response_analyzer_categorization(self):
        cases = [
            ("Sounds interesting, can we book a 15-minute call on Thursday?", ResponseCategory.MEETING_REQUEST),
            ("Please unsubscribe me from this list immediately.", ResponseCategory.UNSUBSCRIBE),
            ("I am currently out of the office on annual leave.", ResponseCategory.OUT_OF_OFFICE),
            ("We are not interested at this moment. Thanks.", ResponseCategory.NOT_INTERESTED),
            ("Could you send over your pricing and features sheet?", ResponseCategory.NEEDS_INFO),
        ]

        for text, expected_cat in cases:
            task = Task(
                task_type="analyze_response",
                payload={"response_text": text, "lead_info": {"company_name": "Test Co"}},
            )
            result = await self.orchestrator.execute_task(task)
            self.assertTrue(result.is_success)
            self.assertEqual(result.data["category"], expected_cat.value)
            self.assertIn("action_items", result.data)
            self.assertGreater(len(result.data["action_items"]), 0)

    async def test_full_pipeline_execution(self):
        self.orchestrator.define_pipeline(
            "test_lead_gen",
            [
                {
                    "task_type": "research_leads",
                    "payload": {"target_industry": "AI", "target_location": "UK", "max_leads": 2},
                },
                {"task_type": "generate_content", "payload": {"variants": 1}},
                {"task_type": "send_emails", "payload": {}},
                {"task_type": "generate_report", "payload": {"campaign_name": "Test UK Campaign"}},
            ],
        )

        provider_records = [
            {
                "company_name": f"Pipeline Example {index}",
                "website": f"https://pipeline{index}.test",
                "source_id": f"pipeline_org_{index}",
                "contact_name": f"Contact {index}",
                "contact_email": f"contact{index}@pipeline.test",
                "contact_verified": True,
            }
            for index in range(2)
        ]
        with patch("agents.lead_researcher.get_apollo_key", return_value="test-key"), patch(
            "agents.lead_researcher.fetch_apollo_leads",
            new=AsyncMock(return_value=provider_records),
        ):
            results = await self.orchestrator.run_pipeline("test_lead_gen")
        self.assertEqual(len(results), 4)
        for r in results:
            self.assertTrue(r.is_success, f"Step failed: {r.error}")

        # Check final report has full context from deterministic provider fixtures.
        final_report = results[-1].data
        summary = final_report.get("summary", {})
        self.assertEqual(summary.get("total_leads_found"), 2)
        self.assertEqual(summary.get("content_pieces_generated"), 2)
        self.assertEqual(summary.get("emails_sent"), 2)


if __name__ == "__main__":
    unittest.main()
