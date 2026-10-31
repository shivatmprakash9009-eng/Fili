"""
Autonomous Inbound Handling & Follow-up Demo
===========================================

Simulates the full lifecycle:
1. Research leads
2. Generate personalized outreach
3. Simulate inbound customer responses (hot lead, objection, meeting request, etc.)
4. ResponseAnalyzer agent analyzes each reply (sentiment, intent, action items)
5. ContentWriter agent autonomously drafts contextual follow-ups / meeting invites!
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import Settings
from core.orchestrator import Orchestrator
from core.task import Task
from agents.lead_researcher import LeadResearcherAgent
from agents.content_writer import ContentWriterAgent
from agents.response_analyzer import ResponseAnalyzerAgent, ResponseCategory
from agents.reporting import ReportingAgent


async def main() -> None:
    print("\n" + "=" * 65)
    print("  🤖 AUTONOMOUS MULTI-AGENT INBOUND & FOLLOW-UP SYSTEM")
    print("=" * 65)

    settings = Settings.from_env()
    orchestrator = Orchestrator()

    lead_agent = LeadResearcherAgent()
    writer_agent = ContentWriterAgent(sender_name="Alex Turner (Growth Lead)")
    analyzer_agent = ResponseAnalyzerAgent()
    reporting_agent = ReportingAgent()

    for agent in [lead_agent, writer_agent, analyzer_agent, reporting_agent]:
        orchestrator.register_agent(agent)

    await orchestrator.initialize_all()

    try:
        # Step 1: Research Leads
        print("\n🔍 Step 1: Discovering High-Fit Leads...")
        lead_task = Task("research_leads", {"target_industry": "AI SaaS", "target_location": "USA/UK", "max_leads": 3})
        lead_res = await orchestrator.execute_task(lead_task)
        leads = lead_res.data.get("leads", [])
        print(f"  ✅ Found {len(leads)} qualified leads:")
        for lead in leads:
            print(f"     • {lead['company_name']} ({lead['location']}) - Score: {lead['relevance_score']}/10")

        # Step 2: Generate Outreach
        print("\n✍️  Step 2: Drafting Hyper-Personalized Outreach...")
        write_task = Task("generate_content", {"leads": leads, "variants": 2})
        write_res = await orchestrator.execute_task(write_task)
        content_items = write_res.data.get("content_items", [])
        print(f"  ✅ Generated {len(content_items)} tailored outreach drafts (A/B tested)")

        # Step 3: Simulate realistic inbound responses
        print("\n📨 Step 3: Simulating Inbound Prospect Responses...")
        simulated_inbox = [
            {
                "lead": leads[0],
                "reply": "Hey Alex, this is actually very timely. We are struggling with manual processes. Can we hop on a 15-minute Zoom call on Thursday?",
            },
            {
                "lead": leads[1] if len(leads) > 1 else leads[0],
                "reply": "Could you share a brief case study or pricing sheet first before we jump on a call?",
            },
            {
                "lead": leads[2] if len(leads) > 2 else leads[0],
                "reply": "Not interested at this time, please remove us from your email list.",
            },
        ]

        # Step 4: Analyze responses & autonomously take action
        print("\n🧠 Step 4: ResponseAnalyzer & Autonomous Action Engine...")
        print("-" * 65)

        for i, item in enumerate(simulated_inbox, 1):
            lead = item["lead"]
            reply_text = item["reply"]

            print(f"\n📩 Incoming Reply #{i} from: {lead['contact_name']} @ {lead['company_name']}")
            print(f"   \"{reply_text}\"")

            analysis_task = Task(
                "analyze_response",
                {"response_text": reply_text, "lead_info": lead},
            )
            analysis_res = await orchestrator.execute_task(analysis_task)
            data = analysis_res.data

            cat = data["category"]
            sentiment = data["sentiment"]
            next_action = data["next_action"]

            icon = "🔥" if cat in ["meeting_request", "interested"] else ("ℹ️" if cat == "needs_more_info" else "🚫")
            print(f"   {icon} Intent:     {cat.upper()}")
            print(f"   📊 Sentiment:  {sentiment['label'].upper()} ({sentiment['confidence']:.0%} confidence)")
            print(f"   🎯 Next Step:   {next_action}")

            # Autonomous Follow-Up Drafting
            if cat in [ResponseCategory.MEETING_REQUEST.value, ResponseCategory.INTERESTED.value]:
                follow_up_payload = {
                    "lead": lead,
                    "template": (
                        "Hi {contact_name},\n\n"
                        "Awesome! I'd love to connect. Here is my booking link: "
                        "https://cal.com/alex-growth/15min\n\n"
                        "Feel free to grab whatever slot suits your schedule best.\n\n"
                        "Best,\nAlex Turner"
                    ),
                }
                follow_task = Task("personalize_template", follow_up_payload)
                follow_res = await orchestrator.execute_task(follow_task)
                print("\n   🤖 AUTONOMOUS ACTION TAKEN: Auto-Drafted Booking Invite:")
                for line in follow_res.data["personalized_content"].split("\n"):
                    print(f"      | {line}")

            elif cat == ResponseCategory.NEEDS_INFO.value:
                info_payload = {
                    "lead": lead,
                    "template": (
                        "Hi {contact_name},\n\n"
                        "Attached is our 1-page overview and recent case study for {company_name}.\n"
                        "Let me know if this aligns with your current priorities!\n\n"
                        "Best,\nAlex Turner"
                    ),
                }
                follow_task = Task("personalize_template", info_payload)
                follow_res = await orchestrator.execute_task(follow_task)
                print("\n   🤖 AUTONOMOUS ACTION TAKEN: Auto-Drafted Collateral Dispatch:")
                for line in follow_res.data["personalized_content"].split("\n"):
                    print(f"      | {line}")

            elif cat == ResponseCategory.UNSUBSCRIBE.value:
                print("   🛡️ COMPLIANCE ACTION: Contact marked as DO NOT CONTACT and quarantined.")

            print("-" * 65)

        print("\n✅ Autonomous Inbound Loop Completed Successfully!")

    finally:
        await orchestrator.shutdown_all()


if __name__ == "__main__":
    asyncio.run(main())
