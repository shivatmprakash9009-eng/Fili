"""Fili v1 developer API.

Run with: uvicorn api_v1:app --host 0.0.0.0 --port 8080
Firebase ID tokens manage keys; fili_live_* API keys access prospect endpoints.
All persistent access is server-side through the Supabase service-role key.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import threading
import time
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

import firebase_admin
import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from firebase_admin import auth as firebase_auth, credentials
from pydantic import BaseModel, Field, field_validator

from utils.lead_quality import deduplicate_leads, normalize_discovered_lead
from utils.live_search import (
    ProviderRequestError,
    fetch_apollo_leads,
    fetch_serpapi_leads,
    get_apollo_key,
    get_serpapi_key,
)
from utils.prospecting import enrich_lead

app = FastAPI(
    title="Fili API",
    version="1.1.0",
    description="Evidence-first B2B prospect discovery and research API.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

def _cors_origins() -> list[str]:
    """Return explicitly trusted browser origins; opaque null origins are intentionally excluded."""
    configured = os.getenv("CORS_ALLOWED_ORIGINS", "")
    defaults = "https://fili-nine.vercel.app,http://localhost:8000,http://127.0.0.1:8000"
    return sorted({origin.strip().rstrip("/") for origin in (configured or defaults).split(",") if origin.strip() and origin.strip() != "null"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    expose_headers=["Retry-After", "X-Request-ID"],
    max_age=600,
)

API_PREFIX = "/v1"
MAX_PAGE_SIZE = 100
DEFAULT_RATE_LIMIT = 60
DEFAULT_MAX_ACTIVE_KEYS = 10
DEFAULT_DAILY_SEARCH_LIMIT = 200
SEARCH_ROUTE = f"POST {API_PREFIX}/prospects/search"
USAGE_PAGE_SIZE = 1000
USAGE_MAX_PAGES = 20
LAST_USED_REFRESH_SECONDS = 60


def _env_int(name: str, default: int, low: int = 1, high: int = 1_000_000) -> int:
    try:
        return max(low, min(int(os.getenv(name, str(default))), high))
    except ValueError:
        return default


class SearchRequest(BaseModel):
    industry: str = Field(min_length=2, max_length=120)
    location: str = Field(default="Global", max_length=120)
    sources: list[Literal["apollo", "google_maps", "web_search"]] = Field(
        default_factory=lambda: ["apollo", "google_maps", "web_search"], min_length=1, max_length=3
    )
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("industry", "location")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()


class KeyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    scopes: list[Literal["prospects:read", "prospects:write", "usage:read"]] = Field(
        default_factory=lambda: ["prospects:read", "prospects:write"], min_length=1
    )


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(status_code=503, detail=f"Server configuration missing: {name}")
    return value


def _supabase_request(method: str, table: str, *, params: dict[str, str] | None = None,
                      payload: Any = None, prefer: str | None = None) -> tuple[Any, httpx.Response]:
    base = _required_env("SUPABASE_URL").rstrip("/")
    secret = _required_env("SUPABASE_SERVICE_ROLE_KEY")
    headers = {
        "apikey": secret,
        "Authorization": f"Bearer {secret}",
        "Accept": "application/json",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer
    try:
        response = httpx.request(
            method, f"{base}/rest/v1/{table}", params=params, json=payload,
            headers=headers, timeout=httpx.Timeout(12.0, connect=4.0),
        )
        response.raise_for_status()
        data = response.json() if response.content else None
        return data, response
    except httpx.HTTPStatusError as exc:
        # Never leak database response bodies or credentials to clients.
        raise HTTPException(status_code=503, detail="Database operation failed.") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Database is temporarily unavailable.") from exc


def _firebase_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
        project_id = _required_env("FIREBASE_PROJECT_ID")
        if raw:
            try:
                service_account = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=503, detail="Firebase service account configuration is invalid.") from exc
            cred = credentials.Certificate(service_account)
        else:
            # ADC is supported on managed Google runtimes; never accept a client key here.
            cred = credentials.ApplicationDefault()
        return firebase_admin.initialize_app(cred, {"projectId": project_id})


def _verify_firebase_token(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Firebase bearer token required.")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Firebase bearer token required.")
    try:
        claims = firebase_auth.verify_id_token(token, app=_firebase_app(), check_revoked=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Firebase session is invalid or expired.") from exc
    if not claims.get("uid"):
        raise HTTPException(status_code=401, detail="Firebase identity is missing.")
    return claims


def current_firebase_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return _verify_firebase_token(authorization)


def _hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


# ── Rate limiting ────────────────────────────────────────────────
# In-memory sliding window per API key. It is exact for the single instance this
# service runs on and costs no database round-trips; a multi-instance deployment
# needs a shared counter (for example Redis).
_RATE_WINDOW_SECONDS = 60.0
_rate_events: dict[str, deque[float]] = {}
_rate_lock = threading.Lock()


def _enforce_rate_limit(key_id: str) -> None:
    limit = _env_int("FILI_API_RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT, 1, 100_000)
    now = time.monotonic()
    with _rate_lock:
        events = _rate_events.setdefault(key_id, deque())
        while events and now - events[0] >= _RATE_WINDOW_SECONDS:
            events.popleft()
        if len(events) >= limit:
            retry_after = max(1, int(_RATE_WINDOW_SECONDS - (now - events[0])) + 1)
            raise HTTPException(
                status_code=429,
                detail="API rate limit exceeded. Retry shortly.",
                headers={"Retry-After": str(retry_after)},
            )
        events.append(now)
        if len(_rate_events) > 10_000:
            for stale in [k for k, v in _rate_events.items() if not v or now - v[-1] >= _RATE_WINDOW_SECONDS]:
                del _rate_events[stale]


def _api_key_context(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Fili API key required.")
    raw_key = authorization[7:].strip()
    if not raw_key.startswith("fili_live_") or len(raw_key) < 40:
        raise HTTPException(status_code=401, detail="Invalid Fili API key.")
    digest = _hash_api_key(raw_key)
    rows, _ = _supabase_request(
        "GET", "fili_api_keys",
        params={
            "select": "id,owner_uid,scopes,last_used_at",
            "key_hash": f"eq.{digest}",
            "revoked_at": "is.null",
            "limit": "1",
        },
    )
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid or revoked Fili API key.")
    key = rows[0]
    _enforce_rate_limit(str(key["id"]))
    key["key_prefix"] = raw_key[:17]
    return key


def require_api_scope(scope: str):
    def dependency(request: Request, authorization: str | None = Header(default=None)) -> dict[str, Any]:
        key = _api_key_context(authorization)
        # Recorded after the response by the usage middleware, with the real route and status.
        request.state.api_key = key
        if scope not in (key.get("scopes") or []):
            raise HTTPException(status_code=403, detail=f"API key requires the {scope} scope.")
        return key
    return dependency


def _record_usage(key: dict[str, Any], route: str, status_code: int) -> None:
    now = datetime.now(timezone.utc)
    try:
        _supabase_request("POST", "fili_api_usage", payload={
            "api_key_id": key["id"],
            "owner_uid": key["owner_uid"],
            "route": route[:120],
            "status_code": max(100, min(int(status_code), 599)),
        }, prefer="return=minimal")
        last_used = key.get("last_used_at")
        stale = True
        if last_used:
            try:
                parsed = datetime.fromisoformat(str(last_used).replace("Z", "+00:00"))
                stale = (now - parsed).total_seconds() >= LAST_USED_REFRESH_SECONDS
            except ValueError:
                stale = True
        if stale:
            _supabase_request("PATCH", "fili_api_keys", params={"id": f"eq.{key['id']}"}, payload={
                "last_used_at": now.isoformat(),
            }, prefer="return=minimal")
    except HTTPException:
        # Usage telemetry must not turn a valid API request into an outage.
        return


@app.middleware("http")
async def usage_logging(request: Request, call_next):
    response = await call_next(request)
    key = getattr(request.state, "api_key", None)
    if key:
        route = request.scope.get("route")
        template = getattr(route, "path", None) or request.url.path
        await asyncio.to_thread(_record_usage, key, f"{request.method} {template}", response.status_code)
    return response


def _derive_source_id(lead: dict[str, Any]) -> str:
    """Provider ID when present, otherwise an internal stable dedupe key (never shown as a provider ID)."""
    source_id = str(lead.get("source_id") or "")
    if source_id:
        return source_id
    identity = str(lead.get("source_url") or lead.get("website") or lead.get("company_name") or "")
    return "derived:" + hashlib.sha256(identity.casefold().encode("utf-8")).hexdigest()[:32]


def _save_prospects(owner_uid: str, leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for lead in leads:
        source_id = _derive_source_id(lead)
        records.append({
            "owner_uid": owner_uid,
            "source_type": str(lead.get("source_type") or "unknown"),
            "source_id": source_id,
            "company_name": str(lead.get("company_name") or "")[:240],
            "website": str(lead.get("website") or "")[:2048],
            "payload": {**lead, "internal_record_key": source_id},
        })
    if not records:
        return []
    saved, _ = _supabase_request(
        "POST", "fili_prospects", payload=records,
        params={"on_conflict": "owner_uid,source_type,source_id"},
        prefer="resolution=merge-duplicates,return=representation",
    )
    return saved or []


def _usage_events(owner_uid: str, days: int = 30) -> tuple[list[dict[str, Any]], bool]:
    """Fetch usage rows page by page (the REST API caps a single response), newest first."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    events: list[dict[str, Any]] = []
    for page in range(USAGE_MAX_PAGES):
        rows, _ = _supabase_request("GET", "fili_api_usage", params={
            "select": "id,route,status_code,created_at",
            "owner_uid": f"eq.{owner_uid}",
            "created_at": f"gte.{since}",
            "order": "created_at.desc,id.desc",
            "limit": str(USAGE_PAGE_SIZE),
            "offset": str(page * USAGE_PAGE_SIZE),
        })
        rows = rows or []
        events.extend(rows)
        if len(rows) < USAGE_PAGE_SIZE:
            return events, False
    return events, True


