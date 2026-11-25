"use client";

import { Shell } from "@/components/Shell";
import { useState, useEffect, useCallback } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface ProcessingRun {
  id: string;
  invoice_id: string;
  run_number: number;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  triggered_by: string;
  summary: Record<string, unknown>;
}

interface RunsResponse {
  runs: ProcessingRun[];
  total: number;
}

export default function ProcessingPage() {
  const [runs, setRuns] = useState<ProcessingRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const fetchRuns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: "20",
      });
      const res = await fetch(`${API_BASE_URL}/api/v1/invoices/runs?${params.toString()}`);
      if (!res.ok) {
        throw new Error("Failed to fetch processing runs");
      }
      const data: RunsResponse = await res.json();
      setRuns(data.runs);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load processing runs");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchRuns();
  }, [fetchRuns]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "COMPLETED": return "statusApproved";
      case "RUNNING": return "statusRunning";
      case "FAILED": return "statusRejected";
      case "WAITING": return "statusOnHold";
      case "QUEUED": return "statusPending";
      default: return "";
    }
  };

  const formatDuration = (started: string | null, completed: string | null) => {
    if (!started) return "—";
    const start = new Date(started);
    const end = completed ? new Date(completed) : new Date();
    const diff = end.getTime() - start.getTime();
    const seconds = Math.floor(diff / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m ${seconds % 60}s`;
  };

  if (loading && runs.length === 0) {
    return (
      <Shell>
        <header className="topbar">
          <div>
            <div className="eyebrow">ACCOUNTS PAYABLE / PROCESSING</div>
            <h1>Live Processing</h1>
          </div>
        </header>
        <div className="emptyState">
          <div className="emptyIcon">↻</div>
          <strong>Loading processing runs…</strong>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <header className="topbar">
        <div>
          <div className="eyebrow">ACCOUNTS PAYABLE / PROCESSING</div>
          <h1>Live Processing</h1>
        </div>
      </header>

      {error && (
        <div className="errorCard">
          <div className="errorIcon">!</div>
          <strong>Failed to load processing runs</strong>
          <p>{error}</p>
          <button className="btnGreen" onClick={fetchRuns}>Retry</button>
        </div>
      )}

      <div className="sectionHead">
        <div>
          <h3>Processing runs</h3>
          <p>Active and recent runs with stage timeline and outcomes.</p>
        </div>
      </div>

      <div className="tableWrap">
        <table className="dataTable">
          <thead>
            <tr>
              <th>Run ID</th>
              <th>Invoice</th>
              <th>Run #</th>
              <th>Status</th>
              <th>Triggered by</th>
              <th>Duration</th>
              <th>Started</th>
              <th>Completed</th>
            </tr>
          </thead>
          <tbody>
            {runs.length === 0 ? (
              <tr>
                <td colSpan={8} className="emptyRow">
                  {error ? "Failed to load runs" : "No processing runs yet. Upload an invoice to start processing."}
                </td>
              </tr>
            ) : (
              runs.map((run) => (
                <tr key={run.id}>
                  <td><code>{run.id.slice(0, 8)}…</code></td>
                  <td>{run.invoice_id.slice(0, 8)}…</td>
                  <td>{run.run_number}</td>
                  <td>
                    <span className={`statusBadge ${getStatusColor(run.status)}`}>
                      {run.status}
                    </span>
                  </td>
                  <td>{run.triggered_by}</td>
                  <td>{formatDuration(run.started_at, run.completed_at)}</td>
                  <td>{run.started_at ? new Date(run.started_at).toLocaleString() : "—"}</td>
                  <td>{run.completed_at ? new Date(run.completed_at).toLocaleString() : "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {total > 20 && (
        <div className="pagination">
          <button
            className="btnOutline"
            disabled={page === 1}
            onClick={() => setPage(p => p - 1)}
          >
            ← Previous
          </button>
          <span className="pageInfo">
            Page {page} of {Math.ceil(total / 20)} ({total} total)
          </span>
          <button
            className="btnOutline"
            disabled={page * 20 >= total}
            onClick={() => setPage(p => p + 1)}
          >
            Next →
          </button>
        </div>
      )}
    </Shell>
  );
}