"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import { Shell } from "@/components/Shell";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface FieldValue {
  value: string | null;
  status: "found" | "missing" | "edited";
}

interface LineItem {
  description: string | null;
  hsn_sac: string | null;
  quantity: string | number | null;
  unit_price: string | number | null;
  taxable_value: string | number | null;
  cgst: string | number | null;
  sgst: string | number | null;
  igst: string | number | null;
}

interface ReviewData {
  draft_id: string;
  status: string;
  filename: string;
  file_size_bytes: number;
  sha256: string;
  extraction_kind: string;
  ocr_supported: boolean;
  raw_text: string;
  fields: Record<string, string | number | null>;
  field_status: Record<string, string>;
  line_items: LineItem[];
  message: string | null;
}

const HEADER_LABELS: Record<string, string> = {
  supplier_legal_name: "Supplier legal name",
  supplier_gstin: "Supplier GSTIN",
  supplier_address: "Supplier address",
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  due_date: "Due date",
  buyer_legal_name: "Buyer legal name",
  buyer_gstin: "Buyer GSTIN",
  po_number: "PO number",
  taxable_value: "Taxable value",
  cgst: "CGST",
  sgst: "SGST",
  igst: "IGST",
  total_tax: "Total tax",
  invoice_grand_total: "Invoice grand total",
  currency: "Currency",
};

