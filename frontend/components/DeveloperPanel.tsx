"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { onAuthStateChanged, type User } from "firebase/auth";
import { Activity, AlertCircle, BookOpen, Check, Copy, KeyRound, LoaderCircle, Plus, RefreshCw, ShieldCheck, Trash2 } from "lucide-react";
import { getFirebaseAuth } from "@/lib/firebase";

type ApiKey = {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

type Usage = { period_days: number; requests: number; successful: number; failed: number; by_route: Record<string, number> };

const DEFAULT_SCOPES = ["prospects:read", "prospects:write", "usage:read"];

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch("/api/developer/" + path, {
    ...init,
    cache: "no-store",
    headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}), Authorization: "Bearer " + token, ...init.headers }
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || payload.detail || "Developer API request failed (" + response.status + ")");
  return payload as T;
}

function dateLabel(value: string | null) {
  return value ? new Date(value).toLocaleString() : "Never";
}

export default function DeveloperPanel() {
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [name, setName] = useState("Production integration");
  const [scopes, setScopes] = useState<string[]>(DEFAULT_SCOPES);
  const [newKey, setNewKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [copied, setCopied] = useState(false);

  const loadData = useCallback(async (activeUser: User) => {
    setLoading(true);
    setError("");
    try {
      const token = await activeUser.getIdToken();
      const [keyResult, usageResult] = await Promise.all([
        request<{ data: ApiKey[] }>("keys", token),
        request<Usage>("account/usage", token)
      ]);
      setKeys(keyResult.data || []);
      setUsage(usageResult);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load developer data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let unsubscribe = () => {};
    let cancelled = false;
    Promise.resolve().then(() => {
      if (cancelled) return;
      try {
        unsubscribe = onAuthStateChanged(getFirebaseAuth(), (nextUser) => {
          setUser(nextUser);
          setAuthReady(true);
          if (nextUser) void loadData(nextUser);
          else {
            setKeys([]);
            setUsage(null);
          }
        });
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Firebase authentication is unavailable.");
        setAuthReady(true);
      }
    });
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [loadData]);

  const activeKeys = useMemo(() => keys.filter((item) => !item.revoked_at), [keys]);

  async function createKey(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user || !name.trim() || !scopes.length) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const token = await user.getIdToken();
      const result = await request<{ key: string; prefix: string; warning: string }>("keys", token, {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), scopes })
      });
      setNewKey(result.key);
      setCopied(false);
      setNotice("API key created. Copy it now; the secret cannot be retrieved again.");
      await loadData(user);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "API key creation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function revokeKey(key: ApiKey) {
    if (!user || !window.confirm("Revoke “" + key.name + "”? Applications using this key will stop working.")) return;
    setError("");
    try {
      const token = await user.getIdToken();
      await request("keys/" + encodeURIComponent(key.id), token, { method: "DELETE" });
      setNotice("API key revoked.");
      await loadData(user);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not revoke this key.");
    }
  }

  async function copyKey() {
    if (!newKey) return;
    try {
      await navigator.clipboard.writeText(newKey);
      setCopied(true);
      setNotice("API key copied to clipboard.");
    } catch {
      setError("Clipboard access failed. Select and copy the key manually.");
    }
  }

  function toggleScope(scope: string) {
    setScopes((current) => current.includes(scope) ? current.filter((item) => item !== scope) : [...current, scope]);
  }

  return (
    <section className="surface-card developer-panel">
      <div className="developer-heading">
        <div className="developer-heading-icon"><KeyRound size={19}/></div>
        <div className="developer-heading-copy">
          <span className="section-kicker">DEVELOPER PLATFORM</span>
          <h3>API keys & usage</h3>
          <p>Manage secure keys for your Fili integrations.</p>
        </div>
        <a className="developer-docs-link" href="https://fili-api-p0uz.onrender.com/docs" target="_blank" rel="noreferrer"><BookOpen size={14}/> API docs</a>
      </div>

      {!authReady ? <div className="developer-state"><LoaderCircle className="spin" size={17}/> Checking your Fili session…</div> :
        !user ? <div className="developer-callout"><AlertCircle size={17}/><span>Sign in to Fili to create and manage API keys.</span></div> :
        <>
          <div className="developer-metrics">
            <div><span>Active keys</span><strong>{activeKeys.length}</strong></div>
            <div><span>Requests · 30 days</span><strong>{usage?.requests ?? (loading ? "…" : "—")}</strong></div>
            <div><span>Successful</span><strong>{usage?.successful ?? "—"}</strong></div>
            <div><span>Failed</span><strong>{usage?.failed ?? "—"}</strong></div>
          </div>

          <div className="developer-section-title"><div><h4>Create an API key</h4><p>Keys are shown once. Only a secure hash is stored by Fili.</p></div></div>
          <form className="developer-create-form" onSubmit={createKey}>
            <label className="developer-field"><span>Key name</span><input value={name} onChange={(event) => setName(event.target.value)} maxLength={80} minLength={2} required placeholder="e.g. Production integration"/></label>
            <div className="developer-field"><span>Permissions</span><div className="developer-scopes">
              {DEFAULT_SCOPES.map((scope) => <label key={scope}><input type="checkbox" checked={scopes.includes(scope)} onChange={() => toggleScope(scope)}/><span>{scope}</span></label>)}
            </div></div>
            <button className="button button-primary" type="submit" disabled={busy || loading || !name.trim() || !scopes.length}>
              {busy ? <LoaderCircle size={15} className="spin"/> : <Plus size={15}/>} Generate API key
            </button>
          </form>

          {newKey && <div className="developer-secret" role="status">
            <div><ShieldCheck size={17}/><strong>Copy your new API key now</strong></div>
            <p>This secret is displayed only once. Do not add it to public repositories or client-side source code.</p>
            <div className="developer-secret-value"><code>{newKey}</code><button type="button" className="button button-outline" onClick={copyKey}>{copied ? <Check size={14}/> : <Copy size={14}/>} {copied ? "Copied" : "Copy key"}</button></div>
          </div>}

          <div className="developer-section-title developer-list-title"><div><h4>Your API keys</h4><p>Revoked keys remain visible for audit history.</p></div><button type="button" className="developer-refresh" onClick={() => void loadData(user)} disabled={loading}><RefreshCw size={14} className={loading ? "spin" : ""}/> Refresh</button></div>
          {keys.length ? <div className="developer-key-list">{keys.map((key) => <article className="developer-key-row" key={key.id}>
            <div className="developer-key-main"><span className="developer-key-icon"><KeyRound size={16}/></span><div><strong>{key.name}</strong><code>{key.key_prefix}••••••••</code><small>Created {dateLabel(key.created_at)} · Last used {dateLabel(key.last_used_at)}</small><div className="developer-key-scopes">{key.scopes.map((scope) => <span key={scope}>{scope}</span>)}</div></div></div>
            <div className="developer-key-actions"><span className={key.revoked_at ? "developer-revoked" : "developer-active"}>{key.revoked_at ? "Revoked" : "Active"}</span>{!key.revoked_at && <button type="button" aria-label={"Revoke " + key.name} title="Revoke key" onClick={() => void revokeKey(key)}><Trash2 size={15}/></button>}</div>
          </article>)}</div> : <div className="developer-empty"><KeyRound size={20}/><strong>No API keys yet</strong><span>Create a key to connect an application to Fili.</span></div>}

          <div className="developer-limit-note"><Activity size={15}/><span>Default rate limit: 60 requests/minute per key. Usage covers the last 30 days. Limits are enforced by the API service.</span></div>
        </>}

      {error && <div className="developer-error" role="alert"><AlertCircle size={15}/>{error}</div>}
      {notice && <div className="developer-notice" role="status"><Check size={15}/>{notice}</div>}
    </section>
  );
}
