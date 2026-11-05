import io
import zipfile

from fastapi.testclient import TestClient

from resume_analyzer.api import create_app
from resume_analyzer.llm.fake import FakeLLM
from tests.conftest import SAMPLE_JD, SAMPLE_RESUME, make_docx, make_pdf


def post(client, data: bytes, filename="resume.txt", jd=None):
    form = {"job_description": jd} if jd is not None else {}
    return client.post("/api/analyze", files={"resume": (filename, data)}, data=form)


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "AI Resume Analyzer" in response.text
    assert "not any real ATS vendor" in response.text


def test_health_reports_llm_configuration(client, client_without_llm):
    assert client.get("/api/health").json() == {"status": "ok", "llm_configured": True}
    assert client_without_llm.get("/api/health").json() == {"status": "ok", "llm_configured": False}


def test_analyze_txt_with_jd_and_llm(client):
    response = post(client, SAMPLE_RESUME.encode(), jd=SAMPLE_JD)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "skills",
        "sections",
        "word_count",
        "ats_score",
        "jd_match",
        "llm",
        "redaction",
        "warnings",
    }
    assert "Python" in body["skills"]["languages"]
    assert body["jd_match"]["match_percent"] == 60
    assert body["llm"]["used"] is True
    assert body["llm"]["interview_questions"][0]["skill"] == "FastAPI"
    assert body["ats_score"]["total"] == sum(c["score"] for c in body["ats_score"]["breakdown"])


def test_analyze_without_llm_still_returns_200(client_without_llm):
    response = post(client_without_llm, SAMPLE_RESUME.encode())
    assert response.status_code == 200
    body = response.json()
    assert body["llm"]["used"] is False and body["llm"]["reason"]
    assert body["jd_match"] is None


def test_analyze_pdf_and_docx(client_without_llm):
    for data, name in [
        (make_pdf("Skills\nPython, Docker"), "cv.pdf"),
        (make_docx("Skills\nPython, Docker"), "cv.docx"),
    ]:
        response = post(client_without_llm, data, filename=name)
        assert response.status_code == 200, response.text
        assert "Docker" in response.json()["skills"]["cloud_devops"]


def test_wrong_magic_bytes_is_415_even_with_pdf_name(client):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("x.bin", "data")
    response = post(client, buffer.getvalue(), filename="resume.pdf")
    assert response.status_code == 415
    assert "detail" in response.json()


def test_empty_file_is_422(client):
    response = post(client, b"")
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)


def test_too_large_file_is_413(settings):
    small = settings.model_copy(update={"max_upload_mb": 0.001})  # about 1 KB
    client = TestClient(create_app(small, llm_client=None))
    response = post(client, b"a" * 5000)
    assert response.status_code == 413


def test_too_long_jd_is_413(client):
    response = post(client, SAMPLE_RESUME.encode(), jd="x" * 20_001)
    assert response.status_code == 413


def test_missing_file_is_422(client):
    assert client.post("/api/analyze").status_code == 422


def test_llm_failure_does_not_break_api(settings):
    client = TestClient(create_app(settings, llm_client=FakeLLM([TimeoutError()])))
    response = post(client, SAMPLE_RESUME.encode())
    assert response.status_code == 200
    assert response.json()["llm"]["used"] is False
