"""
Persistent Database Manager (SQLite)
=====================================
Stores campaigns, leads, content variants, and analytics persistently
so data survives server restarts and session resets.
"""

from __future__ import annotations

import sqlite3
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("database")

DEFAULT_DB_PATH = Path("data/fili_leads.db")


class DatabaseManager:
    """Manages SQLite database connections and CRUD operations for Fili."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database tables if they don't exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_name TEXT UNIQUE NOT NULL,
                    target_industry TEXT,
                    target_location TEXT,
                    platform TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id INTEGER,
                    company_name TEXT NOT NULL,
                    website TEXT,
                    industry TEXT,
                    location TEXT,
                    contact_name TEXT,
                    contact_title TEXT,
                    contact_email TEXT,
                    phone TEXT,
                    company_size TEXT,
                    relevance_score REAL,
                    data_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS content_variants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER,
                    subject TEXT,
                    body TEXT,
                    channel TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (lead_id) REFERENCES leads (id)
                )
            """)
            conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    def save_campaign_results(
        self,
        campaign_name: str,
        target_industry: str,
        target_location: str,
        platform: str,
        leads: list[dict[str, Any]],
        content_list: list[dict[str, Any]],
    ) -> int:
        """Save campaign execution results to database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO campaigns (campaign_name, target_industry, target_location, platform)
                VALUES (?, ?, ?, ?)
                """,
                (campaign_name, target_industry, target_location, platform),
            )
            cursor.execute(
                "SELECT id FROM campaigns WHERE campaign_name = ?", (campaign_name,)
            )
            row = cursor.fetchone()
            campaign_id = row["id"] if row else 1

            for lead in leads:
                cursor.execute(
                    """
                    INSERT INTO leads (
                        campaign_id, company_name, website, industry, location,
                        contact_name, contact_title, contact_email, phone, company_size,
                        relevance_score, data_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        campaign_id,
                        lead.get("company_name"),
                        lead.get("website"),
                        lead.get("industry"),
                        lead.get("location"),
                        lead.get("contact_name"),
                        lead.get("contact_title"),
                        lead.get("contact_email"),
                        lead.get("phone"),
                        lead.get("company_size"),
                        lead.get("relevance_score", 0.0),
                        json.dumps(lead),
                    ),
                )
            conn.commit()
        logger.info(f"Successfully saved campaign '{campaign_name}' with {len(leads)} leads to DB.")
        return campaign_id

    def get_all_campaigns(self) -> list[dict[str, Any]]:
        """Retrieve all campaigns."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM campaigns ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_leads_for_campaign(self, campaign_id: int) -> list[dict[str, Any]]:
        """Retrieve leads for a specific campaign."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM leads WHERE campaign_id = ?", (campaign_id,))
            return [dict(row) for row in cursor.fetchall()]
