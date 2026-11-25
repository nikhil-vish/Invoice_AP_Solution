"use client";

import { Shell } from "@/components/Shell";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface InvoiceSummary {
  id: string;
  invoice_number: string;
  invoice_date: string;
  supplier_name: string;
  supplier_gstin: string;
  total_amount: number;
  currency: string;
  processing_status: string;
  approval_status: string;
  created_at: string;
}

interface InvoicesResponse {
  invoices: InvoiceSummary[];
  total: number;
  page: number;
  page_size: number;
}

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<InvoiceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: "20",
      });
      if (search) params.append("search", search);
      if (statusFilter) params.append("status", statusFilter);

      const res = await fetch(`${API_BASE_URL}/api/v1/invoices?${params.toString()}`);
      if (!res.ok) {
        throw new Error("Failed to fetch invoices");
      }
      const data: InvoicesResponse = await res.json();
      setInvoices(data.invoices);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load invoices");
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter]);

  useEffect(() => {
    fetchInvoices();
  }, [fetchInvoices]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "APPROVED": return "statusApproved";
      case "PENDING": return "statusPending";
      case "REJECTED": return "statusRejected";
      case "ON_HOLD": return "statusOnHold";
      default: return "";
    }
  };

  const formatCurrency = (amount: number, currency: string) => {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: currency || "INR",
      minimumFractionDigits: 2,
    }).format(amount);
  };

  if (loading && invoices.length === 0) {
    return (
      <Shell>
        <header className="topbar">
          <div>
            <div className="eyebrow">ACCOUNTS PAYABLE / INVOICES</div>
            <h1>All Invoices</h1>
          </div>
        </header>
        <div className="emptyState">
          <div className="emptyIcon">↻</div>
          <strong>Loading invoices…</strong>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <header className="topbar">
        <div>
          <div className="eyebrow">ACCOUNTS PAYABLE / INVOICES</div>
          <h1>All Invoices</h1>
        </div>
        <a href="/upload" className="btnGreen" style={{ textDecoration: "none" }}>
          ▤ Upload Invoice
        </a>
      </header>

      <div className="filterBar">
        <input
          type="text"
          placeholder="Search invoice number, supplier, PO…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="searchInput"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="filterSelect"
        >
          <option value="">All statuses</option>
          <option value="RECEIVED">Received</option>
          <option value="EXTRACTING">Extracting</option>
          <option value="VALIDATING">Validating</option>
          <option value="MATCHING">Matching</option>
          <option value="TAX_CHECK">Tax Check</option>
          <option value="DECISION_READY">Decision Ready</option>
          <option value="ON_HOLD">On Hold</option>
          <option value="APPROVAL_PENDING">Approval Pending</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
          <option value="FAILED">Failed</option>
        </select>
      </div>

      {error && (
        <div className="errorCard">
          <div className="errorIcon">!</div>
          <strong>Failed to load invoices</strong>
          <p>{error}</p>
          <button className="btnGreen" onClick={fetchInvoices}>Retry</button>
        </div>
      )}

      <div className="tableWrap">
        <table className="dataTable">
          <thead>
            <tr>
              <th>Invoice #</th>
              <th>Date</th>
              <th>Supplier</th>
              <th>GSTIN</th>
              <th>Amount</th>
              <th>Processing</th>
              <th>Approval</th>
              <th>Received</th>
            </tr>
          </thead>
          <tbody>
            {invoices.length === 0 ? (
              <tr>
                <td colSpan={8} className="emptyRow">
                  {error ? "Failed to load invoices" : "No invoices found. Upload an invoice to get started."}
                </td>
              </tr>
            ) : (
              invoices.map((inv) => (
                <tr key={inv.id} style={{ cursor: "pointer" }} onClick={() => window.location.href = `/review/${inv.id}`}>
                  <td><strong>{inv.invoice_number || "—"}</strong></td>
                  <td>{inv.invoice_date || "—"}</td>
                  <td>{inv.supplier_name || "—"}</td>
                  <td>{inv.supplier_gstin || "—"}</td>
                  <td>{formatCurrency(inv.total_amount || 0, inv.currency)}</td>
                  <td>
                    <span className={`statusBadge ${getStatusColor(inv.processing_status)}`}>
                      {inv.processing_status}
                    </span>
                  </td>
                  <td>
                    <span className={`statusBadge ${getStatusColor(inv.approval_status)}`}>
                      {inv.approval_status}
                    </span>
                  </td>
                  <td>{inv.created_at ? new Date(inv.created_at).toLocaleDateString() : "—"}</td>
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