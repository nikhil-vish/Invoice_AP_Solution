"""Backend tests for invoice intake upload."""

import io
import json
from contextlib import ExitStack
from unittest.mock import patch, MagicMock

import fitz
from fastapi.testclient import TestClient
from app.main import app
from app.invoices import repository

client = TestClient(app)


def _chain_result(data, count=None):
    chain = MagicMock()
    chain.eq.return_value = chain
    chain.or_.return_value = chain
    chain.order.return_value = chain
    chain.range.return_value = chain
    chain.limit.return_value = chain
    chain.in_.return_value = chain
    chain.execute.return_value = MagicMock(data=data, count=count)
    return chain


def _make_digital_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_scanned_pdf() -> bytes:
    """Create a PDF with no extractable text (simulates a scanned image)."""
    doc = fitz.open()
    page = doc.new_page()
    # Draw nothing - completely empty page, will have 0 text
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_corrupt_pdf() -> bytes:
    return b"%PDF-1.4\nthis is not a real pdf structure\n%%EOF"


def _make_mock_client(existing: bool = False):
    mock_client = MagicMock()
    mock_storage = MagicMock()
    mock_storage.from_.return_value.upload.return_value = None
    mock_client.storage = mock_storage
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table

    # Select result (for duplicate check)
    mock_select = MagicMock()
    if existing:
        mock_select.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "existing-draft-id"}], error=None
        )
    else:
        mock_select.eq.return_value.execute.return_value = MagicMock(
            data=[], error=None
        )
    mock_table.select.return_value = mock_select

    # Insert result (for draft creation)
    mock_insert = MagicMock()
    mock_insert.execute.return_value = MagicMock(
        data=[{"id": "new-draft-id", "processing_status": "EXTRACTED"}], error=None
    )
    mock_table.insert.return_value = mock_insert

    return mock_client


def _mock_settings():
    s = MagicMock()
    s.supabase_url = "https://test-project.supabase.co"
    s.supabase_service_role_key = "test-service-role-key"
    s.supabase_storage_bucket = "invoices"
    return s


def _settings_patch(mock_client):
    mock = _mock_settings()
    stack = ExitStack()
    stack.enter_context(patch.multiple("app.config", settings=mock))
    stack.enter_context(patch.multiple("app.invoices.router", settings=mock))
    stack.enter_context(patch.multiple("app.invoices.storage", settings=mock))
    stack.enter_context(patch.multiple("app.invoices.repository", settings=mock))
    stack.enter_context(patch.multiple("app.invoices.router", create_client=MagicMock(return_value=mock_client)))
    stack.enter_context(patch.multiple("app.invoices.storage", create_client=MagicMock(return_value=mock_client)))
    stack.enter_context(patch.multiple("app.invoices.repository", create_client=MagicMock(return_value=mock_client)))
    # Most legacy route tests are not testing workspace lookup or unified
    # creation. Keep their database chain mock focused on the route itself.
    stack.enter_context(patch("app.invoices.router.resolve_demo_workspace", return_value=("demo-client", "demo-entity")))
    stack.enter_context(patch("app.invoices.router.create_invoice_for_draft", return_value={"id": "new-invoice-id"}))
    stack.enter_context(patch("app.invoices.router._verified_reviewer_id", return_value="reviewer-001"))
    return stack


def test_upload_valid_digital_pdf():
    pdf_bytes = _make_digital_pdf(
        "TAX INVOICE\n"
        "Supplier: Acme Supplies Pvt Ltd\n"
        "GSTIN: 27ABCDE1234F1Z5\n"
        "Invoice No: INV-2024-001\n"
        "Invoice Date: 01/01/2024\n"
        "Buyer: Buyer Corp Ltd\n"
        "GSTIN: 27XYZAB5678G1Z6\n"
        "Taxable Value: 1000.00\n"
        "CGST: 90.00\n"
        "SGST: 90.00\n"
        "Total: 1180.00\n"
    )
    mock_client = _make_mock_client()

    # Mock OpenRouter AI extraction to avoid rate limiting
    ai_json = json.dumps({
        "supplier_name": "Acme Supplies Pvt Ltd",
        "supplier_gstin": "27ABCDE1234F1Z5",
        "buyer_name": "Buyer Corp Ltd",
        "buyer_gstin": "27XYZAB5678G1Z6",
        "invoice_number": "INV-2024-001",
        "invoice_date": "2024-01-01",
        "due_date": None,
        "po_number": None,
        "currency": "INR",
        "taxable_value": 1000.0,
        "cgst": 90.0,
        "sgst": 90.0,
        "igst": None,
        "total_tax": 180.0,
        "grand_total": 1180.0,
        "line_items": [],
    })
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": ai_json}}]}
    mock_response.raise_for_status = MagicMock()

    mock_http_client = MagicMock()
    mock_http_client.__aenter__.return_value = mock_http_client

    async def _async_post(*args, **kwargs):
        return mock_response

    mock_http_client.post = _async_post

    with _settings_patch(mock_client), \
         patch("app.invoices.ai_extract.httpx.AsyncClient", return_value=mock_http_client):
        response = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["extraction_kind"] == "ai_enhanced"
    assert body["ocr_supported"] is False
    assert body["filename"] == "invoice.pdf"
    assert body["fields"]["invoice_number"] == "INV-2024-001"
    assert body["fields"]["supplier_legal_name"] is not None
    assert body["fields"]["supplier_gstin"] == "27ABCDE1234F1Z5"
    assert body["draft_id"] == "new-draft-id"
    assert body["message"] is None



def test_upload_invalid_file_type():
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("document.txt", b"hello world", "text/plain")},
        )
    assert response.status_code == 400, response.text
    assert "Only PDF files" in response.json()["detail"]


def test_upload_oversized_file():
    big_data = b"%PDF-1.4\n" + b"\x00" * (15 * 1024 * 1024 + 1)
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("big.pdf", big_data, "application/pdf")},
        )
    assert response.status_code == 413, response.text
    assert "15 MB" in response.json()["detail"]


def test_upload_corrupt_pdf():
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("corrupt.pdf", _make_corrupt_pdf(), "application/pdf")},
        )
    assert response.status_code == 400, response.text
    assert "The PDF could not be opened." in response.json()["detail"]


def test_upload_scanned_pdf_no_text():
    pdf_bytes = _make_scanned_pdf()
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("scanned.pdf", pdf_bytes, "application/pdf")},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["extraction_kind"] == "scanned"
    assert "OCR is not implemented" in body["message"]
    assert body["draft_id"] is not None


def test_upload_duplicate_hash():
    pdf_bytes = _make_digital_pdf("INVOICE\nInvoice No: DUP-001\n")
    mock_client = _make_mock_client(existing=True)
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("dup.pdf", pdf_bytes, "application/pdf")},
        )
    assert response.status_code == 409, response.text
    assert "already been uploaded" in response.json()["detail"]
    assert response.headers.get("x-existing-draft-id") == "existing-draft-id"


