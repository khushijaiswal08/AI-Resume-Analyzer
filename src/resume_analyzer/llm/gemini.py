"""Gemini implementation of `LLMClient` using the official `google-genai` SDK."""

import logging
import time
from typing import Any

from pydantic import BaseModel

from resume_analyzer.llm.base import LLMError, generate_with_retries

logger = logging.getLogger(__name__)


class GeminiClient:
    """Calls Gemini in JSON mode with a request timeout and validation retries."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        timeout_seconds: float = 20,
        max_retries: int = 2,
        sdk_client: Any | None = None,
    ):
        """`sdk_client` lets tests inject a stand-in so no network call is ever made."""
        self.model = model
        self.max_retries = max_retries
        if sdk_client is None:
            # Imported lazily so the rest of the app works even if the SDK is missing.
            from google import genai
            from google.genai import types

            sdk_client = genai.Client(
                api_key=api_key,
                # The SDK's timeout is in milliseconds.
                http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
            )
        self._client = sdk_client

    def _request(
        self, prompt: str, schema_model: type[BaseModel], system_instruction: str | None
    ) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            # Gemini constrains its output to this JSON Schema; we still validate it ourselves.
            response_json_schema=schema_model.model_json_schema(),
            temperature=0.4,
        )
        started = time.perf_counter()
        try:
            response = self._client.models.generate_content(
                model=self.model, contents=prompt, config=config
            )
        except Exception as exc:  # SDK raises APIError, httpx timeouts, etc.
            # Only the exception type is logged/returned: messages could echo request data.
            logger.warning("Gemini request failed: %s", type(exc).__name__)
            raise LLMError(f"Gemini request failed ({type(exc).__name__})") from exc
        text = response.text or ""
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("Gemini responded in %.0f ms (%d chars)", elapsed_ms, len(text))
        return text

    def generate_json[M: BaseModel](
        self, prompt: str, schema_model: type[M], *, system_instruction: str | None = None
    ) -> M:
        """Return Gemini's answer validated against `schema_model`, or raise LLMError."""
        return generate_with_retries(
            lambda: self._request(prompt, schema_model, system_instruction),
            schema_model,
            self.max_retries,
        )
