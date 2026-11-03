"""Website contact extractor (no API key).

Fetches a handful of public pages from ONE website and reports only what is
literally present in the fetched HTML: mailto/visible e-mail addresses, tel:
links, social profile links and the page title. Nothing is guessed. When a
field is not found it stays empty, and when no page can be fetched no lead is
returned at all.

Safety: every request (and every redirect target) is validated against
``validate_public_http_url`` so localhost, private, link-local and otherwise
non-public destinations are refused, redirects are followed manually, and
response bodies are capped.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import logging
import re
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from utils.prospecting import validate_public_http_url

logger = logging.getLogger("domain_scraper")

MAX_PAGES = 5
MAX_REDIRECTS = 3
MAX_BODY_BYTES = 1_000_000
REQUEST_TIMEOUT = httpx.Timeout(8.0, connect=4.0)
SUBPATHS = ("/contact", "/contact-us", "/about", "/about-us", "/team")
REDIRECT_CODES = {301, 302, 303, 307, 308}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
MAILTO_RE = re.compile(r"""href=["']mailto:([^"'?#>\s]+)""", re.IGNORECASE)
TEL_RE = re.compile(r"""href=["']tel:([^"']+)["']""", re.IGNORECASE)
SOCIAL_RE = re.compile(
    r"""href=["'](https?://(?:www\.)?(?:linkedin\.com/(?:company|in)|twitter\.com|x\.com|github\.com)/[A-Za-z0-9_.\-/]+)["']""",
    re.IGNORECASE,
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
SITE_NAME_RE = re.compile(
    r"""<meta[^>]+property=["']og:site_name["'][^>]+content=["']([^"']+)["']""", re.IGNORECASE
)
ASSET_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js", ".woff", ".woff2")
PLACEHOLDER_DOMAINS = {"example.com", "example.org", "example.net", "domain.com", "email.com", "yourdomain.com"}


def normalize_target(domain_or_url: str) -> str:
    """Return an https URL for a bare domain, or the URL unchanged."""
    raw = str(domain_or_url or "").strip()
    if not raw:
        raise ValueError("A website domain or URL is required.")
    return raw if "://" in raw else f"https://{raw}"


def looks_like_domain(value: str) -> bool:
    """True for a bare hostname or URL such as ``acme.com`` or ``https://acme.com/about``."""
    raw = str(value or "").strip()
    return bool(re.fullmatch(
        r"(?:https?://)?(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}(?::\d{2,5})?(?:/\S*)?",
        raw,
    ))


def _clean_email(value: str) -> str:
    email = unquote(str(value or "")).strip().strip(".,;:()[]<>\"'").lower()
    if not EMAIL_RE.fullmatch(email) or email.endswith(ASSET_SUFFIXES):
        return ""
    if email.rsplit("@", 1)[1] in PLACEHOLDER_DOMAINS:
        return ""
    return email


def _clean_phone(value: str) -> str:
    raw = unquote(str(value or "")).strip()
    digits = re.sub(r"\D", "", raw)
    if not 7 <= len(digits) <= 15:
        return ""
    return ("+" if raw.startswith("+") else "") + digits


async def _fetch_page(client: httpx.AsyncClient, url: str) -> str | None:
    """Fetch one page; revalidate every redirect target. Returns HTML or None."""
    target = url
    for hop in range(MAX_REDIRECTS + 1):
        try:
            # DNS resolution inside the validator is blocking; keep it off the event loop.
            target = await asyncio.to_thread(validate_public_http_url, target)
        except ValueError as exc:
            logger.info("Refusing to crawl %s: %s", url, exc)
            return None
        try:
            async with client.stream("GET", target) as response:
                if response.status_code in REDIRECT_CODES:
                    location = response.headers.get("location")
                    if not location or hop == MAX_REDIRECTS:
                        return None
                    target = urljoin(target, location)
                    continue
                if response.status_code != 200:
                    return None
                content_type = response.headers.get("content-type", "").lower()
                if content_type and "html" not in content_type and "text" not in content_type:
                    return None
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_BODY_BYTES:
                        return None
                    chunks.append(chunk)
                return b"".join(chunks).decode("utf-8", errors="replace")
        except httpx.HTTPError as exc:
            logger.debug("Failed to crawl %s: %s", target, exc)
            return None
    return None


async def scrape_domain_leads(
    domain_or_url: str,
    industry: str = "",
    location: str = "",
) -> list[dict[str, Any]]:
    """Crawl one public website and return at most one evidence-only lead."""
    base_url = normalize_target(domain_or_url)
    # Raises ValueError for private/local targets before any request is made.
    base_url = await asyncio.to_thread(validate_public_http_url, base_url)
    parts = urlsplit(base_url)
    root_domain = (parts.hostname or "").removeprefix("www.")
    origin = f"{parts.scheme}://{parts.netloc}"

    page_urls = [base_url] + [urljoin(origin, path) for path in SUBPATHS]
    emails: dict[str, str] = {}  # email -> page it was found on
    phones: dict[str, str] = {}
    socials: list[str] = []
    page_title = ""
    site_name = ""
    pages_fetched = 0

    headers = {"User-Agent": "FiliResearchBot/1.0 (+public business contact discovery)"}
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT, follow_redirects=False, trust_env=False, headers=headers
    ) as client:
        for url in page_urls[:MAX_PAGES]:
            body = await _fetch_page(client, url)
            if body is None:
                continue
            pages_fetched += 1
            visible = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body)
            for raw in MAILTO_RE.findall(body) + EMAIL_RE.findall(html_lib.unescape(visible)):
                email = _clean_email(raw)
                if email:
                    emails.setdefault(email, url)
            for raw in TEL_RE.findall(body):
                phone = _clean_phone(raw)
                if phone:
                    phones.setdefault(phone, url)
            for link in SOCIAL_RE.findall(body):
                if link not in socials:
                    socials.append(link)
            if not page_title:
                match = TITLE_RE.search(body)
                if match:
                    page_title = re.sub(r"\s+", " ", html_lib.unescape(match.group(1))).strip()
            if not site_name:
                match = SITE_NAME_RE.search(body)
                if match:
                    site_name = html_lib.unescape(match.group(1)).strip()

    if pages_fetched == 0:
        logger.info("No pages could be fetched from %s", root_domain)
        return []

    # Prefer an address on the company's own domain, but never invent one.
    ordered_emails = sorted(emails, key=lambda e: (not e.endswith("@" + root_domain), e))
    primary_email = ordered_emails[0] if ordered_emails else ""
    primary_phone = next(iter(phones), "")
    company_name = site_name or re.split(r"\s+[|–—-]\s+", page_title, maxsplit=1)[0].strip()
    name_is_derived = not company_name
    if name_is_derived:
        company_name = root_domain.split(".")[0].capitalize()

    lead = {
        "company_name": company_name[:160],
        "company_name_derived_from_domain": name_is_derived,
        "website": base_url,
        "industry": industry,
        "location": "",
        "contact_name": "",
        "contact_title": "",
        "contact_email": primary_email,
        "phone": primary_phone,
        "linkedin_url": next((s for s in socials if "linkedin.com" in s.lower()), ""),
        "platform": f"Website crawl ({root_domain})",
        "source_type": "website_crawl",
        "source_id": f"domain:{root_domain}",
        "source_url": emails.get(primary_email) or base_url,
        "all_extracted_emails": ordered_emails,
        "all_extracted_phones": list(phones),
        "social_links": socials,
        "pages_fetched": pages_fetched,
        "is_live_data": True,
        "contact_verified": False,
    }
    logger.info(
        "Website crawl of %s: pages=%d emails=%d phones=%d",
        root_domain, pages_fetched, len(emails), len(phones),
    )
    return [lead]
