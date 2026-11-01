"""Evidence-first business discovery agent."""

from __future__ import annotations

from typing import Any

from core.base_agent import BaseAgent
from core.task import Task
from utils.lead_quality import (
    deduplicate_leads,
    match_selected_location,
    normalize_discovered_lead,
)
from utils.live_search import (
    fetch_apollo_leads,
    fetch_duckduckgo_leads,
    fetch_indiamart_leads,
    fetch_serpapi_leads,
    get_apollo_key,
    get_serpapi_key,
)


def _matches_selected_city(lead: dict[str, Any], scope: dict[str, Any] | None) -> bool:
    """Return true only when provider address evidence matches city and state."""
    matched, _status = match_selected_location(str(lead.get("location") or ""), scope)
    return matched


class LeadResearcherAgent(BaseAgent):
    """Find businesses using live connectors; never manufacture prospect records.

    AI may assist with later research and qualification, but generated names,
    guessed contacts, and search snippets are not represented as real prospects.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(name="LeadResearcher", **kwargs)

    def get_capabilities(self) -> list[str]:
        return ["research_leads", "enrich_lead", "score_lead"]

    async def process_task(self, task: Task) -> dict[str, Any]:
        if task.task_type == "research_leads":
            return await self.research_leads(task.payload)
        if task.task_type == "enrich_lead":
            return await self.enrich_lead_data(task.payload)
        if task.task_type == "score_lead":
            return await self.score_lead(task.payload)
        raise ValueError(f"Unknown task type: {task.task_type}")

    async def research_leads(self, payload: dict[str, Any]) -> dict[str, Any]:
        target_industry = str(payload.get("target_industry") or "SaaS").strip()[:160]
        target_location = str(payload.get("target_location") or "").strip()[:160]
        location_scope = payload.get("target_location_scope")
        platform = str(payload.get("platform") or "apollo").strip().casefold()
        try:
            max_leads = max(1, min(int(payload.get("max_leads", 10)), 100))
        except (TypeError, ValueError):
            max_leads = 10

        if not target_industry:
            raise ValueError("A target industry or business category is required.")
        if location_scope is not None:
            if not isinstance(location_scope, dict):
                raise ValueError("Location scope must be an object.")
            if not all(str(location_scope.get(field) or "").strip() for field in ("city", "state", "country")):
                raise ValueError("Strict location targeting requires country, state and city.")

        self.logger.info(
            "Discovery start provider=%s industry=%s location=%s limit=%s",
            platform, target_industry, target_location, max_leads,
        )

        providers = {
            "apollo": "Apollo.io",
            "google_maps": "Google Maps via SerpAPI",
            "indiamart": "IndiaMART",
            "web_search": "Web search",
            "linkedin": "LinkedIn",
        }
        if platform not in providers:
            raise ValueError("Unsupported discovery source.")
        provider_name = providers[platform]
        raw_leads: list[dict[str, Any]] = []
        source_status = "not_configured"
        source_message = ""

        if platform == "apollo":
            if get_apollo_key():
                raw_leads = await fetch_apollo_leads(
                    industry=target_industry,
                    location=target_location,
                    max_leads=max_leads,
                )
                source_status = "results" if raw_leads else "no_results_or_provider_error"
            else:
                source_message = "Apollo API key is not configured."
        elif platform == "google_maps":
            if get_serpapi_key():
                raw_leads = await fetch_serpapi_leads(
                    query=target_industry,
                    location=target_location,
                    max_leads=max_leads,
                    engine="google_maps",
                )
                source_status = "results" if raw_leads else "no_results_or_provider_error"
            else:
                source_message = "SerpAPI key is not configured."
        elif platform == "indiamart":
            raw_leads = await fetch_indiamart_leads(
                query=target_industry,
                location=target_location,
                max_leads=max_leads,
            )
            source_status = "results" if raw_leads else "connector_disabled_or_no_results"
            if not raw_leads:
                source_message = (
                    "IndiaMART HTML discovery is disabled by default. Use an approved provider "
                    "integration or enable the connector only after reviewing its terms."
                )
        elif platform == "web_search":
            if get_serpapi_key():
                raw_leads = await fetch_serpapi_leads(
                    query=target_industry,
                    location=target_location,
                    max_leads=max_leads,
                    engine="google",
                )
                source_status = "results" if raw_leads else "no_results_or_provider_error"
            else:
                raw_leads = await fetch_duckduckgo_leads(
                    query=target_industry,
                    location=target_location,
                    max_leads=max_leads,
                )
                source_status = "search_hints" if raw_leads else "no_results"
        else:
            # There is no dedicated LinkedIn connector in this repository.
            source_status = "unsupported_connector"
            source_message = (
                "A dedicated LinkedIn API integration is not configured. "
                "Fili will not label generic web or AI results as LinkedIn data."
            )

        normalized: list[dict[str, Any]] = []
        for raw in raw_leads:
            if not isinstance(raw, dict):
                continue
            lead = normalize_discovered_lead(
                raw,
                provider=provider_name,
                target_industry=target_industry,
                location_scope=location_scope,
            )
            if lead.get("company_name"):
                normalized.append(lead)

        before_deduplication = len(normalized)
        unique = deduplicate_leads(normalized)
        duplicate_count = before_deduplication - len(unique)

        location_rejected = 0
        if location_scope:
            accepted: list[dict[str, Any]] = []
            for lead in unique:
                if lead.get("location_verified"):
                    accepted.append(lead)
                else:
                    location_rejected += 1
            unique = accepted

        unique.sort(
            key=lambda item: (
                item.get("discovery_quality_score", 0),
                bool(item.get("website")),
                bool(item.get("source_id")),
            ),
            reverse=True,
        )
        leads = unique[:max_leads]

        if location_scope and not leads:
            source_status = "no_verified_city_matches"
            if not source_message:
                source_message = (
                    "No provider result contained address evidence matching the selected city and state. "
                    "Fili did not substitute nearby or synthetic records."
                )
        elif not leads and not source_message:
            source_message = (
                "No usable records were returned by the selected source. "
                "Check provider credentials, source coverage and query filters."
            )

        diagnostics = {
            "provider": provider_name,
            "raw_results": len(raw_leads),
            "normalized_results": before_deduplication,
            "duplicates_removed": duplicate_count,
            "rejected_by_location": location_rejected,
            "returned_results": len(leads),
            "strict_city_filter": bool(location_scope),
            "location_verified_results": sum(1 for lead in leads if lead.get("location_verified")),
            "contact_verified_results": sum(1 for lead in leads if lead.get("contact_verified")),
        }

        self.logger.info("Discovery complete: %s", diagnostics)
        return {
            "leads": leads,
            "total": len(leads),
            "provider": provider_name,
            "source_status": source_status,
            "message": source_message,
            "diagnostics": diagnostics,
            "location_filter_applied": bool(location_scope),
        }

    async def enrich_lead_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Generate clearly labelled research hypotheses, not unverified facts."""
        lead = dict(payload.get("lead") or {})
        company = str(lead.get("company_name") or "Unknown business")
        website = str(lead.get("website") or "")
        if not self.llm_client:
            lead["research_status"] = "not_configured"
            lead["research_note"] = "Configure a research provider to enrich this business."
            return {"lead": lead}

        prompt = f"""Analyze only the business information supplied below.
Do not invent news, funding, revenue, employees, customers, contacts, or technologies.
When evidence is absent, return an empty value and explicitly say it is unknown.
Return JSON with keys: observed_facts, unknowns, research_hypotheses.
Each observed fact must cite the supplied field it relies on.

Business name: {company}
Website: {website or "not supplied"}
Location: {lead.get("location") or "not supplied"}
Industry query: {lead.get("industry") or "not supplied"}
Source: {lead.get("platform") or "not supplied"}"""

        try:
            response = await self.call_llm(prompt=prompt, temperature=0.1)
            parsed = self._parse_json_safe(response)
            lead["research_enrichment"] = parsed
            lead["research_status"] = "ai_assisted_unverified"
        except Exception as exc:
            self.logger.warning("Lead research enrichment unavailable: %s", exc)
            lead["research_status"] = "unavailable"
        return {"lead": lead}

    async def score_lead(self, payload: dict[str, Any]) -> dict[str, Any]:
        lead = dict(payload.get("lead") or {})
        score = int(lead.get("discovery_quality_score") or 0)
        return {
            "lead": lead,
            "score": score,
            "score_type": "evidence_completeness_0_to_100",
            "quality_signals": lead.get("quality_signals", []),
        }

    def _parse_json_safe(self, text: str) -> dict[str, Any]:
        import json

        try:
            clean = text.strip()
            start = clean.find("{")
            end = clean.rfind("}") + 1
            if start != -1 and end > start:
                parsed = json.loads(clean[start:end])
                return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            pass
        return {}
