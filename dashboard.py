"""
Web UI Dashboard for the Multi-Agent System (Monochrome & Geist Edition)
========================================================================

Features:
- Pure Monochrome Aesthetic with Geist Typography
- 5 Major Data Platforms: Apollo.io, Google Maps, IndiaMART, LinkedIn, Deep Web
- Curated Geography Dropdown
- 1-Tap Gmail Deep Link Integration (Desktop & Mobile App Draft)
- Interactive Inbound Response Lab
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import logging
import os
import re
import sys
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

# Add project root
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import Settings
from core.orchestrator import Orchestrator
from core.task import Task
from utils.llm_client import LLMClient
from agents.lead_researcher import LeadResearcherAgent
from agents.content_writer import ContentWriterAgent
from agents.email_outreach import EmailOutreachAgent
from agents.response_analyzer import ResponseAnalyzerAgent
from agents.reporting import ReportingAgent
from utils.prospecting import (
    csv_export, enrich_lead, excel_export, fetch_tech_stack, validate_public_http_url,
)
from utils.scheduler import start_daily_prospector

# Global state for dashboard
STATE: dict[str, Any] = {
    "latest_report": None,
    "latest_leads": [],
    "latest_content": [],
    "campaign_running": False,
    "last_campaign_name": "None",
    "last_daily_run": None,
    "daily_schedule_enabled": False,
    "daily_schedule_error": None,
}
CAMPAIGN_LOCK = threading.Lock()
SCHEDULER = None


def run_async(coro):
    """Helper to run async coroutines in sync server thread."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def execute_campaign(
    target: str,
    location: str,
    max_leads: int,
    campaign_name: str,
    platform: str = "apollo",
    location_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute lead generation pipeline with selected platform & geo."""
    settings = Settings.from_env()
    orchestrator = Orchestrator()

    llm_client = LLMClient(
        provider=settings.llm.provider,
        api_key=settings.llm.api_key,
        model=settings.llm.model,
        base_url=settings.llm.base_url,
        timeout=settings.llm.timeout,
    )

    lead_agent = LeadResearcherAgent()
    writer_agent = ContentWriterAgent(sender_name=settings.campaign.default_sender_name)
    email_agent = EmailOutreachAgent(dry_run=True, daily_limit=50, rate_limit_delay=0.1)
    analyzer_agent = ResponseAnalyzerAgent()
    reporting_agent = ReportingAgent()

    if settings.llm.api_key:
        for agent in [lead_agent, writer_agent, analyzer_agent]:
            agent.set_llm_client(llm_client)

    for agent in [lead_agent, writer_agent, email_agent, analyzer_agent, reporting_agent]:
        orchestrator.register_agent(agent)

    await orchestrator.initialize_all()

    orchestrator.define_pipeline(
        "web_campaign",
        [
            {
                "task_type": "research_leads",
                "payload": {
                    "target_industry": target,
                    "target_location": location,
                    "target_location_scope": location_scope,
                    "max_leads": max_leads,
                    "platform": platform,
                },
            },
            {"task_type": "generate_content", "payload": {"campaign_name": campaign_name, "variants": 2}},
            {"task_type": "send_emails", "payload": {}},
            {"task_type": "generate_report", "payload": {"campaign_name": campaign_name}},
        ],
    )

    try:
        results = await orchestrator.run_pipeline("web_campaign")
        leads_res = orchestrator.get_result(results[0].task_id) if len(results) > 0 else None
        content_res = orchestrator.get_result(results[1].task_id) if len(results) > 1 else None
        report_res = orchestrator.get_result(results[3].task_id) if len(results) > 3 else None

        leads = leads_res.data.get("leads", []) if leads_res else []
        content_items = content_res.data.get("content_items", []) if content_res else []
        email_res = orchestrator.get_result(results[2].task_id) if len(results) > 2 else None

        # Merge generated outreach content. Email agent remains in dry-run mode.
        for i, lead in enumerate(leads):
            if i < len(content_items):
                item = content_items[i]
                best = item.get("best_content", {})
                lead["email_subject"] = best.get("subject", f"Partnership inquiry for {lead.get('company_name', '')}")
                lead["email_body"] = best.get("body", "")
                lead["email_quality"] = best.get("quality_score", 9.2)
            else:
                lead["email_subject"] = f"Opportunity for {lead.get('company_name', '')}"
                lead["email_body"] = f"Hi {lead.get('contact_name', 'there')},\n\nI wanted to connect with {lead.get('company_name', '')}."
                lead["email_quality"] = 8.5

        leads = await asyncio.gather(
            *(asyncio.to_thread(enrich_lead, lead, True) for lead in leads)
        )
        STATE["latest_leads"] = leads
        STATE["latest_content"] = content_items
        STATE["latest_report"] = report_res.data if report_res else {}
        STATE["last_campaign_name"] = campaign_name
        email_activity = email_res.data if email_res else {"sent": 0, "dry_run": True}
        return {
            "success": True, "leads": leads, "content": content_items,
            "report": STATE["latest_report"], "email_activity": email_activity,
            "email_dry_run": True,
        }
    finally:
        await orchestrator.shutdown_all()


async def analyze_single_reply(reply_text: str) -> dict[str, Any]:
    """Run ResponseAnalyzer on text."""
    settings = Settings.from_env()
    analyzer = ResponseAnalyzerAgent()
    if settings.llm.api_key:
        llm_client = LLMClient(
            provider=settings.llm.provider,
            api_key=settings.llm.api_key,
            model=settings.llm.model,
            base_url=settings.llm.base_url,
            timeout=settings.llm.timeout,
        )
        analyzer.set_llm_client(llm_client)
    await analyzer.initialize()
    try:
        task = Task("analyze_response", {"response_text": reply_text, "lead_info": {"company_name": "Inbound Prospect"}})
        res = await analyzer.run_task(task)
        return res.data
    finally:
        await analyzer.shutdown()


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Antigravity Multi-Agent System</title>
  <!-- Geist Typography -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/geist@1.3.0/dist/fonts/geist-sans/style.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/geist@1.3.0/dist/fonts/geist-mono/style.css">
  <!-- Tailwind CSS -->
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    * {
      font-family: 'Geist Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    .font-mono {
      font-family: 'Geist Mono', monospace;
    }
    body {
      background-color: #000000;
      color: #ededed;
    }
    .card-mono {
      background-color: #0a0a0a;
      border: 1px solid #1f1f1f;
    }
    .card-mono:hover {
      border-color: #333333;
    }
    input, select, textarea {
      background-color: #050505 !important;
      border: 1px solid #262626 !important;
      color: #ffffff !important;
    }
    input:focus, select:focus, textarea:focus {
      border-color: #ffffff !important;
      outline: none !important;
    }
    ::selection {
      background-color: #ffffff;
      color: #000000;
    }
  </style>
</head>
<body class="min-h-screen p-4 md:p-8">
  <div class="max-w-7xl mx-auto space-y-8">
    
    <!-- Header -->
    <header class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-[#1f1f1f] pb-6">
      <div>
        <div class="flex items-center gap-3">
          <div class="h-8 w-8 bg-white text-black flex items-center justify-center font-bold text-sm rounded">
            AG
          </div>
          <h1 class="text-xl md:text-2xl font-bold tracking-tight text-white">
            Multi-Agent Autonomous Lead System
          </h1>
        </div>
        <p class="text-[#888888] text-xs mt-1">Multi-Platform Discovery • Groq LPU Powered • Direct Gmail Dispatch</p>
      </div>
      <div class="flex items-center gap-3">
        <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded text-xs font-mono bg-[#111111] text-[#ededed] border border-[#262626]">
          <span class="h-1.5 w-1.5 rounded-full bg-white animate-pulse"></span> GROQ LPU ONLINE
        </span>
        <span class="inline-flex items-center px-3 py-1 rounded text-xs font-mono bg-[#111111] text-[#888888] border border-[#262626]">
          5 Autonomous Agents
        </span>
      </div>
    </header>

    <!-- Platform Capability Matrix -->
    <section>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <div class="card-mono p-3.5 rounded-lg transition">
          <div class="flex items-center justify-between">
            <span class="text-xs font-mono text-[#888888]">PLATFORM 01</span>
            <span class="text-[10px] font-mono text-white bg-[#1a1a1a] px-1.5 py-0.5 rounded">B2B SaaS</span>
          </div>
          <div class="font-semibold text-sm text-white mt-1">Apollo.io</div>
          <div class="text-[11px] text-[#737373] mt-0.5">Verified Decision Makers</div>
        </div>

        <div class="card-mono p-3.5 rounded-lg transition">
          <div class="flex items-center justify-between">
            <span class="text-xs font-mono text-[#888888]">PLATFORM 02</span>
            <span class="text-[10px] font-mono text-white bg-[#1a1a1a] px-1.5 py-0.5 rounded">Local Biz</span>
          </div>
          <div class="font-semibold text-sm text-white mt-1">Google Maps</div>
          <div class="text-[11px] text-[#737373] mt-0.5">Physical Retail & Agencies</div>
        </div>

        <div class="card-mono p-3.5 rounded-lg transition">
          <div class="flex items-center justify-between">
            <span class="text-xs font-mono text-[#888888]">PLATFORM 03</span>
            <span class="text-[10px] font-mono text-white bg-[#1a1a1a] px-1.5 py-0.5 rounded">Trade</span>
          </div>
          <div class="font-semibold text-sm text-white mt-1">IndiaMART</div>
          <div class="text-[11px] text-[#737373] mt-0.5">Manufacturers & Exporters</div>
        </div>

        <div class="card-mono p-3.5 rounded-lg transition">
          <div class="flex items-center justify-between">
            <span class="text-xs font-mono text-[#888888]">PLATFORM 04</span>
            <span class="text-[10px] font-mono text-white bg-[#1a1a1a] px-1.5 py-0.5 rounded">Executive</span>
          </div>
          <div class="font-semibold text-sm text-white mt-1">LinkedIn Sales</div>
          <div class="text-[11px] text-[#737373] mt-0.5">C-Suite & Founders</div>
        </div>

        <div class="card-mono p-3.5 rounded-lg transition">
          <div class="flex items-center justify-between">
            <span class="text-xs font-mono text-[#888888]">PLATFORM 05</span>
            <span class="text-[10px] font-mono text-white bg-[#1a1a1a] px-1.5 py-0.5 rounded">Startups</span>
          </div>
          <div class="font-semibold text-sm text-white mt-1">Deep Web</div>
          <div class="text-[11px] text-[#737373] mt-0.5">Crunchbase & Fast Growth</div>
        </div>
      </div>
    </section>

    <!-- Main Section: Campaign Launch Form & Response Lab -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      
      <!-- Launch Form -->
      <div class="card-mono p-6 rounded-xl space-y-4">
        <div class="border-b border-[#1f1f1f] pb-3">
          <h2 class="text-base font-semibold text-white">Launch Campaign</h2>
          <p class="text-xs text-[#888888] mt-0.5">Select platform and region to begin prospecting</p>
        </div>

        <form id="campaignForm" class="space-y-3.5">
          <!-- Platform Dropdown -->
          <div>
            <label class="block text-xs font-mono text-[#888888] mb-1">DATA PLATFORM SOURCE</label>
            <select id="platformSelect" class="w-full rounded px-3 py-2 text-sm">
              <option value="apollo">Apollo.io (Verified B2B & C-Suite)</option>
              <option value="google_maps">Google Maps (Local Businesses & Retail)</option>
              <option value="indiamart">IndiaMART (Wholesale, Suppliers & Exporters)</option>
              <option value="linkedin">LinkedIn Sales Navigator (Executive Profiles)</option>
              <option value="web_search">Deep Web & Crunchbase (Funded Startups)</option>
            </select>
          </div>

          <!-- Target Industry Input -->
          <div>
            <label class="block text-xs font-mono text-[#888888] mb-1">TARGET INDUSTRY / NICHE</label>
            <input id="targetInput" type="text" value="SaaS & Cloud Software" placeholder="e.g. Textile Exporters, Solar EPC, FinTech" class="w-full rounded px-3 py-2 text-sm">
          </div>

          <!-- Geography Dropdown -->
          <div>
            <label class="block text-xs font-mono text-[#888888] mb-1">TARGET GEOGRAPHY</label>
            <select id="locationSelect" class="w-full rounded px-3 py-2 text-sm">
              <option value="United States (USA)">🇺🇸 United States (USA)</option>
              <option value="United Kingdom (UK)">🇬🇧 United Kingdom (UK)</option>
              <option value="India (Pan India)">🇮🇳 India (Pan India)</option>
              <option value="India - Bengaluru (Tech Hub)">🇮🇳 India - Bengaluru (Tech Hub)</option>
              <option value="India - Mumbai (Finance Hub)">🇮🇳 India - Mumbai (Finance Hub)</option>
              <option value="India - Delhi NCR (Trade Hub)">🇮🇳 India - Delhi NCR (Trade Hub)</option>
              <option value="Canada">🇨🇦 Canada</option>
              <option value="Australia & New Zealand">🇦🇺 Australia & New Zealand</option>
              <option value="Germany & Western Europe">🇩🇪 Germany & Western Europe</option>
              <option value="United Arab Emirates (Dubai / UAE)">🇦🇪 UAE (Dubai & Middle East)</option>
              <option value="Singapore & Southeast Asia">🇸🇬 Singapore & Southeast Asia</option>
              <option value="Global / Remote">🌐 Global / Remote</option>
            </select>
          </div>

          <!-- Leads Count & Campaign Tag -->
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-mono text-[#888888] mb-1">LEADS</label>
              <select id="leadsCountSelect" class="w-full rounded px-3 py-2 text-sm">
                <option value="3">3 Leads</option>
                <option value="5" selected>5 Leads</option>
                <option value="10">10 Leads</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-mono text-[#888888] mb-1">CAMPAIGN TAG</label>
              <input id="campaignNameInput" type="text" value="Q4 Outreach" class="w-full rounded px-3 py-2 text-sm">
            </div>
          </div>

          <!-- Submit Button -->
          <button type="submit" id="btnLaunch" class="w-full mt-2 bg-white text-black font-semibold py-2.5 px-4 rounded text-sm hover:bg-[#d4d4d4] transition duration-150">
            Start Autonomous Pipeline
          </button>
        </form>

        <div id="campaignStatus" class="text-xs text-[#888888] min-h-[20px] text-center font-mono"></div>
      </div>

      <!-- Inbound Intelligence Lab -->
      <div class="card-mono p-6 rounded-xl space-y-4 lg:col-span-2 flex flex-col justify-between">
        <div class="border-b border-[#1f1f1f] pb-3 flex justify-between items-center">
          <div>
            <h2 class="text-base font-semibold text-white">Inbound Reply Analyzer</h2>
            <p class="text-xs text-[#888888] mt-0.5">Test objection handling, calendar invites & intent detection</p>
          </div>
          <span class="text-[10px] font-mono text-[#888888] border border-[#262626] px-2 py-0.5 rounded">Autonomous Closer</span>
        </div>

        <div class="space-y-3">
          <textarea id="replyTextInput" rows="3" class="w-full rounded p-3 text-sm" placeholder="Paste any inbound prospect reply, e.g.: 'Sounds relevant! Can we book a 15-minute call on Thursday to discuss pricing?'"></textarea>
          
          <div class="flex flex-wrap items-center gap-2">
            <button onclick="preset('call')" class="text-xs bg-[#111111] hover:bg-[#1a1a1a] text-[#a3a3a3] hover:text-white px-2.5 py-1 rounded border border-[#262626] transition">Example: Meeting Request</button>
            <button onclick="preset('info')" class="text-xs bg-[#111111] hover:bg-[#1a1a1a] text-[#a3a3a3] hover:text-white px-2.5 py-1 rounded border border-[#262626] transition">Example: Pricing Inquiry</button>
            <button onclick="preset('unsub')" class="text-xs bg-[#111111] hover:bg-[#1a1a1a] text-[#a3a3a3] hover:text-white px-2.5 py-1 rounded border border-[#262626] transition">Example: Unsubscribe</button>
            
            <button onclick="analyzeReply()" class="ml-auto bg-white text-black px-4 py-1 text-xs font-semibold rounded hover:bg-[#d4d4d4] transition">
              Analyze Reply
            </button>
          </div>
        </div>

        <div id="replyResult" class="hidden p-4 rounded bg-[#050505] border border-[#262626] space-y-2 text-xs font-mono">
          <!-- Filled by JS -->
        </div>
      </div>

    </div>

    <!-- Results Section -->
    <section class="space-y-4">
      <div class="flex justify-between items-center border-b border-[#1f1f1f] pb-3">
        <div>
          <h2 class="text-base font-semibold text-white">Prospects & Generated Outreach</h2>
          <p class="text-xs text-[#888888] mt-0.5">Direct 1-tap Gmail dispatch ready</p>
        </div>
        <span id="campaignBadge" class="text-xs font-mono text-[#888888]"></span>
      </div>

      <!-- KPI Metrics -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div class="card-mono p-4 rounded-lg text-center">
          <div class="text-xs font-mono text-[#737373]">DISCOVERED</div>
          <div id="kpiLeads" class="text-2xl font-bold text-white mt-1">--</div>
        </div>
        <div class="card-mono p-4 rounded-lg text-center">
          <div class="text-xs font-mono text-[#737373]">DRAFTED</div>
          <div id="kpiContent" class="text-2xl font-bold text-white mt-1">--</div>
        </div>
        <div class="card-mono p-4 rounded-lg text-center">
          <div class="text-xs font-mono text-[#737373]">DRY-RUN PREVIEWS</div>
          <div id="kpiSent" class="text-2xl font-bold text-white mt-1">--</div>
        </div>
        <div class="card-mono p-4 rounded-lg text-center">
          <div class="text-xs font-mono text-[#737373]">QUALITY SCORE</div>
          <div id="kpiQuality" class="text-2xl font-bold text-white mt-1">--</div>
        </div>
      </div>

      <!-- Leads Table with Gmail Deep Link -->
      <div class="card-mono rounded-xl overflow-hidden">
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-[#050505] font-mono text-[#888888] uppercase border-b border-[#1f1f1f]">
              <tr>
                <th class="py-3 px-4">Company & Platform</th>
                <th class="py-3 px-4">Contact Person</th>
                <th class="py-3 px-4">Location</th>
                <th class="py-3 px-4">Score</th>
                <th class="py-3 px-4 text-right">Actions (Direct Gmail)</th>
              </tr>
            </thead>
            <tbody id="leadsTableBody" class="divide-y divide-[#171717]">
              <tr>
                <td colspan="5" class="py-8 text-center text-[#525252] font-mono">No campaign has been launched yet. Select options above and tap Start!</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section class="card-mono rounded-xl p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <h2 class="text-sm font-semibold text-white">CRM & Daily Prospector</h2>
        <p class="text-xs text-[#888888] mt-1">Export the current campaign. Daily discovery runs at 09:00 Asia/Kolkata when enabled in environment settings.</p>
        <p id="dailyScheduleStatus" class="text-xs font-mono text-[#a3a3a3] mt-2">Checking daily schedule...</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <a href="/api/export.csv" class="px-3 py-2 rounded bg-white text-black text-xs font-semibold hover:bg-[#d4d4d4]">Export CSV</a>
        <a href="/api/export.xlsx" class="px-3 py-2 rounded border border-[#333333] text-white text-xs hover:bg-[#171717]">Export Excel</a>
      </div>
    </section>

  </div>

  <!-- Follow-up Draft Sequence Modal -->
  <div id="followupModal" class="hidden fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="card-mono rounded-xl max-w-3xl w-full p-6 space-y-4 border border-[#333333] max-h-[90vh] overflow-y-auto">
      <div class="flex justify-between items-center border-b border-[#1f1f1f] pb-3">
        <div>
          <h3 class="font-semibold text-white text-sm">Follow-up Sequence</h3>
          <p id="followupLeadLabel" class="text-xs text-[#777777] mt-1"></p>
        </div>
        <button onclick="closeFollowups()" class="text-[#888888] hover:text-white text-sm font-mono">[ ESC / ✕ ]</button>
      </div>
      <div id="followupsContent" class="space-y-3"></div>
      <p class="text-[11px] text-[#737373]">These are editable drafts only. Fili does not send follow-ups automatically.</p>
    </div>
  </div>

  <!-- Email Draft Inspection Modal -->
  <div id="draftModal" class="hidden fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="card-mono rounded-xl max-w-2xl w-full p-6 space-y-4 border border-[#333333]">
      <div class="flex justify-between items-center border-b border-[#1f1f1f] pb-3">
        <h3 class="font-semibold text-white text-sm">Personalized Email Draft</h3>
        <button onclick="closeModal()" class="text-[#888888] hover:text-white text-sm font-mono">[ ESC / ✕ ]</button>
      </div>

      <div class="space-y-3 text-xs">
        <div>
          <span class="font-mono text-[#737373] block mb-1">RECIPIENT</span>
          <div id="modalTo" class="p-2 rounded bg-[#050505] border border-[#222222] text-white font-mono"></div>
        </div>
        <div>
          <span class="font-mono text-[#737373] block mb-1">SUBJECT</span>
          <div id="modalSubject" class="p-2 rounded bg-[#050505] border border-[#222222] text-white font-medium"></div>
        </div>
        <div>
          <span class="font-mono text-[#737373] block mb-1">EMAIL BODY</span>
          <div id="modalBody" class="p-3 rounded bg-[#050505] border border-[#222222] text-[#d4d4d4] whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto"></div>
        </div>
      </div>

      <div class="flex justify-end gap-2 pt-2 border-t border-[#1f1f1f]">
        <button onclick="copyModalBody()" id="btnCopy" class="px-3 py-1.5 rounded border border-[#262626] text-xs hover:border-[#444444] text-[#ededed]">Copy Body</button>
        <button onclick="openModalGmail()" class="px-4 py-1.5 rounded bg-white text-black font-semibold text-xs hover:bg-[#d4d4d4] transition">✉️ Open in Gmail</button>
      </div>
    </div>
  </div>

  <script>
    let currentLeads = [];
    let activeModalLead = null;
    let currentReport = {};
    let currentEmailActivity = { sent: 0 };

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      })[char]);
    }

    async function refreshDashboardStatus() {
      try {
        const response = await fetch('/api/status');
        const data = await response.json();
        const status = document.getElementById('dailyScheduleStatus');
        if (!status) return;
        if (data.daily_schedule_enabled) {
          status.textContent = 'Daily prospector active · ' + data.daily_schedule_time + ' · ' + data.daily_schedule_timezone
            + (data.next_run ? ' · Next run: ' + data.next_run : '');
        } else {
          status.textContent = 'Daily prospector disabled · Set FILI_DAILY_PROSPECTOR_ENABLED=true in .env and restart.';
        }
      } catch (_) {
        const status = document.getElementById('dailyScheduleStatus');
        if (status) status.textContent = 'Schedule status unavailable.';
      }
    }
    refreshDashboardStatus();

    function preset(type) {
      const field = document.getElementById('replyTextInput');
      if (type === 'call') {
        field.value = "Hey! This looks relevant for us. Can we schedule a quick 15-minute call on Thursday to discuss details?";
      } else if (type === 'info') {
        field.value = "Can you send over your pricing deck and customer case studies before we book time?";
      } else if (type === 'unsub') {
        field.value = "Please remove our company from your mailing list immediately. Unsubscribe.";
      }
      analyzeReply();
    }

    async function analyzeReply() {
      const text = document.getElementById('replyTextInput').value.trim();
      if (!text) return;
      const resContainer = document.getElementById('replyResult');
      resContainer.classList.remove('hidden');
      resContainer.innerHTML = '<span class="text-[#737373] animate-pulse">ResponseAnalyzer classifying intent on Groq LPU...</span>';

      try {
        const resp = await fetch('/api/analyze-reply', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reply_text: text })
        });
        const data = await resp.json();
        
        resContainer.innerHTML = `
          <div class="flex items-center justify-between border-b border-[#1f1f1f] pb-2">
            <span class="text-white">INTENT: <b class="underline underline-offset-4">${data.category.toUpperCase()}</b></span>
            <span class="text-[#888888]">SENTIMENT: ${data.sentiment.label.toUpperCase()} (${(data.sentiment.confidence*100).toFixed(0)}%)</span>
          </div>
          <div class="mt-1"><span class="text-[#737373]">AUTONOMOUS NEXT STEP:</span> <span class="text-white">${data.next_action}</span></div>
          <div class="mt-1"><span class="text-[#737373]">RECOMMENDED ACTIONS:</span>
            <ul class="list-disc list-inside text-[#a3a3a3] mt-1 space-y-0.5">
              ${data.action_items.map(a => `<li>${a}</li>`).join('')}
            </ul>
          </div>
        `;
      } catch (err) {
        resContainer.innerHTML = `<span class="text-white font-mono">Analysis error: ${err}</span>`;
      }
    }

    document.getElementById('campaignForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('btnLaunch');
      const statusDiv = document.getElementById('campaignStatus');
      
      btn.disabled = true;
      btn.innerText = "⚡ Agents Prospecting on Groq LPU...";
      statusDiv.innerHTML = '<span class="text-white animate-pulse">Orchestrator running: Researching Leads → Writing Outreach → Preparing Gmail Drafts...</span>';

      const payload = {
        platform: document.getElementById('platformSelect').value,
        target: document.getElementById('targetInput').value,
        location: document.getElementById('locationSelect').value,
        max_leads: parseInt(document.getElementById('leadsCountSelect').value),
        campaign_name: document.getElementById('campaignNameInput').value
      };

      try {
        const resp = await fetch('/api/run-campaign', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!resp.ok) {
          throw new Error(`Server returned HTTP ${resp.status}`);
        }
        const data = await resp.json();
        if (data.error) {
          statusDiv.innerHTML = `<span class="text-white">Error: ${data.error}</span>`;
          return;
        }
        currentLeads = data.leads || [];
        renderCampaign(data);
        statusDiv.innerHTML = '<span class="text-white font-mono">✓ Pipeline completed! Click "Send via Gmail" on any lead below.</span>';
      } catch (err) {
        statusDiv.innerHTML = `<span class="text-white">Failed: ${err.message || err}</span>`;
      } finally {
        btn.disabled = false;
        btn.innerText = "Start Autonomous Pipeline";
      }
    });

    function renderCampaign(data) {
      const leads = data.leads || [];
      const report = data.report || currentReport || {};
      currentReport = report;
      const activity = data.email_activity || currentEmailActivity || { sent: 0 };
      currentEmailActivity = activity;
      const summary = report.summary || {};
      const quality = report.lead_quality || {};

      document.getElementById('kpiLeads').innerText = summary.total_leads_found ?? leads.length;
      document.getElementById('kpiContent').innerText = summary.content_pieces_generated ?? leads.length;
      document.getElementById('kpiSent').innerText = (activity.sent ?? 0) + ' preview';
      document.getElementById('kpiQuality').innerText = (quality.average_score ?? '—') + '/10';
      document.getElementById('campaignBadge').innerText = report.report_title || 'Active';

      const tbody = document.getElementById('leadsTableBody');
      if (leads.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="py-8 text-center text-[#525252] font-mono">No leads found.</td></tr>';
        return;
      }

      tbody.innerHTML = leads.map((l, idx) => {
        const sourceLabel = l.is_synthetic ? 'AI / MOCK · UNVERIFIED' : 'SEARCH RESULT · VERIFY CONTACT';
        const mx = (l.email_verification || {}).status || 'not_checked';
        const stack = Array.isArray(l.tech_stack) ? l.tech_stack.join(', ') : '';
        const actions = []
          .concat('<button onclick="viewDraft(' + idx + ')" class="px-2.5 py-1.5 text-xs bg-[#111111] text-[#ededed] border border-[#262626] rounded">View Draft</button>')
          .concat('<button onclick="viewFollowups(' + idx + ')" class="px-2.5 py-1.5 text-xs bg-[#111111] text-[#ededed] border border-[#262626] rounded">Follow-ups</button>')
          .concat(l.website ? '<button onclick="scanTechStack(' + idx + ')" class="px-2.5 py-1.5 text-xs bg-[#111111] text-[#ededed] border border-[#262626] rounded">Scan Tech</button>' : '')
          .concat(l.outreach_enabled !== false && l.contact_email ? '<button onclick="sendViaGmail(' + idx + ')" class="px-3 py-1.5 text-xs bg-white text-black font-semibold rounded">Gmail</button>' : '')
          .concat(l.outreach_enabled !== false && l.whatsapp_url ? '<a href="' + escapeHtml(l.whatsapp_url) + '" target="_blank" rel="noopener noreferrer" class="inline-block px-3 py-1.5 text-xs bg-[#171717] text-white border border-[#333333] rounded">WhatsApp</a>' : '');
        return '<tr class="hover:bg-[#111111] transition">'
          + '<td class="py-3.5 px-4 font-medium text-white">' + escapeHtml(l.company_name || 'Unknown company')
          + '<div class="flex flex-wrap items-center gap-2 mt-1">'
          + '<span class="text-[10px] font-mono bg-[#1a1a1a] text-[#a3a3a3] border border-[#262626] px-1.5 py-0.2 rounded">' + escapeHtml(l.platform || 'Unknown source') + '</span>'
          + '<span class="text-[10px] font-mono text-[#777777]">' + escapeHtml(sourceLabel) + '</span></div>'
          + '<div class="text-[11px] text-[#737373] font-mono mt-1">' + escapeHtml(l.website || '') + '</div>'
          + (stack ? '<div class="text-[11px] text-[#a3a3a3] mt-1">Stack signals: ' + escapeHtml(stack) + '</div>' : '')
          + '</td>'
          + '<td class="py-3.5 px-4 text-[#d4d4d4]"><b>' + escapeHtml(l.contact_name || 'Not found') + '</b><br>'
          + '<span class="text-[#888888] font-mono text-[11px]">' + escapeHtml(l.contact_email || 'No email') + '</span>'
          + (l.phone ? '<br><span class="text-[#666666] font-mono text-[10px]">' + escapeHtml(l.phone) + '</span>' : '')
          + '<br><span class="text-[10px] text-[#777777]">Domain check: ' + escapeHtml(mx) + ' · mailbox not verified</span></td>'
          + '<td class="py-3.5 px-4 text-[#a3a3a3] font-mono">' + escapeHtml(l.location || '—') + '</td>'
          + '<td class="py-3.5 px-4 font-mono font-bold text-white"><span class="px-2 py-0.5 rounded bg-[#171717] border border-[#262626]">' + escapeHtml(l.relevance_score ?? '—') + '/10</span></td>'
          + '<td class="py-3.5 px-4 text-right space-x-1.5 whitespace-nowrap">' + actions.join('') + '</td></tr>';
      }).join('');
    }

    function viewFollowups(idx) {
      const lead = currentLeads[idx];
      if (!lead) return;
      document.getElementById('followupLeadLabel').textContent =
        (lead.company_name || 'Prospect') + ' · drafts for Day 1, Day 3 and Day 7';
      const container = document.getElementById('followupsContent');
      container.innerHTML = '';
      const sequence = Array.isArray(lead.follow_up_sequence) ? lead.follow_up_sequence : [];
      sequence.forEach((draft) => {
        const card = document.createElement('section');
        card.className = 'rounded-lg border border-[#292929] bg-[#050505] p-4 space-y-2';
        const heading = document.createElement('div');
        heading.className = 'text-xs font-mono text-white';
        heading.textContent = 'DAY ' + draft.day + ' · ' + draft.label;
        const subject = document.createElement('div');
        subject.className = 'text-sm font-semibold text-white';
        subject.textContent = draft.subject || '';
        const body = document.createElement('pre');
        body.className = 'text-xs text-[#c4c4c4] whitespace-pre-wrap font-sans';
        body.textContent = draft.body || '';
        const actions = document.createElement('div');
        actions.className = 'flex gap-2';
        const copy = document.createElement('button');
        copy.className = 'px-3 py-1.5 rounded border border-[#333333] text-xs text-white';
        copy.textContent = 'Copy draft';
        copy.onclick = async () => {
          try {
            await navigator.clipboard.writeText((draft.subject || '') + '\n\n' + (draft.body || ''));
            copy.textContent = 'Copied';
          } catch (_) { copy.textContent = 'Copy unavailable'; }
        };
        actions.appendChild(copy);
        if (lead.outreach_enabled !== false && lead.contact_email) {
          const open = document.createElement('button');
          open.className = 'px-3 py-1.5 rounded bg-white text-black text-xs font-semibold';
          open.textContent = 'Open email draft';
          open.onclick = () => openGmailDraft(lead.contact_email, draft.subject, draft.body);
          actions.appendChild(open);
        }
        card.append(heading, subject, body, actions);
        container.appendChild(card);
      });
      if (!sequence.length) container.textContent = 'No follow-up drafts available for this lead.';
      document.getElementById('followupModal').classList.remove('hidden');
    }

    function closeFollowups() {
      document.getElementById('followupModal').classList.add('hidden');
    }

    function openGmailDraft(email, subject, body) {
      const url = 'https://mail.google.com/mail/?view=cm&fs=1&to=' + encodeURIComponent(email || '')
        + '&su=' + encodeURIComponent(subject || '') + '&body=' + encodeURIComponent(body || '');
      window.open(url, '_blank', 'noopener,noreferrer');
    }

    async function scanTechStack(idx) {
      const lead = currentLeads[idx];
      if (!lead || !lead.website) return;
      const status = document.getElementById('campaignStatus');
      status.textContent = 'Scanning public website signals...';
      try {
        const response = await fetch('/api/scan-tech', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: lead.website })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
        lead.tech_stack = data.signals || [];
        lead.tech_scan_status = data.status;
        renderCampaign({ leads: currentLeads, report: currentReport });
        status.textContent = data.signals?.length
          ? 'Technology signals detected: ' + data.signals.join(', ')
          : 'Scan complete; no known technology signals were detected.';
      } catch (error) {
        status.textContent = 'Website scan blocked or unavailable: ' + (error.message || error);
      }
    }

    function sendViaGmail(idx) {
      const lead = currentLeads[idx];
      if (!lead) return;
      if (lead.outreach_enabled === false) {
        document.getElementById('campaignStatus').textContent = 'AI-generated preview only: contact details are unverified and outreach is disabled.';
        return;
      }
      const email = lead.contact_email || '';
      const subject = lead.email_subject || `Quick question regarding ${lead.company_name}`;
      const body = lead.email_body || `Hi ${lead.contact_name || ''},\\n\\nI wanted to reach out regarding ${lead.company_name}.`;

      const encEmail = encodeURIComponent(email);
      const encSub = encodeURIComponent(subject);
      const encBody = encodeURIComponent(body);

      // Deep link web & mobile
      const webGmail = `https://mail.google.com/mail/?view=cm&fs=1&to=${encEmail}&su=${encSub}&body=${encBody}`;
      const mailto = `mailto:${encEmail}?subject=${encSub}&body=${encBody}`;

      // Open Gmail
      const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
      if (isMobile) {
        window.location.href = mailto;
      } else {
        window.open(webGmail, '_blank');
      }
    }

    function viewDraft(idx) {
      const lead = currentLeads[idx];
      if (!lead) return;
      activeModalLead = lead;
      document.getElementById('modalTo').innerText = `${lead.contact_name} <${lead.contact_email}>`;
      document.getElementById('modalSubject').innerText = lead.email_subject || `Quick question regarding ${lead.company_name}`;
      document.getElementById('modalBody').innerText = lead.email_body || '';
      document.getElementById('btnCopy').innerText = 'Copy Body';
      document.getElementById('draftModal').classList.remove('hidden');
    }

    function closeModal() {
      document.getElementById('draftModal').classList.add('hidden');
    }

    function copyModalBody() {
      if (!activeModalLead) return;
      navigator.clipboard.writeText(activeModalLead.email_body || '');
      document.getElementById('btnCopy').innerText = '✓ Copied!';
      setTimeout(() => { document.getElementById('btnCopy').innerText = 'Copy Body'; }, 2000);
    }

    function openModalGmail() {
      if (!activeModalLead) return;
      const idx = currentLeads.indexOf(activeModalLead);
      if (idx !== -1) sendViaGmail(idx);
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { closeModal(); closeFollowups(); }
    });
  </script>
</body>
</html>
"""


