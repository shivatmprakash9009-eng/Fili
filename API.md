# Fili Developer API v1

The developer API is a separate Python service. It does not replace the existing dashboard API.

## Run locally

Python 3.11+:

```bash
pip install -r requirements.txt
pip install -r api-requirements.txt
uvicorn api_v1:app --host 127.0.0.1 --port 8080
```

Interactive OpenAPI docs: `/docs`. Health: `GET /v1/health`.

## Server environment

Set these only on the API host:

- `FIREBASE_PROJECT_ID=fili-26b9d`
- `FIREBASE_SERVICE_ACCOUNT_JSON`: full Firebase Admin service-account JSON, stored as a server secret (or use managed Google Application Default Credentials).
- `SUPABASE_URL=https://aynlbiuakpaxtmrgaxeh.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase service-role/secret key. Server-side only; never put it in Vercel `NEXT_PUBLIC_*` variables or browser code.
- `APOLLO_API_KEY` and/or `SERPAPI_API_KEY` for live provider search. A source whose key is missing is reported in `meta.provider_errors` as `provider_not_configured`.
- Optional limits: `FILI_API_RATE_LIMIT_PER_MINUTE` (60), `FILI_API_MAX_ACTIVE_KEYS` (10 per user), `FILI_API_DAILY_SEARCH_LIMIT` (200 searches per user per UTC day).

Apply both migrations in order to the Fili Supabase project before using key or prospect endpoints: `202611020001_fili_public_api.sql`, then `202611030001_fili_api_hardening.sql` (keeps `updated_at` accurate and adds the quota index). The API uses only the dedicated `fili_*` tables; it does not touch TIWAT tables.

## Authentication

- Key management endpoints require a Firebase ID token in `Authorization: Bearer <firebase-id-token>`.
- Prospect and usage endpoints require a generated `fili_live_*` key.
- API keys are displayed only once. The database stores a SHA-256 hash, never the raw key.
- Revoke keys immediately if exposed. Scope checks are enforced per endpoint.
- Keys belong to the Firebase UID that created them; prospect reads are always owner-scoped.

## Endpoints

| Method | Endpoint | Authentication | Purpose |
|---|---|---|---|
| GET | `/v1/health` | Public | API health/config status |
| POST | `/v1/keys` | Firebase ID token | Create API key (verified email required) |
| GET | `/v1/keys` | Firebase ID token | List own keys (secret omitted) |
| DELETE | `/v1/keys/{key_id}` | Firebase ID token | Revoke own key |
| POST | `/v1/prospects/search` | API key: `prospects:write` | Search Apollo, Google Maps and web search |
| GET | `/v1/prospects/{id}` | API key: `prospects:read` | Read an owned prospect |
| POST | `/v1/prospects/research?prospect_id=...` | API key: `prospects:read` | Return bounded evidence-aware enrichment |
| GET | `/v1/usage` | API key: `usage:read` | Last 30 days of API usage for this key owner |
| GET | `/v1/account/usage` | Firebase ID token | Last 30 days of usage for the signed-in dashboard owner |

Search body:

```json
{
  "industry": "SaaS companies",
  "location": "India",
  "sources": ["apollo", "google_maps", "web_search"],
  "limit": 10
}
```

Provider credentials and rate limits are controlled by their respective accounts. Missing contacts remain empty; search snippets are not verification. The API does not send outreach.

## Deployment

Deploy `api_v1.py` as a separate Python web service (for example, a Render Web Service) with start command:

```bash
uvicorn api_v1:app --host 0.0.0.0 --port $PORT
```

Use Python runtime 3.11+. Add both `requirements.txt` and `api-requirements.txt` during build:

```bash
pip install -r requirements.txt -r api-requirements.txt
```

Configure secrets in the API host dashboard. Do not deploy Firebase service-account JSON or Supabase service-role credentials to the Next.js frontend. Restrict API ingress with TLS and provider-level rate limiting before exposing it to third parties.

## Limits and errors

- Requests per key per minute are limited in memory on the API instance (exact for one instance; use a shared counter such as Redis before scaling out). `429` responses carry `Retry-After`.
- Search calls are capped per user per UTC day. `404` is returned for unknown prospects or keys, `422` for malformed IDs or bodies, and `409` when the active-key cap is reached.
- Usage records the real route (for example `GET /v1/prospects/{prospect_id}`) and the real HTTP status, so `failed` and `by_route` are accurate. Usage totals page through all rows; `truncated: true` means the 20,000-row reporting cap was hit.

## Current boundary

This is the first developer API slice: key lifecycle, discovery, owned-prospect reads, research response and usage reporting. It does not yet provide durable asynchronous jobs, a distributed quota/rate-limit counter, billing, contact enrichment beyond current licensed connectors, or automated outreach.
