"""Unit tests for SQLite DatabaseManager."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from utils.database import DatabaseManager


def lead(name="TestCorp", **extra):
    return {"company_name": name, "website": f"https://{name.lower()}.test", "industry": "SaaS",
            "location": "USA", "contact_email": "", **extra}


class TestDatabaseManager(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test.db"
        self.db = DatabaseManager(self.db_path)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def save(self, leads, name="Camp", owner="local"):
        return self.db.save_campaign_results(name, "SaaS", "USA", "apollo", leads, [], owner_uid=owner)

    def test_save_and_retrieve_campaign(self) -> None:
        campaign_id = self.save([lead("TestCorp", relevance_score=9.5)], name="Test Campaign 1")
        self.assertGreater(campaign_id, 0)
        campaigns = self.db.get_all_campaigns()
        self.assertEqual([c["campaign_name"] for c in campaigns], ["Test Campaign 1"])
        db_leads = self.db.get_leads_for_campaign(campaign_id)
        self.assertEqual(len(db_leads), 1)
        self.assertEqual(db_leads[0]["company_name"], "TestCorp")

    def test_repeated_runs_do_not_duplicate_leads(self) -> None:
        campaign_id = self.save([lead("Acme"), lead("Beta")], name="Daily Prospector")
        again = self.save([lead("Acme"), lead("Gamma")], name="Daily Prospector")
        self.assertEqual(campaign_id, again)
        names = sorted(row["company_name"] for row in self.db.get_leads_for_campaign(campaign_id))
        self.assertEqual(names, ["Acme", "Beta", "Gamma"])

    def test_owners_are_isolated_even_with_same_campaign_name(self) -> None:
        a = self.save([lead("Acme")], name="Q4", owner="alice")
        b = self.save([lead("Acme")], name="Q4", owner="bob")
        self.assertNotEqual(a, b)
        self.assertEqual(len(self.db.get_all_campaigns("alice")), 1)
        self.assertEqual(self.db.get_leads_for_campaign(a, owner_uid="bob"), [])
        self.assertEqual(len(self.db.get_leads_for_campaign(a, owner_uid="alice")), 1)

    def test_legacy_database_is_migrated_in_place(self) -> None:
        legacy = Path(self.tmp_dir.name) / "legacy.db"
        conn = sqlite3.connect(legacy)
        conn.executescript("""
            CREATE TABLE campaigns (id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_name TEXT UNIQUE NOT NULL,
                target_industry TEXT, target_location TEXT, platform TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE leads (id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER, company_name TEXT NOT NULL,
                website TEXT, industry TEXT, location TEXT, contact_name TEXT, contact_title TEXT, contact_email TEXT,
                phone TEXT, company_size TEXT, relevance_score REAL, data_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            INSERT INTO campaigns (campaign_name) VALUES ('Old');
            INSERT INTO leads (campaign_id, company_name) VALUES (1, 'OldCo');
        """)
        conn.commit()
        conn.close()
        db = DatabaseManager(legacy)
        self.assertEqual(db.get_all_campaigns("local")[0]["campaign_name"], "Old")
        self.assertEqual(db.get_leads_for_campaign(1)[0]["company_name"], "OldCo")
        # New behaviour works on the migrated file: same name, different owner.
        db.save_campaign_results("Old", "x", "y", "apollo", [lead("New")], [], owner_uid="alice")
        self.assertEqual(len(db.get_all_campaigns()), 2)


if __name__ == "__main__":
    unittest.main()
