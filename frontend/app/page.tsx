"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import {
  ArrowRight, ArrowUpRight, Check, ChevronDown, CircleDot, Compass,
  Database, FileCheck2, Fingerprint, Globe2, Layers3, Menu, ShieldCheck,
  Target, Workflow, X, Zap
} from "lucide-react";

const steps = [
  { number: "01", title: "Discover", text: "Find businesses that match your target market and the locations you actually serve.", icon: Compass },
  { number: "02", title: "Research", text: "Bring company context and source links into one focused prospect record.", icon: Database },
  { number: "03", title: "Qualify", text: "See what is supported by evidence, what is missing, and what needs review.", icon: ShieldCheck },
  { number: "04", title: "Activate", text: "Organize prospects and prepare thoughtful outreach when the information is ready.", icon: Zap }
];

const capabilities = [
  { icon: Globe2, title: "Location-aware discovery", text: "Keep your search grounded in the country, state and city you selected." },
  { icon: FileCheck2, title: "Evidence before assumptions", text: "Source provenance and field-level evidence help your team inspect the facts." },
  { icon: Fingerprint, title: "Clear confidence boundaries", text: "Missing information stays missing. Unverified hints are not presented as confirmed facts." },
  { icon: Layers3, title: "One connected workflow", text: "Move from discovery to review and follow-up without scattering context across tools." }
];

