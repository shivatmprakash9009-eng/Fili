import type { ApiStatus, CampaignPayload, CampaignResponse, Lead } from "./types";

async function readJson<T>(response: Response): Promise<T> {
  const payload = (await response.json().catch(() => ({}))) as T & { error?: string };
  if (!response.ok) {
    throw new Error(payload.error || \`Request failed (\${response.status})\`);
  }
  return payload;
}

export async function getApiStatus(): Promise<ApiStatus> {
  const response = await fetch("/api/fili/status", {
    method: "GET",
    cache: "no-store",
    headers: { Accept: "application/json" }
  });
  return readJson<ApiStatus>(response);
}

export async function runCampaign(payload: CampaignPayload): Promise<CampaignResponse> {
  const response = await fetch("/api/fili/run-campaign", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload)
  });
  return readJson<CampaignResponse>(response);
}

export async function scanWebsite(url: string): Promise<{ status: string; signals: string[]; note?: string }> {
  const response = await fetch("/api/fili/scan-tech", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ url })
  });
  return readJson<{ status: string; signals: string[]; note?: string }>(response);
}

export function exportUrl(kind: "csv" | "xlsx"): string {
  return \`/api/fili/export.\${kind}\`;
}

export function isOutreachEligible(lead: Lead): boolean {
  return lead.outreach_enabled !== false
    && !lead.is_synthetic
    && Boolean(lead.contact_email || lead.whatsapp_url);
}
