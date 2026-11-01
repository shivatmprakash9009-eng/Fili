"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowLeft, ArrowRight, Eye, EyeOff, LoaderCircle,
  LockKeyhole, Mail, ShieldCheck, Sparkles, CheckCircle2
} from "lucide-react";
import {
  createUserWithEmailAndPassword, GithubAuthProvider, GoogleAuthProvider,
  sendEmailVerification, sendPasswordResetEmail, signInWithEmailAndPassword,
  signInWithPopup, updateProfile
} from "firebase/auth";
import { getFirebaseAuth } from "../lib/firebase";
import "./AuthScreen.css";

type Mode = "login" | "signup" | "forgot";

function GitHubMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
      <path d="M12 .9a11.1 11.1 0 0 0-3.51 21.63c.56.1.76-.24.76-.54v-2.08c-3.1.67-3.76-1.32-3.76-1.32-.5-1.28-1.23-1.62-1.23-1.62-1.01-.69.08-.68.08-.68 1.12.08 1.71 1.15 1.71 1.15 1 .1.76 2.03 3.2 1.55.1-.72.4-1.2.72-1.48-2.48-.28-5.09-1.24-5.09-5.52 0-1.22.44-2.22 1.15-3-.12-.28-.5-1.42.11-2.96 0 0 .94-.3 3.05 1.15a10.6 10.6 0 0 1 5.55 0c2.12-1.44 3.05-1.15 3.05-1.15.61 1.54.23 2.68.11 2.96.72.78 1.15 1.78 1.15 3 0 4.29-2.61 5.24-5.1 5.51.4.35.76 1.03.76 2.08v3.1c0 .3.2.65.77.54A11.1 11.1 0 0 0 12 .9Z" />
    </svg>
  );
}

const friendlyError = (code: string) => {
  const errors: Record<string, string> = {
    "auth/invalid-credential": "Email or password is incorrect.",
    "auth/user-not-found": "No account exists with this email.",
    "auth/wrong-password": "Email or password is incorrect.",
    "auth/email-already-in-use": "An account with this email already exists.",
    "auth/weak-password": "Use a stronger password with at least 8 characters.",
    "auth/invalid-email": "Enter a valid email address.",
    "auth/popup-closed-by-user": "The sign-in window was closed before completing.",
    "auth/account-exists-with-different-credential": "An account already exists with another sign-in method.",
    "auth/too-many-requests": "Too many attempts. Wait a moment and try again.",
    "auth/unauthorized-domain": "This domain is not authorized in Firebase Authentication.",
    "auth/network-request-failed": "Network error. Check your connection and retry."
  };
  return errors[code] || "Something went wrong. Please try again.";
};

