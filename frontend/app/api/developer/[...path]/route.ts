import { NextRequest, NextResponse } from "next/server";

const API_ORIGIN = "https://fili-api-p0uz.onrender.com";

async function proxyDeveloperRequest(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const endpoint = path.join("/");
  if (!(endpoint === "keys" || endpoint === "account/usage" || /^keys\/[A-Za-z0-9_-]+$/.test(endpoint))) {
    return NextResponse.json({ error: "Unknown developer API route." }, { status: 404 });
  }

  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ")) {
    return NextResponse.json({ error: "Sign in to Fili before using developer tools." }, { status: 401 });
  }

  const url = new URL("/v1/" + endpoint, API_ORIGIN);
  const headers = new Headers({ Accept: "application/json", Authorization: authorization });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);

  try {
    const response = await fetch(url, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.text(),
      cache: "no-store",
      signal: AbortSignal.timeout(20000)
    });
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("content-type") || "application/json", "Cache-Control": "no-store" }
    });
  } catch {
    return NextResponse.json({ error: "Fili Developer API is temporarily unavailable. Retry in a moment." }, { status: 502 });
  }
}

export const GET = proxyDeveloperRequest;
export const POST = proxyDeveloperRequest;
export const DELETE = proxyDeveloperRequest;
