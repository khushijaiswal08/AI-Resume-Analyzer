from resume_analyzer.sections import split_lines
from resume_analyzer.skill_evidence import build_skill_evidence
from resume_analyzer.skills import find_skill_mentions

TEXT = """\
Summary
Engineer who likes Kubernetes.

Skills
Python, SQL, Docker, Terraform

Experience
Engineer (2022 - 2024)
- Built a Python service in Docker that cut latency by 30% for 4 teams.

Projects
Demo - Python and Redis app.
"""


def evidence():
    return build_skill_evidence(TEXT, find_skill_mentions(TEXT), split_lines(TEXT))


def uses():
    return {use.skill: use for use in evidence().skills}


def test_status_demonstrated_listed_only_and_mentioned():
    skills = uses()
    assert skills["Python"].status == "demonstrated"
    assert skills["Docker"].status == "demonstrated"
    assert skills["SQL"].status == "listed_only"
    assert skills["Terraform"].status == "listed_only"
    assert skills["Kubernetes"].status == "mentioned"  # only in the summary
    assert skills["Redis"].status == "demonstrated"  # used in a project


def test_counts_per_area():
    python = uses()["Python"]
    assert (python.in_skills_section, python.in_experience, python.in_projects) == (1, 1, 1)
    assert python.elsewhere == 0 and python.mentions == 3


def test_summary_counts():
    result = evidence()
    assert result.listed_only_skills == ["SQL", "Terraform"]
    assert (result.demonstrated, result.listed_only, result.mentioned) == (3, 2, 1)
    assert result.demonstrated + result.listed_only + result.mentioned == len(result.skills)


def test_locations_point_at_the_mentions_and_are_capped():
    python = uses()["Python"]
    assert [TEXT[s.start : s.end] for s in python.locations] == ["Python"] * 3
    many = "Skills\n" + "Python\n" * 6
    result = build_skill_evidence(many, find_skill_mentions(many), split_lines(many))
    assert len(result.skills[0].locations) == 3 and result.skills[0].mentions == 6


def test_skill_in_inline_skills_heading_line_counts_as_skills_section():
    text = "Skills: Python, SQL\n"
    result = build_skill_evidence(text, find_skill_mentions(text), split_lines(text))
    assert {u.skill: u.status for u in result.skills} == {
        "Python": "listed_only",
        "SQL": "listed_only",
    }


def test_no_skills():
    result = build_skill_evidence("Hello", [], split_lines("Hello"))
    assert result.skills == [] and result.demonstrated == 0
