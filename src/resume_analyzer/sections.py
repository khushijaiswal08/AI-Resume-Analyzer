"""Detect which standard resume sections are present, based on heading lines."""

import re
from dataclasses import dataclass

# Canonical section name -> headings that mean the same thing.
SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": (
        "summary",
        "professional summary",
        "profile",
        "professional profile",
        "objective",
        "career objective",
        "about me",
    ),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "work history",
        "internships",
        "internship experience",
    ),
    "education": ("education", "academic background", "academics", "educational qualifications"),
    "skills": (
        "skills",
        "technical skills",
        "key skills",
        "core competencies",
        "skills and tools",
        "skills & tools",
    ),
    "projects": ("projects", "personal projects", "academic projects", "key projects"),
    "certifications": (
        "certifications",
        "certificates",
        "licenses and certifications",
        "licenses & certifications",
        "courses and certifications",
    ),
}

SECTION_ORDER = list(SECTION_ALIASES)

# Headings are short; anything longer is a sentence that merely mentions a word like "skills".
MAX_HEADING_WORDS = 5

_HEADING_LOOKUP = {alias: name for name, aliases in SECTION_ALIASES.items() for alias in aliases}


_LEADING_DECORATION = re.compile(r"[\s#*=_\-|•–—]*")
_LEADING_DECORATION_REVERSED = re.compile(r"[\s:#*=_\-|•–—]*")  # applied to the reversed line


def _clean_heading(line: str) -> str:
    # Strip decoration such as "## ", "SKILLS:", "--- Projects ---", "Experience —".
    # Two anchored scans, one per end. The old single pattern with an "|" and a "$" alternative
    # re-scanned a long run of spaces or dashes from every start position (quadratic: about 15 s
    # for one 50,000-character line, and the whole server stalls while it runs).
    line = line[_LEADING_DECORATION.match(line).end() :]
    line = line[: len(line) - _LEADING_DECORATION_REVERSED.match(line[::-1]).end()]
    return re.sub(r"\s+", " ", line).lower()


def _heading_candidates(line: str) -> list[str]:
    """Possible headings on one line, already cleaned.

    Besides the whole line, this covers inline headings ("Skills: Python, SQL" -> "skills")
    and combined ones ("Work Experience & Internships" -> "work experience", "internships").
    """
    heading = _clean_heading(line)
    candidates = [heading]
    if ":" in line:
        candidates.append(_clean_heading(line.split(":", 1)[0]))
    # Only short candidates can be headings; split those, never a whole sentence.
    candidates = [c for c in candidates if c and len(c.split()) <= MAX_HEADING_WORDS]
    for candidate in list(candidates):
        candidates.extend(part.strip() for part in re.split(r"\s*&\s*|\s+and\s+", candidate))
    return candidates


def detect_sections(text: str) -> list[str]:
    """Return canonical section names found in `text`, in a fixed order."""
    found: set[str] = set()
    for line in text.splitlines():
        for heading in _heading_candidates(line):
            name = _HEADING_LOOKUP.get(heading)
            if name:
                found.add(name)
    return [name for name in SECTION_ORDER if name in found]


@dataclass(frozen=True)
class Line:
    """One non-blank line of the resume with its position in the original text."""

    start: int  # offset of the first non-space character
    end: int  # offset just after the last non-space character
    text: str  # the stripped line
    section: str | None  # canonical section the line belongs to (None before any heading)
    is_heading: bool


def split_lines(text: str) -> list[Line]:
    """Split `text` into non-blank lines, each tagged with the section it sits in.

    Offsets index into `text`, so the UI can highlight `text[start:end]`. A line such as
    "Skills: Python, SQL" is both a heading and content of the skills section; it is tagged
    with that section and `is_heading=True`.
    """
    lines: list[Line] = []
    current: str | None = None
    position = 0
    for raw in text.splitlines(keepends=True):
        stripped = raw.strip()
        if stripped:
            start = position + (len(raw) - len(raw.lstrip()))
            names = [
                _HEADING_LOOKUP[c] for c in _heading_candidates(stripped) if c in _HEADING_LOOKUP
            ]
            if names:
                current = names[0]
            lines.append(Line(start, start + len(stripped), stripped, current, bool(names)))
        position += len(raw)
    return lines
