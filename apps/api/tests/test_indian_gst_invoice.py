"""Real Indian GST invoice extraction tests.

Tests the actual extraction pipeline (PyMuPDF -> regex fallback -> optional AI)
using a synthetic Indian GST invoice PDF fixture.

The fixture is synthetic software-testing data, not a valid tax invoice.
"""

import io
import json
from unittest.mock import MagicMock, patch

import fitz
import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.invoices.extract import extract_invoice_pdf, _run_ai_extraction
from app.invoices.ai_extract import extract_with_ai
from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Synthetic Indian GST invoice PDF fixture
# ---------------------------------------------------------------------------

def _make_indian_gst_invoice_pdf() -> bytes:
    """Generate a synthetic Indian GST invoice PDF with selectable digital text.

    Contains:
    - Supplier: Bluepeak Office Supplies (Sample) Pvt. Ltd. (GSTIN: 27AAAAA0000A1Z5)
    - Buyer: Northstar Digital Services (Sample) Pvt. Ltd. (GSTIN: 27BBBBB1111B1Z6)
    - Invoice: BOS/26-27/0042, dated 25-Nov-2026, due 25-Dec-2026
    - PO: NSDS/PO/2026/118, Currency: INR
    - Two line items with HSN codes, quantities, unit prices, taxable values
    - Tax breakdown: CGST 1,080 + SGST 1,080 = Total GST 2,160
    - Grand total: 14,160
    """
    doc = fitz.open()
    page = doc.new_page()

    y = 72
    line_height = 18

    def write_line(text: str, x: float = 72, size: float = 11, bold: bool = False):
        nonlocal y
        fontname = "hebo" if bold else "helv"
        page.insert_text((x, y), text, fontname=fontname, fontsize=size)
        y += line_height

    # Header
    write_line("TAX INVOICE", bold=True, size=16)
    y += 10

    # Supplier block
    write_line("Supplier:", bold=True)
    write_line("Bluepeak Office Supplies (Sample) Pvt. Ltd.")
    write_line("GSTIN: 27AAAAA0000A1Z5")
    y += 6

    # Buyer block
    write_line("Buyer:", bold=True)
    write_line("Northstar Digital Services (Sample) Pvt. Ltd.")
    write_line("GSTIN: 27BBBBB1111B1Z6")
    y += 10

    # Invoice details
    write_line("Invoice Number: BOS/26-27/0042")
    write_line("Invoice Date: 25/11/2026")
    write_line("Due Date: 25/12/2026")
    write_line("Purchase Order: NSDS/PO/2026/118")
    write_line("Currency: INR")
    y += 10

    # Line items header
    write_line("Line Items:", bold=True)
    write_line("Description                          HSN/SAC    Qty  Unit Price   Taxable")
    write_line("Laptop docking station               84718000   2    4,500        9,000")
    write_line("Keyboard/mouse combo                 84716060   3    1,000        3,000")
    y += 10

    # Totals
    write_line("Taxable Value: 12,000")
    write_line("CGST: 1,080")
    write_line("SGST: 1,080")
    write_line("Total GST: 2,160")
    write_line("Grand Total: 14,160")

    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Expected values
# ---------------------------------------------------------------------------

EXPECTED_SUPPLIER_NAME = "Bluepeak Office Supplies (Sample) Pvt. Ltd."
EXPECTED_SUPPLIER_GSTIN = "27AAAAA0000A1Z5"
EXPECTED_BUYER_NAME = "Northstar Digital Services (Sample) Pvt. Ltd."
EXPECTED_BUYER_GSTIN = "27BBBBB1111B1Z6"
EXPECTED_INVOICE_NUMBER = "BOS/26-27/0042"
EXPECTED_INVOICE_DATE = "2026-11-25"
EXPECTED_DUE_DATE = "2026-12-25"
EXPECTED_PO_NUMBER = "NSDS/PO/2026/118"
EXPECTED_CURRENCY = "INR"

EXPECTED_LINE_ITEMS = [
    {
        "description": "Laptop docking station",
        "quantity": 2,
        "unit_price": 4500.0,
        "taxable_value": 9000.0,
        "hsn_sac": "84718000",
    },
    {
        "description": "Keyboard/mouse combo",
        "quantity": 3,
        "unit_price": 1000.0,
        "taxable_value": 3000.0,
        "hsn_sac": "84716060",
    },
]

