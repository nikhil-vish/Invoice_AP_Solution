"use client";

import { Shell } from "@/components/Shell";
import { useState, useEffect, useCallback } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface DashboardMetrics {
  total_invoices: number;
  invoices_received: number;
  queued_processing_runs: number;
  invoices_awaiting_review: number;
}

export default function Home() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/invoices/dashboard/metrics`);
      if (!res.ok) throw new Error("Failed to fetch metrics");
      const data: DashboardMetrics = await res.json();
      setMetrics(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load metrics");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  const formatMetric = (value: number | null | undefined, label: string) => {
    if (value === null || value === undefined) return "Not available";
    return String(value);
  };

  if (loading) {
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
            <p>Loading workspace metrics…</p>
          </div>
          <div className="introIcon">↗</div>
        </section>

        <div className="emptyState">
          <div className="emptyIcon">↻</div>
          <strong>Loading metrics…</strong>
        </div>
      </Shell>
    );
  }

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

      {error && (
        <div className="errorCard">
          <div className="errorIcon">!</div>
          <strong>Failed to load metrics</strong>
          <p>{error}</p>
        </div>
      )}

      <section className="intro">
        <div>
          <div className="eyebrow light">INVOICE OPERATIONS</div>
          <h2>Good afternoon</h2>
          <p>Your invoice processing workspace metrics below reflect live data from the backend.</p>
        </div>
        <div className="introIcon">↗</div>
      </section>

      <div className="sectionHead">
        <div>
          <h3>Processing overview</h3>
          <p>Live operational metrics from processing records.</p>
        </div>
        <span className="period">All time ▾</span>
      </div>

      <div className="metricGrid">
        <article className="metric" key="invoices-received">
          <span>Invoices received</span>
          <strong>{formatMetric(metrics?.total_invoices, "Invoices received")}</strong>
          <small>Converted business invoices</small>
        </article>
        <article className="metric" key="ready-for-approval">
          <span>Invoices received (RECEIVED)</span>
          <strong>{formatMetric(metrics?.invoices_received, "Received")}</strong>
          <small>Awaiting validation engine</small>
        </article>
        <article className="metric" key="open-exceptions">
          <span>Queued processing runs</span>
          <strong>{formatMetric(metrics?.queued_processing_runs, "Queued runs")}</strong>
          <small>Processing not yet started</small>
        </article>
        <article className="metric" key="pending-approvals">
          <span>Invoices awaiting review</span>
          <strong>{formatMetric(metrics?.invoices_awaiting_review, "Awaiting review")}</strong>
          <small>Saved drafts ready for conversion</small>
        </article>
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
        <p>Convert a draft to create an invoice and start a processing run.</p>
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
