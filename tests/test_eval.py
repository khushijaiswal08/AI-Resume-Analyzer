"""Sanity checks for the evaluation set and scripts/run_eval.py."""

import importlib.util
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "evals" / "samples"


def load_run_eval():
    spec = importlib.util.spec_from_file_location("run_eval", ROOT / "scripts" / "run_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prf():
    run_eval = load_run_eval()
    assert run_eval.prf(8, 2, 0) == (0.8, 1.0, 2 * 0.8 / 1.8)
    assert run_eval.prf(0, 0, 0) == (0.0, 0.0, 0.0)


def test_eval_runs_on_all_samples():
    rows = load_run_eval().evaluate()
    expected = json.loads((ROOT / "evals" / "expected.json").read_text(encoding="utf-8"))
    assert len(rows) == len(expected["samples"]) == 4
    for row in rows:
        assert all(0.0 <= value <= 1.0 for value in row["metrics"])


def test_labels_use_taxonomy_names():
    from resume_analyzer.skills import load_taxonomy

    names = {skill.name for skill in load_taxonomy()}
    expected = json.loads((ROOT / "evals" / "expected.json").read_text(encoding="utf-8"))
    for labels in expected["samples"].values():
        assert set(labels) <= names


def test_samples_are_fictional():
    files = list(SAMPLES.glob("*.txt"))
    assert len([f for f in files if not f.name.endswith(".jd.txt")]) == 4
    assert 2 <= len([f for f in files if f.name.endswith(".jd.txt")]) <= 3
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "fictional" in text.lower()
        for email in re.findall(r"[\w.+-]+@[\w.-]+", text):
            assert email.endswith("@example.com")
        for digits in re.findall(r"\d{3}[\s.-]\d{3}[\s.-]\d{4}", text):
            assert digits.startswith("555")


def test_min_f1_threshold_sets_exit_code(capsys):
    run_eval = load_run_eval()
    assert run_eval.main(["--min-f1", "0.0"]) == 0
    assert run_eval.main(["--min-f1", "1.01"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_ci_threshold_holds_for_current_extractor():
    # Mirrors the CI step: a regression in skill extraction must fail this test too.
    run_eval = load_run_eval()
    assert run_eval.overall_f1(run_eval.evaluate()) >= 0.90
