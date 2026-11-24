from app.invoices.extract import field_status
from app.invoices.fields import HEADER_FIELDS, LINE_FIELDS


def blank_fields() -> dict:
    return {key: None for key in HEADER_FIELDS}


def blank_line() -> dict:
    return {key: None for key in LINE_FIELDS}


def normalize_fields(payload: dict | None) -> dict:
    incoming = payload or {}
    fields = blank_fields()
    for key in HEADER_FIELDS:
        if key in incoming:
            fields[key] = _empty_to_none(incoming[key])
    return fields


def normalize_lines(payload: list | None) -> list[dict]:
    lines = []
    for item in payload or []:
        line = blank_line()
        if not isinstance(item, dict):
            continue
        for key in LINE_FIELDS:
            if key in item:
                line[key] = _empty_to_none(item[key])
        if any(value is not None for value in line.values()):
            lines.append(line)
    return lines


def extraction_summary(filename: str, size_bytes: int, extraction: dict, intake_status: str = "DRAFT") -> dict:
    # Handle both digital and scanned PDF extraction results
    if extraction.get("kind") == "scanned":
        fields = blank_fields()
        line_items = []
    else:
        fields = normalize_fields(extraction.get("fields") or {})
        line_items = extraction.get("line_items") or []
    return {
        "extractor": "pymupdf",
        "ocr_supported": False,
        "raw_text": extraction.get("raw_text") or "",
        "fields": fields,
        "field_status": field_status(fields),
        "line_items": normalize_lines(line_items),
        "intake_status": intake_status,
        "filename": filename,
        "size_bytes": size_bytes,
    }


def invoice_columns(fields: dict) -> dict:
    return {
        "invoice_number": fields.get("invoice_number"),
        "invoice_date": fields.get("invoice_date"),
        "currency": fields.get("currency"),
        "taxable_value": fields.get("taxable_value"),
        "cgst_amount": fields.get("cgst"),
        "sgst_amount": fields.get("sgst"),
        "igst_amount": fields.get("igst"),
        "total_amount": fields.get("invoice_grand_total"),
    }


def line_columns(invoice_id: str, line_number: int, line: dict) -> dict:
    return {
        "invoice_id": invoice_id,
        "line_number": line_number,
        "description": line.get("description"),
        "hsn_sac": line.get("hsn_sac"),
        "quantity": line.get("quantity"),
        "unit_price": line.get("unit_price"),
        "taxable_value": line.get("taxable_value"),
        "cgst_amount": line.get("cgst"),
        "sgst_amount": line.get("sgst"),
        "igst_amount": line.get("igst"),
    }


def _empty_to_none(value):
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value
