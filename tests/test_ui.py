"""UI smoke tests: static assets are served, the CSP allows them, key element ids exist,
and no script source builds HTML from data with innerHTML."""

import re
from pathlib import Path

import pytest

from resume_analyzer.api import STATIC_DIR

ASSETS = [
    "theme.js",
    "dom.js",
    "charts.js",
    "viewer.js",
    "views.js",
    "export.js",
    "app.js",
    "styles.css",
]
IDS = [
    "dropzone",
    "resume",
    "role",
    "jd",
    "analyze",
    "sample",
    "error",
    "loading",
    "results",
    "tablist",
    "panels",
    "viewer-text",
    "theme-toggle",
    "export-json",
    "export-md",
    "export-print",
    "new-analysis",
]


@pytest.mark.parametrize("name", ASSETS)
def test_static_assets_are_served(client, name):
    response = client.get(f"/static/{name}")
    assert response.status_code == 200
    assert "content-security-policy" in response.headers


def test_index_references_assets_and_has_key_ids(client):
    html = client.get("/").text
    for name in ASSETS:
        assert f"/static/{name}" in html
    for element_id in IDS:
        assert f'id="{element_id}"' in html
    assert "<script>" not in html and "onclick=" not in html


def test_every_script_loaded_by_page_is_same_origin(client):
    html = client.get("/").text
    assert all(src.startswith("/static/") for src in re.findall(r'<script[^>]+src="([^"]+)"', html))


def test_scripts_never_use_innerhtml():
    for path in Path(STATIC_DIR).glob("*.js"):
        text = path.read_text(encoding="utf-8")
        for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
            assert banned not in text, f"{banned} in {path.name}"


def test_category_labels_and_rate_limit_wording_are_in_the_scripts():
    dom = (Path(STATIC_DIR) / "dom.js").read_text(encoding="utf-8")
    app = (Path(STATIC_DIR) / "app.js").read_text(encoding="utf-8")
    assert '"ML / AI"' in dom and '"Cloud / DevOps"' in dom
    assert "minutes" in app and "Retry-After" in app
