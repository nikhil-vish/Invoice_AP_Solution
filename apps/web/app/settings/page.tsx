"use client";

import { Shell } from "@/components/Shell";

export default function SettingsPage() {
  return (
    <Shell>
      <header className="topbar">
        <div>
          <div className="eyebrow">ACCOUNTS PAYABLE / SETTINGS</div>
          <h1>Settings</h1>
        </div>
      </header>

      <div className="sectionHead">
        <div>
          <h3>Workspace settings</h3>
          <p>Configure integrations, extraction provider, and approval rules.</p>
        </div>
      </div>

      <div className="settingsGrid">
        <section className="settingsCard">
          <h4>Integrations</h4>
          <dl className="settingsList">
            <dt>Supabase</dt>
            <dd>
              <span className="statusBadge statusConnected">Connected</span>
              <small className="muted">Project: tczihlegkpahhqsxgenk</small>
            </dd>
            <dt>Storage bucket</dt>
            <dd>
              <span className="statusBadge statusConnected">invoices</span>
              <small className="muted">Private bucket</small>
            </dd>
            <dt>OpenRouter</dt>
            <dd>
              <span className="statusBadge statusNotConfigured">Not configured</span>
              <small className="muted">Set OPENROUTER_API_KEY in backend .env</small>
            </dd>
            <dt>n8n</dt>
            <dd>
              <span className="statusBadge statusNotConfigured">Not configured</span>
              <small className="muted">Gmail intake webhook not set</small>
            </dd>
          </dl>
        </section>

        <section className="settingsCard">
          <h4>Extraction provider</h4>
          <dl className="settingsList">
            <dt>Current provider</dt>
            <dd>PyMuPDF (digital text only)</dd>
            <dt>AI extraction</dt>
            <dd>
              <span className="statusBadge statusNotConfigured">Disabled</span>
              <small className="muted">Set AI_EXTRACTION_ENABLED=true and OPENROUTER_API_KEY to enable</small>
            </dd>
            <dt>OCR fallback</dt>
            <dd>
              <span className="statusBadge statusNotConfigured">Not implemented</span>
              <small className="muted">No OCR adapter configured</small>
            </dd>
          </dl>
        </section>

        <section className="settingsCard">
          <h4>Approval policy</h4>
          <dl className="settingsList">
            <dt>Default approval levels</dt>
            <dd>1 level (configurable per entity)</dd>
            <dt>Segregation of duties</dt>
            <dd>Enforced server-side</dd>
            <dt>Amount thresholds</dt>
            <dd>Not configured</dd>
          </dl>
        </section>

        <section className="settingsCard">
          <h4>GST & tax</h4>
          <dl className="settingsList">
            <dt>GST validation</dt>
            <dd>Format validation only (GSTIN regex)</dd>
            <dt>IRN/QR verification</dt>
            <dd>
              <span className="statusBadge statusNotConfigured">Not configured</span>
              <small className="muted">Requires authorised GSP integration</small>
            </dd>
            <dt>TDS rules</dt>
            <dd>Not implemented</dd>
          </dl>
        </section>

        <section className="settingsCard">
          <h4>Tolerances</h4>
          <dl className="settingsList">
            <dt>Line price tolerance</dt>
            <dd>±2% (default, not yet enforced)</dd>
            <dt>Line quantity tolerance</dt>
            <dd>±5% (default, not yet enforced)</dd>
            <dt>Tax rounding tolerance</dt>
            <dd>₹1 (default, not yet enforced)</dd>
          </dl>
        </section>
      </div>

      <div className="sectionHead" style={{ marginTop: 32 }}>
        <div>
          <h3>Development mode</h3>
          <p>Running in local development configuration.</p>
        </div>
      </div>

      <div className="infoBox">
        <div className="infoIcon">⚙</div>
        <p>
          This workspace is running with local development settings. Configure environment variables in
          <code>apps/api/.env</code> and <code>apps/web/.env.local</code> for production use.
          Secrets are never committed to version control.
        </p>
      </div>
    </Shell>
  );
}