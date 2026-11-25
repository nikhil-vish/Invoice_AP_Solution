"""Deterministic invoice validation. Financial comparisons use Decimal only."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
REQUIRED_FIELDS = (
    "supplier_legal_name", "supplier_gstin", "invoice_number", "invoice_date",
    "buyer_legal_name", "buyer_gstin", "currency", "invoice_grand_total",
)
TOLERANCE = Decimal("1.00")


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def valid_gstin(value: str | None) -> bool:
    if not value or not GSTIN_RE.fullmatch(value.upper()):
        return False
    total = 0
    factor = 2
    for char in reversed(value.upper()[:-1]):
        code = GST_CHARS.index(char)
        product = code * factor
        total += product // 36 + product % 36
        factor = 1 if factor == 2 else 2
    return GST_CHARS[(36 - total % 36) % 36] == value.upper()[-1]


def _result(rule_code: str, status: str, message: str, evidence: dict | None = None) -> dict:
    return {"rule_code": rule_code, "status": status, "message": message, "evidence": evidence or {}}


def validate_invoice(invoice: dict, items: list[dict], duplicate_exists: bool) -> list[dict]:
    """Return six explainable validation results without altering invoice values."""
    missing = [field for field in REQUIRED_FIELDS if invoice.get(field) in (None, "")]
    results = [_result("REQUIRED_FIELDS", "FAILED" if missing else "PASSED",
        "Missing required fields: " + ", ".join(missing) if missing else "Required fields are present.", {"missing_fields": missing})]
    for field, rule in (("supplier_gstin", "SUPPLIER_GSTIN"), ("buyer_gstin", "BUYER_GSTIN")):
        value = invoice.get(field)
        results.append(_result(rule, "PASSED" if valid_gstin(value) else "FAILED",
            "GSTIN checksum is valid." if valid_gstin(value) else "GSTIN is missing, malformed, or has an invalid checksum.", {field: value}))
    results.append(_result("DUPLICATE_INVOICE", "FAILED" if duplicate_exists else "PASSED",
        "A matching supplier GSTIN and invoice number already exists." if duplicate_exists else "No matching supplier GSTIN and invoice number found.",
        {"supplier_gstin": invoice.get("supplier_gstin"), "invoice_number": invoice.get("invoice_number")}))
    components = [decimal_or_none(invoice.get(key)) for key in ("taxable_value", "cgst_amount", "sgst_amount", "igst_amount")]
    grand_total = decimal_or_none(invoice.get("total_amount"))
    if grand_total is None or any(value is None for value in components):
        results.append(_result("TAX_RECONCILIATION", "SKIPPED", "Tax reconciliation needs taxable value, all tax amounts, and grand total."))
    else:
        expected = sum(components, Decimal("0"))
        diff = abs(expected - grand_total)
        results.append(_result("TAX_RECONCILIATION", "PASSED" if diff <= TOLERANCE else "FAILED",
            "Tax totals reconcile within tolerance." if diff <= TOLERANCE else "Tax components do not reconcile to grand total.",
            {"expected_total": str(expected), "grand_total": str(grand_total), "difference": str(diff), "tolerance": str(TOLERANCE)}))
    if not items:
        results.append(_result("LINE_ITEM_RECONCILIATION", "SKIPPED", "No line items are available for reconciliation."))
    else:
        fields = (("taxable_value", "taxable_value"), ("cgst_amount", "cgst_amount"), ("sgst_amount", "sgst_amount"), ("igst_amount", "igst_amount"))
        unknown_line_values = [header for header, line in fields if any(decimal_or_none(item.get(line)) is None for item in items)]
        sums = {header: sum((decimal_or_none(item.get(line)) or Decimal("0")) for item in items) for header, line in fields}
        headers = {"taxable_value": decimal_or_none(invoice.get("taxable_value")), "cgst_amount": decimal_or_none(invoice.get("cgst_amount")), "sgst_amount": decimal_or_none(invoice.get("sgst_amount")), "igst_amount": decimal_or_none(invoice.get("igst_amount"))}
        unknown = [key for key, value in headers.items() if value is None]
        differences = {key: abs(sums[key] - value) for key, value in headers.items() if value is not None}
        passed = not unknown and not unknown_line_values and all(value <= TOLERANCE for value in differences.values())
        incomplete = unknown or unknown_line_values
        results.append(_result("LINE_ITEM_RECONCILIATION", "SKIPPED" if incomplete else ("PASSED" if passed else "FAILED"),
            "Line-item reconciliation needs complete header and line-item amounts." if incomplete else ("Line items reconcile with invoice totals." if passed else "Line items do not reconcile with invoice totals."),
            {"line_item_sums": {k: str(v) for k, v in sums.items()}, "differences": {k: str(v) for k, v in differences.items()}, "unknown_headers": unknown, "unknown_line_values": unknown_line_values}))
    return results
