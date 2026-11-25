"""Invoice PDF extraction pipeline: PyMuPDF -> AI (optional) -> structured output."""

import asyncio
import concurrent.futures
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Any, List

import fitz

from app.config import settings
from app.invoices.fields import HEADER_FIELDS, LINE_FIELDS
from app.invoices.models import InvoiceExtraction, ExtractionResult, LineItem
from app.invoices.ai_extract import extract_with_ai, AIExtractionError
logger = logging.getLogger(__name__)


def _run_ai_extraction(raw_text: str) -> Optional[ExtractionResult]:
    """Run the async AI extraction coroutine safely in sync or async contexts.

    If an event loop is already running (e.g., inside a FastAPI request),
    ``asyncio.run()`` cannot be used directly. In that case, the coroutine is
    executed in a separate worker thread with its own event loop.
    """
    try:
        running_loop = asyncio.get_running_loop()
    except RuntimeError:
        running_loop = None

    if running_loop is not None and running_loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, extract_with_ai(raw_text))
            return future.result()
    return asyncio.run(extract_with_ai(raw_text))


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


def extract_invoice_pdf(data: bytes) -> Dict[str, Any]:
    """
    Main extraction pipeline:
    1. Validate PDF
    2. Extract digital text with PyMuPDF
    3. Detect scanned pages
    4. Try AI extraction if enabled (with fallback to regex)
    5. Return structured result
    """
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
        page_count = len(pages)
    finally:
        document.close()

    raw_text = "\n".join(pages).strip("\n")

    # Check if PDF has extractable text
    if len(re.sub(r"\s+", "", raw_text)) < 20:
        return {
            "kind": "scanned",
            "raw_text": raw_text,
            "message": OCR_MESSAGE,
            "fields": {},
            "field_status": {key: "missing" for key in HEADER_FIELDS},
            "line_items": [],
        }

    # Parse with regex-based extractor (baseline)
    regex_result = parse_invoice_text(raw_text)

    # Try AI extraction if enabled
    ai_result = None
    if settings.ai_extraction_enabled:
        try:
            ai_result = _run_ai_extraction(raw_text)
        except Exception as e:
            logger.warning(f"AI extraction failed: {e}")

    # Merge results: prefer AI for structured fields, fallback to regex
    merged = merge_extractions(regex_result, ai_result, raw_text)
    merged["kind"] = "ai_enhanced" if ai_result and ai_result.extraction else "digital"

    return merged


def merge_extractions(
    regex_result: Dict[str, Any],
    ai_result: Optional[ExtractionResult],
    raw_text: str
) -> Dict[str, Any]:
    """
    Merge regex and AI extraction results.
    AI takes precedence for structured fields; regex is fallback.
    """
    if not ai_result or not ai_result.extraction:
        # No AI result, return regex with proper structure
        return {
            "raw_text": raw_text,
            "fields": regex_result.get("fields", {}),
            "field_status": regex_result.get("field_status", {}),
            "line_items": regex_result.get("line_items", []),
            "message": None,
        }

    ai_extraction = ai_result.extraction

    # Convert AI extraction to flat fields dict for compatibility
    ai_fields = _ai_to_flat_fields(ai_extraction)
    ai_line_items = _ai_to_line_items(ai_extraction)

    # Merge: use AI where available (FOUND), fallback to regex
    merged_fields = {}
    merged_field_status = {}

    for key in HEADER_FIELDS:
        ai_field = _get_ai_field(ai_extraction, key)
        regex_value = regex_result.get("fields", {}).get(key)

        if ai_field:
            merged_fields[key] = ai_field
            merged_field_status[key] = "found"
        elif regex_value is not None:
            merged_fields[key] = regex_value
            merged_field_status[key] = "found"
        else:
            merged_fields[key] = None
            merged_field_status[key] = "missing"

    # Merge line items
    merged_line_items = ai_line_items if ai_line_items else regex_result.get("line_items", [])

    return {
        "raw_text": raw_text,
        "fields": merged_fields,
        "field_status": merged_field_status,
        "line_items": merged_line_items,
        "message": None,
    }


def _ai_to_flat_fields(extraction: InvoiceExtraction) -> Dict[str, Optional[str]]:
    """Convert AI extraction to flat fields dict."""
    return {
        "supplier_legal_name": extraction.supplier_name,
        "supplier_gstin": extraction.supplier_gstin,
        "supplier_address": None,
        "invoice_number": extraction.invoice_number,
        "invoice_date": extraction.invoice_date,
        "due_date": extraction.due_date,
        "buyer_legal_name": extraction.buyer_name,
        "buyer_gstin": extraction.buyer_gstin,
        "po_number": extraction.po_number,
        "taxable_value": str(extraction.taxable_value) if extraction.taxable_value is not None else None,
        "cgst": str(extraction.cgst) if extraction.cgst is not None else None,
        "sgst": str(extraction.sgst) if extraction.sgst is not None else None,
        "igst": str(extraction.igst) if extraction.igst is not None else None,
        "total_tax": str(extraction.total_tax) if extraction.total_tax is not None else None,
        "invoice_grand_total": str(extraction.grand_total) if extraction.grand_total is not None else None,
        "currency": extraction.currency,
    }


