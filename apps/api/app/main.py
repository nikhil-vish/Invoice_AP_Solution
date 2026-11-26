from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.invoices.router import router as invoices_router

app = FastAPI(
    title="Invoice Intelligence API",
    version="0.1.0",
    description="Invoice-to-approval workflow API. Processing endpoints will be added incrementally.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

app.include_router(invoices_router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "invoice-intelligence-api", "version": "0.1.0"}


@app.get("/api/v1", tags=["system"])
def api_info():
    return {
        "message": "Invoice Intelligence API",
        "implemented": [
            "health",
            "POST /api/v1/invoices/upload",
            "GET /api/v1/invoices",
            "GET /api/v1/invoices/{id}",
            "POST /api/v1/invoices/{id}/process",
            "GET /api/v1/invoices/runs",
            "GET /api/v1/invoices/runs/{id}",
            "GET /api/v1/invoices/suppliers",
            "GET /api/v1/invoices/approvals",
            "POST /api/v1/invoices/approvals/{id}/action",
            "GET /api/v1/invoices/exceptions",
            "POST /api/v1/invoices/exceptions/{id}/assign",
            "POST /api/v1/invoices/exceptions/{id}/resolve",
            "GET /api/v1/invoices/dashboard/metrics",
            "POST /api/v1/invoices/copilot",
        ],
        "next": [],
    }
