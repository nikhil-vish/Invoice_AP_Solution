"use client";

import { Shell } from "@/components/Shell";
import { useState, useEffect, useCallback } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface ExceptionInvoice {
  invoice_number: string;
  supplier_name: string;
}

interface ExceptionItem {
  id: string;
  invoice_id: string;
  exception_code: string;
  severity: string;
  status: string;
  description: string;
  owner_team: string | null;
  created_at: string;
  resolved_at: string | null;
  invoices: ExceptionInvoice;
}

interface ExceptionsResponse {
  exceptions: ExceptionItem[];
  total: number;
  page: number;
  page_size: number;
}

export default function ExceptionsPage() {
  const [exceptions, setExceptions] = useState<ExceptionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [severityFilter, setSeverityFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [confirm, setConfirm] = useState<{ id: string; action: string; value: string } | null>(null);
  const [selected, setSelected] = useState<ExceptionItem | null>(null);

  const fetchExceptions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ page: page.toString(), page_size: "20" });
      if (severityFilter) params.append("severity", severityFilter);
      if (statusFilter) params.append("status", statusFilter);
      const res = await fetch(`${API_BASE_URL}/api/v1/invoices/exceptions?${params.toString()}`);
      if (!res.ok) throw new Error("Failed to fetch exceptions");
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

  const openConfirm = (id: string, action: string) => setConfirm({ id, action, value: "" });
  const closeConfirm = () => setConfirm(null);

  const handleConfirmValue = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (confirm) setConfirm({ ...confirm, value: e.target.value });
  };

  const submitConfirm = async () => {
    if (!confirm) return;
    const { id, action, value } = confirm;
    const isResolve = action === "resolve";
    if (isResolve && !value.trim()) {
      setToast({ type: "error", message: "Resolution comment is required" });
      return;
    }
    setActionLoading({ ...actionLoading, [id]: true });
    try {
      if (isResolve) {
        const res = await fetch(`${API_BASE_URL}/api/v1/invoices/exceptions/${id}/resolve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ resolution_comment: value, actor_id: "current-user" }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: "Resolve failed" }));
          throw new Error(err.detail || "Resolve failed");
        }
        setExceptions(exceptions.map(e => e.id === id ? { ...e, status: "RESOLVED", resolved_at: new Date().toISOString() } : e));
        setSelected(prev => prev?.id === id ? { ...prev!, status: "RESOLVED", resolved_at: new Date().toISOString() } : prev);
        setToast({ type: "success", message: "Exception resolved successfully" });
      } else {
        const res = await fetch(`${API_BASE_URL}/api/v1/invoices/exceptions/${id}/assign`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ owner_team: value, actor_id: "current-user" }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: "Assign failed" }));
          throw new Error(err.detail || "Assign failed");
        }
        setExceptions(exceptions.map(e => e.id === id ? { ...e, owner_team: value, status: "IN_REVIEW" } : e));
        setSelected(prev => prev?.id === id ? { ...prev!, owner_team: value, status: "IN_REVIEW" } : prev);
        setToast({ type: "success", message: `Exception assigned to ${value}` });
      }
    } catch (err) {
      setToast({ type: "error", message: err instanceof Error ? err.message : "Action failed" });
    } finally {
      setActionLoading({ ...actionLoading, [id]: false });
      setConfirm(null);
    }
  };

  const dismissToast = () => setToast(null);

  const selectException = (exc: ExceptionItem) => setSelected(selected?.id === exc.id ? null : exc);

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

      {toast && (
        <div className={`errorCard ${toast.type === "success" ? "successCard" : ""}`}>
          <div className={`${toast.type === "success" ? "successIcon" : "errorIcon"}`}>
            {toast.type === "success" ? "✓" : "!"}
          </div>
          <strong>{toast.type === "success" ? "Success" : "Error"}</strong>
          <p>{toast.message}</p>
          <button className="btnGreen" onClick={dismissToast} style={{ marginTop: 12, padding: "6px 14px", fontSize: 12 }}>
            Dismiss
          </button>
        </div>
      )}

      {error && (
        <div className="errorCard">
          <div className="errorIcon">!</div>
          <strong>Failed to load exceptions</strong>
          <p>{error}</p>
          <button className="btnGreen" onClick={fetchExceptions}>Retry</button>
        </div>
      )}

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
                <tr
                  key={exc.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => selectException(exc)}
                  className={selected?.id === exc.id ? "selectedRow" : ""}
                >
                  <td><code>{exc.exception_code}</code></td>
                  <td>{exc.invoices.invoice_number || exc.invoice_id.slice(0, 8) + "…"}</td>
                  <td>{exc.invoices.supplier_name}</td>
                  <td>
                    <span className={`statusBadge ${getSeverityColor(exc.severity)}`}>{exc.severity}</span>
                  </td>
                  <td>
                    <span className={`statusBadge ${getStatusColor(exc.status)}`}>{exc.status}</span>
                  </td>
                  <td className="truncate" style={{ maxWidth: 300 }}>{exc.description}</td>
                  <td>{new Date(exc.created_at).toLocaleDateString()}</td>
                  <td>
                    <div style={{ display: "flex", gap: 6, flexDirection: "column" }}>
                      {exc.status !== "RESOLVED" && exc.status !== "CLOSED" && (
                        <>
                          <button
                            className="btnOutline"
                            disabled={actionLoading[exc.id]}
                            onClick={(e) => { e.stopPropagation(); openConfirm(exc.id, "assign"); }}
                            style={{ fontSize: 11, padding: "3px 8px" }}
                          >
                            Assign
                          </button>
                          <button
                            className="btnOutline"
                            disabled={actionLoading[exc.id] || exc.status === "RESOLVED"}
                            onClick={(e) => { e.stopPropagation(); openConfirm(exc.id, "resolve"); }}
                            style={{ fontSize: 11, padding: "3px 8px" }}
                          >
                            Resolve
                          </button>
                        </>
                      )}
                      {exc.status === "RESOLVED" && (
                        <span style={{ fontSize: 11, color: "var(--muted)" }}>Resolved</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="reviewPanel full" style={{ marginTop: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <h3 style={{ margin: 0 }}>Exception Detail</h3>
            <button className="btnOutline" onClick={() => setSelected(null)} style={{ padding: "6px 14px", fontSize: 12 }}>
              Close
            </button>
          </div>
          <div className="fieldList">
            <div className="fieldRow">
              <label>Exception Code</label>
              <span><code>{selected.exception_code}</code></span>
            </div>
            <div className="fieldRow">
              <label>Invoice</label>
              <span>{selected.invoices.invoice_number || selected.invoice_id.slice(0, 8) + "…"}</span>
            </div>
            <div className="fieldRow">
              <label>Supplier</label>
              <span>{selected.invoices.supplier_name}</span>
            </div>
            <div className="fieldRow">
              <label>Severity</label>
              <span className={`statusBadge ${getSeverityColor(selected.severity)}`}>{selected.severity}</span>
            </div>
            <div className="fieldRow">
              <label>Status</label>
              <span className={`statusBadge ${getStatusColor(selected.status)}`}>{selected.status}</span>
            </div>
            <div className="fieldRow">
              <label>Owner Team</label>
              <span>{selected.owner_team || "—"}</span>
            </div>
            <div className="fieldRow">
              <label>Description</label>
              <span style={{ whiteSpace: "pre-wrap" }}>{selected.description}</span>
            </div>
            <div className="fieldRow">
              <label>Created At</label>
              <span>{new Date(selected.created_at).toLocaleString()}</span>
            </div>
            {selected.resolved_at && (
              <div className="fieldRow">
                <label>Resolved At</label>
                <span>{new Date(selected.resolved_at).toLocaleString()}</span>
              </div>
            )}
          </div>

          {selected.status !== "RESOLVED" && selected.status !== "CLOSED" && (
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--line)" }}>
              <h4 style={{ margin: "0 0 12px 0", fontSize: 13 }}>Take Action</h4>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button
                  className="btnOutline"
                  disabled={actionLoading[selected.id]}
                  onClick={() => openConfirm(selected.id, "assign")}
                  style={{ padding: "8px 16px", fontSize: 13 }}
                >
                  {actionLoading[selected.id] ? "Assigning…" : "Assign to Team"}
                </button>
                <button
                  className="btnOutline"
                  disabled={actionLoading[selected.id]}
                  onClick={() => openConfirm(selected.id, "resolve")}
                  style={{ padding: "8px 16px", fontSize: 13 }}
                >
                  {actionLoading[selected.id] ? "Resolving…" : "Resolve Exception"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {confirm && (
        <div className="reviewPanel full" style={{ marginTop: 20, position: "fixed", top: 100, left: "50%", transform: "translateX(-50%)", width: "min(500px, 90vw)", zIndex: 50, background: "#fff", border: "1px solid var(--line)", borderRadius: 10, padding: 24, boxShadow: "0 8px 32px rgba(0,0,0,0.15)" }}>
          <h3 style={{ margin: "0 0 16px 0" }}>
            {confirm.action === "assign" ? "Confirm Assign" : "Confirm Resolve"}
          </h3>
          <p style={{ color: "var(--muted)", marginBottom: 16 }}>
            This will {confirm.action === "assign" ? "assign" : "resolve"} exception for invoice{" "}
            <strong>{exceptions.find(e => e.id === confirm.id)?.invoices.invoice_number || "unknown"}</strong>.
          </p>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", marginBottom: 6, fontSize: 12, color: "var(--ink)" }}>
              {confirm.action === "assign" ? "Owner Team" : "Resolution Comment"} <span style={{ color: "#c0392b" }}>*</span>
            </label>
            <input
              type="text"
              value={confirm.value}
              onChange={handleConfirmValue}
              placeholder={confirm.action === "assign" ? "e.g. tax-team, procurement" : "Enter resolution comment…"}
              className="inputField"
            />
          </div>
          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
            <button className="btnOutline" onClick={closeConfirm} style={{ padding: "8px 16px" }}>
              Cancel
            </button>
            <button
              className="btnGreen"
              disabled={actionLoading[confirm.id]}
              onClick={submitConfirm}
              style={{ padding: "8px 16px" }}
            >
              {actionLoading[confirm.id] ? "Processing…" : "Confirm"}
            </button>
          </div>
        </div>
      )}

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