export default function Home() {
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);

  return (
    <main className="marketing-shell">
      <div className="announcement"><span className="announcement-dot" /> Built for evidence-led prospecting <span className="announcement-separator">·</span> <a href="#approach">See how Fili works <ArrowUpRight size={12}/></a></div>
      <header className="marketing-nav">
        <Link href="/" className="marketing-brand" aria-label="Fili home">
          <span className="marketing-brand-mark">f</span><span>fili</span><small>PROSPECTING OS</small>
        </Link>
        <nav className={menuOpen ? "marketing-links is-open" : "marketing-links"}>
          <a href="#platform" onClick={closeMenu}>Platform</a>
          <a href="#approach" onClick={closeMenu}>How it works</a>
          <a href="#principles" onClick={closeMenu}>Our approach</a>
          <a href="#faq" onClick={closeMenu}>FAQ</a>
          <Link className="mobile-nav-cta" href="/login" onClick={closeMenu}>Open workspace <ArrowRight size={15}/></Link>
        </nav>
        <div className="marketing-nav-actions">
          <Link href="/login" className="nav-login">Sign in</Link>
          <Link href="/login" className="marketing-nav-cta">Open workspace <ArrowUpRight size={14}/></Link>
          <button className="marketing-menu-toggle" onClick={() => setMenuOpen(!menuOpen)} aria-label={menuOpen ? "Close menu" : "Open menu"}>{menuOpen ? <X size={21}/> : <Menu size={21}/>}</button>
        </div>
      </header>

      <section className="marketing-hero">
        <div className="hero-copy-block">
          <div className="eyebrow"><span className="eyebrow-line"/> A clearer way to find your next customer</div>
          <h1>Less noise.<br/><span>Better prospects.</span></h1>
          <p className="hero-description">Fili brings business discovery, company research and prospect qualification into one focused workspace — with evidence behind the details.</p>
          <div className="hero-actions">
            <Link href="/login" className="primary-cta">Explore the workspace <ArrowRight size={17}/></Link>
            <a href="#approach" className="secondary-cta">See how it works <span><ArrowDownIcon/></span></a>
          </div>
          <div className="hero-proof"><span className="proof-icon"><ShieldCheck size={15}/></span><span>Evidence-led by design</span><i/> <span>No guessed contacts or fabricated details</span></div>
        </div>
        <div className="hero-visual">
          <div className="hero-photo-wrap">
            <Image src="https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=1500&q=85" alt="Modern city office buildings" fill priority unoptimized sizes="(max-width: 900px) 100vw, 52vw" className="hero-photo"/>
            <div className="photo-shade"/>
          </div>
          <div className="floating-workspace">
            <div className="preview-top"><div className="preview-brand"><span className="preview-brand-mark">f</span> fili <small>WORKSPACE PREVIEW</small></div><span className="preview-live"><i/> LIVE INTERFACE</span></div>
            <div className="preview-body">
              <div className="preview-sidebar"><span className="preview-side-active"/><span/><span/><span/><span/></div>
              <div className="preview-main">
                <div className="preview-heading"><div><small>YOUR WORKSPACE</small><strong>Prospect overview</strong></div><span className="preview-filter">All locations <ChevronDown size={11}/></span></div>
                <div className="preview-metrics"><div><small>DISCOVERED</small><strong>—</strong><span>Awaiting search</span></div><div><small>LOCATION MATCH</small><strong>—</strong><span>Evidence-based</span></div><div><small>CONTACTS</small><strong>—</strong><span>Not assumed</span></div></div>
                <div className="preview-table-head"><span>COMPANY</span><span>LOCATION</span><span>EVIDENCE</span></div>
                <div className="preview-row"><span><b className="preview-company-icon">A</b><i><strong>Company record</strong><small>Source-linked profile</small></i></span><span className="preview-location">Needs review</span><span className="preview-evidence">Inspect <ArrowUpRight size={11}/></span></div>
                <div className="preview-row"><span><b className="preview-company-icon alt">B</b><i><strong>Company record</strong><small>Source-linked profile</small></i></span><span className="preview-location">Matched</span><span className="preview-evidence">Inspect <ArrowUpRight size={11}/></span></div>
                <div className="preview-row"><span><b className="preview-company-icon third">C</b><i><strong>Company record</strong><small>Source-linked profile</small></i></span><span className="preview-location">Needs review</span><span className="preview-evidence">Inspect <ArrowUpRight size={11}/></span></div>
              </div>
            </div>
            <div className="preview-foot"><span><CircleDot size={12}/> Illustrative interface preview</span><span>DISCOVER → REVIEW → ACT</span></div>
          </div>
          <div className="hero-visual-caption"><span>01 / THE FILI WORKSPACE</span><span>Clarity at every step</span></div>
        </div>
      </section>

      <section className="principle-strip" id="principles">
        <div className="principle-strip-intro">A better standard<br/>for prospect data.</div>
        <div><ShieldCheck size={19}/><strong>Evidence first</strong><span>Every detail should have a source.</span></div>
        <div><Target size={19}/><strong>Location precise</strong><span>Search where your market exists.</span></div>
        <div><Fingerprint size={19}/><strong>Honest by default</strong><span>Unknown is better than invented.</span></div>
      </section>

      <section className="platform-section" id="platform">
        <div className="section-heading">
          <div><div className="eyebrow"><span className="eyebrow-line"/> THE PLATFORM</div><h2>From scattered research<br/>to a <em>clear next step.</em></h2></div>
          <p>Prospecting should feel like a system, not a spreadsheet hunt. Fili gives every stage a place, every record context, and every decision a reason.</p>
        </div>
        <div className="capability-grid">
          {capabilities.map((item,index)=>{const Icon=item.icon;return <article className="capability-card" key={item.title}><div className="capability-top"><span>0{index+1}</span><Icon size={19}/></div><h3>{item.title}</h3><p>{item.text}</p><span className="capability-rule"/></article>;})}
        </div>
      </section>

      <section className="approach-section" id="approach">
        <div className="approach-image">
          <Image src="https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1300&q=85" alt="Minimal modern office workspace" fill unoptimized sizes="(max-width: 800px) 100vw, 46vw"/>
          <div className="approach-image-overlay"><span>THE FILI METHOD</span><strong>Context before<br/>conversation.</strong></div>
        </div>
        <div className="approach-copy">
          <div className="eyebrow"><span className="eyebrow-line"/> HOW IT WORKS</div>
          <h2>A deliberate workflow.<br/><em>Not another lead list.</em></h2>
          <p className="approach-intro">Each step makes the next one more useful. Keep the signal, inspect the source, and move forward when the information is ready.</p>
          <div className="workflow-list">
            {steps.map((step)=>{const Icon=step.icon;return <div className="workflow-item" key={step.number}><span className="workflow-number">{step.number}</span><span className="workflow-icon"><Icon size={18}/></span><div><h3>{step.title}</h3><p>{step.text}</p></div><ArrowUpRight size={15} className="workflow-arrow"/></div>;})}
          </div>
        </div>
      </section>

      <section className="trust-section">
        <div className="trust-copy"><div className="eyebrow"><span className="eyebrow-line"/> TRUST IS A PRODUCT FEATURE</div><h2>Never confuse<br/><em>more data</em> with<br/>better intelligence.</h2><p>Fili is designed to make the quality of information visible. Sources, location match and missing fields should be easy to inspect — not hidden behind a confident-looking score.</p><Link href="/login" className="text-link">See the workspace <ArrowRight size={15}/></Link></div>
        <div className="trust-visual">
          <div className="trust-card"><div className="trust-card-header"><span>RECORD INTEGRITY</span><span className="trust-status"><i/> TRANSPARENT</span></div><div className="trust-field"><span>Company name</span><strong><Check size={14}/> Source available</strong></div><div className="trust-field"><span>Business location</span><strong><Check size={14}/> Match inspected</strong></div><div className="trust-field"><span>Contact details</span><strong className="not-available">Not provided</strong></div><div className="trust-field"><span>Source provenance</span><strong><Check size={14}/> View source</strong></div><div className="trust-card-note"><ShieldCheck size={15}/> Missing data stays visible. No generated identities.</div></div>
          <div className="trust-decoration">F / 01</div>
        </div>
      </section>

      <section className="closing-cta">
        <div className="closing-cta-image"><Image src="https://images.unsplash.com/photo-1497366811353-6870744d04b2?auto=format&fit=crop&w=1800&q=85" alt="Light-filled contemporary office" fill unoptimized sizes="100vw"/></div>
        <div className="closing-cta-content"><div className="eyebrow"><span className="eyebrow-line"/> START WITH CLARITY</div><h2>Make every prospect<br/>worth a closer look.</h2><p>Bring your discovery and research workflow into one place.</p><Link href="/login" className="primary-cta">Open Fili workspace <ArrowRight size={17}/></Link></div>
      </section>

      <section className="faq-section" id="faq"><div><div className="eyebrow"><span className="eyebrow-line"/> QUESTIONS</div><h2>Clarity, before<br/><em>you get started.</em></h2></div><div className="faq-list"><details><summary>What is Fili? <ChevronDown size={16}/></summary><p>Fili is a prospecting workspace for discovering businesses, researching company context, reviewing evidence and organizing outreach.</p></details><details><summary>Does Fili invent contact information? <ChevronDown size={16}/></summary><p>No. The product is designed to avoid guessed identities and generated contact details. Missing or unsupported information should remain clearly marked.</p></details><details><summary>Can I search by a specific location? <ChevronDown size={16}/></summary><p>Yes. The discovery workflow supports hierarchical country, state and city targeting where the selected data provider can verify location evidence.</p></details><details><summary>Does Fili send outreach automatically? <ChevronDown size={16}/></summary><p>Outreach is currently draft-oriented. Review prospect sources and details before contacting anyone.</p></details></div></section>

      <footer className="marketing-footer"><Link href="/" className="marketing-brand"><span className="marketing-brand-mark">f</span><span>fili</span><small>PROSPECTING OS</small></Link><span>Evidence-led prospecting.</span><div><a href="#platform">Platform</a><a href="#approach">How it works</a><Link href="/login">Workspace <ArrowUpRight size={12}/></Link></div><small>© {new Date().getFullYear()} Fili. All rights reserved.</small></footer>
    </main>
  );
}

function ArrowDownIcon() {
  return <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M6.5 1.5v9m0 0 3.5-3.5M6.5 10.5 3 7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}
