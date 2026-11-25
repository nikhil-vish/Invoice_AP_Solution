"""Backend tests for invoice intake upload."""

import io
from contextlib import ExitStack
from unittest.mock import patch, MagicMock

import fitz
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


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
    with _settings_patch(mock_client):
        response = client.post(
            "/api/v1/invoices/upload",
            files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "EXTRACTED"
    assert body["extraction_kind"] == "digital"
    assert body["ocr_supported"] is False
    assert body["filename"] == "invoice.pdf"
    assert body["fields"]["invoice_number"] == "INV-2024-001"
    # Supplier name extraction depends on text format;
    # with "TAX INVOICE" prefix, the supplier field is found
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