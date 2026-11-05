"""A deterministic stand-in for a real LLM, used by the test suite.

It goes through the same `generate_with_retries` loop as the real client, so tests of the
retry guardrail exercise production code, not a mock of it.
"""

import json

from pydantic import BaseModel

from resume_analyzer.llm.base import LLMError, generate_with_retries

DEFAULT_RESPONSE = json.dumps(
    {
        "summary": "Candidate with hands-on Python experience building data and web projects.",
        "suggestions": [
            "Add measurable outcomes (numbers or percentages) to more bullet points.",
            "Start each bullet with a strong action verb.",
        ],
        "interview_questions": [
            {
                "question": "Walk me through a Python project you are proud of.",
                "skill": "Python",
                "difficulty": "easy",
            }
        ],
    }
)


class FakeLLM:
    """Returns scripted responses in order; the last one repeats once the list runs out.

    A response may be a string (raw model text) or an Exception instance (raised as-is,
    to simulate timeouts and API errors).
    """

    def __init__(self, responses: list[str | Exception] | None = None, max_retries: int = 2):
        self.responses: list[str | Exception] = responses or [DEFAULT_RESPONSE]
        self.max_retries = max_retries
        self.prompts: list[str] = []
        self.system_instructions: list[str | None] = []
        self.calls = 0

    def _next_raw(self) -> str:
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        response = self.responses[index]
        if isinstance(response, LLMError):
            raise response
        if isinstance(response, Exception):
            raise LLMError(f"Fake LLM error: {type(response).__name__}") from response
        return response

    def generate_json[M: BaseModel](
        self, prompt: str, schema_model: type[M], *, system_instruction: str | None = None
    ) -> M:
        """Record the prompt, then return the next scripted response validated."""
        self.prompts.append(prompt)
        self.system_instructions.append(system_instruction)
        return generate_with_retries(self._next_raw, schema_model, self.max_retries)
