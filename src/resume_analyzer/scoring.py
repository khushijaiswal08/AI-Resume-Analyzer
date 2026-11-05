"""Deterministic, explainable ATS-style score (0-100).

This is a transparent heuristic written for this project. It is NOT the algorithm of any
real applicant-tracking-system vendor. Every point awarded comes with a reason, and the
LLM never influences the score.
"""

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from resume_analyzer.models import ATSScore, CriterionScore, JDMatch, RedactionCounts

# Base weights (sum to 100). Without a JD, "jd_coverage" is dropped and the remaining
# weights are scaled up proportionally so the total is still out of 100.
WEIGHTS: dict[str, int] = {
    "sections": 25,
    "skills": 20,
    "quantified_achievements": 15,
    "action_verbs": 15,
    "length": 10,
    "contact_info": 5,
    "jd_coverage": 10,
}

# Points inside the "sections" criterion: core sections matter most.
SECTION_POINTS = {
    "experience": 6,
    "education": 6,
    "skills": 6,
    "summary": 3,
    "projects": 2,
    "certifications": 2,
}

SKILLS_FOR_FULL_MARKS = 15
QUANTIFIED_LINES_FOR_FULL_MARKS = 5
ACTION_VERB_LINES_FOR_FULL_MARKS = 8
IDEAL_WORDS = (300, 1000)

# A whitespace-separated block is easier to read and extend than a long list literal.
ACTION_VERBS = frozenset(
    """
    achieved analyzed analysed architected automated boosted built cleaned collaborated
    configured contributed coordinated created cut debugged decreased delivered deployed
    designed developed directed drove enhanced established evaluated executed expanded
    fine-tuned generated grew implemented improved increased integrated introduced launched
    led maintained managed mentored migrated modernized monitored optimized optimised
    orchestrated organized owned pioneered planned presented produced prototyped published
    raised rebuilt reduced refactored resolved restructured saved scaled set shipped
    simplified spearheaded streamlined supervised taught tested trained transformed tuned
    upgraded wrote
    """.split()
)

_BULLET_PREFIX = re.compile(r"^[\s\-*•·●▪◦>]+")
_YEAR = re.compile(r"^(19|20)\d{2}$")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass
class _Result:
    """Fraction of the criterion achieved (0..1) and why."""

    fraction: float
    reason: str


def allocate_weights(include_jd: bool) -> dict[str, int]:
    """Return integer weights that always sum to 100.

    Without a JD, the JD weight is redistributed proportionally using the largest-remainder
    method, so integer rounding never makes the total 99 or 101.
    """
    if include_jd:
        return dict(WEIGHTS)
    base = {name: weight for name, weight in WEIGHTS.items() if name != "jd_coverage"}
    scale = 100 / sum(base.values())
    exact = {name: weight * scale for name, weight in base.items()}
    allocated = {name: math.floor(value) for name, value in exact.items()}
    leftover = 100 - sum(allocated.values())
    by_remainder = sorted(exact, key=lambda name: exact[name] - allocated[name], reverse=True)
    for name in by_remainder[:leftover]:
        allocated[name] += 1
    return allocated


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _score_sections(sections: list[str]) -> _Result:
    earned = sum(SECTION_POINTS.get(name, 0) for name in sections)
    missing = [name for name in SECTION_POINTS if name not in sections]
    reason = f"Found {len(sections)}/{len(SECTION_POINTS)} standard sections"
    reason += f"; missing: {', '.join(missing)}." if missing else "."
    return _Result(earned / sum(SECTION_POINTS.values()), reason)


def _score_skills(skill_count: int) -> _Result:
    reason = (
        f"{skill_count} recognised skills found (full marks at {SKILLS_FOR_FULL_MARKS} or more)."
    )
    return _Result(min(1.0, skill_count / SKILLS_FOR_FULL_MARKS), reason)


