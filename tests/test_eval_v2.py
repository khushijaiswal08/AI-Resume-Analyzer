"""The v2 quality checks in scripts/run_eval.py, and the discrimination they stand for."""

import json
import shutil

from resume_analyzer.service import analyze_text
from tests.conftest import EVALS, read_eval
from tests.test_eval import load_run_eval


def test_quality_checks_pass_on_the_shipped_samples():
    run_eval = load_run_eval()
    rows = run_eval.evaluate_quality()
    assert len(rows) == 6
    assert run_eval.quality_failures(rows) == []


def test_a_violated_bound_is_reported(tmp_path):
    run_eval = load_run_eval()
    shutil.copytree(EVALS, tmp_path / "evals")
    expected = json.loads((EVALS / "quality_expected.json").read_text(encoding="utf-8"))
    expected["samples"]["quality_samples/weak_pat_generic.txt"]["ats_max"] = 5
    expected["samples"]["quality_samples/messy_sam_layout.txt"]["non_pass"] = ["email"]
    (tmp_path / "evals" / "quality_expected.json").write_text(
        json.dumps(expected), encoding="utf-8"
    )
    problems = run_eval.quality_failures(run_eval.evaluate_quality(tmp_path / "evals"))
    assert any("weak_pat_generic" in p and "ats=" in p for p in problems)
    assert any("messy_sam_layout" in p and "'email' should not pass" in p for p in problems)


def test_main_exit_code_includes_quality(capsys):
    run_eval = load_run_eval()
    assert run_eval.main(["--min-f1", "0.0"]) == 0
    assert "v2 layers" in capsys.readouterr().out


def test_weak_resume_scores_below_every_strong_resume_on_every_layer():
    weak = analyze_text(read_eval("quality_samples/weak_pat_generic.txt"))
    for name in (
        "ada_testwell_ml",
        "bruno_placeholder_frontend",
        "carla_sampleton_data",
        "dev_fakename_devops",
    ):
        strong = analyze_text(read_eval(f"samples/{name}.txt"))
        assert weak.ats_score.total < strong.ats_score.total, name
        assert weak.bullets.average_score < strong.bullets.average_score, name
        assert weak.readiness.score < strong.readiness.score, name


def test_messy_layout_scores_below_clean_layout_on_parseability():
    messy = analyze_text(read_eval("quality_samples/messy_sam_layout.txt"))
    clean = analyze_text(read_eval("samples/dev_fakename_devops.txt"))
    assert messy.ats_checks.score < clean.ats_checks.score
    assert messy.ats_checks.failed >= 1 and clean.ats_checks.failed == 0


def test_quality_samples_are_fictional():
    for path in (EVALS / "quality_samples").glob("*.txt"):
        text = path.read_text(encoding="utf-8")
        assert "fictional" in text.lower()
        assert "@example.com" in text


def test_packaged_sample_matches_the_eval_sample():
    from resume_analyzer.sample import load_sample

    sample = load_sample()
    assert sample.resume_text == read_eval("samples/ada_testwell_ml.txt")
    assert sample.job_description == read_eval("samples/ml_engineer.jd.txt")