EXPECTED_TOTALS = {
    "taxable_value": 12000.0,
    "cgst": 1080.0,
    "sgst": 1080.0,
    "total_tax": 2160.0,
    "invoice_grand_total": 14160.0,
}


# ---------------------------------------------------------------------------
# Helper: valid OpenRouter JSON response
# ---------------------------------------------------------------------------

def _valid_ai_extraction_json() -> str:
    return json.dumps({
        "supplier_name": EXPECTED_SUPPLIER_NAME,
        "supplier_gstin": EXPECTED_SUPPLIER_GSTIN,
        "buyer_name": EXPECTED_BUYER_NAME,
        "buyer_gstin": EXPECTED_BUYER_GSTIN,
        "invoice_number": EXPECTED_INVOICE_NUMBER,
        "invoice_date": EXPECTED_INVOICE_DATE,
        "due_date": EXPECTED_DUE_DATE,
        "po_number": EXPECTED_PO_NUMBER,
        "currency": EXPECTED_CURRENCY,
        "taxable_value": EXPECTED_TOTALS["taxable_value"],
        "cgst": EXPECTED_TOTALS["cgst"],
        "sgst": EXPECTED_TOTALS["sgst"],
        "igst": None,
        "total_tax": EXPECTED_TOTALS["total_tax"],
        "grand_total": EXPECTED_TOTALS["invoice_grand_total"],
        "line_items": [
            {
                "description": EXPECTED_LINE_ITEMS[0]["description"],
                "hsn_sac": EXPECTED_LINE_ITEMS[0]["hsn_sac"],
                "quantity": EXPECTED_LINE_ITEMS[0]["quantity"],
                "unit_price": EXPECTED_LINE_ITEMS[0]["unit_price"],
                "taxable_value": EXPECTED_LINE_ITEMS[0]["taxable_value"],
            },
            {
                "description": EXPECTED_LINE_ITEMS[1]["description"],
                "hsn_sac": EXPECTED_LINE_ITEMS[1]["hsn_sac"],
                "quantity": EXPECTED_LINE_ITEMS[1]["quantity"],
                "unit_price": EXPECTED_LINE_ITEMS[1]["unit_price"],
                "taxable_value": EXPECTED_LINE_ITEMS[1]["taxable_value"],
            },
        ],
    })


# ---------------------------------------------------------------------------
# Mock HTTP response helpers
# ---------------------------------------------------------------------------

def _make_success_response(content: str):
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": content}}]}
    mock_response.raise_for_status = MagicMock()
    return mock_response


def _make_async_client(mock_response):
    mock_client = MagicMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post = MagicMock(return_value=mock_response)
    # Make post awaitable
    async def _post(*args, **kwargs):
        return mock_response
    mock_client.post = _post
    return mock_client


# ---------------------------------------------------------------------------
# Tests: AI disabled (deterministic regex fallback)
# ---------------------------------------------------------------------------

