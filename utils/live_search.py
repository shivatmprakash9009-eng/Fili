"""
Provider adapters for first-party business discovery.

These connectors return only fields actually supplied by the upstream provider.
They do not synthesize contact names, role emails, phone numbers, employee counts,
locations, or verification claims.
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import random
import re
from typing import Any
from urllib.parse import quote_plus, unquote, urlsplit

import httpx

logger = logging.getLogger("live_search")

API_TIMEOUT = httpx.Timeout(18.0, connect=6.0)
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
MAX_RETRIES = 3


class ProviderRequestError(RuntimeError):
    """Safe, machine-readable upstream provider failure."""

    def __init__(self, provider: str, reason: str, status_code: int | None = None) -> None:
        super().__init__(f"{provider}: {reason}")
        self.provider = provider
        self.reason = reason
        self.status_code = status_code


def get_apollo_key() -> str:
    return os.getenv("APOLLO_API_KEY", "").strip()


def get_serpapi_key() -> str:
    return os.getenv("SERPAPI_API_KEY", "").strip()


def _clean_company_name(value: Any) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def _website(value: Any) -> str:
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


async def _request_json(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bounded retry for transient provider failures; never retry hard 4xx errors."""
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=API_TIMEOUT, follow_redirects=False) as client:
                response = await client.request(
                    method, url, params=params, headers=headers, json=json_body
                )
            if response.status_code in RETRYABLE_STATUS_CODES:
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = min(8.0, max(0.25, float(retry_after)))
                except ValueError:
                    delay = min(8.0, (2 ** attempt) + random.random() * 0.25)
                if attempt + 1 < MAX_RETRIES:
                    await asyncio.sleep(delay)
                    continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Provider returned a non-object JSON response")
            return payload
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, ValueError) as exc:
            last_error = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None and status not in RETRYABLE_STATUS_CODES:
                break
            if attempt + 1 < MAX_RETRIES:
                await asyncio.sleep(min(8.0, (2 ** attempt) + random.random() * 0.25))
    status_code = getattr(getattr(last_error, "response", None), "status_code", None)
    host = urlsplit(url).hostname or "upstream"
    if status_code in {401, 403}:
        reason = "provider_authentication_or_permission_denied"
    elif status_code == 429:
        reason = "provider_rate_limit_exceeded"
    elif status_code is not None and status_code >= 500:
        reason = "provider_temporarily_unavailable"
    elif isinstance(last_error, ValueError):
        reason = "provider_returned_invalid_json"
    else:
        reason = "provider_network_or_timeout_error"
    logger.warning("Provider request failed (%s %s): %s", method, host, reason)
    raise ProviderRequestError(host, reason, status_code) from last_error


