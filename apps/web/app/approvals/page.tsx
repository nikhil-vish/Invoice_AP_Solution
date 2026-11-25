"use client";

import { Shell } from "@/components/Shell";
import { useState, useEffect, useCallback } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface ApprovalTask {
  id: string;
  invoice_id: string;
  invoice_number: string;
  supplier_name: string;
  total_amount: number;
  currency: string;
  approval_level: number;
  status: string;
  assigned_at: string;
  requester: string;
}

interface ApprovalsResponse {
  approvals: ApprovalTask[];
  total: number;
}

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<ApprovalTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const fetchApprovals = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: "20",
      });
      const res = await fetch(`${API_BASE_URL}/api/v1/approvals?${params.toString()}`);
      if (!res.ok) {
        throw new Error("Failed to fetch approvals");
      }
      const data: ApprovalsResponse = await res.json();
      setApprovals(data.approvals);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load approvals");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchApprovals();
  }, [fetchApprovals]);

  const formatCurrency = (amount: number, currency: string) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: currency || "INR",
      minimumFractionDigits: 2,
    }).format(amount);
  };

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

      {error && (
        <div className="errorCard">
          <div className="errorIcon">!</div>
          <strong>Failed to load approvals</strong>
          <p>{error}</p>
          <button className="btnGreen" onClick={fetchApprovals}>Retry</button>
        </div>
      )}

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
              <th>Requester</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {approvals.length === 0 ? (
              <tr>
                <td colSpan={8} className="emptyRow">
                  {error ? "Failed to load approvals" : "No pending approvals."}
                </td>
              </tr>
            ) : (
              approvals.map((app) => (
                <tr key={app.id}>
                  <td><strong>{app.invoice_number || "—"}</strong></td>
                  <td>{app.supplier_name}</td>
                  <td>{formatCurrency(app.total_amount, app.currency)}</td>
                  <td>{app.approval_level}</td>
                  <td>
                    <span className={`statusBadge ${getStatusColor(app.status)}`}>
                      {app.status}
                    </span>
                  </td>
                  <td>{new Date(app.assigned_at).toLocaleString()}</td>
                  <td>{app.requester}</td>
                  <td>
                    <div style={{ display: "flex", gap: 8 }}>
                      <button className="btnGreen" style={{ fontSize: 12, padding: "4px 8px" }} disabled>
                        Approve
                      </button>
                      <button className="btnOutline" style={{ fontSize: 12, padding: "4px 8px" }} disabled>
                        Reject
                      </button>
                    </div>
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