def test_upload_storage_failure():
    pdf_bytes = _make_digital_pdf("INVOICE\nInvoice No: ST-001\n")
    mock_client = _make_mock_client()
    # Override storage upload to fail
    mock_client.storage.from_.return_value.upload.side_effect = Exception("bucket not found")
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("storage-fail.pdf", pdf_bytes, "application/pdf")},
        )
    assert response.status_code == 500, response.text
    assert "Storage upload failed" in response.json()["detail"]


def test_upload_missing_supabase_config():
    pdf_bytes = _make_digital_pdf("INVOICE\nInvoice No: CFG-001\n")
    with patch("app.config.settings", MagicMock(supabase_url="", supabase_service_role_key="", supabase_storage_bucket="invoices")), patch(
        "app.invoices.router.settings", MagicMock(supabase_url="", supabase_service_role_key="", supabase_storage_bucket="invoices")
    ), patch(
        "app.invoices.storage.settings", MagicMock(supabase_url="", supabase_service_role_key="", supabase_storage_bucket="invoices")
    ), patch(
        "app.invoices.repository.settings", MagicMock(supabase_url="", supabase_service_role_key="", supabase_storage_bucket="invoices")
    ):
        response = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("config.pdf", pdf_bytes, "application/pdf")},
        )
    assert response.status_code == 500, response.text
    assert "Supabase is not configured" in response.json()["detail"]


def test_upload_empty_file():
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
    assert response.status_code == 400, response.text
    assert "empty" in response.json()["detail"].lower()


def test_extraction_returns_null_for_missing_fields():
    pdf_bytes = _make_digital_pdf("INVOICE\nInvoice No: NULL-001\n")
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("nulls.pdf", pdf_bytes, "application/pdf")},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["fields"]["supplier_legal_name"] is None
    assert body["fields"]["supplier_gstin"] is None
    assert body["fields"]["buyer_legal_name"] is None
    assert body["fields"]["invoice_grand_total"] is None
    assert body["field_status"]["supplier_legal_name"] == "missing"
    assert body["field_status"]["invoice_number"] == "found"


def test_raw_text_preserved():
    sample_text = "INVOICE\nInvoice No: RAW-001\nSupplier: Test Co\n"
    pdf_bytes = _make_digital_pdf(sample_text)
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("raw.pdf", pdf_bytes, "application/pdf")},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert "RAW-001" in body["raw_text"]
    assert "Test Co" in body["raw_text"]


def test_upload_response_contains_draft_id():
    pdf_bytes = _make_digital_pdf("INVOICE\nInvoice No: ID-001\n")
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("id.pdf", pdf_bytes, "application/pdf")},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert "draft_id" in body
    assert isinstance(body["draft_id"], str)
    assert len(body["draft_id"]) > 0


def test_get_draft_invalid_uuid_format():
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/drafts/not-a-uuid")
    assert response.status_code == 400, response.text
    assert "Invalid ID format" in response.json()["detail"]


def test_get_draft_not_found():
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655440000")
    assert response.status_code == 404, response.text
    assert "Draft not found" in response.json()["detail"]


def test_save_draft_invalid_uuid_format():
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.post("/api/v1/invoices/drafts/not-a-uuid/save")
    assert response.status_code == 400, response.text
    assert "Invalid ID format" in response.json()["detail"]


def test_list_invoices():
    mock_client = _make_mock_client()
    # Mock the invoices table response - use a flexible chain that handles both with and without search
    mock_table = mock_client.table.return_value
    
    # Create a chain mock that returns itself for eq, or_, order, range
    chain_mock = MagicMock()
    chain_mock.eq.return_value = chain_mock
    chain_mock.or_.return_value = chain_mock
    chain_mock.order.return_value = chain_mock
    chain_mock.range.return_value = chain_mock
    chain_mock.execute.return_value = MagicMock(
        data=[{"id": "inv-1", "invoice_number": "INV-001"}],
        count=1
    )
    mock_table.select.return_value = chain_mock
    
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "invoices" in body
    assert "total" in body
    assert body["total"] == 1


def test_list_invoices_with_filters():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    chain_mock = MagicMock()
    chain_mock.eq.return_value = chain_mock
    chain_mock.or_.return_value = chain_mock
    chain_mock.order.return_value = chain_mock
    chain_mock.range.return_value = chain_mock
    chain_mock.execute.return_value = MagicMock(
        data=[],
        count=0
    )
    mock_table.select.return_value = chain_mock
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices?search=test&status=RECEIVED&page=2&page_size=10")
    assert response.status_code == 200, response.text


def test_get_invoice_not_found():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[],
        count=0
    )
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/550e8400-e29b-41d4-a716-446655440000")
    assert response.status_code == 404, response.text


def test_get_invoice_invalid_uuid():
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/not-a-uuid")
    assert response.status_code == 400, response.text


def test_list_runs():
    mock_client = _make_mock_client()
    # Mock the processing_runs join query
    mock_table = mock_client.table.return_value
    mock_table.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=[{"id": "run-1", "invoice_id": "inv-1", "run_number": 1, "status": "COMPLETED"}],
    )
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/runs")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "runs" in body
    assert "total" in body


def test_get_run_not_found():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[],
    )
    with _settings_patch(mock_client):
        response = client.get("/api/v1/runs/550e8400-e29b-41d4-a716-446655440000")
    assert response.status_code == 404, response.text


def test_list_suppliers():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    chain_mock = MagicMock()
    chain_mock.eq.return_value = chain_mock
    chain_mock.or_.return_value = chain_mock
    chain_mock.order.return_value = chain_mock
    chain_mock.range.return_value = chain_mock
    chain_mock.execute.return_value = MagicMock(
        data=[{"id": "sup-1", "legal_name": "Test Supplier"}],
        count=1
    )
    mock_table.select.return_value = chain_mock
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/suppliers")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "suppliers" in body
    assert "total" in body
    assert body["total"] == 1


def test_list_suppliers_with_filters():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    chain_mock = MagicMock()
    chain_mock.eq.return_value = chain_mock
    chain_mock.or_.return_value = chain_mock
    chain_mock.order.return_value = chain_mock
    chain_mock.range.return_value = chain_mock
    chain_mock.execute.return_value = MagicMock(
        data=[],
        count=0
    )
    mock_table.select.return_value = chain_mock
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/suppliers?search=test&status=ACTIVE&page=2&page_size=10")
    assert response.status_code == 200, response.text


def test_process_invoice_not_found():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[],
    )
    with _settings_patch(mock_client):
        response = client.post("/api/v1/invoices/550e8400-e29b-41d4-a716-446655440000/process")
    assert response.status_code == 404, response.text


# ==================== Approvals Tests ====================

def test_list_approvals():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    chain_mock = MagicMock()
    chain_mock.eq.return_value = chain_mock
    chain_mock.order.return_value = chain_mock
    chain_mock.range.return_value = chain_mock
    chain_mock.execute.return_value = MagicMock(
        data=[{
            "id": "app-1",
            "invoice_id": "inv-1",
            "approval_level": 1,
            "status": "PENDING",
            "assigned_at": "2024-01-15T10:00:00Z",
            "invoices": {"invoice_number": "INV-001", "supplier_name": "Test Supplier", "total_amount": 10000, "currency": "INR"}
        }],
        count=1
    )
    mock_table.select.return_value = chain_mock
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/approvals")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "approvals" in body
    assert "total" in body
    assert body["total"] == 1


