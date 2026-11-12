import pytest

from resume_analyzer.service import analyze_text
from tests.conftest import SAMPLE_JD, SAMPLE_RESUME, read_eval


@pytest.fixture(scope="module")
def result():
    return analyze_text(SAMPLE_RESUME, SAMPLE_JD)


def by_id(result):
    return {item.id: item for item in result.evidence}


def test_one_evidence_entry_per_criterion_in_score_order(result):
    assert [e.criterion for e in result.evidence] == [
        c.criterion for c in result.ats_score.breakdown
    ]
    assert [e.id for e in result.evidence] == [
        "sections",
        "skills",
        "quantified_achievements",
        "action_verbs",
        "length",
        "contact_info",
        "jd_coverage",
    ]


def test_without_jd_there_is_no_jd_evidence():
    no_jd = analyze_text(SAMPLE_RESUME)
    assert "jd_coverage" not in {e.id for e in no_jd.evidence}


def test_every_snippet_text_matches_the_resume_at_its_offsets(result):
    for criterion in result.evidence:
        for snippet in criterion.snippets:
            assert result.resume_text[snippet.start : snippet.end] == snippet.text, criterion.id
            assert snippet.kind in ("earned", "lost")


def test_sections_evidence_points_at_headings_and_lists_missing(result):
    sections = by_id(result)["sections"]
    assert {s.text for s in sections.snippets} >= {"Summary", "Skills", "Experience", "Projects"}
    assert sections.missing == ["certifications"]


def test_quantified_lines_earn_and_lines_without_numbers_lose(result):
    snippets = by_id(result)["quantified_achievements"].snippets
    earned = [s.text for s in snippets if s.kind == "earned"]
    lost = [s.text for s in snippets if s.kind == "lost"]
    assert any("2,000 requests" in text for text in earned)
    assert any("Led a team of 3 interns" in text for text in earned)
    assert not any("(555)" in text for text in earned)  # a phone number is not a result
    assert lost == ["Todo API - FastAPI + PostgreSQL demo app."]  # the one line with no number


def test_action_verb_evidence_marks_bullets_that_do_not_start_with_one():
    text = (
        "Experience\n"
        "- Built a service that handled 2,000 requests per minute.\n"
        "- Was part of the team.\n"
    )
    snippets = by_id(analyze_text(text))["action_verbs"].snippets
    assert [(s.kind, s.text) for s in snippets] == [
        ("earned", "- Built a service that handled 2,000 requests per minute."),
        ("lost", "Was part of the team."),
    ]


def test_skills_evidence_has_first_mention_of_each_skill(result):
    skills = by_id(result)["skills"]
    names = [s.note for s in skills.snippets]
    assert len(names) == len(set(names)) and "Python" in names
    assert skills.missing and "more recognised skills" in skills.missing[0]


def test_contact_evidence_and_missing():
    assert [s.text for s in by_id(analyze_text(SAMPLE_RESUME))["contact_info"].snippets] == [
        "testy.mcsample@example.com",
        "(555) 010-1234",
    ]
    bare = by_id(analyze_text("Skills\nPython\n"))["contact_info"]
    assert bare.snippets == [] and bare.missing == ["email", "phone number"]


def test_jd_evidence_lists_matched_mentions_and_missing_skills(result):
    jd = by_id(result)["jd_coverage"]
    assert {s.text for s in jd.snippets} >= {"Python", "FastAPI"}
    assert set(jd.missing) == {"AWS", "Terraform"}


def test_length_evidence():
    assert by_id(analyze_text(SAMPLE_RESUME))["length"].missing  # short resume: explained
    long = analyze_text(read_eval("samples/ada_testwell_ml.txt"))
    assert isinstance(by_id(long)["length"].missing, list)


def test_long_lines_are_cut_but_stay_consistent():
    text = "Experience\n- Built " + "x" * 400 + " for 5 teams\n"
    for item in by_id(analyze_text(text))["quantified_achievements"].snippets:
        assert len(item.text) <= 160 and text[item.start : item.end] == item.text
