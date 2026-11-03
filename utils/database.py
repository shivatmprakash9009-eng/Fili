"""
Persistent Database Manager (SQLite)
=====================================
Stores campaigns, leads, content variants, and analytics persistently
so data survives server restarts and session resets.

Every campaign belongs to an owner (``owner_uid``) so users never share rows,
and leads are de-duplicated inside a campaign so recurring runs (for example
the daily prospector) do not pile up duplicates.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit

logger = logging.getLogger("database")

DEFAULT_DB_PATH = Path("data/fili_leads.db")
LOCAL_OWNER = "local"


def _lead_dedupe_key(lead: dict[str, Any]) -> str:
    """Stable identity for a lead inside one campaign."""
    source_id = str(lead.get("source_id") or "").strip().casefold()
    if source_id:
        return f"id:{source_id}"
    website = str(lead.get("website") or "").strip()
    host = ""
    if website:
        try:
            host = (urlsplit(website if "://" in website else f"https://{website}").hostname or "").casefold()
        except ValueError:
            host = ""
    host = host.removeprefix("www.")
    name = re.sub(r"[^a-z0-9]+", " ", str(lead.get("company_name") or "").casefold()).strip()
    location = re.sub(r"[^a-z0-9]+", " ", str(lead.get("location") or "").casefold()).strip()
    if host:
        return f"domain:{host}:{location}"
    return f"name:{name}:{location}"


class DatabaseManager:
    """Manages SQLite database connections and CRUD operations for Fili."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Open a connection, commit on success, roll back on error, always close."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}

    def _init_db(self) -> None:
        """Create tables and upgrade databases created by older versions."""
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS campaigns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_uid TEXT NOT NULL DEFAULT 'local',
                    campaign_name TEXT NOT NULL,
                    target_industry TEXT,
                    target_location TEXT,
                    platform TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (owner_uid, campaign_name)
                )
            """)
            if "owner_uid" not in self._columns(conn, "campaigns"):
                # Old schema had a global UNIQUE(campaign_name); SQLite cannot drop it, so rebuild the
                # table (create new, copy, drop old, rename). Foreign keys are not enforced on this
                # connection, so existing leads keep pointing at the same campaign ids.
                conn.execute("""
                    CREATE TABLE campaigns_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        owner_uid TEXT NOT NULL DEFAULT 'local',
                        campaign_name TEXT NOT NULL,
                        target_industry TEXT,
                        target_location TEXT,
                        platform TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (owner_uid, campaign_name)
                    )
                """)
                conn.execute("""
                    INSERT INTO campaigns_new (id, owner_uid, campaign_name, target_industry,
                                               target_location, platform, created_at)
                    SELECT id, 'local', campaign_name, target_industry,
                           target_location, platform, created_at FROM campaigns
                """)
                conn.execute("DROP TABLE campaigns")
                conn.execute("ALTER TABLE campaigns_new RENAME TO campaigns")
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
                    dedupe_key TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
                )
            """)
            if "dedupe_key" not in self._columns(conn, "leads"):
                conn.execute("ALTER TABLE leads ADD COLUMN dedupe_key TEXT")
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS leads_campaign_dedupe_idx
                ON leads (campaign_id, dedupe_key)
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
        logger.info(f"Database initialized at {self.db_path}")

    def save_campaign_results(
        self,
        campaign_name: str,
        target_industry: str,
        target_location: str,
        platform: str,
        leads: list[dict[str, Any]],
        content_list: list[dict[str, Any]],
        owner_uid: str = LOCAL_OWNER,
    ) -> int:
        """Save campaign results for one owner; repeated leads are skipped."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO campaigns (owner_uid, campaign_name, target_industry, target_location, platform)
                VALUES (?, ?, ?, ?, ?)
                """,
                (owner_uid, campaign_name, target_industry, target_location, platform),
            )
            cursor.execute(
                "SELECT id FROM campaigns WHERE owner_uid = ? AND campaign_name = ?",
                (owner_uid, campaign_name),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Campaign row could not be created.")
            campaign_id = row["id"]

            inserted = 0
            for lead in leads:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO leads (
                        campaign_id, company_name, website, industry, location,
                        contact_name, contact_title, contact_email, phone, company_size,
                        relevance_score, data_json, dedupe_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        lead.get("relevance_score"),
                        json.dumps(lead, default=str),
                        _lead_dedupe_key(lead),
                    ),
                )
                inserted += cursor.rowcount
        logger.info(
            f"Saved campaign '{campaign_name}': {inserted} new of {len(leads)} leads (owner={owner_uid})."
        )
        return campaign_id

    def get_all_campaigns(self, owner_uid: str | None = None) -> list[dict[str, Any]]:
        """Retrieve campaigns, optionally limited to one owner."""
        with self._connection() as conn:
            if owner_uid is None:
                rows = conn.execute("SELECT * FROM campaigns ORDER BY created_at DESC, id DESC")
            else:
                rows = conn.execute(
                    "SELECT * FROM campaigns WHERE owner_uid = ? ORDER BY created_at DESC, id DESC",
                    (owner_uid,),
                )
            return [dict(row) for row in rows.fetchall()]

    def get_leads_for_campaign(self, campaign_id: int, owner_uid: str | None = None) -> list[dict[str, Any]]:
        """Retrieve leads for a campaign, optionally enforcing ownership."""
        with self._connection() as conn:
            if owner_uid is None:
                rows = conn.execute("SELECT * FROM leads WHERE campaign_id = ?", (campaign_id,))
            else:
                rows = conn.execute(
                    """
                    SELECT leads.* FROM leads
                    JOIN campaigns ON campaigns.id = leads.campaign_id
                    WHERE leads.campaign_id = ? AND campaigns.owner_uid = ?
                    """,
                    (campaign_id, owner_uid),
                )
            return [dict(row) for row in rows.fetchall()]
