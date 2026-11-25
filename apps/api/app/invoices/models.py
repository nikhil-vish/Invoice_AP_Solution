"""Pydantic models for structured invoice extraction."""

from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator
from decimal import Decimal


class LineItem(BaseModel):
    """A single line item from the invoice."""
    description: Optional[str] = None
    hsn_sac: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    taxable_value: Optional[float] = None


class InvoiceExtraction(BaseModel):
    """Complete structured invoice extraction result (simplified flat schema)."""
    supplier_name: Optional[str] = None
    supplier_gstin: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_gstin: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    po_number: Optional[str] = None
    currency: Optional[str] = None
    taxable_value: Optional[float] = None
    cgst: Optional[float] = None
    sgst: Optional[float] = None
    igst: Optional[float] = None
    total_tax: Optional[float] = None
    grand_total: Optional[float] = None
    line_items: List[LineItem] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    """Wrapper for extraction result with processing info."""
    kind: Literal["digital", "scanned", "ai_enhanced"]
    raw_text: str
    extraction: Optional[InvoiceExtraction] = None
    field_status: dict = Field(default_factory=dict)
    line_items: List[dict] = Field(default_factory=list)
    message: Optional[str] = None
    reasoning_details: Optional[dict] = None
