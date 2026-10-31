"use client";

import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, KeyRound, LoaderCircle, ShieldCheck, X } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import Dashboard from "./dashboard";

type GateState = "checking" | "open" | "locked" | "unconfigured";

export default function AuthGate() {
  const [state,setState]=useState<GateState>("checking");
  const [password,setPassword]=useState("");
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);

  useEffect(()=>{
    const timer=window.setTimeout(()=>{
      void fetch("/api/auth/session",{cache:"no-store"})
        .then(async(response)=>{
          const data=await response.json();
          if(response.status===503&&!data.configured){setState("unconfigured");return;}
          setState(data.authenticated?"open":"locked");
        })
        .catch(()=>setState("unconfigured"));
    },0);
    return ()=>window.clearTimeout(timer);
  },[]);

  useEffect(()=>{
    const logout=()=>{
      void fetch("/api/auth/logout",{method:"POST"}).finally(()=>{
        setPassword("");
        setError("");
        setState("locked");
      });
    };
    window.addEventListener("fili:logout",logout);
    return ()=>window.removeEventListener("fili:logout",logout);
  },[]);

  async function handleLogin(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    setBusy(true);setError("");
    try{
      const response=await fetch("/api/auth/login",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({password})
      });
      const data=await response.json();
      if(!response.ok)throw new Error(data.error||"Access denied.");
      setPassword("");
      setState("open");
    }catch(reason){
      setError(reason instanceof Error?reason.message:"Unable to unlock workspace.");
    }finally{setBusy(false);}
  }

  if(state==="checking"){
    return <div className="auth-loading"><span className="auth-loader"/><span>FILI / PRIVATE WORKSPACE</span></div>;
  }
  if(state==="open")return <Dashboard/>;

  return (
    <main className="auth-screen">
      <div className="auth-glow auth-glow-one"/><div className="auth-glow auth-glow-two"/>
      <motion.section className="auth-card" initial={{opacity:0,y:18}} animate={{opacity:1,y:0}} transition={{duration:.4}}>
        <div className="auth-mark"><KeyRound size={21}/></div>
        <span className="section-kicker">FILI / PRIVATE WORKSPACE</span>
        {state==="unconfigured"?(
          <>
            <h1>Workspace access<br/><em>is not configured.</em></h1>
            <p>Set the dashboard password and session secret in your server environment before exposing this workspace.</p>
            <div className="auth-config-list"><span>FILI_DASHBOARD_PASSWORD</span><span>FILI_SESSION_SECRET</span></div>
          </>
        ):(
          <>
            <h1>Your workspace.<br/><em>Your signals.</em></h1>
            <p>Enter the workspace password to continue.</p>
            <form className="auth-form" onSubmit={handleLogin}>
              <label htmlFor="workspace-password">Workspace password</label>
              <input id="workspace-password" type="password" autoComplete="current-password" value={password} onChange={(event)=>setPassword(event.target.value)} required autoFocus/>
              {error&&<span className="auth-error"><X size={14}/>{error}</span>}
              <button type="submit" className="button button-primary" disabled={busy||!password}>
                {busy?<><LoaderCircle className="spin" size={16}/> Unlocking</>:<>Unlock workspace <ArrowRight size={15}/></>}
              </button>
            </form>
          </>
        )}
        <div className="auth-footer"><ShieldCheck size={14}/> Encrypted session · 12-hour access</div>
      </motion.section>
    </main>
  );
}