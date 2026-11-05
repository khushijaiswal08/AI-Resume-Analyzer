import pytest

from resume_analyzer.skills import categories, extract_skills, flatten, load_taxonomy


def found(text: str) -> set[str]:
    return set(flatten(extract_skills(text)))


def test_taxonomy_size_and_categories():
    names = [skill.name for skill in load_taxonomy()]
    assert 140 <= len(names) <= 200
    assert len(names) == len(set(names)), "skill names must be unique"
    assert categories() == [
        "languages",
        "ml_ai",
        "data",
        "web",
        "cloud_devops",
        "databases",
        "tools",
        "soft",
    ]


@pytest.mark.parametrize(
    ("text", "skill"),
    [
        ("Wrote JS daily", "JavaScript"),
        ("Deployed on k8s", "Kubernetes"),
        ("Data in Postgres", "PostgreSQL"),
        ("Used sklearn", "scikit-learn"),
        ("Built ReactJS apps", "React"),
        ("Strong problem-solving", "Problem Solving"),
        ("Strong problem solving", "Problem Solving"),
        ("Services in Golang", "Go"),
    ],
)
def test_aliases_map_to_canonical_names(text, skill):
    assert skill in found(text)


def test_java_is_not_found_inside_javascript():
    assert found("Expert in JavaScript") == {"JavaScript"}


def test_sql_is_not_found_inside_mysql():
    assert found("Tuned MySQL indexes") == {"MySQL"}


def test_matching_is_case_insensitive_for_normal_terms():
    assert {"Python", "Docker"} <= found("python and DOCKER")


@pytest.mark.parametrize("text", ["I go to meetups", "Quick to react to incidents", "R&D team"])
def test_ambiguous_short_words_need_exact_case(text):
    assert not found(text) & {"Go", "React", "R"}


def test_cased_terms_still_match_with_exact_case():
    assert {"Go", "React", "R"} <= found("Go, React and R")


def test_symbols_in_names():
    assert {"C++", "C#", "CI/CD", "Node.js"} <= found("C++, C# and CI/CD with Node.js.")


def test_sentence_ending_period_still_matches():
    assert "Python" in found("I mostly write Python.")


def test_results_are_grouped_by_category():
    skills = extract_skills("Python, Docker, Leadership")
    assert skills == {"languages": ["Python"], "cloud_devops": ["Docker"], "soft": ["Leadership"]}


def test_no_skills_returns_empty_dict():
    assert extract_skills("Nothing technical here at all.") == {}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CI with GitHub Actions", {"GitHub Actions"}),
        ("Pipelines in GitLab CI", {"GitLab CI"}),
        ("Styled with Tailwind CSS", {"Tailwind CSS"}),
    ],
)
def test_longest_match_wins_for_nested_names(text, expected):
    assert found(text) == expected


def test_shorter_skill_still_counts_when_mentioned_on_its_own():
    assert found("GitHub Actions, GitHub and CSS3") == {"GitHub Actions", "GitHub", "CSS"}


@pytest.mark.parametrize(
    "text", ["Go-to-market plan for the launch", "R-squared of 0.92 on the holdout set"]
)
def test_cased_short_terms_ignore_hyphenated_phrases(text):
    assert not found(text) & {"Go", "R"}


def test_hyphenated_cased_term_followed_by_other_words_still_matches():
    assert "React" in found("Built React-based dashboards")


def test_skills_inside_urls_and_emails_are_ignored():
    text = (
        "github.com/someone/docker-tools | https://example.com/kubernetes | python.fan@example.com"
    )
    assert found(text) == set()
