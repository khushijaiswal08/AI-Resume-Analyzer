"""LLM layer: optional, guarded, and never responsible for the score."""

from resume_analyzer.llm.base import LLMClient, LLMError
from resume_analyzer.llm.fake import FakeLLM

__all__ = ["FakeLLM", "LLMClient", "LLMError"]
