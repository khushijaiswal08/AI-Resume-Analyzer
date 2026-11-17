"""Layer 3: job-description intelligence.

Goes beyond "which skills appear in the JD":
- required vs preferred, from headings ("Nice to have") and phrases ("is a plus", "must");
- required skills weigh 2, preferred 1;
- "X or Y" alternatives count once and are satisfied by either;
- years-of-experience asks and a seniority cue;
- per-skill status with a hint on where in the resume to show it.

Everything is rule-based. The rules are deliberately simple and listed at the top so they can
be read and argued with. They will not understand every JD, and the notes say when they are unsure.
"""

import re
from bisect import bisect_right
from dataclasses import dataclass

from resume_analyzer.schemas import JDAnalysis, JDRequirement, SkillEvidence, YearsAsk
from resume_analyzer.skills import SkillMention, find_skill_mentions

REQUIRED_WEIGHT, PREFERRED_WEIGHT = 2, 1

# A line that sets the priority for the lines below it ("Requirements", "Nice to have: ...").
REQUIRED_HEADINGS = (
    "requirements",
    "required",
    "required skills",
    "must have",
    "must haves",
    "qualifications",
    "minimum qualifications",
    "basic qualifications",
    "what you need",
    "what we are looking for",
    "what we're looking for",
    "you have",
    "essential",
)
PREFERRED_HEADINGS = (
    "nice to have",
    "nice to haves",
    "preferred",
    "preferred qualifications",
    "preferred skills",
    "bonus",
    "bonus points",
    "good to have",
    "desirable",
    "a plus",
    "plus",
)
NEUTRAL_HEADINGS = (
    "responsibilities",
    "about us",
    "about the role",
    "benefits",
    "what you will do",
)

# Phrases inside one clause that decide its priority, whatever the heading says.
PREFERRED_CUE = re.compile(
    r"\b(?:nice[- ]to[- ]have|bonus|preferred|good to have|desirable|(?:is|are) an? plus|"
    r"a plus|ideally|familiarity with|exposure to)\b",
    re.IGNORECASE,
)
REQUIRED_CUE = re.compile(
    r"\b(?:must|required|requirement|essential|strong|proven|proficien\w+|need|needs)\b",
    re.IGNORECASE,
)

YEARS_RE = re.compile(
    r"(?P<n>\d{1,2})\s*(?:\+|\s*(?:-|to)\s*\d{1,2})?\s*(?:years?|yrs?)\b(?!\s*(?:ago|old))",
    re.IGNORECASE,
)
# Title cues first: "Senior ML Engineer". Body cues only for unambiguous phrases.
TITLE_SENIORITY = (
    ("lead", re.compile(r"\b(?:lead|principal|staff|head of|architect)\b", re.IGNORECASE)),
    ("senior", re.compile(r"\b(?:senior|sr\.?)(?=\W)", re.IGNORECASE)),
    (
        "entry",
        re.compile(r"\b(?:junior|jr\.?|intern|trainee|graduate|fresher|entry[- ]level)\b", re.I),
    ),
    ("mid", re.compile(r"\bmid[- ]?level\b", re.IGNORECASE)),
)
BODY_ENTRY = re.compile(r"\b(?:entry[- ]level|freshers?|new grad(?:uate)?s?)\b", re.IGNORECASE)

# Link between two consecutive skill mentions. "or"-type links make alternatives.
# Matched against the link with its outer whitespace already stripped: the old pattern had two
# adjacent "\s*" runs, which is quadratic on a long gap between two skill mentions.
_OR_LINK = re.compile(r"^(?:,\s*)?(?:or|/|\|)$|^,?\s*and/or$", re.IGNORECASE)
_OR_WORD = re.compile(r"\bor\b", re.IGNORECASE)  # the word "or", unlike "/"
_COMMA_LINK = re.compile(r"^\s*,\s*$")
_CLAUSE_END = re.compile(r"[;.](?:\s|$)")

SECTION_BY_CATEGORY = {
    "soft": ["Summary", "Experience"],
}
DEFAULT_PLACES = ["Skills", "Projects", "Experience"]


@dataclass
class _Ask:
    """A skill mention in the JD, with the priority of the clause it sits in."""

    mention: SkillMention
    priority: str  # "required" | "preferred"


def _norm_heading(text: str) -> str:
    return re.sub(r"[^a-z' ]+", " ", text.lower()).strip()


def _heading_state(line: str) -> tuple[bool, str | None]:
    """(is this line a heading?, priority it sets: 'required' | 'preferred' | None).

    "Nice to have: Docker" is a heading *and* content, so the part before ':' is tested too.
    """
    candidates = [_norm_heading(line)]
    if ":" in line:
        candidates.append(_norm_heading(line.split(":", 1)[0]))
    for candidate in candidates:
        if len(candidate.split()) > 6:
            continue
        if candidate in REQUIRED_HEADINGS:
            return True, "required"
        if candidate in PREFERRED_HEADINGS:
            return True, "preferred"
        if candidate in NEUTRAL_HEADINGS:
            return True, None
    return False, None


