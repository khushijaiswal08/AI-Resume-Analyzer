from resume_analyzer.ats_checks import run_ats_checks
from resume_analyzer.sections import detect_sections, split_lines
from tests.conftest import SAMPLE_RESUME, read_eval


def checks(text: str) -> dict[str, object]:
    report = run_ats_checks(text, split_lines(text), detect_sections(text))
    return {item.id: item for item in report.items}


def test_clean_resume_passes_the_basics():
    items = checks(read_eval("samples/ada_testwell_ml.txt"))
    for check_id in ("email", "phone", "headings", "section_order", "columns", "glyphs"):
        assert items[check_id].status == "pass", check_id


def test_missing_contact_details():
    items = checks("Skills\nPython\n")
    assert items["email"].status == "fail" and items["email"].fix
    assert items["phone"].status == "warn"
    assert "contact_position" not in items  # nothing to position


def test_contact_far_from_the_top_warns():
    text = "\n".join(["Line of text"] * 12) + "\nme@example.com\n"
    assert checks(text)["contact_position"].status == "warn"
    assert "contact_position" not in checks(SAMPLE_RESUME)


def test_missing_headings_one_warns_two_fail():
    text = "Experience\nDid things\nSkills\nPython\n"
    assert checks(text)["headings"].status == "warn"
    assert checks("Experience\nDid things\n")["headings"].status == "fail"
    assert "education" in checks(text)["headings"].detail


def test_education_before_experience_is_flagged():
    text = "Education\nB.Sc.\nExperience\nDeveloper\nSkills\nPython\n"
    item = checks(text)["section_order"]
    assert item.status == "warn" and "Education comes before Experience" in item.detail


def test_summary_not_first_is_flagged():
    text = "Skills\nPython\nSummary\nHello there\nExperience\nX\n"
    assert "Summary is not the first section" in checks(text)["section_order"].detail


def test_mixed_date_formats_warn():
    text = "Experience\nA, Jan 2021 - Mar 2022\nB, 05/2019 - 06/2020\n"
    item = checks(text)["date_formats"]
    assert item.status == "warn" and "2 different ways" in item.detail
    assert checks("Experience\nA, Jan 2021 - Mar 2022\n")["date_formats"].status == "pass"


def test_column_artifacts_warn_and_fail_with_evidence():
    row = "Python, SQL        Developer at Notreal Inc."
    warn = checks("\n".join([row] * 3))["columns"]
    fail = checks("\n".join([row] * 8))["columns"]
    assert warn.status == "warn" and fail.status == "fail"
    assert warn.evidence and warn.evidence[0].text == row  # lines are stripped but intact


def test_table_like_lines_and_run_on_lines():
    header = "\n".join(f"Header line {i}" for i in range(8))
    piped = "\n".join(["Role | Company | 2020"] * 3)
    assert checks(header + "\n" + piped)["tables"].status == "warn"
    assert checks(header + "\n" + "\n".join(["x" * 170] * 3))["tables"].status == "warn"
    assert checks(piped)["tables"].status == "pass"  # first lines may hold "email | phone | city"


def test_odd_glyphs_are_found_with_offsets():
    text = "Skills\n➤ Python\n icon\n- plain dash is fine\n"
    item = checks(text)["glyphs"]
    assert item.status == "warn"
    assert [text[e.start : e.end] for e in item.evidence] == ["➤", ""]
    assert checks("- a\n* b\n• c\n")["glyphs"].status == "pass"


def test_length_thresholds():
    def status(words: int) -> str:
        return checks(" ".join(["word"] * words))["length"].status

    assert [status(n) for n in (50, 200, 500, 1500, 2000)] == [
        "fail",
        "warn",
        "pass",
        "warn",
        "fail",
    ]


def test_extraction_check():
    assert checks("tiny")["text_extraction"].status == "fail"
    assert checks(read_eval("samples/ada_testwell_ml.txt"))["text_extraction"].status == "pass"


def test_summary_counts_and_score():
    text = read_eval("quality_samples/messy_sam_layout.txt")
    report = run_ats_checks(text, split_lines(text), detect_sections(text))
    assert report.passed + report.warned + report.failed == len(report.items)
    assert report.score == round(100 * (report.passed + 0.5 * report.warned) / len(report.items))
    good = read_eval("samples/ada_testwell_ml.txt")
    better = run_ats_checks(good, split_lines(good), detect_sections(good))
    assert better.score > report.score


def test_length_advice_matches_the_score_breakdown_range():
    from resume_analyzer.scoring import IDEAL_WORDS

    low, high = IDEAL_WORDS
    fix = checks(" ".join(["word"] * 200))["length"].fix
    assert f"{low}-{high:,}" in fix.replace(",", "", 1) or f"{low:,}-{high:,}" in fix