def _usage_summary(owner_uid: str) -> dict[str, Any]:
    events, truncated = _usage_events(owner_uid)
    codes = [int(event.get("status_code") or 0) for event in events]
    return {
        "period_days": 30,
        "requests": len(events),
        "successful": sum(1 for code in codes if code < 400),
        "failed": sum(1 for code in codes if code >= 400),
        "by_route": dict(sorted(Counter(str(event.get("route") or "unknown") for event in events).items())),
        "truncated": truncated,
    }


def _enforce_daily_search_quota(owner_uid: str) -> None:
    limit = _env_int("FILI_API_DAILY_SEARCH_LIMIT", DEFAULT_DAILY_SEARCH_LIMIT, 1, 1_000_000)
    midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows, _ = _supabase_request("GET", "fili_api_usage", params={
        "select": "id",
        "owner_uid": f"eq.{owner_uid}",
        "route": f"eq.{SEARCH_ROUTE}",
        "created_at": f"gte.{midnight.isoformat()}",
        "limit": str(limit),
    })
    if len(rows or []) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Daily search quota reached. It resets at 00:00 UTC.",
            headers={"Retry-After": str(int((midnight + timedelta(days=1) - datetime.now(timezone.utc)).total_seconds()) + 1)},
        )


@app.get(f"{API_PREFIX}/health", tags=["System"])
def health():
    return {
        "status": "ok",
        "service": "fili-api",
        "version": app.version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": {
            "supabase_configured": bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
            "firebase_configured": bool(os.getenv("FIREBASE_PROJECT_ID")),
        },
    }


