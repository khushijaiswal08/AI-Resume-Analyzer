import pytest

from resume_analyzer.roles import get_role, list_roles, related_skills, role_fit
from resume_analyzer.skills import load_taxonomy

TAXONOMY = {skill.name for skill in load_taxonomy()}


def test_eight_roles_with_unique_ids():
    roles = list_roles()
    assert len(roles) == 8
    assert len({role.id for role in roles}) == 8
    assert {"ml-engineer", "data-analyst", "automation-rpa", "devops-cloud"} <= {
        r.id for r in roles
    }


def test_every_role_skill_is_in_the_taxonomy():
    for role in list_roles():
        assert role.core and role.bonus and role.description
        assert set(role.core + role.bonus) <= TAXONOMY, role.id
        assert not set(role.core) & set(role.bonus), role.id


def test_related_map_uses_taxonomy_names_and_is_symmetric():
    related = related_skills()
    for skill, others in related.items():
        assert skill in TAXONOMY and set(others) <= TAXONOMY
        assert all(skill in related[other] for other in others)


def test_get_role():
    assert get_role("data-analyst").name == "Data Analyst"
    assert get_role("astronaut") is None


def test_full_core_and_bonus_is_100_and_nothing_is_0():
    role = get_role("data-analyst")
    assert role_fit(role, role.core + role.bonus).fit_percent == 100
    empty = role_fit(role, [])
    assert empty.fit_percent == 0 and empty.core_matched == []
    assert empty.core_missing == role.core


def test_core_counts_more_than_bonus():
    role = get_role("data-analyst")
    only_core = role_fit(role, role.core).fit_percent
    only_bonus = role_fit(role, role.bonus).fit_percent
    assert only_core == 70 and only_bonus == 30


def test_learn_next_is_core_first_with_related_hints():
    role = get_role("devops-cloud")
    fit = role_fit(role, ["Docker", "Linux", "Git", "Bash", "AWS", "CI/CD", "Python"])
    assert set(fit.core_missing) == {"Kubernetes", "Terraform"}
    first = fit.learn_next[0]
    assert first.priority == "core" and first.skill in fit.core_missing
    kube = next(item for item in fit.learn_next if item.skill == "Kubernetes")
    assert "Docker" in kube.related_you_have and "Docker" in kube.hint
    core_positions = [i for i, item in enumerate(fit.learn_next) if item.priority == "core"]
    bonus_positions = [i for i, item in enumerate(fit.learn_next) if item.priority == "bonus"]
    assert max(core_positions) < min(bonus_positions)
    assert len(fit.learn_next) <= 8


def test_hint_without_related_skills_is_generic():
    fit = role_fit(get_role("frontend"), [])
    assert all(item.related_you_have == [] for item in fit.learn_next)
    assert "core" in fit.learn_next[0].hint


@pytest.mark.parametrize("role_id", [r.id for r in list_roles()])
def test_role_fit_percent_is_bounded(role_id):
    fit = role_fit(get_role(role_id), ["Python", "SQL", "Git"])
    assert 0 <= fit.fit_percent <= 100
