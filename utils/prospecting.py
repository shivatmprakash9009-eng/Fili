"""Utilities for contact validation, CRM exports, and prospect enrichment.

DNS/MX verification validates domain mail-routing configuration only. It does not
prove that a specific mailbox exists or is deliverable.
"""
from __future__ import annotations

import csv
import io
import re
import socket
import ssl
from typing import Any
from urllib.parse import urlparse

PLACEHOLDER_EMAILS = {"", "unknown", "n/a", "none", "null"}
PLACEHOLDER_PHONES = ("555-01", "555-010", "xxxxx", "xxxx")


def clean_phone(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw or any(token in raw.lower() for token in PLACEHOLDER_PHONES):
        return ""
    digits = re.sub(r"\D", "", raw)
    return raw if 7 <= len(digits) <= 15 else ""


def email_domain(value: Any) -> str:
    email = str(value or "").strip().lower()
    if email in PLACEHOLDER_EMAILS or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return ""
    return email.rsplit("@", 1)[1].strip(".")


def verify_email_domain(value: Any, timeout: float = 3.0) -> dict[str, Any]:
    """Return MX/domain status; deliberately never labels an inbox 'verified'."""
    domain = email_domain(value)
    if not domain:
        return {"status": "invalid_format", "mx_found": False, "mailbox_verified": False}
    try:
        import dns.resolver  # type: ignore
        answers = dns.resolver.resolve(domain, "MX", lifetime=timeout)
        hosts = sorted({str(answer.exchange).rstrip(".") for answer in answers})
        return {"status": "mx_found", "mx_found": bool(hosts), "mx_hosts": hosts,
                "mailbox_verified": False, "note": "MX confirms domain mail routing, not mailbox existence."}
    except ImportError:
        try:
            socket.getaddrinfo(domain, 25, type=socket.SOCK_STREAM)
            return {"status": "domain_resolves_mx_unchecked", "mx_found": False,
                    "mailbox_verified": False, "note": "Install dnspython for MX lookup; domain resolution is not MX verification."}
        except OSError:
            return {"status": "dns_lookup_failed", "mx_found": False, "mailbox_verified": False}
    except Exception as exc:
        return {"status": "mx_not_confirmed", "mx_found": False, "mailbox_verified": False,
                "note": str(exc)[:180]}


def enrich_lead(lead: dict[str, Any], verify_mx: bool = True) -> dict[str, Any]:
    enriched = dict(lead)
    enriched["phone"] = clean_phone(enriched.get("phone"))
    email = str(enriched.get("contact_email") or "").strip()
    if email_domain(email):
        enriched["email_verification"] = verify_email_domain(email) if verify_mx else {
            "status": "not_checked", "mx_found": False, "mailbox_verified": False
        }
    else:
        enriched["contact_email"] = ""
        enriched["email_verification"] = {
            "status": "missing_or_placeholder", "mx_found": False, "mailbox_verified": False
        }
    enriched["phone_available"] = bool(enriched["phone"])
    enriched["email_domain"] = email_domain(enriched.get("contact_email"))
    return enriched


def tech_stack_signals(url: str, html: str = "", headers: dict[str, str] | None = None) -> list[str]:
    """Best-effort public HTML/header fingerprint; signals are not guaranteed."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    domain = parsed.hostname or ""
    text = (html or "").lower()
    header_text = " ".join(f"{k}:{v}" for k, v in (headers or {}).items()).lower()
    haystack = text + " " + header_text
    checks = {
        "Shopify": ("cdn.shopify.com", "shopify.theme", "x-shopid"),
        "WordPress": ("wp-content", "wp-includes", "wordpress"),
        "WooCommerce": ("woocommerce",),
        "Webflow": ("webflow.js", "webflow.com"),
        "Wix": ("wixstatic.com", "wix.com"),
        "Next.js": ("_next/static", "__next_data__"),
        "React": ("react-dom", "data-reactroot", "__react"),
        "HubSpot": ("js.hs-scripts.com", "hubspot"),
        "Google Tag Manager": ("googletagmanager.com",),
        "Cloudflare": ("cf-ray", "cloudflare"),
        "Stripe": ("js.stripe.com", "stripe.com/v3"),
    }
    found = [name for name, needles in checks.items() if any(n in haystack for n in needles)]
    if domain.endswith("webflow.io"):
        found.append("Webflow")
    return sorted(set(found))


def fetch_tech_stack(url: str, timeout: float = 5.0) -> dict[str, Any]:
    try:
        import httpx
        target = url if url.startswith(("http://", "https://")) else f"https://{url}"
        with httpx.Client(timeout=timeout, follow_redirects=True,
                          headers={"User-Agent": "FiliTechSignals/1.0"}) as client:
            response = client.get(target)
        signals = tech_stack_signals(str(response.url), response.text[:1_000_000], dict(response.headers))
        return {"status": "scanned", "signals": signals, "http_status": response.status_code,
                "final_url": str(response.url), "note": "Best-effort public fingerprint; not a complete infrastructure inventory."}
    except Exception as exc:
        return {"status": "unavailable", "signals": [], "note": str(exc)[:180]}


def build_follow_up_sequence(lead: dict[str, Any]) -> list[dict[str, Any]]:
    company = str(lead.get("company_name") or "your team")
    contact = str(lead.get("contact_name") or "there")
    subject = str(lead.get("email_subject") or f"Idea for {company}")
    first = str(lead.get("email_body") or f"Hi {contact},\n\nI wanted to share a relevant idea for {company}.")
    return [
        {"step": 1, "day": 1, "label": "Value hook", "subject": subject, "body": first},
        {"step": 2, "day": 3, "label": "Insight follow-up", "subject": f"One more idea for {company}",
         "body": f"Hi {contact},\n\nFollowing up with one additional thought for {company}. A short example or relevant result may help assess whether this is worth exploring.\n\nWould a brief overview be useful?"},
        {"step": 3, "day": 7, "label": "Polite close", "subject": f"Should I close the loop, {contact}?",
         "body": f"Hi {contact},\n\nI don't want to clutter your inbox. Should I close the loop for now, or would a short conversation about {company}'s priorities be useful?\n\nIf this isn't relevant, reply 'no' and I won't follow up."},
    ]


def csv_export(leads: list[dict[str, Any]]) -> str:
    fields = ["company_name", "contact_name", "contact_title", "contact_email", "phone",
              "email_verification_status", "website", "tech_stack", "location", "industry",
              "relevance_score", "email_subject", "email_body", "platform"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for lead in leads:
        row = dict(lead)
        row["email_verification_status"] = (row.get("email_verification") or {}).get("status", "not_checked")
        row["tech_stack"] = ", ".join(row.get("tech_stack") or [])
        writer.writerow({key: (value if isinstance(value, (str, int, float)) else "") for key, value in row.items()})
    return output.getvalue()
