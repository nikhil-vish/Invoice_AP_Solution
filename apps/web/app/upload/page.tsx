
"use client";

import { useState, useCallback, useRef } from "react";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const MAX_FILE_SIZE = 15 * 1024 * 1024;

type UploadState = "idle" | "uploading" | "success" | "error";

interface ExtractedField {
  [key: string]: string | number | null;
}

interface UploadResponse {
  draft_id: string;
  status: string;
  filename: string;
  file_size_bytes: number;
  sha256: string;
  extraction_kind: string;
  ocr_supported: boolean;
  raw_text: string;
  fields: ExtractedField;
  field_status: Record<string, string>;
  line_items: Array<Record<string, string | number | null>>;
  message: string | null;
}

export default function UploadPage() {
  const [state, setState] = useState<UploadState>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<UploadResponse | null>(null);
  const [reviewUrl, setReviewUrl] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState("idle");
    setFile(null);
    setProgress(0);
    setError(null);
    setResponse(null);
    setReviewUrl(null);
    abortRef.current = null;
  }, []);

  const handleDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;

    const f = acceptedFiles[0];

    if (f.type !== "application/pdf") {
      setError("Only PDF files are accepted.");
      return;
    }

    if (f.size === 0) {
      setError("The uploaded file is empty.");
      return;
    }

    if (f.size > MAX_FILE_SIZE) {
      setError("File exceeds the 15 MB limit.");
      return;
    }

    setFile(f);
    setError(null);
    setState("idle");
    setResponse(null);
    setReviewUrl(null);
  }, []);

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  };

  const handleDropEvent = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();

    const files = Array.from(e.dataTransfer.files).filter(
      (f) => f.type === "application/pdf"
    );

    handleDrop(files);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;

    handleDrop([f]);
    e.target.value = "";
  };

  const handleUpload = async () => {
    if (!file) return;

    abortRef.current = new AbortController();

    setState("uploading");
    setProgress(0);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/v1/invoices/upload`,
        {
          method: "POST",
          body: formData,
          signal: abortRef.current.signal,
        }
      );

      if (!res.ok) {
        let detail = "Upload failed.";

        try {
          const errBody = await res.json();
          detail = errBody.detail || detail;
        } catch {
          // Ignore response parsing errors.
        }

        throw new Error(detail);
      }

      const data: UploadResponse = await res.json();

      setResponse(data);
      setState("success");
      setProgress(100);
      setReviewUrl(`/review/${data.draft_id}`);
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        return;
      }

      setError(
        err instanceof Error
          ? err.message
          : "An unexpected error occurred."
      );

      setState("error");
    }
  };

  const handleRetry = () => {
    if (file) handleUpload();
  };

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandMark">I</div>
          <div>
            <strong>Invoice Intelligence</strong>
            <span>AP WORKSPACE</span>
          </div>
        </div>

        <div className="navLabel">WORKSPACE</div>

        <a className="navItem" href="/">
          ▦ <span>Overview</span>
        </a>
        <a className="navItem" href="/invoices">
          ▤ <span>All invoices</span>
        </a>
        <a className="navItem active">
          ⌁ <span>Live processing</span>
        </a>
        <a className="navItem">
          ⚑ <span>Exception centre</span>
        </a>
        <a className="navItem">
          ✓ <span>Approvals</span>
        </a>

        <div className="navLabel second">CONFIGURATION</div>

        <a className="navItem">
          ▣ <span>Suppliers</span>
        </a>
        <a className="navItem">
          ⚙ <span>Settings</span>
        </a>

        <div className="sidebarFoot">
          Development workspace
          <br />
          <span>Local environment</span>
        </div>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <div className="eyebrow">ACCOUNTS PAYABLE / INTAKE</div>
            <h1>Upload Invoice</h1>
          </div>

          <div className="userPill">
            <span className="dot" /> Development mode
          </div>
        </header>

        {state === "success" && response && reviewUrl ? (
          <div className="successCard">
            <div className="successIcon">✓</div>
            <strong>Upload complete</strong>

            <p>
              {response.filename} (
              {Math.round(response.file_size_bytes / 1024)} KB)
            </p>

            <p className="muted">
              {response.message || "Text extraction completed."}
            </p>

            <button
              className="btnGreen"
              onClick={() => {
                window.location.href = reviewUrl;
              }}
            >
              Review extracted data
            </button>

            <button className="btnOutline" onClick={reset}>
              Upload another
            </button>
          </div>
        ) : state === "error" && error ? (
          <div className="errorCard">
            <div className="errorIcon">!</div>
            <strong>Upload failed</strong>
            <p>{error}</p>

            {file && (
              <button className="btnGreen" onClick={handleRetry}>
                Try again
              </button>
            )}

            <button className="btnOutline" onClick={reset}>
              Cancel
            </button>
          </div>
        ) : (
          <div className="uploadZone">
            <div
              className="dropArea"
              onDragOver={handleDragOver}
              onDrop={handleDropEvent}
              onClick={() => {
                const input = document.getElementById(
                  "file-input"
                ) as HTMLInputElement | null;

                input?.click();
              }}
            >
              <div className="dropIcon">▤</div>

              <p className="dropHint">
                Drag &amp; drop a PDF invoice here
              </p>

              <p className="dropLimit">PDF only · Max 15 MB</p>

              <input
                id="file-input"
                type="file"
                accept="application/pdf"
                style={{ display: "none" }}
                onChange={handleFileSelect}
              />

              {file && (
                <div className="selectedFile">
                  <strong>{file.name}</strong>
                  <span>
                    ({Math.round(file.size / 1024)} KB)
                  </span>
                </div>
              )}
            </div>

            {progress > 0 && state === "uploading" && (
              <div className="progressBar">
                <div
                  className="progressFill"
                  style={{ width: `${progress}%` }}
                />
              </div>
            )}

            <button
              className="btnGreen"
              disabled={!file || state === "uploading"}
              onClick={handleUpload}
            >
              {state === "uploading"
                ? "Uploading..."
                : "Upload Invoice"}
            </button>
          </div>
        )}
      </section>
    </main>
  );
}
