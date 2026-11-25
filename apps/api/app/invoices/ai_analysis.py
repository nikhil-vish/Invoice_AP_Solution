"""OpenRouter-powered advisory analysis; it never changes approval decisions."""

import json
from datetime import datetime, timezone
import httpx

from app.config import settings
from app.invoices.ai_extract import AIExtractionError
from app.invoices.models import InvoiceAnalysis


async def analyse_invoice(invoice: dict, items: list[dict], validation_results: list[dict]) -> InvoiceAnalysis:
    if not settings.ai_extraction_enabled or not settings.openrouter_api_key or not settings.openrouter_model:
        raise AIExtractionError("OpenRouter analysis is not configured or enabled.")
    evidence = {"invoice": invoice, "line_items": items, "deterministic_validation_results": validation_results}
    prompt = """You are an invoice-review assistant. Analyse only the supplied evidence. Never invent facts. Clearly distinguish deterministic failures, suspicions, and unknown information. Your recommendation is advisory only and cannot approve or reject an invoice. Return JSON only with recommendation (APPROVE|REJECT|REQUEST_CLARIFICATION), risk_level (LOW|MEDIUM|HIGH), confidence_score (0-100 model confidence, not correctness probability), executive_summary, findings (category, severity, description, evidence object, suggested_action), validation_results, generated_at (ISO datetime), and model_used. Preserve deterministic results verbatim in validation_results."""
    payload = {"model": settings.openrouter_model, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": json.dumps(evidence, default=str)}], "temperature": 0.1, "response_format": {"type": "json_object"}}
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}", "Content-Type": "application/json", "HTTP-Referer": settings.openrouter_http_referer, "X-Title": settings.openrouter_app_title}
    try:
        async with httpx.AsyncClient(timeout=settings.ai_extraction_timeout_seconds) as client:
            response = await client.post(f"{settings.openrouter_base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
        content = (response.json().get("choices") or [{}])[0].get("message", {}).get("content")
        if not content:
            raise AIExtractionError("OpenRouter returned empty analysis content.")
        data = json.loads(content)
        data["validation_results"] = validation_results
        data["generated_at"] = data.get("generated_at") or datetime.now(timezone.utc).isoformat()
        # Provider configuration is authoritative; the model must not self-report
        # a different value in its JSON.
        data["model_used"] = settings.openrouter_model
        return InvoiceAnalysis.model_validate(data)
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        raise AIExtractionError(f"OpenRouter analysis failed: {exc}") from exc
