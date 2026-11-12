from resume_analyzer.jd import analyze_jd, detect_seniority, find_years
from resume_analyzer.sections import split_lines
from resume_analyzer.skill_evidence import build_skill_evidence
from resume_analyzer.skills import find_skill_mentions
from tests.conftest import read_eval

RESUME = """\
Skills
Python, SQL, Docker, PyTorch, AWS

Experience
Engineer (2022 - 2024)
- Built a Python service in Docker that cut latency by 30% for 4 teams.
"""


def analyze(jd: str, resume: str = RESUME, years: float | None = None):
    lines = split_lines(resume)
    evidence = build_skill_evidence(resume, find_skill_mentions(resume), lines)
    return analyze_jd(jd, evidence, years)


def by_skill(analysis):
    return {req.skill: req for req in analysis.requirements}


def test_headings_set_priority():
    jd = "Requirements\n- Python\nNice to have\n- Kubernetes\n- Airflow\n"
    reqs = by_skill(analyze(jd))
    assert reqs["Python"].priority == "required" and reqs["Python"].weight == 2
    assert reqs["Kubernetes"].priority == "preferred" and reqs["Kubernetes"].weight == 1
    assert reqs["Airflow"].priority == "preferred"


def test_inline_heading_and_phrase_cues():
    jd = "Knowledge of Redis.\nNice to have: Kubernetes\nPython is a must; Terraform is a plus.\n"
    reqs = by_skill(analyze(jd))
    assert reqs["Kubernetes"].priority == "preferred"
    assert reqs["Python"].priority == "required"
    assert reqs["Terraform"].priority == "preferred"
    assert reqs["Redis"].priority == "required"  # unlabelled skills count as required


def test_phrase_cue_beats_heading():
    jd = "Nice to have\n- Docker\n- Must know Python\n"
    reqs = by_skill(analyze(jd))
    assert reqs["Python"].priority == "required" and reqs["Docker"].priority == "preferred"


def test_required_wins_when_a_skill_is_mentioned_both_ways():
    jd = "Requirements\n- Python\nNice to have\n- Python again\n"
    assert by_skill(analyze(jd))["Python"].priority == "required"


def test_weighted_percent_counts_required_double():
    # required Python (matched, weight 2) + preferred Kubernetes (missing, weight 1) = 2/3
    analysis = analyze("Requirements\n- Python\nNice to have\n- Kubernetes\n")
    assert analysis.weighted_percent == 67
    assert (analysis.required_percent, analysis.preferred_percent) == (100, 0)
    assert (analysis.required_count, analysis.preferred_count) == (1, 1)


def test_alternatives_are_satisfied_by_either_and_counted_once():
    analysis = analyze("Requirements\n- PyTorch or TensorFlow\n- Terraform\n")
    reqs = by_skill(analysis)
    assert reqs["PyTorch"].status == "matched" and reqs["PyTorch"].alternatives == ["TensorFlow"]
    assert reqs["TensorFlow"].status == "covered_by_alternative"
    assert "PyTorch" in reqs["TensorFlow"].hint
    # group (2/2 points: matched) + Terraform (0/2): 50%, not 4/6
    assert analysis.weighted_percent == 50


def test_comma_list_ending_in_or_is_one_group_and_slash_is_a_pair():
    reqs = by_skill(analyze("Requirements\n- AWS, Azure, or Google Cloud\n- Docker/Kubernetes\n"))
    assert set(reqs["AWS"].alternatives) == {"Azure", "Google Cloud"}
    assert reqs["Docker"].alternatives == ["Kubernetes"]
    plain = by_skill(analyze("Requirements\n- Python, SQL and Redis\n"))
    assert all(not req.alternatives for req in plain.values())


def test_missing_and_listed_only_get_where_to_add_hints():
    jd = "Requirements\n- Terraform\n- SQL\n- Docker\n- Communication\n"
    reqs = by_skill(analyze(jd))
    assert reqs["Terraform"].status == "missing"
    assert reqs["Terraform"].where_to_add == ["Skills", "Projects", "Experience"]
    assert reqs["Communication"].where_to_add == ["Summary", "Experience"]
    assert reqs["SQL"].status == "matched" and reqs["SQL"].demonstrated is False  # only in Skills
    assert reqs["SQL"].where_to_add == ["Experience", "Projects"]
    assert reqs["Docker"].demonstrated is True and reqs["Docker"].where_to_add == []


def test_required_lane_is_listed_first():
    jd = "Nice to have\n- Kubernetes\nRequirements\n- Python\n"
    assert [r.priority for r in analyze(jd).requirements] == ["required", "preferred"]


def test_years_asks_and_seniority():
    assert [
        a.years for a in find_years("3+ years of Python, 2-4 yrs SQL, founded 10 years ago")
    ] == [
        3,
        2,
    ]
    assert detect_seniority("Senior Backend Engineer\nWe want...", None) == "senior"
    assert detect_seniority("Lead Data Scientist", 2) == "lead"
    assert detect_seniority("Junior Analyst", 8) == "entry"
    assert detect_seniority("Analyst\nFreshers welcome", None) == "entry"
    assert detect_seniority("Engineer\n4 years of experience", 4) == "mid"
    assert detect_seniority("Engineer\n8 years", 8) == "senior"
    assert detect_seniority("Engineer", None) is None
    assert detect_seniority("Engineer\nwork with senior engineers", None) is None


def test_years_note_when_resume_is_short():
    jd = "Backend Engineer\n5+ years of experience.\nRequirements\n- Python\n"
    analysis = analyze(jd, years=2.0)
    assert analysis.years_required == 5 and analysis.resume_years_estimate == 2.0
    assert any("5+ years" in note for note in analysis.notes)
    assert not analyze(jd, years=6.0).notes
    assert any("no date ranges" in n for n in analyze(jd, years=None).notes)


def test_jd_without_skills():
    analysis = analyze("We want a friendly person.")
    assert analysis.requirements == [] and analysis.weighted_percent is None
    assert analysis.required_percent is None and analysis.notes


def test_sample_jd_files():
    ml = analyze(read_eval("samples/ml_engineer.jd.txt"), read_eval("samples/ada_testwell_ml.txt"))
    reqs = by_skill(ml)
    assert reqs["Python"].priority == "required"
    assert reqs["Kubernetes"].priority == "preferred" and reqs["Airflow"].priority == "preferred"
    assert reqs["TensorFlow"].status == "covered_by_alternative"
    assert reqs["Vector Databases"].status == "missing"
    analyst = by_skill(analyze(read_eval("samples/data_analyst.jd.txt")))
    assert analyst["SQL"].priority == "required" and analyst["dbt"].priority == "preferred"
    assert analyst["Tableau"].alternatives == ["Power BI"]


def test_years_snippet_is_cut_at_word_boundaries_and_stays_on_the_line():
    jd = "Intro line.\nLooking for somebody with 5+ years of experience in tooling.\nNext"
    snippet = find_years(jd)[0].text
    assert "5+ years" in snippet
    assert snippet.split()[0] in jd.split() and snippet.split()[-1] in jd.split()
    assert "Intro" not in snippet and "Next" not in snippet