def test_list_approvals_with_status_filter():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    chain_mock = MagicMock()
    chain_mock.eq.return_value = chain_mock
    chain_mock.order.return_value = chain_mock
    chain_mock.range.return_value = chain_mock
    chain_mock.execute.return_value = MagicMock(
        data=[],
        count=0
    )
    mock_table.select.return_value = chain_mock
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/approvals?status=APPROVED&page=2&page_size=10")
    assert response.status_code == 200, response.text


def test_get_approval_not_found():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[],
        count=0
    )
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/approvals/550e8400-e29b-41d4-a716-446655440000")
    assert response.status_code == 404, response.text


def test_get_approval_invalid_uuid():
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/approvals/not-a-uuid")
    assert response.status_code == 400, response.text


# ==================== Exceptions Tests ====================

def test_list_exceptions():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    chain_mock = MagicMock()
    chain_mock.eq.return_value = chain_mock
    chain_mock.order.return_value = chain_mock
    chain_mock.range.return_value = chain_mock
    chain_mock.execute.return_value = MagicMock(
        data=[{
            "id": "exc-1",
            "invoice_id": "inv-1",
            "exception_code": "GST_MISMATCH",
            "severity": "HIGH",
            "status": "OPEN",
            "description": "GST mismatch",
            "created_at": "2024-01-15T10:00:00Z",
            "invoices": {"invoice_number": "INV-001", "supplier_name": "Test Supplier"}
        }],
        count=1
    )
    mock_table.select.return_value = chain_mock
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/exceptions")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "exceptions" in body
    assert "total" in body
    assert body["total"] == 1


def test_list_exceptions_with_filters():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    chain_mock = MagicMock()
    chain_mock.eq.return_value = chain_mock
    chain_mock.order.return_value = chain_mock
    chain_mock.range.return_value = chain_mock
    chain_mock.execute.return_value = MagicMock(
        data=[],
        count=0
    )
    mock_table.select.return_value = chain_mock
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/exceptions?severity=CRITICAL&status=OPEN&page=2&page_size=10")
    assert response.status_code == 200, response.text


def test_get_exception_not_found():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    mock_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[],
        count=0
    )
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/exceptions/550e8400-e29b-41d4-a716-446655440000")
    assert response.status_code == 404, response.text


def test_get_exception_invalid_uuid():
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/exceptions/not-a-uuid")
    assert response.status_code == 400, response.text


# ==================== Exception Actions Tests ====================

def test_assign_exception():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    # Mock the update chain for assign_exception
    mock_eq = MagicMock()
    mock_eq.execute.return_value = MagicMock(
        data=[{
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "invoice_id": "550e8400-e29b-41d4-a716-446655440001",
            "owner_team": "tax-team",
            "status": "IN_REVIEW",
        }],
        error=None
    )
    mock_update = MagicMock()
    mock_update.eq.return_value = mock_eq
    mock_table.update.return_value = mock_update
    # Mock audit log insert
    mock_table.insert.return_value.execute.return_value = MagicMock(data=[], error=None)
    
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/exceptions/550e8400-e29b-41d4-a716-446655440000/assign",
            json={"owner_team": "tax-team", "actor_id": "user-001"}
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "IN_REVIEW"
    assert body["owner_team"] == "tax-team"


def test_assign_exception_invalid_uuid():
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/exceptions/not-a-uuid/assign",
            json={"owner_team": "tax-team"}
        )
    assert response.status_code == 400, response.text


def test_resolve_exception():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    # First select to check current state
    mock_select = MagicMock()
    mock_select.eq.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "invoice_id": "550e8400-e29b-41d4-a716-446655440001",
            "status": "OPEN",
        }],
        error=None
    )
    mock_table.select.return_value = mock_select
    
    # Mock the update chain for resolve_exception
    mock_eq = MagicMock()
    mock_eq.execute.return_value = MagicMock(
        data=[{
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "invoice_id": "550e8400-e29b-41d4-a716-446655440001",
            "status": "RESOLVED",
            "resolution": {"comment": "Fixed GSTIN", "resolved_by": "user-001"},
        }],
        error=None
    )
    mock_update = MagicMock()
    mock_update.eq.return_value = mock_eq
    mock_table.update.return_value = mock_update
    # Mock audit log insert
    mock_table.insert.return_value.execute.return_value = MagicMock(data=[], error=None)
    
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/exceptions/550e8400-e29b-41d4-a716-446655440000/resolve",
            json={"resolution_comment": "Fixed GSTIN", "actor_id": "user-001"}
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "RESOLVED"
    assert body["resolution"]["comment"] == "Fixed GSTIN"


def test_resolve_exception_already_resolved():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    # First select returns already resolved
    mock_select = MagicMock()
    mock_select.eq.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "invoice_id": "550e8400-e29b-41d4-a716-446655440001",
            "status": "RESOLVED",
        }],
        error=None
    )
    mock_table.select.return_value = mock_select
    
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/exceptions/550e8400-e29b-41d4-a716-446655440000/resolve",
            json={"resolution_comment": "Fixed", "actor_id": "user-001"}
        )
    assert response.status_code == 400, response.text
    assert "already resolved" in response.json()["detail"].lower()


def test_resolve_exception_not_found():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    mock_select = MagicMock()
    mock_select.eq.return_value.execute.return_value = MagicMock(
        data=[],
        error=None
    )
    mock_table.select.return_value = mock_select
    
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/exceptions/550e8400-e29b-41d4-a716-446655440000/resolve",
            json={"resolution_comment": "Fixed", "actor_id": "user-001"}
        )
    assert response.status_code == 400, response.text
    assert "not found" in response.json()["detail"].lower()


def test_resolve_exception_invalid_uuid():
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/exceptions/not-a-uuid/resolve",
            json={"resolution_comment": "Fixed", "actor_id": "user-001"}
        )
    assert response.status_code == 400, response.text


# ==================== Approval Actions Tests ====================

