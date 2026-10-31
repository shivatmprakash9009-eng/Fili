import { NextRequest, NextResponse } from "next/server";
import {
  createSessionToken,
  isSessionConfigured,
  isSessionValid,
  SESSION_COOKIE,
  SESSION_MAX_AGE,
  verifyDashboardPassword
} from "@/lib/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ action: string }> };

function configMissing() {
  return process.env.NODE_ENV === "production" && !isSessionConfigured();
}

export async function GET(request: NextRequest, context: Context) {
  const { action } = await context.params;
  if (action !== "session") return NextResponse.json({ error: "Route not found." }, { status: 404 });
  if (configMissing()) {
    return NextResponse.json(
      { authenticated: false, configured: false, error: "Set FILI_DASHBOARD_PASSWORD and FILI_SESSION_SECRET." },
      { status: 503, headers: { "Cache-Control": "no-store" } }
    );
  }
  const authenticated = isSessionValid(request.cookies.get(SESSION_COOKIE)?.value);
  return NextResponse.json(
    { authenticated, configured: isSessionConfigured() },
    { headers: { "Cache-Control": "no-store" } }
  );
}

export async function POST(request: NextRequest, context: Context) {
  const { action } = await context.params;
  if (action === "logout") {
    const response = NextResponse.json({ success: true }, { headers: { "Cache-Control": "no-store" } });
    response.cookies.set(SESSION_COOKIE, "", {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "lax",
      path: "/",
      maxAge: 0
    });
    return response;
  }
  if (action !== "login") return NextResponse.json({ error: "Route not found." }, { status: 404 });
  if (!isSessionConfigured()) {
    return NextResponse.json({ error: "Workspace access is not configured." }, { status: 503 });
  }

  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) {
    return NextResponse.json({ error: "Invalid request origin." }, { status: 403 });
  }

  const length = Number(request.headers.get("content-length") || 0);
  if (length > 4096) return NextResponse.json({ error: "Request is too large." }, { status: 413 });

  let password = "";
  try {
    const body: unknown = await request.json();
    if (!body || typeof body !== "object" || !("password" in body) || typeof body.password !== "string") {
      return NextResponse.json({ error: "Enter the workspace password." }, { status: 400 });
    }
    password = body.password;
  } catch {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }

  if (password.length > 256 || !verifyDashboardPassword(password)) {
    return NextResponse.json({ error: "Incorrect workspace password." }, { status: 401 });
  }

  const response = NextResponse.json({ success: true }, { headers: { "Cache-Control": "no-store" } });
  response.cookies.set(SESSION_COOKIE, createSessionToken(), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE
  });
  return response;
}