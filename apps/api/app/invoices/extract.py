import re
from datetime import date
from decimal import Decimal, InvalidOperation

import fitz

from app.invoices.fields import HEADER_FIELDS, LINE_FIELDS

GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")
SKIP_LINE = re.compile(
    r"^(tax invoice|gst invoice|invoice|original(?: for recipient)?|duplicate|triplicate)$",
    re.IGNORECASE,
)
BUYER_SPLIT = re.compile(
    r"(?im)^[ \t]*(?:bill to|billed to|buyer|details of (?:the )?buyer|customer)\b.*$"
)
PIPE_LINE = re.compile(
    r"^(?P<desc>.+?)\s*\|\s*(?P<hsn>\d{4,8})\s*\|\s*(?P<qty>\d+(?:\.\d+)?)\s*\|\s*"
    r"(?P<rate>\d[\d,]*(?:\.\d+)?)\s*\|\s*(?P<taxable>\d[\d,]*(?:\.\d+)?)\s*$"
)
SPACE_LINE = re.compile(
    r"^(?P<desc>[A-Za-z].+?)\s+(?P<hsn>\d{4,8})\s+(?P<qty>\d+(?:\.\d+)?)\s+"
    r"(?P<rate>\d[\d,]*(?:\.\d{1,2})?)\s+(?P<taxable>\d[\d,]*(?:\.\d{1,2})?)\s*$"
)
AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?")
OCR_MESSAGE = (
    "This PDF has no extractable digital text. OCR is not implemented, "
    "so scanned invoices cannot be read yet."
)


class PdfReadError(Exception):
    pass


def extract_invoice_pdf(data: bytes) -> dict:
    if not data.startswith(b"%PDF-"):
        raise PdfReadError("The file is not a PDF.")
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PdfReadError("The PDF could not be opened.") from exc
    try:
        if document.needs_pass:
            raise PdfReadError("This PDF is password protected and cannot be read.")
        pages = [(page.get_text("text") or "") for page in document]
    finally:
        document.close()

    raw_text = "\n".join(pages).strip("\n")
    if len(re.sub(r"\s+", "", raw_text)) < 20:
        return {"kind": "scanned", "raw_text": raw_text, "message": OCR_MESSAGE}
    parsed = parse_invoice_text(raw_text)
    parsed["kind"] = "digital"
    return parsed


def parse_invoice_text(raw_text: str) -> dict:
    supplier_text, buyer_text = _split_parties(raw_text)
    supplier_name, supplier_gstin, supplier_address = _party(supplier_text)
    buyer_name, buyer_gstin, _buyer_address = _party(buyer_text) if buyer_text else (None, None, None)
    if buyer_gstin and buyer_gstin == supplier_gstin:
        buyer_gstin = None

    fields = {
        "supplier_legal_name": supplier_name,
        "supplier_gstin": supplier_gstin,
        "supplier_address": supplier_address,
        "invoice_number": _find_token(
            raw_text,
            r"\binvoice\s*(?:no\.?|number|#)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9/\-]*)",
        ),
        "invoice_date": _find_date(raw_text, r"\binvoice\s*date\b|\bdated\b"),
        "due_date": _find_date(raw_text, r"\bdue\s*date\b"),
        "buyer_legal_name": buyer_name,
        "buyer_gstin": buyer_gstin,
        "po_number": _find_token(
            raw_text,
            r"\b(?:purchase\s*order(?:\s*(?:no\.?|number|#))?|p\.?\s*o\.?\s*(?:no\.?|number|#)?)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9/\-]*)",
        ),
        "taxable_value": _find_amount(raw_text, r"\btaxable\s+(?:value|amount)\b"),
        "cgst": _find_amount(raw_text, r"\bcgst\b"),
        "sgst": _find_amount(raw_text, r"\bsgst\b"),
        "igst": _find_amount(raw_text, r"\bigst\b"),
        "total_tax": _find_amount(raw_text, r"\btotal\s+tax\b|\bgst\s+amount\b"),
        "invoice_grand_total": _find_total(raw_text),
        "currency": _find_currency(raw_text),
    }
    line_items = _line_items(raw_text)
    return {
        "raw_text": raw_text,
        "fields": fields,
        "field_status": field_status(fields),
        "line_items": line_items,
    }


