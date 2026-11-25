"use client";

import { Shell } from "@/components/Shell";
import { useState, useEffect, useCallback } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface Exception {
  id: string;
  invoice_id: string;
  invoice_number: string;
  supplier_name: string;
  exception_code: string;
  severity: string;
  status: string;
  description: string;
  created_at: string;
}

interface ExceptionsResponse {
  exceptions: Exception[];
  total: number;
}

export default function ExceptionsPage() {
  const [exceptions, setExceptions] = useState<Exception[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [severityFilter, setSeverityFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const fetchExceptions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: "20",
      });
      if (severityFilter) params.append("severity", severityFilter);
      if (statusFilter) params.append("status", statusFilter);

      const res = await fetch(`${API_BASE_URL}/api/v1/exceptions?${params.toString()}`);
      if (!res.ok) {
        throw new Error("Failed to fetch exceptions");
      }
      const data: ExceptionsResponse = await res.json();
      setExceptions(data.exceptions);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load exceptions");
    } finally {
      setLoading(false);
    }
  }, [page, severityFilter, statusFilter]);

  useEffect(() => {
    fetchExceptions();
  }, [fetchExceptions]);

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "CRITICAL": return "severityCritical";
      case "HIGH": return "severityHigh";
      case "MEDIUM": return "severityMedium";
      case "LOW": return "severityLow";
      default: return "";
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "OPEN": return "statusOpen";
      case "AWAITING_RESPONSE": return "statusAwaiting";
      case "IN_REVIEW": return "statusInReview";
      case "RESOLVED": return "statusResolved";
      case "ESCALATED": return "statusEscalated";
      case "CLOSED": return "statusClosed";
      default: return "";
    }
  };

  if (loading && exceptions.length === 0) {
    return (
      <Shell>
        <header className="topbar">
          <div>
            <div className="eyebrow">ACCOUNTS PAYABLE / EXCEPTIONS</div>
            <h1>Exception Centre</h1>
          </div>
        </header>
        <div className="emptyState">
          <div className="emptyIcon">↻</div>
          <strong>Loading exceptions…</strong>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <header className="topbar">
        <div>
          <div className="eyebrow">ACCOUNTS PAYABLE / EXCEPTIONS</div>
          <h1>Exception Centre</h1>
        </div>
      </header>

      <div className="filterBar">
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="filterSelect"
        >
          <option value="">All severities</option>
          <option value="CRITICAL">Critical</option>
          <option value="HIGH">High</option>
          <option value="MEDIUM">Medium</option>
          <option value="LOW">Low</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="filterSelect"
        >
          <option value="">All statuses</option>
          <option value="OPEN">Open</option>
          <option value="AWAITING_RESPONSE">Awaiting Response</option>
          <option value="IN_REVIEW">In Review</option>
          <option value="RESOLVED">Resolved</option>
          <option value="ESCALATED">Escalated</option>
          <option value="CLOSED">Closed</option>
        </select>
      </div>

      {error && (
        <div className="errorCard">
          <div className="errorIcon">!</div>
          <strong>Failed to load exceptions</strong>
          <p>{error}</p>
          <button className="btnGreen" onClick={fetchExceptions}>Retry</button>
        </div>
      )}

      <div className="tableWrap">
        <table className="dataTable">
          <thead>
            <tr>
              <th>Exception</th>
              <th>Invoice</th>
              <th>Supplier</th>
              <th>Severity</th>
              <th>Status</th>
              <th>Description</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {exceptions.length === 0 ? (
              <tr>
                <td colSpan={8} className="emptyRow">
                  {error ? "Failed to load exceptions" : "No exceptions found."}
                </td>
              </tr>
            ) : (
              exceptions.map((exc) => (
                <tr key={exc.id}>
                  <td><code>{exc.exception_code}</code></td>
                  <td>{exc.invoice_number || exc.invoice_id.slice(0, 8) + "…"}</td>
                  <td>{exc.supplier_name}</td>
                  <td>
                    <span className={`statusBadge ${getSeverityColor(exc.severity)}`}>
                      {exc.severity}
                    </span>
                  </td>
                  <td>
                    <span className={`statusBadge ${getStatusColor(exc.status)}`}>
                      {exc.status}
                    </span>
                  </td>
                  <td className="truncate" style={{ maxWidth: 300 }}>{exc.description}</td>
                  <td>{new Date(exc.created_at).toLocaleDateString()}</td>
                  <td>
                    <button className="btnOutline" disabled style={{ fontSize: 12, padding: "4px 8px" }}>
                      View
                    </button>
                  </td>
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