class TestExtractionWithAIDisabled:
    """Verify deterministic regex fallback when AI extraction is disabled."""

    def test_pdf_has_selectable_text(self):
        """The synthetic fixture must contain extractable digital text."""
        pdf_bytes = _make_indian_gst_invoice_pdf()
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        raw_text = "\n".join(page.get_text("text") or "" for page in document)
        document.close()
        assert EXPECTED_SUPPLIER_NAME in raw_text
        assert EXPECTED_SUPPLIER_GSTIN in raw_text
        assert EXPECTED_BUYER_NAME in raw_text
        assert EXPECTED_BUYER_GSTIN in raw_text
        assert EXPECTED_INVOICE_NUMBER in raw_text
        assert "Laptop docking station" in raw_text
        assert "Keyboard/mouse combo" in raw_text

    def test_extraction_pipeline_ai_disabled(self):
        """With AI disabled, regex fallback must extract key fields correctly."""
        pdf_bytes = _make_indian_gst_invoice_pdf()

        with patch.object(settings, "ai_extraction_enabled", False):
            result = extract_invoice_pdf(pdf_bytes)

        assert result["kind"] == "digital"
        fields = result["fields"]
        field_status = result["field_status"]

        # Supplier and buyer GSTINs must not be swapped
        assert fields["supplier_gstin"] == EXPECTED_SUPPLIER_GSTIN, \
            f"Supplier GSTIN mismatch: {fields['supplier_gstin']}"
        assert fields["buyer_gstin"] == EXPECTED_BUYER_GSTIN, \
            f"Buyer GSTIN mismatch: {fields['buyer_gstin']}"
        assert fields["supplier_gstin"] != fields["buyer_gstin"], \
            "Supplier and buyer GSTINs must differ"

        # Invoice number and date
        assert EXPECTED_INVOICE_NUMBER in str(fields.get("invoice_number")), \
            f"Invoice number not found: {fields.get('invoice_number')}"
        assert EXPECTED_INVOICE_DATE == str(fields.get("invoice_date")), \
            f"Invoice date mismatch: {fields.get('invoice_date')}"

        # Line items extracted
        items = result["line_items"]
        assert len(items) == 2, f"Expected 2 line items, got {len(items)}"

        # Verify arithmetic: taxable values sum
        item_totals = [it.get("taxable_value") for it in items if it.get("taxable_value")]
        assert sum(item_totals) == EXPECTED_TOTALS["taxable_value"], \
            f"Line item taxable sum mismatch: {sum(item_totals)}"

        # Currency
        assert fields.get("currency") == EXPECTED_CURRENCY, \
            f"Currency mismatch: {fields.get('currency')}"

        # Missing fields are not fabricated
        for key in ["discount", "freight", "cess", "round_off"]:
            assert fields.get(key) is None or fields.get(key) == 0, \
                f"Field {key} should be null/missing, got {fields.get(key)}"


# ---------------------------------------------------------------------------
# Tests: AI enabled with mocked OpenRouter
# ---------------------------------------------------------------------------

class TestExtractionWithAIMocked:
    """Verify full pipeline with AI enabled and mocked OpenRouter HTTP response."""

    @pytest.mark.asyncio
    async def test_ai_extraction_success(self):
        """With AI enabled and a successful OpenRouter response, structured extraction
        must conform to the Pydantic schema and match expected values."""
        pdf_bytes = _make_indian_gst_invoice_pdf()
        ai_json = _valid_ai_extraction_json()
        mock_response = _make_success_response(ai_json)
        mock_client = _make_async_client(mock_response)

        with patch.object(settings, "ai_extraction_enabled", True), \
             patch.object(settings, "openrouter_api_key", "test-key"), \
             patch.object(settings, "openrouter_model", "test-model"), \
             patch("app.invoices.ai_extract.httpx.AsyncClient", return_value=mock_client):
            result = await extract_with_ai(pdf_bytes.decode("utf-8", errors="replace")[:1000])

        assert result is not None
        assert result.kind == "ai_enhanced"
        extraction = result.extraction

        # Supplier and buyer GSTINs not swapped
        assert extraction.supplier_gstin == EXPECTED_SUPPLIER_GSTIN
        assert extraction.buyer_gstin == EXPECTED_BUYER_GSTIN
        assert extraction.supplier_gstin != extraction.buyer_gstin

        # Invoice fields
        assert extraction.invoice_number == EXPECTED_INVOICE_NUMBER
        assert extraction.invoice_date == EXPECTED_INVOICE_DATE

        # Line items
        assert len(extraction.line_items) == 2
        li1 = extraction.line_items[0]
        assert li1.description == EXPECTED_LINE_ITEMS[0]["description"]
        assert li1.hsn_sac == EXPECTED_LINE_ITEMS[0]["hsn_sac"]
        assert li1.quantity == EXPECTED_LINE_ITEMS[0]["quantity"]
        assert li1.unit_price == EXPECTED_LINE_ITEMS[0]["unit_price"]
        assert li1.taxable_value == EXPECTED_LINE_ITEMS[0]["taxable_value"]

        li2 = extraction.line_items[1]
        assert li2.description == EXPECTED_LINE_ITEMS[1]["description"]
        assert li2.hsn_sac == EXPECTED_LINE_ITEMS[1]["hsn_sac"]

        # Arithmetic
        assert extraction.taxable_value == EXPECTED_TOTALS["taxable_value"]
        assert extraction.cgst == EXPECTED_TOTALS["cgst"]
        assert extraction.sgst == EXPECTED_TOTALS["sgst"]
        assert extraction.total_tax == EXPECTED_TOTALS["total_tax"]
        assert extraction.grand_total == EXPECTED_TOTALS["invoice_grand_total"]

    @pytest.mark.asyncio
    async def test_ai_extraction_malformed_json(self):
        """Malformed JSON from OpenRouter must return None (graceful fallback)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "not valid json {{{"}}]}
        mock_response.raise_for_status = MagicMock()

        async def _post(*args, **kwargs):
            return mock_response
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = _post

        with patch.object(settings, "ai_extraction_enabled", True), \
             patch.object(settings, "openrouter_api_key", "test-key"), \
             patch.object(settings, "openrouter_model", "test-model"), \
             patch("app.invoices.ai_extract.httpx.AsyncClient", return_value=mock_client):
            result = await extract_with_ai("some invoice text")

        assert result is None

    @pytest.mark.asyncio
    async def test_ai_extraction_empty_content(self):
        """Empty content from OpenRouter must return None (graceful fallback)."""
        mock_response = _make_success_response("")
        mock_client = _make_async_client(mock_response)

        with patch.object(settings, "ai_extraction_enabled", True), \
             patch.object(settings, "openrouter_api_key", "test-key"), \
             patch.object(settings, "openrouter_model", "test-model"), \
             patch("app.invoices.ai_extract.httpx.AsyncClient", return_value=mock_client):
            result = await extract_with_ai("some invoice text")

        assert result is None

    @pytest.mark.asyncio
    async def test_ai_extraction_auth_failure(self):
        """401 from OpenRouter must return None (graceful fallback)."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=mock_response
        )
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client

        async def _post(*args, **kwargs):
            return mock_response
        mock_client.post = _post

        with patch.object(settings, "ai_extraction_enabled", True), \
             patch.object(settings, "openrouter_api_key", "test-key"), \
             patch.object(settings, "openrouter_model", "test-model"), \
             patch("app.invoices.ai_extract.httpx.AsyncClient", return_value=mock_client):
            result = await extract_with_ai("some invoice text")

        assert result is None


