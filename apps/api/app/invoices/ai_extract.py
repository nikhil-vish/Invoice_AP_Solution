"""OpenRouter AI extraction adapter with fallback handling."""

import json
import logging
from typing import Optional, List, Dict, Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings
from app.invoices.models import InvoiceExtraction, ExtractionResult

logger = logging.getLogger(__name__)


class AIExtractionError(Exception):
    """Raised when AI extraction fails."""
    pass


class OpenRouterAdapter:
    """Adapter for OpenRouter chat completions API.

    Supports OpenRouter reasoning (e.g., particle-1) by sending
    `"reasoning": {"enabled": True}` and preserving `reasoning_details`
    across conversation turns so the model can continue reasoning from
    where it left off.
    """

    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.base_url = settings.openrouter_base_url.rstrip("/")
        self.model = settings.openrouter_model
        self.timeout = settings.ai_extraction_timeout_seconds
        self.max_retries = settings.ai_extraction_max_retries
        self.reasoning_enabled = settings.ai_reasoning_enabled

        # Conversation state for multi-turn reasoning continuation.
        # Each entry is a message dict that may include "reasoning_details".
        self._messages: List[Dict[str, Any]] = []

    def is_configured(self) -> bool:
        """Check if the adapter is properly configured."""
        return bool(self.api_key and self.model)

    def _build_prompt(self, raw_text: str) -> str:
        """Build a concise extraction prompt requesting only essential structured JSON."""
        return f"""You are an expert invoice extraction system. Extract structured data from the following Indian GST invoice text and return ONLY a valid JSON object.

RULES:
- Return ONLY the JSON object. No explanations, no markdown, no reasoning, no extra text.
- Missing fields must be null. Never invent values.
- Normalize dates to YYYY-MM-DD.
- Normalize amounts to plain numbers (no currency symbols or commas).
- Distinguish supplier GSTIN from buyer GSTIN.

Invoice text:
{raw_text}

Required JSON:
{{
  "supplier_name": "string|null",
  "supplier_gstin": "string|null",
  "buyer_name": "string|null",
  "buyer_gstin": "string|null",
  "invoice_number": "string|null",
  "invoice_date": "string|null",
  "due_date": "string|null",
  "po_number": "string|null",
  "currency": "string|null",
  "taxable_value": "number|null",
  "cgst": "number|null",
  "sgst": "number|null",
  "igst": "number|null",
  "total_tax": "number|null",
  "grand_total": "number|null",
  "line_items": [
    {{
      "description": "string|null",
      "hsn_sac": "string|null",
      "quantity": "number|null",
      "unit_price": "number|null",
      "taxable_value": "number|null"
    }}
  ]
}}"""

    def _build_messages(self, raw_text: str, include_reasoning_details: bool = True) -> List[Dict[str, Any]]:
        """Build the messages array for the API call.

        When reasoning is enabled and we have prior conversation state,
        prepend the stored messages (including assistant messages with
        reasoning_details) so the model can continue reasoning from where
        it left off.
        """
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": "You are an expert invoice extraction system. Return only valid JSON matching the requested schema."
            },
        ]

        # Preserve prior assistant messages with reasoning_details for reasoning continuation.
        if include_reasoning_details and self.reasoning_enabled:
            for msg in self._messages:
                messages.append(msg)

        messages.append({
            "role": "user",
            "content": self._build_prompt(raw_text)
        })

        return messages

    def _build_payload(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build the request payload, including reasoning when enabled.

        Nemotron-3.5-super-vl:free supports response_format JSON mode.
        """
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4000,
            "response_format": {"type": "json_object"},
        }

        if self.reasoning_enabled:
            payload["reasoning"] = {"enabled": True}

        return payload

    def _extract_message_and_reasoning(self, data: Dict[str, Any]) -> dict:
        """Extract content, reasoning_details, and response metadata from the assistant message.

        Returns a dict with:
          - content: the message content string (may be empty or null)
          - reasoning_details: the reasoning object from the message, if present
          - finish_reason: the choice finish_reason (e.g., "stop", "length")
          - native_finish_reason: OpenRouter's native finish reason, if present
          - model: the model actually used, if present
          - usage: token usage info, if present
          - provider_error: any provider-level error info, if present
        """
        choices = data.get("choices", [])
        choice = choices[0] if choices else {}
        message = choice.get("message", {})
        content = message.get("content")
        if content is None:
            content = ""
        reasoning_details = message.get("reasoning_details")

        return {
            "content": content,
            "reasoning_details": reasoning_details,
            "finish_reason": choice.get("finish_reason"),
            "native_finish_reason": choice.get("native_finish_reason"),
            "model": data.get("model"),
            "usage": data.get("usage"),
            "provider_error": data.get("provider_error") or data.get("error"),
        }

    def _store_assistant_message(self, content: str, reasoning_details: Optional[Dict[str, Any]]) -> None:
        """Store the assistant message (with reasoning_details) for future reasoning continuation."""
        msg: Dict[str, Any] = {"role": "assistant", "content": content}
        if reasoning_details is not None:
            msg["reasoning_details"] = reasoning_details
        self._messages.append(msg)

    @retry(
        stop=stop_after_attempt(settings.ai_extraction_max_retries + 1),
        wait=wait_exponential(multiplier=2, min=4, max=60),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError)),
        reraise=True
    )
    async def extract(self, raw_text: str) -> InvoiceExtraction:
        """Extract structured invoice data using OpenRouter.

        When reasoning is enabled, sends `"reasoning": {"enabled": True}`
        and preserves `reasoning_details` across turns.
        """
        if not self.is_configured():
            raise AIExtractionError("OpenRouter not configured: missing API key or model")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.openrouter_http_referer,
            "X-Title": settings.openrouter_app_title,
        }

        messages = self._build_messages(raw_text)
        payload = self._build_payload(messages)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise AIExtractionError(
                f"OpenRouter API error (HTTP {exc.response.status_code}): {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise AIExtractionError(f"OpenRouter request timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise AIExtractionError(f"OpenRouter connection error: {exc}") from exc

        response_info = self._extract_message_and_reasoning(data)

        # Diagnostic logging - safe fields only, never API key or invoice text
        logger.info(
            "OpenRouter response: model=%s finish_reason=%s native_finish_reason=%s "
            "content_len=%d has_reasoning=%s usage=%s provider_error=%s",
            response_info.get("model"),
            response_info.get("finish_reason"),
            response_info.get("native_finish_reason"),
            len(response_info.get("content", "")),
            response_info.get("reasoning_details") is not None,
            response_info.get("usage"),
            response_info.get("provider_error"),
        )

        # Detect incomplete responses (non-stop finish reasons)
        finish_reason = response_info.get("finish_reason")
        if finish_reason and finish_reason != "stop":
            raise AIExtractionError(
                f"OpenRouter response incomplete (finish_reason={finish_reason})"
            )

        content_text = response_info.get("content", "")
        if not content_text:
            raise AIExtractionError(
                "Empty response from OpenRouter: message.content is null or empty"
            )

        # Store assistant message with reasoning_details for reasoning continuation.
        reasoning_details = response_info.get("reasoning_details")
        if self.reasoning_enabled and reasoning_details is not None:
            self._store_assistant_message(content_text, reasoning_details)

        try:
            parsed = json.loads(content_text)
        except json.JSONDecodeError as e:
            raise AIExtractionError(f"Invalid JSON from OpenRouter: {e}")

        # Validate against our schema
        try:
            extraction = InvoiceExtraction(**parsed)
        except Exception as e:
            raise AIExtractionError(f"Schema validation failed: {e}")

        return extraction

    async def refine(self, follow_up_prompt: str) -> InvoiceExtraction:
        """Run a second reasoning turn that continues from the previous assistant message.

        Preserves the assistant message (with reasoning_details) from the
        prior `extract()` call and appends a follow-up user message so the
        model can continue reasoning from where it left off.
        """
        if not self.is_configured():
            raise AIExtractionError("OpenRouter not configured: missing API key or model")
        if not self.reasoning_enabled:
            raise AIExtractionError("Reasoning is not enabled. Set AI_REASONING_ENABLED=true.")
        if not self._messages:
            raise AIExtractionError("No prior extraction to refine from. Call extract() first.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.openrouter_http_referer,
            "X-Title": settings.openrouter_app_title,
        }

        messages = list(self._messages)
        messages.append({
            "role": "user",
            "content": follow_up_prompt
        })

        payload = self._build_payload(messages)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise AIExtractionError(
                f"OpenRouter API error (HTTP {exc.response.status_code}): {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise AIExtractionError(f"OpenRouter request timed out: {exc}") from exc
        except httpx.ConnectError as exc:
            raise AIExtractionError(f"OpenRouter connection error: {exc}") from exc

        response_info = self._extract_message_and_reasoning(data)
        content_text = response_info.get("content", "")
        if not content_text:
            raise AIExtractionError("Empty response from OpenRouter")

        reasoning_details = response_info.get("reasoning_details")
        if self.reasoning_enabled and reasoning_details is not None:
            self._store_assistant_message(content_text, reasoning_details)

        try:
            parsed = json.loads(content_text)
        except json.JSONDecodeError as e:
            raise AIExtractionError(f"Invalid JSON from OpenRouter: {e}")

        try:
            extraction = InvoiceExtraction(**parsed)
        except Exception as e:
            raise AIExtractionError(f"Schema validation failed: {e}")

        return extraction

    def reset_conversation(self) -> None:
        """Clear the stored conversation state."""
        self._messages = []

    def get_reasoning_details(self) -> Optional[Dict[str, Any]]:
        """Return the reasoning_details from the most recent assistant message, if any."""
        if not self._messages:
            return None
        last = self._messages[-1]
        return last.get("reasoning_details")


async def extract_with_ai(raw_text: str) -> Optional[ExtractionResult]:
    """
    Attempt AI extraction with graceful fallback.
    Returns None if AI is not configured or fails after retries.
    """
    if not settings.ai_extraction_enabled:
        return None

    adapter = OpenRouterAdapter()
    if not adapter.is_configured():
        logger.warning("AI extraction enabled but OpenRouter not configured")
        return None

    try:
        extraction = await adapter.extract(raw_text)
        reasoning_details = None
        if adapter.reasoning_enabled:
            rd = adapter.get_reasoning_details()
            if isinstance(rd, dict):
                reasoning_details = rd
        return ExtractionResult(
            kind="ai_enhanced",
            raw_text=raw_text,
            extraction=extraction,
            field_status={},  # Will be populated by post-processor
            line_items=[],
            message=None,
            reasoning_details=reasoning_details,
        )
    except AIExtractionError as e:
        logger.warning(f"AI extraction failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in AI extraction: {e}")
        return None
