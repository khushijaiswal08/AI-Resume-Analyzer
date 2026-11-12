from resume_analyzer.privacy import build_redacted_preview
from resume_analyzer.readiness import BASE_WEIGHTS, build_readiness
from resume_analyzer.service import analyze_text
from tests.conftest import SAMPLE_JD, SAMPLE_RESUME


def readiness(**overrides):
    values = {
        "ats_total": 80,
        "bullet_average": 60,
        "parse_score": 100,
        "fit_percent": 40,
        "fit_label": "Job match",
    }
    return build_readiness(**{**values, **overrides})


def test_weights_sum_to_100_whatever_is_missing():
    for kwargs in (
        {},
        {"bullet_average": None},
        {"fit_percent": None, "fit_label": None},
        {"bullet_average": None, "fit_percent": None, "fit_label": None},
    ):
        assert sum(c.weight for c in readiness(**kwargs).components) == 100


def test_composite_is_the_weighted_average_and_checkable_by_hand():
    result = readiness()
    assert [c.weight for c in result.components] == [
        BASE_WEIGHTS[k] for k in ("ats", "parseability", "bullets", "fit")
    ]
    assert result.score == round((80 * 35 + 100 * 20 + 60 * 25 + 40 * 20) / 100)
    assert "does not replace" in result.explanation


def test_missing_components_are_left_out_and_explained():
    result = readiness(bullet_average=None, fit_percent=None, fit_label=None)
    assert [c.id for c in result.components] == ["ats", "parseability"]
    assert "left out" in result.explanation


def test_labels():
    assert (
        readiness(ats_total=100, bullet_average=100, parse_score=100, fit_percent=100).label
        == "Strong"
    )
    assert (
        readiness(ats_total=0, bullet_average=0, parse_score=0, fit_percent=0).label == "Major gaps"
    )


def test_readiness_sits_beside_the_ats_score_in_the_result():
    result = analyze_text(SAMPLE_RESUME, SAMPLE_JD)
    assert result.ats_score.total == sum(c.score for c in result.ats_score.breakdown)  # v1 intact
    fit = next(c for c in result.readiness.components if c.id == "fit")
    assert fit.label == "Job match" and fit.score == result.jd_analysis.weighted_percent
    role_only = analyze_text(SAMPLE_RESUME, role="backend-python")
    fit = next(c for c in role_only.readiness.components if c.id == "fit")
    assert fit.label == "Role fit" and fit.score == role_only.role_fit.fit_percent


def test_privacy_preview_shows_exactly_what_is_redacted():
    preview = build_redacted_preview(SAMPLE_RESUME, "Mail jobs@example.com", llm_configured=False)
    assert "[EMAIL]" in preview.text and "[PHONE]" in preview.text and "[URL]" in preview.text
    assert "example.com" not in preview.text and "555" not in preview.text
    assert preview.jd_text == "Mail [EMAIL]"
    assert (preview.emails, preview.phones, preview.urls) == (2, 1, 1)
    assert "No AI key" in preview.note and preview.llm_configured is False


def test_privacy_preview_matches_what_the_llm_receives(fake_llm):
    result = analyze_text(SAMPLE_RESUME, SAMPLE_JD, llm_client=fake_llm)
    prompt = fake_llm.prompts[0]
    assert result.redacted_preview.text in prompt
    assert result.redacted_preview.jd_text in prompt
    assert result.redacted_preview.llm_configured is True
    assert "testy.mcsample@example.com" not in prompt


def test_privacy_preview_without_jd():
    assert build_redacted_preview("Skills\nPython", None, llm_configured=True).jd_text is None
