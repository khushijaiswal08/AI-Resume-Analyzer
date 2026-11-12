"""Layer 7: skill depth signals.

A skill that appears only in the Skills list is a claim. A skill that also appears in an
Experience or Projects bullet is *demonstrated*. This module counts where each skill appears.
"""

from bisect import bisect_right

from resume_analyzer.schemas import SkillEvidence, SkillUse, Snippet
from resume_analyzer.sections import Line
from resume_analyzer.skills import SkillMention

MAX_LOCATIONS = 3
USE_SECTIONS = ("experience", "projects")


def line_at(offset: int, lines: list[Line], starts: list[int]) -> Line | None:
    """The line that contains `offset`, or None if it falls between lines."""
    index = bisect_right(starts, offset) - 1
    if index >= 0 and offset < lines[index].end:
        return lines[index]
    return None


def _status(in_skills: int, in_use: int, elsewhere: int) -> str:
    if in_use:
        return "demonstrated"
    if in_skills and not elsewhere:
        return "listed_only"
    return "mentioned"


def build_skill_evidence(
    text: str, mentions: list[SkillMention], lines: list[Line]
) -> SkillEvidence:
    """Count, for every found skill, mentions per resume area and classify its evidence."""
    starts = [line.start for line in lines]
    buckets: dict[str, dict] = {}
    for mention in mentions:
        entry = buckets.setdefault(
            mention.name,
            {
                "category": mention.category,
                "skills": 0,
                "experience": 0,
                "projects": 0,
                "elsewhere": 0,
                "locations": [],
            },
        )
        line = line_at(mention.start, lines, starts)
        section = line.section if line else None
        entry[section if section in ("skills", *USE_SECTIONS) else "elsewhere"] += 1
        if len(entry["locations"]) < MAX_LOCATIONS:
            snippet = Snippet(
                start=mention.start, end=mention.end, text=text[mention.start : mention.end]
            )
            entry["locations"].append(snippet)

    skills = []
    for name, entry in buckets.items():
        in_use = entry["experience"] + entry["projects"]
        skills.append(
            SkillUse(
                skill=name,
                category=entry["category"],
                mentions=in_use + entry["skills"] + entry["elsewhere"],
                in_skills_section=entry["skills"],
                in_experience=entry["experience"],
                in_projects=entry["projects"],
                elsewhere=entry["elsewhere"],
                status=_status(entry["skills"], in_use, entry["elsewhere"]),
                locations=entry["locations"],
            )
        )
    statuses = [skill.status for skill in skills]
    return SkillEvidence(
        demonstrated=statuses.count("demonstrated"),
        listed_only=statuses.count("listed_only"),
        mentioned=statuses.count("mentioned"),
        listed_only_skills=[s.skill for s in skills if s.status == "listed_only"],
        skills=skills,
    )