def _get_ai_field(extraction: InvoiceExtraction, key: str) -> Optional[str]:
    """Get an AI field value by flat key."""
    field_map = {
        "supplier_legal_name": extraction.supplier_name,
        "supplier_gstin": extraction.supplier_gstin,
        "supplier_address": None,
        "invoice_number": extraction.invoice_number,
        "invoice_date": extraction.invoice_date,
        "due_date": extraction.due_date,
        "buyer_legal_name": extraction.buyer_name,
        "buyer_gstin": extraction.buyer_gstin,
        "po_number": extraction.po_number,
        "taxable_value": str(extraction.taxable_value) if extraction.taxable_value is not None else None,
        "cgst": str(extraction.cgst) if extraction.cgst is not None else None,
        "sgst": str(extraction.sgst) if extraction.sgst is not None else None,
        "igst": str(extraction.igst) if extraction.igst is not None else None,
        "total_tax": str(extraction.total_tax) if extraction.total_tax is not None else None,
        "invoice_grand_total": str(extraction.grand_total) if extraction.grand_total is not None else None,
        "currency": extraction.currency,
    }
    return field_map.get(key)


def _ai_to_line_items(extraction: InvoiceExtraction) -> List[Dict[str, Any]]:
    """Convert AI line items to legacy format."""
    items = []
    for item in extraction.line_items:
        items.append({
            "description": item.description,
            "hsn_sac": item.hsn_sac,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "taxable_value": item.taxable_value,
            "cgst": None,
            "sgst": None,
            "igst": None,
        })
    for item in items:
        for key in LINE_FIELDS:
            item.setdefault(key, None)
    return items


def _parse_number(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse_invoice_text(raw_text: str) -> Dict[str, Any]:
    """Regex-based invoice text parsing (baseline extractor)."""
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


def field_status(fields: Dict[str, Any]) -> Dict[str, str]:
    return {key: "missing" if fields.get(key) is None else "found" for key in HEADER_FIELDS}


def _split_parties(text: str) -> tuple[str, str]:
    parts = BUYER_SPLIT.split(text, maxsplit=1)
    if len(parts) == 1:
        return text, ""
    return parts[0], parts[1]


def _party(text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
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
        for follower in lines[index + 1:]:
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


def _find_token(text: str, pattern: str) -> Optional[str]:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip() or None


def _find_date(text: str, label: str) -> Optional[str]:
    for line in text.splitlines():
        match = re.search(label, line, re.IGNORECASE)
        if not match:
            continue
        found = re.search(r"\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}", line[match.end():])
        if found:
            return _iso_date(found.group(0))
    return None


def _iso_date(value: str) -> Optional[str]:
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


def _find_amount(text: str, label: str) -> Optional[float]:
    for line in text.splitlines():
        match = re.search(label, line, re.IGNORECASE)
        if not match:
            continue
        rest = re.sub(r"\d+(?:\.\d+)?\s*%", " ", line[match.end():])
        numbers = AMOUNT_RE.findall(rest)
        if numbers:
            return _number(numbers[-1])
    return None


def _find_total(text: str) -> Optional[float]:
    for label in (r"\bgrand\s+total\b", r"\bamount\s+payable\b", r"\binvoice\s+total\b", r"\bnet\s+payable\b"):
        amount = _find_amount(text, label)
        if amount is not None:
            return amount
    return None


def _find_currency(text: str) -> Optional[str]:
    match = re.search(r"\bcurrency\s*[:\-]?\s*([A-Z]{3})\b", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    if re.search(r"₹|\bRs\.?\b|\bINR\b", text):
        return "INR"
    return None


def _line_items(text: str) -> List[Dict[str, Any]]:
    items = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = PIPE_LINE.match(line) or SPACE_LINE.match(line)
        if not match or match.group("desc").strip().lower() == "description":
            continue
        description = match.group("desc").strip(" |-")
        if not re.search(r"[A-Za-z]", description):
            continue
        items.append({
            "description": description,
            "hsn_sac": match.group("hsn"),
            "quantity": _number(match.group("qty")),
            "unit_price": _number(match.group("rate")),
            "taxable_value": _number(match.group("taxable")),
            "cgst": None,
            "sgst": None,
            "igst": None,
        })
    for item in items:
        for key in LINE_FIELDS:
            item.setdefault(key, None)
    return items


def _number(value: str) -> Optional[float]:
    try:
        amount = Decimal(value.replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None
    if amount == amount.to_integral():
        return int(amount)
    return float(amount)