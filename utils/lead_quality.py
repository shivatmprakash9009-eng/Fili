"""Evidence-first lead normalization, location validation and deduplication.

The discovery pipeline must never turn missing data into plausible-looking facts.
Only provider-supplied values are retained as business/contact facts.
"""
from __future__ import annotations

import html
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


def normalize_text(value: Any) -> str:
    """Normalize text for deterministic, token-aware comparisons."""
    raw = unicodedata.normalize("NFKD", str(value or "")).casefold()
    raw = html.unescape(raw)
    raw = "".join(char for char in raw if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", raw).strip()


def contains_place(haystack: str, needle: str) -> bool:
    """Match a full comma-delimited address component, not a substring."""
    normalized_needle = normalize_text(needle)
    if not normalized_needle:
        return False
    components = [
        normalize_text(component)
        for component in re.split(r"[,|·]+", str(haystack or ""))
    ]
    return any(
        component == normalized_needle or component.startswith(normalized_needle + " ")
        for component in components
    )


def match_selected_location(
    location: str,
    scope: dict[str, Any] | None,
) -> tuple[bool, str]:
    """Require provider-supplied city + state evidence for strict city targeting.

    Country is checked when the provider includes it in the address. We do not
    infer a missing city/state from the search query or from a result's rank.
    """
    if not scope:
        return False, "unscoped"
    city = str(scope.get("city") or "").strip()
    state = str(scope.get("state") or "").strip()
    state_code = str(scope.get("state_code") or "").strip()
    country = str(scope.get("country") or "").strip()
    address = str(location or "").strip()
    if not address or not city or not (state or state_code):
        return False, "insufficient_location_evidence"
    address_components = [
        normalize_text(component)
        for component in re.split(r"[,|·]+", address)
    ]
    city_normalized = normalize_text(city)
    matching_city_components = [
        component for component in address_components
        if component == city_normalized or component.startswith(city_normalized + " ")
    ]
    if not matching_city_components:
        return False, "city_mismatch"

    code_match = bool(state_code and contains_place(address, state_code))
    state_normalized = normalize_text(state)
    state_text_match = bool(state and contains_place(address, state))
    # When city and state share the same name (e.g. New York, New York),
    # the city occurrence cannot also prove the state. Require a second
    # address component or an explicit state code.
    if state_normalized and state_normalized == city_normalized:
        state_text_match = len(matching_city_components) >= 2
    if not (state_text_match or code_match):
        return False, "state_mismatch"
    # Do not reject abbreviated/local addresses that omit country, but reject
    # explicit contradictory country evidence.
    if country:
        aliases = {
            "united states": {"united states", "usa", "us"},
            "united kingdom": {"united kingdom", "uk", "great britain"},
            "india": {"india"},
            "canada": {"canada"},
            "australia": {"australia"},
            "germany": {"germany"},
            "france": {"france"},
            "singapore": {"singapore"},
            "united arab emirates": {"united arab emirates", "uae"},
        }
        selected = normalize_text(country)
        selected_aliases = aliases.get(selected, {selected})
        address_components = {
            normalize_text(component)
            for component in re.split(r"[,|·]+", address)
        }
        known_countries = set().union(*aliases.values())
        explicit_countries = address_components.intersection(known_countries)
        if explicit_countries and not explicit_countries.intersection(selected_aliases):
            return False, "country_mismatch"
        country_code = normalize_text(scope.get("country_code") or "")
        if country_code and country_code in address_components:
            pass
    return True, "matched_city_state"


def _valid_website(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        if parsed.username or parsed.password:
            return ""
        return candidate
    except ValueError:
        return ""


def _valid_email(value: Any) -> str:
    email = str(value or "").strip().lower()
    if email in {"", "unknown", "n/a", "none", "null"}:
        return ""
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]{2,}", email):
        return ""
    if email.startswith(("info@", "contact@", "sales@", "partnerships@")):
        # These role addresses are retained only if the provider explicitly
        # returned them. This function does not generate role addresses.
        return email
    return email


def _valid_phone(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or any(token in raw.casefold() for token in ("xxxxx", "xxxx", "555-01", "555-010")):
        return ""
    digits = re.sub(r"\D", "", raw)
    return raw if 7 <= len(digits) <= 15 else ""


def normalize_discovered_lead(
    raw: dict[str, Any],
    *,
    provider: str,
    target_industry: str,
    location_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a canonical lead without inventing any missing business facts."""
    lead = dict(raw)
    company_name = html.unescape(str(raw.get("company_name") or raw.get("name") or "")).strip()
    website = _valid_website(raw.get("website") or raw.get("website_url"))
    location = str(raw.get("location") or raw.get("address") or raw.get("full_address") or "").strip()
    email = _valid_email(raw.get("contact_email") or raw.get("email"))
    phone = _valid_phone(raw.get("phone") or raw.get("sanitized_phone"))
    location_verified, location_status = match_selected_location(location, location_scope)

    lead.update({
        "company_name": company_name,
        "website": website,
        "location": location,
        "industry": str(raw.get("industry") or target_industry).strip(),
        "contact_name": str(raw.get("contact_name") or "").strip(),
        "contact_title": str(raw.get("contact_title") or "").strip(),
        "contact_email": email,
        "phone": phone,
        "platform": str(raw.get("platform") or provider),
        "source_type": str(raw.get("source_type") or "provider_result"),
        "source_id": str(raw.get("source_id") or raw.get("place_id") or raw.get("id") or ""),
        "source_url": str(raw.get("source_url") or raw.get("website") or raw.get("website_url") or ""),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "is_live_data": bool(raw.get("is_live_data", True)),
        "is_synthetic": bool(raw.get("is_synthetic", False)),
        "location_verified": location_verified,
        "location_match_status": location_status,
        "contact_verified": bool(raw.get("contact_verified", False)),
        "email_verification_status": "not_checked" if email else "missing",
        "outreach_enabled": False,
    })

    evidence: dict[str, dict[str, Any]] = {}
    if company_name:
        evidence["company_name"] = {"source": provider, "status": "provider_supplied"}
    if website:
        evidence["website"] = {"source": provider, "status": "provider_supplied"}
    if location:
        evidence["location"] = {
            "source": provider,
            "status": "matched" if location_verified else location_status,
        }
    if email:
        evidence["contact_email"] = {"source": provider, "status": "provider_supplied_unverified"}
    if phone:
        evidence["phone"] = {"source": provider, "status": "provider_supplied_unverified"}
    if lead["source_id"]:
        evidence["source_id"] = {"source": provider, "status": "provider_supplied"}
    lead["field_evidence"] = evidence

    # Quality measures evidence completeness, not likelihood to convert.
    score = 0
    signals: list[str] = []
    if company_name:
        score += 30
        signals.append("company_name_from_source")
    if website:
        score += 20
        signals.append("website_from_source")
    if location:
        score += 5
        signals.append("address_from_source")
    if location_verified:
        score += 20
        signals.append("selected_city_and_state_match")
    if lead["source_id"]:
        score += 10
        signals.append("stable_provider_identifier")
    if phone:
        score += 5
        signals.append("phone_from_source_not_verified")
    if email:
        score += 5
        signals.append("email_from_source_not_verified")
    if raw.get("rating") is not None or raw.get("reviews") is not None:
        score += 5
        signals.append("provider_reputation_signal")
    lead["discovery_quality_score"] = min(score, 100)
    lead["quality_signals"] = signals
    # Evidence completeness is not buyer relevance; relevance is intentionally
    # left unscored until a product ICP or explicit ranking model is defined.
    lead["relevance_score"] = None
    lead["relevance_score_status"] = "not_scored"
    lead["outreach_enabled"] = bool(
        lead["contact_verified"] and email and not lead["is_synthetic"]
    )
    return lead


def deduplicate_leads(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate by provider identity, then domain + normalized name/location."""
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lead in leads:
        source_id = str(lead.get("source_id") or "").strip().casefold()
        website = _valid_website(lead.get("website"))
        host = urlsplit(website).hostname.casefold().removeprefix("www.") if website else ""
        name = normalize_text(lead.get("company_name"))
        location = normalize_text(lead.get("location"))
        key = (
            f"id:{lead.get('platform', '')}:{source_id}" if source_id
            else f"domain:{host}:{location}" if host
            else f"name:{name}:{location}"
        )
        if not name or key in seen:
            continue
        seen.add(key)
        output.append(lead)
    return output
