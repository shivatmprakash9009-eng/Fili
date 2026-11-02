"""Unit tests for SQLite DatabaseManager."""

import unittest
from pathlib import Path
import tempfile

from utils.database import DatabaseManager


class TestDatabaseManager(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test.db"
        self.db = DatabaseManager(self.db_path)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_save_and_retrieve_campaign(self) -> None:
        leads = [
            {
                "company_name": "TestCorp",
                "website": "https://testcorp.com",
                "industry": "SaaS",
                "location": "USA",
                "contact_name": "John Doe",
                "contact_title": "CEO",
                "contact_email": "john@testcorp.com",
                "phone": "+1-555-0100",
                "company_size": "50 employees",
                "relevance_score": 9.5,
            }
        ]
        campaign_id = self.db.save_campaign_results(
            campaign_name="Test Campaign 1",
            target_industry="SaaS",
            target_location="USA",
            platform="apollo",
            leads=leads,
            content_list=[],
        )
        self.assertGreater(campaign_id, 0)

        campaigns = self.db.get_all_campaigns()
        self.assertEqual(len(campaigns), 1)
        self.assertEqual(campaigns[0]["campaign_name"], "Test Campaign 1")

        db_leads = self.db.get_leads_for_campaign(campaign_id)
        self.assertEqual(len(db_leads), 1)
        self.assertEqual(db_leads[0]["company_name"], "TestCorp")


if __name__ == "__main__":
    unittest.main()
