"""Detect which standard resume sections are present, based on heading lines."""

import re

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


def _clean_heading(line: str) -> str:
    # Strip decoration such as "## ", "SKILLS:", "--- Projects ---", "Experience —".
    line = re.sub(r"^[\s#*=_\-|•–—]+|[\s:#*=_\-|•–—]+$", "", line)
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
