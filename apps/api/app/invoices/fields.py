HEADER_FIELDS = (
    "supplier_legal_name",
    "supplier_gstin",
    "supplier_address",
    "invoice_number",
    "invoice_date",
    "due_date",
    "buyer_legal_name",
    "buyer_gstin",
    "po_number",
    "taxable_value",
    "cgst",
    "sgst",
    "igst",
    "total_tax",
    "invoice_grand_total",
    "currency",
)

LINE_FIELDS = (
    "description",
    "hsn_sac",
    "quantity",
    "unit_price",
    "taxable_value",
    "cgst",
    "sgst",
    "igst",
)

DATE_FIELDS = {"invoice_date", "due_date"}
TEXT_FIELDS = {
    "supplier_legal_name",
    "supplier_gstin",
    "supplier_address",
    "invoice_number",
    "buyer_legal_name",
    "buyer_gstin",
    "po_number",
    "currency",
}
MONEY_FIELDS = {
    "taxable_value",
    "cgst",
    "sgst",
    "igst",
    "total_tax",
    "invoice_grand_total",
}

PERSISTENCE_SETTINGS = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_STORAGE_BUCKET",
    "DEFAULT_CLIENT_ID",
    "DEFAULT_CLIENT_ENTITY_ID",
)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