class DashboardHandler(SimpleHTTPRequestHandler):
    """HTTP request handler for the dashboard."""
    protocol_version = "HTTP/1.1"

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def _require_api_auth(self) -> bool:
        secret = os.getenv("FILI_API_TOKEN", "").strip()
        if not secret:
            return True
        authorization = self.headers.get("Authorization", "")
        supplied = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        if hmac.compare_digest(supplied, secret):
            return True
        self.send_json({"error": "Unauthorized."}, HTTPStatus.UNAUTHORIZED)
        return False

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/") and not self._require_api_auth():
            return
        if parsed.path in ["/", "/index.html"]:
            payload = HTML_PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif parsed.path == "/api/status":
            jobs = SCHEDULER.get_jobs() if SCHEDULER else []
            next_run = jobs[0].next_run_time.isoformat() if jobs and jobs[0].next_run_time else None
            self.send_json({
                "online": True, "agents_count": 5,
                "latest_campaign": STATE["last_campaign_name"],
                "daily_schedule_enabled": bool(SCHEDULER),
                "daily_schedule_time": os.getenv("FILI_DAILY_PROSPECTOR_TIME", "09:00"),
                "daily_schedule_timezone": os.getenv("FILI_DAILY_PROSPECTOR_TIMEZONE", "Asia/Kolkata"),
                "next_run": next_run, "last_daily_run": STATE["last_daily_run"],
            })
        elif parsed.path in {"/api/export.csv", "/api/export.xlsx"}:
            leads = STATE["latest_leads"]
            if not leads:
                self.send_json({"error": "No campaign leads are available to export."}, HTTPStatus.CONFLICT)
                return
            if parsed.path.endswith(".csv"):
                payload = csv_export(leads).encode("utf-8-sig")
                content_type, filename = "text/csv; charset=utf-8", "fili-crm-export.csv"
            else:
                payload = excel_export(leads)
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                filename = "fili-crm-export.xlsx"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not self._require_api_auth():
            return
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self.send_json({"error": "Invalid Content-Length."}, HTTPStatus.BAD_REQUEST)
            return
        if content_length < 0 or content_length > 1_000_000:
            self.send_json({"error": "Request body exceeds the 1 MB limit."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("JSON request body must be an object.")
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc) or "Invalid JSON request."}, HTTPStatus.BAD_REQUEST)
            return

        try:
            if parsed.path == "/api/run-campaign":
                target = str(data.get("target", "SaaS")).strip()[:160]
                location = str(data.get("location", "India")).strip()[:160]
                max_leads = max(1, min(int(data.get("max_leads", 5)), 25))
                campaign_name = str(data.get("campaign_name", "Fili Campaign")).strip()[:100]
                platform = str(data.get("platform", "apollo")).lower()
                if platform not in {"apollo", "google_maps", "indiamart", "linkedin", "web_search"}:
                    self.send_json({"error": "Unsupported prospecting platform."}, HTTPStatus.BAD_REQUEST)
                    return
                location_scope = data.get("location_scope")
                if not isinstance(location_scope, dict) or not all(str(location_scope.get(key, "")).strip() for key in ("country", "country_code", "state", "state_code", "city")):
                    self.send_json({"error": "Select a valid country, state and city before starting discovery."}, HTTPStatus.BAD_REQUEST)
                    return
                if not re.fullmatch(r"[A-Z]{2}", str(location_scope.get("country_code", ""))) or not re.fullmatch(r"[A-Z0-9-]{1,8}", str(location_scope.get("state_code", ""))):
                    self.send_json({"error": "The selected country or state code is invalid."}, HTTPStatus.BAD_REQUEST)
                    return
                location = ", ".join(str(location_scope[key]).strip() for key in ("city", "state", "country"))
                if not target or not location or not campaign_name:
                    self.send_json({"error": "Target, location and campaign name are required."}, HTTPStatus.BAD_REQUEST)
                    return
                if not CAMPAIGN_LOCK.acquire(blocking=False):
                    self.send_json({"error": "A campaign is already running. Retry after it finishes."}, HTTPStatus.CONFLICT)
                    return
                STATE["campaign_running"] = True
                try:
                    result = run_async(execute_campaign(target, location, max_leads, campaign_name, platform, location_scope))
                    self.send_json(result)
                finally:
                    STATE["campaign_running"] = False
                    CAMPAIGN_LOCK.release()

            elif parsed.path == "/api/analyze-reply":
                reply_text = str(data.get("reply_text", "")).strip()
                if not reply_text or len(reply_text) > 10_000:
                    self.send_json({"error": "Reply text must contain 1–10,000 characters."}, HTTPStatus.BAD_REQUEST)
                    return
                result = run_async(analyze_single_reply(reply_text))
                self.send_json(result)

            elif parsed.path == "/api/scan-tech":
                safe_url = validate_public_http_url(data.get("url", ""))
                result = fetch_tech_stack(safe_url)
                self.send_json(result)

            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self.send_json({"error": str(exc), "success": False}, HTTPStatus.BAD_REQUEST)
        except Exception:
            logging.exception("Dashboard API request failed")
            self.send_json({"error": "The request could not be completed.", "success": False}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format: str, *args: Any) -> None:
        # Silent dashboard logging to avoid cluttering stdout
        pass




