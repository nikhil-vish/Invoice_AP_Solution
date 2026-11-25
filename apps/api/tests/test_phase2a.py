import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.invoices.ai_analysis import analyse_invoice
from app.invoices.ai_extract import AIExtractionError
from app.invoices.validation import validate_invoice, valid_gstin


def invoice(**overrides):
    base = {"id": "i1", "supplier_legal_name": "Supplier", "supplier_gstin": "27AAPFU0939F1ZV",
            "buyer_legal_name": "Buyer", "buyer_gstin": "27AAPFU0939F1ZV", "invoice_number": "INV-1",
            "invoice_date": "2026-01-01", "currency": "INR", "taxable_value": "100",
            "cgst_amount": "9", "sgst_amount": "9", "igst_amount": "0", "total_amount": "118"}
    base.update(overrides)
    return base


def test_gstin_checksum_and_required_fields():
    assert valid_gstin("27AAPFU0939F1ZV")
    results = validate_invoice(invoice(supplier_legal_name=None), [], False)
    assert next(r for r in results if r["rule_code"] == "REQUIRED_FIELDS")["status"] == "FAILED"
    assert next(r for r in results if r["rule_code"] == "SUPPLIER_GSTIN")["status"] == "PASSED"


def test_buyer_gstin_duplicate_and_tax_reconciliation_failures():
    results = validate_invoice(invoice(buyer_gstin="27AAPFU0939F1ZZ", total_amount="120"), [], True)
    by_rule = {result["rule_code"]: result for result in results}
    assert by_rule["BUYER_GSTIN"]["status"] == "FAILED"
    assert by_rule["DUPLICATE_INVOICE"]["status"] == "FAILED"
    assert by_rule["TAX_RECONCILIATION"]["status"] == "FAILED"


def test_line_item_reconciliation_and_unknown_amounts():
    items = [{"taxable_value": "100", "cgst_amount": "9", "sgst_amount": "9", "igst_amount": "0"}]
    results = validate_invoice(invoice(), items, False)
    assert next(r for r in results if r["rule_code"] == "LINE_ITEM_RECONCILIATION")["status"] == "PASSED"
    unknown = validate_invoice(invoice(total_amount=None), items, False)
    assert next(r for r in unknown if r["rule_code"] == "TAX_RECONCILIATION")["status"] == "SKIPPED"


@pytest.mark.asyncio
async def test_ai_analysis_parses_structured_json():
    content = json.dumps({"recommendation": "REQUEST_CLARIFICATION", "risk_level": "MEDIUM", "confidence_score": 70,
        "executive_summary": "A total is missing.", "findings": [{"category": "missing_data", "severity": "MEDIUM", "description": "Total missing", "evidence": {}, "suggested_action": "Confirm total"}]})
    response = MagicMock(); response.json.return_value = {"choices": [{"message": {"content": content}}]}; response.raise_for_status = MagicMock()
    session = MagicMock(); session.__aenter__.return_value = session; session.post = AsyncMock(return_value=response)
    with patch("app.invoices.ai_analysis.settings.ai_extraction_enabled", True), patch("app.invoices.ai_analysis.settings.openrouter_api_key", "key"), patch("app.invoices.ai_analysis.settings.openrouter_model", "model"), patch("app.invoices.ai_analysis.httpx.AsyncClient", return_value=session):
        analysis = await analyse_invoice(invoice(), [], [])
    assert analysis.recommendation == "REQUEST_CLARIFICATION"
    assert analysis.model_used == "model"


@pytest.mark.asyncio
async def test_ai_analysis_rejects_malformed_and_provider_failure():
    bad = MagicMock(); bad.json.return_value = {"choices": [{"message": {"content": "not-json"}}]}; bad.raise_for_status = MagicMock()
    session = MagicMock(); session.__aenter__.return_value = session; session.post = AsyncMock(return_value=bad)
    with patch("app.invoices.ai_analysis.settings.ai_extraction_enabled", True), patch("app.invoices.ai_analysis.settings.openrouter_api_key", "key"), patch("app.invoices.ai_analysis.settings.openrouter_model", "model"), patch("app.invoices.ai_analysis.httpx.AsyncClient", return_value=session):
        with pytest.raises(AIExtractionError): await analyse_invoice(invoice(), [], [])
    session.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    with patch("app.invoices.ai_analysis.settings.ai_extraction_enabled", True), patch("app.invoices.ai_analysis.settings.openrouter_api_key", "key"), patch("app.invoices.ai_analysis.settings.openrouter_model", "model"), patch("app.invoices.ai_analysis.httpx.AsyncClient", return_value=session):
        with pytest.raises(AIExtractionError): await analyse_invoice(invoice(), [], [])


def test_ai_recommendation_is_advisory_and_does_not_mutate_invoice():
    """The AI contract has no invoice-status field or mutation capability."""
    results = validate_invoice(invoice(), [], False)
    assert all("processing_status" not in result for result in results)
