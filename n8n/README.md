# n8n workflows (later milestone)

Create separate workflows rather than one monolithic automation:
1. Gmail invoice intake → attachment download → call backend ingestion API.
2. Supplier clarification response watcher → attach response to invoice case.
3. Approval notification → send approver a link to the authenticated application.
4. Escalation scheduler → find overdue open exceptions and notify owners.

n8n should not calculate PO balances, GST/TDS, or make approval decisions. Those rules live in FastAPI.
