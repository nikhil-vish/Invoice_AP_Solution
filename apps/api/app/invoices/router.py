"""Invoice API routes.

Endpoints:
- POST /api/v1/invoices/upload — multipart/form-data PDF upload
- GET /api/v1/invoices — list/filter/paginate invoices
- GET /api/v1/invoices/{invoice_id} — invoice detail with items, documents, runs
- POST /api/v1/invoices/{invoice_id}/process — start/retry processing idempotently
- GET /api/v1/invoices/runs — list processing runs
- GET /api/v1/invoices/runs/{run_id} — processing run detail with stage events
- GET /api/v1/invoices/suppliers — list suppliers
- GET /api/v1/invoices/approvals — list approval tasks
- GET /api/v1/invoices/approvals/{approval_id} — approval detail
- POST /api/v1/invoices/approvals/{approval_id}/action — process approval action
- GET /api/v1/invoices/exceptions — list exceptions
- GET /api/v1/invoices/exceptions/{exception_id} — exception detail
- POST /api/v1/invoices/exceptions/{exception_id}/assign — assign exception
- POST /api/v1/invoices/exceptions/{exception_id}/resolve — resolve exception
- GET /api/v1/invoices/drafts/{draft_id} — retrieve intake draft
- POST /api/v1/invoices/drafts/{draft_id}/save — save edited draft
"""

import hashlib
import uuid
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, status, Path, Query
from pydantic import BaseModel

from app.invoices.extract import extract_invoice_pdf, PdfReadError
from app.invoices.fields import MAX_UPLOAD_BYTES
from app.invoices.records import extraction_summary, invoice_columns, line_columns
from app.invoices.storage import upload_pdf, StorageError
from app.invoices.repository import (
    find_draft_by_sha256,
    insert_intake_draft,
    list_invoices,
    get_invoice,
    insert_invoice,
    insert_invoice_items,
    insert_invoice_document,
    update_invoice_status,
    list_processing_runs,
    get_processing_run,
    insert_processing_run,
    update_processing_run,
    insert_validation_result,
    list_suppliers,
    list_approvals,
    get_approval,
    list_exceptions,
    get_exception,
    assign_exception,
    resolve_exception,
    action_approval,
    RepositoryError,
)
from app.config import settings
from supabase import create_client

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])

ALLOWED_CONTENT_TYPES = {"application/pdf"}

# Development default client ID (replace with auth context in production)
DEFAULT_CLIENT_ID = "00000000-0000-0000-0000-000000000001"


# Pydantic models for request bodies
class ExceptionAssignRequest(BaseModel):
    owner_team: str
    actor_id: str = "current-user"  # In production, get from auth context


class ExceptionResolveRequest(BaseModel):
    resolution_comment: str
    actor_id: str = "current-user"


class ApprovalActionRequest(BaseModel):
    action: str  # APPROVE, REJECT, RETURN_FOR_INFORMATION
    comment: Optional[str] = None
    actor_id: str = "current-user"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_uuid(value: str) -> None:
    """Raise HTTPException 400 if value is not a valid UUID."""
    try:
        uuid.UUID(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ID format.",
        )


def _get_client():
    """Get Supabase client with service role."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.",
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


# ==================== Sub-routers (must be included first for route priority) ====================

# Processing Runs sub-router
runs_router = APIRouter(prefix="/runs", tags=["runs"])


@runs_router.get("")
async def list_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List processing runs with pagination."""
    client = _get_client()
    try:
        result = list_processing_runs(
            client,
            client_id=DEFAULT_CLIENT_ID,
            page=page,
            page_size=page_size,
        )
        return result
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@runs_router.get("/{run_id}")
async def get_run(run_id: str = Path(...)):
    """Get processing run detail with stage events."""
    _validate_uuid(run_id)
    client = _get_client()
    try:
        run = get_processing_run(client, run_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {exc}",
        )
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Processing run not found.",
        )
    return run


# Suppliers sub-router
suppliers_router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@suppliers_router.get("")
async def list_suppliers_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List suppliers with pagination and filtering."""
    client = _get_client()
    try:
        result = list_suppliers(
            client,
            client_id=DEFAULT_CLIENT_ID,
            page=page,
            page_size=page_size,
            search=search,
            status=status_filter,
        )
        return result
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


# Approvals sub-router
approvals_router = APIRouter(prefix="/approvals", tags=["approvals"])


@approvals_router.get("")
async def list_approvals_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List approval tasks with pagination and filtering."""
    client = _get_client()
    try:
        result = list_approvals(
            client,
            client_id=DEFAULT_CLIENT_ID,
            page=page,
            page_size=page_size,
            status=status_filter,
        )
        return result
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@approvals_router.get("/{approval_id}")
async def get_approval_endpoint(approval_id: str = Path(...)):
    """Get approval detail."""
    _validate_uuid(approval_id)
    client = _get_client()
    try:
        approval = get_approval(client, approval_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {exc}",
        )
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found.",
        )
    return approval