def count_quantified_lines(text: str) -> int:
    """Count lines with a number that is not just a year (e.g. "cut costs by 30%")."""
    count = 0
    for line in _lines(text):
        numbers = _NUMBER.findall(line)
        if any(not _YEAR.match(number) for number in numbers):
            count += 1
    return count


def _score_quantified(text: str) -> _Result:
    count = count_quantified_lines(text)
    reason = (
        f"{count} lines contain measurable results such as numbers or percentages "
        f"(full marks at {QUANTIFIED_LINES_FOR_FULL_MARKS})."
    )
    return _Result(min(1.0, count / QUANTIFIED_LINES_FOR_FULL_MARKS), reason)


def count_action_verb_lines(text: str) -> int:
    """Count lines (bullets included) that start with a strong action verb."""
    count = 0
    for line in _lines(text):
        words = _BULLET_PREFIX.sub("", line).split()
        if words and words[0].lower().strip(",.:;") in ACTION_VERBS:
            count += 1
    return count


def _score_action_verbs(text: str) -> _Result:
    count = count_action_verb_lines(text)
    reason = (
        f"{count} lines start with an action verb like 'Built' or 'Improved' "
        f"(full marks at {ACTION_VERB_LINES_FOR_FULL_MARKS})."
    )
    return _Result(min(1.0, count / ACTION_VERB_LINES_FOR_FULL_MARKS), reason)


def _score_length(word_count: int) -> _Result:
    low, high = IDEAL_WORDS
    if low <= word_count <= high:
        return _Result(1.0, f"{word_count} words is within the ideal {low}-{high} range.")
    if word_count < low:
        return _Result(word_count / low, f"{word_count} words is short; aim for {low}-{high}.")
    # Too long: lose credit gradually, reaching zero at twice the upper bound.
    fraction = max(0.0, 1 - (word_count - high) / high)
    return _Result(fraction, f"{word_count} words is long; aim for {low}-{high}.")


def _score_contact(redaction: RedactionCounts) -> _Result:
    has_email = redaction.emails > 0
    has_phone = redaction.phones > 0
    if has_email and has_phone:
        return _Result(1.0, "Email and phone number present.")
    if has_email or has_phone:
        found = "email" if has_email else "phone number"
        return _Result(0.6, f"Only {found} found; include both email and phone.")
    return _Result(0.0, "No email or phone number found.")


def _score_jd(jd_match: JDMatch) -> _Result:
    reason = (
        f"Resume mentions {len(jd_match.matched)} of "
        f"{len(jd_match.matched) + len(jd_match.missing)} skills from the job description."
    )
    return _Result(jd_match.match_percent / 100, reason)


LABELS = {
    "sections": "Sections present",
    "skills": "Skills found",
    "quantified_achievements": "Quantified achievements",
    "action_verbs": "Action verbs",
    "length": "Length",
    "contact_info": "Contact info",
    "jd_coverage": "JD keyword coverage",
}


def score_resume(
    *,
    text: str,
    sections: list[str],
    skill_count: int,
    word_count: int,
    redaction: RedactionCounts,
    jd_match: JDMatch | None,
) -> ATSScore:
    """Compute the weighted score. `text` should be the redacted resume text."""
    weights = allocate_weights(include_jd=jd_match is not None)
    scorers: dict[str, Callable[[], _Result]] = {
        "sections": lambda: _score_sections(sections),
        "skills": lambda: _score_skills(skill_count),
        "quantified_achievements": lambda: _score_quantified(text),
        "action_verbs": lambda: _score_action_verbs(text),
        "length": lambda: _score_length(word_count),
        "contact_info": lambda: _score_contact(redaction),
    }
    if jd_match is not None:
        scorers["jd_coverage"] = lambda: _score_jd(jd_match)

    breakdown = []
    for name, scorer in scorers.items():
        result = scorer()
        max_points = weights[name]
        breakdown.append(
            CriterionScore(
                criterion=LABELS[name],
                score=round(result.fraction * max_points),
                max=max_points,
                reason=result.reason,
            )
        )
    return ATSScore(total=sum(item.score for item in breakdown), breakdown=breakdown)
