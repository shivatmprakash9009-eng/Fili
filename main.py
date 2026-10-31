"""
Multi-Agent Lead Generation & Outreach System
==============================================

Main entry point — initializes agents, registers with orchestrator,
defines the lead generation pipeline, and runs it.

Usage:
    python main.py --target "SaaS companies" --location "USA" --max-leads 10
    python main.py --target "FinTech startups" --location "UK" --max-leads 5 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import Settings
from core.message_bus import MessageBus
from core.orchestrator import Orchestrator
from core.task import Task, TaskPriority
from utils.llm_client import LLMClient

from agents.lead_researcher import LeadResearcherAgent
from agents.content_writer import ContentWriterAgent
from agents.email_outreach import EmailOutreachAgent
from agents.response_analyzer import ResponseAnalyzerAgent
from agents.reporting import ReportingAgent


def setup_logging(settings: Settings) -> None:
    """Configure logging based on settings."""
    log_dir = Path(settings.logging.log_file).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, settings.logging.log_level.upper(), logging.INFO),
        format=settings.logging.log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(settings.logging.log_file, mode="a"),
        ],
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="🚀 Multi-Agent Lead Generation & Outreach System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --target "SaaS companies" --location "USA" --max-leads 10
  python main.py --target "FinTech startups" --location "UK" --campaign "Q4 UK Push"
  python main.py --target "AI/ML startups" --dry-run --max-leads 5
        """,
    )
    parser.add_argument(
        "--target",
        type=str,
        default="SaaS companies",
        help="Target industry/niche (default: 'SaaS companies')",
    )
    parser.add_argument(
        "--location",
        type=str,
        default="USA",
        help="Target location (default: 'USA')",
    )
    parser.add_argument(
        "--platform",
        type=str,
        default="apollo",
        choices=["apollo", "indiamart", "google_maps", "linkedin", "web_search"],
        help="Target data source platform (default: 'apollo')",
    )
    parser.add_argument(
        "--campaign-name",
        type=str,
        default="Lead Gen Campaign",
        help="Campaign name for reporting",
    )
    parser.add_argument(
        "--max-leads",
        type=int,
        default=10,
        help="Maximum leads to generate (default: 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Dry run mode — don't actually send emails (default: True)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Live mode — actually send emails (requires SMTP config)",
    )
    parser.add_argument(
        "--variants",
        type=int,
        default=2,
        help="Number of A/B test content variants (default: 2)",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Path to .env configuration file",
    )
    return parser.parse_args()


