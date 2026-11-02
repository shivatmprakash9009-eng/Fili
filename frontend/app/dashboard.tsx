"use client";

import Image from "next/image";
import LocationSelector from "@/components/LocationSelector";
import DeveloperPanel from "@/components/DeveloperPanel";
import {
  Activity, ArrowRight, ArrowUpRight, Bell, CalendarDays, Check,
  ChevronDown, ChevronRight, CircleAlert, Command, Download, ExternalLink,
  Globe, LayoutDashboard, LoaderCircle, Mail, Menu, MoreHorizontal,
  Plus, Rocket, Search, Settings2, ShieldCheck, Sparkles, Users, Workflow, X, Zap
} from "lucide-react";
import {
  AnimatePresence, motion, useReducedMotion
} from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { exportUrl, getApiStatus, isOutreachEligible, runCampaign, scanWebsite } from "@/lib/api";
import type {
  ApiState, ApiStatus, CampaignPayload, CampaignResponse, Lead, NavItem
} from "@/lib/types";

const NAV_ITEMS: { id: NavItem; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "prospects", label: "Prospects", icon: Users },
  { id: "campaigns", label: "Campaigns", icon: Workflow },
  { id: "settings", label: "Settings", icon: Settings2 }
];

const PLATFORM_OPTIONS = [
  { value: "web_search", label: "Web discovery", disabled: true },
  { value: "apollo", label: "Apollo.io" },
  { value: "google_maps", label: "Google Maps" },
  { value: "indiamart", label: "IndiaMART", disabled: true },
  { value: "linkedin", label: "LinkedIn", disabled: true }
] as const;

const PAGE_TITLES: Record<NavItem, string> = {
  overview: "Overview",
  prospects: "Prospects",
  campaigns: "Campaigns",
  settings: "Workspace settings"
};

function Brand() {
  return (
    <div className="brand-lockup">
      <Image src="/fili-mark.svg" alt="Fili" width={38} height={38} priority />
      <div className="brand-wordmark">
        <span>fili</span>
        <span className="brand-caption">PROSPECTING OS</span>
      </div>
    </div>
  );
}

function StatusPill({ state }: { state: ApiState }) {
  const label = state === "connected" ? "Engine connected" : state === "checking" ? "Connecting" : "Engine offline";
  return (
    <span className={"status-pill status-" + state}>
      <span className="status-dot" />
      {label}
    </span>
  );
}

function EmptyLeads({ onLaunch }: { onLaunch: () => void }) {
  return (
    <div className="empty-state">
      <div className="empty-illustration">
        <div className="empty-ring ring-a" />
        <div className="empty-ring ring-b" />
        <div className="empty-icon"><Users size={23} strokeWidth={1.7} /></div>
        <span className="empty-spark spark-a"><Sparkles size={13} /></span>
        <span className="empty-spark spark-b"><Zap size={12} /></span>
      </div>
      <h3>No prospects in this session</h3>
      <p>Launch a search to bring your first prospects into Fili.</p>
      <button type="button" className="button button-primary button-small" onClick={onLaunch}>
        <Plus size={15} /> Start prospecting
      </button>
    </div>
  );
}

function WorkflowCard({ apiState, leadsCount, schedule }: {
  apiState: ApiState;
  leadsCount: number;
  schedule: ApiStatus | null;
}) {
  const ready = apiState === "connected";
  const steps = [
    { title: "Discover", subtitle: ready ? "Search connectors" : "Connect your API", icon: Globe, done: leadsCount > 0 },
    { title: "Enrich", subtitle: "MX, phone & tech signals", icon: Sparkles, done: leadsCount > 0 },
    { title: "Activate", subtitle: "Review-ready drafts", icon: Mail, done: leadsCount > 0 }
  ];
  return (
    <section className="surface-card workflow-card">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">THE SYSTEM</span>
          <h3>One clear workflow</h3>
        </div>
        <span className="icon-badge"><Workflow size={17} /></span>
      </div>
      <div className="workflow-steps">
        {steps.map((step,index)=>{
          const Icon=step.icon;
          return (
            <div className="workflow-step" key={step.title}>
              <div className={"workflow-icon " + (step.done ? "workflow-done" : ready ? "workflow-ready" : "")}>
                {step.done ? <Check size={17}/> : <Icon size={17}/>}
              </div>
              <div className="workflow-copy">
                <strong>{step.title}</strong>
                <span>{step.subtitle}</span>
              </div>
              <span className="workflow-step-state">{step.done ? "Ready" : ready ? "Idle" : "Offline"}</span>
              {index !== steps.length-1 && <div className="workflow-connector"/>}
            </div>
          );
        })}
      </div>
      <div className="workflow-footer">
        <div className="workflow-foot-icon"><CalendarDays size={15}/></div>
        <div>
          <strong>{schedule?.daily_schedule_enabled ? "Daily prospecting active" : "Daily prospecting is optional"}</strong>
          <span>{schedule?.daily_schedule_enabled
            ? "Next run " + (schedule.next_run ? new Date(schedule.next_run).toLocaleString() : schedule.daily_schedule_time || "09:00")
            : "Enable the 09:00 schedule in your server environment."}</span>
        </div>
        <ChevronRight size={16} className="muted-icon"/>
      </div>
    </section>
  );
}

