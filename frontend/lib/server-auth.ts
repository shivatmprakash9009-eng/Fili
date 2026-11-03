import { createRemoteJWKSet, jwtVerify } from "jose";

/**
 * Server-side verification of Firebase ID tokens (no firebase-admin needed).
 * Checks the RS256 signature against Google's published securetoken keys, plus
 * issuer, audience and expiry. Runs only in Next.js route handlers.
 */
const JWKS = createRemoteJWKSet(
  new URL("https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"),
  { cooldownDuration: 30_000, cacheMaxAge: 3_600_000 }
);

export type VerifiedUser = { uid: string; email: string; emailVerified: boolean; provider: string };

export function firebaseProjectId(): string | null {
  const id = (process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID || process.env.FIREBASE_PROJECT_ID || "").trim();
  return id || null;
}

export async function verifyFirebaseToken(authorization: string | null): Promise<VerifiedUser | null> {
  const projectId = firebaseProjectId();
  if (!projectId || !authorization?.startsWith("Bearer ")) return null;
  const token = authorization.slice(7).trim();
  if (!token || token.length > 4096) return null;
  try {
    const { payload } = await jwtVerify(token, JWKS, {
      algorithms: ["RS256"],
      issuer: `https://securetoken.google.com/${projectId}`,
      audience: projectId
    });
    const uid = typeof payload.sub === "string" ? payload.sub : "";
    // Firebase UIDs are 1-128 chars; reject anything that could not be a safe header/DB key.
    if (!/^[A-Za-z0-9_-]{1,128}$/.test(uid)) return null;
    const firebase = (payload.firebase ?? {}) as { sign_in_provider?: string };
    return {
      uid,
      email: typeof payload.email === "string" ? payload.email : "",
      emailVerified: payload.email_verified === true,
      provider: firebase.sign_in_provider || ""
    };
  } catch {
    return null;
  }
}

/** Password accounts must verify their email; Google/GitHub sign-ins are verified by the provider. */
export function isAccountAllowed(user: VerifiedUser): boolean {
  return user.provider !== "password" || user.emailVerified;
}