@approvals_router.post("/{approval_id}/action")
async def approval_action_endpoint(
    approval_id: str = Path(...),
    request: ApprovalActionRequest = None,
):
    """Process an approval action (APPROVE, REJECT, RETURN_FOR_INFORMATION)."""
    _validate_uuid(approval_id)
    client = _get_client()
    try:
        result = action_approval(
            client,
            approval_id=approval_id,
            action=request.action.upper(),
            comment=request.comment,
            actor_id=request.actor_id,
        )
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {exc}",
        )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found.",
        )
    return result


# Exceptions sub-router
exceptions_router = APIRouter(prefix="/exceptions", tags=["exceptions"])


@exceptions_router.get("")
async def list_exceptions_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    severity_filter: Optional[str] = Query(None, alias="severity"),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List exceptions with pagination and filtering."""
    client = _get_client()
    try:
        result = list_exceptions(
            client,
            client_id=DEFAULT_CLIENT_ID,
            page=page,
            page_size=page_size,
            severity=severity_filter,
            status=status_filter,
        )
        return result
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@exceptions_router.get("/{exception_id}")
async def get_exception_endpoint(exception_id: str = Path(...)):
    """Get exception detail."""
    _validate_uuid(exception_id)
    client = _get_client()
    try:
        exception = get_exception(client, exception_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {exc}",
        )
    if not exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exception not found.",
        )
    return exception


@exceptions_router.post("/{exception_id}/assign")
async def assign_exception_endpoint(
    exception_id: str = Path(...),
    request: ExceptionAssignRequest = None,
):
    """Assign an exception to an owner team."""
    _validate_uuid(exception_id)
    client = _get_client()
    try:
        result = assign_exception(
            client,
            exception_id=exception_id,
            owner_team=request.owner_team,
            actor_id=request.actor_id,
        )
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {exc}",
        )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exception not found.",
        )
    return result


@exceptions_router.post("/{exception_id}/resolve")
async def resolve_exception_endpoint(
    exception_id: str = Path(...),
    request: ExceptionResolveRequest = None,
):
    """Resolve an exception with a mandatory resolution comment."""
    _validate_uuid(exception_id)
    client = _get_client()
    try:
        result = resolve_exception(
            client,
            exception_id=exception_id,
            resolution_comment=request.resolution_comment,
            actor_id=request.actor_id,
        )
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {exc}",
        )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exception not found.",
        )
    return result


# Include sub-routers FIRST so their routes have priority over catch-all routes
router.include_router(runs_router)
router.include_router(suppliers_router)
router.include_router(approvals_router)
router.include_router(exceptions_router)


# ==================== Main Invoice Routes ====================

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

    client = _get_client()
    storage_bucket = getattr(settings, "supabase_storage_bucket", None) or "invoices"
    storage_path = f"intake/{sha256}/{file.filename or 'invoice.pdf'}"

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


@router.get("")
async def list_invoices_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List invoices with pagination and filtering."""
    client = _get_client()
    try:
        result = list_invoices(
            client,
            client_id=DEFAULT_CLIENT_ID,
            page=page,
            page_size=page_size,
            search=search,
            status=status_filter,
        )
        return result
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )


@router.get("/{invoice_id}")
async def get_invoice_endpoint(invoice_id: str = Path(...)):
    """Get invoice detail with line items and documents."""
    _validate_uuid(invoice_id)
    client = _get_client()
    try:
        invoice = get_invoice(client, invoice_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {exc}",
        )
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found.",
        )
    return invoice


@router.post("/{invoice_id}/process")
async def process_invoice(invoice_id: str = Path(...)):
    """Start or retry invoice processing idempotently."""
    _validate_uuid(invoice_id)
    client = _get_client()
    
    # Check invoice exists
    invoice = get_invoice(client, invoice_id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found.",
        )
    
    # Check if there's already a running/queued run
    runs_result = client.table("processing_runs").select("*").eq("invoice_id", invoice_id).eq("status", "QUEUED").execute()
    if runs_result.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Processing already queued for this invoice.",
        )
    
    runs_result = client.table("processing_runs").select("*").eq("invoice_id", invoice_id).eq("status", "RUNNING").execute()
    if runs_result.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Processing already running for this invoice.",
        )
    
    # Create new processing run
    run_number = 1
    existing_runs = client.table("processing_runs").select("run_number").eq("invoice_id", invoice_id).order("run_number", desc=True).limit(1).execute()
    if existing_runs.data:
        run_number = existing_runs.data[0]["run_number"] + 1
    
    run_payload = {
        "invoice_id": invoice_id,
        "run_number": run_number,
        "status": "QUEUED",
        "triggered_by": "MANUAL_RETRY" if run_number > 1 else "MANUAL_UPLOAD",
    }
    
    try:
        run = insert_processing_run(client, run_payload)
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not create processing run: {exc}",
        )
    
    # Update invoice status
    update_invoice_status(client, invoice_id, "EXTRACTING")
    
    return {"run_id": run["id"], "run_number": run_number, "status": "QUEUED"}


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str = Path(...)):
    """Retrieve an intake draft by ID."""
    _validate_uuid(draft_id)
    client = _get_client()
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
    client = _get_client()
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