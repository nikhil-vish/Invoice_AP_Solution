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
from decimal import Decimal, InvalidOperation
from typing import Any, Optional
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException, status, Path, Query, Header
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
    transition_invoice,
    list_lifecycle_events,
    record_lifecycle_event,
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
    insert_approval,
    insert_exception,
    get_draft_by_id,
    get_invoice_by_draft_id,
    convert_draft_to_invoice,
    update_draft_conversion,
    create_invoice_for_draft,
    get_draft_by_invoice_id,
    resolve_demo_workspace,
    update_draft_and_invoice,
    duplicate_invoice_exists,
    phase4_context,
    next_analysis_attempt,
    insert_invoice_analysis,
    latest_invoice_analysis,
    invoice_analysis_history,
    ai_dashboard_metrics,
    RepositoryError,
)
from app.config import settings
from supabase import create_client
from app.invoices.ai_analysis import analyse_invoice
from app.invoices.ai_extract import AIExtractionError
from app.invoices.validation import validate_invoice
from app.invoices.matching import phase4_checks

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])

ALLOWED_CONTENT_TYPES = {"application/pdf"}

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


class ReviewFieldValue(BaseModel):
    value: Any = None
    status: str = "edited"


class ReviewLineItem(BaseModel):
    description: Optional[str] = None
    hsn_sac: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    taxable_value: Optional[Decimal] = None
    cgst: Optional[Decimal] = None
    sgst: Optional[Decimal] = None
    igst: Optional[Decimal] = None


class DraftSaveRequest(BaseModel):
    fields: dict[str, ReviewFieldValue]
    line_items: list[ReviewLineItem]


class PurchaseOrderLine(BaseModel):
    description: str
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    taxable_value: Optional[Decimal] = None


class PurchaseOrderImportRequest(BaseModel):
    po_number: str
    supplier_id: str
    total_amount: Decimal
    currency: str = "INR"
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    items: list[PurchaseOrderLine] = []


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


def _demo_client_id(client) -> str:
    return resolve_demo_workspace(client)[0]