def _clause_priority(clause: str, section_priority: str | None) -> str:
    """Phrase cues beat headings; a preferred cue beats a required one in the same clause."""
    if PREFERRED_CUE.search(clause):
        return "preferred"
    if REQUIRED_CUE.search(clause):
        return "required"
    return section_priority or "required"  # unlabelled skills are treated as required


def _collect_asks(jd_text: str) -> list[_Ask]:
    """Find every skill mention in the JD and decide whether it is required or preferred."""
    mentions = find_skill_mentions(jd_text)  # sorted by start
    asks: list[_Ask] = []
    next_mention = 0  # mentions are in text order, so one forward pass covers all lines
    position = 0
    section: str | None = None
    for raw in jd_text.splitlines(keepends=True):
        line_start, position = position, position + len(raw)
        line = raw.strip()
        if not line:
            continue
        is_heading, state = _heading_state(line)
        if is_heading:
            section = state
        while next_mention < len(mentions) and mentions[next_mention].start < line_start:
            next_mention += 1  # mention inside skipped (blank) text
        first = next_mention
        while next_mention < len(mentions) and mentions[next_mention].start < position:
            next_mention += 1
        line_mentions = mentions[first:next_mention]
        if not line_mentions:
            # A short unknown heading ("Tech stack") resets the section.
            if not is_heading and len(line.split()) <= 4 and not line.endswith("."):
                section = None
            continue
        # Split the line into clauses so "Python is a must; Docker is a plus" gets two priorities.
        bounds = [line_start] + [line_start + m.end() for m in _CLAUSE_END.finditer(raw)]
        bounds.append(position)
        priorities: dict[int, str] = {}  # one cue search per clause, not one per mention
        for mention in line_mentions:
            # The clause is the last boundary at or before the mention (binary search).
            index = bisect_right(bounds, mention.start, 0, len(bounds) - 1) - 1
            if index not in priorities:
                clause = jd_text[bounds[index] : bounds[index + 1]]
                priorities[index] = _clause_priority(clause, section)
            asks.append(_Ask(mention, priorities[index]))
    return asks


def _alternative_groups(asks: list[_Ask], jd_text: str) -> list[list[str]]:
    """Groups of skills joined by "or" or "/" ("PyTorch or TensorFlow", "AWS, Azure or GCP").

    Only adjacent mentions are linked. A comma list is absorbed when it ends with "or"; a "/"
    links just its two neighbours (so "Docker/Kubernetes" does not swallow a preceding list).
    """
    groups: list[list[str]] = []
    comma_run: list[str] = []  # consecutive mentions joined only by commas
    for previous, ask in zip([None, *asks], asks, strict=False):  # (previous, current)
        name = ask.mention.name
        link = "" if previous is None else jd_text[previous.mention.end : ask.mention.start]
        if previous is not None and _OR_LINK.match(link.strip()):
            absorb = comma_run if _OR_WORD.search(link) else [previous.mention.name]
            linked = {*absorb, name}
            # Merge with any group that shares a skill, so groups never overlap.
            for group in [g for g in groups if linked & set(g)]:
                groups.remove(group)
                linked |= set(group)
            groups.append(sorted(linked, key=lambda n: _first_position(n, asks)))
            comma_run = [name]
        elif previous is not None and _COMMA_LINK.match(link):
            comma_run.append(name)
        else:
            comma_run = [name]
    return [group for group in groups if len(group) > 1]


def _first_position(name: str, asks: list[_Ask]) -> int:
    return next(ask.mention.start for ask in asks if ask.mention.name == name)


