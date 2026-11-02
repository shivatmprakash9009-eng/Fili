"""Reporting Agent — collects metrics and generates campaign reports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.base_agent import BaseAgent
from core.task import Task


class ReportingAgent(BaseAgent):
    """Collects metrics from all agents and generates campaign reports,
    daily/weekly summaries, and analytics."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(name="Reporting", **kwargs)
        self._reports: list[dict[str, Any]] = []

    def get_capabilities(self) -> list[str]:
        return ["generate_report", "collect_metrics", "campaign_summary"]

    async def process_task(self, task: Task) -> dict[str, Any]:
        if task.task_type == "generate_report":
            return await self.generate_report(task.payload)
        elif task.task_type == "collect_metrics":
            return await self.collect_metrics(task.payload)
        elif task.task_type == "campaign_summary":
            return await self.campaign_summary(task.payload)
        raise ValueError(f"Unknown task type: {task.task_type}")

    async def generate_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Generate a comprehensive campaign report.

        Args:
            payload: Should contain pipeline results or metrics data
                     from previous steps.
        """
        # Collect data from payload and pipeline context
        pipeline_context = payload.get("_pipeline_context", {})
        previous_result = payload.get("_previous_result", {})
        # Merge all available sources (payload, context, previous result)
        merged_data = {**pipeline_context, **payload, **previous_result}
        campaign_name = payload.get("campaign_name", "Campaign Report")

        # Extract stats from different pipeline stages
        leads_data = self._extract_stage_data(merged_data, "leads")
        content_data = self._extract_stage_data(merged_data, "content_items")
        email_data = self._extract_stage_data(merged_data, "details")

        total_leads = len(leads_data) if leads_data else merged_data.get("total", 0)
        total_content = len(content_data) if content_data else merged_data.get("total_generated", 0)
        emails_sent = merged_data.get("sent", len(email_data) if email_data else 0)
        emails_failed = merged_data.get("failed", 0)
        is_dry_run = merged_data.get("dry_run", True)

        # Build report
        report = {
            "report_title": campaign_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_leads_found": total_leads,
                "content_pieces_generated": total_content,
                "emails_sent": emails_sent,
                "emails_failed": emails_failed,
                "dry_run_mode": is_dry_run,
            },
            "lead_quality": self._analyze_lead_quality(leads_data),
            "content_performance": self._analyze_content_quality(content_data),
            "email_delivery": {
                "sent": emails_sent,
                "failed": emails_failed,
                "success_rate": (
                    f"{(emails_sent / (emails_sent + emails_failed) * 100):.1f}%"
                    if (emails_sent + emails_failed) > 0
                    else "N/A"
                ),
            },
            "recommendations": self._generate_recommendations(
                total_leads, total_content, emails_sent, emails_failed
            ),
        }

        # Pretty-print the report
        report["formatted_report"] = self._format_report(report)

        self._reports.append(report)
        return report

    async def collect_metrics(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Collect metrics from orchestrator status."""
        system_status = payload.get("system_status", {})
        agents = system_status.get("agents", {})

        agent_metrics: list[dict[str, Any]] = []
        total_tasks = 0
        total_failures = 0

        for agent_id, status in agents.items():
            metrics = status.get("metrics", {})
            processed = metrics.get("tasks_processed", 0)
            failed = metrics.get("tasks_failed", 0)
            total_tasks += processed
            total_failures += failed
            agent_metrics.append({
                "agent": status.get("name", agent_id),
                "state": status.get("state", "unknown"),
                "tasks_processed": processed,
                "tasks_failed": failed,
                "total_duration_seconds": round(metrics.get("total_duration", 0), 2),
            })

        return {
            "agent_metrics": agent_metrics,
            "total_tasks_processed": total_tasks,
            "total_failures": total_failures,
            "success_rate": (
                f"{((total_tasks - total_failures) / total_tasks * 100):.1f}%"
                if total_tasks > 0 else "N/A"
            ),
        }

    async def campaign_summary(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Generate a brief campaign summary."""
        return {
            "total_reports_generated": len(self._reports),
            "latest_report": self._reports[-1] if self._reports else None,
        }

    # ── Private Helpers ───────────────────────────────────────────

    def _extract_stage_data(
        self, data: dict[str, Any], key: str
    ) -> list[dict[str, Any]]:
        """Extract list data from nested pipeline results."""
        if key in data:
            val = data[key]
            return val if isinstance(val, list) else []
        return []

    def _analyze_lead_quality(self, leads: list[dict[str, Any]]) -> dict[str, Any]:
        """Report evidence completeness without pretending it is sales relevance."""
        if not leads:
            return {
                "average_score": 0,
                "score_scale": "0_to_100",
                "scoring_basis": "provider evidence completeness",
                "high_quality": 0,
                "medium_quality": 0,
                "low_quality": 0,
                "total": 0,
            }

        scores = [
            max(0, min(100, float(lead.get("discovery_quality_score") or 0)))
            for lead in leads
        ]
        return {
            "average_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "score_scale": "0_to_100",
            "scoring_basis": "provider evidence completeness",
            "high_quality": sum(1 for score in scores if score >= 80),
            "medium_quality": sum(1 for score in scores if 50 <= score < 80),
            "low_quality": sum(1 for score in scores if score < 50),
            "total": len(scores),
        }

    def _analyze_content_quality(self, content_items: list[dict[str, Any]]) -> dict[str, Any]:
        """Analyze content quality from generated items."""
        if not content_items:
            return {"average_quality_score": 0, "total": 0}

        scores = []
        for item in content_items:
            best = item.get("best_content", {})
            score = best.get("quality_score", 5.0)
            scores.append(score)

        return {
            "average_quality_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "total": len(scores),
        }

    def _generate_recommendations(
        self, leads: int, content: int, sent: int, failed: int
    ) -> list[str]:
        """Generate actionable recommendations."""
        recs: list[str] = []

        if leads == 0:
            recs.append("⚠️ No leads found. Broaden target industry or location.")
        elif leads < 5:
            recs.append("📊 Low lead count. Consider expanding search criteria.")

        if failed > 0 and sent > 0 and failed / (sent + failed) > 0.2:
            recs.append("🔧 High email failure rate. Check email configuration and addresses.")

        if content > sent:
            recs.append("📧 Not all content was sent. Check daily email limits.")

        if not recs:
            recs.append("✅ Campaign executed successfully. Monitor responses for follow-ups.")

        recs.append("💡 Tip: Configure LLM API keys for AI-powered personalization.")
        return recs

    def _format_report(self, report: dict[str, Any]) -> str:
        """Format report as readable text."""
        summary = report["summary"]
        lines = [
            "=" * 60,
            f"  📊 CAMPAIGN REPORT: {report['report_title']}",
            f"  Generated: {report['generated_at']}",
            "=" * 60,
            "",
            "  📋 SUMMARY",
            f"    Leads Found:       {summary['total_leads_found']}",
            f"    Content Generated: {summary['content_pieces_generated']}",
            f"    Emails Sent:       {summary['emails_sent']}",
            f"    Emails Failed:     {summary['emails_failed']}",
            f"    Dry Run Mode:      {'Yes' if summary['dry_run_mode'] else 'No'}",
            "",
            "  📈 LEAD QUALITY",
        ]

        lq = report.get("lead_quality", {})
        lines += [
            f"    Average Evidence Score: {lq.get('average_score', 'N/A')}/100",
            f"    High Quality:  {lq.get('high_quality', 0)}",
            f"    Medium:        {lq.get('medium_quality', 0)}",
            f"    Low:           {lq.get('low_quality', 0)}",
            "",
            "  📧 EMAIL DELIVERY",
            f"    Success Rate:  {report.get('email_delivery', {}).get('success_rate', 'N/A')}",
            "",
            "  💡 RECOMMENDATIONS",
        ]

        for rec in report.get("recommendations", []):
            lines.append(f"    • {rec}")

        lines += ["", "=" * 60]
        return "\n".join(lines)
