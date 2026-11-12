from resume_analyzer.bullets import analyze_bullets, extract_bullets, rating_for, tense_of
from resume_analyzer.sections import split_lines
from tests.conftest import read_eval


def report(body: str):
    return analyze_bullets(split_lines("Experience\n" + body))


def codes(item) -> set[str]:
    return {issue.code for issue in item.issues}


def test_extracts_bullets_not_headers_or_other_sections():
    text = (
        "Experience\n"
        "Engineer, Example Corp (2021 - 2024)\n"
        "- Built a service that handled 2,000 requests per minute for internal teams.\n"
        "Education\n"
        "- Studied computer science at a sample university for four years of study.\n"
    )
    found = extract_bullets(split_lines(text))
    assert [body for _, _, body in found] == [
        "Built a service that handled 2,000 requests per minute for internal teams."
    ]


def test_offsets_point_at_bullet_text():
    text = "Experience\n- Built a service that cut latency by 40% across all internal teams.\n"
    item = analyze_bullets(split_lines(text)).items[0]
    assert text[item.start : item.end] == item.text
    assert not item.text.startswith("-")


def test_strong_bullet_scores_full_marks():
    item = report(
        "- Reduced cloud costs by 30% by right-sizing Docker containers for 12 services.\n"
    ).items[0]
    assert item.score == 100 and item.rating == "strong" and item.issues == []
    assert item.hint is None


def test_weak_bullet_collects_issues_and_a_template_hint():
    item = report("- Responsible for helping with various tasks in the office.\n").items[0]
    assert {"no_action_verb", "no_metric", "weak_phrase", "too_short"} <= codes(item)
    assert item.rating == "weak"
    assert "strong verb" in item.hint
    assert not any(ch.isdigit() for ch in item.hint)  # hints never invent numbers


def test_each_issue_is_detected():
    assert "buzzword" in codes(
        report("- Built a dynamic dashboard for 4 teams using synergy and care.\n").items[0]
    )
    assert "first_person" in codes(
        report("- I built a dashboard for 4 teams to track weekly sales figures.\n").items[0]
    )
    long = " ".join(["word"] * 40)
    assert "too_long" in codes(report(f"- Built {long} for 4 teams.\n").items[0])


def test_tense_helper_and_mismatch_flags_the_minority():
    assert tense_of("Built a thing") == "past"
    assert tense_of("Build a thing") == "present"
    assert tense_of("Totally unknown start") is None
    body = (
        "- Built a service that cut latency by 40% across all internal teams quickly.\n"
        "- Deployed a pipeline that handled 12 jobs per day across the whole organisation.\n"
        "- Manage a team of 4 engineers across two product areas in different time zones.\n"
    )
    items = report(body).items
    assert [("tense_mismatch" in codes(i)) for i in items] == [False, False, True]


def test_summary_counts_and_no_bullets():
    r = report(
        "- Built a service that cut latency by 40% across all internal teams quickly.\n"
        "- Responsible for various tasks.\n"
    )
    assert r.count == 2 and r.strong + r.ok + r.weak == 2
    assert r.average_score == round(sum(i.score for i in r.items) / 2)
    empty = analyze_bullets(split_lines("Skills\nPython"))
    assert empty.count == 0 and empty.average_score is None and empty.items == []


def test_rating_thresholds():
    assert [rating_for(s) for s in (100, 75, 74, 50, 49, 0)] == [
        "strong",
        "strong",
        "ok",
        "ok",
        "weak",
        "weak",
    ]


def test_weak_resume_bullets_score_below_strong_resume():
    strong = analyze_bullets(split_lines(read_eval("samples/ada_testwell_ml.txt")))
    weak = analyze_bullets(split_lines(read_eval("quality_samples/weak_pat_generic.txt")))
    assert strong.average_score >= 75 > 50 >= weak.average_score