def field_status(fields: dict) -> dict:
    return {key: "missing" if fields.get(key) is None else "found" for key in HEADER_FIELDS}


def _split_parties(text: str) -> tuple[str, str]:
    parts = BUYER_SPLIT.split(text, maxsplit=1)
    if len(parts) == 1:
        return text, ""
    return parts[0], parts[1]


def _party(text: str) -> tuple[str | None, str | None, str | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    gstin = None
    gstin_at = None
    for index, line in enumerate(lines):
        match = GSTIN_RE.search(line.upper())
        if match:
            gstin = match.group(0)
            gstin_at = index
            break
    before: list[str] = []
    if gstin_at is not None:
        for line in lines[:gstin_at]:
            if SKIP_LINE.match(line) or re.match(r"(?i)^(gstin|address)\b", line):
                continue
            before.append(line)
    address = None
    for index, line in enumerate(lines):
        labeled = re.match(r"(?i)address\s*[:\-]\s*(.*)", line)
        if not labeled:
            continue
        parts = [labeled.group(1).strip()] if labeled.group(1).strip() else []
        for follower in lines[index + 1 :]:
            if GSTIN_RE.search(follower.upper()) or re.match(r"(?i)^(invoice|bill to|gstin)\b", follower):
                break
            parts.append(follower)
        if parts:
            address = ", ".join(parts)
        break
    name = before[0] if before else None
    if address is None and len(before) > 1:
        address = ", ".join(before[1:])
    return name, gstin, address


def _find_token(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip() or None


def _find_date(text: str, label: str) -> str | None:
    for line in text.splitlines():
        match = re.search(label, line, re.IGNORECASE)
        if not match:
            continue
        found = re.search(r"\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}", line[match.end() :])
        if found:
            return _iso_date(found.group(0))
    return None


def _iso_date(value: str) -> str | None:
    match = re.match(r"(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})$", value.strip())
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    if year < 100:
        year += 2000
    if month > 12 and day <= 12:
        day, month = month, day
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _find_amount(text: str, label: str):
    for line in text.splitlines():
        match = re.search(label, line, re.IGNORECASE)
        if not match:
            continue
        rest = re.sub(r"\d+(?:\.\d+)?\s*%", " ", line[match.end() :])
        numbers = AMOUNT_RE.findall(rest)
        if numbers:
            return _number(numbers[-1])
    return None


def _find_total(text: str):
    for label in (r"\bgrand\s+total\b", r"\bamount\s+payable\b", r"\binvoice\s+total\b", r"\bnet\s+payable\b"):
        amount = _find_amount(text, label)
        if amount is not None:
            return amount
    return None


def _find_currency(text: str) -> str | None:
    match = re.search(r"\bcurrency\s*[:\-]?\s*([A-Z]{3})\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    if re.search(r"₹|\bRs\.?\b|\bINR\b", text):
        return "INR"
    return None


def _line_items(text: str) -> list[dict]:
    items = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = PIPE_LINE.match(line) or SPACE_LINE.match(line)
        if not match or match.group("desc").strip().lower() == "description":
            continue
        description = match.group("desc").strip(" |-")
        if not re.search(r"[A-Za-z]", description):
            continue
        items.append(
            {
                "description": description,
                "hsn_sac": match.group("hsn"),
                "quantity": _number(match.group("qty")),
                "unit_price": _number(match.group("rate")),
                "taxable_value": _number(match.group("taxable")),
                "cgst": None,
                "sgst": None,
                "igst": None,
            }
        )
    for item in items:
        for key in LINE_FIELDS:
            item.setdefault(key, None)
    return items


def _number(value: str):
    try:
        amount = Decimal(value.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None
    if amount == amount.to_integral():
        return int(amount)
    return float(amount)
