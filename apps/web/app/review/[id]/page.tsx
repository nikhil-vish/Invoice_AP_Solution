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
  invoice_id: string | null;
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

interface Analysis {
  recommendation: string;
  risk_level: string;
  confidence_score: number;
  executive_summary: string;
  findings: Array<{ category: string; severity: string; description: string; suggested_action: string }>;
  model_used: string;
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
  const [editedLines, setEditedLines] = useState<LineItem[]>([]);
  const [saved, setSaved] = useState(false);
  const [queueing, setQueueing] = useState(false);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);

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

  const fetchAnalysis = useCallback(async () => {
    if (!data?.invoice_id) return;
    const res = await fetch(`${API_BASE_URL}/api/v1/invoices/${data.invoice_id}/analysis/latest`);
    if (res.ok) setAnalysis(await res.json());
  }, [data?.invoice_id]);

  useEffect(() => { fetchAnalysis(); }, [fetchAnalysis]);

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
    setEditedLines(data.line_items);
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

  const updateLine = (index: number, key: keyof LineItem, value: string) => {
    setEditedLines((lines) => lines.map((line, lineIndex) =>
      lineIndex === index ? { ...line, [key]: value === "" ? null : value } : line,
    ));
    setSaved(false);
  };

  const addLine = () => {
    setEditedLines((lines) => [...lines, {
      description: null, hsn_sac: null, quantity: null, unit_price: null,
      taxable_value: null, cgst: null, sgst: null, igst: null,
    }]);
    setSaved(false);
  };

  const removeLine = (index: number) => {
    setEditedLines((lines) => lines.filter((_, lineIndex) => lineIndex !== index));
    setSaved(false);
  };

  const handleSaveDraft = async () => {
    if (!data || !draftId) return;
    const payload = {
      draft_id: data.draft_id,
      fields: editedFields,
      line_items: editedLines,
    };
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/invoices/drafts/${draftId}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Save failed.");
      }
      setSaved(true);
      await fetchData();
      window.setTimeout(fetchAnalysis, 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed.");
    }
  };

  const handleSubmit = async () => {
    if (!data?.invoice_id) return;
    setQueueing(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/invoices/${data.invoice_id}/process`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Could not queue invoice.");
      }
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not queue invoice.");
    } finally {
      setQueueing(false);
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
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {editedLines.map((item, idx) => (
                  <tr key={idx}>
                    <td>
                      <input
                        type="text"
                        value={item.description ?? ""}
                        onChange={(e) => updateLine(idx, "description", e.target.value)}
                        className="inputCell"
                      />
                    </td>
                    <td>
                      <input type="text" value={item.hsn_sac ?? ""} onChange={(e) => updateLine(idx, "hsn_sac", e.target.value)} className="inputCell" />
                    </td>
                    <td>
                      <input type="number" value={String(item.quantity ?? "")} onChange={(e) => updateLine(idx, "quantity", e.target.value)} className="inputCell" />
                    </td>
                    <td>
                      <input type="number" value={String(item.unit_price ?? "")} onChange={(e) => updateLine(idx, "unit_price", e.target.value)} className="inputCell" />
                    </td>
                    <td>
                      <input type="number" value={String(item.taxable_value ?? "")} onChange={(e) => updateLine(idx, "taxable_value", e.target.value)} className="inputCell" />
                    </td>
                    <td>
                      <input type="number" value={String(item.cgst ?? "")} onChange={(e) => updateLine(idx, "cgst", e.target.value)} className="inputCell" />
                    </td>
                    <td>
                      <input type="number" value={String(item.sgst ?? "")} onChange={(e) => updateLine(idx, "sgst", e.target.value)} className="inputCell" />
                    </td>
                    <td>
                      <input type="number" value={String(item.igst ?? "")} onChange={(e) => updateLine(idx, "igst", e.target.value)} className="inputCell" />
                    </td>
                    <td><button className="btnOutline" onClick={() => removeLine(idx)}>Remove</button></td>
                  </tr>
                ))}
                {editedLines.length === 0 && (
                  <tr><td colSpan={9} className="emptyRow">No line items extracted.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
      {analysis && (
        <section className="reviewPanel full" style={{ marginTop: 16 }}>
          <h3>AI review recommendation <button className="btnOutline" onClick={fetchAnalysis}>Refresh analysis</button></h3>
          <p><strong>{analysis.recommendation}</strong> · {analysis.risk_level} risk · model confidence {analysis.confidence_score}/100</p>
          <p>{analysis.executive_summary}</p>
          {analysis.findings.map((finding, index) => <div key={index} className="infoBox"><strong>{finding.category} · {finding.severity}</strong><p>{finding.description}</p><small>{finding.suggested_action}</small></div>)}
          <small className="muted">Advisory only · model: {analysis.model_used}</small>
        </section>
      )}
      <button className="btnOutline" onClick={addLine}>+ Add line item</button>

      {missingFields.length > 0 && (
        <div className="missingNotice">
          <span className="missingDot"/> Missing: {missingFields.map((k) => HEADER_LABELS[k] || k).join(", ")}
        </div>
      )}

      <div className="reviewFooter">
        <button className="btnGreen" onClick={handleSaveDraft}>
          {saved ? "Saved" : "Save draft"}
        </button>
        {saved && data.invoice_id && (
          <button className="btnOutline" onClick={handleSubmit} disabled={queueing} style={{ marginLeft: 8 }}>
            {queueing ? "Queuing…" : "Submit for processing"}
          </button>
        )}
        <a href="/invoices" className="btnOutline" style={{ marginLeft: 8 }}>View All Invoices</a>

        <span className="muted">Extraction method: PyMuPDF (digital text only, no OCR)</span>
      </div>
    </Shell>
  );
}