@app.post(f"{API_PREFIX}/keys", tags=["API keys"], status_code=201)
def create_api_key(body: KeyCreateRequest, user: dict[str, Any] = Depends(current_firebase_user)):
    if not user.get("email_verified"):
        raise HTTPException(status_code=403, detail="Verify your email before creating API keys.")
    max_keys = _env_int("FILI_API_MAX_ACTIVE_KEYS", DEFAULT_MAX_ACTIVE_KEYS, 1, 1000)
    active, _ = _supabase_request("GET", "fili_api_keys", params={
        "select": "id", "owner_uid": f"eq.{user['uid']}", "revoked_at": "is.null", "limit": str(max_keys),
    })
    if len(active or []) >= max_keys:
        raise HTTPException(status_code=409, detail=f"Active key limit reached ({max_keys}). Revoke a key first.")
    raw_key = "fili_live_" + secrets.token_urlsafe(36)
    prefix = raw_key[:17]
    _supabase_request("POST", "fili_api_keys", payload={
        "owner_uid": user["uid"],
        "name": body.name.strip(),
        "key_prefix": prefix,
        "key_hash": _hash_api_key(raw_key),
        "scopes": sorted(set(body.scopes)),
    }, prefer="return=minimal")
    return {
        "key": raw_key,
        "prefix": prefix,
        "warning": "Copy this key now. It cannot be retrieved again.",
    }


