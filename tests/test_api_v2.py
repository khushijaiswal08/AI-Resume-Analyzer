"""The v2 API surface: new response fields, /api/roles, /api/sample, headers, errors."""

import pytest
from fastapi.testclient import TestClient

from resume_analyzer import __version__
from resume_analyzer.api import create_app
from resume_analyzer.config import Settings
from tests.conftest import SAMPLE_JD, SAMPLE_RESUME, read_eval

V2_FIELDS = {
    "resume_text",
    "bullets",
    "ats_checks",
    "jd_analysis",
    "role_fit",
    "readability",
    "skill_evidence",
    "evidence",
    "redacted_preview",
    "readiness",
}


def post(client, text=SAMPLE_RESUME, jd=None, role=None):
    form = {}
    if jd is not None:
        form["job_description"] = jd
    if role is not None:
        form["role"] = role
    return client.post("/api/analyze", files={"resume": ("resume.txt", text.encode())}, data=form)


def test_analyze_returns_all_v2_fields(client):
    body = post(client, jd=SAMPLE_JD, role="backend-python").json()
    assert set(body) >= V2_FIELDS
    assert body["resume_text"] == SAMPLE_RESUME.strip()
    assert body["jd_analysis"]["requirements"] and body["role_fit"]["role_id"] == "backend-python"
    assert body["bullets"]["count"] >= 3
    assert body["llm"]["first_impression"] is None and body["llm"]["bullet_rewrites"] == []


def test_optional_fields_are_null_without_jd_and_role(client_without_llm):
    body = post(client_without_llm).json()
    assert body["jd_analysis"] is None and body["role_fit"] is None
    assert body["jd_match"] is None
    assert body["ats_checks"]["items"] and body["readiness"]["score"] >= 0


def test_blank_role_is_ignored_and_unknown_role_is_422(client_without_llm):
    assert post(client_without_llm, role="  ").json()["role_fit"] is None
    response = post(client_without_llm, role="astronaut")
    assert response.status_code == 422 and "GET /api/roles" in response.json()["detail"]


def test_v1_fields_are_unchanged_by_v2(client_without_llm):
    body = post(client_without_llm, jd=SAMPLE_JD).json()
    assert body["jd_match"]["match_percent"] == 60
    assert body["ats_score"]["total"] == sum(c["score"] for c in body["ats_score"]["breakdown"])
    assert body["redaction"] == {"emails": 1, "phones": 1, "urls": 1}


def test_roles_endpoint(client):
    roles = client.get("/api/roles").json()
    assert len(roles) == 8
    assert set(roles[0]) == {"id", "name", "description", "core", "bonus"}
    assert post(client, role=roles[0]["id"]).status_code == 200  # every listed id is accepted


def test_sample_endpoint_returns_a_fictional_resume_that_analyses(client_without_llm):
    sample = client_without_llm.get("/api/sample").json()
    assert set(sample) == {"name", "filename", "resume_text", "job_description", "role_id"}
    assert "fictional" in sample["resume_text"].lower()
    assert "@example.com" in sample["resume_text"] and "555" in sample["resume_text"]
    assert sample["resume_text"] == read_eval("samples/ada_testwell_ml.txt")
    assert sample["job_description"] == read_eval("samples/ml_engineer.jd.txt")
    body = post(
        client_without_llm, sample["resume_text"], sample["job_description"], sample["role_id"]
    ).json()
    assert body["readiness"]["score"] >= 80 and body["role_fit"]["fit_percent"] > 50


def test_health_has_version(client):
    assert client.get("/api/health").json()["version"] == __version__ == "2.0.0"


def test_security_headers_on_every_kind_of_response(client):
    for response in (client.get("/"), client.get("/api/health"), client.get("/nope")):
        headers = response.headers
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["x-frame-options"] == "DENY"
        assert headers["referrer-policy"] == "no-referrer"
        csp = headers["content-security-policy"]
        assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
        assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp.split("style-src")[0]
    assert client.get("/api/health").headers["cache-control"] == "no-store"


def test_error_responses_also_carry_headers(client):
    response = client.post("/api/analyze", files={"resume": ("r.txt", b"")})
    assert response.status_code == 422 and response.headers["x-frame-options"] == "DENY"


def test_index_page_has_no_inline_script_and_static_files_are_served(client):
    html = client.get("/").text
    assert "<script>" not in html  # the CSP forbids inline scripts
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/does-not-exist.js").status_code == 404


def test_api_docs_ui_is_disabled_but_schema_is_available(client):
    assert client.get("/docs").status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/api/analyze", "/api/roles", "/api/sample", "/api/health"} <= set(paths)


def test_cors_is_disabled_by_default_and_opt_in(settings):
    origin = {"Origin": "https://other.example"}
    default = TestClient(create_app(settings, llm_client=None))
    assert "access-control-allow-origin" not in default.get("/api/health", headers=origin).headers
    opted = Settings(_env_file=None, gemini_api_key=None, cors_origins="https://other.example, ")
    assert opted.cors_origin_list == ["https://other.example"]
    client = TestClient(create_app(opted, llm_client=None))
    allowed = client.get("/api/health", headers=origin).headers["access-control-allow-origin"]
    assert allowed == "https://other.example"


def test_port_env_is_respected(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    assert Settings(_env_file=None).port == 10000
    monkeypatch.delenv("PORT")
    assert Settings(_env_file=None).port == 8000


@pytest.mark.parametrize("name", ["ada_testwell_ml", "weak_pat_generic"])
def test_offsets_in_every_field_index_into_resume_text(client_without_llm, name):
    folder = "samples" if name.startswith("ada") else "quality_samples"
    text = read_eval(f"{folder}/{name}.txt")
    body = post(client_without_llm, text, SAMPLE_JD).json()
    resume = body["resume_text"]
    snippets = [
        *[(i["start"], i["end"], i["text"]) for i in body["bullets"]["items"]],
        *[
            (e["start"], e["end"], e["text"])
            for c in body["ats_checks"]["items"]
            for e in c["evidence"]
        ],
        *[(e["start"], e["end"], e["text"]) for c in body["evidence"] for e in c["snippets"]],
        *[(e["start"], e["end"], e["text"]) for e in body["readability"]["passive_examples"]],
        *[
            (e["start"], e["end"], e["text"])
            for s in body["skill_evidence"]["skills"]
            for e in s["locations"]
        ],
    ]
    assert snippets
    for start, end, snippet in snippets:
        assert resume[start:end] == snippet
