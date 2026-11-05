"""The LLM interface and the shared "validate or retry" loop.

Any provider (Gemini, a fake for tests, another vendor later) only has to implement
`generate_json`. The retry loop lives here so every implementation gets the same guardrail.
"""

import json
import logging
from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """The LLM could not produce a usable answer (API error, timeout, invalid output)."""


class LLMClient(Protocol):
    """Anything that can turn a prompt into a validated Pydantic model."""

    def generate_json[M: BaseModel](
        self, prompt: str, schema_model: type[M], *, system_instruction: str | None = None
    ) -> M:
        """Return the model's answer parsed into `schema_model`, or raise LLMError."""
        ...


def parse_json_response[M: BaseModel](raw: str, schema_model: type[M]) -> M:
    """Parse raw LLM text into `schema_model`.

    Models sometimes wrap JSON in ```json fences even in JSON mode, so strip those first.
    Raises ValueError (json) or ValidationError (pydantic) on bad output.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    return schema_model.model_validate(json.loads(cleaned))


def generate_with_retries[M: BaseModel](
    call: Callable[[], str], schema_model: type[M], max_retries: int
) -> M:
    """Call the LLM, validate the output, and retry on invalid JSON / schema errors.

    `call` performs one request and returns raw text. It may raise LLMError for transport
    problems, which are NOT retried here (a timeout is unlikely to fix itself instantly).
    After 1 + `max_retries` invalid answers, raise LLMError so the caller can fall back.
    """
    attempts = 1 + max_retries
    for attempt in range(1, attempts + 1):
        raw = call()
        try:
            return parse_json_response(raw, schema_model)
        except (ValueError, ValidationError) as exc:
            # Log only the error type and size, never the content.
            logger.warning(
                "LLM output invalid (attempt %d/%d, %s, %d chars)",
                attempt,
                attempts,
                type(exc).__name__,
                len(raw),
            )
    raise LLMError(f"LLM returned invalid output {attempts} times")
