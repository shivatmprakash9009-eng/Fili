import { NextRequest, NextResponse } from "next/server";
import { isSessionConfigured, isSessionValid, SESSION_COOKIE } from "@/lib/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 120;

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

const GET_ROUTES = new Set(["status", "export.csv", "export.xlsx"]);
const POST_ROUTES = new Set(["run-campaign", "analyze-reply", "scan-tech"]);
const BODY_LIMIT = 1_000_000;

function backendUrl(): URL | null {
  const configured = process.env.FILI_API_BASE_URL?.trim();
  if (!configured) return null;

  try {
    const url = new URL(configured);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
      return null;
    }
    url.pathname = url.pathname.replace(/\/+$/, "") + "/";
    url.search = "";
    url.hash = "";
    return url;
  } catch {
    return null;
  }
}

async function handle(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const key = path.join("/");
  const method = request.method.toUpperCase();

  if ((method === "GET" && !GET_ROUTES.has(key)) || (method === "POST" && !POST_ROUTES.has(key))) {
    return NextResponse.json({ error: "Route not found." }, { status: 404 });
  }

  const base = backendUrl();
  const apiToken = process.env.FILI_API_TOKEN?.trim();
  if (process.env.NODE_ENV === "production" && !isSessionConfigured()) {
    return NextResponse.json(
      { error: "Workspace access is not configured. Set FILI_DASHBOARD_PASSWORD and FILI_SESSION_SECRET." },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    );
  }
  if (isSessionConfigured() && !isSessionValid(request.cookies.get(SESSION_COOKIE)?.value)) {
    return NextResponse.json(
      { error: "Workspace session expired. Unlock Fili to continue." },
      { status: 401, headers: { "Cache-Control": "no-store" } }
    );
  }
  if (process.env.NODE_ENV === "production" && !apiToken) {
    return NextResponse.json(
      { error: "FILI_API_TOKEN is required for production API access." },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    );
  }
  if (!base) {
    return NextResponse.json(
      { error: "Fili API is not connected. Configure FILI_API_BASE_URL on the server." },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    );
  }

  let body: string | undefined;
  if (method === "POST") {
    const length = Number(request.headers.get("content-length") || 0);
    if (length > BODY_LIMIT) {
      return NextResponse.json({ error: "Request body exceeds the 1 MB limit." }, { status: 413 });
    }
    body = await request.text();
    if (new TextEncoder().encode(body).byteLength > BODY_LIMIT) {
      return NextResponse.json({ error: "Request body exceeds the 1 MB limit." }, { status: 413 });
    }
    try {
      const parsed: unknown = JSON.parse(body || "{}");
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        return NextResponse.json({ error: "Request body must be a JSON object." }, { status: 400 });
      }
    } catch {
      return NextResponse.json({ error: "Invalid JSON request." }, { status: 400 });
    }
  }

  const target = new URL(key, base);
  const timeout = key === "run-campaign" ? 110_000 : 18_000;

  try {
    const upstream = await fetch(target, {
      method,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(timeout),
      headers: {
        Accept: request.headers.get("accept") || "application/json",
        ...(apiToken ? { Authorization: "Bearer " + apiToken } : {}),
        ...(body ? { "Content-Type": "application/json" } : {})
      },
      ...(body ? { body } : {})
    });

    const contentType = upstream.headers.get("content-type") || "application/octet-stream";
    const headers = new Headers({
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Content-Type": contentType
    });

    const disposition = upstream.headers.get("content-disposition");
    if (disposition && (key === "export.csv" || key === "export.xlsx")) {
      headers.set("Content-Disposition", disposition);
    }

    if (key === "export.csv" || key === "export.xlsx") {
      const bytes = await upstream.arrayBuffer();
      return new NextResponse(bytes, { status: upstream.status, headers });
    }

    const text = await upstream.text();
    return new NextResponse(text, { status: upstream.status, headers });
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "TimeoutError";
    return NextResponse.json(
      { error: timedOut ? "Fili API timed out. Retry the request." : "Fili API is unreachable." },
      { status: timedOut ? 504 : 502, headers: { "Cache-Control": "no-store" } }
    );
  }
}

export const GET = handle;
export const POST = handle;
