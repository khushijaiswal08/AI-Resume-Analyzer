import json
import subprocess
import sys

import pytest

from resume_analyzer import cli
from resume_analyzer.config import Settings
from tests.conftest import SAMPLE_JD, SAMPLE_RESUME


@pytest.fixture(autouse=True)
def no_real_key(monkeypatch):
    # Make sure a developer's local .env can never cause a network call during tests.
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None, gemini_api_key=None))


@pytest.fixture
def resume_file(tmp_path):
    path = tmp_path / "resume.txt"
    path.write_text(SAMPLE_RESUME, encoding="utf-8")
    return path


def test_json_output(resume_file, tmp_path, capsys):
    jd = tmp_path / "jd.txt"
    jd.write_text(SAMPLE_JD, encoding="utf-8")
    assert cli.main(["analyze", str(resume_file), "--jd", str(jd), "--format", "json"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["jd_match"]["match_percent"] == 60
    assert body["llm"]["used"] is False


def test_markdown_output(resume_file, capsys):
    assert cli.main(["analyze", str(resume_file), "--no-llm"]) == 0
    out = capsys.readouterr().out
    assert "# Resume analysis" in out
    assert "ATS-style score" in out
    assert "| Sections present |" in out


def test_missing_file_exit_code(tmp_path, capsys):
    assert cli.main(["analyze", str(tmp_path / "nope.txt")]) == 2
    assert "cannot read file" in capsys.readouterr().err


def test_unsupported_file_exit_code(tmp_path, capsys):
    path = tmp_path / "image.txt"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
    assert cli.main(["analyze", str(path)]) == 1
    assert "Unsupported" in capsys.readouterr().err


def test_module_entry_point_help():
    result = subprocess.run(
        [sys.executable, "-m", "resume_analyzer", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "analyze" in result.stdout
