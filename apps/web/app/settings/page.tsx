"use client";
import { Shell } from "@/components/Shell";
import { useState, useEffect, useCallback } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface ConfigStatus {
  supabase_configured: boolean; storage_bucket_configured: boolean;
  openrouter_configured: boolean; ai_extraction_enabled: boolean;
  ai_reasoning_enabled: boolean;
}

export default function SettingsPage() {
  const [config, setConfig] = useState<ConfigStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/invoices/config/status`);
      if (!res.ok) throw new Error("Failed to fetch config status");
      const data: ConfigStatus = await res.json();
      setConfig(data);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed to load configuration status"); } finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchConfig(); }, [fetchConfig]);

  if (loading) {
    return (<Shell><header className="topbar"><div><div className="eyebrow">ACCOUNTS PAYABLE / SETTINGS</div><h1>Settings</h1></div></header><div className="emptyState"><div className="emptyIcon">↻</div><strong>Loading configuration…</strong></div></Shell>);
  }

  const badge = (on?: boolean) => on ? "statusBadge statusConnected" : "statusBadge statusNotConfigured";

  return (
    <Shell>
      <header className="topbar"><div><div className="eyebrow">ACCOUNTS PAYABLE / SETTINGS</div><h1>Settings</h1></div></header>
      <div className="sectionHead"><div><h3>Workspace settings</h3><p>Configure integrations, extraction provider, and approval rules.</p></div></div>
      <div className="settingsGrid">
        <section className="reviewPanel" style={{padding:20}}>
          <h3 style={{margin:"0 0 14px 0",fontSize:15}}>Integrations</h3>
          <dl className="settingsList">
            <dt>Supabase</dt><dd><span className={`${badge(config?.supabase_configured)}`}>{config?.supabase_configured ? "Connected" : "Not configured"}</span><small className="muted">Project configured via SUPABASE_URL</small></dd>
            <dt>Storage bucket</dt><dd><span className={`${badge(config?.storage_bucket_configured)}`}>{config?.storage_bucket_configured ? "invoices" : "Not configured"}</span><small className="muted">Private bucket</small></dd>
            <dt>OpenRouter</dt><dd><span className={`${badge(config?.openrouter_configured)}`}>{config?.openrouter_configured ? "Configured" : "Not configured"}</span><small className="muted">Set OPENROUTER_API_KEY and OPENROUTER_MODEL in backend .env</small></dd>
            <dt>n8n</dt><dd><span className="statusBadge statusNotConfigured">Not configured</span><small className="muted">Gmail intake webhook not set</small></dd>
          </dl>
        </section>
        <section className="reviewPanel" style={{padding:20}}>
          <h3 style={{margin:"0 0 14px 0",fontSize:15}}>Extraction provider</h3>
          <dl className="settingsList">
            <dt>Current provider</dt><dd>PyMuPDF (digital text only)</dd>
            <dt>AI extraction</dt><dd><span className={`${badge(config?.ai_extraction_enabled)}`}>{config?.ai_extraction_enabled ? "Enabled" : "Disabled"}</span><small className="muted">Set AI_EXTRACTION_ENABLED=true to enable</small></dd>
            <dt>OCR fallback</dt><dd><span className="statusBadge statusNotConfigured">Not implemented</span><small className="muted">No OCR adapter configured</small></dd>
          </dl>
        </section>
        <section className="reviewPanel" style={{padding:20}}>
          <h3 style={{margin:"0 0 14px 0",fontSize:15}}>Approval policy</h3>
          <dl className="settingsList">
            <dt>Default approval levels</dt><dd>1 level (configurable per entity)</dd>
            <dt>Segregation of duties</dt><dd>Enforced server-side</dd>
            <dt>Amount thresholds</dt><dd>Not configured</dd>
          </dl>
        </section>
        <section className="reviewPanel" style={{padding:20}}>
          <h3 style={{margin:"0 0 14px 0",fontSize:15}}>GST & tax</h3>
          <dl className="settingsList">
            <dt>GST validation</dt><dd>Format validation only (GSTIN regex)</dd>
            <dt>IRN/QR verification</dt><dd><span className="statusBadge statusNotConfigured">Not configured</span><small className="muted">Requires authorised GSP integration</small></dd>
            <dt>TDS rules</dt><dd>Not implemented</dd>
          </dl>
        </section>
        <section className="reviewPanel" style={{padding:20}}>
          <h3 style={{margin:"0 0 14px 0",fontSize:15}}>Tolerances</h3>
          <dl className="settingsList">
            <dt>Line price tolerance</dt><dd>±2% (default, not yet enforced)</dd>
            <dt>Line quantity tolerance</dt><dd>±5% (default, not yet enforced)</dd>
            <dt>Tax rounding tolerance</dt><dd>₹1 (default, not yet enforced)</dd>
          </dl>
        </section>
      </div>
      {error && (<div className="errorCard"><div className="errorIcon">!</div><strong>Failed to load configuration</strong><p>{error}</p></div>)}
      <div className="sectionHead" style={{marginTop:32}}><div><h3>Development mode</h3><p>Running in local development configuration.</p></div></div>
      <div className="reviewPanel" style={{padding:20,border:"1px solid var(--line)",background:"#fbfbff"}}>
        <div className="infoBox" style={{background:"#fbfbff",borderColor:"#e8eaff",margin:0}}><div className="infoIcon">⚙</div><p style={{margin:0,fontSize:12}}>This workspace is running with local development settings. Configure environment variables in <code>apps/api/.env</code> and <code>apps/web/.env.local</code> for production use. Secrets are never committed to version control.</p></div>
      </div>
    </Shell>
  );
}
