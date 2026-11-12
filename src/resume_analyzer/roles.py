"""Layer 4: target-role profiles and role fit.

With no job description, a user can pick a role (e.g. "Data Analyst") and see how well the
resume's skills cover that role's core and bonus skills, plus a ranked "learn next" list.
The profiles are hand-written in data/roles.json: opinionated, and meant to be edited.
"""

import json
from functools import lru_cache
from importlib import resources

from resume_analyzer.schemas import LearnNext, RoleFit, RoleInfo
from resume_analyzer.skills import load_taxonomy

CORE_SHARE, BONUS_SHARE = 0.7, 0.3  # core skills are worth more than bonus skills
MAX_LEARN_NEXT = 8
MAX_RELATED = 3


@lru_cache
def _data() -> dict:
    raw = resources.files("resume_analyzer").joinpath("data/roles.json").read_text("utf-8")
    return json.loads(raw)


def list_roles() -> list[RoleInfo]:
    """All role profiles, in file order (for `GET /api/roles`)."""
    return [RoleInfo(**role) for role in _data()["roles"]]


def get_role(role_id: str) -> RoleInfo | None:
    """Look a role up by id; None if unknown."""
    return next((role for role in list_roles() if role.id == role_id), None)


@lru_cache
def related_skills() -> dict[str, list[str]]:
    """The `related` map made symmetric: if A lists B, B also lists A."""
    related: dict[str, list[str]] = {}
    for skill, others in _data()["related"].items():
        for other in others:
            related.setdefault(skill, []).append(other)
            related.setdefault(other, []).append(skill)
    return {skill: list(dict.fromkeys(others)) for skill, others in related.items()}


def _hint(skill: str, known: list[str], priority: str) -> str:
    if known:
        return f"You already know {', '.join(known)}, so {skill} is a short step."
    if priority == "core":
        return f"{skill} is core for this role. Build a small project with it and add it to Skills."
    return f"{skill} would make you stand out. Try it in a side project."


def role_fit(role: RoleInfo, resume_skills: list[str]) -> RoleFit:
    """How much of the role's core and bonus skills the resume mentions, and what to learn next."""
    have = set(resume_skills)
    core_hit = [s for s in role.core if s in have]
    core_miss = [s for s in role.core if s not in have]
    bonus_hit = [s for s in role.bonus if s in have]
    bonus_miss = [s for s in role.bonus if s not in have]

    core_fraction = len(core_hit) / len(role.core) if role.core else 0.0
    if role.bonus:
        fraction = CORE_SHARE * core_fraction + BONUS_SHARE * len(bonus_hit) / len(role.bonus)
    else:
        fraction = core_fraction

    categories = {skill.name: skill.category for skill in load_taxonomy()}
    learn: list[LearnNext] = []
    for priority, missing in (("core", core_miss), ("bonus", bonus_miss)):
        for skill in missing:
            # Related skills the candidate has: curated links first, then same-category skills.
            related = [r for r in related_skills().get(skill, []) if r in have]
            same_category = [
                s
                for s in resume_skills
                if categories.get(s) == categories.get(skill) and s != skill
            ]
            known = list(dict.fromkeys([*related, *same_category]))[:MAX_RELATED]
            learn.append(
                LearnNext(
                    skill=skill,
                    priority=priority,
                    related_you_have=known,
                    hint=_hint(skill, known, priority),
                )
            )
    # Core before bonus; inside each group, skills with a bridge from what you know come first.
    learn.sort(key=lambda item: (item.priority != "core", not item.related_you_have))
    return RoleFit(
        role_id=role.id,
        role_name=role.name,
        fit_percent=round(100 * fraction),
        core_matched=core_hit,
        core_missing=core_miss,
        bonus_matched=bonus_hit,
        bonus_missing=bonus_miss,
        learn_next=learn[:MAX_LEARN_NEXT],
    )
