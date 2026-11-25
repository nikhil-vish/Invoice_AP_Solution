"""Invoice intake API routes.

POST /api/v1/invoices/upload — multipart/form-data PDF upload.
"""

import hashlib
import uuid
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Path

from app.invoices.extract import extract_invoice_pdf, PdfReadError
from app.invoices.fields import MAX_UPLOAD_BYTES
from app.invoices.records import extraction_summary
from app.invoices.storage import upload_pdf, StorageError
from app.invoices.repository import (
    find_draft_by_sha256,
    insert_intake_draft,
    RepositoryError,
)
from app.config import settings
from supabase import create_client

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])

ALLOWED_CONTENT_TYPES = {"application/pdf"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_uuid(value: str) -> None:
    """Raise HTTPException 400 if value is not a valid UUID."""
    try:
        uuid.UUID(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid draft ID format.",
        )


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_invoice(file: UploadFile = File(...)):
    """Upload a PDF invoice, extract text, and persist an intake draft."""
    content_type = file.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted.",
        )

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )

    if not data.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The file is not a valid PDF.",
        )

    sha256 = _sha256(data)

    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.",
        )

    storage_bucket = getattr(settings, "supabase_storage_bucket", None) or "invoices"
    storage_path = f"intake/{sha256}/{file.filename or 'invoice.pdf'}"

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    try:
        existing = find_draft_by_sha256(client, sha256)
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A document with this content has already been uploaded.",
            headers={"X-Existing-Draft-Id": existing["id"]},
        )

    try:
        upload_pdf(storage_bucket, storage_path, data, content_type)
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    try:
        extraction = extract_invoice_pdf(data)
    except PdfReadError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Text extraction failed: {exc}",
        )

    summary = extraction_summary(
        filename=file.filename or "invoice.pdf",
        size_bytes=len(data),
        extraction=extraction,
        intake_status="EXTRACTED",
    )
    draft_payload = {
        "original_filename": file.filename or "invoice.pdf",
        "storage_path": storage_path,
        "mime_type": content_type,
        "sha256": sha256,
        "file_size_bytes": len(data),
        "extracted_data": summary,
        "raw_text": extraction.get("raw_text"),
        "extraction_method": "pymupdf_digital" if extraction.get("kind") == "digital" else "scanned_no_text",
        "processing_status": "FAILED" if extraction.get("kind") == "scanned" else "EXTRACTED",
    }
    try:
        draft = insert_intake_draft(client, draft_payload)
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not persist intake draft: {exc}",
        )

    extracted = extraction.get("fields", {})
    line_items = extraction.get("line_items", [])
    response = {
        "draft_id": draft["id"],
        "status": draft["processing_status"],
        "filename": file.filename,
        "file_size_bytes": len(data),
        "sha256": sha256,
        "storage_path": storage_path,
        "extraction_kind": extraction.get("kind"),
        "ocr_supported": False,
        "raw_text": extraction.get("raw_text"),
        "fields": extracted,
        "field_status": extraction.get("field_status", {}),
        "line_items": line_items,
        "message": None,
    }
    if extraction.get("kind") == "scanned":
        response["message"] = (
            "This PDF has no extractable digital text. OCR is not implemented, "
            "so scanned invoices cannot be read yet. The file has been stored "
            "and can be reviewed manually."
        )

    return response


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str = Path(...)):
    """Retrieve an intake draft by ID."""
    _validate_uuid(draft_id)
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase is not configured.",
        )
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    try:
        result = client.table("invoice_intake_drafts").select("*").eq("id", draft_id).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {exc}",
        )
    data = result.data or []
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found.",
        )
    draft = data[0]
    summary = draft.get("extracted_data") or {}
    return {
        "draft_id": draft["id"],
        "status": draft["processing_status"],
        "filename": draft["original_filename"],
        "file_size_bytes": draft["file_size_bytes"],
        "sha256": draft["sha256"],
        "storage_path": draft["storage_path"],
        "extraction_kind": "digital" if draft["extraction_method"] == "pymupdf_digital" else "scanned",
        "ocr_supported": False,
        "raw_text": draft.get("raw_text") or "",
        "fields": (summary.get("fields") or {}),
        "field_status": (summary.get("field_status") or {}),
        "line_items": (summary.get("line_items") or []),
        "message": None,
    }


@router.post("/drafts/{draft_id}/save")
async def save_draft(draft_id: str = Path(...)):
    """Save edited draft data (placeholder for future persistence)."""
    _validate_uuid(draft_id)
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase is not configured.",
        )
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    try:
        result = client.table("invoice_intake_drafts").select("*").eq("id", draft_id).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {exc}",
        )
    data = result.data or []
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found.",
        )
    try:
        client.table("invoice_intake_drafts").update({
            "processing_status": "READY_FOR_VALIDATION",
            "updated_at": "now()",
        }).eq("id", draft_id).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Save failed: {exc}",
        )
    return {"draft_id": draft_id, "status": "READY_FOR_VALIDATION", "saved": True}