def _verified_reviewer_id(authorization: str | None) -> str:
    """Validate a Supabase Auth JWT; never trust a client-provided reviewer ID."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A Supabase Auth bearer token is required.")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        auth_client = create_client(settings.supabase_url, settings.supabase_anon_key)
        response = auth_client.auth.get_user(token)
        user = getattr(response, "user", None)
        if not user or not user.id:
            raise ValueError("No authenticated user")
        return str(user.id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired Supabase Auth token.") from exc


def _review_fields(values: dict[str, ReviewFieldValue]) -> dict:
    """Normalise frontend field wrappers and reject invalid date/amount values."""
    from app.invoices.fields import DATE_FIELDS, HEADER_FIELDS, MONEY_FIELDS

    result: dict[str, Any] = {key: None for key in HEADER_FIELDS}
    for key, wrapped in values.items():
        if key not in result:
            continue
        value = wrapped.value
        if isinstance(value, str):
            value = value.strip() or None
        if value is None:
            result[key] = None
            continue
        if key in MONEY_FIELDS:
            try:
                result[key] = str(Decimal(str(value)))
            except (InvalidOperation, ValueError):
                raise HTTPException(status_code=422, detail=f"{key} must be a valid amount.")
        elif key in DATE_FIELDS:
            try:
                from datetime import date
                result[key] = date.fromisoformat(str(value)).isoformat()
            except ValueError:
                raise HTTPException(status_code=422, detail=f"{key} must use YYYY-MM-DD.")
        else:
            result[key] = str(value)
    return result


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
            client_id=_demo_client_id(client),
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

# Lightweight import only: this supplies matching context, not procurement workflows.
purchase_orders_router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


@purchase_orders_router.post("/import")
async def import_purchase_order(request: PurchaseOrderImportRequest):
    client = _get_client()
    _, entity_id = resolve_demo_workspace(client)
    try:
        po = (client.table("purchase_orders").insert({
            "client_entity_id": entity_id, "supplier_id": request.supplier_id, "po_number": request.po_number,
            "currency": request.currency.upper(), "total_amount": str(request.total_amount), "status": "APPROVED",
            "valid_from": request.valid_from, "valid_to": request.valid_to,
        }).execute().data or [None])[0]
        if not po:
            raise RepositoryError("PO import returned no record")
        lines = [{"purchase_order_id": po["id"], "line_number": index + 1, "description": line.description,
                  "quantity": str(line.quantity) if line.quantity is not None else None,
                  "unit_price": str(line.unit_price) if line.unit_price is not None else None,
                  "taxable_value": str(line.taxable_value) if line.taxable_value is not None else None}
                 for index, line in enumerate(request.items)]
        if lines:
            client.table("purchase_order_items").insert(lines).execute()
        return {"purchase_order": po, "line_count": len(lines)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not import purchase order: {exc}")


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
            client_id=_demo_client_id(client),
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
            client_id=_demo_client_id(client),
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
    authorization: Optional[str] = Header(None),
):
    """Process an approval action (APPROVE, REJECT, RETURN_FOR_INFORMATION)."""
    _validate_uuid(approval_id)
    reviewer_id = _verified_reviewer_id(authorization)
    client = _get_client()
    if not request:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A request body is required.")
    try:
        result = action_approval(
            client,
            approval_id=approval_id,
            action=request.action.upper(),
            comment=request.comment,
            actor_id=reviewer_id,
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
            client_id=_demo_client_id(client),
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
    authorization: Optional[str] = Header(None),
):
    """Assign an exception to an owner team."""
    _validate_uuid(exception_id)
    reviewer_id = _verified_reviewer_id(authorization)
    client = _get_client()
    if not request:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A request body is required.")
    try:
        result = assign_exception(
            client,
            exception_id=exception_id,
            owner_team=request.owner_team,
            actor_id=reviewer_id,
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
    authorization: Optional[str] = Header(None),
):
    """Resolve an exception with a mandatory resolution comment."""
    _validate_uuid(exception_id)
    reviewer_id = _verified_reviewer_id(authorization)
    client = _get_client()
    if not request:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A request body is required.")
    try:
        result = resolve_exception(
            client,
            exception_id=exception_id,
            resolution_comment=request.resolution_comment,
            actor_id=reviewer_id,
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
router.include_router(purchase_orders_router)
router.include_router(approvals_router)
router.include_router(exceptions_router)


# ==================== Dashboard Metrics ====================

@router.get("/dashboard/metrics")
async def dashboard_metrics(date_from: Optional[str] = Query(None), date_to: Optional[str] = Query(None), risk_level: Optional[str] = Query(None), invoice_status: Optional[str] = Query(None)):
    """Return dashboard metrics for the overview page."""
    client = _get_client()
    try:
        return ai_dashboard_metrics(client, _demo_client_id(client), date_from, date_to, risk_level, invoice_status)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch metrics: {exc}",
        )



@router.get("/config/status")
async def config_status():
    """Return safe integration status booleans for the Settings page.

    Never exposes API keys, service-role credentials, or sensitive values.
    """
    return {
        "supabase_configured": bool(settings.supabase_url and settings.supabase_service_role_key),
        "storage_bucket_configured": bool(settings.supabase_storage_bucket),
        "openrouter_configured": bool(settings.openrouter_api_key and settings.openrouter_model),
        "ai_extraction_enabled": settings.ai_extraction_enabled,
        "ai_reasoning_enabled": settings.ai_reasoning_enabled,
    }


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

    try:
        invoice = create_invoice_for_draft(client, draft)
    except RepositoryError as exc:
        # The upload is not successful unless the primary invoice register is
        # available too. The retained draft records the recoverable intake.
        update_draft_conversion(client, draft["id"], None, "FAILED")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not create invoice record: {exc}",
        )

    extracted = extraction.get("fields", {})
    line_items = extraction.get("line_items", [])
    response = {
        "draft_id": draft["id"],
        "invoice_id": invoice["id"],
        "status": invoice.get("processing_status", "DRAFT"),
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
            client_id=_demo_client_id(client),
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


async def _run_analysis(invoice_id: str, run_id: str) -> None:
    """Background worker: deterministic checks first, then advisory AI analysis.
    AI is optional — if not enabled/configured, deterministic-only path is taken.
    """
    client = _get_client()
    update_processing_run(client, run_id, "RUNNING")
    transition_invoice(client, invoice_id, "PROCESSING", "ANALYSIS_RUNNING", "ANALYSIS_STARTED", processing_run_id=run_id)
    invoice = get_invoice(client, invoice_id)
    if not invoice:
        return
    checks = validate_invoice(invoice, invoice.get("items", []), duplicate_invoice_exists(client, invoice))
    po, history = phase4_context(client, invoice)
    checks.extend(phase4_checks(invoice, invoice.get("items", []), po, history))
    for check in checks:
        insert_validation_result(client, {"processing_run_id": run_id, "stage": "PHASE_2A", **check})

    hard_failure = any(result["status"] == "FAILED" for result in checks)

    ai_enabled = settings.ai_extraction_enabled and bool(settings.openrouter_api_key) and bool(settings.openrouter_model)
    ai_completed = False
    recommendation = None
    risk_level = None
    provider_error = None

    if ai_enabled:
        attempt = next_analysis_attempt(client, invoice_id)
        try:
            analysis = await analyse_invoice(invoice, invoice.get("items", []), checks)
            insert_invoice_analysis(client, {"invoice_id": invoice_id, "processing_run_id": run_id, "attempt_number": attempt,
                "status": "COMPLETED", **analysis.model_dump(mode="json")})
            ai_completed = True
            recommendation = analysis.recommendation
            risk_level = analysis.risk_level
        except Exception as exc:
            insert_invoice_analysis(client, {"invoice_id": invoice_id, "processing_run_id": run_id, "attempt_number": attempt,
                "status": "FAILED", "findings": [], "validation_results": checks, "provider_error": str(exc)})
            provider_error = str(exc)
    else:
        # AI intentionally disabled / not configured — no analysis attempt
        pass

    # Stage decision — honest, no fabricated recommendation
    if not ai_completed:
        stage = "REVIEW_REQUIRED" if hard_failure else "HUMAN_APPROVAL"
    elif recommendation == "REQUEST_CLARIFICATION":
        stage = "CLARIFICATION_REQUIRED"
    elif hard_failure or risk_level == "HIGH" or recommendation == "REJECT":
        stage = "REVIEW_REQUIRED"
    else:
        stage = "HUMAN_APPROVAL"

    # WP4: runtime actionable workflow records — idempotent, never block processing
    try:
        if hard_failure:
            # Every deterministic failure is independently actionable.  The
            # repository deduplicates retries by invoice and rule code.
            for failed_check in (c for c in checks if c.get("status") == "FAILED"):
                code = failed_check.get("rule_code", "DETERMINISTIC_FAILURE")
                insert_exception(
                    client, invoice_id, run_id, code, "HIGH",
                    failed_check.get("message") or f"Deterministic check failed: {code}",
                    owner_team="tax-team",
                )
        elif ai_completed and recommendation == "REQUEST_CLARIFICATION":
            insert_exception(
                client,
                invoice_id,
                run_id,
                "AI_CLARIFICATION_REQUESTED",
                "MEDIUM",
                "AI requests clarification before approval",
                owner_team="tax-team",
            )
        else:
            # No active pending approval → create one for human review
            existing_approval = client.table("approvals").select("id").eq("invoice_id", invoice_id).eq("status", "PENDING").execute().data or []
            if not existing_approval:
                insert_approval(client, invoice_id, processing_run_id=run_id)
    except Exception as exc:
        # Never let workflow-record creation block deterministic processing or raise to user
        pass

    transition_invoice(client, invoice_id, "PENDING_APPROVAL", stage, "ANALYSIS_COMPLETED",
                       processing_run_id=run_id, payload={"recommendation": recommendation,
                       "risk_level": risk_level, "deterministic_failures": hard_failure, "ai_enabled": ai_enabled, "provider_error": provider_error})

    run_status = "COMPLETED" if ai_completed or not ai_enabled else "FAILED"
    update_processing_run(client, run_id, run_status, {"recommendation": recommendation, "risk_level": risk_level, "deterministic_failures": hard_failure, "ai_enabled": ai_enabled, "provider_error": provider_error})


async def _queue_analysis(background_tasks: BackgroundTasks, invoice_id: str, trigger: str) -> dict:
    """Create exactly one queued run; used for submit, correction resubmission and retry."""
    client = _get_client()
    invoice = get_invoice(client, invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")
    if invoice.get("processing_status") in {"QUEUED", "PROCESSING"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Processing is already active for this invoice.")
    existing = client.table("processing_runs").select("run_number").eq("invoice_id", invoice_id).order("run_number", desc=True).limit(1).execute()
    run_number = (existing.data[0]["run_number"] + 1) if existing.data else 1
    run = insert_processing_run(client, {"invoice_id": invoice_id, "run_number": run_number, "status": "QUEUED", "triggered_by": trigger})
    event = "INVOICE_SUBMITTED" if trigger == "MANUAL_UPLOAD" else ("INVOICE_RESUBMITTED" if trigger == "CLARIFICATION_RESUBMISSION" else "ANALYSIS_RETRIED")
    # Submission is a durable user-visible state; background work then moves it
    # to PROCESSING.  There is no second manual submit step.
    update_invoice_status(client, invoice_id, "SUBMITTED")
    client.table("invoices").update({"current_stage": "SUBMITTED"}).eq("id", invoice_id).execute()
    record_lifecycle_event(client, invoice_id, invoice.get("processing_status"), "SUBMITTED", "SUBMITTED",
                           event, processing_run_id=run["id"])
    background_tasks.add_task(_run_analysis, invoice_id, run["id"])
    return {"run_id": run["id"], "run_number": run_number, "status": "SUBMITTED"}


@router.post("/{invoice_id}/process")
async def process_invoice(background_tasks: BackgroundTasks, invoice_id: str = Path(...)):
    """Start or retry invoice processing idempotently."""
    _validate_uuid(invoice_id)
    return await _queue_analysis(background_tasks, invoice_id, "MANUAL_UPLOAD")


@router.post("/{invoice_id}/analysis")
async def retry_analysis(background_tasks: BackgroundTasks, invoice_id: str = Path(...)):
    """Explicit retry; creates a new processing run and preserves prior analysis history."""
    _validate_uuid(invoice_id)
    return await _queue_analysis(background_tasks, invoice_id, "MANUAL_RETRY")


@router.post("/{invoice_id}/resubmit")
async def resubmit_invoice(background_tasks: BackgroundTasks, invoice_id: str = Path(...)):
    """Queue a corrected invoice after a reviewer requested clarification."""
    _validate_uuid(invoice_id)
    return await _queue_analysis(background_tasks, invoice_id, "CLARIFICATION_RESUBMISSION")


@router.get("/{invoice_id}/lifecycle")
async def invoice_lifecycle(invoice_id: str = Path(...)):
    _validate_uuid(invoice_id)
    return {"events": list_lifecycle_events(_get_client(), invoice_id)}


@router.get("/{invoice_id}/analysis/latest")
async def get_latest_analysis(invoice_id: str = Path(...)):
    _validate_uuid(invoice_id)
    result = latest_invoice_analysis(_get_client(), invoice_id)
    if not result:
        raise HTTPException(status_code=404, detail="No analysis has been generated for this invoice.")
    return result


@router.get("/{invoice_id}/analysis/history")
async def get_analysis_history(invoice_id: str = Path(...)):
    _validate_uuid(invoice_id)
    return {"analyses": invoice_analysis_history(_get_client(), invoice_id)}


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
    invoice = get_invoice(client, draft["converted_invoice_id"]) if draft.get("converted_invoice_id") else None
    return {
        "draft_id": draft["id"],
        "invoice_id": draft.get("converted_invoice_id"),
        "status": (invoice or draft)["processing_status"],
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
async def save_draft(request: DraftSaveRequest | None = None, draft_id: str = Path(...)):
    """Persist reviewed fields and line items to the draft and primary invoice."""
    _validate_uuid(draft_id)
    if request is None:
        raise HTTPException(status_code=422, detail="Request body is required.")
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
    fields = _review_fields(request.fields)
    line_items = [item.model_dump(mode="json") for item in request.line_items]
    try:
        invoice = update_draft_and_invoice(client, data[0], fields, line_items)
    except RepositoryError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Save failed: {exc}",
        )
    return {"draft_id": draft_id, "invoice_id": invoice["id"], "status": "DRAFT", "saved": True}


@router.post("/drafts/{draft_id}/convert")
async def convert_draft(
    draft_id: str = Path(...),
):
    """Convert a saved intake draft into a business invoice record.

    Idempotent: calling more than once returns the same invoice.
    Requires the draft to have been saved (status READY_FOR_VALIDATION).
    """
    _validate_uuid(draft_id)
    client = _get_client()

    try:
        draft = get_draft_by_id(client, draft_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database query failed: {exc}",
        )
    if not draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draft not found.",
        )

    # Require the draft to have been saved/reviewed before conversion
    if draft.get("processing_status") != "READY_FOR_VALIDATION":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Draft has not been saved for review. Save the draft first.",
        )

    try:
        result = convert_draft_to_invoice(
            client,
            draft_id=draft_id,
        )
    except RepositoryError as exc:
        # Mark draft as failed on conversion error
        try:
            update_draft_conversion(client, draft_id, None, "FAILED")
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT
            if "not configured" in str(exc) or "not found" in str(exc).lower()
            else status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Conversion failed: {exc}",
        )

    return {
        "draft_id": draft_id,
        "invoice_id": result["invoice_id"],
        "invoice_number": result.get("invoice_number"),
        "status": result["status"],
        "message": "Draft converted to invoice successfully"
        if result["status"] == "converted"
        else "Draft was already converted to this invoice.",
    }


class CopilotRequest(BaseModel):
    question: str
    invoice_id: Optional[str] = None


@router.post("/copilot")
async def copilot(req: CopilotRequest, authorization: Optional[str] = Header(None)):
    _verified_reviewer_id(authorization)
    client = _get_client()
    ctx: dict[str, Any] = {}
    if req.invoice_id:
        _validate_uuid(req.invoice_id)
        inv = get_invoice(client, req.invoice_id)
        if not inv:
            raise HTTPException(status_code=404, detail="Invoice not found.")
        ctx["invoice"] = inv
        ctx["analysis"] = latest_invoice_analysis(client, req.invoice_id)
        po, history = phase4_context(client, inv)
        ctx["purchase_order"] = po
        ctx["supplier_history"] = history
        ctx["exceptions"] = list_exceptions(client, inv.get("client_id"), page_size=20)["exceptions"]
    else:
        cid, _ = resolve_demo_workspace(client)
        ctx["invoices"] = list_invoices(client, cid, page_size=25)["invoices"]
        ctx["approvals"] = list_approvals(client, cid, page_size=25)["approvals"]
        ctx["exceptions"] = list_exceptions(client, cid, page_size=25)["exceptions"]
    from app.invoices.copilot import answer
    try:
        text = await answer(req.question, ctx)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"answer": text}
