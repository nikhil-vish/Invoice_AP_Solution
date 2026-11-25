"use client";

import { Shell } from "@/components/Shell";

const metrics = [
  { label: "Invoices received", value: "—", note: "Connected data will appear here" },
  { label: "Ready for approval", value: "—", note: "Awaiting validation engine" },
  { label: "Open exceptions", value: "—", note: "No demo data seeded yet" },
  { label: "Pending approvals", value: "—", note: "Approval workflow not connected" },
];

export default function Home() {
  return (
    <Shell>
      <header className="topbar">
        <div>
          <div className="eyebrow">ACCOUNTS PAYABLE / WORKSPACE</div>
          <h1>Overview</h1>
        </div>
        <div className="userPill">
          <span className="dot" /> Development mode
        </div>
      </header>

      <section className="intro">
        <div>
          <div className="eyebrow light">INVOICE OPERATIONS</div>
          <h2>Good afternoon</h2>
          <p>Your invoice processing workspace is being set up. Connect the data layer to start processing real invoices.</p>
        </div>
        <div className="introIcon">↗</div>
      </section>

      <div className="sectionHead">
        <div>
          <h3>Processing overview</h3>
          <p>Live operational metrics will populate from processing records.</p>
        </div>
        <span className="period">All time ▾</span>
      </div>

      <div className="metricGrid">
        {metrics.map((m) => (
          <article className="metric" key={m.label}>
            <span>{m.label}</span>
            <strong>{m.value}</strong>
            <small>{m.note}</small>
          </article>
        ))}
      </div>

      <div className="sectionHead lower">
        <div>
          <h3>Recent processing runs</h3>
          <p>Every execution will be recorded with its stage history and outcome.</p>
        </div>
      </div>

      <div className="emptyState">
        <div className="emptyIcon">▤</div>
        <strong>No processing runs yet</strong>
        <p>Once the API, database and invoice intake are connected, your processing history will appear here.</p>
      </div>

      <div className="intakeAction" style={{ marginTop: 24 }}>
        <a href="/upload" className="btnGreen" style={{ textDecoration: "none", display: "inline-block" }}>
          ▤ Upload Invoice
        </a>
      </div>

      <footer>INVOICE INTELLIGENCE WORKBENCH <span>STARTER · v0.1.0</span></footer>
    </Shell>
  );
}