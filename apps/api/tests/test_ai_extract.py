"""Tests for OpenRouter AI extraction adapter."""

import json
from unittest.mock import MagicMock, AsyncMock, patch
import httpx
import pytest

from app.invoices.ai_extract import OpenRouterAdapter, extract_with_ai, AIExtractionError
from app.invoices.models import InvoiceExtraction


def _make_adapter(api_key="test-key", model="test-model", reasoning_enabled=False):
    adapter = OpenRouterAdapter()
    adapter.api_key = api_key
    adapter.model = model
    adapter.base_url = "https://openrouter.ai/api/v1"
    adapter.reasoning_enabled = reasoning_enabled
    adapter._messages = []
    return adapter


def _make_response(content: str):
    """Create a mock httpx response returning the given content string."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": content}}]}
    mock_response.raise_for_status = MagicMock()
    return mock_response


def _make_response_with_reasoning(content: str, reasoning_details: dict):
    """Create a mock httpx response with content and reasoning_details."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": content,
                    "reasoning_details": reasoning_details,
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()
    return mock_response


def _make_async_client(mock_response):
    """Create a mock httpx.AsyncClient that returns mock_response on post."""
    mock_client = MagicMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.post = AsyncMock(return_value=mock_response)
    return mock_client


VALID_EXTRACTION_JSON = json.dumps(
    {
        "invoice_number": {"value": "INV-2024-001", "status": "FOUND", "confidence": 0.95},
        "supplier": {
            "legal_name": {"value": "Test Supplier", "status": "FOUND"},
            "gstin": {"value": "27ABCDE1234F1Z5", "status": "FOUND"},
        },
        "buyer": {
            "legal_name": {"value": "Buyer Corp", "status": "FOUND"},
            "gstin": {"value": "27XYZAB5678G1Z6", "status": "FOUND"},
        },
        "amounts": {
            "grand_total": {"value": "11800", "status": "FOUND", "confidence": 0.99},
        },
    }
)


class TestOpenRouterAdapterConfiguration:
    def test_is_configured_true_when_key_and_model_set(self):
        adapter = _make_adapter()
        assert adapter.is_configured() is True

    def test_is_configured_false_when_no_api_key(self):
        adapter = _make_adapter(api_key="")
        assert adapter.is_configured() is False

    def test_is_configured_false_when_no_model(self):
        adapter = _make_adapter(model="")
        assert adapter.is_configured() is False


class TestExtractSuccess:
    @pytest.mark.asyncio
    async def test_extract_returns_validated_extraction(self):
        adapter = _make_adapter()
        mock_response = _make_response(VALID_EXTRACTION_JSON)
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            extraction = await adapter.extract("INVOICE text here")

        assert isinstance(extraction, InvoiceExtraction)
        assert extraction.invoice_number.value == "INV-2024-001"
        assert extraction.supplier.legal_name.value == "Test Supplier"
        assert extraction.supplier.gstin.value == "27ABCDE1234F1Z5"
        assert extraction.amounts.grand_total.value == "11800"

    @pytest.mark.asyncio
    async def test_extract_posts_to_chat_completions_endpoint(self):
        adapter = _make_adapter()
        mock_response = _make_response(VALID_EXTRACTION_JSON)
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client) as mock_async_client:
            await adapter.extract("INVOICE text here")

        call_args = mock_client.post.call_args
        url = call_args.args[0]
        assert url == "https://openrouter.ai/api/v1/chat/completions"

    @pytest.mark.asyncio
    async def test_extract_sends_correct_headers(self):
        adapter = _make_adapter()
        mock_response = _make_response(VALID_EXTRACTION_JSON)
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.extract("INVOICE text here")

        call_args = mock_client.post.call_args
        headers = call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer test-key"
        assert headers["Content-Type"] == "application/json"
        assert headers["HTTP-Referer"] == "http://localhost:3000"
        assert headers["X-Title"] == "Invoice Intelligence Workbench"

    @pytest.mark.asyncio
    async def test_extract_payload_contains_model_and_messages(self):
        adapter = _make_adapter()
        mock_response = _make_response(VALID_EXTRACTION_JSON)
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.extract("INVOICE text here")

        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["model"] == "test-model"
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"
        assert "INVOICE text here" in payload["messages"][1]["content"]

    @pytest.mark.asyncio
    async def test_extract_excludes_reasoning_when_disabled(self):
        adapter = _make_adapter(reasoning_enabled=False)
        mock_response = _make_response(VALID_EXTRACTION_JSON)
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.extract("INVOICE text here")

        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        assert "reasoning" not in payload

    @pytest.mark.asyncio
    async def test_extract_includes_reasoning_when_enabled(self):
        adapter = _make_adapter(reasoning_enabled=True)
        mock_response = _make_response(VALID_EXTRACTION_JSON)
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.extract("INVOICE text here")

        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        assert payload["reasoning"] == {"enabled": True}


