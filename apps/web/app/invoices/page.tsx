"use client";
import { Shell } from "@/components/Shell";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface InvoiceSummary {
  id: string;
  draft_id: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  supplier_legal_name: string | null;
  supplier_gstin: string | null;
  total_amount: number | null;
  currency: string | null;
  processing_status: string;
  current_stage: string | null;
  approval_status: string;
  created_at: string;
  ai_summary: { risk_level: string | null; recommendation: string | null; finding_count: number; created_at: string } | null;
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
      const params = new URLSearchParams({ page: page.toString(), page_size: "20" });
      if (search) params.append("search", search);
      if (statusFilter) params.append("status", statusFilter);
      const res = await fetch(`${API_BASE_URL}/api/v1/invoices?${params.toString()}`);
      if (!res.ok) throw new Error("Failed to fetch invoices");
      const data: InvoicesResponse = await res.json();
      setInvoices(data.invoices);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load invoices");
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter]);

  useEffect(() => { fetchInvoices(); }, [fetchInvoices]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "APPROVED": return "statusApproved";
      case "PENDING": return "statusPending";
      case "REJECTED": return "statusRejected";
      case "ON_HOLD": return "statusOnHold";
      case "SUBMITTED": return "statusSubmitted";
      default: return "";
    }
  };

  const formatCurrency = (amount: number, currency: string) => {
    return new Intl.NumberFormat("en-IN", { style: "currency", currency: currency || "INR", minimumFractionDigits: 2 }).format(amount);
  };

  if (loading && invoices.length === 0) {
    return (
      <Shell>
        <header className="topbar"><div><div className="eyebrow">ACCOUNTS PAYABLE / INVOICES</div><h1>All Invoices</h1></div><a href="/upload" className="btnPrimary" style={{textDecoration:"none"}}>▤ Upload Invoice</a></header>
        <div className="emptyState"><div className="emptyIcon">↻</div><strong>Loading invoices…</strong></div>
      </Shell>
    );
  }

  return (
    <Shell>
      <header className="topbar"><div><div className="eyebrow">ACCOUNTS PAYABLE / INVOICES</div><h1>All Invoices</h1></div><a href="/upload" className="btnPrimary" style={{textDecoration:"none"}}>▤ Upload Invoice</a></header>
      <div className="filterBar">
        <input type="text" placeholder="Search invoice number, supplier, PO…" value={search} onChange={(e)=>setSearch(e.target.value)} className="searchInput"/>
        <select value={statusFilter} onChange={(e)=>setStatusFilter(e.target.value)} className="filterSelect">
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="QUEUED">Queued</option>
          <option value="SUBMITTED">Submitted</option>
          <option value="PROCESSING">Processing</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
        </select>
      </div>
      {error && (
        <div className="errorCard"><div className="errorIcon">!</div><strong>Failed to load invoices</strong><p>{error}</p><button className="btnPrimary" onClick={fetchInvoices}>Retry</button></div>
      )}
      <div className="tableWrap">
        <table className="dataTable">
          <thead>
            <tr>
              <th style={{textAlign:"left"}}>Invoice #</th>
              <th style={{textAlign:"left"}}>Date</th>
              <th style={{textAlign:"left"}}>Supplier</th>
              <th style={{textAlign:"left"}}>GSTIN</th>
              <th style={{textAlign:"right"}}>Amount</th>
              <th style={{textAlign:"left"}}>Processing</th>
              <th style={{textAlign:"left"}}>AI intelligence</th>
              <th style={{textAlign:"left"}}>Received</th>
            </tr>
          </thead>
          <tbody>
            {invoices.length === 0 ? (
              <tr><td colSpan={8} className="emptyRow">{error ? "Failed to load invoices" : "No invoices found. Upload an invoice to get started."}</td></tr>
            ) : (
              invoices.map((inv) => (
                <tr key={inv.id} style={{cursor:inv.draft_id ? "pointer" : "default"}} onClick={()=>inv.draft_id && (window.location.href=`/review/${inv.draft_id}`)}>
                  <td><strong style={{color:"var(--ink)"}}>{inv.invoice_number || "—"}</strong></td>
                  <td style={{color:"var(--muted)"}}>{inv.invoice_date || "—"}</td>
                  <td>{inv.supplier_legal_name || "—"}</td>
                  <td style={{fontSize:12,color:"var(--muted)"}}>{inv.supplier_gstin || "—"}</td>
                  <td style={{textAlign:"right",fontWeight:600}}>{formatCurrency(inv.total_amount || 0, inv.currency || "INR")}</td>
                  <td><span className={`statusBadge ${getStatusColor(inv.processing_status)}`}>{inv.processing_status}</span></td>
                  <td>{inv.ai_summary ? (<><span className={`statusBadge risk${(inv.ai_summary.risk_level||"Unknown").toUpperCase()}`}>{inv.ai_summary.risk_level || "Unknown"}</span>&nbsp;{inv.ai_summary.recommendation || "—"} · {inv.ai_summary.finding_count} finding{inv.ai_summary.finding_count === 1 ? "" : "s"}</>):<span className="muted">Not analysed</span>}</td>
                  <td style={{color:"var(--muted)"}}>{inv.created_at ? new Date(inv.created_at).toLocaleDateString() : "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {total > 20 && (
        <div className="pagination">
          <button className="btnOutline" disabled={page===1} onClick={()=>setPage(p=>p-1)}>← Previous</button>
          <span className="pageInfo">Page {page} of {Math.ceil(total / 20)} ({total} total)</span>
          <button className="btnOutline" disabled={page * 20 >= total} onClick={()=>setPage(p=>p+1)}>Next →</button>
        </div>
      )}
    </Shell>
  );
}
