import { createHmac, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "fili_access";
export const SESSION_MAX_AGE = 60 * 60 * 12;

export function isSessionConfigured(): boolean {
  return Boolean(process.env.FILI_DASHBOARD_PASSWORD?.trim() && process.env.FILI_SESSION_SECRET?.trim());
}

export function isSessionValid(value?: string): boolean {
  if (process.env.NODE_ENV !== "production" && !isSessionConfigured()) return true;
  if (!value || !isSessionConfigured()) return false;

  const [timestampText, signature, extra] = value.split(".");
  if (!timestampText || !signature || extra !== undefined) return false;

  const timestamp = Number(timestampText);
  const now = Math.floor(Date.now() / 1000);
  if (!Number.isSafeInteger(timestamp) || timestamp > now + 60 || now - timestamp > SESSION_MAX_AGE) {
    return false;
  }

  const expected = createHmac("sha256", process.env.FILI_SESSION_SECRET as string)
    .update(timestampText)
    .digest();
  let supplied: Buffer;
  try {
    supplied = Buffer.from(signature, "base64url");
  } catch {
    return false;
  }
  return supplied.length === expected.length && timingSafeEqual(supplied, expected);
}

export function createSessionToken(now = Math.floor(Date.now() / 1000)): string {
  const timestamp = String(now);
  const signature = createHmac("sha256", process.env.FILI_SESSION_SECRET as string)
    .update(timestamp)
    .digest("base64url");
  return timestamp + "." + signature;
}

export function verifyDashboardPassword(candidate: string): boolean {
  const configured = process.env.FILI_DASHBOARD_PASSWORD || "";
  if (!configured || !candidate) return false;
  const supplied = Buffer.from(candidate);
  const expected = Buffer.from(configured);
  return supplied.length === expected.length && timingSafeEqual(supplied, expected);
}