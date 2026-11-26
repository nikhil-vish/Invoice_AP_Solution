"use client";

import { Shell } from "@/components/Shell";
import { useState, useEffect, useCallback } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

interface ApprovalInvoice {
  invoice_number: string;
  supplier_legal_name: string | null;
  total_amount: number;
  currency: string;
}

interface ApprovalTask {
  id: string;
  invoice_id: string;
  approval_level: number;
  status: string;
  assigned_at: string;
  requester: string;
  invoices: ApprovalInvoice;
}

interface ApprovalsResponse {
  approvals: ApprovalTask[];
  total: number;
  page: number;
  page_size: number;
}

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<ApprovalTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [toast, setToast] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({});
  const [confirm, setConfirm] = useState<{ id: string; action: string; comment: string } | null>(null);
  const [selected, setSelected] = useState<ApprovalTask | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => setToken(window.localStorage.getItem("supabase_access_token")), []);

  const signIn = async () => {
    if (!SUPABASE_URL || !SUPABASE_ANON_KEY) { setToast({ type: "error", message: "Configure NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY." }); return; }
    try {
      const res = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, { method: "POST", headers: { "apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
      if (!res.ok) throw new Error("Sign-in failed."); const session = await res.json(); window.localStorage.setItem("supabase_access_token", session.access_token); setToken(session.access_token); setPassword(""); setToast({ type: "success", message: "Signed in as reviewer." });
    } catch (err) { setToast({ type: "error", message: err instanceof Error ? err.message : "Sign-in failed." }); }
  };

  const fetchApprovals = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ page: page.toString(), page_size: "20" });
      if (statusFilter) params.append("status", statusFilter);
      const res = await fetch(`${API_BASE_URL}/api/v1/invoices/approvals?${params.toString()}`);
      if (!res.ok) throw new Error("Failed to fetch approvals");
      const data: ApprovalsResponse = await res.json();
      setApprovals(data.approvals);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load approvals");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    fetchApprovals();
  }, [fetchApprovals]);

  const formatCurrency = (amount: number, currency: string) =>
    new Intl.NumberFormat("en-IN", { style: "currency", currency: currency || "INR", minimumFractionDigits: 2 }).format(amount);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "PENDING": return "statusPending";
      case "APPROVED": return "statusApproved";
      case "REJECTED": return "statusRejected";
      case "REASSIGNED": return "statusReassigned";
      case "CANCELLED": return "statusCancelled";
      default: return "";
    }
  };

  const openConfirm = (id: string, action: string) => setConfirm({ id, action, comment: "" });
  const closeConfirm = () => setConfirm(null);

  const handleConfirmComment = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (confirm) setConfirm({ ...confirm, comment: e.target.value });
  };

  const submitConfirm = async () => {
    if (!confirm) return;
    if (!token) { setToast({ type: "error", message: "Sign in with Supabase Auth before deciding." }); return; }
    const { id, action, comment } = confirm;
    const requiresComment = action === "REJECT" || action === "RETURN_FOR_INFORMATION";
    if (requiresComment && !comment.trim()) {
      setToast({ type: "error", message: `Comment is required for ${action} action` });
      return;
    }
    setActionLoading({ ...actionLoading, [id]: true });
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/invoices/approvals/${id}/action`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ action, comment: comment || undefined }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Action failed" }));
        throw new Error(err.detail || "Action failed");
      }
      const newStatus = action === "APPROVE" ? "APPROVED" : action === "REJECT" ? "REJECTED" : "REASSIGNED";
      setApprovals(approvals.map(a => a.id === id ? { ...a, status: newStatus } : a));
      setSelected(prev => prev?.id === id ? { ...prev!, status: newStatus } : prev);
      setToast({ type: "success", message: `Approval ${action.toLowerCase()}d successfully` });
    } catch (err) {
      setToast({ type: "error", message: err instanceof Error ? err.message : "Action failed" });
    } finally {
      setActionLoading({ ...actionLoading, [id]: false });
      setConfirm(null);
    }
  };

  const dismissToast = () => setToast(null);

  const selectApproval = (app: ApprovalTask) => setSelected(selected?.id === app.id ? null : app);

  if (loading && approvals.length === 0) {
    return (
      <Shell>
        <header className="topbar">
          <div>
            <div className="eyebrow">ACCOUNTS PAYABLE / APPROVALS</div>
            <h1>Approvals</h1>
          </div>
        </header>
        <div className="emptyState">
          <div className="emptyIcon">↻</div>
          <strong>Loading approvals…</strong>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <header className="topbar">
        <div>
          <div className="eyebrow">ACCOUNTS PAYABLE / APPROVALS</div>
          <h1>Approvals</h1>
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
          <strong>Failed to load approvals</strong>
          <p>{error}</p>
          <button className="btnGreen" onClick={fetchApprovals}>Retry</button>
        </div>
      )}

      {!token && <div className="reviewPanel full" style={{ marginBottom: 16 }}><h3>Reviewer sign in</h3><p className="muted">A verified Supabase Auth session is required for final decisions.</p><input className="inputField" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} /><input className="inputField" type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} style={{ marginTop: 8 }} /><button className="btnGreen" onClick={signIn} style={{ marginTop: 8 }}>Sign in</button></div>}

      <div className="filterBar">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="filterSelect"
        >
          <option value="">All statuses</option>
          <option value="PENDING">Pending</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
          <option value="REASSIGNED">Returned for Info</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="sectionHead">
        <div>
          <h3>Pending approval queue</h3>
          <p>Invoices awaiting human approval decision.</p>
        </div>
      </div>

      <div className="tableWrap">
        <table className="dataTable">
          <thead>
            <tr>
              <th>Invoice #</th>
              <th>Supplier</th>
              <th>Amount</th>
              <th>Level</th>
              <th>Status</th>
              <th>Assigned</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {approvals.length === 0 ? (
              <tr>
                <td colSpan={7} className="emptyRow">
                  {error ? "Failed to load approvals" : "No pending approvals."}
                </td>
              </tr>
            ) : (
              approvals.map((app) => (
                <tr
                  key={app.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => selectApproval(app)}
                  className={selected?.id === app.id ? "selectedRow" : ""}
                >
                  <td><strong>{app.invoices.invoice_number || "—"}</strong></td>
                  <td>{app.invoices.supplier_legal_name || "—"}</td>
                  <td>{formatCurrency(app.invoices.total_amount, app.invoices.currency)}</td>
                  <td>{app.approval_level}</td>
                  <td>
                    <span className={`statusBadge ${getStatusColor(app.status)}`}>{app.status}</span>
                  </td>
                  <td>{new Date(app.assigned_at).toLocaleString()}</td>
                  <td>
                    <div style={{ display: "flex", gap: 6 }}>
                      <button
                        className="btnOutline"
                        disabled={app.status !== "PENDING" || actionLoading[app.id]}
                        onClick={(e) => { e.stopPropagation(); openConfirm(app.id, "APPROVE"); }}
                        style={{ fontSize: 11, padding: "3px 8px" }}
                      >
                        Approve
                      </button>
                      <button
                        className="btnOutline"
                        disabled={app.status !== "PENDING" || actionLoading[app.id]}
                        onClick={(e) => { e.stopPropagation(); openConfirm(app.id, "REJECT"); }}
                        style={{ fontSize: 11, padding: "3px 8px" }}
                      >
                        Reject
                      </button>
                      <button
                        className="btnOutline"
                        disabled={app.status !== "PENDING" || actionLoading[app.id]}
                        onClick={(e) => { e.stopPropagation(); openConfirm(app.id, "RETURN_FOR_INFORMATION"); }}
                        style={{ fontSize: 11, padding: "3px 8px" }}
                      >
                        Return
                      </button>
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
            <h3 style={{ margin: 0 }}>Approval Detail</h3>
            <button className="btnOutline" onClick={() => setSelected(null)} style={{ padding: "6px 14px", fontSize: 12 }}>
              Close
            </button>
          </div>
          <div className="fieldList">
            <div className="fieldRow">
              <label>Invoice #</label>
              <span>{selected.invoices.invoice_number || "—"}</span>
            </div>
            <div className="fieldRow">
              <label>Supplier</label>
              <span>{selected.invoices.supplier_legal_name || "—"}</span>
            </div>
            <div className="fieldRow">
              <label>Amount</label>
              <span>{formatCurrency(selected.invoices.total_amount, selected.invoices.currency)}</span>
            </div>
            <div className="fieldRow">
              <label>Approval Level</label>
              <span>{selected.approval_level}</span>
            </div>
            <div className="fieldRow">
              <label>Status</label>
              <span className={`statusBadge ${getStatusColor(selected.status)}`}>{selected.status}</span>
            </div>
            <div className="fieldRow">
              <label>Assigned At</label>
              <span>{new Date(selected.assigned_at).toLocaleString()}</span>
            </div>
            <div className="fieldRow">
              <label>Requester</label>
              <span>{selected.requester}</span>
            </div>
          </div>

          {selected.status === "PENDING" && (
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--line)" }}>
              <h4 style={{ margin: "0 0 12px 0", fontSize: 13 }}>Take Action</h4>
              <div style={{ display: "flex", gap: 10 }}>
                <button
                  className="btnGreen"
                  disabled={actionLoading[selected.id]}
                  onClick={() => openConfirm(selected.id, "APPROVE")}
                  style={{ padding: "8px 16px", fontSize: 13 }}
                >
                  {actionLoading[selected.id] ? "Approving…" : "Approve"}
                </button>
                <button
                  className="btnOutline"
                  disabled={actionLoading[selected.id]}
                  onClick={() => openConfirm(selected.id, "REJECT")}
                  style={{ padding: "8px 16px", fontSize: 13 }}
                >
                  {actionLoading[selected.id] ? "Rejecting…" : "Reject"}
                </button>
                <button
                  className="btnOutline"
                  disabled={actionLoading[selected.id]}
                  onClick={() => openConfirm(selected.id, "RETURN_FOR_INFORMATION")}
                  style={{ padding: "8px 16px", fontSize: 13 }}
                >
                  {actionLoading[selected.id] ? "Returning…" : "Return for Info"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {confirm && (
        <div className="reviewPanel full" style={{ marginTop: 20, position: "fixed", top: 100, left: "50%", transform: "translateX(-50%)", width: "min(500px, 90vw)", zIndex: 50, background: "#fff", border: "1px solid var(--line)", borderRadius: 10, padding: 24, boxShadow: "0 8px 32px rgba(0,0,0,0.15)" }}>
          <h3 style={{ margin: "0 0 16px 0" }}>
            {confirm.action === "APPROVE" ? "Confirm Approve" : confirm.action === "REJECT" ? "Confirm Reject" : "Confirm Return for Information"}
          </h3>
          <p style={{ color: "var(--muted)", marginBottom: 16 }}>
            This will {confirm.action.toLowerCase()} the approval for invoice{" "}
            <strong>{approvals.find(a => a.id === confirm.id)?.invoices.invoice_number || "unknown"}</strong>.
          </p>
          {(confirm.action === "REJECT" || confirm.action === "RETURN_FOR_INFORMATION") && (
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", marginBottom: 6, fontSize: 12, color: "var(--ink)" }}>
                Decision Comment <span style={{ color: "#c0392b" }}>*</span>
              </label>
              <input
                type="text"
                value={confirm.comment}
                onChange={handleConfirmComment}
                placeholder="Enter your comment…"
                className="inputField"
              />
            </div>
          )}
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
