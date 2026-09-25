from typing import Any, Protocol

import httpx

from src.config.settings import settings


class LLMUnavailableError(Exception):
    """The model could not be reached or returned an unusable HTTP response."""


class LLMClient(Protocol):
    """Anything that turns chat messages into a JSON string matching a schema.

    The model has no tools: it can only return text. Swapping the local model for another provider will require another implementation of this.
    """

    async def complete_json(
        self,
        messages: list[dict[str, str]],
        json_schema: dict[str, Any],
    ) -> str: ...


class LlamaCppClient:
    """Calls a llama.cpp server through its OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.LLM_TIMEOUT_SECONDS
        self.max_tokens = max_tokens or settings.LLM_MAX_TOKENS

    async def complete_json(
        self,
        messages: list[dict[str, str]],
        json_schema: dict[str, Any],
    ) -> str:
        payload = {
            "messages": messages,
            "temperature": 0,
            "max_tokens": self.max_tokens,
            # the server can only emit JSON that matches this schema.
            "response_format": {"type": "json_object", "schema": json_schema},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            # Only the exception type is kept as response bodies may echo the prompt.
            raise LLMUnavailableError(type(exc).__name__) from None
