"""Fili v1 developer API.

Run with: uvicorn api_v1:app --host 0.0.0.0 --port 8080
Firebase ID tokens manage keys; fili_live_* API keys access prospect endpoints.
All persistent access is server-side through the Supabase service-role key.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Literal
from urllib.parse import quote

import firebase_admin
import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from firebase_admin import auth as firebase_auth, credentials
from pydantic import BaseModel, Field, field_validator

from utils.live_search import (
    ProviderRequestError,
    fetch_apollo_leads,
    fetch_duckduckgo_leads,
    fetch_serpapi_leads,
)
from utils.prospecting import enrich_lead

app = FastAPI(
    title="Fili API",
    version="1.0.0",
    description="Evidence-first B2B prospect discovery and research API.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

API_PREFIX = "/v1"
MAX_PAGE_SIZE = 100
DEFAULT_RATE_LIMIT = 60


class SearchRequest(BaseModel):
    industry: str = Field(min_length=2, max_length=120)
    location: str = Field(default="Global", max_length=120)
    sources: list[Literal["apollo", "google_maps", "web_search"]] = Field(
        default_factory=lambda: ["apollo", "google_maps", "web_search"], max_length=3
    )
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("industry", "location")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()


class KeyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    scopes: list[Literal["prospects:read", "prospects:write", "usage:read"]] = Field(
        default_factory=lambda: ["prospects:read", "prospects:write"]
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
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Firebase session is invalid or expired.") from exc
    if not claims.get("uid"):
        raise HTTPException(status_code=401, detail="Firebase identity is missing.")
    return claims


def current_firebase_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return _verify_firebase_token(authorization)


def _hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


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
            "select": "id,owner_uid,scopes",
            "key_hash": f"eq.{digest}",
            "revoked_at": "is.null",
            "limit": "1",
        },
    )
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid or revoked Fili API key.")
    key = rows[0]
    rate_limit = int(os.getenv("FILI_API_RATE_LIMIT_PER_MINUTE", str(DEFAULT_RATE_LIMIT)))
    since = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    recent, _ = _supabase_request("GET", "fili_api_usage", params={
        "select": "id",
        "api_key_id": f"eq.{key['id']}",
        "created_at": f"gte.{since}",
        "limit": str(rate_limit + 1),
    })
    if len(recent or []) >= rate_limit:
        raise HTTPException(status_code=429, detail="API rate limit exceeded. Retry in one minute.")
    key["key_prefix"] = raw_key[:17]
    return key


def require_api_scope(scope: str):
    def dependency(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        key = _api_key_context(authorization)
        if scope not in (key.get("scopes") or []):
            raise HTTPException(status_code=403, detail=f"API key requires the {scope} scope.")
        _record_usage(key, "authenticated", 200)
        return key
    return dependency


def _record_usage(key: dict[str, Any], route: str, status_code: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        _supabase_request("POST", "fili_api_usage", payload={
            "api_key_id": key["id"],
            "owner_uid": key["owner_uid"],
            "route": route[:120],
            "status_code": status_code,
        }, prefer="return=minimal")
        _supabase_request("PATCH", "fili_api_keys", params={"id": f"eq.{key['id']}"}, payload={
            "last_used_at": now,
        }, prefer="return=minimal")
    except HTTPException:
        # Usage telemetry must not turn a valid API request into an outage.
        return


def _save_prospects(owner_uid: str, leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for lead in leads:
        source_type = str(lead.get("source_type") or "unknown")
        source_id = str(lead.get("source_id") or "")
        if not source_id:
            # Internal stable dedupe key; this is not represented as a provider-supplied ID.
            identity = str(lead.get("source_url") or lead.get("website") or lead.get("company_name") or "")
            source_id = "derived:" + hashlib.sha256(identity.casefold().encode("utf-8")).hexdigest()[:32]
        records.append({
            "owner_uid": owner_uid,
            "source_type": source_type,
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
def revoke_api_key(key_id: str, user: dict[str, Any] = Depends(current_firebase_user)):
    _supabase_request("PATCH", "fili_api_keys", params={
        "id": f"eq.{key_id}", "owner_uid": f"eq.{user['uid']}", "revoked_at": "is.null",
    }, payload={"revoked_at": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")
    return {"success": True}


@app.post(f"{API_PREFIX}/prospects/search", tags=["Prospecting"])
async def search_prospects(
    body: SearchRequest,
    key: dict[str, Any] = Depends(require_api_scope("prospects:write")),
):
    results: list[dict[str, Any]] = []
    provider_errors: list[dict[str, str]] = []
    tasks = []
    if "apollo" in body.sources:
        tasks.append(("apollo", fetch_apollo_leads(body.industry, body.location, body.limit)))
    if "google_maps" in body.sources:
        tasks.append(("google_maps", fetch_serpapi_leads(body.industry, body.location, body.limit, engine="google_maps")))
    if "web_search" in body.sources:
        tasks.append(("web_search", fetch_serpapi_leads(body.industry, body.location, body.limit, engine="google")))
    import asyncio
    settled = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
    seen: set[str] = set()
    for (provider, _), outcome in zip(tasks, settled):
        if isinstance(outcome, Exception):
            reason = outcome.reason if isinstance(outcome, ProviderRequestError) else "provider_unavailable"
            provider_errors.append({"provider": provider, "error": reason})
            continue
        for lead in outcome:
            identity = str(lead.get("source_id") or lead.get("website") or lead.get("company_name") or "").casefold()
            if identity and identity not in seen:
                seen.add(identity)
                results.append(lead)
    results = results[:body.limit]
    saved = _save_prospects(key["owner_uid"], results)
    by_identity = {
        str((item.get("payload") or {}).get("internal_record_key") or item.get("source_id") or "").casefold(): item
        for item in saved
    }
    data = []
    for lead in results:
        source_id = str(lead.get("source_id") or "")
        if not source_id:
            identity_value = str(lead.get("source_url") or lead.get("website") or lead.get("company_name") or "")
            source_id = "derived:" + hashlib.sha256(identity_value.casefold().encode("utf-8")).hexdigest()[:32]
        stored = by_identity.get(source_id.casefold(), {})
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
    prospect_id: str,
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
    prospect_id: str = Query(min_length=8, max_length=64),
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


@app.get(f"{API_PREFIX}/usage", tags=["Usage"])
def get_usage(key: dict[str, Any] = Depends(require_api_scope("usage:read"))):
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    rows, _ = _supabase_request("GET", "fili_api_usage", params={
        "select": "id,route,status_code,created_at",
        "owner_uid": f"eq.{key['owner_uid']}",
        "created_at": f"gte.{since}",
        "order": "created_at.desc",
        "limit": "10000",
    })
    events = rows or []
    return {
        "period_days": 30,
        "requests": len(events),
        "successful": sum(1 for event in events if int(event.get("status_code") or 0) < 400),
        "failed": sum(1 for event in events if int(event.get("status_code") or 0) >= 400),
        "by_route": {
            route: sum(1 for event in events if event.get("route") == route)
            for route in sorted({event.get("route", "unknown") for event in events})
        },
    }


@app.exception_handler(HTTPException)
async def safe_http_error(_request: Request, exc: HTTPException):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
        headers={"Cache-Control": "no-store"},
    )
