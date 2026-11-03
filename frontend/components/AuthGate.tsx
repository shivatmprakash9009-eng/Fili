"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { onAuthStateChanged, reload, sendEmailVerification, signOut, type User } from "firebase/auth";
import { LoaderCircle, MailCheck } from "lucide-react";
import { getFirebaseAuth } from "@/lib/firebase";

type Session = { name: string; email: string; signOut: () => void };

/** Password accounts must verify their email; Google/GitHub identities are already verified by the provider. */
function needsEmailVerification(user: User): boolean {
  const usesPassword = user.providerData.some((info) => info.providerId === "password");
  return usesPassword && !user.emailVerified;
}

export default function AuthGate({ children }: { children: (session: Session) => React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let unsubscribe = () => {};
    let cancelled = false;
    // Deferred so state is only set from async callbacks, never synchronously in the effect body.
    Promise.resolve().then(() => {
      if (cancelled) return;
      try {
        unsubscribe = onAuthStateChanged(getFirebaseAuth(), (next) => {
          setUser(next);
          setReady(true);
          if (!next) router.replace("/login");
        });
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Authentication is unavailable.");
        setReady(true);
      }
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [router]);

  const logout = () => {
    void signOut(getFirebaseAuth()).finally(() => router.replace("/login"));
  };

  if (error) {
    return <main className="auth-gate"><div className="auth-gate-card" role="alert"><h1>Sign-in unavailable</h1><p>{error}</p></div></main>;
  }
  if (!ready || !user) {
    return <main className="auth-gate"><div className="auth-gate-card"><LoaderCircle className="spin" size={20}/><p>Checking your session…</p></div></main>;
  }
  if (needsEmailVerification(user)) {
    const resend = async () => {
      setBusy(true);
      setMessage("");
      try {
        await sendEmailVerification(user);
        setMessage("Verification email sent. Check your inbox.");
      } catch {
        setMessage("Could not send the email right now. Wait a minute and retry.");
      } finally {
        setBusy(false);
      }
    };
    const refresh = async () => {
      setBusy(true);
      try {
        await reload(user);
        setUser(getFirebaseAuth().currentUser);
        if (getFirebaseAuth().currentUser?.emailVerified) await getFirebaseAuth().currentUser?.getIdToken(true);
        else setMessage("Your email is not verified yet.");
      } finally {
        setBusy(false);
      }
    };
    return (
      <main className="auth-gate">
        <div className="auth-gate-card">
          <MailCheck size={22}/>
          <h1>Verify your email</h1>
          <p>We sent a verification link to <strong>{user.email}</strong>. Verify it to open your workspace.</p>
          {message && <p role="status">{message}</p>}
          <div className="auth-gate-actions">
            <button type="button" className="button button-primary" onClick={refresh} disabled={busy}>I have verified</button>
            <button type="button" className="button button-outline" onClick={resend} disabled={busy}>Resend email</button>
            <button type="button" className="button button-outline" onClick={logout}>Sign out</button>
          </div>
        </div>
      </main>
    );
  }
  return <>{children({ name: user.displayName || "", email: user.email || "", signOut: logout })}</>;
}
