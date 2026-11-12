"""Shared fixtures. Everything is offline: PDFs/DOCX are generated here and the LLM is faked."""

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from resume_analyzer.api import create_app
from resume_analyzer.config import Settings
from resume_analyzer.llm.fake import FakeLLM

# A fictional resume used across tests. Contact details are obviously fake.
SAMPLE_RESUME = """\
Testy McSample (fictional)
testy.mcsample@example.com | (555) 010-1234 | https://example.com/testy

Summary
Backend developer who likes Python, data and well-tested APIs.

Skills
Python, JS, FastAPI, PostgreSQL, Docker, k8s, Git, Communication

Experience
Software Engineer, Example Corp (2021 - 2024)
- Built a FastAPI service handling 2,000 requests per minute.
- Reduced cloud costs by 30% by right-sizing Docker containers.
- Improved test coverage from 40% to 85% with pytest.
- Led a team of 3 interns.

Projects
Todo API - FastAPI + PostgreSQL demo app.

Education
B.Sc. Computer Science, Sample University, 2021
"""

SAMPLE_JD = "We need Python, FastAPI, Kubernetes, AWS and Terraform experience."


def make_pdf(text: str, pages: int = 1) -> bytes:
    """Render `text` onto `pages` PDF pages with reportlab and return the bytes."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for _ in range(pages):
        y = 800
        for line in text.splitlines():
            pdf.drawString(40, y, line)
            y -= 14
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_docx(text: str, table_cells: list[str] | None = None) -> bytes:
    """Build a DOCX with one paragraph per line (and optionally a one-row table)."""
    from docx import Document

    document = Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    if table_cells:
        table = document.add_table(rows=1, cols=len(table_cells))
        for cell, value in zip(table.rows[0].cells, table_cells, strict=True):
            cell.text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def llm_json(**overrides) -> str:
    """A valid LLM response, with fields overridable per test."""
    payload = {
        "summary": "Backend developer focused on Python APIs.",
        "suggestions": ["Quantify the impact of the Todo API project."],
        "interview_questions": [
            {
                "question": "How do you structure a FastAPI app?",
                "skill": "FastAPI",
                "difficulty": "medium",
            }
        ],
    }
    payload.update(overrides)
    return json.dumps(payload)


@pytest.fixture
def settings() -> Settings:
    """Settings that ignore any local .env file, so tests never see a real key."""
    return Settings(_env_file=None, gemini_api_key=None)


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM([llm_json()])


@pytest.fixture
def client(settings: Settings, fake_llm: FakeLLM) -> TestClient:
    return TestClient(create_app(settings, llm_client=fake_llm))


@pytest.fixture
def client_without_llm(settings: Settings) -> TestClient:
    return TestClient(create_app(settings, llm_client=None))


EVALS = Path(__file__).resolve().parent.parent / "evals"


def read_eval(relative: str) -> str:
    """Text of a fictional sample under evals/, e.g. read_eval("samples/ada_testwell_ml.txt")."""
    return (EVALS / relative).read_text(encoding="utf-8")