def run_daily_prospecting() -> None:
    """Run a scheduled discovery pass. Email stays in the pipeline's dry-run mode."""
    if not CAMPAIGN_LOCK.acquire(blocking=False):
        logging.warning("Daily prospector skipped because another campaign is running.")
        return
    STATE["campaign_running"] = True
    try:
        target = os.getenv("FILI_DAILY_PROSPECTOR_TARGET", "SaaS companies")
        location = os.getenv("FILI_DAILY_PROSPECTOR_LOCATION", "India")
        try:
            count = max(1, min(int(os.getenv("FILI_DAILY_PROSPECTOR_MAX_LEADS", "10")), 25))
        except ValueError:
            count = 10
        result = run_async(execute_campaign(target, location, count, "Daily Prospector", "web_search"))
        STATE["last_daily_run"] = {
            "success": bool(result.get("success")),
            "lead_count": len(result.get("leads", [])),
        }
    except Exception:
        logging.exception("Daily prospecting run failed")
        STATE["last_daily_run"] = {"success": False, "lead_count": 0}
    finally:
        STATE["campaign_running"] = False
        CAMPAIGN_LOCK.release()


def main():
    global SCHEDULER
    parser = argparse.ArgumentParser(description="Multi-Agent System Web Dashboard")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind dashboard server (default: 8000)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not os.getenv("FILI_API_TOKEN", "").strip():
        parser.error("FILI_API_TOKEN is required when binding the API beyond localhost.")

    SCHEDULER = start_daily_prospector(run_daily_prospecting)
    STATE["daily_schedule_enabled"] = bool(SCHEDULER)
    if not SCHEDULER and os.getenv("FILI_DAILY_PROSPECTOR_ENABLED", "false").lower() in {"1", "true", "yes"}:
        STATE["daily_schedule_error"] = "Scheduler failed to initialize; check logs and APScheduler installation."

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    server.daemon_threads = True
    print("\n" + "=" * 65)
    print("  🌐 MULTI-AGENT SYSTEM WEB DASHBOARD (Monochrome Edition)")
    print("=" * 65)
    print(f"  Listening at: http://{args.host}:{args.port}/")
    print("  Press Ctrl+C to stop.")
    print("=" * 65 + "\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server...")
        server.shutdown()
    finally:
        if SCHEDULER:
            SCHEDULER.shutdown(wait=False)


if __name__ == "__main__":
    main()