@app.get(f"{API_PREFIX}/keys", tags=["API keys"])
def list_api_keys(user: dict[str, Any] = Depends(current_firebase_user)):
    rows, _ = _supabase_request("GET", "fili_api_keys", params={
        "select": "id,name,key_prefix,scopes,last_used_at,revoked_at,created_at",
        "owner_uid": f"eq.{user['uid']}",
        "order": "created_at.desc",
    })
    return {"data": rows or []}


@app.delete(f"{API_PREFIX}/keys/{{key_id}}", tags=["API keys"])
def revoke_api_key(key_id: UUID, user: dict[str, Any] = Depends(current_firebase_user)):
    rows, _ = _supabase_request("PATCH", "fili_api_keys", params={
        "id": f"eq.{key_id}", "owner_uid": f"eq.{user['uid']}", "revoked_at": "is.null", "select": "id",
    }, payload={"revoked_at": datetime.now(timezone.utc).isoformat()}, prefer="return=representation")
    if not rows:
        raise HTTPException(status_code=404, detail="Active API key not found.")
    # Make the revoked key unusable immediately on this instance.
    with _rate_lock:
        _rate_events.pop(str(key_id), None)
    return {"success": True}


@app.post(f"{API_PREFIX}/prospects/search", tags=["Prospecting"])
async def search_prospects(
    body: SearchRequest,
    key: dict[str, Any] = Depends(require_api_scope("prospects:write")),
):
    await asyncio.to_thread(_enforce_daily_search_quota, key["owner_uid"])

    provider_errors: list[dict[str, str]] = []
    tasks: list[tuple[str, Any]] = []
    if "apollo" in body.sources:
        if get_apollo_key():
            tasks.append(("apollo", fetch_apollo_leads(body.industry, body.location, body.limit)))
        else:
            provider_errors.append({"provider": "apollo", "error": "provider_not_configured"})
    serp_configured = bool(get_serpapi_key())
    for source, engine in (("google_maps", "google_maps"), ("web_search", "google")):
        if source in body.sources:
            if serp_configured:
                tasks.append((source, fetch_serpapi_leads(body.industry, body.location, body.limit, engine=engine)))
            else:
                provider_errors.append({"provider": source, "error": "provider_not_configured"})

    settled = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
    raw_results: list[dict[str, Any]] = []
    for (provider, _), outcome in zip(tasks, settled):
        if isinstance(outcome, ProviderRequestError):
            provider_errors.append({"provider": provider, "error": outcome.reason})
        elif isinstance(outcome, BaseException):
            provider_errors.append({"provider": provider, "error": "provider_unavailable"})
        else:
            raw_results.extend(outcome)

    normalized = [
        normalize_discovered_lead(
            lead, provider=str(lead.get("platform") or "provider"),
            target_industry=body.industry, location_scope=None,
        )
        for lead in raw_results
    ]
    results = deduplicate_leads(normalized)[:body.limit]

    saved = await asyncio.to_thread(_save_prospects, key["owner_uid"], results)
    by_identity = {
        str((item.get("payload") or {}).get("internal_record_key") or item.get("source_id") or "").casefold(): item
        for item in saved
    }
    data = []
    for lead in results:
        stored = by_identity.get(_derive_source_id(lead).casefold(), {})
        data.append({"id": stored.get("id"), **lead})
    return {
        "data": data,
        "meta": {
            "count": len(data),
            "requested": body.limit,
            "providers_queried": [name for name, _ in tasks],
            "provider_errors": provider_errors,
            "evidence_note": "Search snippets are discovery hints. Missing contact fields remain empty; no mailbox or phone verification is implied.",
        },
    }


