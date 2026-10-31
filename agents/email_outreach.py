"""Email Outreach Agent — sends personalized emails with scheduling & rate limiting."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from core.base_agent import BaseAgent
from core.task import Task


class EmailOutreachAgent(BaseAgent):
    """Handles email sending with scheduling, rate limiting, and delivery tracking.

    Supports both real SMTP sending and dry-run mode for testing.
    """

    def __init__(
        self,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
        smtp_user: str = "",
        smtp_password: str = "",
        from_email: str = "",
        daily_limit: int = 50,
        dry_run: bool = True,
        rate_limit_delay: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(name="EmailOutreach", **kwargs)
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email
        self.daily_limit = daily_limit
        self.dry_run = dry_run
        self._sent_today: int = 0
        self._sent_log: list[dict[str, Any]] = []
        self._rate_limit_delay: float = rate_limit_delay if rate_limit_delay is not None else (0.1 if dry_run else 2.0)

    def get_capabilities(self) -> list[str]:
        return ["send_emails", "schedule_email", "track_delivery"]

    async def process_task(self, task: Task) -> dict[str, Any]:
        if task.task_type == "send_emails":
            return await self.send_emails(task.payload)
        elif task.task_type == "schedule_email":
            return await self.schedule_email(task.payload)
        elif task.task_type == "track_delivery":
            return await self.track_delivery(task.payload)
        raise ValueError(f"Unknown task type: {task.task_type}")

    async def send_emails(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send emails to leads from content items.

        Args:
            payload: Should contain 'content_items' (from ContentWriter output).
        """
        content_items = payload.get("content_items", [])
        if not content_items:
            content_items = payload.get("_previous_result", {}).get("content_items", [])

        results: list[dict[str, Any]] = []
        sent = 0
        failed = 0
        skipped = 0

        for item in content_items:
            if self._sent_today >= self.daily_limit:
                self.logger.warning(f"Daily limit ({self.daily_limit}) reached. Stopping.")
                skipped += len(content_items) - sent - failed
                break

            to_email = item.get("contact_email", "")
            content = item.get("best_content", {})
            subject = content.get("subject", "Hello")
            body = content.get("body", "")

            if not to_email:
                self.logger.warning(f"Skipping {item.get('lead', '?')} — no email")
                skipped += 1
                continue

            result = await self.send_email(
                to_email=to_email,
                subject=subject,
                body=body,
                lead_name=item.get("lead", "Unknown"),
            )
            results.append(result)

            if result["status"] == "sent":
                sent += 1
            else:
                failed += 1

            # Rate limiting
            await asyncio.sleep(self._rate_limit_delay)

        return {
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "total": len(content_items),
            "details": results,
            "dry_run": self.dry_run,
        }

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        lead_name: str = "",
    ) -> dict[str, Any]:
        """Send a single email.

        Returns:
            Dict with send status and metadata.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Email to {to_email}: {subject}")
            record = {
                "status": "sent",
                "mode": "dry_run",
                "to": to_email,
                "lead": lead_name,
                "subject": subject,
                "timestamp": timestamp,
                "body_preview": body[:100] + "..." if len(body) > 100 else body,
            }
            self._sent_log.append(record)
            self._sent_today += 1
            return record

        # Real email sending
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_email
            msg["To"] = to_email
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, to_email, msg.as_string())

            self.logger.info(f"Email sent to {to_email}")
            record = {
                "status": "sent",
                "mode": "live",
                "to": to_email,
                "lead": lead_name,
                "subject": subject,
                "timestamp": timestamp,
            }
            self._sent_log.append(record)
            self._sent_today += 1
            return record

        except Exception as exc:
            self.logger.error(f"Failed to send email to {to_email}: {exc}")
            return {
                "status": "failed",
                "to": to_email,
                "lead": lead_name,
                "error": str(exc),
                "timestamp": timestamp,
            }

    async def schedule_email(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Schedule an email for later sending (placeholder).

        In production, this would integrate with a task scheduler like
        Celery, APScheduler, or a cron-based system.
        """
        to_email = payload.get("to_email", "")
        scheduled_at = payload.get("scheduled_at", "")
        self.logger.info(f"Scheduled email to {to_email} at {scheduled_at}")
        return {
            "status": "scheduled",
            "to": to_email,
            "scheduled_at": scheduled_at,
            "message": "Email scheduled (placeholder — integrate with scheduler in production)",
        }

    async def track_delivery(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Get delivery tracking information."""
        return {
            "sent_today": self._sent_today,
            "daily_limit": self.daily_limit,
            "remaining": self.daily_limit - self._sent_today,
            "sent_log": self._sent_log[-20:],  # Last 20
            "total_sent_all_time": len(self._sent_log),
        }