export default function AuthScreen({ mode }: { mode: Mode }) {
  const router = useRouter();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const title = mode === "signup" ? "Create your account" : mode === "forgot" ? "Reset your password" : "Welcome back";
  const subtitle = mode === "signup"
    ? "Start building a clearer, more intentional prospecting workflow."
    : mode === "forgot"
      ? "We’ll send a secure reset link to your inbox."
      : "Sign in to continue to your Fili workspace.";

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const auth = getFirebaseAuth();
      if (mode === "forgot") {
        await sendPasswordResetEmail(auth, email.trim());
        setNotice("Password reset link sent. Check your inbox.");
      } else if (mode === "signup") {
        if (!firstName.trim() || !lastName.trim()) throw new Error("Enter your first and last name.");
        if (password.length < 8) throw new Error("Use a password with at least 8 characters.");
        if (password !== confirmPassword) throw new Error("Passwords do not match.");
        const credential = await createUserWithEmailAndPassword(auth, email.trim(), password);
        await updateProfile(credential.user, { displayName: `${firstName.trim()} ${lastName.trim()}` });
        await sendEmailVerification(credential.user);
        setNotice("Account created. Verify your email to complete setup. You can sign in after verification.");
      } else {
        await signInWithEmailAndPassword(auth, email.trim(), password);
        router.push("/dashboard");
      }
    } catch (err) {
      const value = err as Error & { code?: string };
      setError(value.code ? friendlyError(value.code) : value.message || "Unable to complete this request.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSocial(providerName: "google" | "github") {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const auth = getFirebaseAuth();
      const provider = providerName === "google" ? new GoogleAuthProvider() : new GithubAuthProvider();
      if (providerName === "github") provider.addScope("read:user");
      await signInWithPopup(auth, provider);
      router.push("/dashboard");
    } catch (err) {
      const value = err as Error & { code?: string };
      setError(value.code ? friendlyError(value.code) : value.message || "Social sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-story">
        <Link href="/" className="auth-logo"><span className="auth-logo-mark">f</span><span>fili</span><small>PROSPECTING OS</small></Link>
        <div className="auth-story-content">
          <div className="auth-overline"><span/> THE CLEARER WAY TO GROW</div>
          <h1>Find the right<br/><em>signal.</em> Make it<br/>count.</h1>
          <p>One focused workspace for discovering businesses, understanding context and making better prospecting decisions.</p>
          <div className="auth-story-proof"><span><ShieldCheck size={16}/></span><div><strong>Evidence-led by design</strong><small>Source-aware. Transparent. Built for trust.</small></div></div>
        </div>
        <div className="auth-story-footer"><span>© {new Date().getFullYear()} Fili</span><span>Prospecting, with purpose.</span></div>
        <div className="auth-orbit auth-orbit-one"/><div className="auth-orbit auth-orbit-two"/>
      </section>

      <section className="auth-panel">
        <div className="auth-panel-top"><Link href="/" className="auth-back"><ArrowLeft size={15}/> Back to Fili</Link><span className="auth-secure"><LockKeyhole size={12}/> SECURE ACCESS</span></div>
        <div className="auth-form-wrap">
          <div className="auth-mobile-brand"><span className="auth-logo-mark">f</span> fili</div>
          <div className="auth-form-heading"><div className="auth-icon"><Sparkles size={18}/></div><div className="auth-eyebrow">{mode === "signup" ? "GET STARTED" : mode === "forgot" ? "ACCOUNT RECOVERY" : "YOUR WORKSPACE"}</div><h2>{title}</h2><p>{subtitle}</p></div>

          {mode !== "forgot" && <div className="auth-socials">
            <button type="button" onClick={() => handleSocial("google")} disabled={busy}><span className="google-g">G</span> Continue with Google</button>
            <button type="button" onClick={() => handleSocial("github")} disabled={busy}><GitHubMark/> GitHub</button>
          </div>}
          {mode !== "forgot" && <div className="auth-divider"><span/> <small>OR CONTINUE WITH EMAIL</small> <span/></div>}

          <form className="auth-form" onSubmit={handleSubmit}>
            {mode === "signup" && <div className="auth-name-row">
              <label>First name<input autoComplete="given-name" value={firstName} onChange={e=>setFirstName(e.target.value)} placeholder="First name" required/></label>
              <label>Last name<input autoComplete="family-name" value={lastName} onChange={e=>setLastName(e.target.value)} placeholder="Last name" required/></label>
            </div>}
            <label>Email address<span className="auth-input-wrap"><Mail size={16}/><input type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="you@company.com" required/></span></label>
            {mode !== "forgot" && <label>Password<span className="auth-input-wrap"><LockKeyhole size={16}/><input type={showPassword ? "text" : "password"} autoComplete={mode === "signup" ? "new-password" : "current-password"} value={password} onChange={e=>setPassword(e.target.value)} placeholder="At least 8 characters" minLength={8} required/><button type="button" className="auth-eye" onClick={()=>setShowPassword(!showPassword)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff size={16}/> : <Eye size={16}/>}</button></span></label>}
            {mode === "signup" && <label>Confirm password<span className="auth-input-wrap"><LockKeyhole size={16}/><input type={showPassword ? "text" : "password"} autoComplete="new-password" value={confirmPassword} onChange={e=>setConfirmPassword(e.target.value)} placeholder="Re-enter your password" minLength={8} required/></span></label>}
            {mode === "login" && <div className="auth-forgot-row"><span>Protected access</span><Link href="/forgot-password">Forgot password?</Link></div>}
            {error && <div className="auth-message auth-error" role="alert">{error}</div>}
            {notice && <div className="auth-message auth-success" role="status"><CheckCircle2 size={15}/>{notice}</div>}
            <button className="auth-submit" type="submit" disabled={busy}>{busy ? <LoaderCircle className="auth-spinner" size={17}/> : null}{mode === "signup" ? "Create account" : mode === "forgot" ? "Send reset link" : "Sign in"}{!busy && <ArrowRight size={16}/>}</button>
          </form>

          {mode === "login" && <p className="auth-switch">New to Fili? <Link href="/signup">Create an account <ArrowRight size={13}/></Link></p>}
          {mode === "signup" && <p className="auth-switch">Already have an account? <Link href="/login">Sign in <ArrowRight size={13}/></Link></p>}
          {mode === "forgot" && <p className="auth-switch"><Link href="/login"><ArrowLeft size={13}/> Back to sign in</Link></p>}
          <div className="auth-legal">By continuing, you agree to Fili’s Terms and Privacy Policy.</div>
        </div>
        <div className="auth-panel-bottom"><span>FILI / AUTHENTICATION</span><span>ENCRYPTED CONNECTION <i/></span></div>
      </section>
    </main>
  );
}
