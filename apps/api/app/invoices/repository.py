from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any
from app.config import settings
from supabase import create_client, Client


class RepositoryError(Exception):
    pass


DEMO_WORKSPACE_NAME = "Invoice Intelligence Demo Workspace"


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
            f"supplier_legal_name.ilike.%{search}%,"
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
    invoices = result.data or []
    invoice_ids = [row["id"] for row in invoices]
    drafts_by_invoice: dict[str, str] = {}
    if invoice_ids:
        drafts = (
            client.table("invoice_intake_drafts")
            .select("id, converted_invoice_id")
            .in_("converted_invoice_id", invoice_ids)
            .execute()
            .data
            or []
        )
        drafts_by_invoice = {
            row["converted_invoice_id"]: row["id"]
            for row in drafts
            if row.get("converted_invoice_id")
        }
    for invoice in invoices:
        invoice["draft_id"] = drafts_by_invoice.get(invoice["id"])
    return {
        "invoices": invoices,
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
    update_data = {
        "processing_status": processing_status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
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


def duplicate_invoice_exists(client: Client, invoice: dict) -> bool:
    gstin, number = invoice.get("supplier_gstin"), invoice.get("invoice_number")
    if not gstin or not number:
        return False
    rows = (client.table("invoices").select("id").eq("supplier_gstin", gstin)
        .eq("invoice_number", number).neq("id", invoice["id"]).execute().data or [])
    return bool(rows)


def next_analysis_attempt(client: Client, invoice_id: str) -> int:
    rows = (client.table("invoice_ai_analyses").select("attempt_number").eq("invoice_id", invoice_id)
        .order("attempt_number", desc=True).limit(1).execute().data or [])
    return (rows[0]["attempt_number"] if rows else 0) + 1


def insert_invoice_analysis(client: Client, payload: dict) -> dict:
    result = client.table("invoice_ai_analyses").insert(payload).execute()
    data = result.data or []
    if not data:
        raise RepositoryError("Invoice analysis insert returned no data")
    return data[0]


def latest_invoice_analysis(client: Client, invoice_id: str) -> dict | None:
    rows = (client.table("invoice_ai_analyses").select("*").eq("invoice_id", invoice_id)
        .order("created_at", desc=True).limit(1).execute().data or [])
    return rows[0] if rows else None


def invoice_analysis_history(client: Client, invoice_id: str) -> list[dict]:
    return (client.table("invoice_ai_analyses").select("*").eq("invoice_id", invoice_id)
        .order("created_at", desc=True).execute().data or [])


def ai_dashboard_metrics(client: Client, client_id: str, date_from: str | None = None, date_to: str | None = None,
                         risk_level: str | None = None, invoice_status: str | None = None) -> dict:
    """Aggregate persisted invoice, analysis, run, and approval records in Python."""
    invoice_query = client.table("invoices").select("id,processing_status,created_at").eq("client_id", client_id)
    if date_from: invoice_query = invoice_query.gte("created_at", date_from)
    if date_to: invoice_query = invoice_query.lte("created_at", date_to)
    if invoice_status: invoice_query = invoice_query.eq("processing_status", invoice_status)
    invoices = invoice_query.execute().data or []
    ids = [row["id"] for row in invoices]
    empty = {"total_invoices_analysed": 0, "recommendations": {}, "human_decisions": {}, "comparison": {}, "override_rate": None, "risk_distribution": {}, "common_findings": [], "average_submission_to_decision_hours": None}
    if not ids: return empty
    analyses = client.table("invoice_ai_analyses").select("*").in_("invoice_id", ids).eq("status", "COMPLETED").order("created_at", desc=True).execute().data or []
    latest = {}
    for analysis in analyses:
        latest.setdefault(analysis["invoice_id"], analysis)
    if risk_level: latest = {key: value for key, value in latest.items() if value.get("risk_level") == risk_level}
    active_ids = list(latest)
    if not active_ids: return empty
    approvals = client.table("approvals").select("invoice_id,status,decided_at").in_("invoice_id", active_ids).in_("status", ["APPROVED", "REJECTED"]).order("decided_at", desc=True).execute().data or []
    final = {}
    for approval in approvals:
        final.setdefault(approval["invoice_id"], approval)
    runs = client.table("processing_runs").select("invoice_id,created_at").in_("invoice_id", active_ids).order("created_at").execute().data or []
    submitted = {}
    for run in runs: submitted.setdefault(run["invoice_id"], run.get("created_at"))
    recommendations, human, comparison, risks, findings = {}, {}, {}, {}, {}
    paired = overrides = 0; durations = []
    for invoice_id, analysis in latest.items():
        rec, risk = analysis.get("recommendation"), analysis.get("risk_level")
        recommendations[rec] = recommendations.get(rec, 0) + 1
        risks[risk] = risks.get(risk, 0) + 1
        for finding in analysis.get("findings") or []:
            key = finding.get("category") or "uncategorised"
            findings[key] = findings.get(key, 0) + 1
        for validation in analysis.get("validation_results") or []:
            if validation.get("status") == "FAILED":
                key = validation.get("rule_code") or "validation_failure"
                findings[key] = findings.get(key, 0) + 1
        decision = final.get(invoice_id)
        if decision:
            outcome = decision["status"]; human[outcome] = human.get(outcome, 0) + 1
            comparison[f"{rec} → {outcome}"] = comparison.get(f"{rec} → {outcome}", 0) + 1
            paired += 1
            if (rec == "APPROVE" and outcome != "APPROVED") or (rec == "REJECT" and outcome != "REJECTED") or rec == "REQUEST_CLARIFICATION": overrides += 1
            if submitted.get(invoice_id) and decision.get("decided_at"):
                durations.append((datetime.fromisoformat(decision["decided_at"].replace("Z", "+00:00")) - datetime.fromisoformat(submitted[invoice_id].replace("Z", "+00:00"))).total_seconds() / 3600)
    return {"total_invoices_analysed": len(latest), "recommendations": recommendations, "human_decisions": human,
            "comparison": comparison, "override_rate": round(overrides / paired * 100, 2) if paired else None,
            "risk_distribution": risks, "common_findings": [{"category": key, "count": value} for key, value in sorted(findings.items(), key=lambda item: item[1], reverse=True)[:10]],
            "average_submission_to_decision_hours": round(sum(durations) / len(durations), 2) if durations else None}


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


# ==================== Exception Actions ====================

def assign_exception(client: Client, exception_id: str, owner_team: str, actor_id: str) -> dict:
    """Assign an exception to an owner team."""
    result = client.table("exceptions").update({
        "owner_team": owner_team,
        "status": "IN_REVIEW",
        "updated_at": "now()",
    }).eq("id", exception_id).execute()
    if getattr(result, "error", None):
        raise RepositoryError(f"Assign failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Exception not found or assign returned no data")
    
    # Log to audit
    client.table("audit_logs").insert({
        "invoice_id": data[0].get("invoice_id"),
        "actor_type": "USER",
        "actor_id": actor_id,
        "action": "EXCEPTION_ASSIGNED",
        "after_state": {"owner_team": owner_team, "status": "IN_REVIEW"},
    }).execute()
    
    return data[0]


def resolve_exception(client: Client, exception_id: str, resolution_comment: str, actor_id: str) -> dict:
    """Resolve an exception with a mandatory resolution comment."""
    # First check current state
    current = get_exception(client, exception_id)
    if not current:
        raise RepositoryError("Exception not found")
    
    if current.get("status") in ("RESOLVED", "CLOSED"):
        raise RepositoryError("Exception already resolved. Use reopen workflow to modify.")
    
    result = client.table("exceptions").update({
        "status": "RESOLVED",
        "resolution": {"comment": resolution_comment, "resolved_by": actor_id},
        "resolved_at": "now()",
        "updated_at": "now()",
    }).eq("id", exception_id).execute()
    if getattr(result, "error", None):
        raise RepositoryError(f"Resolve failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Exception not found or resolve returned no data")
    
    # Log to audit
    client.table("audit_logs").insert({
        "invoice_id": data[0].get("invoice_id"),
        "actor_type": "USER",
        "actor_id": actor_id,
        "action": "EXCEPTION_RESOLVED",
        "after_state": {"resolution": {"comment": resolution_comment, "resolved_by": actor_id}, "status": "RESOLVED"},
    }).execute()
    
    return data[0]


# ==================== Approval Actions ====================

def get_invoice_validation_status(client: Client, invoice_id: str) -> dict:
    """Get the latest validation status for an invoice."""
    # Get the latest processing run
    runs_result = client.table("processing_runs").select("*").eq("invoice_id", invoice_id).order("run_number", desc=True).limit(1).execute()
    runs = runs_result.data or []
    if not runs:
        return {"ready_for_approval": False, "has_hard_stop_exceptions": False, "validation_passed": False}
    
    run = runs[0]
    run_id = run["id"]
    
    # Check validation results
    vr_result = client.table("validation_results").select("*").eq("processing_run_id", run_id).execute()
    validations = vr_result.data or []
    
    # Check for hard-stop exceptions (CRITICAL severity, not resolved)
    exc_result = client.table("exceptions").select("*").eq("invoice_id", invoice_id).in_("status", ["OPEN", "IN_REVIEW", "AWAITING_RESPONSE"]).execute()
    exceptions = exc_result.data or []
    hard_stop_exceptions = [e for e in exceptions if e.get("severity") == "CRITICAL"]
    
    validation_passed = all(v.get("status") in ("PASSED", "SKIPPED") for v in validations)
    
    return {
        "ready_for_approval": validation_passed and len(hard_stop_exceptions) == 0,
        "has_hard_stop_exceptions": len(hard_stop_exceptions) > 0,
        "validation_passed": validation_passed,
        "hard_stop_count": len(hard_stop_exceptions),
    }


def action_approval(
    client: Client,
    approval_id: str,
    action: str,
    comment: Optional[str],
    actor_id: str,
) -> dict:
    """Process an approval action (APPROVE, REJECT, RETURN_FOR_INFORMATION)."""
    valid_actions = ["APPROVE", "REJECT", "RETURN_FOR_INFORMATION"]
    if action not in valid_actions:
        raise RepositoryError(f"Invalid action. Must be one of: {valid_actions}")
    
    if action in ("REJECT", "RETURN_FOR_INFORMATION") and not comment:
        raise RepositoryError(f"Comment is required for {action} action")
    
    # Get approval
    approval = get_approval(client, approval_id)
    if not approval:
        raise RepositoryError("Approval not found")
    
    if approval.get("status") != "PENDING":
        raise RepositoryError(f"Approval already processed (status: {approval['status']})")
    
    invoice_id = approval["invoice_id"]
    
    # For APPROVE action, check validation status and hard-stop exceptions
    if action == "APPROVE":
        validation_status = get_invoice_validation_status(client, invoice_id)
        if not validation_status["ready_for_approval"]:
            if validation_status["has_hard_stop_exceptions"]:
                raise RepositoryError(f"Cannot approve: {validation_status['hard_stop_count']} unresolved CRITICAL exception(s) exist")
            raise RepositoryError("Cannot approve: validation not passed")
    
    # Map action to approval status
    status_map = {
        "APPROVE": "APPROVED",
        "REJECT": "REJECTED",
        "RETURN_FOR_INFORMATION": "REASSIGNED",  # Using REASSIGNED as "returned for info"
    }
    new_status = status_map[action]
    
    # Update approval
    update_data = {
        "status": new_status,
        "decision_comment": comment,
        "decided_at": "now()",
    }
    result = client.table("approvals").update(update_data).eq("id", approval_id).execute()
    if getattr(result, "error", None):
        raise RepositoryError(f"Approval action failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Approval not found or update returned no data")
    
    # Update invoice approval status
    invoice_approval_status_map = {
        "APPROVE": "APPROVED",
        "REJECT": "REJECTED",
        "RETURN_FOR_INFORMATION": "PENDING",  # Stays pending when returned for info
    }
    client.table("invoices").update({
        "approval_status": invoice_approval_status_map[action],
        "updated_at": "now()",
    }).eq("id", invoice_id).execute()
    
    # Also update processing status if approved
    if action == "APPROVE":
        client.table("invoices").update({
            "processing_status": "APPROVED",
            "updated_at": "now()",
        }).eq("id", invoice_id).execute()
    
    # Log to audit
    client.table("audit_logs").insert({
        "invoice_id": invoice_id,
        "actor_type": "USER",
        "actor_id": actor_id,
        "action": f"APPROVAL_{action}",
        "after_state": {"approval_status": new_status, "comment": comment},
    }).execute()
    
    return data[0]


# ==================== Draft-to-Invoice Conversion ====================

def get_draft_by_id(client: Client, draft_id: str) -> dict | None:
    """Return an intake draft by ID, or None if not found."""
    result = client.table("invoice_intake_drafts").select("*").eq("id", draft_id).execute()
    data = result.data or []
    if not data:
        return None
    return data[0]


def get_invoice_by_draft_id(client: Client, draft_id: str) -> dict | None:
    """Return the invoice already converted from a draft, or None."""
    result = client.table("invoice_intake_drafts").select("converted_invoice_id").eq("id", draft_id).execute()
    data = result.data or []
    if not data or not data[0].get("converted_invoice_id"):
        return None
    invoice_id = data[0]["converted_invoice_id"]
    return get_invoice(client, invoice_id)


def get_draft_by_invoice_id(client: Client, invoice_id: str) -> dict | None:
    result = (
        client.table("invoice_intake_drafts")
        .select("*")
        .eq("converted_invoice_id", invoice_id)
        .execute()
    )
    data = result.data or []
    return data[0] if data else None


def resolve_demo_workspace(client: Client) -> tuple[str, str]:
    """Return the active workspace seeded by migration 0004."""
    clients = (
        client.table("clients")
        .select("id")
        .eq("display_name", DEMO_WORKSPACE_NAME)
        .eq("status", "ACTIVE")
        .execute()
        .data
        or []
    )
    if not clients:
        raise RepositoryError(
            "Demo workspace is missing. Apply migration 0005_unified_invoice_register_schema.sql."
        )
    client_id = clients[0]["id"]
    entities = (
        client.table("client_entities")
        .select("id")
        .eq("client_id", client_id)
        .eq("is_active", True)
        .execute()
        .data
        or []
    )
    if not entities:
        raise RepositoryError("Demo workspace entity is missing. Apply migration 0005_unified_invoice_register_schema.sql.")
    return client_id, entities[0]["id"]


def create_invoice_for_draft(client: Client, draft: dict) -> dict:
    """Create the primary DRAFT invoice and its children for a newly uploaded draft."""
    client_id, client_entity_id = resolve_demo_workspace(client)
    summary = draft.get("extracted_data") or {}
    fields = summary.get("fields") or {}
    invoice = insert_invoice(client, {
        "client_id": client_id,
        "client_entity_id": client_entity_id,
        "supplier_legal_name": fields.get("supplier_legal_name"),
        "supplier_gstin": fields.get("supplier_gstin"),
        "supplier_address": fields.get("supplier_address"),
        "invoice_number": fields.get("invoice_number"),
        "invoice_date": fields.get("invoice_date"),
        "due_date": fields.get("due_date"),
        "buyer_legal_name": fields.get("buyer_legal_name"),
        "buyer_gstin": fields.get("buyer_gstin"),
        "po_number": fields.get("po_number"),
        "currency": fields.get("currency"),
        "taxable_value": fields.get("taxable_value"),
        "cgst_amount": fields.get("cgst"),
        "sgst_amount": fields.get("sgst"),
        "igst_amount": fields.get("igst"),
        "total_tax": fields.get("total_tax"),
        "total_amount": fields.get("invoice_grand_total"),
        "procurement_type": "PO" if fields.get("po_number") else "NON_PO",
        "processing_status": "DRAFT",
        "current_stage": "REVIEW",
        "source_file_sha256": draft["sha256"],
    })
    invoice_id = invoice["id"]
    lines = []
    for number, item in enumerate(summary.get("line_items") or [], start=1):
        lines.append({
            "invoice_id": invoice_id, "line_number": number,
            "description": item.get("description"), "hsn_sac": item.get("hsn_sac"),
            "quantity": item.get("quantity"), "unit_price": item.get("unit_price"),
            "taxable_value": item.get("taxable_value"), "cgst_amount": item.get("cgst"),
            "sgst_amount": item.get("sgst"), "igst_amount": item.get("igst"),
        })
    insert_invoice_items(client, invoice_id, lines)
    insert_invoice_document(client, {
        "invoice_id": invoice_id, "storage_path": draft["storage_path"],
        "original_filename": draft["original_filename"], "mime_type": draft["mime_type"],
        "sha256": draft["sha256"], "document_type": "INVOICE",
        "extraction_method": draft.get("extraction_method"),
    })
    update_draft_conversion(client, draft["id"], invoice_id, "CONVERTED")
    return invoice


def update_draft_and_invoice(client: Client, draft: dict, fields: dict, line_items: list[dict]) -> dict:
    """Persist reviewed fields to the intake snapshot and linked invoice."""
    invoice_id = draft.get("converted_invoice_id")
    if not invoice_id:
        raise RepositoryError("Draft is not linked to an invoice.")
    summary = draft.get("extracted_data") or {}
    summary["fields"] = fields
    summary["line_items"] = line_items
    summary["field_status"] = {key: "found" if value is not None else "missing" for key, value in fields.items()}
    updated_at = datetime.now(timezone.utc).isoformat()
    client.table("invoice_intake_drafts").update({
        "extracted_data": summary, "processing_status": "READY_FOR_VALIDATION", "updated_at": updated_at,
    }).eq("id", draft["id"]).execute()
    client.table("invoices").update({
        "supplier_legal_name": fields.get("supplier_legal_name"), "supplier_gstin": fields.get("supplier_gstin"),
        "supplier_address": fields.get("supplier_address"), "invoice_number": fields.get("invoice_number"),
        "invoice_date": fields.get("invoice_date"), "due_date": fields.get("due_date"),
        "buyer_legal_name": fields.get("buyer_legal_name"), "buyer_gstin": fields.get("buyer_gstin"),
        "po_number": fields.get("po_number"), "currency": fields.get("currency"),
        "taxable_value": fields.get("taxable_value"), "cgst_amount": fields.get("cgst"),
        "sgst_amount": fields.get("sgst"), "igst_amount": fields.get("igst"),
        "total_tax": fields.get("total_tax"), "total_amount": fields.get("invoice_grand_total"),
        "procurement_type": "PO" if fields.get("po_number") else "NON_PO",
        "processing_status": "DRAFT", "current_stage": "REVIEW", "updated_at": updated_at,
    }).eq("id", invoice_id).execute()
    client.table("invoice_items").delete().eq("invoice_id", invoice_id).execute()
    insert_invoice_items(client, invoice_id, [
        {"invoice_id": invoice_id, "line_number": number, "description": item.get("description"),
         "hsn_sac": item.get("hsn_sac"), "quantity": item.get("quantity"),
         "unit_price": item.get("unit_price"), "taxable_value": item.get("taxable_value"),
         "cgst_amount": item.get("cgst"), "sgst_amount": item.get("sgst"), "igst_amount": item.get("igst")}
        for number, item in enumerate(line_items, start=1)
    ])
    return get_invoice(client, invoice_id) or {"id": invoice_id}


def update_draft_conversion(
    client: Client,
    draft_id: str,
    invoice_id: str | None,
    status: str,
) -> dict:
    """Update the conversion tracking fields on an intake draft."""
    result = (
        client.table("invoice_intake_drafts")
        .update({
            "converted_invoice_id": invoice_id,
            "conversion_status": status,
            "converted_at": "now()" if status == "CONVERTED" else None,
            "updated_at": "now()",
        })
        .eq("id", draft_id)
        .execute()
    )
    if getattr(result, "error", None):
        raise RepositoryError(f"Draft conversion update failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Draft conversion update returned no data")
    return data[0]


def resolve_client_from_buyer(
    client: Client,
    buyer_gstin: str | None,
    buyer_name: str | None,
) -> tuple[str, str]:
    """Resolve client_id and client_entity_id from extracted buyer data.

    Looks up client_entities by buyer GSTIN (primary) or buyer legal name
    (fallback). Verifies the entity is active and the owning client is ACTIVE.

    Returns (client_id, client_entity_id).
    Raises RepositoryError if no matching active client/entity is found.
    """
    if not buyer_gstin and not buyer_name:
        raise RepositoryError(
            "Cannot resolve buyer: no GSTIN or legal name extracted from invoice."
        )

    # Try GSTIN match first (most reliable)
    if buyer_gstin:
        result = (
            client.table("client_entities")
            .select("id, client_id, is_active")
            .eq("gstin", buyer_gstin)
            .execute()
        )
        entities = result.data or []
        for entity in entities:
            if not entity.get("is_active"):
                continue
            client_res = (
                client.table("clients")
                .select("id, status")
                .eq("id", entity["client_id"])
                .eq("status", "ACTIVE")
                .execute()
            )
            clients = client_res.data or []
            if clients:
                return (clients[0]["id"], entity["id"])

    # Fallback: match by legal name (case-insensitive)
    if buyer_name:
        result = (
            client.table("client_entities")
            .select("id, client_id, is_active, legal_name, gstin")
            .ilike("legal_name", buyer_name)
            .execute()
        )
        entities = result.data or []
        for entity in entities:
            if not entity.get("is_active"):
                continue
            client_res = (
                client.table("clients")
                .select("id, status")
                .eq("id", entity["client_id"])
                .eq("status", "ACTIVE")
                .execute()
            )
            clients = client_res.data or []
            if clients:
                return (clients[0]["id"], entity["id"])

    raise RepositoryError(
        "Buyer entity not configured: no active client entity matches the "
        f"extracted buyer GSTIN ({buyer_gstin or '—'}) or name "
        f"({buyer_name or '—'}). Onboard the client before converting."
    )


def convert_draft_to_invoice(
    client: Client,
    draft_id: str,
) -> dict:
    """Convert an intake draft into a business invoice record.

    Resolves client_id and client_entity_id from the extracted buyer data.
    Does not accept or use hardcoded client IDs.

    Returns a dict with keys:
      - invoice_id: the invoice UUID
      - invoice_number: invoice number (or None)
      - status: "converted" or "already_converted"
    """
    draft = get_draft_by_id(client, draft_id)
    if not draft:
        raise RepositoryError("Draft not found")

    # Idempotency: if already converted, return the existing invoice
    existing_invoice = get_invoice_by_draft_id(client, draft_id)
    if existing_invoice:
        return {
            "invoice_id": existing_invoice["id"],
            "invoice_number": existing_invoice.get("invoice_number"),
            "status": "already_converted",
        }

    # Validate draft has extraction data
    extracted_data = draft.get("extracted_data") or {}
    fields = extracted_data.get("fields") or {}
    line_items = extracted_data.get("line_items") or []

    # Resolve client from buyer data
    buyer_gstin = fields.get("buyer_gstin")
    buyer_name = fields.get("buyer_legal_name")
    client_id, client_entity_id = resolve_client_from_buyer(
        client, buyer_gstin, buyer_name
    )

    # Determine procurement type from PO number presence
    po_number = fields.get("po_number")
    procurement_type = "PO" if po_number else "NON_PO"

    # Helper to default None to 0 for NOT NULL columns
    def _zero(val):
        return val if val is not None else 0

    # Insert invoice record
    invoice_payload = {
        "client_id": client_id,
        "client_entity_id": client_entity_id,
        "invoice_number": fields.get("invoice_number"),
        "invoice_date": fields.get("invoice_date"),
        "currency": fields.get("currency") or "INR",
        "procurement_type": procurement_type,
        "purchase_order_id": None,  # PO matching is Phase 2
        "contract_id": None,
        "taxable_value": _zero(fields.get("taxable_value")),
        "cgst_amount": _zero(fields.get("cgst")),
        "sgst_amount": _zero(fields.get("sgst")),
        "igst_amount": _zero(fields.get("igst")),
        "cess_amount": _zero(fields.get("cess")),
        "other_charges": _zero(fields.get("other_charges")),
        "discount_amount": _zero(fields.get("discount_amount")),
        "total_amount": _zero(fields.get("invoice_grand_total")),
        "processing_status": "RECEIVED",
        "approval_status": "PENDING",
        "source_file_sha256": draft.get("sha256"),
    }

    invoice = insert_invoice(client, invoice_payload)
    invoice_id = invoice["id"]

    # Insert line items
    if line_items:
        item_payloads = []
        for idx, item in enumerate(line_items, start=1):
            item_payloads.append({
                "invoice_id": invoice_id,
                "line_number": idx,
                "description": item.get("description"),
                "item_code": None,
                "hsn_sac": item.get("hsn_sac"),
                "quantity": _zero(item.get("quantity")),
                "unit_of_measure": None,
                "unit_price": _zero(item.get("unit_price")),
                "taxable_value": _zero(item.get("taxable_value")),
                "gst_rate": None,
                "cgst_amount": _zero(item.get("cgst")),
                "sgst_amount": _zero(item.get("sgst")),
                "igst_amount": _zero(item.get("igst")),
                "total_amount": _zero(item.get("taxable_value")),
            })
        insert_invoice_items(client, invoice_id, item_payloads)

    # Insert document reference
    insert_invoice_document(client, {
        "invoice_id": invoice_id,
        "storage_path": draft.get("storage_path"),
        "original_filename": draft.get("original_filename"),
        "mime_type": draft.get("mime_type"),
        "sha256": draft.get("sha256"),
        "document_type": "invoice_pdf",
        "extraction_method": draft.get("extraction_method") or "pymupdf_digital",
    })

    # Create initial processing run
    run_payload = {
        "invoice_id": invoice_id,
        "run_number": 1,
        "status": "QUEUED",
        "triggered_by": "DRAFT_CONVERSION",
        "idempotency_key": f"convert-{draft_id}",
        "summary": {
            "draft_id": draft_id,
            "extraction_kind": extracted_data.get("kind"),
            "line_item_count": len(line_items),
        },
    }
    run = insert_processing_run(client, run_payload)

    # Update draft with conversion tracking
    update_draft_conversion(client, draft_id, invoice_id, "CONVERTED")

    # Write audit log
    client.table("audit_logs").insert({
        "client_id": client_id,
        "invoice_id": invoice_id,
        "actor_type": "SYSTEM",
        "actor_id": "draft-conversion",
        "action": "DRAFT_CONVERTED_TO_INVOICE",
        "before_state": {"draft_id": draft_id, "draft_status": draft.get("processing_status")},
        "after_state": {
            "invoice_id": invoice_id,
            "invoice_number": invoice.get("invoice_number"),
            "processing_run_id": run.get("id"),
        },
    }).execute()

    return {
        "invoice_id": invoice_id,
        "invoice_number": invoice.get("invoice_number"),
        "status": "converted",
    }