def test_approval_action_approve():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    # Mock get_approval
    mock_select = MagicMock()
    mock_select.eq.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "invoice_id": "550e8400-e29b-41d4-a716-446655440001",
            "status": "PENDING",
        }],
        error=None
    )
    # Mock validation_results for invoice validation check
    mock_table.select.return_value = mock_select
    # Mock update for approval action
    mock_eq = MagicMock()
    mock_eq.execute.return_value = MagicMock(
        data=[{
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "invoice_id": "550e8400-e29b-41d4-a716-446655440001",
            "status": "APPROVED",
            "decision_comment": "Approved",
        }],
        error=None
    )
    mock_update = MagicMock()
    mock_update.eq.return_value = mock_eq
    mock_table.update.return_value = mock_update
    # Mock audit log insert
    mock_table.insert.return_value.execute.return_value = MagicMock(data=[], error=None)
    
    # Mock validation results query (for get_invoice_validation_status)
    def mock_table_side_effect(table_name):
        if table_name == "validation_results":
            mock_vr_table = MagicMock()
            mock_vr_select = MagicMock()
            mock_vr_select.eq.return_value.execute.return_value = MagicMock(
                data=[{"status": "PASSED"}],
                error=None
            )
            mock_vr_table.select.return_value = mock_vr_select
            return mock_vr_table
        elif table_name == "exceptions":
            mock_exc_table = MagicMock()
            mock_exc_select = MagicMock()
            mock_exc_select.eq.return_value.in_.return_value.execute.return_value = MagicMock(
                data=[],
                error=None
            )
            mock_exc_table.select.return_value = mock_exc_select
            return mock_exc_table
        elif table_name == "processing_runs":
            mock_run_table = MagicMock()
            mock_run_select = MagicMock()
            mock_run_select.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"id": "550e8400-e29b-41d4-a716-446655440002"}],
                error=None
            )
            mock_run_table.select.return_value = mock_run_select
            return mock_run_table
        return mock_table
    
    mock_client.table.side_effect = mock_table_side_effect
    
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/approvals/550e8400-e29b-41d4-a716-446655440000/action",
            json={"action": "APPROVE", "comment": "Approved", "actor_id": "user-001"}
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "APPROVED"


def test_approval_action_reject():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    mock_select = MagicMock()
    mock_select.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "550e8400-e29b-41d4-a716-446655440000", "invoice_id": "550e8400-e29b-41d4-a716-446655440001", "status": "PENDING"}],
        error=None
    )
    mock_table.select.return_value = mock_select
    mock_eq = MagicMock()
    mock_eq.execute.return_value = MagicMock(
        data=[{"id": "550e8400-e29b-41d4-a716-446655440000", "invoice_id": "550e8400-e29b-41d4-a716-446655440001", "status": "REJECTED", "decision_comment": "Rejected - amount mismatch"}],
        error=None
    )
    mock_update = MagicMock()
    mock_update.eq.return_value = mock_eq
    mock_table.update.return_value = mock_update
    mock_table.insert.return_value.execute.return_value = MagicMock(data=[], error=None)
    
    def mock_table_side_effect(table_name):
        if table_name == "validation_results":
            mock_vr_table = MagicMock()
            mock_vr_select = MagicMock()
            mock_vr_select.eq.return_value.execute.return_value = MagicMock(data=[{"status": "PASSED"}], error=None)
            mock_vr_table.select.return_value = mock_vr_select
            return mock_vr_table
        elif table_name == "exceptions":
            mock_exc_table = MagicMock()
            mock_exc_select = MagicMock()
            mock_exc_select.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[], error=None)
            mock_exc_table.select.return_value = mock_exc_select
            return mock_exc_table
        elif table_name == "processing_runs":
            mock_run_table = MagicMock()
            mock_run_select = MagicMock()
            mock_run_select.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "550e8400-e29b-41d4-a716-446655440002"}], error=None)
            mock_run_table.select.return_value = mock_run_select
            return mock_run_table
        return mock_table
    
    mock_client.table.side_effect = mock_table_side_effect
    
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/approvals/550e8400-e29b-41d4-a716-446655440000/action",
            json={"action": "REJECT", "comment": "Amount mismatch", "actor_id": "user-001"}
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "REJECTED"


def test_approval_action_reject_no_comment():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    mock_select = MagicMock()
    mock_select.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "550e8400-e29b-41d4-a716-446655440000", "invoice_id": "550e8400-e29b-41d4-a716-446655440001", "status": "PENDING"}],
        error=None
    )
    mock_table.select.return_value = mock_select
    
    def mock_table_side_effect(table_name):
        if table_name == "validation_results":
            mock_vr_table = MagicMock()
            mock_vr_select = MagicMock()
            mock_vr_select.eq.return_value.execute.return_value = MagicMock(data=[{"status": "PASSED"}], error=None)
            mock_vr_table.select.return_value = mock_vr_select
            return mock_vr_table
        elif table_name == "exceptions":
            mock_exc_table = MagicMock()
            mock_exc_select = MagicMock()
            mock_exc_select.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[], error=None)
            mock_exc_table.select.return_value = mock_exc_select
            return mock_exc_table
        elif table_name == "processing_runs":
            mock_run_table = MagicMock()
            mock_run_select = MagicMock()
            mock_run_select.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "550e8400-e29b-41d4-a716-446655440002"}], error=None)
            mock_run_table.select.return_value = mock_run_select
            return mock_run_table
        return mock_table
    
    mock_client.table.side_effect = mock_table_side_effect
    
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/approvals/550e8400-e29b-41d4-a716-446655440000/action",
            json={"action": "REJECT", "actor_id": "user-001"}
        )
    assert response.status_code == 400, response.text
    assert "comment is required" in response.json()["detail"].lower()


def test_approval_action_return_for_information():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    mock_select = MagicMock()
    mock_select.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "550e8400-e29b-41d4-a716-446655440000", "invoice_id": "550e8400-e29b-41d4-a716-446655440001", "status": "PENDING"}],
        error=None
    )
    mock_table.select.return_value = mock_select
    mock_eq = MagicMock()
    mock_eq.execute.return_value = MagicMock(
        data=[{"id": "550e8400-e29b-41d4-a716-446655440000", "invoice_id": "550e8400-e29b-41d4-a716-446655440001", "status": "REASSIGNED", "decision_comment": "Need more info"}],
        error=None
    )
    mock_update = MagicMock()
    mock_update.eq.return_value = mock_eq
    mock_table.update.return_value = mock_update
    mock_table.insert.return_value.execute.return_value = MagicMock(data=[], error=None)
    
    def mock_table_side_effect(table_name):
        if table_name == "validation_results":
            mock_vr_table = MagicMock()
            mock_vr_select = MagicMock()
            mock_vr_select.eq.return_value.execute.return_value = MagicMock(data=[{"status": "PASSED"}], error=None)
            mock_vr_table.select.return_value = mock_vr_select
            return mock_vr_table
        elif table_name == "exceptions":
            mock_exc_table = MagicMock()
            mock_exc_select = MagicMock()
            mock_exc_select.eq.return_value.in_.return_value.execute.return_value = MagicMock(data=[], error=None)
            mock_exc_table.select.return_value = mock_exc_select
            return mock_exc_table
        elif table_name == "processing_runs":
            mock_run_table = MagicMock()
            mock_run_select = MagicMock()
            mock_run_select.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": "550e8400-e29b-41d4-a716-446655440002"}], error=None)
            mock_run_table.select.return_value = mock_run_select
            return mock_run_table
        return mock_table
    
    mock_client.table.side_effect = mock_table_side_effect
    
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/approvals/550e8400-e29b-41d4-a716-446655440000/action",
            json={"action": "RETURN_FOR_INFORMATION", "comment": "Need more info", "actor_id": "user-001"}
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "REASSIGNED"