@app.get(f"{API_PREFIX}/prospects/{{prospect_id}}", tags=["Prospecting"])
def get_prospect(
    prospect_id: UUID,
    key: dict[str, Any] = Depends(require_api_scope("prospects:read")),
):
    rows, _ = _supabase_request("GET", "fili_prospects", params={
        "select": "id,company_name,website,payload,created_at,updated_at",
        "id": f"eq.{prospect_id}",
        "owner_uid": f"eq.{key['owner_uid']}",
        "limit": "1",
    })
    if not rows:
        raise HTTPException(status_code=404, detail="Prospect not found.")
    return {"data": rows[0]}


@app.post(f"{API_PREFIX}/prospects/research", tags=["Prospecting"])
def research_prospect(
    prospect_id: UUID = Query(),
    key: dict[str, Any] = Depends(require_api_scope("prospects:read")),
):
    rows, _ = _supabase_request("GET", "fili_prospects", params={
        "select": "id,payload",
        "id": f"eq.{prospect_id}",
        "owner_uid": f"eq.{key['owner_uid']}",
        "limit": "1",
    })
    if not rows:
        raise HTTPException(status_code=404, detail="Prospect not found.")
    lead = rows[0].get("payload") or {}
    researched = enrich_lead(lead, verify_mx=False)
    researched["research_note"] = (
        "Best-effort public data enrichment only. MX/domain checks do not verify a mailbox; "
        "missing facts and contact details are not inferred."
    )
    return {"data": {"id": rows[0]["id"], **researched}}


@app.get(f"{API_PREFIX}/account/usage", tags=["API keys"])
def get_account_usage(user: dict[str, Any] = Depends(current_firebase_user)):
    """Usage overview for the signed-in dashboard owner; no API key secret required."""
    return _usage_summary(user["uid"])


@app.get(f"{API_PREFIX}/usage", tags=["Usage"])
def get_usage(key: dict[str, Any] = Depends(require_api_scope("usage:read"))):
    return _usage_summary(key["owner_uid"])


@app.exception_handler(HTTPException)
async def safe_http_error(_request: Request, exc: HTTPException):
    headers = {"Cache-Control": "no-store", **(exc.headers or {})}
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail}, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    message = f"Invalid request: {location or 'input'} — {first.get('msg', 'validation failed')}."
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"error": message},
                        headers={"Cache-Control": "no-store"})


@app.exception_handler(Exception)
async def unexpected_error(_request: Request, _exc: Exception):
    # Details are in the server log; never return tracebacks to API clients.
    return JSONResponse(status_code=500, content={"error": "Internal server error."},
                        headers={"Cache-Control": "no-store"})
