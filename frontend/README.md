# Fili Dashboard

The Next.js frontend lives in this directory. It uses the App Router, React, TypeScript, Motion for React and Lucide icons.

## Local development

Requirements: Node.js 22+ and Python 3.11+.

1. Start the Python prospecting API from the repository root:

       python dashboard.py --port 8000

   For a local-only setup, the Python server defaults to 127.0.0.1 and does not require an API token.

2. Install and start the Next.js app:

       cd frontend
       npm install
       cp .env.example .env.local
       npm run dev

3. Open http://localhost:3000.

Set FILI_API_BASE_URL=http://127.0.0.1:8000 in frontend/.env.local to connect the UI to the local Python API. The proxy is server-side; do not rename this variable with a NEXT_PUBLIC_ prefix.

## Vercel deployment

Create or configure the Vercel project with Root Directory = frontend, Framework Preset = Next.js, and Node.js 22.

Configure these server-side environment variables:

- FILI_API_BASE_URL: HTTPS URL of the deployed Python API.
- FILI_API_TOKEN: a high-entropy shared secret. Set the same value in the Python API environment.

Run the Python service with a reachable HTTPS endpoint and:

    FILI_API_TOKEN=<same-secret>
    python dashboard.py --host 0.0.0.0 --port 8000

The Python API rejects protected API requests without the bearer token when the token is configured. Its host must be private-network reachable only through your trusted ingress or firewall; the shared token is an additional control, not a replacement for network restrictions.

## Current architecture boundary

The UI is wired to the existing Python API for campaign discovery, status, website scanning and CSV/XLSX exports. It does not fabricate prospect metrics; before the first campaign it shows an empty state.

The password gate is single-workspace access protection, not a multi-user identity provider. It has no account recovery or organisation membership. Add edge/WAF rate limiting to the login route before wide public access.

This is a SaaS dashboard foundation, not a complete multi-tenant SaaS release. The current Python engine keeps the latest campaign in process memory and its daily scheduler is in-process. User accounts, organisation membership, row-level tenant isolation, persistent campaign/lead storage, billing, audit events and a durable multi-instance job queue still need to be implemented before accepting external customers or storing their data. Do not expose the current Python service publicly without private ingress controls.
