from app.invoices.matching import phase4_checks


def invoice(**updates):
    result = {"po_number": "PO-1", "total_amount": "118", "invoice_date": "2026-01-01", "due_date": "2026-01-31"}
    result.update(updates)
    return result


def test_po_and_line_matching_detects_quantity_and_price_discrepancies():
    po = {"total_amount": "118", "items": [{"description": "Paper", "quantity": "2", "unit_price": "50"}]}
    checks = phase4_checks(invoice(), [{"description": "Paper", "quantity": "3", "unit_price": "55"}], po, [])
    by_rule = {check["rule_code"]: check for check in checks}
    assert by_rule["PO_MATCH"]["status"] == "PASSED"
    assert by_rule["PO_LINE_MATCH"]["status"] == "FAILED"


def test_history_anomaly_and_unknown_values_are_explainable():
    history = [{"total_amount": "100"}, {"total_amount": "110"}, {"total_amount": "90"}]
    checks = phase4_checks(invoice(total_amount="500"), [], None, history)
    by_rule = {check["rule_code"]: check for check in checks}
    assert by_rule["PO_MATCH"]["status"] == "FAILED"
    assert by_rule["SUPPLIER_AMOUNT_ANOMALY"]["status"] == "WARNING"
    assert by_rule["PAYMENT_TERMS"]["status"] == "PASSED"
