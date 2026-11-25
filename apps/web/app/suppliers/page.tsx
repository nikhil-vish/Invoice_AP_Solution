"use client";

import { Shell } from "@/components/Shell";
import { useState, useEffect, useCallback } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface Supplier {
  id: string;
  legal_name: string;
  trade_name: string | null;
  gstin: string | null;
  vendor_code: string | null;
  status: string;
  aliases: string[];
  created_at: string;
}

interface SuppliersResponse {
  suppliers: Supplier[];
  total: number;
}

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const fetchSuppliers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: "20",
      });
      if (search) params.append("search", search);
      if (statusFilter) params.append("status", statusFilter);

      const res = await fetch(`${API_BASE_URL}/api/v1/invoices/suppliers?${params.toString()}`);
      if (!res.ok) {
        throw new Error("Failed to fetch suppliers");
      }
      const data: SuppliersResponse = await res.json();
      setSuppliers(data.suppliers);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load suppliers");
    } finally {
      setLoading(false);
    }
  }, [page, search, statusFilter]);

  useEffect(() => {
    fetchSuppliers();
  }, [fetchSuppliers]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "ACTIVE": return "statusActive";
      case "PENDING": return "statusPending";
      case "BLOCKED": return "statusBlocked";
      case "INACTIVE": return "statusInactive";
      default: return "";
    }
  };

  if (loading && suppliers.length === 0) {
    return (
      <Shell>
        <header className="topbar">
          <div>
            <div className="eyebrow">ACCOUNTS PAYABLE / SUPPLIERS</div>
            <h1>Suppliers</h1>
          </div>
        </header>
        <div className="emptyState">
          <div className="emptyIcon">↻</div>
          <strong>Loading suppliers…</strong>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <header className="topbar">
        <div>
          <div className="eyebrow">ACCOUNTS PAYABLE / SUPPLIERS</div>
          <h1>Suppliers</h1>
        </div>
      </header>

      <div className="filterBar">
        <input
          type="text"
          placeholder="Search supplier name, GSTIN, vendor code…"
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
          <option value="ACTIVE">Active</option>
          <option value="PENDING">Pending</option>
          <option value="BLOCKED">Blocked</option>
          <option value="INACTIVE">Inactive</option>
        </select>
      </div>

      {error && (
        <div className="errorCard">
          <div className="errorIcon">!</div>
          <strong>Failed to load suppliers</strong>
          <p>{error}</p>
          <button className="btnGreen" onClick={fetchSuppliers}>Retry</button>
        </div>
      )}

      <div className="tableWrap">
        <table className="dataTable">
          <thead>
            <tr>
              <th>Legal name</th>
              <th>Trade name</th>
              <th>GSTIN</th>
              <th>Vendor code</th>
              <th>Status</th>
              <th>Aliases</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {suppliers.length === 0 ? (
              <tr>
                <td colSpan={8} className="emptyRow">
                  {error ? "Failed to load suppliers" : "No suppliers found."}
                </td>
              </tr>
            ) : (
              suppliers.map((sup) => (
                <tr key={sup.id}>
                  <td><strong>{sup.legal_name}</strong></td>
                  <td>{sup.trade_name || "—"}</td>
                  <td>{sup.gstin || "—"}</td>
                  <td>{sup.vendor_code || "—"}</td>
                  <td>
                    <span className={`statusBadge ${getStatusColor(sup.status)}`}>
                      {sup.status}
                    </span>
                  </td>
                  <td>{sup.aliases?.length ? sup.aliases.join(", ") : "—"}</td>
                  <td>{new Date(sup.created_at).toLocaleDateString()}</td>
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