export default function ReviewPage() {
  const params = useParams<{ id: string }>();
  const draftId = params?.id ?? "";

  const [data, setData] = useState<ReviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editedFields, setEditedFields] = useState<Record<string, FieldValue>>({});
  const [saved, setSaved] = useState(false);

  const fetchData = useCallback(async () => {
    if (!draftId) {
      setError("Invalid draft ID.");
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/invoices/drafts/${draftId}`);
      if (!res.ok) {
        if (res.status === 404) {
          throw new Error("Draft not found.");
        }
        throw new Error("Could not load draft.");
      }
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load draft.");
    } finally {
      setLoading(false);
    }
  }, [draftId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const initializeEdited = useCallback(() => {
    if (!data) return;
    const next: Record<string, FieldValue> = {};
    for (const [key, value] of Object.entries(data.fields)) {
      next[key] = {
        value: value === null ? null : String(value),
        status: data.field_status?.[key] === "found" ? "found" : "missing",
      };
    }
    setEditedFields(next);
  }, [data]);

  useEffect(() => {
    initializeEdited();
  }, [initializeEdited]);

  const updateField = (key: string, value: string) => {
    setEditedFields((prev) => ({
      ...prev,
      [key]: { value, status: "edited" },
    }));
    setSaved(false);
  };

  const handleSaveDraft = async () => {
    if (!data || !draftId) return;
    const payload = {
      draft_id: data.draft_id,
      fields: editedFields,
      line_items: data.line_items,
    };
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/invoices/drafts/${draftId}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Save failed.");
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    }
  };

  const missingFields = data
    ? Object.entries(data.field_status).filter(([, s]) => s === "missing").map(([k]) => k)
    : [];

  if (loading) {
    return (
      <Shell>
        <header className="topbar">
          <div>
            <div className="eyebrow">ACCOUNTS PAYABLE / REVIEW</div>
            <h1>Review Invoice</h1>
          </div>
        </header>
        <div className="emptyState">
          <div className="emptyIcon">↻</div>
          <strong>Loading…</strong>
        </div>
      </Shell>
    );
  }

  if (error || !data) {
    return (
      <Shell>
        <header className="topbar">
          <div>
            <div className="eyebrow">ACCOUNTS PAYABLE / REVIEW</div>
            <h1>Review Invoice</h1>
          </div>
        </header>
        <div className="errorCard">
          <div className="errorIcon">!</div>
          <strong>Could not load draft</strong>
          <p>{error || "Draft not found."}</p>
          <button className="btnGreen" onClick={() => { window.location.href = "/upload"; }}>
            Upload another
          </button>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <header className="topbar">
        <div>
          <div className="eyebrow">ACCOUNTS PAYABLE / REVIEW</div>
          <h1>Review Invoice</h1>
        </div>
        <a className="btnOutline" href="/upload">← Upload another</a>
      </header>

      <div className="reviewHeader">
        <div className="docInfo">
          <div className="docBadge">{data.extraction_kind === "scanned" ? "SCANNED" : "DIGITAL"}</div>
          <strong>{data.filename}</strong>
          <span className="muted">{Math.round(data.file_size_bytes / 1024)} KB · SHA-256: {data.sha256.slice(0, 16)}…</span>
        </div>
        <div className="statusBadge">
          {data.extraction_kind === "scanned" ? (
            <span className="statusScanned">No extractable text · OCR not implemented</span>
          ) : (
            <span className="statusDigital">Digital text extracted</span>
          )}
        </div>
      </div>

      {data.message && (
        <div className="infoBox">
          <div className="infoIcon">!</div>
          <p>{data.message}</p>
        </div>
      )}

      <div className="reviewGrid">
        <section className="reviewPanel">
          <h3>Invoice details</h3>
          <div className="fieldList">
            {Object.entries(HEADER_LABELS).map(([key, label]) => {
              const field = editedFields[key];
              const val = field ? field.value : data.fields[key];
              const status = field ? field.status : data.field_status?.[key];
              const isMissing = status === "missing";
              return (
                <div key={key} className="fieldRow">
                  <label>{label}</label>
                  <input
                    type="text"
                    value={val ?? ""}
                    onChange={(e) => updateField(key, e.target.value)}
                    disabled={data.extraction_kind === "scanned"}
                    className={isMissing ? "inputMissing" : "inputField"}
                    placeholder={isMissing ? "Not extracted" : undefined}
                  />
                  {isMissing && <span className="missingTag">Missing</span>}
                </div>
              );
            })}
          </div>
        </section>

        <section className="reviewPanel full">
          <h3>Line items</h3>
          <div className="tableWrap">
            <table className="dataTable">
              <thead>
                <tr>
                  <th>Description</th>
                  <th>HSN/SAC</th>
                  <th>Qty</th>
                  <th>Unit price</th>
                  <th>Taxable value</th>
                  <th>CGST</th>
                  <th>SGST</th>
                  <th>IGST</th>
                </tr>
              </thead>
              <tbody>
                {data.line_items.map((item, idx) => (
                  <tr key={idx}>
                    <td>
                      <input
                        type="text"
                        value={item.description ?? ""}
                        onChange={() => {}}
                        disabled
                        className="inputCell"
                      />
                    </td>
                    <td>
                      <input type="text" value={item.hsn_sac ?? ""} disabled className="inputCell" />
                    </td>
                    <td>
                      <input type="text" value={String(item.quantity ?? "")} disabled className="inputCell" />
                    </td>
                    <td>
                      <input type="text" value={String(item.unit_price ?? "")} disabled className="inputCell" />
                    </td>
                    <td>
                      <input type="text" value={String(item.taxable_value ?? "")} disabled className="inputCell" />
                    </td>
                    <td>
                      <input type="text" value={String(item.cgst ?? "")} disabled className="inputCell" />
                    </td>
                    <td>
                      <input type="text" value={String(item.sgst ?? "")} disabled className="inputCell" />
                    </td>
                    <td>
                      <input type="text" value={String(item.igst ?? "")} disabled className="inputCell" />
                    </td>
                  </tr>
                ))}
                {data.line_items.length === 0 && (
                  <tr><td colSpan={8} className="emptyRow">No line items extracted.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {missingFields.length > 0 && (
        <div className="missingNotice">
          <span className="missingDot"/> Missing: {missingFields.map((k) => HEADER_LABELS[k] || k).join(", ")}
        </div>
      )}

      <div className="reviewFooter">
        <button className="btnGreen" onClick={handleSaveDraft} disabled={saved}>
          {saved ? "Saved" : "Save draft"}
        </button>
        <span className="muted">Extraction method: PyMuPDF (digital text only, no OCR)</span>
      </div>
    </Shell>
  );
}