# ---------------------------------------------------------------------------
# Tests: Run-async helper in both sync and async contexts
# ---------------------------------------------------------------------------

class TestRunAsyncAIExtraction:
    """Verify _run_ai_extraction works in both sync and async contexts."""

    def test_run_ai_extraction_sync_context(self):
        """In a sync context (no running event loop), _run_ai_extraction uses asyncio.run()."""
        with patch.object(settings, "ai_extraction_enabled", True), \
             patch.object(settings, "openrouter_api_key", ""):
            # Not configured - should return None gracefully
            result = _run_ai_extraction("some text")
            assert result is None

    @pytest.mark.asyncio
    async def test_run_ai_extraction_async_context(self):
        """In an async context (running event loop), _run_ai_extraction uses a thread pool."""
        with patch.object(settings, "ai_extraction_enabled", True), \
             patch.object(settings, "openrouter_api_key", ""):
            # Not configured - should return None gracefully even in async context
            result = _run_ai_extraction("some text")
            assert result is None


# ---------------------------------------------------------------------------
# Manual live-model test (not in default suite)
# ---------------------------------------------------------------------------

@pytest.mark.live_model
class TestLiveModelExtraction:
    """Manual live-model test against OpenRouter.

    Not run by default. Execute with:
        pytest tests/test_indian_gst_invoice.py -m live_model -v
    Requires OPENROUTER_API_KEY and OPENROUTER_MODEL to be set in .env.
    """

    @pytest.mark.asyncio
    async def test_live_extraction_against_sample(self):
        """Run actual OpenRouter extraction against the synthetic invoice PDF."""
        if not settings.openrouter_api_key or not settings.openrouter_model:
            pytest.skip("OpenRouter not configured - skipping live model test")

        pdf_bytes = _make_indian_gst_invoice_pdf()
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        raw_text = "\n".join(page.get_text("text") or "" for page in document)
        document.close()

        result = await extract_with_ai(raw_text)

        assert result is not None
        assert result.extraction is not None
        extraction = result.extraction

        assert extraction.supplier_gstin == EXPECTED_SUPPLIER_GSTIN
        assert extraction.buyer_gstin == EXPECTED_BUYER_GSTIN
        assert extraction.supplier_gstin != extraction.buyer_gstin
        assert len(extraction.line_items) == 2
        assert extraction.grand_total == EXPECTED_TOTALS["invoice_grand_total"]