async def main() -> None:
    """Main async entry point."""
    args = parse_args()

    # ── Load Settings ────────────────────────────────────────────
    settings = Settings.from_env(args.env_file)
    setup_logging(settings)
    logger = logging.getLogger("main")

    print("\n" + "=" * 60)
    print("  🚀 MULTI-AGENT LEAD GENERATION SYSTEM")
    print("=" * 60)
    print(f"  Target:    {args.target}")
    print(f"  Location:  {args.location}")
    print(f"  Campaign:  {args.campaign_name}")
    print(f"  Max Leads: {args.max_leads}")
    print(f"  LLM Provider: {settings.llm.provider.upper()} ({settings.llm.model})")
    print(f"  Dry Run:   {not args.live}")
    print(f"  Variants:  {args.variants}")
    print("=" * 60 + "\n")

    # Validate settings
    warnings = settings.validate()
    for w in warnings:
        logger.warning(f"⚠️  {w}")

    # ── Initialize LLM Client ───────────────────────────────────
    llm_client = LLMClient(
        provider=settings.llm.provider,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
        base_url=settings.llm.base_url,
        timeout=settings.llm.timeout,
    )

    # ── Create Message Bus & Orchestrator ────────────────────────
    message_bus = MessageBus()
    orchestrator = Orchestrator(message_bus=message_bus)

    # ── Create Agents ────────────────────────────────────────────
    lead_researcher = LeadResearcherAgent(
        max_retries=settings.agent.max_retries,
        retry_delay=settings.agent.retry_delay,
    )
    content_writer = ContentWriterAgent(
        sender_name=settings.campaign.default_sender_name,
        max_retries=settings.agent.max_retries,
        retry_delay=settings.agent.retry_delay,
    )
    email_outreach = EmailOutreachAgent(
        smtp_host=settings.email.smtp_host,
        smtp_port=settings.email.smtp_port,
        smtp_user=settings.email.username,
        smtp_password=settings.email.password,
        from_email=settings.email.from_email,
        daily_limit=settings.campaign.daily_email_limit,
        dry_run=not args.live,
        max_retries=settings.agent.max_retries,
        retry_delay=settings.agent.retry_delay,
    )
    response_analyzer = ResponseAnalyzerAgent(
        max_retries=settings.agent.max_retries,
        retry_delay=settings.agent.retry_delay,
    )
    reporting_agent = ReportingAgent(
        max_retries=settings.agent.max_retries,
        retry_delay=settings.agent.retry_delay,
    )

    # Attach LLM client to agents that need it
    for agent in [lead_researcher, content_writer, response_analyzer]:
        agent.set_llm_client(llm_client)

    # ── Register Agents ──────────────────────────────────────────
    for agent in [lead_researcher, content_writer, email_outreach, response_analyzer, reporting_agent]:
        orchestrator.register_agent(agent)

    # ── Initialize All Agents ────────────────────────────────────
    await orchestrator.initialize_all()

    # ── Define Pipeline ──────────────────────────────────────────
    orchestrator.define_pipeline(
        name="lead_generation",
        steps=[
            {
                "task_type": "research_leads",
                "payload": {
                    "target_industry": args.target,
                    "target_location": args.location,
                    "max_leads": args.max_leads,
                    "platform": args.platform,
                },
                "priority": "HIGH",
            },
            {
                "task_type": "generate_content",
                "payload": {
                    "template_type": "cold_email",
                    "campaign_name": args.campaign_name,
                    "variants": args.variants,
                },
                "priority": "HIGH",
            },
            {
                "task_type": "send_emails",
                "payload": {},
                "priority": "MEDIUM",
            },
            {
                "task_type": "generate_report",
                "payload": {"campaign_name": args.campaign_name},
                "priority": "LOW",
            },
        ],
    )

    # ── Run Pipeline ─────────────────────────────────────────────
    print("🔄 Starting pipeline...\n")
    try:
        results = await orchestrator.run_pipeline("lead_generation")

        # Print results summary
        print("\n" + "─" * 60)
        print("  📋 PIPELINE RESULTS")
        print("─" * 60)
        for i, result in enumerate(results, 1):
            status = "✅" if result.is_success else "❌"
            print(f"  Step {i}: {status} {result.status.value} ({result.duration_seconds:.2f}s)")
            if result.error:
                print(f"         Error: {result.error}")

        # Print the formatted report if available
        if results and results[-1].is_success:
            report_text = results[-1].data.get("formatted_report", "")
            if report_text:
                print(f"\n{report_text}")

        # Print LLM usage stats
        stats = llm_client.get_usage_stats()
        if stats["total_requests"] > 0:
            print(f"\n  📊 LLM Usage: {stats['total_requests']} requests, "
                  f"{stats['total_tokens']} tokens, "
                  f"~${stats['estimated_cost_usd']:.4f}")

    except Exception as exc:
        logger.error(f"Pipeline failed: {exc}", exc_info=True)
        print(f"\n❌ Pipeline failed: {exc}")

    finally:
        # ── Graceful Shutdown ────────────────────────────────────
        print("\n🔄 Shutting down...")
        await orchestrator.shutdown_all()
        print("✅ System shut down successfully.\n")

    # Print system status
    status = orchestrator.get_system_status()
    print(f"  Total results: {status['total_results']}")
    print(f"  Agents: {len(status['agents'])}")


if __name__ == "__main__":
    asyncio.run(main())
