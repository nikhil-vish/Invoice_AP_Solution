"""Phase 4 deterministic matching.  All monetary comparison uses Decimal."""
from decimal import Decimal
from datetime import date
from typing import Any
from app.invoices.validation import decimal_or_none, TOLERANCE, _result


def _line_match(invoice_line: dict, po_lines: list[dict]) -> dict | None:
    text = (invoice_line.get("description") or "").strip().lower()
    for line in po_lines:
        po_text = (line.get("description") or "").strip().lower()
        if text and po_text and (text in po_text or po_text in text):
            return line
    return None


def phase4_checks(invoice: dict, items: list[dict], po: dict | None, history: list[dict]) -> list[dict]:
    """Return explainable PO, commercial-history and due-date checks; unknowns stay skipped."""
    results: list[dict] = []
    po_number = invoice.get("po_number")
    if not po_number:
        results.append(_result("PO_MATCH", "SKIPPED", "Invoice has no purchase-order reference."))
        results.append(_result("PO_LINE_MATCH", "SKIPPED", "Invoice has no purchase-order reference."))
    elif not po:
        results.append(_result("PO_MATCH", "FAILED", "No imported purchase order matches the invoice PO number.", {"po_number": po_number}))
        results.append(_result("PO_LINE_MATCH", "SKIPPED", "Line matching requires an imported purchase order."))
    else:
        total, po_total = decimal_or_none(invoice.get("total_amount")), decimal_or_none(po.get("total_amount"))
        if total is None or po_total is None:
            results.append(_result("PO_MATCH", "SKIPPED", "PO amount matching requires known invoice and PO totals."))
        else:
            diff = abs(total - po_total)
            results.append(_result("PO_MATCH", "PASSED" if diff <= TOLERANCE else "FAILED",
                "Invoice total matches PO." if diff <= TOLERANCE else "Invoice total differs from PO.",
                {"invoice_total": str(total), "po_total": str(po_total), "difference": str(diff)}))
        po_lines = po.get("items") or []
        if not items or not po_lines:
            results.append(_result("PO_LINE_MATCH", "SKIPPED", "Line matching requires invoice and PO line items."))
        else:
            discrepancies = []
            for item in items:
                matched = _line_match(item, po_lines)
                if not matched:
                    discrepancies.append({"description": item.get("description"), "reason": "no matching PO line"}); continue
                quantity, po_quantity = decimal_or_none(item.get("quantity")), decimal_or_none(matched.get("quantity"))
                price, po_price = decimal_or_none(item.get("unit_price")), decimal_or_none(matched.get("unit_price"))
                if quantity is not None and po_quantity is not None and quantity > po_quantity:
                    discrepancies.append({"description": item.get("description"), "reason": "quantity exceeds PO", "invoice_quantity": str(quantity), "po_quantity": str(po_quantity)})
                if price is not None and po_price is not None and abs(price - po_price) > TOLERANCE:
                    discrepancies.append({"description": item.get("description"), "reason": "unit price differs", "invoice_price": str(price), "po_price": str(po_price)})
            results.append(_result("PO_LINE_MATCH", "FAILED" if discrepancies else "PASSED",
                "Invoice lines match the PO." if not discrepancies else "Invoice line discrepancies found against PO.", {"discrepancies": discrepancies}))
    current = decimal_or_none(invoice.get("total_amount"))
    historical = [decimal_or_none(row.get("total_amount")) for row in history]
    known = [value for value in historical if value is not None]
    if current is None or len(known) < 3:
        results.append(_result("SUPPLIER_AMOUNT_ANOMALY", "SKIPPED", "Amount comparison needs a known total and at least three historical supplier invoices."))
    else:
        average = sum(known, Decimal("0")) / Decimal(len(known))
        anomalous = average > 0 and (current > average * Decimal("2") or current < average / Decimal("2"))
        results.append(_result("SUPPLIER_AMOUNT_ANOMALY", "WARNING" if anomalous else "PASSED",
            "Invoice amount is outside the supplier's usual range." if anomalous else "Invoice amount is within the supplier's usual range.",
            {"invoice_total": str(current), "historical_average": str(average), "sample_size": len(known)}))
    try:
        terms = (date.fromisoformat(str(invoice["due_date"])) - date.fromisoformat(str(invoice["invoice_date"]))).days if invoice.get("due_date") and invoice.get("invoice_date") else None
    except ValueError:
        terms = None
    if terms is None:
        results.append(_result("PAYMENT_TERMS", "SKIPPED", "Payment terms/due-date analysis requires invoice date and due date."))
    else:
        results.append(_result("PAYMENT_TERMS", "PASSED" if 0 <= terms <= 180 else "WARNING",
            "Payment terms are within the configured review range." if 0 <= terms <= 180 else "Payment terms are unusually short or long.", {"payment_terms_days": terms}))
    return results
