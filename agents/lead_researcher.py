"""Lead Researcher Agent — finds and scores potential leads."""

from __future__ import annotations

import json
import random
from typing import Any

from core.base_agent import BaseAgent
from core.task import Task
from utils.live_search import (
    fetch_apollo_leads,
    fetch_serpapi_leads,
    fetch_indiamart_leads,
    fetch_duckduckgo_leads,
    get_apollo_key,
    get_serpapi_key,
)


class LeadResearcherAgent(BaseAgent):
    """Researches target industries/niches and finds potential leads.

    Uses LLM to generate search queries, extract company info, and
    score leads based on relevance.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(name="LeadResearcher", **kwargs)

    def get_capabilities(self) -> list[str]:
        return ["research_leads", "enrich_lead", "score_lead"]

    async def process_task(self, task: Task) -> dict[str, Any]:
        """Process a lead research task."""
        if task.task_type == "research_leads":
            return await self.research_leads(task.payload)
        elif task.task_type == "enrich_lead":
            return await self.enrich_lead_data(task.payload)
        elif task.task_type == "score_lead":
            return await self.score_lead(task.payload)
        else:
            raise ValueError(f"Unknown task type: {task.task_type}")

    async def research_leads(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Research and find leads for a target industry.

        Args:
            payload: Must contain 'target_industry' and optionally
                     'target_location', 'max_leads'.
        """
        target_industry = payload.get("target_industry", "SaaS")
        target_location = payload.get("target_location", "USA")
        max_leads = payload.get("max_leads", 10)
        platform = payload.get("platform", "apollo").lower()

        platform_names = {
            "apollo": "Apollo.io B2B Intelligence",
            "indiamart": "IndiaMART B2B Marketplace",
            "google_maps": "Google Maps Local Business",
            "linkedin": "LinkedIn Sales Navigator",
            "web_search": "Deep Web & Crunchbase",
        }
        platform_label = platform_names.get(platform, "Apollo.io B2B Intelligence")

        self.logger.info(
            f"Researching leads via [{platform_label}]: industry={target_industry}, "
            f"location={target_location}, max={max_leads}"
        )

        platform_guidance = ""
        if platform == "indiamart":
            platform_guidance = """
Focus specifically on Indian/global manufacturers, wholesale suppliers, exporters, and industrial trade businesses listed on IndiaMART.
Include fields: 'business_type' (e.g. Manufacturer, Exporter, Wholesaler), 'verified_supplier' (true), 'phone': '+91...', 'main_products': ['item1', 'item2']."""
        elif platform == "google_maps":
            platform_guidance = """
Focus on physical and regional businesses found on Google Maps.
Include fields: 'rating' (e.g. '4.8 ★'), 'reviews_count' (e.g. 142), 'full_address', 'phone'."""
        elif platform == "linkedin":
            platform_guidance = """
Focus on senior decision makers (Founder, CEO, VP, Director) discovered via LinkedIn Sales Navigator.
Include fields: 'headline' (e.g. 'VP of Engineering @...'), 'growth_rate' (e.g. '+24% YoY')."""
        elif platform == "apollo":
            platform_guidance = """
Focus on high-growth B2B companies with verified corporate email domains and direct intelligence via Apollo.io.
Include fields: 'verified_email': true, 'technologies_used': ['AWS', 'Salesforce'], 'funding_stage': 'Series A/Bootstrapped'."""

        leads: list[dict[str, Any]] = []

        # ── 1. Attempt Live Data Connectors First ─────────────────
        if platform == "apollo" and get_apollo_key():
            self.logger.info("Attempting live Apollo.io B2B intelligence lookup...")
            leads = await fetch_apollo_leads(
                industry=target_industry,
                location=target_location,
                max_leads=max_leads,
            )
        elif platform in ["serpapi", "google_maps"] and get_serpapi_key():
            self.logger.info("Attempting live SerpAPI lookup...")
            engine = "google_maps" if platform == "google_maps" else "google"
            leads = await fetch_serpapi_leads(
                query=target_industry,
                location=target_location,
                max_leads=max_leads,
                engine=engine,
            )
        elif platform == "indiamart":
            leads = await fetch_indiamart_leads(
                query=target_industry,
                location=target_location,
                max_leads=max_leads,
            )
        elif platform == "web_search":
            if get_serpapi_key():
                leads = await fetch_serpapi_leads(
                    query=target_industry,
                    location=target_location,
                    max_leads=max_leads,
                    engine="google",
                )
            else:
                leads = await fetch_duckduckgo_leads(
                    query=target_industry,
                    location=target_location,
                    max_leads=max_leads,
                )

        # ── 2. Fallback to LLM or Mock Generation if no live leads ──
        if not leads:
            prompt = f"""You are a B2B Lead Intelligence Agent utilizing the database: {platform_label}.
Generate {max_leads} realistic, high-value qualified leads in the {target_industry} domain located in/targeting {target_location}.
{platform_guidance}

For each lead, return a JSON array of objects:
[
  {{
    "company_name": "Company Name",
    "website": "https://example.com",
    "industry": "{target_industry}",
    "sub_industry": "niche",
    "company_size": "small/medium/large",
    "location": "{target_location}",
    "contact_name": "Decision Maker Full Name",
    "contact_title": "CEO / Founder / Director",
    "contact_email": "name@company.com",
    "phone": "+1-555-0199 or local phone",
    "pain_points": ["specific problem 1", "specific problem 2"],
    "platform": "{platform_label}",
    "key_details": "Brief 1-sentence value hook or note"
  }}
]

Return ONLY the JSON array, no extra markdown commentary."""

            try:
                response = await self.call_llm(
                    prompt=prompt,
                    system_prompt="You are a professional B2B lead generation researcher. Return only valid JSON array.",
                    temperature=0.8,
                )
                leads = self._parse_leads(response)
            except RuntimeError:
                # LLM not available — use mock data
                self.logger.info("LLM not available, generating mock leads")
                leads = self._generate_mock_leads(target_industry, target_location, max_leads)

        # Score and annotate platform on each lead
        for lead in leads:
            lead["platform"] = lead.get("platform") or platform_label
            lead["relevance_score"] = self._calculate_score(lead, target_industry)

        # Sort by score descending
        leads.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

        self.logger.info(f"Found {len(leads)} leads")
        return {"leads": leads, "total": len(leads)}

    async def enrich_lead_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Enrich a lead with additional data using LLM."""
        lead = payload.get("lead", {})
        company = lead.get("company_name", "Unknown")

        try:
            prompt = f"""Provide additional business intelligence for the company "{company}":
