"""Pydantic models for structured invoice extraction."""

from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator
from decimal import Decimal


class ExtractionField(BaseModel):
    """Base model for an extracted field with metadata."""
    value: Optional[str] = None
    normalized_value: Optional[str] = None
    status: Literal["FOUND", "MISSING", "LOW_CONFIDENCE", "CONFLICT"] = "MISSING"
    confidence: Optional[float] = Field(None, ge=0, le=1)
    source_text: Optional[str] = None
    page: Optional[int] = None


class SupplierFields(BaseModel):
    legal_name: ExtractionField = Field(default_factory=ExtractionField)
    gstin: ExtractionField = Field(default_factory=ExtractionField)
    address: ExtractionField = Field(default_factory=ExtractionField)


class BuyerFields(BaseModel):
    legal_name: ExtractionField = Field(default_factory=ExtractionField)
    gstin: ExtractionField = Field(default_factory=ExtractionField)
    address: ExtractionField = Field(default_factory=ExtractionField)


class CommercialFields(BaseModel):
    po_number: ExtractionField = Field(default_factory=ExtractionField)
    currency: ExtractionField = Field(default_factory=ExtractionField)


class AmountFields(BaseModel):
    taxable_value: ExtractionField = Field(default_factory=ExtractionField)
    discount: ExtractionField = Field(default_factory=ExtractionField)
    freight: ExtractionField = Field(default_factory=ExtractionField)
    cgst: ExtractionField = Field(default_factory=ExtractionField)
    sgst: ExtractionField = Field(default_factory=ExtractionField)
    igst: ExtractionField = Field(default_factory=ExtractionField)
    cess: ExtractionField = Field(default_factory=ExtractionField)
    total_tax: ExtractionField = Field(default_factory=ExtractionField)
    round_off: ExtractionField = Field(default_factory=ExtractionField)
    grand_total: ExtractionField = Field(default_factory=ExtractionField)
    amount_due: ExtractionField = Field(default_factory=ExtractionField)


class LineItem(BaseModel):
    description: ExtractionField = Field(default_factory=ExtractionField)
    hsn_sac: ExtractionField = Field(default_factory=ExtractionField)
    quantity: ExtractionField = Field(default_factory=ExtractionField)
    unit: ExtractionField = Field(default_factory=ExtractionField)
    unit_price: ExtractionField = Field(default_factory=ExtractionField)
    discount: ExtractionField = Field(default_factory=ExtractionField)
    taxable_value: ExtractionField = Field(default_factory=ExtractionField)
    tax_rate: ExtractionField = Field(default_factory=ExtractionField)
    tax_amount: ExtractionField = Field(default_factory=ExtractionField)
    line_total: ExtractionField = Field(default_factory=ExtractionField)
    page: Optional[int] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, v):
        if v is not None:
            return max(0.0, min(1.0, float(v)))
        return v


class PaymentFields(BaseModel):
    due_date: ExtractionField = Field(default_factory=ExtractionField)
    payment_terms: ExtractionField = Field(default_factory=ExtractionField)
    bank_details_detected: bool = False


class ComplianceFields(BaseModel):
    irn: ExtractionField = Field(default_factory=ExtractionField)
    acknowledgement_number: ExtractionField = Field(default_factory=ExtractionField)
    qr_data_detected: bool = False
    reverse_charge: ExtractionField = Field(default_factory=ExtractionField)


class ExtractionMetadata(BaseModel):
    provider: str
    model: str
    prompt_version: str


class InvoiceExtraction(BaseModel):
    """Complete structured invoice extraction result."""
    document_type: Optional[str] = None
    invoice_number: ExtractionField = Field(default_factory=ExtractionField)
    invoice_date: ExtractionField = Field(default_factory=ExtractionField)
    supplier: SupplierFields = Field(default_factory=SupplierFields)
    buyer: BuyerFields = Field(default_factory=BuyerFields)
    commercial: CommercialFields = Field(default_factory=CommercialFields)
    amounts: AmountFields = Field(default_factory=AmountFields)
    line_items: List[LineItem] = Field(default_factory=list)
    payment: PaymentFields = Field(default_factory=PaymentFields)
    compliance: ComplianceFields = Field(default_factory=ComplianceFields)
    extraction_metadata: Optional[ExtractionMetadata] = None


class ExtractionResult(BaseModel):
    """Wrapper for extraction result with processing info."""
    kind: Literal["digital", "scanned", "ai_enhanced"]
    raw_text: str
    extraction: Optional[InvoiceExtraction] = None
    field_status: dict = Field(default_factory=dict)
    line_items: List[dict] = Field(default_factory=list)
    message: Optional[str] = None