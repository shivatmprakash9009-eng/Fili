import { getFirebaseAuth } from "./firebase";
import type { ApiStatus, CampaignPayload, CampaignResponse, Lead } from "./types";

/** Firebase ID token for the signed-in user. The Next.js proxy verifies it server-side. */
async function authHeaders(): Promise<Record<string, string>> {
  const user = getFirebaseAuth().currentUser;
  if (!user) throw new Error("Your session has expired. Sign in again.");
  return { Authorization: "Bearer " + (await user.getIdToken()) };
}

async function readJson<T>(response: Response): Promise<T> {
  const payload = (await response.json().catch(() => ({}))) as T & { error?: string };
  if (!response.ok) {
    throw new Error(payload.error || `Request failed (${response.status})`);
  }
  return payload;
}

export async function getApiStatus(): Promise<ApiStatus> {
  const response = await fetch("/api/fili/status", {
    method: "GET",
    cache: "no-store",
    headers: { Accept: "application/json", ...(await authHeaders()) }
  });
  return readJson<ApiStatus>(response);
}

export async function runCampaign(payload: CampaignPayload): Promise<CampaignResponse> {
  const response = await fetch("/api/fili/run-campaign", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", ...(await authHeaders()) },
    body: JSON.stringify(payload)
  });
  return readJson<CampaignResponse>(response);
}

export async function scanWebsite(url: string): Promise<{ status: string; signals: string[]; note?: string }> {
  const response = await fetch("/api/fili/scan-tech", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", ...(await authHeaders()) },
    body: JSON.stringify({ url })
  });
  return readJson<{ status: string; signals: string[]; note?: string }>(response);
}

/** Downloads the current campaign export. A plain link cannot carry the auth header, so fetch a blob. */
export async function downloadExport(kind: "csv" | "xlsx"): Promise<void> {
  const response = await fetch(`/api/fili/export.${kind}`, {
    cache: "no-store",
    headers: await authHeaders()
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as { error?: string };
    throw new Error(payload.error || `Export failed (${response.status})`);
  }
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = `fili-crm-export.${kind}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 10_000);
}

export function isOutreachEligible(lead: Lead): boolean {
  return lead.outreach_enabled === true
    && !lead.is_synthetic
    && Boolean(lead.contact_email || lead.whatsapp_url);
}
