"""Opt-in daily prospecting scheduler using APScheduler."""
from __future__ import annotations

import logging
import os
from typing import Callable

logger = logging.getLogger(__name__)


def start_daily_prospector(job: Callable[[], None]):
    """Start an in-process scheduler only when explicitly enabled."""
    if os.getenv("FILI_DAILY_PROSPECTOR_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        return None
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from zoneinfo import ZoneInfo
        timezone = ZoneInfo(os.getenv("FILI_DAILY_PROSPECTOR_TIMEZONE", "Asia/Kolkata"))
        hour, minute = (int(part) for part in os.getenv("FILI_DAILY_PROSPECTOR_TIME", "09:00").split(":"))
        scheduler = BackgroundScheduler(timezone=timezone, daemon=True)
        scheduler.add_job(job, "cron", hour=hour, minute=minute, id="fili-daily-prospector",
                          replace_existing=True, max_instances=1, coalesce=True)
        scheduler.start()
        logger.info("Daily prospector enabled for %02d:%02d %s", hour, minute, timezone)
        return scheduler
    except Exception:
        logger.exception("Daily prospector could not start")
        return None
