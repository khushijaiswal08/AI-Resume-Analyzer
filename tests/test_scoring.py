import pytest

from resume_analyzer.models import JDMatch, RedactionCounts
from resume_analyzer.scoring import (
    WEIGHTS,
    allocate_weights,
    count_action_verb_lines,
    count_quantified_lines,
    score_resume,
)
from resume_analyzer.service import analyze_text
from tests.conftest import SAMPLE_JD, SAMPLE_RESUME


def test_base_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


@pytest.mark.parametrize("include_jd", [True, False])
def test_allocated_weights_sum_to_100(include_jd):
    assert sum(allocate_weights(include_jd).values()) == 100


def test_no_jd_redistributes_proportionally():
    weights = allocate_weights(include_jd=False)
    assert "jd_coverage" not in weights
    # Every remaining criterion grows, and the order of importance is preserved.
    for name, weight in weights.items():
        assert weight >= WEIGHTS[name]
    assert weights["sections"] > weights["skills"] > weights["length"] > weights["contact_info"]


def _score(jd_match=None, text=SAMPLE_RESUME, **kwargs):
    defaults = {
        "sections": ["experience", "education", "skills"],
        "skill_count": 10,
        "word_count": 500,
        "redaction": RedactionCounts(emails=1, phones=1),
    }
    return score_resume(text=text, jd_match=jd_match, **{**defaults, **kwargs})


def test_total_is_sum_of_breakdown_and_maxes_sum_to_100():
    for jd in (None, JDMatch(match_percent=50, matched=["Python"], missing=["AWS"])):
        score = _score(jd)
        assert score.total == sum(item.score for item in score.breakdown)
        assert sum(item.max for item in score.breakdown) == 100
        assert all(0 <= item.score <= item.max and item.reason for item in score.breakdown)


def test_jd_criterion_only_present_with_jd():
    assert "JD keyword coverage" not in [c.criterion for c in _score().breakdown]
    jd = JDMatch(match_percent=100, matched=["Python"], missing=[])
    jd_item = next(c for c in _score(jd).breakdown if c.criterion == "JD keyword coverage")
    assert jd_item.score == jd_item.max == 10


def test_no_jd_warning_is_reported():
    result = analyze_text(SAMPLE_RESUME)
    assert any("redistributed" in warning for warning in result.warnings)


@pytest.mark.parametrize(("words", "expected"), [(500, 1.0), (150, 0.5), (2000, 0.0)])
def test_length_criterion(words, expected):
    item = next(c for c in _score(word_count=words).breakdown if c.criterion == "Length")
    assert item.score == round(expected * item.max)


@pytest.mark.parametrize(("emails", "phones", "points_of_5"), [(1, 1, 5), (1, 0, 3), (0, 0, 0)])
def test_contact_criterion(emails, phones, points_of_5):
    jd = JDMatch(match_percent=0, matched=[], missing=[])  # keeps contact max at 5
    score = _score(jd, redaction=RedactionCounts(emails=emails, phones=phones))
    item = next(c for c in score.breakdown if c.criterion == "Contact info")
    assert item.score == points_of_5


def test_years_alone_are_not_quantified_achievements():
    text = "Example Corp 2019 - 2023\n- Cut latency by 40%\n- Handled 3 launches\nGraduated 2018"
    assert count_quantified_lines(text) == 2


def test_action_verbs_after_bullets():
    text = "- Built an API\n* improved tests\n• Led a team\nResponsible for things"
    assert count_action_verb_lines(text) == 3


def test_full_pipeline_score_with_jd_is_deterministic():
    first = analyze_text(SAMPLE_RESUME, SAMPLE_JD)
    second = analyze_text(SAMPLE_RESUME, SAMPLE_JD)
    assert first.ats_score == second.ats_score
    assert 0 <= first.ats_score.total <= 100
