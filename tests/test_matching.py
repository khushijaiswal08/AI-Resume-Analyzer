from resume_analyzer.matching import extract_jd_skills, match_skills
from resume_analyzer.service import analyze_text
from tests.conftest import SAMPLE_JD, SAMPLE_RESUME


def test_extract_jd_skills():
    assert extract_jd_skills(SAMPLE_JD) == ["Python", "FastAPI", "AWS", "Kubernetes", "Terraform"]


def test_match_and_missing_and_percent():
    match = match_skills(["Python", "FastAPI", "Docker"], ["Python", "FastAPI", "AWS", "Terraform"])
    assert match.matched == ["Python", "FastAPI"]
    assert match.missing == ["AWS", "Terraform"]
    assert match.match_percent == 50


def test_match_is_case_insensitive():
    assert match_skills(["python"], ["Python"]).match_percent == 100


def test_match_percent_is_zero_for_empty_jd_skills():
    assert match_skills(["Python"], []).match_percent == 0


def test_jd_without_skills_is_scored_like_no_jd():
    # A JD with no recognised skills must not cost the resume the 10 JD points.
    with_jd = analyze_text(SAMPLE_RESUME, "We want a friendly person.")
    without_jd = analyze_text(SAMPLE_RESUME)
    assert with_jd.jd_match is None
    assert with_jd.ats_score == without_jd.ats_score
    assert any("No recognised skills" in w and "redistributed" in w for w in with_jd.warnings)


def test_nested_skill_in_jd_is_not_listed_as_missing():
    # "GitHub Actions" must not also count as a separate "GitHub" requirement.
    assert extract_jd_skills("Ship through GitHub Actions and GitLab CI.") == [
        "GitHub Actions",
        "GitLab CI",
    ]


def test_pipeline_match_uses_aliases():
    # The resume says "k8s"; the JD says "Kubernetes". They should match.
    result = analyze_text(SAMPLE_RESUME, SAMPLE_JD)
    assert "Kubernetes" in result.jd_match.matched
    assert set(result.jd_match.missing) == {"AWS", "Terraform"}
    assert result.jd_match.match_percent == 60