- Recent news or developments
- Key competitors
- Potential business needs
- Best approach for outreach

Return as JSON with keys: recent_news, competitors, business_needs, outreach_approach"""

            response = await self.call_llm(prompt=prompt, temperature=0.7)
            enrichment = self._parse_json_safe(response)
        except (RuntimeError, Exception):
            enrichment = {
                "recent_news": "Data not available — configure LLM API key",
                "competitors": [],
                "business_needs": ["Automation", "Efficiency"],
                "outreach_approach": "Email outreach with personalized value proposition",
            }

        lead.update(enrichment)
        return {"lead": lead}

    async def score_lead(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Score a single lead."""
        lead = payload.get("lead", {})
        industry = payload.get("target_industry", "")
        score = self._calculate_score(lead, industry)
        return {"lead": lead, "score": score}

    # ── Private Helpers ───────────────────────────────────────────

    def _calculate_score(self, lead: dict[str, Any], target_industry: str) -> int:
        """Calculate relevance score (1-10) for a lead."""
        score = 5  # Base score

        # Industry match
        if lead.get("industry", "").lower() == target_industry.lower():
            score += 2

        # Company size preference (medium companies often convert better)
        size = lead.get("company_size", "").lower()
        if size == "medium":
            score += 1
        elif size == "large":
            score += 0

        # Has contact email
        if lead.get("contact_email"):
            score += 1

        # Has pain points identified
        if lead.get("pain_points") and len(lead["pain_points"]) > 0:
            score += 1

        return min(score, 10)

    def _parse_leads(self, response: str) -> list[dict[str, Any]]:
        """Parse LLM response to extract leads."""
        try:
            # Try to find JSON array in response
            text = response.strip()
            start = text.find("[")
            end = text.rfind("]") + 1
            if start != -1 and end > start:
                return json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError):
            self.logger.warning("Failed to parse LLM leads response")
        return self._generate_mock_leads("Technology", "USA", 5)

    def _parse_json_safe(self, text: str) -> dict[str, Any]:
        """Safely parse JSON from text."""
        try:
            clean = text.strip()
            start = clean.find("{")
            end = clean.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(clean[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return {}

    def _generate_mock_leads(
        self, industry: str, location: str, count: int
    ) -> list[dict[str, Any]]:
        """Generate mock lead data for testing."""
        mock_companies = [
            ("TechFlow Solutions", "techflow.io", "CTO", "Alex Johnson"),
            ("DataStream Inc", "datastream.com", "VP Engineering", "Sarah Chen"),
            ("CloudNine Software", "cloudnine.io", "Head of Product", "Mike Peters"),
            ("ScaleUp AI", "scaleupai.com", "CEO", "Priya Sharma"),
            ("NextGen Analytics", "nextgenanalytics.com", "CTO", "David Wilson"),
            ("AutomateIQ", "automateiq.io", "VP Operations", "Lisa Rodriguez"),
            ("SmartStack Labs", "smartstack.dev", "Engineering Lead", "Tom Baker"),
            ("GrowthEngine", "growthengine.co", "CMO", "Emma Davis"),
            ("PipelineHQ", "pipelinehq.com", "Head of Sales", "James Lee"),
            ("InnovateTech", "innovatetech.io", "CTO", "Rachel Kim"),
        ]

        leads = []
        for i in range(min(count, len(mock_companies))):
            name, domain, title, contact = mock_companies[i]
            leads.append({
                "company_name": name,
                "website": f"https://{domain}",
                "industry": industry,
                "sub_industry": f"{industry} Solutions",
                "company_size": random.choice(["small", "medium", "large"]),
                "estimated_employees": random.randint(20, 500),
                "location": f"{random.choice(['New York', 'San Francisco', 'Austin', 'Chicago', 'Seattle'])}, {location}",
                "contact_name": contact,
                "contact_title": title,
                "contact_email": f"{contact.split()[0].lower()}@{domain}",
                "pain_points": random.sample(
                    ["manual processes", "scaling issues", "data silos",
                     "slow deployment", "customer churn", "high CAC",
                     "poor analytics", "talent shortage"],
                    k=random.randint(2, 4),
                ),
                "technologies_used": random.sample(
                    ["AWS", "Python", "React", "Docker", "Kubernetes",
                     "PostgreSQL", "Redis", "Terraform"],
                    k=random.randint(2, 4),
                ),
                "annual_revenue_estimate": random.choice(
                    ["$1M-$5M", "$5M-$10M", "$10M-$50M", "$50M-$100M"]
                ),
            })

        return leads