async def fetch_apollo_leads(
    industry: str,
    location: str,
    max_leads: int = 5,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Search Apollo organizations using its current mixed-company search endpoint."""
    key = (api_key or get_apollo_key()).strip()
    if not key:
        return []
    limit = max(1, min(int(max_leads), 100))
    keywords = [part.strip() for part in re.split(r"[,/]+", industry) if part.strip()]
    payload: dict[str, Any] = {"page": 1, "per_page": limit}
    if keywords:
        payload["q_organization_keyword_tags"] = keywords[:5]
    if location and "global" not in location.casefold():
        payload["organization_locations"] = [location]

    data = await _request_json(
        "POST",
        "https://api.apollo.io/api/v1/mixed_companies/search",
        headers={"accept": "application/json", "content-type": "application/json", "X-Api-Key": key},
        json_body=payload,
    )
    organizations = data.get("organizations", [])
    leads: list[dict[str, Any]] = []
    if not isinstance(organizations, list):
        return leads

    for org in organizations[:limit]:
        if not isinstance(org, dict):
            continue
        name = _clean_company_name(org.get("name"))
        if not name:
            continue
        city = str(org.get("city") or "").strip()
        state = str(org.get("state") or org.get("state_name") or "").strip()
        country = str(org.get("country") or "").strip()
        address = ", ".join(part for part in (city, state, country) if part)
        domain = str(org.get("primary_domain") or "").strip()
        website = _website(org.get("website_url") or (f"https://{domain}" if domain else ""))
        employees = org.get("estimated_num_employees")
        leads.append({
            "company_name": name,
            "website": website,
            "industry": industry,
            "location": address,
            "phone": str(org.get("sanitized_phone") or ""),
            "company_size": str(employees) if employees is not None else "",
            "estimated_employees": employees,
            "linkedin_url": str(org.get("linkedin_url") or ""),
            "platform": "Apollo.io",
            "source_type": "provider_api",
            "source_id": str(org.get("id") or ""),
            "source_url": website,
            "is_live_data": True,
            "contact_name": "",
            "contact_title": "",
            "contact_email": "",
            "contact_verified": False,
        })
    logger.info("Apollo organization search returned %d provider records", len(leads))
    return leads


async def fetch_serpapi_leads(
    query: str,
    location: str,
    max_leads: int = 5,
    api_key: str | None = None,
    engine: str = "google",
) -> list[dict[str, Any]]:
    """Search Google Maps or Google Search through SerpAPI."""
    key = (api_key or get_serpapi_key()).strip()
    if not key:
        return []
    safe_limit = max(1, min(int(max_leads), 100))
    params: dict[str, Any] = {
        "api_key": key,
        "engine": engine,
        "q": f"{query} in {location}".strip() if location else query,
    }
    if engine == "google_maps":
        params["type"] = "search"
    else:
        params["num"] = min(safe_limit, 100)

    data = await _request_json(
        "GET", "https://serpapi.com/search.json", params=params
    )
    leads: list[dict[str, Any]] = []

    if engine == "google_maps":
        local_results = data.get("local_results", [])
        if not isinstance(local_results, list):
            return leads
        for item in local_results[:safe_limit]:
            if not isinstance(item, dict):
                continue
            name = _clean_company_name(item.get("title"))
            if not name:
                continue
            leads.append({
                "company_name": name,
                "website": _website(item.get("website")),
                "industry": query,
                "location": str(item.get("address") or ""),
                "phone": str(item.get("phone") or ""),
                "rating": item.get("rating"),
                "reviews": item.get("reviews"),
                "business_type": str(item.get("type") or ""),
                "platform": "Google Maps via SerpAPI",
                "source_type": "provider_api",
                "source_id": str(item.get("place_id") or item.get("data_id") or ""),
                "source_url": _website(item.get("website")),
                "is_live_data": True,
                "contact_name": "",
                "contact_title": "",
                "contact_email": "",
                "contact_verified": False,
            })
    else:
        organic_results = data.get("organic_results", [])
        if not isinstance(organic_results, list):
            return leads
        blocked_domains = {
            "google.com", "youtube.com", "wikipedia.org", "facebook.com",
            "linkedin.com", "yelp.com",
        }
        for item in organic_results:
            if len(leads) >= safe_limit or not isinstance(item, dict):
                break
            link = _website(item.get("link"))
            host = urlsplit(link).hostname.casefold().removeprefix("www.") if link else ""
            if not host or any(host == blocked or host.endswith("." + blocked) for blocked in blocked_domains):
                continue
            name = _clean_company_name(item.get("title")).split(" - ")[0].split(" | ")[0].strip()
            if not name:
                continue
            leads.append({
                "company_name": name,
                "website": link,
                "industry": query,
                "location": "",
                "platform": "Google Search via SerpAPI",
                "source_type": "search_result",
                "result_position": item.get("position"),
                "source_url": link,
                "key_details": str(item.get("snippet") or "")[:500],
                "is_live_data": True,
                "contact_name": "",
                "contact_title": "",
                "contact_email": "",
                "phone": "",
                "contact_verified": False,
            })
    logger.info("SerpAPI %s returned %d source records", engine, len(leads))
    return leads


async def fetch_indiamart_leads(
    query: str,
    location: str,
    max_leads: int = 5,
) -> list[dict[str, Any]]:
    """Optional IndiaMART HTML connector; disabled unless explicitly enabled.

    Prefer a licensed/official provider integration for production. HTML markup
    is not a stable API and scraped records remain unverified.
    """
    if os.getenv("FILI_ENABLE_INDIAMART_SCRAPER", "false").casefold() not in {"1", "true", "yes"}:
        logger.info("IndiaMART HTML connector is disabled; enable only after policy review.")
        return []
    url = f"https://dir.indiamart.com/search.mp?ss={quote_plus(f'{query} {location}'.strip())}"
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "FiliResearchBot/1.0"})
            response.raise_for_status()
            source = response.text[:2_000_000]
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("IndiaMART request failed: %s", exc)
        return []

    matches = re.findall(
        r'<a[^>]+class="[^"]*(?:gpname|to-hd|cmpny)[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        source, re.IGNORECASE | re.DOTALL,
    )
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link, raw_name in matches:
        name = _clean_company_name(raw_name)
        if len(name) < 3 or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        href = link if link.startswith("http") else f"https://www.indiamart.com{link}"
        output.append({
            "company_name": name,
            "website": _website(href),
            "industry": query,
            "location": "",
            "platform": "IndiaMART HTML (unverified)",
            "source_type": "scraped_listing",
            "source_url": _website(href),
            "is_live_data": True,
            "contact_name": "",
            "contact_title": "",
            "contact_email": "",
            "phone": "",
            "contact_verified": False,
        })
        if len(output) >= max(1, min(int(max_leads), 100)):
            break
    return output


async def fetch_duckduckgo_leads(
    query: str,
    location: str,
    max_leads: int = 5,
    platform_label: str = "Web Search",
) -> list[dict[str, Any]]:
    """Fallback web search. Search snippets are discovery hints, not verified leads."""
    full_query = f"{query} companies in {location} official website".strip()
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT, follow_redirects=True) as client:
            response = await client.post(
                "https://html.duckduckgo.com/html/",
                data={"q": full_query},
                headers={"User-Agent": "Mozilla/5.0 FiliResearch/1.0"},
            )
            response.raise_for_status()
            source = response.text[:2_000_000]
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)
        return []

    results = re.findall(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        source, re.IGNORECASE | re.DOTALL,
    )
    leads: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link, raw_title in results:
        title = _clean_company_name(raw_title).split(" - ")[0].split(" | ")[0].strip()
        redirected = re.search(r"(?:\?|&)uddg=([^&]+)", link)
        actual_url = unquote(redirected.group(1)) if redirected else html.unescape(link)
        actual_url = _website(actual_url)
        if not title or not actual_url:
            continue
        host = urlsplit(actual_url).hostname.casefold().removeprefix("www.")
        if any(part in host for part in ("duckduckgo", "google", "wikipedia", "youtube", "facebook", "linkedin")):
            continue
        identity = f"{normalize_key(title)}:{host}"
        if identity in seen:
            continue
        seen.add(identity)
        leads.append({
            "company_name": title,
            "website": actual_url,
            "industry": query,
            "location": "",
            "platform": f"{platform_label} (search hint)",
            "source_type": "search_result",
            "source_url": actual_url,
            "is_live_data": True,
            "contact_name": "",
            "contact_title": "",
            "contact_email": "",
            "phone": "",
            "contact_verified": False,
        })
        if len(leads) >= max(1, min(int(max_leads), 100)):
            break
    return leads


def normalize_key(value: str) -> str:
    """Small local key normalizer to avoid importing higher-level domain code."""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


async def fetch_github_tech_leads(
    industry: str,
    location: str,
    max_leads: int = 5,
) -> list[dict[str, Any]]:
    """Find organizations behind popular public GitHub repositories (no API key).

    Only fields GitHub actually returns are kept. GitHub does not provide a
    contact person, email, employee count or address, so those stay empty.
    ``location`` is accepted for interface symmetry but is never claimed as a
    fact about a result.
    """
    limit = max(1, min(int(max_leads), 30))
    data = await _request_json(
        "GET",
        "https://api.github.com/search/repositories",
        params={"q": industry, "sort": "stars", "order": "desc", "per_page": limit},
        headers={
            "User-Agent": "Fili-Prospecting/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    items = data.get("items", [])
    leads: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not isinstance(items, list):
        return leads
    for item in items:
        if not isinstance(item, dict):
            continue
        owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
        login = str(owner.get("login") or "").strip()
        if not login or login.casefold() in seen:
            continue
        seen.add(login.casefold())
        repo_url = str(item.get("html_url") or "")
        homepage = _website(item.get("homepage"))
        profile_url = str(owner.get("html_url") or f"https://github.com/{login}")
        leads.append({
            "company_name": login,
            "website": homepage,
            "industry": industry,
            "location": "",
            "platform": "GitHub public repositories",
            "source_type": "provider_api",
            "source_id": f"github_repo:{item.get('id')}" if item.get("id") else "",
            "source_url": repo_url or profile_url,
            "github_repo": repo_url,
            "github_owner_type": str(owner.get("type") or ""),
            "key_details": str(item.get("description") or "")[:500],
            "is_live_data": True,
            "contact_name": "",
            "contact_title": "",
            "contact_email": "",
            "phone": "",
            "contact_verified": False,
        })
        if len(leads) >= limit:
            break
    logger.info("GitHub search returned %d owner records", len(leads))
    return leads


async def fetch_hacker_news_leads(
    industry: str,
    max_leads: int = 5,
) -> list[dict[str, Any]]:
    """Find products launched on Show HN via the public Algolia API (no API key).

    The post title, URL and author handle are provider-supplied. A Hacker News
    username is not a verified person or email, so contact fields stay empty.
    """
    limit = max(1, min(int(max_leads), 30))
    data = await _request_json(
        "GET",
        "https://hn.algolia.com/api/v1/search",
        params={"query": industry, "tags": "show_hn", "hitsPerPage": min(limit * 3, 60)},
        headers={"User-Agent": "Fili-Prospecting/1.0", "Accept": "application/json"},
    )
    hits = data.get("hits", [])
    leads: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not isinstance(hits, list):
        return leads
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        link = _website(hit.get("url"))
        host = urlsplit(link).hostname.casefold().removeprefix("www.") if link else ""
        if not host or host.endswith("ycombinator.com") or host in seen:
            continue
        seen.add(host)
        title = _clean_company_name(hit.get("title"))
        title = re.sub(r"^show hn:\s*", "", title, flags=re.IGNORECASE)
        name = re.split(r"\s+[\u2013\u2014-]\s+|\s*:\s+", title, maxsplit=1)[0].strip()[:80]
        if not name:
            continue
        object_id = str(hit.get("objectID") or "")
        leads.append({
            "company_name": name,
            "website": link,
            "industry": industry,
            "location": "",
            "platform": "Hacker News Show HN",
            "source_type": "provider_api",
            "source_id": f"hn:{object_id}" if object_id else "",
            "source_url": f"https://news.ycombinator.com/item?id={object_id}" if object_id else link,
            "hn_author": str(hit.get("author") or ""),
            "key_details": title[:500],
            "is_live_data": True,
            "contact_name": "",
            "contact_title": "",
            "contact_email": "",
            "phone": "",
            "contact_verified": False,
        })
        if len(leads) >= limit:
            break
    logger.info("Hacker News search returned %d launch records", len(leads))
    return leads