def _snippet(text: str, start: int, end: int, before: int = 10, after: int = 25) -> str:
    """A little context around text[start:end]: widened to whole words, never past the line."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    line_end = len(text) if line_end == -1 else line_end
    lo, hi = max(line_start, start - before), min(line_end, end + after)
    while lo > line_start and not text[lo - 1].isspace():
        lo -= 1  # a cut inside a word: take the whole word
    while hi < line_end and not text[hi].isspace():
        hi += 1
    return " ".join(text[lo:hi].split())


def find_years(jd_text: str) -> list[YearsAsk]:
    """Every "N years" / "N+ years" / "3-5 years" phrase, with a little surrounding text."""
    asks = []
    for match in YEARS_RE.finditer(jd_text):
        years = int(match["n"])
        if years > 40:
            continue
        asks.append(YearsAsk(years=years, text=_snippet(jd_text, match.start(), match.end())))
    return asks


def detect_seniority(jd_text: str, years_required: int | None) -> str | None:
    """'entry' | 'mid' | 'senior' | 'lead' from the title line, else from the years asked."""
    first_line = next((line for line in jd_text.splitlines() if line.strip()), "")
    for level, pattern in TITLE_SENIORITY:
        if pattern.search(first_line):
            return level
    if BODY_ENTRY.search(jd_text):
        return "entry"
    if years_required is None:
        return None
    return "entry" if years_required <= 2 else "mid" if years_required <= 5 else "senior"


def _where_to_add(category: str, status: str, demonstrated: bool | None) -> list[str]:
    """Resume sections where the skill should appear. Empty when nothing needs to change."""
    if status == "missing":
        return SECTION_BY_CATEGORY.get(category, DEFAULT_PLACES)
    if status == "matched" and demonstrated is False:
        return ["Experience", "Projects"]  # only listed so far: show it being used
    return []


def _hint(
    skill: str, status: str, demonstrated: bool | None, alternatives: list[str]
) -> str | None:
    if status == "covered_by_alternative":
        return f"The JD accepts {' or '.join(alternatives)}; your resume already covers it."
    if status == "missing":
        return (
            f"Not found. If you have really used {skill}, list it under Skills and show it in a "
            "project or job bullet. If not, treat it as something to learn."
        )
    if demonstrated is False:
        return f"{skill} is only listed. Add a bullet that shows how you used it."
    return None


def analyze_jd(
    jd_text: str,
    evidence: SkillEvidence,
    resume_years: float | None,
) -> JDAnalysis:
    """Build the weighted JD analysis. `evidence` tells which resume skills are demonstrated."""
    asks = _collect_asks(jd_text)
    years = find_years(jd_text)
    years_required = max((ask.years for ask in years), default=None)
    seniority = detect_seniority(jd_text, years_required)

    # One entry per skill; "required" wins if the skill is mentioned both ways.
    by_skill: dict[str, _Ask] = {}
    for ask in asks:
        known = by_skill.get(ask.mention.name)
        if known is None or (known.priority == "preferred" and ask.priority == "required"):
            by_skill[ask.mention.name] = ask
    groups = _alternative_groups(asks, jd_text)
    group_of = {name: group for group in groups for name in group}
    resume = {use.skill: use for use in evidence.skills}

    requirements: list[JDRequirement] = []
    for name, ask in by_skill.items():
        group = group_of.get(name, [name])
        alternatives = [other for other in group if other != name]
        priority = (
            "required" if any(by_skill[m].priority == "required" for m in group) else ("preferred")
        )
        if name in resume:
            status, use = "matched", resume[name]
            demonstrated: bool | None = use.status == "demonstrated"
        elif any(other in resume for other in alternatives):
            status, demonstrated = "covered_by_alternative", None
        else:
            status, demonstrated = "missing", None
        requirements.append(
            JDRequirement(
                skill=name,
                category=ask.mention.category,
                priority=priority,
                weight=REQUIRED_WEIGHT if priority == "required" else PREFERRED_WEIGHT,
                status=status,
                demonstrated=demonstrated,
                alternatives=alternatives,
                where_to_add=_where_to_add(ask.mention.category, status, demonstrated),
                hint=_hint(name, status, demonstrated, alternatives),
            )
        )
    requirements.sort(key=lambda r: r.priority != "required")  # stable: text order inside each lane

    def percent(priority: str | None) -> int | None:
        """Weighted share met. An alternatives group is one unit and counts once."""
        total = achieved = 0
        seen: set[str] = set()
        for req in requirements:
            if priority and req.priority != priority:
                continue
            members = frozenset([req.skill, *req.alternatives])
            key = ",".join(sorted(members))
            if key in seen:
                continue
            seen.add(key)
            total += req.weight
            if any(other.skill in members and other.status != "missing" for other in requirements):
                achieved += req.weight
        return round(100 * achieved / total) if total else None

    required_count = sum(r.priority == "required" for r in requirements)
    notes = _notes(requirements, years_required, resume_years, seniority)
    return JDAnalysis(
        weighted_percent=percent(None),
        required_percent=percent("required"),
        preferred_percent=percent("preferred"),
        required_count=required_count,
        preferred_count=len(requirements) - required_count,
        requirements=requirements,
        years_asked=years,
        years_required=years_required,
        resume_years_estimate=resume_years,
        seniority=seniority,
        notes=notes,
    )


def _notes(
    requirements: list[JDRequirement],
    years_required: int | None,
    resume_years: float | None,
    seniority: str | None,
) -> list[str]:
    notes = []
    if not requirements:
        notes.append(
            "No recognised skills were found in the job description, so nothing was scored."
        )
    if (
        years_required is not None
        and resume_years is not None
        and resume_years + 0.5 < years_required
    ):
        notes.append(
            f"The JD asks for {years_required}+ years; your dated experience adds up to about "
            f"{resume_years:g}. This is an estimate from the date ranges in your Experience "
            "section."
        )
    elif years_required is not None and resume_years is None:
        notes.append(
            f"The JD asks for {years_required}+ years, but no date ranges were found in your "
            "Experience section to compare against."
        )
    if seniority in ("senior", "lead") and years_required is None:
        notes.append(f"The JD reads as {seniority}-level; check you show ownership and impact.")
    return notes
