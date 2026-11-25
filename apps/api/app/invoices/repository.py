from typing import Optional, List, Dict, Any
from app.config import settings
from supabase import create_client, Client


class RepositoryError(Exception):
    pass


def _client() -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RepositoryError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured "
            "for backend database operations."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


# ==================== Intake Drafts ====================

def find_draft_by_sha256(client: Client, sha256: str) -> dict | None:
    """Return an existing intake draft matching the SHA-256, if any."""
    result = client.table("invoice_intake_drafts").select("*").eq("sha256", sha256).execute()
    data = result.data or []
    if not data:
        return None
    return data[0]


def insert_intake_draft(client: Client, draft: dict) -> dict:
    """Insert a new intake draft and return the inserted row."""
    result = client.table("invoice_intake_drafts").insert(draft).execute()
    if getattr(result, "error", None):
        raise RepositoryError(f"Insert failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Insert returned no data")
    return data[0]


def update_draft_status(client: Client, draft_id: str, status: str) -> dict:
    """Update the processing_status of an intake draft."""
    result = (
        client.table("invoice_intake_drafts")
        .update({"processing_status": status, "updated_at": "now()"})
        .eq("id", draft_id)
        .execute()
    )
    if getattr(result, "error", None):
        raise RepositoryError(f"Update failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Update returned no data")
    return data[0]


# ==================== Invoices ====================

