"""Layer 5: evidence for every ATS score criterion.

For each criterion in `ats_score.breakdown` this returns the lines that earned or lost points,
with character offsets into the resume text, so the UI can highlight them. The scoring itself
stays in scoring.py; this module only *explains* it, and uses the same helper functions so the
evidence cannot disagree with the score.
"""

from resume_analyzer.bullets import extract_bullets
from resume_analyzer.models import ATSScore, JDMatch
from resume_analyzer.redaction import EMAIL_RE, PHONE_RE, redact
from resume_analyzer.schemas import CriterionEvidence, EvidenceItem
from resume_analyzer.scoring import (
    IDEAL_WORDS,
    LABELS,
    SKILLS_FOR_FULL_MARKS,
    is_quantified_line,
    starts_with_action_verb,
)
from resume_analyzer.sections import Line
from resume_analyzer.skills import SkillMention

MAX_SNIPPET_CHARS = 160
MAX_PER_KIND = 25
_ID_BY_LABEL = {label: criterion_id for criterion_id, label in LABELS.items()}


def _item(start: int, end: int, text: str, kind: str, note: str | None = None) -> EvidenceItem:
    """An evidence item. Long lines are cut so that `text == resume_text[start:end]` still holds."""
    end = min(end, start + MAX_SNIPPET_CHARS)
    return EvidenceItem(start=start, end=end, text=text[: end - start], kind=kind, note=note)


def _line_item(line: Line, kind: str, note: str | None = None) -> EvidenceItem:
    return _item(line.start, line.end, line.text, kind, note)


def _sections(lines: list[Line], sections: list[str]) -> tuple[list[EvidenceItem], list[str]]:
    first_heading: dict[str, Line] = {}
    for line in lines:
        if line.is_heading and line.section and line.section not in first_heading:
            first_heading[line.section] = line
    earned = [
        _line_item(line, "earned", f"{name} section found")
        for name, line in first_heading.items()
        if name in sections
    ]
    return earned, [
        name
        for name in ("experience", "education", "skills", "summary", "projects", "certifications")
        if name not in sections
    ]


def _skills(text: str, mentions: list[SkillMention]) -> tuple[list[EvidenceItem], list[str]]:
    seen: set[str] = set()
    earned = []
    for mention in mentions:  # first mention of each distinct skill
        if mention.name not in seen:
            seen.add(mention.name)
            earned.append(_item(mention.start, mention.end, text[mention.start : mention.end],
                                "earned", mention.name))  # fmt: skip
    missing = []
    if len(seen) < SKILLS_FOR_FULL_MARKS:
        missing.append(f"{SKILLS_FOR_FULL_MARKS - len(seen)} more recognised skills for full marks")
    return earned, missing


def _quantified(
    lines: list[Line],
) -> tuple[list[EvidenceItem], list[str], list[EvidenceItem]]:
    earned = [
        _line_item(line, "earned", "contains a measurable number")
        for line in lines
        if is_quantified_line(
            redact(line.text)[0]
        )  # score uses redacted text: phones are not metrics
    ]
    lost = [
        _item(start, line.end, body, "lost", "no number or % in this bullet")
        for line, start, body in extract_bullets(lines)
        if not is_quantified_line(body)
    ]
    return earned, [] if earned else ["no line with a measurable result"], lost


def _verbs(lines: list[Line]) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
    earned = [
        _line_item(line, "earned", "starts with an action verb")
        for line in lines
        if starts_with_action_verb(line.text)
    ]
    lost = [
        _item(start, line.end, body, "lost", "does not start with a strong verb")
        for line, start, body in extract_bullets(lines)
        if not starts_with_action_verb(body)
    ]
    return earned, lost


def _contact(text: str) -> tuple[list[EvidenceItem], list[str]]:
    earned, missing = [], []
    for label, regex in (("email", EMAIL_RE), ("phone number", PHONE_RE)):
        match = regex.search(text)
        if match:
            earned.append(_item(match.start(), match.end(), match.group(), "earned", label))
        else:
            missing.append(label)
    return earned, missing


def _jd(
    text: str, mentions: list[SkillMention], jd_match: JDMatch
) -> tuple[list[EvidenceItem], list[str]]:
    matched = {skill.lower() for skill in jd_match.matched}
    seen: set[str] = set()
    earned = []
    for mention in mentions:
        if mention.name.lower() in matched and mention.name not in seen:
            seen.add(mention.name)
            earned.append(_item(mention.start, mention.end, text[mention.start : mention.end],
                                "earned", f"{mention.name} is asked for in the JD"))  # fmt: skip
    return earned, list(jd_match.missing)


def build_evidence(
    *,
    text: str,
    lines: list[Line],
    sections: list[str],
    mentions: list[SkillMention],
    ats_score: ATSScore,
    jd_match: JDMatch | None,
) -> list[CriterionEvidence]:
    """One `CriterionEvidence` per entry of `ats_score.breakdown`, in the same order."""
    low, high = IDEAL_WORDS
    words = len(text.split())
    builders = {
        "sections": lambda: (*_sections(lines, sections), []),
        "skills": lambda: (*_skills(text, mentions), []),
        "quantified_achievements": lambda: _quantified(lines),
        "action_verbs": lambda: (_verbs(lines)[0], [], _verbs(lines)[1]),
        "length": lambda: (
            [],
            [] if low <= words <= high else [f"{words} words; ideal is {low}-{high}"],
            [],
        ),
        "contact_info": lambda: (*_contact(text), []),
    }
    result = []
    for criterion in ats_score.breakdown:
        criterion_id = _ID_BY_LABEL[criterion.criterion]
        if criterion_id == "jd_coverage":
            earned, missing = _jd(text, mentions, jd_match) if jd_match else ([], [])
            lost: list[EvidenceItem] = []
        else:
            earned, missing, lost = builders[criterion_id]()
        result.append(
            CriterionEvidence(
                id=criterion_id,
                criterion=criterion.criterion,
                snippets=[*earned[:MAX_PER_KIND], *lost[:MAX_PER_KIND]],
                missing=missing,
            )
        )
    return result