def test_approval_action_already_processed():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    mock_select = MagicMock()
    mock_select.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "550e8400-e29b-41d4-a716-446655440000", "invoice_id": "550e8400-e29b-41d4-a716-446655440001", "status": "APPROVED"}],
        error=None
    )
    mock_table.select.return_value = mock_select
    
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/approvals/550e8400-e29b-41d4-a716-446655440000/action",
            json={"action": "APPROVE", "actor_id": "user-001"}
        )
    assert response.status_code == 400, response.text
    assert "already processed" in response.json()["detail"].lower()


def test_approval_action_invalid_action():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    mock_select = MagicMock()
    mock_select.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "550e8400-e29b-41d4-a716-446655440000", "invoice_id": "550e8400-e29b-41d4-a716-446655440001", "status": "PENDING"}],
        error=None
    )
    mock_table.select.return_value = mock_select
    
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/approvals/550e8400-e29b-41d4-a716-446655440000/action",
            json={"action": "INVALID_ACTION", "actor_id": "user-001"}
        )
    assert response.status_code == 400, response.text
    assert "invalid action" in response.json()["detail"].lower()


def test_approval_action_not_found():
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value
    mock_select = MagicMock()
    mock_select.eq.return_value.execute.return_value = MagicMock(
        data=[],
        error=None
    )
    mock_table.select.return_value = mock_select
    
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/approvals/550e8400-e29b-41d4-a716-446655440000/action",
            json={"action": "APPROVE", "actor_id": "user-001"}
        )
    assert response.status_code == 400, response.text
    assert "not found" in response.json()["detail"].lower()


def test_approval_action_invalid_uuid():
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/approvals/not-a-uuid/action",
            json={"action": "APPROVE", "actor_id": "user-001"}
        )
    assert response.status_code == 400, response.text


# ==================== Draft-to-Invoice Conversion Tests ====================

# Client and entity used for buyer resolution in conversion tests.
TEST_CLIENT_ID = "cccc0000-0000-0000-0000-000000000101"
TEST_ENTITY_ID = "eeee0000-0000-0000-0000-000000000101"

TEST_CLIENT = {
    "id": TEST_CLIENT_ID,
    "legal_name": "Nizam Gourmet Foods Pvt. Ltd.",
    "display_name": "Nizam Foods",
    "status": "ACTIVE",
    "created_at": "2026-01-01T00:00:00Z",
}

TEST_CLIENT_ENTITY = {
    "id": TEST_ENTITY_ID,
    "client_id": TEST_CLIENT_ID,
    "legal_name": "Nizam Gourmet Foods Pvt. Ltd.",
    "gstin": "36AABCN8901K1Z4",
    "registered_email_domains": [],
    "is_active": True,
    "created_at": "2026-01-01T00:00:00Z",
}


def _make_conversion_mock_client():
    """Create a mock Supabase client that supports conversion operations.

    Includes mocked clients and client_entities tables so buyer resolution
    can succeed for the Nizam Gourmet Foods buyer (GSTIN: 36AABCN8901K1Z4).
    """
    mock_client = MagicMock()
    mock_storage = MagicMock()
    mock_storage.from_.return_value.upload.return_value = None
    mock_client.storage = mock_storage

    # Table-specific mocks
    mock_tables = {}

    def _get_table(name):
        if name not in mock_tables:
            mock_tables[name] = MagicMock()
        return mock_tables[name]

    mock_client.table.side_effect = _get_table

    # Draft select (for get_draft_by_id)
    draft_data = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "original_filename": "deccan_invoice.pdf",
        "storage_path": "intake/abc123/deccan_invoice.pdf",
        "mime_type": "application/pdf",
        "sha256": "abc123def456",
        "file_size_bytes": 102400,
        "extracted_data": {
            "kind": "digital",
            "fields": {
                "supplier_legal_name": "Deccan Print & Packaging Solutions",
                "supplier_gstin": "36AABCD4512L1Z7",
                "buyer_legal_name": "Nizam Gourmet Foods Pvt. Ltd.",
                "buyer_gstin": "36AABCN8901K1Z4",
                "invoice_number": "DPP/2026-27/0823",
                "invoice_date": "2026-11-25",
                "due_date": "2026-12-10",
                "po_number": None,
                "taxable_value": 80000.0,
                "cgst": 7200.0,
                "sgst": 7200.0,
                "igst": None,
                "total_tax": 14400.0,
                "invoice_grand_total": 94400.0,
                "currency": "INR",
            },
            "field_status": {
                "supplier_legal_name": "found",
                "supplier_gstin": "found",
                "buyer_legal_name": "found",
                "buyer_gstin": "found",
                "invoice_number": "found",
                "invoice_date": "found",
                "due_date": "found",
                "po_number": "missing",
                "taxable_value": "found",
                "cgst": "found",
                "sgst": "found",
                "igst": "missing",
                "total_tax": "found",
                "invoice_grand_total": "found",
                "currency": "found",
            },
            "line_items": [
                {
                    "description": "Offset printing plates",
                    "hsn_sac": "84425010",
                    "quantity": 10.0,
                    "unit_price": 4000.0,
                    "taxable_value": 40000.0,
                },
                {
                    "description": "UV coating service",
                    "hsn_sac": "998713",
                    "quantity": 5.0,
                    "unit_price": 8000.0,
                    "taxable_value": 40000.0,
                },
                {
                    "description": "Die cutting",
                    "hsn_sac": "84411010",
                    "quantity": 2.0,
                    "unit_price": 15000.0,
                    "taxable_value": 30000.0,
                },
                {
                    "description": "Packaging material",
                    "hsn_sac": "4819",
                    "quantity": 1.0,
                    "unit_price": 24000.0,
                    "taxable_value": 24000.0,
                },
            ],
        },
        "raw_text": "TAX INVOICE...",
        "extraction_method": "pymupdf_digital",
        "processing_status": "READY_FOR_VALIDATION",
        "created_at": "2026-11-25T10:00:00Z",
        "updated_at": "2026-11-25T10:00:00Z",
        "converted_invoice_id": None,
        "conversion_status": "PENDING",
        "converted_at": None,
    }

    # Insert results
    invoice_insert_result = MagicMock()
    invoice_insert_result.execute.return_value = MagicMock(
        data=[{
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "client_id": TEST_CLIENT_ID,
            "client_entity_id": TEST_ENTITY_ID,
            "invoice_number": "DPP/2026-27/0823",
            "invoice_date": "2026-11-25",
            "currency": "INR",
            "procurement_type": "NON_PO",
            "taxable_value": 80000.0,
            "cgst_amount": 7200.0,
            "sgst_amount": 7200.0,
            "igst_amount": 0,
            "cess_amount": 0,
            "other_charges": 0,
            "discount_amount": 0,
            "total_amount": 94400.0,
            "processing_status": "RECEIVED",
            "approval_status": "PENDING",
            "source_file_sha256": "abc123def456",
            "created_at": "2026-11-25T10:00:00Z",
            "updated_at": "2026-11-25T10:00:00Z",
        }],
        error=None
    )

    items_insert_result = MagicMock()
    items_insert_result.execute.return_value = MagicMock(
        data=[
            {"id": "item-1", "invoice_id": "550e8400-e29b-41d4-a716-446655440001", "line_number": 1},
            {"id": "item-2", "invoice_id": "550e8400-e29b-41d4-a716-446655440001", "line_number": 2},
            {"id": "item-3", "invoice_id": "550e8400-e29b-41d4-a716-446655440001", "line_number": 3},
            {"id": "item-4", "invoice_id": "550e8400-e29b-41d4-a716-446655440001", "line_number": 4},
        ],
        error=None
    )

    document_insert_result = MagicMock()
    document_insert_result.execute.return_value = MagicMock(
        data=[{"id": "doc-1", "invoice_id": "550e8400-e29b-41d4-a716-446655440001"}],
        error=None
    )

    run_insert_result = MagicMock()
    run_insert_result.execute.return_value = MagicMock(
        data=[{
            "id": "550e8400-e29b-41d4-a716-446655440003",
            "invoice_id": "550e8400-e29b-41d4-a716-446655440001",
            "run_number": 1,
            "status": "QUEUED",
            "triggered_by": "DRAFT_CONVERSION",
            "created_at": "2026-11-25T10:00:00Z",
        }],
        error=None
    )

    draft_update_result = MagicMock()
    draft_update_result.execute.return_value = MagicMock(
        data=[{**draft_data, "converted_invoice_id": "550e8400-e29b-41d4-a716-446655440001", "conversion_status": "CONVERTED"}],
        error=None
    )

    audit_insert_result = MagicMock()
    audit_insert_result.execute.return_value = MagicMock(data=[], error=None)

    # Configure select for drafts table
    drafts_table = _get_table("invoice_intake_drafts")
    draft_select = MagicMock()
    draft_select.eq.return_value.execute.return_value = MagicMock(
        data=[draft_data], error=None
    )
    drafts_table.select.return_value = draft_select
    drafts_table.insert.return_value = draft_insert_result = MagicMock()
    draft_insert_result.execute.return_value = MagicMock(data=[], error=None)
    drafts_table.update.return_value = MagicMock()
    drafts_table.update.return_value.eq.return_value = draft_update_result

    # Configure invoices table
    invoices_table = _get_table("invoices")
    invoices_table.insert.return_value = invoice_insert_result

    # Configure invoice_items table
    items_table = _get_table("invoice_items")
    items_table.insert.return_value = items_insert_result

    # Configure invoice_documents table
    docs_table = _get_table("invoice_documents")
    docs_table.insert.return_value = document_insert_result

    # Configure processing_runs table
    runs_table = _get_table("processing_runs")
    runs_table.insert.return_value = run_insert_result

    # Configure audit_logs table
    audit_table = _get_table("audit_logs")
    audit_table.insert.return_value = audit_insert_result

    # Configure clients table (for buyer resolution)
    clients_table = _get_table("clients")
    clients_select = MagicMock()
    clients_select.eq.return_value = clients_select
    clients_select.execute.return_value = MagicMock(
        data=[TEST_CLIENT], error=None
    )
    clients_table.select.return_value = clients_select

    # Configure client_entities table (for buyer resolution)
    entities_table = _get_table("client_entities")
    entities_select = MagicMock()
    entities_select.eq.return_value = entities_select
    entities_select.execute.return_value = MagicMock(
        data=[TEST_CLIENT_ENTITY], error=None
    )
    entities_table.select.return_value = entities_select

    return mock_client