def list_invoices(
    client: Client,
    client_id: str,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """List invoices with pagination and filtering."""
    query = client.table("invoices").select("*", count="exact").eq("client_id", client_id)
    
    if search:
        query = query.or_(
            f"invoice_number.ilike.%{search}%,"
            f"supplier_name.ilike.%{search}%,"
            f"po_number.ilike.%{search}%"
        )
    if status:
        query = query.eq("processing_status", status)
    
    # Order by created_at desc
    query = query.order("created_at", desc=True)
    
    # Pagination
    start = (page - 1) * page_size
    end = start + page_size - 1
    query = query.range(start, end)
    
    result = query.execute()
    return {
        "invoices": result.data or [],
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


def get_invoice(client: Client, invoice_id: str) -> Optional[dict]:
    """Get a single invoice by ID with related data."""
    result = client.table("invoices").select("*").eq("id", invoice_id).execute()
    data = result.data or []
    if not data:
        return None
    invoice = data[0]
    
    # Fetch line items
    items_result = client.table("invoice_items").select("*").eq("invoice_id", invoice_id).order("line_number").execute()
    invoice["items"] = items_result.data or []
    
    # Fetch documents
    docs_result = client.table("invoice_documents").select("*").eq("invoice_id", invoice_id).execute()
    invoice["documents"] = docs_result.data or []
    
    return invoice


def insert_invoice(client: Client, invoice: dict) -> dict:
    """Insert a new invoice and return the inserted row."""
    result = client.table("invoices").insert(invoice).execute()
    if getattr(result, "error", None):
        raise RepositoryError(f"Insert failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Insert returned no data")
    return data[0]


def insert_invoice_items(client: Client, invoice_id: str, items: List[dict]) -> List[dict]:
    """Insert invoice line items."""
    if not items:
        return []
    for item in items:
        item["invoice_id"] = invoice_id
    result = client.table("invoice_items").insert(items).execute()
    if getattr(result, "error", None):
        raise RepositoryError(f"Insert items failed: {result.error}")
    return result.data or []


def insert_invoice_document(client: Client, document: dict) -> dict:
    """Insert an invoice document reference."""
    result = client.table("invoice_documents").insert(document).execute()
    if getattr(result, "error", None):
        raise RepositoryError(f"Insert document failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Insert document returned no data")
    return data[0]


def update_invoice_status(client: Client, invoice_id: str, processing_status: str, approval_status: Optional[str] = None) -> dict:
    """Update invoice processing and/or approval status."""
    update_data = {"processing_status": processing_status, "updated_at": "now()"}
    if approval_status:
        update_data["approval_status"] = approval_status
    result = (
        client.table("invoices")
        .update(update_data)
        .eq("id", invoice_id)
        .execute()
    )
    if getattr(result, "error", None):
        raise RepositoryError(f"Update failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Update returned no data")
    return data[0]


# ==================== Processing Runs ====================

def list_processing_runs(
    client: Client,
    client_id: str,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """List processing runs with pagination."""
    # Join with invoices to filter by client_id
    result = client.table("processing_runs").select(
        "*, invoices!inner(client_id)",
        count="exact"
    ).eq("invoices.client_id", client_id).order("created_at", desc=True).execute()
    
    runs = result.data or []
    
    # Manual pagination since we can't use range with join easily
    total = len(runs)
    start = (page - 1) * page_size
    end = start + page_size
    
    return {
        "runs": runs[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_processing_run(client: Client, run_id: str) -> Optional[dict]:
    """Get a single processing run with stage events."""
    result = client.table("processing_runs").select("*").eq("id", run_id).execute()
    data = result.data or []
    if not data:
        return None
    run = data[0]
    
    # Fetch validation results (stage events)
    vr_result = client.table("validation_results").select("*").eq("processing_run_id", run_id).order("created_at").execute()
    run["stage_events"] = vr_result.data or []
    
    return run


def insert_processing_run(client: Client, run: dict) -> dict:
    """Insert a new processing run."""
    result = client.table("processing_runs").insert(run).execute()
    if getattr(result, "error", None):
        raise RepositoryError(f"Insert failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Insert returned no data")
    return data[0]


def update_processing_run(client: Client, run_id: str, status: str, summary: Optional[dict] = None, completed_at: Optional[str] = None) -> dict:
    """Update processing run status."""
    update_data = {"status": status}
    if summary is not None:
        update_data["summary"] = summary
    if completed_at:
        update_data["completed_at"] = completed_at
    elif status in ("COMPLETED", "FAILED"):
        update_data["completed_at"] = "now()"
    if status == "RUNNING":
        update_data["started_at"] = "now()"
    
    result = (
        client.table("processing_runs")
        .update(update_data)
        .eq("id", run_id)
        .execute()
    )
    if getattr(result, "error", None):
        raise RepositoryError(f"Update failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Update returned no data")
    return data[0]


def insert_validation_result(client: Client, validation: dict) -> dict:
    """Insert a validation result (stage event)."""
    result = client.table("validation_results").insert(validation).execute()
    if getattr(result, "error", None):
        raise RepositoryError(f"Insert validation failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Insert validation returned no data")
    return data[0]


# ==================== Suppliers ====================

def list_suppliers(
    client: Client,
    client_id: str,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """List suppliers with pagination and filtering."""
    query = client.table("suppliers").select("*", count="exact").eq("client_id", client_id)
    
    if search:
        query = query.or_(
            f"legal_name.ilike.%{search}%,"
            f"trade_name.ilike.%{search}%,"
            f"gstin.ilike.%{search}%,"
            f"vendor_code.ilike.%{search}%"
        )
    if status:
        query = query.eq("status", status)
    
    query = query.order("created_at", desc=True)
    
    start = (page - 1) * page_size
    end = start + page_size - 1
    query = query.range(start, end)
    
    result = query.execute()
    return {
        "suppliers": result.data or [],
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


# ==================== Approvals ====================

def list_approvals(
    client: Client,
    client_id: str,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """List approval tasks with pagination and filtering."""
    # Join with invoices to filter by client_id
    query = client.table("approvals").select(
        "*, invoices!inner(client_id, invoice_number, supplier_name, total_amount, currency)",
        count="exact"
    ).eq("invoices.client_id", client_id)
    
    if status:
        query = query.eq("status", status)
    
    query = query.order("assigned_at", desc=True)
    
    start = (page - 1) * page_size
    end = start + page_size - 1
    query = query.range(start, end)
    
    result = query.execute()
    return {
        "approvals": result.data or [],
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


def get_approval(client: Client, approval_id: str) -> Optional[dict]:
    """Get a single approval by ID."""
    result = client.table("approvals").select("*").eq("id", approval_id).execute()
    data = result.data or []
    if not data:
        return None
    return data[0]


# ==================== Exceptions ====================

def list_exceptions(
    client: Client,
    client_id: str,
    page: int = 1,
    page_size: int = 20,
    severity: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """List exceptions with pagination and filtering."""
    query = client.table("exceptions").select(
        "*, invoices!inner(client_id, invoice_number, supplier_name)",
        count="exact"
    ).eq("invoices.client_id", client_id)
    
    if severity:
        query = query.eq("severity", severity)
    if status:
        query = query.eq("status", status)
    
    query = query.order("created_at", desc=True)
    
    start = (page - 1) * page_size
    end = start + page_size - 1
    query = query.range(start, end)
    
    result = query.execute()
    return {
        "exceptions": result.data or [],
        "total": result.count or 0,
        "page": page,
        "page_size": page_size,
    }


def get_exception(client: Client, exception_id: str) -> Optional[dict]:
    """Get a single exception by ID."""
    result = client.table("exceptions").select("*").eq("id", exception_id).execute()
    data = result.data or []
    if not data:
        return None
    return data[0]