function ProspectTable({ leads, onSelect, query, onQueryChange, compact = false }: {
  leads: Lead[];
  onSelect: (lead: Lead) => void;
  query: string;
  onQueryChange: (value: string) => void;
  compact?: boolean;
}) {
  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return leads;
    return leads.filter((lead) => [
      lead.company_name, lead.contact_name, lead.contact_email, lead.website, lead.location, lead.industry
    ].some((value) => String(value || "").toLowerCase().includes(term)));
  }, [leads, query]);

  return (
    <section className="surface-card prospects-card">
      <div className="panel-heading prospects-heading">
        <div>
          <span className="section-kicker">{compact ? "LATEST DISCOVERIES" : "YOUR PIPELINE"}</span>
          <h3>{compact ? "Recent prospects" : "All prospects"} <span className="count-chip">{leads.length}</span></h3>
        </div>
        <div className="table-tools">
          <label className="table-search">
            <Search size={14}/>
            <input aria-label="Search prospects" value={query} onChange={(e)=>onQueryChange(e.target.value)} placeholder="Search prospects"/>
          </label>
        </div>
      </div>

      {leads.length === 0 ? (
        <EmptyLeads onLaunch={()=>window.dispatchEvent(new Event("fili:launch-campaign"))}/>
      ) : filtered.length === 0 ? (
        <div className="table-no-results">No prospects match “{query}”.</div>
      ) : (
        <div className="table-scroll">
          <table className="prospects-table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Contact</th>
                <th>Domain</th>
                <th>Evidence</th>
                <th>Source</th>
                <th><span className="sr-only">Open details</span></th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0,compact?5:100).map((lead,index)=>{
                const mx=lead.email_verification?.status || "not checked";
                return (
                  <tr key={lead.company_name + "-" + index} onClick={()=>onSelect(lead)} tabIndex={0}
                    onKeyDown={(e)=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();onSelect(lead);}}}>
                    <td>
                      <div className="company-cell">
                        <div className="company-avatar">{(lead.company_name || "F").slice(0,1).toUpperCase()}</div>
                        <div className="cell-copy">
                          <strong>{lead.company_name || "Unknown company"}</strong>
                          <span>{lead.website || lead.industry || "Website not available"}</span>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="cell-copy">
                        <strong>{lead.contact_name || "Contact not found"}</strong>
                        <span>{lead.contact_email || "No email available"}</span>
                      </div>
                    </td>
                    <td><span className={"domain-state " + (mx==="mx_found"?"domain-ok":"")}>
                      <span className="domain-indicator"/>{mx.replaceAll("_"," ")}
                    </span></td>
                    <td><span className="score-value">{typeof lead.discovery_quality_score==="number"?lead.discovery_quality_score+"%":"—"}</span></td>
                    <td><span className={"source-pill " + (lead.is_synthetic?"source-preview":"")}>{lead.is_synthetic?"Preview":(lead.platform || "Search")}</span></td>
                    <td><button type="button" className="icon-button row-open" aria-label={"Open " + lead.company_name} onClick={(e)=>{e.stopPropagation();onSelect(lead);}}><ChevronRight size={16}/></button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {compact && leads.length > 5 && (
        <button type="button" className="panel-link" onClick={()=>window.dispatchEvent(new Event("fili:show-prospects"))}>
          View all prospects <ArrowRight size={14}/>
        </button>
      )}
    </section>
  );
}

function CampaignDialog({ open, busy, error, onClose, onSubmit }: {
  open: boolean;
  busy: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (payload: CampaignPayload) => void;
}) {
  const [target,setTarget]=useState("SaaS & Cloud Software");
  const [locationScope,setLocationScope]=useState<CampaignPayload["location_scope"]|null>(null);
  const [count,setCount]=useState("10");
  const [name,setName]=useState("New campaign");
  const [platform,setPlatform]=useState<CampaignPayload["platform"]>("google_maps");

  useEffect(()=>{
    if(!open)return;
    const onKey=(event:KeyboardEvent)=>{if(event.key==="Escape"&&!busy)onClose();};
    window.addEventListener("keydown",onKey);
    return ()=>window.removeEventListener("keydown",onKey);
  },[open,busy,onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="modal-backdrop" initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} onMouseDown={(e)=>{if(e.target===e.currentTarget&&!busy)onClose();}}>
          <motion.div className="campaign-modal" role="dialog" aria-modal="true" aria-labelledby="campaign-dialog-title"
            initial={{opacity:0,y:24,scale:.98}} animate={{opacity:1,y:0,scale:1}} exit={{opacity:0,y:16,scale:.98}}
            transition={{type:"spring",stiffness:340,damping:30}}>
            <div className="modal-head">
              <div className="modal-icon"><Rocket size={19}/></div>
              <div><span className="section-kicker">NEW WORKFLOW</span><h2 id="campaign-dialog-title">Launch a campaign</h2></div>
              <button type="button" className="icon-button modal-close" onClick={onClose} disabled={busy} aria-label="Close"><X size={18}/></button>
            </div>
            <form onSubmit={(event)=>{event.preventDefault();onSubmit({target,location:locationScope ? `${locationScope.city}, ${locationScope.state}, ${locationScope.country}` : "",location_scope:locationScope!,max_leads:Number(count),campaign_name:name,platform});}} className="campaign-form">
              <label className="field-group">
                <span>Campaign name</span>
                <input value={name} onChange={(e)=>setName(e.target.value)} maxLength={100} required/>
              </label>
              <label className="field-group">
                <span>Who are you looking for?</span>
                <input value={target} onChange={(e)=>setTarget(e.target.value)} maxLength={160} placeholder="e.g. FinTech founders" required/>
              </label>
              <div className="form-grid">
                <label className="field-group">
                  <span>Discovery source</span>
                  <select value={platform} onChange={(e)=>setPlatform(e.target.value as CampaignPayload["platform"])}>
                    {PLATFORM_OPTIONS.map((option)=><option value={option.value} key={option.value} disabled={"disabled" in option && option.disabled}>{option.label}</option>)}
                  </select>
                </label>
                <div className="field-group location-field"><LocationSelector value={locationScope} onChange={setLocationScope}/><span className="location-provider-note">City-verified discovery is currently enabled for Google Maps and Apollo. Other connectors stay disabled until they can verify each business address.</span></div>
              </div>
              <label className="field-group">
                <span>Maximum prospects</span>
                <select value={count} onChange={(e)=>setCount(e.target.value)}>
                  <option value="3">3 prospects</option>
                  <option value="5">5 prospects</option>
                  <option value="10">10 prospects</option>
                  <option value="25">25 prospects</option>
                </select>
              </label>
              {error && <div className="form-error"><CircleAlert size={16}/>{error}</div>}
              <div className="modal-footnote"><ShieldCheck size={15}/> Outreach remains draft-only. Review prospect sources before contacting.</div>
              <div className="modal-actions">
                <button type="button" className="button button-quiet" onClick={onClose} disabled={busy}>Cancel</button>
                <button type="submit" className="button button-primary" disabled={busy||!target.trim()||!name.trim()||!locationScope}>
                  {busy?<><LoaderCircle size={16} className="spin"/> Building pipeline</>:<>Start discovery <ArrowRight size={16}/></>}
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function ProspectDrawer({ lead, scanning, onClose, onScan }: {
  lead: Lead | null;
  scanning: boolean;
  onClose: () => void;
  onScan: () => void;
}) {
  const [expandedFollowUp,setExpandedFollowUp]=useState<number|null>(0);
  useEffect(()=>{
    if(!lead)return;
    const onKey=(event:KeyboardEvent)=>{if(event.key==="Escape")onClose();};
    window.addEventListener("keydown",onKey);
    return ()=>window.removeEventListener("keydown",onKey);
  },[lead,onClose]);

  return (
    <AnimatePresence>
      {lead && (
        <>
          <motion.button type="button" className="drawer-scrim" aria-label="Close prospect details" onClick={onClose}
            initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}}/>
          <motion.aside className="prospect-drawer" role="dialog" aria-modal="true" aria-label="Prospect details"
            initial={{x:"100%"}} animate={{x:0}} exit={{x:"100%"}}
            transition={{type:"spring",stiffness:330,damping:34}}>
            <div className="drawer-header">
              <div><span className="section-kicker">PROSPECT DETAILS</span><h2>Company profile</h2></div>
              <button type="button" className="icon-button" onClick={onClose} aria-label="Close drawer"><X size={18}/></button>
            </div>
            <div className="drawer-scroll">
              <div className="drawer-company">
                <div className="drawer-company-icon">{(lead.company_name||"F").slice(0,1).toUpperCase()}</div>
                <div><h3>{lead.company_name}</h3><span>{lead.industry || "Industry not available"}</span></div>
                {lead.is_synthetic && <span className="source-pill source-preview">Preview</span>}
              </div>
              <div className="drawer-score-row">
                <div><span>Evidence completeness</span><strong>{typeof lead.discovery_quality_score==="number"?lead.discovery_quality_score+"%":"—"}</strong></div>
                <div><span>Location match</span><strong>{lead.location_verified?"Verified":"Unverified"}</strong></div>
              </div>
              <div className="drawer-section">
                <div className="drawer-section-title"><span>Source provenance</span><span className="detail-muted">{lead.source_type?.replaceAll("_"," ") || "SOURCE RECORD"}</span></div>
                <div className="detail-line"><Globe size={15}/><span>{lead.platform || "Unknown provider"}</span></div>
                <div className="detail-line"><ShieldCheck size={15}/><span>{lead.location_match_status?.replaceAll("_"," ") || "Location not verified"}</span></div>
                <div className="detail-line"><Activity size={15}/><span>{lead.retrieved_at ? new Date(lead.retrieved_at).toLocaleString() : "Retrieval time unavailable"}</span></div>
                {lead.source_url && <a className="source-evidence-link" href={lead.source_url} target="_blank" rel="noopener noreferrer">Open source record <ExternalLink size={13}/></a>}
                <div className="evidence-list">{Object.entries(lead.field_evidence||{}).map(([field,evidence])=>(<div key={field}><span>{field.replaceAll("_"," ")}</span><strong>{evidence.status.replaceAll("_"," ")}</strong></div>))}</div>
              </div>
              <div className="drawer-section">
                <div className="drawer-section-title"><span>Contact</span><span className="detail-muted">NOT VERIFIED</span></div>
                <div className="detail-line"><Mail size={15}/><span>{lead.contact_email || "No email available"}</span></div>
                <div className="detail-line"><Users size={15}/><span>{lead.contact_name || "Contact not found"}{lead.contact_title?" · "+lead.contact_title:""}</span></div>
                <div className="detail-line"><Globe size={15}/><span>{lead.website || "No website available"}</span></div>
                {lead.phone && <div className="detail-line"><Activity size={15}/><span>{lead.phone}</span></div>}
                <div className="detail-line"><ShieldCheck size={15}/><span>MX: {lead.email_verification?.status?.replaceAll("_"," ") || "Not checked"} · mailbox not verified</span></div>
              </div>
              <div className="drawer-section">
                <div className="drawer-section-title"><span>Technology signals</span><button type="button" className="text-button" onClick={onScan} disabled={!lead.website||scanning}>
                  {scanning?<LoaderCircle size={13} className="spin"/>:<Activity size={13}/>} Scan
                </button></div>
                {lead.tech_stack?.length ? <div className="tech-chips">{lead.tech_stack.map((tech)=><span key={tech}>{tech}</span>)}</div>
                  : <p className="detail-empty">No scan signals yet. Scan the public website to inspect visible technologies.</p>}
              </div>
              <div className="drawer-section">
                <div className="drawer-section-title"><span>Follow-up drafts</span><span className="detail-muted">DAY 1 / 3 / 7</span></div>
                {(lead.follow_up_sequence||[]).map((draft,index)=>(
                  <div className="followup-item" key={draft.day}>
                    <button type="button" className="followup-toggle" onClick={()=>setExpandedFollowUp(expandedFollowUp===index?null:index)}>
                      <span><b>Day {draft.day}</b><small>{draft.label}</small></span>
                      <ChevronDown size={15} className={expandedFollowUp===index?"rotate-chevron":""}/>
                    </button>
                    <AnimatePresence initial={false}>
                      {expandedFollowUp===index&&(
                        <motion.div className="followup-body" initial={{height:0,opacity:0}} animate={{height:"auto",opacity:1}} exit={{height:0,opacity:0}}>
                          <strong>{draft.subject}</strong>
                          <p>{draft.body}</p>
                          <button type="button" className="text-button" onClick={()=>window.open("https://mail.google.com/mail/?view=cm&fs=1&to="+encodeURIComponent(lead.contact_email||"")+"&su="+encodeURIComponent(draft.subject)+"&body="+encodeURIComponent(draft.body),"_blank","noopener,noreferrer")} disabled={!isOutreachEligible(lead)}>
                            Open email draft <ExternalLink size={13}/>
                          </button>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                ))}
                {!lead.follow_up_sequence?.length&&<p className="detail-empty">Follow-up drafts are generated after a campaign runs.</p>}
              </div>
            </div>
            <div className="drawer-actions">
              {lead.whatsapp_url && isOutreachEligible(lead) && <a className="button button-outline" href={lead.whatsapp_url} target="_blank" rel="noopener noreferrer">WhatsApp <ExternalLink size={14}/></a>}
              <button type="button" className="button button-primary" disabled={!isOutreachEligible(lead)||!lead.contact_email}
                onClick={()=>window.open("https://mail.google.com/mail/?view=cm&fs=1&to="+encodeURIComponent(lead.contact_email||"")+"&su="+encodeURIComponent(lead.email_subject||"")+"&body="+encodeURIComponent(lead.email_body||""),"_blank","noopener,noreferrer")}>
                <Mail size={15}/> Open email draft
              </button>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

function Dashboard() {
  const reducedMotion=useReducedMotion();
  const [activeNav,setActiveNav]=useState<NavItem>("overview");
  const [mobileNavOpen,setMobileNavOpen]=useState(false);
  const [campaignOpen,setCampaignOpen]=useState(false);
  const [campaignBusy,setCampaignBusy]=useState(false);
  const [campaignError,setCampaignError]=useState("");
  const [apiState,setApiState]=useState<ApiState>("checking");
  const [apiStatus,setApiStatus]=useState<ApiStatus|null>(null);
  const [leads,setLeads]=useState<Lead[]>([]);
  const [selectedLead,setSelectedLead]=useState<Lead|null>(null);
  const [query,setQuery]=useState("");
  const [lastCampaign,setLastCampaign]=useState("");
  const [lastRun,setLastRun]=useState<string|null>(null);
  const [lastDiagnostics,setLastDiagnostics]=useState<CampaignResponse["diagnostics"]|null>(null);
  const [lastSourceStatus,setLastSourceStatus]=useState("");
  const [lastSourceMessage,setLastSourceMessage]=useState("");
  const [scanning,setScanning]=useState(false);
  const [notice,setNotice]=useState("");
  const searchRef=useRef<HTMLInputElement>(null);

  const refreshStatus=useCallback(async()=>{
    try{
      const status=await getApiStatus();
      setApiStatus(status);
      setApiState(status.online?"connected":"disconnected");
    }catch{
      setApiStatus(null);
      setApiState("disconnected");
    }
  },[]);

  useEffect(()=>{
    const timer = window.setTimeout(() => { void refreshStatus(); }, 0);
    return () => window.clearTimeout(timer);
  },[refreshStatus]);

  useEffect(()=>{
    const onLaunch=()=>setCampaignOpen(true);
    const onShowProspects=()=>setActiveNav("prospects");
    const onKey=(event:KeyboardEvent)=>{
      if((event.metaKey||event.ctrlKey)&&event.key.toLowerCase()==="k"){
        event.preventDefault();
        searchRef.current?.focus();
      }
      if(event.key==="/"&&document.activeElement?.tagName!=="INPUT"&&document.activeElement?.tagName!=="TEXTAREA"){
        event.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("fili:launch-campaign",onLaunch);
    window.addEventListener("fili:show-prospects",onShowProspects);
    window.addEventListener("keydown",onKey);
    return ()=>{
      window.removeEventListener("fili:launch-campaign",onLaunch);
      window.removeEventListener("fili:show-prospects",onShowProspects);
      window.removeEventListener("keydown",onKey);
    };
  },[]);

  const showNotice=useCallback((message:string)=>{
    setNotice(message);
    window.setTimeout(()=>setNotice(""),3200);
  },[]);

  const handleLaunch=useCallback(async(payload:CampaignPayload)=>{
    setCampaignBusy(true);
    setCampaignError("");
    try{
      const response=await runCampaign(payload);
      if(!response.success)throw new Error(response.error||"Campaign could not be completed.");
      setLeads(response.leads||[]);
      setLastDiagnostics(response.diagnostics||null);
      setLastSourceStatus(response.source_status||"");
      setLastSourceMessage(response.message||"");
      setLastCampaign(payload.campaign_name);
      setLastRun(new Date().toISOString());
      setCampaignOpen(false);
      setSelectedLead(null);
      setApiState("connected");
      setActiveNav("prospects");
      showNotice(response.source_status==="provider_error" ? "Provider error — review source diagnostics" : (response.leads||[]).length+" prospects discovered");
    }catch(error){
      setCampaignError(error instanceof Error?error.message:"Campaign failed. Check the Fili API connection.");
    }finally{
      setCampaignBusy(false);
    }
  },[showNotice]);

  const handleScan=useCallback(async()=>{
    if(!selectedLead?.website)return;
    setScanning(true);
    try{
      const result=await scanWebsite(selectedLead.website);
      const next={...selectedLead,tech_stack:result.signals||[],tech_scan_status:result.status};
      setSelectedLead(next);
      setLeads((current)=>current.map((lead)=>lead===selectedLead?next:lead));
      showNotice(result.status==="scanned"?"Website scan complete":"Website scan unavailable");
    }catch(error){
      showNotice(error instanceof Error?error.message:"Website scan failed");
    }finally{
      setScanning(false);
    }
  },[selectedLead,showNotice]);

  const filteredLeads=useMemo(()=>{
    const term=query.trim().toLowerCase();
    if(!term)return leads;
    return leads.filter((lead)=>[
      lead.company_name,lead.contact_name,lead.contact_email,lead.website,lead.location,lead.industry
    ].some((value)=>String(value||"").toLowerCase().includes(term)));
  },[leads,query]);

  const outreachCount=leads.filter(isOutreachEligible).length;
  const mxCount=leads.filter((lead)=>lead.email_verification?.mx_found).length;
  const techCount=leads.filter((lead)=>(lead.tech_stack||[]).length>0).length;
  const locationVerified=leads.filter((lead)=>lead.location_verified).length;
  const contactVerified=leads.filter((lead)=>lead.contact_verified).length;
  const avgEvidence=leads.length ? Math.round(leads.reduce((total,lead)=>total+(lead.discovery_quality_score||0),0)/leads.length) : 0;
  const stats=[
    {label:"Companies discovered",value:String(leads.length),hint:lastRun?"Latest discovery run":"No run in this session",icon:Users,tone:"blue"},
    {label:"Location verified",value:String(locationVerified),hint:"Exact city + state evidence",icon:Globe,tone:"green"},
    {label:"Contacts verified",value:String(contactVerified),hint:"Provider-confirmed contacts",icon:ShieldCheck,tone:"violet"},
    {label:"Evidence completeness",value:leads.length?avgEvidence+"%":"—",hint:"Not a sales conversion score",icon:Activity,tone:"amber"}
  ];

  const pageTitle=PAGE_TITLES[activeNav];
  const openCampaign=()=>{setCampaignError("");setCampaignOpen(true);};
  const exportFile=(kind:"csv"|"xlsx")=>{
    if(leads.length===0){showNotice("Run a campaign before exporting prospects.");return;}
    window.location.assign(exportUrl(kind));
  };

  return (
    <div className="app-shell">
      <AnimatePresence>
        {mobileNavOpen&&(
          <motion.button type="button" aria-label="Close navigation" className="mobile-scrim"
            initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} onClick={()=>setMobileNavOpen(false)}/>
        )}
      </AnimatePresence>
      <motion.aside className={"sidebar "+(mobileNavOpen?"sidebar-open":"")}
        initial={reducedMotion?false:{x:-18,opacity:0}} animate={{x:0,opacity:1}}
        transition={{duration:reducedMotion?0:.45,ease:[.2,.75,.2,1]}}>
        <div className="sidebar-top">
          <Brand/>
          <button type="button" className="icon-button mobile-close" onClick={()=>setMobileNavOpen(false)} aria-label="Close navigation"><X size={18}/></button>
        </div>
        <button type="button" className="workspace-switcher" onClick={()=>setActiveNav("settings")}>
          <span className="workspace-avatar">F</span>
          <span className="workspace-label"><strong>Fili workspace</strong><small>Personal workspace</small></span>
          <ChevronDown size={15}/>
        </button>

        <div className="nav-group">
          <span className="nav-label">WORKSPACE</span>
          <nav aria-label="Main navigation">
            {NAV_ITEMS.map((item)=>{
              const Icon=item.icon;
              return (
                <button type="button" key={item.id} className={"nav-link "+(activeNav===item.id?"nav-active":"")}
                  onClick={()=>{setActiveNav(item.id);setMobileNavOpen(false);}}>
                  <Icon size={17} strokeWidth={1.8}/>
                  <span>{item.label}</span>
                  {item.id==="prospects"&&leads.length>0&&<span className="nav-count">{leads.length}</span>}
                  {activeNav===item.id&&<motion.span layoutId="nav-rail" className="nav-rail"/>}
                </button>
              );
            })}
          </nav>
        </div>

        <div className="sidebar-divider"/>
        <div className="nav-group nav-secondary">
          <span className="nav-label">TOOLS</span>
          <button type="button" className="nav-link" onClick={()=>setActiveNav("prospects")}><Download size={17}/><span>CRM exports</span></button>
          <button type="button" className="nav-link" onClick={()=>setActiveNav("settings")}><CalendarDays size={17}/><span>Daily prospector</span></button>
        </div>

        <div className="sidebar-bottom">
          <div className="engine-card">
            <div className="engine-card-top"><span className="engine-pulse"/><span>FILI ENGINE</span><span className="engine-version">01</span></div>
            <strong>{apiState==="connected"?"Ready for discovery":apiState==="checking"?"Connecting…":"Waiting for API"}</strong>
            <span>{apiState==="connected"?"Your prospecting API is reachable.":"Connect the Python engine to run campaigns."}</span>
            <button type="button" className="engine-link" onClick={()=>setActiveNav("settings")}>Connection settings <ArrowUpRight size={13}/></button>
          </div>
          <div className="sidebar-profile">
            <div className="profile-avatar">F</div>
            <div><strong>Workspace owner</strong><small>Fili account</small></div>
            <MoreHorizontal size={18}/>
          </div>
        </div>
      </motion.aside>

      <div className="main-column">
        <header className="topbar">
          <div className="topbar-leading">
            <button type="button" className="icon-button mobile-menu" onClick={()=>setMobileNavOpen(true)} aria-label="Open navigation"><Menu size={19}/></button>
            <div className="breadcrumb"><span>Workspace</span><ChevronRight size={13}/><strong>{pageTitle}</strong></div>
          </div>
          <div className="topbar-actions">
            <label className="global-search">
              <Search size={16}/>
              <input ref={searchRef} value={query} onChange={(e)=>{setQuery(e.target.value);if(e.target.value)setActiveNav("prospects");}} placeholder="Search anything…" aria-label="Search prospects"/>
              <kbd><Command size={11}/> K</kbd>
            </label>
            <StatusPill state={apiState}/>
            <button type="button" className="icon-button notification-button" onClick={()=>showNotice(apiStatus?.daily_schedule_enabled?"Daily prospector is active.":"No new activity")} aria-label="Notifications">
              <Bell size={17}/><span className="notification-dot"/>
            </button>
            <button type="button" className="topbar-avatar" onClick={()=>setActiveNav("settings")} aria-label="Workspace settings">F</button>
          </div>
        </header>

        <main className="page-content">
          {activeNav==="overview"&&(
            <>
              <div className="page-intro">
                <div><span className="section-kicker">WORKSPACE OVERVIEW</span><h1>Good work starts with <span>good signals.</span></h1></div>
                <div className="intro-actions">
                  <button type="button" className="button button-outline" onClick={()=>{setApiState("checking");void refreshStatus();}}><Activity size={15}/> Refresh status</button>
                  <button type="button" className="button button-primary" onClick={openCampaign}><Plus size={16}/> New campaign</button>
                </div>
              </div>

              <section className="command-hero">
                <div className="command-hero-copy">
                  <span className="hero-overline"><span/> FILI / INTELLIGENCE WORKSPACE</span>
                  <h2>Find companies.<br/><em>Verify every signal.</em></h2>
                  <p>Evidence-led B2B discovery with exact location matching, source transparency and controlled outreach.</p>
                  <div className="hero-buttons">
                    <button type="button" className="button button-primary" onClick={openCampaign}><Plus size={16}/> Start discovery</button>
                    <button type="button" className="button button-outline" onClick={()=>setActiveNav("prospects")}>Review prospects <ArrowRight size={15}/></button>
                  </div>
                </div>
                <div className="command-hero-aside">
                  <div className="command-index">SYSTEM STATUS / 01</div>
                  <div className="command-state"><span className={apiState==="connected"?"command-state-dot is-live":"command-state-dot"}/>{apiState==="connected"?"Discovery engine online":apiState==="checking"?"Checking engine":"Engine unavailable"}</div>
                  <div className="command-divider"/>
                  <div className="command-meta"><span>LAST RUN</span><strong>{lastRun?new Date(lastRun).toLocaleString():"No activity"}</strong></div>
                  <div className="command-meta"><span>ACTIVE SOURCE</span><strong>{lastDiagnostics?.provider||"Not selected"}</strong></div>
                </div>
              </section>
              {lastSourceMessage && <div className={"discovery-notice "+(lastSourceStatus==="provider_error"?"notice-error":"")}><ShieldCheck size={16}/><div><strong>{lastSourceStatus.replaceAll("_"," ")||"Discovery status"}</strong><span>{lastSourceMessage}</span></div></div>}

              <section className="stats-grid" aria-label="Current session metrics">
                {stats.map((stat,index)=>{
                  const Icon=stat.icon;
                  return (
                    <motion.article className="stat-card" key={stat.label}
                      initial={reducedMotion?false:{opacity:0,y:14}} animate={{opacity:1,y:0}}
                      transition={{duration:reducedMotion?0:.38,delay:reducedMotion?0:index*.07}}>
                      <div className="stat-top"><span>{stat.label}</span><span className={"stat-icon stat-"+stat.tone}><Icon size={17}/></span></div>
                      <div className="stat-value">{stat.value}</div>
                      <div className="stat-hint">{stat.hint}</div>
                    </motion.article>
                  );
                })}
              </section>

              <div className="overview-grid">
                <ProspectTable leads={filteredLeads} onSelect={setSelectedLead} query={query} onQueryChange={setQuery} compact/>
                <WorkflowCard apiState={apiState} leadsCount={leads.length} schedule={apiStatus}/>
              </div>

              <section className="surface-card integrity-panel">
                <div className="integrity-heading"><div><span className="section-kicker">DISCOVERY INTEGRITY</span><h3>Evidence before volume</h3></div><ShieldCheck size={19}/></div>
                <div className="integrity-grid">
                  <div><strong>{lastDiagnostics?.raw_results??"—"}</strong><span>Raw provider results</span></div>
                  <div><strong>{lastDiagnostics?.duplicates_removed??"—"}</strong><span>Duplicates removed</span></div>
                  <div><strong>{lastDiagnostics?.rejected_by_location??"—"}</strong><span>Location rejected</span></div>
                  <div><strong>{lastDiagnostics?.returned_results??leads.length}</strong><span>Records returned</span></div>
                </div>
                <p>Evidence completeness measures source-backed information. It is not buyer intent, lead relevance or a conversion prediction.</p>
              </section>
            </>
          )}

          {activeNav==="prospects"&&(
            <>
              <div className="page-intro">
                <div><span className="section-kicker">CONTACT INTELLIGENCE</span><h1>Prospects<span className="title-period">.</span></h1><p className="page-subtitle">Your current discovery session, ready to review.</p></div>
                <div className="intro-actions">
                  <button type="button" className="button button-outline" onClick={()=>exportFile("csv")} disabled={!leads.length}><Download size={15}/> CSV</button>
                  <button type="button" className="button button-outline" onClick={()=>exportFile("xlsx")} disabled={!leads.length}><Download size={15}/> Excel</button>
                  <button type="button" className="button button-primary" onClick={openCampaign}><Plus size={16}/> New search</button>
                </div>
              </div>
              <div className="prospect-summary-row">
                <div><strong>{leads.length}</strong><span>Found this session</span></div>
                <div><strong>{locationVerified}</strong><span>City verified</span></div>
                <div><strong>{contactVerified}</strong><span>Contacts verified</span></div>
                <div className="summary-source"><span className="summary-source-dot"/>{lastCampaign||"No active campaign"}</div>
              </div>
              <ProspectTable leads={filteredLeads} onSelect={setSelectedLead} query={query} onQueryChange={setQuery}/>
              <p className="page-footnote"><ShieldCheck size={14}/> MX checks confirm domain mail routing only. They do not verify an individual mailbox.</p>
            </>
          )}

          {activeNav==="campaigns"&&(
            <>
              <div className="page-intro">
                <div><span className="section-kicker">DISCOVERY WORKFLOWS</span><h1>Campaigns<span className="title-period">.</span></h1><p className="page-subtitle">Launch and review your prospecting runs.</p></div>
                <button type="button" className="button button-primary" onClick={openCampaign}><Plus size={16}/> New campaign</button>
              </div>
              <section className="surface-card campaign-overview">
                <div className="campaign-overview-icon"><Rocket size={22}/></div>
                <div className="campaign-overview-copy">
                  <span className="section-kicker">LATEST CAMPAIGN</span>
                  <h2>{lastCampaign||"Your campaign workspace is ready"}</h2>
                  <p>{lastRun?"Completed "+new Date(lastRun).toLocaleString():"Launch discovery to create your first campaign."}</p>
                </div>
                <div className="campaign-overview-metrics"><div><strong>{leads.length}</strong><span>Prospects</span></div><div><strong>{outreachCount}</strong><span>Ready</span></div></div>
              </section>
              {leads.length>0?<ProspectTable leads={filteredLeads} onSelect={setSelectedLead} query={query} onQueryChange={setQuery}/>:<EmptyLeads onLaunch={openCampaign}/>}
            </>
          )}

          {activeNav==="settings"&&(
            <>
              <div className="page-intro">
                <div><span className="section-kicker">CONFIGURATION</span><h1>Workspace settings<span className="title-period">.</span></h1><p className="page-subtitle">Connection health and discovery schedule.</p></div>
                <div className="intro-actions">
          <button type="button" className="button button-outline" onClick={refreshStatus}><Activity size={15}/> Recheck</button>
        </div>
              </div>
              <DeveloperPanel />
              <section className="surface-card settings-card">
                <div className="settings-heading"><div className="settings-symbol"><Zap size={19}/></div><div><h3>Fili prospecting engine</h3><p>Python API connection</p></div><StatusPill state={apiState}/></div>
                <div className="settings-row"><span>API status</span><strong>{apiState==="connected"?"Connected":apiState==="checking"?"Checking":"Not connected"}</strong></div>
                <div className="settings-row"><span>Agents available</span><strong>{apiStatus?.agents_count??"—"}</strong></div>
                <div className="settings-row"><span>Last campaign</span><strong>{apiStatus?.latest_campaign||lastCampaign||"None"}</strong></div>
                {apiState!=="connected"&&<div className="settings-callout"><CircleAlert size={17}/><div><strong>Connect the Python service</strong><span>Set FILI_API_BASE_URL on the Next.js server to the deployed Fili API URL. For local development, use http://127.0.0.1:8000.</span></div></div>}
              </section>
              <section className="surface-card settings-card">
                <div className="settings-heading"><div className="settings-symbol settings-symbol-blue"><CalendarDays size={19}/></div><div><h3>Daily prospector</h3><p>Scheduled discovery</p></div><span className={"setting-state "+(apiStatus?.daily_schedule_enabled?"setting-on":"")}>{apiStatus?.daily_schedule_enabled?"Active":"Disabled"}</span></div>
                <div className="settings-row"><span>Schedule</span><strong>{apiStatus?.daily_schedule_time||"09:00"} · {apiStatus?.daily_schedule_timezone||"Asia/Kolkata"}</strong></div>
                <div className="settings-row"><span>Next run</span><strong>{apiStatus?.next_run?new Date(apiStatus.next_run).toLocaleString():"—"}</strong></div>
                <div className="settings-row"><span>Last scheduled run</span><strong>{apiStatus?.last_daily_run?apiStatus.last_daily_run.lead_count+" prospects":"No runs yet"}</strong></div>
                <p className="settings-note">Enable FILI_DAILY_PROSPECTOR_ENABLED=true on the Python server. The scheduler runs in-process and is intended for a single API instance.</p>
              </section>
              <section className="surface-card settings-card">
                <div className="settings-heading"><div className="settings-symbol"><ShieldCheck size={19}/></div><div><h3>Data & outreach controls</h3><p>Built-in safeguards</p></div></div>
                <div className="settings-row"><span>Email checks</span><strong>MX only · mailbox not verified</strong></div>
                <div className="settings-row"><span>Outbound email</span><strong>Dry-run pipeline</strong></div>
                <div className="settings-row"><span>Preview leads</span><strong>Gmail / WhatsApp disabled</strong></div>
                <div className="settings-row"><span>Website scan</span><strong>Public HTTP(S) only</strong></div>
              </section>
            </>
          )}
          <footer className="app-footer"><span>FILI / PROSPECTING OS</span><span>Focused by design <span className="footer-blue">●</span></span></footer>
        </main>
      </div>

      <CampaignDialog open={campaignOpen} busy={campaignBusy} error={campaignError} onClose={()=>setCampaignOpen(false)} onSubmit={handleLaunch}/>
      <ProspectDrawer key={selectedLead ? selectedLead.company_name + (selectedLead.contact_email || "") : "closed"} lead={selectedLead} scanning={scanning} onClose={()=>setSelectedLead(null)} onScan={handleScan}/>
      <AnimatePresence>
        {notice&&<motion.div className="toast" role="status" aria-live="polite" initial={{opacity:0,y:12}} animate={{opacity:1,y:0}} exit={{opacity:0,y:8}}>
          <span className="toast-check"><Check size={13}/></span>{notice}
        </motion.div>}
      </AnimatePresence>
    </div>
  );
}

export default Dashboard;