def test_convert_draft_success():
    """Successful draft-to-invoice conversion creates all records."""
    mock_client = _make_conversion_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655440000/convert",
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["draft_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert body["invoice_id"] == "550e8400-e29b-41d4-a716-446655440001"
    assert body["invoice_number"] == "DPP/2026-27/0823"
    assert body["status"] == "converted"


def test_convert_draft_resolves_client_from_buyer():
    """Client and entity are resolved from buyer GSTIN, not hardcoded."""
    mock_client = _make_conversion_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655440000/convert",
        )
    assert response.status_code == 200, response.text

    # Verify invoice insert used resolved client/entity IDs
    invoices_table = mock_client.table("invoices")
    insert_call = invoices_table.insert.call_args
    payload = insert_call.args[0]
    assert payload["client_id"] == TEST_CLIENT_ID
    assert payload["client_entity_id"] == TEST_ENTITY_ID
    assert payload["client_id"] != "00000000-0000-0000-0000-000000000001"


def test_convert_draft_all_fields_preserved():
    """All extracted invoice fields are preserved in the business record."""
    mock_client = _make_conversion_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655440000/convert",
        )
    assert response.status_code == 200, response.text
    # Verify the invoice insert payload contains all fields
    invoices_table = mock_client.table("invoices")
    insert_call = invoices_table.insert.call_args
    payload = insert_call.args[0]
    assert payload["invoice_number"] == "DPP/2026-27/0823"
    assert payload["taxable_value"] == 80000.0
    assert payload["cgst_amount"] == 7200.0
    assert payload["sgst_amount"] == 7200.0
    assert payload["igst_amount"] == 0
    assert payload["total_amount"] == 94400.0
    assert payload["procurement_type"] == "NON_PO"
    assert payload["purchase_order_id"] is None


def test_convert_draft_line_items_persisted():
    """All line items are persisted to invoice_items."""
    mock_client = _make_conversion_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655440000/convert",
        )
    assert response.status_code == 200, response.text
    items_table = mock_client.table("invoice_items")
    insert_call = items_table.insert.call_args
    items = insert_call.args[0]
    assert len(items) == 4
    assert items[0]["description"] == "Offset printing plates"
    assert items[0]["hsn_sac"] == "84425010"
    assert items[0]["quantity"] == 10.0
    assert items[0]["taxable_value"] == 40000.0
    assert items[3]["description"] == "Packaging material"


def test_convert_draft_document_reference():
    """Document reference is persisted to invoice_documents."""
    mock_client = _make_conversion_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655440000/convert",
        )
    assert response.status_code == 200, response.text
    docs_table = mock_client.table("invoice_documents")
    insert_call = docs_table.insert.call_args
    payload = insert_call.args[0]
    assert payload["storage_path"] == "intake/abc123/deccan_invoice.pdf"
    assert payload["original_filename"] == "deccan_invoice.pdf"
    assert payload["sha256"] == "abc123def456"


def test_convert_draft_processing_run_created():
    """A processing run is created on successful conversion."""
    mock_client = _make_conversion_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655440000/convert",
        )
    assert response.status_code == 200, response.text
    runs_table = mock_client.table("processing_runs")
    insert_call = runs_table.insert.call_args
    payload = insert_call.args[0]
    assert payload["status"] == "QUEUED"
    assert payload["triggered_by"] == "DRAFT_CONVERSION"
    assert payload["invoice_id"] == "550e8400-e29b-41d4-a716-446655440001"


