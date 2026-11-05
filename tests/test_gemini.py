"""GeminiClient tests with an injected stand-in SDK object: no network, no API key."""

from types import SimpleNamespace

import pytest

from resume_analyzer.config import Settings
from resume_analyzer.llm.base import LLMError
from resume_analyzer.llm.gemini import GeminiClient
from resume_analyzer.models import LLMInsights
from resume_analyzer.service import build_llm_client
from tests.conftest import llm_json


class FakeModels:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        output = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        if isinstance(output, Exception):
            raise output
        return SimpleNamespace(text=output)


def make_client(*outputs, max_retries=2):
    models = FakeModels(outputs)
    sdk = SimpleNamespace(models=models)
    client = GeminiClient("unused", "gemini-test", max_retries=max_retries, sdk_client=sdk)
    return client, models


def test_requests_json_mode_with_schema_and_system_instruction():
    client, models = make_client(llm_json())
    result = client.generate_json("prompt", LLMInsights, system_instruction="be safe")
    assert isinstance(result, LLMInsights)
    call = models.calls[0]
    assert call["model"] == "gemini-test"
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_json_schema == LLMInsights.model_json_schema()
    assert call["config"].system_instruction == "be safe"


def test_invalid_output_is_retried():
    client, models = make_client("nope", llm_json())
    assert client.generate_json("p", LLMInsights).summary
    assert len(models.calls) == 2


def test_gives_up_after_retries():
    client, models = make_client("nope", max_retries=2)
    with pytest.raises(LLMError):
        client.generate_json("p", LLMInsights)
    assert len(models.calls) == 3


def test_sdk_errors_become_llm_error():
    client, _ = make_client(TimeoutError("slow"))
    with pytest.raises(LLMError, match="TimeoutError"):
        client.generate_json("p", LLMInsights)


def test_empty_response_text_is_invalid():
    client, _ = make_client(None, max_retries=0)
    with pytest.raises(LLMError):
        client.generate_json("p", LLMInsights)


def test_no_key_means_no_client():
    assert build_llm_client(Settings(_env_file=None, gemini_api_key=None)) is None


def test_empty_key_from_env_example_counts_as_unset(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    settings = Settings(_env_file=None)
    assert settings.gemini_api_key is None
    assert settings.llm_configured is False
    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.max_upload_bytes == 5 * 1024 * 1024
