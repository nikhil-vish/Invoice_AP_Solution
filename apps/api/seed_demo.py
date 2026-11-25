#!/usr/bin/env python
"""Seed demo data into Supabase for Invoice Intelligence Workbench.

Run after configuring .env with SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.
"""

import os
import sys
import uuid
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from supabase import create_client

# Load .env from apps/api directory
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    sys.exit(1)

client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Fixed IDs matching backend DEFAULT_CLIENT_ID
CLIENT_ID = "00000000-0000-0000-0000-000000000001"
ENTITY_ID = "11111111-1111-1111-1111-111111111111"
SUPPLIER_ID = "22222222-2222-2222-2222-222222222222"

def seed():
    print("Seeding demo data...")

    # 1. Client
    print("  Creating client...")
    client.table("clients").upsert({
        "id": CLIENT_ID,
        "legal_name": "Demo Corp Pvt Ltd",
        "display_name": "Demo Corp",
        "status": "ACTIVE",
    }, on_conflict="id").execute()

    # 2. Client Entity
    print("  Creating client entity...")
    client.table("client_entities").upsert({
        "id": ENTITY_ID,
        "client_id": CLIENT_ID,
        "legal_name": "Demo Corp - Mumbai Unit",
        "gstin": "27ABCDE1234F1Z5",
        "registered_email_domains": ["democorp.com"],
        "is_active": True,
    }, on_conflict="id").execute()

    # 3. Supplier
    print("  Creating supplier...")
    client.table("suppliers").upsert({
        "id": SUPPLIER_ID,
        "client_id": CLIENT_ID,
        "legal_name": "Acme Supplies Pvt Ltd",
        "trade_name": "Acme Supplies",
        "gstin": "27AAAAA0000A1Z5",
        "vendor_code": "VEND-001",
        "status": "ACTIVE",
        "aliases": ["Acme", "Acme Supplies"],
    }, on_conflict="id").execute()

    # 4. Sample Invoices
    print("  Creating sample invoices...")
    invoices_data = [
        {
            "id": "33333333-3333-3333-3333-333333333331",
            "client_id": CLIENT_ID,
            "client_entity_id": ENTITY_ID,
            "supplier_id": SUPPLIER_ID,
            "invoice_number": "INV-2024-001",
            "invoice_date": "2024-01-15",
            "currency": "INR",
            "procurement_type": "PO",
            "taxable_value": 10000.00,
            "cgst_amount": 900.00,
            "sgst_amount": 900.00,
            "igst_amount": 0.00,
            "total_amount": 11800.00,
            "processing_status": "APPROVED",
            "approval_status": "APPROVED",
        },
        {
            "id": "33333333-3333-3333-3333-333333333332",
            "client_id": CLIENT_ID,
            "client_entity_id": ENTITY_ID,
            "supplier_id": SUPPLIER_ID,
            "invoice_number": "INV-2024-002",
            "invoice_date": "2024-01-20",
            "currency": "INR",
            "procurement_type": "NON_PO",
            "taxable_value": 25000.00,
            "cgst_amount": 2250.00,
            "sgst_amount": 2250.00,
            "igst_amount": 0.00,
            "total_amount": 29500.00,
            "processing_status": "APPROVAL_PENDING",
            "approval_status": "PENDING",
        },
        {
            "id": "33333333-3333-3333-3333-333333333333",
            "client_id": CLIENT_ID,
            "client_entity_id": ENTITY_ID,
            "supplier_id": SUPPLIER_ID,
            "invoice_number": "INV-2024-003",
            "invoice_date": "2024-02-01",
            "currency": "INR",
            "procurement_type": "PO",
            "taxable_value": 5000.00,
            "cgst_amount": 450.00,
            "sgst_amount": 450.00,
            "igst_amount": 0.00,
            "total_amount": 5900.00,
            "processing_status": "DECISION_READY",
            "approval_status": "PENDING",
        },
        {
            "id": "33333333-3333-3333-3333-333333333334",
            "client_id": CLIENT_ID,
            "client_entity_id": ENTITY_ID,
            "supplier_id": SUPPLIER_ID,
            "invoice_number": "INV-2024-004",
            "invoice_date": "2024-02-10",
            "currency": "INR",
            "procurement_type": "NON_PO",
            "taxable_value": 75000.00,
            "cgst_amount": 6750.00,
            "sgst_amount": 6750.00,
            "igst_amount": 0.00,
            "total_amount": 88500.00,
            "processing_status": "VALIDATING",
            "approval_status": "PENDING",
        },
        {
            "id": "33333333-3333-3333-3333-333333333335",
            "client_id": CLIENT_ID,
            "client_entity_id": ENTITY_ID,
            "supplier_id": SUPPLIER_ID,
            "invoice_number": "INV-2024-005",
            "invoice_date": "2024-02-15",
            "currency": "INR",
            "procurement_type": "PO",
            "taxable_value": 12000.00,
            "cgst_amount": 1080.00,
            "sgst_amount": 1080.00,
            "igst_amount": 0.00,
            "total_amount": 14160.00,
            "processing_status": "RECEIVED",
            "approval_status": "PENDING",
        },
    ]

    for inv in invoices_data:
        client.table("invoices").upsert(inv, on_conflict="id").execute()

        # Add line items for each invoice
        inv_id = inv["id"]
        line_items = [
            {
                "invoice_id": inv_id,
                "line_number": 1,
                "description": "Professional Services - Consulting",
                "item_code": "CONSULT-001",
                "hsn_sac": "998314",
                "quantity": 1,
                "unit_of_measure": "DAY",
                "unit_price": inv["taxable_value"],
                "taxable_value": inv["taxable_value"],
                "gst_rate": 18.0,
                "cgst_amount": inv["cgst_amount"],
                "sgst_amount": inv["sgst_amount"],
                "igst_amount": inv["igst_amount"],
                "total_amount": inv["total_amount"],
            }
        ]
        client.table("invoice_items").upsert(line_items, on_conflict="invoice_id,line_number").execute()

        # Add processing run for each invoice
        run_id = f"44444444-4444-4444-4444-{inv_id[-12:]}"
        client.table("processing_runs").upsert({
            "id": run_id,
            "invoice_id": inv_id,
            "run_number": 1,
            "status": "COMPLETED",
            "started_at": "2024-01-15T10:00:00Z",
            "completed_at": "2024-01-15T10:00:30Z",
            "triggered_by": "MANUAL_UPLOAD",
            "summary": {"stages_completed": 6, "validation_passed": True},
        }, on_conflict="id").execute()

        # Add validation results
        validation_stages = [
            {"stage": "EXTRACTION", "rule_code": "TEXT_EXTRACTED", "status": "PASSED", "message": "Digital text extracted successfully"},
            {"stage": "VALIDATION", "rule_code": "GSTIN_FORMAT", "status": "PASSED", "message": "Supplier GSTIN format valid"},
            {"stage": "VALIDATION", "rule_code": "INVOICE_NUMBER", "status": "PASSED", "message": "Invoice number extracted"},
            {"stage": "MATCHING", "rule_code": "PO_MATCH", "status": "PASSED", "message": "Matched to PO" if inv["procurement_type"] == "PO" else "No PO - non-PO invoice"},
            {"stage": "TAX_CHECK", "rule_code": "GST_CALCULATION", "status": "PASSED", "message": "Tax amounts match calculated values"},
            {"stage": "DECISION", "rule_code": "AUTO_APPROVE", "status": "PASSED" if inv["total_amount"] < 50000 else "NEEDS_REVIEW", "message": "Within auto-approval threshold" if inv["total_amount"] < 50000 else "Requires manual approval"},
        ]
        for vr in validation_stages:
            client.table("validation_results").upsert({
                "processing_run_id": run_id,
                **vr,
                "evidence": {},
            }, on_conflict="processing_run_id,rule_code").execute()

    print("Done! Demo data seeded successfully.")
    print(f"\nClient ID: {CLIENT_ID}")
    print(f"Entity ID: {ENTITY_ID}")
    print(f"Supplier ID: {SUPPLIER_ID}")
    print("\nInvoices created:")
    for inv in invoices_data:
        print(f"  - {inv['invoice_number']} | {inv['processing_status']} | ₹{inv['total_amount']:,.2f}")

if __name__ == "__main__":
    seed()