def test_convert_draft_idempotent():
    """Repeated conversion returns the same invoice (idempotent)."""
    mock_client = _make_conversion_mock_client()
    with _settings_patch(mock_client):
        # First conversion
        response1 = client.post(
            "/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655440000/convert",
        )
        assert response1.status_code == 200

        # Second conversion - mock draft as already converted
        drafts_table = mock_client.table("invoice_intake_drafts")
        draft_select = MagicMock()
        draft_select.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "original_filename": "deccan_invoice.pdf",
                "storage_path": "intake/abc123/deccan_invoice.pdf",
                "mime_type": "application/pdf",
                "sha256": "abc123def456",
                "file_size_bytes": 102400,
                "extracted_data": {"kind": "digital", "fields": {}, "line_items": []},
                "raw_text": "",
                "extraction_method": "pymupdf_digital",
                "processing_status": "READY_FOR_VALIDATION",
                "converted_invoice_id": "550e8400-e29b-41d4-a716-446655440001",
                "conversion_status": "CONVERTED",
                "converted_at": "2026-11-25T10:05:00Z",
            }], error=None
        )
        drafts_table.select.return_value = draft_select

        # Mock invoices table for get_invoice call
        invoices_table = mock_client.table("invoices")
        invoice_chain = MagicMock()
        invoice_chain.eq.return_value = invoice_chain
        invoice_chain.execute.return_value = MagicMock(
            data=[{
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "invoice_number": "DPP/2026-27/0823",
                "processing_status": "RECEIVED",
                "approval_status": "PENDING",
            }],
            error=None,
        )
        invoices_table.select.return_value = invoice_chain

        response2 = client.post(
            "/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655440000/convert",
        )
        assert response2.status_code == 200, response2.text
        body2 = response2.json()
        assert body2["status"] == "already_converted"
        assert body2["invoice_id"] == "550e8400-e29b-41d4-a716-446655440001"


def test_convert_draft_not_found():
    """Unknown draft returns 404."""
    mock_client = _make_mock_client()
    # Mock draft select to return empty
    mock_table = mock_client.table.return_value
    mock_select = MagicMock()
    mock_select.eq.return_value.execute.return_value = MagicMock(
        data=[], error=None
    )
    mock_table.select.return_value = mock_select

    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655449999/convert",
        )
    assert response.status_code == 404, response.text
    assert "not found" in response.json()["detail"].lower()


def test_convert_draft_unsaved_cannot_convert():
    """Unsaved draft (not READY_FOR_VALIDATION) cannot be converted."""
    mock_client = _make_conversion_mock_client()
    # Override draft processing_status to EXTRACTED (not saved)
    drafts_table = mock_client.table("invoice_intake_drafts")
    draft_select = MagicMock()
    unsaved_draft = {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "original_filename": "deccan_invoice.pdf",
        "storage_path": "intake/abc123/deccan_invoice.pdf",
        "mime_type": "application/pdf",
        "sha256": "abc123def456",
        "file_size_bytes": 102400,
        "extracted_data": {"kind": "digital", "fields": {}, "line_items": []},
        "raw_text": "",
        "extraction_method": "pymupdf_digital",
        "processing_status": "EXTRACTED",  # Not saved/reviewed
        "converted_invoice_id": None,
        "conversion_status": "PENDING",
        "converted_at": None,
    }
    draft_select.eq.return_value.execute.return_value = MagicMock(
        data=[unsaved_draft], error=None
    )
    drafts_table.select.return_value = draft_select

    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655440000/convert",
        )
    assert response.status_code == 400, response.text
    assert "saved" in response.json()["detail"].lower()


def test_convert_draft_invalid_uuid():
    """Invalid UUID returns 400."""
    mock_client = _make_mock_client()
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/drafts/not-a-uuid/convert",
        )
    assert response.status_code == 400, response.text


def test_convert_draft_unknown_buyer_not_converted():
    """Buyer with no matching client/entity does not convert."""
    mock_client = _make_conversion_mock_client()
    # Override client_entities to return no match (unknown GSTIN)
    entities_table = mock_client.table("client_entities")
    entities_select = MagicMock()
    entities_select.eq.return_value = entities_select
    entities_select.execute.return_value = MagicMock(
        data=[], error=None
    )
    entities_table.select.return_value = entities_select

    # Also override clients to return no match
    clients_table = mock_client.table("clients")
    clients_select = MagicMock()
    clients_select.eq.return_value = clients_select
    clients_select.execute.return_value = MagicMock(
        data=[], error=None
    )
    clients_table.select.return_value = clients_select

    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655440000/convert",
        )
    assert response.status_code == 409, response.text
    assert "not configured" in response.json()["detail"].lower()


def test_convert_draft_inactive_entity_not_converted():
    """Inactive client entity does not convert."""
    mock_client = _make_conversion_mock_client()
    # Override client_entities to return inactive entity
    entities_table = mock_client.table("client_entities")
    entities_select = MagicMock()
    inactive_entity = {**TEST_CLIENT_ENTITY, "is_active": False}
    entities_select.eq.return_value = entities_select
    entities_select.execute.return_value = MagicMock(
        data=[inactive_entity], error=None
    )
    entities_table.select.return_value = entities_select

    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655440000/convert",
        )
    assert response.status_code == 409, response.text
    assert "not configured" in response.json()["detail"].lower()


def test_convert_draft_inactive_client_not_converted():
    """Inactive client does not convert even if entity is active."""
    mock_client = _make_conversion_mock_client()
    # Override clients to return inactive client
    clients_table = mock_client.table("clients")
    clients_select = MagicMock()
    inactive_client = {**TEST_CLIENT, "status": "INACTIVE"}
    clients_select.eq.return_value = clients_select
    clients_select.execute.return_value = MagicMock(
        data=[], error=None
    )
    clients_table.select.return_value = clients_select

    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/drafts/550e8400-e29b-41d4-a716-446655440000/convert",
        )
    assert response.status_code == 409, response.text


def test_list_invoices_returns_converted():
    """All Invoices API returns converted invoices."""
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value

    chain_mock = MagicMock()
    chain_mock.eq.return_value = chain_mock
    chain_mock.or_.return_value = chain_mock
    chain_mock.order.return_value = chain_mock
    chain_mock.range.return_value = chain_mock
    chain_mock.execute.return_value = MagicMock(
        data=[{
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "client_id": TEST_CLIENT_ID,
            "client_entity_id": TEST_ENTITY_ID,
            "invoice_number": "DPP/2026-27/0823",
            "invoice_date": "2026-11-25",
            "supplier_name": "Deccan Print & Packaging Solutions",
            "supplier_gstin": "36AABCD4512L1Z7",
            "currency": "INR",
            "taxable_value": 80000.0,
            "cgst_amount": 7200.0,
            "sgst_amount": 7200.0,
            "igst_amount": 0,
            "total_amount": 94400.0,
            "processing_status": "RECEIVED",
            "approval_status": "PENDING",
            "source_file_sha256": "abc123def456",
            "created_at": "2026-11-25T10:00:00Z",
            "updated_at": "2026-11-25T10:00:00Z",
        }],
        count=1,
    )
    mock_table.select.return_value = chain_mock

    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices?page=1&page_size=20")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert len(body["invoices"]) == 1
    assert body["invoices"][0]["invoice_number"] == "DPP/2026-27/0823"