class TestExtractErrors:
    @pytest.mark.asyncio
    async def test_extract_malformed_json_raises_error(self):
        adapter = _make_adapter()
        mock_response = _make_response("not valid json {{{")
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(AIExtractionError, match="Invalid JSON"):
                await adapter.extract("INVOICE text")

    @pytest.mark.asyncio
    async def test_extract_auth_failure_raises_error(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=mock_response
        )
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(AIExtractionError):
                await adapter.extract("INVOICE text")

    @pytest.mark.asyncio
    async def test_extract_timeout_raises_error(self):
        adapter = _make_adapter()
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(AIExtractionError):
                await adapter.extract("INVOICE text")

    @pytest.mark.asyncio
    async def test_extract_provider_error_raises_error(self):
        adapter = _make_adapter()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error", request=MagicMock(), response=mock_response
        )
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(AIExtractionError):
                await adapter.extract("INVOICE text")

    @pytest.mark.asyncio
    async def test_extract_empty_content_raises_error(self):
        adapter = _make_adapter()
        mock_response = _make_response("")
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(AIExtractionError, match="Empty response"):
                await adapter.extract("INVOICE text")

    @pytest.mark.asyncio
    async def test_extract_schema_validation_failure_raises_error(self):
        adapter = _make_adapter()
        invalid_schema_json = json.dumps({"invoice_number": "not-an-object"})
        mock_response = _make_response(invalid_schema_json)
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(AIExtractionError, match="Schema validation"):
                await adapter.extract("INVOICE text")


class TestReasoningPreservation:
    @pytest.mark.asyncio
    async def test_extract_stores_assistant_message_with_reasoning_details(self):
        adapter = _make_adapter(reasoning_enabled=True)
        mock_response = _make_response_with_reasoning(
            VALID_EXTRACTION_JSON, {"tokens": 150, "reasoning": "thinking step by step"}
        )
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.extract("INVOICE text")

        details = adapter.get_reasoning_details()
        assert details is not None
        assert details["tokens"] == 150
        assert details["reasoning"] == "thinking step by step"

    @pytest.mark.asyncio
    async def test_extract_includes_prior_messages_when_reasoning_enabled(self):
        adapter = _make_adapter(reasoning_enabled=True)
        adapter._messages = [
            {"role": "assistant", "content": "previous extraction", "reasoning_details": {"tokens": 100}}
        ]
        mock_response = _make_response(VALID_EXTRACTION_JSON)
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            await adapter.extract("follow up text")

        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        messages = payload["messages"]
        assert len(messages) == 3
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "previous extraction"
        assert messages[1]["reasoning_details"] == {"tokens": 100}

    @pytest.mark.asyncio
    async def test_refine_continues_from_previous_reasoning(self):
        adapter = _make_adapter(reasoning_enabled=True)
        adapter._messages = [
            {"role": "assistant", "content": "previous extraction", "reasoning_details": {"tokens": 100}}
        ]
        mock_response = _make_response(VALID_EXTRACTION_JSON)
        mock_client = _make_async_client(mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            extraction = await adapter.refine("Are you sure? Think carefully.")

        assert isinstance(extraction, InvoiceExtraction)
        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        messages = payload["messages"]
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Are you sure? Think carefully."

    @pytest.mark.asyncio
    async def test_refine_raises_when_reasoning_disabled(self):
        adapter = _make_adapter(reasoning_enabled=False)
        with pytest.raises(AIExtractionError, match="Reasoning is not enabled"):
            await adapter.refine("Think again.")

    @pytest.mark.asyncio
    async def test_refine_raises_when_no_prior_extraction(self):
        adapter = _make_adapter(reasoning_enabled=True)
        with pytest.raises(AIExtractionError, match="No prior extraction"):
            await adapter.refine("Think again.")

    def test_reset_conversation_clears_messages(self):
        adapter = _make_adapter(reasoning_enabled=True)
        adapter._messages = [{"role": "assistant", "content": "old"}]
        adapter.reset_conversation()
        assert adapter._messages == []


class TestExtractWithAI:
    @pytest.mark.asyncio
    async def test_extract_with_ai_returns_none_when_disabled(self):
        with patch(
            "app.invoices.ai_extract.settings.ai_extraction_enabled", False
        ):
            result = await extract_with_ai("INVOICE text")
            assert result is None

    @pytest.mark.asyncio
    async def test_extract_with_ai_returns_none_when_not_configured(self):
        with patch(
            "app.invoices.ai_extract.settings.ai_extraction_enabled", True
        ), patch(
            "app.invoices.ai_extract.settings.openrouter_api_key", ""
        ):
            result = await extract_with_ai("INVOICE text")
            assert result is None

    @pytest.mark.asyncio
    async def test_extract_with_ai_success(self):
        with patch(
            "app.invoices.ai_extract.settings.ai_extraction_enabled", True
        ), patch(
            "app.invoices.ai_extract.settings.openrouter_api_key", "test-key"
        ), patch(
            "app.invoices.ai_extract.settings.openrouter_model", "test-model"
        ):
            adapter = _make_adapter()
            mock_response = _make_response(VALID_EXTRACTION_JSON)
            mock_client = _make_async_client(mock_response)

            with patch(
                "app.invoices.ai_extract.OpenRouterAdapter", return_value=adapter
            ), patch("httpx.AsyncClient", return_value=mock_client):
                result = await extract_with_ai("INVOICE text")

        assert result is not None
        assert result.kind == "ai_enhanced"
        assert result.extraction.invoice_number.value == "INV-2024-001"
