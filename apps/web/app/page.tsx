const metrics = [
  { label: "Invoices received", value: "—", note: "Connected data will appear here" },
  { label: "Ready for approval", value: "—", note: "Awaiting validation engine" },
  { label: "Open exceptions", value: "—", note: "No demo data seeded yet" },
  { label: "Pending approvals", value: "—", note: "Approval workflow not connected" },
];

export default function Home() {
  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand"><div className="brandMark">I</div><div><strong>Invoice Intelligence</strong><span>AP WORKSPACE</span></div></div>
        <div className="navLabel">WORKSPACE</div>
        <a className="navItem active">▦ <span>Overview</span></a>
        <a className="navItem">▤ <span>All invoices</span></a>
        <a className="navItem">⌁ <span>Live processing</span></a>
        <a className="navItem">⚑ <span>Exception centre</span></a>
        <a className="navItem">✓ <span>Approvals</span></a>
        <div className="navLabel second">CONFIGURATION</div>
        <a className="navItem">▣ <span>Suppliers</span></a>
        <a className="navItem">⚙ <span>Settings</span></a>
        <div className="sidebarFoot">Development workspace<br/><span>Local environment</span></div>
      </aside>
      <section className="content">
        <header className="topbar"><div><div className="eyebrow">ACCOUNTS PAYABLE / WORKSPACE</div><h1>Overview</h1></div><div className="userPill"><span className="dot"/> Development mode</div></header>
        <section className="intro"><div><div className="eyebrow light">INVOICE OPERATIONS</div><h2>Good afternoon</h2><p>Your invoice processing workspace is being set up. Connect the data layer to start processing real invoices.</p></div><div className="introIcon">↗</div></section>
        <div className="sectionHead"><div><h3>Processing overview</h3><p>Live operational metrics will populate from processing records.</p></div><span className="period">All time ▾</span></div>
        <div className="metricGrid">{metrics.map((m) => <article className="metric" key={m.label}><span>{m.label}</span><strong>{m.value}</strong><small>{m.note}</small></article>)}</div>
        <div className="sectionHead lower"><div><h3>Recent processing runs</h3><p>Every execution will be recorded with its stage history and outcome.</p></div></div>
        <div className="emptyState"><div className="emptyIcon">▤</div><strong>No processing runs yet</strong><p>Once the API, database and invoice intake are connected, your processing history will appear here.</p></div>
        <footer>INVOICE INTELLIGENCE WORKBENCH <span>STARTER · v0.1.0</span></footer>
      </section>
    </main>
  );
}