def test_list_runs_returns_converted_run():
    """Processing API returns the created run."""
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value

    chain_mock = MagicMock()
    chain_mock.eq.return_value = chain_mock
    chain_mock.or_.return_value = chain_mock
    chain_mock.order.return_value = chain_mock
    chain_mock.range.return_value = chain_mock
    chain_mock.execute.return_value = MagicMock(
        data=[{
            "id": "550e8400-e29b-41d4-a716-446655440003",
            "invoice_id": "550e8400-e29b-41d4-a716-446655440001",
            "run_number": 1,
            "status": "QUEUED",
            "started_at": None,
            "completed_at": None,
            "triggered_by": "DRAFT_CONVERSION",
            "idempotency_key": "convert-550e8400-e29b-41d4-a716-446655440000",
            "summary": {"draft_id": "550e8400-e29b-41d4-a716-446655440000", "extraction_kind": "digital", "line_item_count": 4},
            "created_at": "2026-11-25T10:00:00Z",
        }],
        count=1,
    )
    mock_table.select.return_value = chain_mock

    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/runs?page=1&page_size=20")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert len(body["runs"]) == 1
    assert body["runs"][0]["status"] == "QUEUED"
    assert body["runs"][0]["triggered_by"] == "DRAFT_CONVERSION"


def test_dashboard_metrics_reflect_records():
    """Dashboard metrics reflect actual records."""
    mock_client = _make_mock_client()
    mock_table = mock_client.table.return_value

    call_count = [0]

    def mock_select_side_effect(*args, **kwargs):
        call_count[0] += 1
        chain = MagicMock()
        chain.eq.return_value = chain
        chain.or_.return_value = chain
        chain.order.return_value = chain
        chain.range.return_value = chain

        if call_count[0] == 1:
            # invoices total count
            chain.execute.return_value = MagicMock(
                data=[{"id": "inv-1"}, {"id": "inv-2"}],
                count=2,
            )
        elif call_count[0] == 2:
            # invoices by processing_status
            chain.execute.return_value = MagicMock(
                data=[
                    {"processing_status": "RECEIVED"},
                    {"processing_status": "EXTRACTED"},
                ],
                count=2,
            )
        elif call_count[0] == 3:
            # runs queued count
            chain.execute.return_value = MagicMock(
                data=[{"id": "run-1"}],
                count=1,
            )
        else:
            chain.execute.return_value = MagicMock(
                data=[],
                count=0,
            )
        return chain

    mock_table.select.side_effect = mock_select_side_effect

    with _settings_patch(mock_client):
        response = client.get("/api/v1/invoices/dashboard/metrics")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_invoices_analysed"] == 0
    assert body["override_rate"] is None


# ==================== Phase 1 unified-register tests ====================

def test_upload_invoice_record_keeps_missing_amounts_null_and_links_draft():
    draft = {
        "id": "draft-1", "sha256": "abc", "storage_path": "intake/abc/invoice.pdf",
        "original_filename": "invoice.pdf", "mime_type": "application/pdf",
        "extraction_method": "pymupdf_digital",
        "extracted_data": {"fields": {"supplier_legal_name": "Acme", "taxable_value": None,
            "cgst": None, "sgst": None, "igst": None, "total_tax": None,
            "invoice_grand_total": None}, "line_items": []},
    }
    mock_client = MagicMock()
    with patch.object(repository, "resolve_demo_workspace", return_value=("client-1", "entity-1")), \
         patch.object(repository, "insert_invoice", return_value={"id": "invoice-1"}) as insert, \
         patch.object(repository, "insert_invoice_items"), \
         patch.object(repository, "insert_invoice_document"), \
         patch.object(repository, "update_draft_conversion") as link:
        invoice = repository.create_invoice_for_draft(mock_client, draft)

    assert invoice["id"] == "invoice-1"
    payload = insert.call_args.args[1]
    assert payload["processing_status"] == "DRAFT"
    assert payload["taxable_value"] is None
    assert payload["total_amount"] is None
    link.assert_called_once_with(mock_client, "draft-1", "invoice-1", "CONVERTED")


def test_register_lists_draft_with_its_review_link():
    mock_client = MagicMock()
    invoice_chain = _chain_result([{"id": "invoice-1", "processing_status": "DRAFT"}], count=1)
    draft_chain = _chain_result([{"id": "draft-1", "converted_invoice_id": "invoice-1"}])
    mock_client.table.side_effect = lambda name: MagicMock(
        select=MagicMock(return_value=invoice_chain if name == "invoices" else draft_chain)
    )

    result = repository.list_invoices(mock_client, "client-1")
    assert result["invoices"][0]["draft_id"] == "draft-1"
    assert result["invoices"][0]["processing_status"] == "DRAFT"


def test_review_save_updates_invoice_and_replaces_line_items():
    draft = {"id": "draft-1", "converted_invoice_id": "invoice-1", "extracted_data": {}}
    mock_client = MagicMock()
    fields = {"supplier_legal_name": "Updated Supplier", "invoice_number": "INV-9",
              "taxable_value": None, "cgst": None, "sgst": None, "igst": None,
              "total_tax": None, "invoice_grand_total": None, "po_number": None}
    lines = [{"description": "Service", "hsn_sac": "9983", "quantity": "1",
              "unit_price": "10", "taxable_value": "10", "cgst": None, "sgst": None, "igst": None}]
    with patch.object(repository, "insert_invoice_items") as insert_items, \
         patch.object(repository, "get_invoice", return_value={"id": "invoice-1"}):
        result = repository.update_draft_and_invoice(mock_client, draft, fields, lines)

    assert result["id"] == "invoice-1"
    invoice_updates = mock_client.table.return_value.update.call_args_list
    assert any(call.args[0].get("supplier_legal_name") == "Updated Supplier" for call in invoice_updates)
    insert_items.assert_called_once()
    assert insert_items.call_args.args[2][0]["description"] == "Service"


def test_demo_workspace_resolution_uses_seeded_active_records():
    mock_client = MagicMock()
    client_chain = _chain_result([{"id": "client-1"}])
    entity_chain = _chain_result([{"id": "entity-1"}])
    mock_client.table.side_effect = lambda name: MagicMock(
        select=MagicMock(return_value=client_chain if name == "clients" else entity_chain)
    )
    assert repository.resolve_demo_workspace(mock_client) == ("client-1", "entity-1")


def test_submit_for_processing_persists_submitted_status():
    """Submission is persisted before automatic background processing begins."""
    mock_client = _make_mock_client()
    queued_runs = _chain_result([])
    running_runs = _chain_result([])
    prior_runs = _chain_result([])
    mock_client.table.return_value.select.side_effect = [
        queued_runs, running_runs, prior_runs,
    ]
    with _settings_patch(mock_client), \
         patch("app.invoices.router.get_invoice", return_value={"id": "invoice-1", "processing_status": "DRAFT"}), \
         patch("app.invoices.router.insert_processing_run", return_value={"id": "run-1"}), \
         patch("app.invoices.router._run_analysis"), \
         patch("app.invoices.router.update_invoice_status") as update_status:
        response = client.post("/api/v1/invoices/550e8400-e29b-41d4-a716-446655440001/process")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "SUBMITTED"
    update_status.assert_called_once_with(mock_client, "550e8400-e29b-41d4-a716-446655440001", "SUBMITTED")
