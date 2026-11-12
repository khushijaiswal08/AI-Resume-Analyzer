"""Layer 1: score every experience/project bullet from 0 to 100.

Each bullet earns points for the habits recruiters look for. The points add up to 100:
strong action verb 25, a measurable result 25, length 20, no weak phrases 10, no buzzwords 10,
no first person 5, consistent tense 5. Nothing here calls an LLM, and the improvement
`hint` is a template to follow, never a rewrite with invented facts.
"""

import re

from resume_analyzer.dates import has_date_range
from resume_analyzer.schemas import BulletItem, BulletReport, Issue
from resume_analyzer.scoring import ACTION_VERBS, first_word, is_quantified_line
from resume_analyzer.sections import Line
from resume_analyzer.wordbanks import (
    BUZZ_RE,
    FIRST_PERSON_RE,
    PAST_EXTRA,
    PRESENT_FORMS,
    WEAK_RE,
)

BULLET_SECTIONS = ("experience", "projects")
IDEAL_WORDS = (12, 28)
_GLYPH = re.compile(r"^[-*•·●▪◦▸►➤✓✔>–—]+\s+")
MIN_PLAIN_LINE_WORDS = 5  # a line without a bullet glyph must look like a sentence


def extract_bullets(lines: list[Line]) -> list[tuple[Line, int, str]]:
    """Find bullet lines in experience/projects: (line, text start offset, bullet text).

    A line is a bullet if it starts with a bullet glyph, or is a sentence-like line that is
    not a heading and not a "Role, Company (2021 - 2024)" header (those contain a date range).
    """
    found = []
    for line in lines:
        if line.section not in BULLET_SECTIONS or line.is_heading:
            continue
        glyph = _GLYPH.match(line.text)
        body = line.text[glyph.end() :] if glyph else line.text
        if not glyph and (has_date_range(line.text) or len(body.split()) < MIN_PLAIN_LINE_WORDS):
            continue
        if body:
            found.append((line, line.start + (len(line.text) - len(body)), body))
    return found


def tense_of(text: str) -> str | None:
    """'past' or 'present' from the first word of a bullet, None if it cannot tell."""
    word = first_word(text)
    if word in PRESENT_FORMS:
        return "present"
    if word in ACTION_VERBS or word in PAST_EXTRA or (word.endswith("ed") and len(word) > 3):
        return "past"
    return None


def _length_points(words: int) -> int:
    low, high = IDEAL_WORDS
    if low <= words <= high:
        return 20
    if low - 4 <= words < low or high < words <= high + 7:
        return 12
    if 5 <= words < low - 4:
        return 6
    return 0


def _issues(text: str, words: int, minority_tense: bool) -> tuple[list[Issue], int]:
    """Return the issues found in one bullet and its score."""
    issues: list[Issue] = []
    score = 0
    word = first_word(text)
    weak = WEAK_RE.search(text)
    weak_start = bool(weak and weak.start() == 0)

    if word in ACTION_VERBS:
        score += 25
    elif word.endswith("ed") and not weak_start:
        score += 15  # a past-tense verb, just not on our "strong verbs" list
    else:
        issues.append(Issue(code="no_action_verb", message="Does not start with an action verb."))
    if is_quantified_line(text):
        score += 25
    else:
        issues.append(Issue(code="no_metric", message="No measurable result (number or %)."))

    score += _length_points(words)
    if words < IDEAL_WORDS[0]:
        issues.append(Issue(code="too_short", message=f"Only {words} words; aim for 12-28."))
    elif words > IDEAL_WORDS[1]:
        issues.append(Issue(code="too_long", message=f"{words} words; aim for 12-28."))

    for code, regex, label, points in (
        ("weak_phrase", WEAK_RE, "Weak phrase", 10),
        ("buzzword", BUZZ_RE, "Buzzword", 10),
        ("first_person", FIRST_PERSON_RE, "First-person pronoun", 5),
    ):
        hit = regex.search(text)
        if hit:
            issues.append(Issue(code=code, message=f'{label}: "{hit.group().lower()}".'))
        else:
            score += points
    if minority_tense:
        issues.append(
            Issue(code="tense_mismatch", message="Tense differs from your other bullets.")
        )
    else:
        score += 5
    return issues, score


def _hint(issues: list[Issue]) -> str | None:
    """A template for the two most important fixes. Never contains invented numbers."""
    codes = {issue.code for issue in issues}
    parts = []
    if "weak_phrase" in codes or "no_action_verb" in codes:
        parts.append("Start with a strong verb (Built, Automated, Reduced) and name what you did.")
    if "no_metric" in codes:
        parts.append("Add a result using your real numbers: 'Reduced X by N%'.")
    if "too_long" in codes:
        parts.append("Cut to one idea or split into two bullets.")
    if "too_short" in codes:
        parts.append("Say how and with what, then the outcome.")
    if "buzzword" in codes:
        parts.append("Replace the buzzword with a concrete example.")
    if "first_person" in codes:
        parts.append("Drop 'I/my'; begin with the verb.")
    if "tense_mismatch" in codes:
        parts.append("Use past tense for finished work.")
    return " ".join(parts[:2]) or None


def rating_for(score: int) -> str:
    """strong >= 75, ok >= 50, otherwise weak."""
    return "strong" if score >= 75 else "ok" if score >= 50 else "weak"


def analyze_bullets(lines: list[Line]) -> BulletReport:
    """Score all bullets. Tense is judged across bullets: the minority tense is flagged."""
    found = extract_bullets(lines)
    tenses = [tense_of(body) for _, _, body in found]
    past, present = tenses.count("past"), tenses.count("present")
    minority = None
    if past and present:
        minority = "present" if present <= past else "past"

    items = []
    for (line, start, body), tense in zip(found, tenses, strict=True):
        words = len(body.split())
        issues, score = _issues(body, words, minority is not None and tense == minority)
        items.append(
            BulletItem(
                text=body,
                start=start,
                end=line.end,
                section=line.section or "",
                score=score,
                rating=rating_for(score),
                word_count=words,
                issues=issues,
                hint=_hint(issues),
            )
        )
    average = round(sum(item.score for item in items) / len(items)) if items else None
    ratings = [item.rating for item in items]
    return BulletReport(
        count=len(items),
        average_score=average,
        strong=ratings.count("strong"),
        ok=ratings.count("ok"),
        weak=ratings.count("weak"),
        items=items,
    )
