"""Skill extraction by matching text against a curated taxonomy (data/skills.json).

Why a taxonomy and not an LLM? It is deterministic, explainable, free, testable, and it
works without an API key. The trade-off: it only finds skills that are in the list.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from resume_analyzer.redaction import EMAIL_RE, URL_RE

# A skill must not be glued to other "word" characters. `+` and `#` count as word characters
# so "C" never matches inside "C++"; `&` stops "R" matching in "R&D". A following ".x" is
# rejected so "Node" would not match "Node.js", while a sentence-ending "Python." still matches.
_BEFORE = r"(?<![\w+#&])"
_AFTER = r"(?![\w+#&]|\.\w)"
# Short cased terms (Go, R) also start common hyphenated English phrases such as
# "Go-to-market" or "R-squared"; those are not skill mentions.
_CASED_AFTER = r"(?![\w+#&]|\.\w|-to-|-squared)"


@dataclass(frozen=True)
class Skill:
    """A canonical skill name, its category and the compiled patterns that detect it."""

    name: str
    category: str
    patterns: tuple[re.Pattern[str], ...]


def _term_pattern(term: str, case_sensitive: bool) -> re.Pattern[str]:
    # Treat spaces and hyphens as interchangeable: "problem solving" == "problem-solving".
    parts = [re.escape(part) for part in re.split(r"[\s-]+", term.strip()) if part]
    body = r"[\s-]+".join(parts)
    flags = 0 if case_sensitive else re.IGNORECASE
    after = _CASED_AFTER if case_sensitive else _AFTER
    return re.compile(_BEFORE + body + after, flags)


def _build_skill(entry: dict, category: str) -> Skill:
    cased = set(entry.get("cased", []))
    terms = [entry["name"], *entry.get("aliases", []), *cased]
    unique_terms = list(dict.fromkeys(terms))  # de-duplicate, keep order
    patterns = tuple(_term_pattern(term, term in cased) for term in unique_terms)
    return Skill(name=entry["name"], category=category, patterns=patterns)


@lru_cache
def load_taxonomy() -> tuple[Skill, ...]:
    """Load and compile the skill taxonomy once per process."""
    raw = resources.files("resume_analyzer").joinpath("data/skills.json").read_text("utf-8")
    categories: dict[str, list[dict]] = json.loads(raw)["categories"]
    return tuple(
        _build_skill(entry, category)
        for category, entries in categories.items()
        for entry in entries
    )


def categories() -> list[str]:
    """Category names in taxonomy order."""
    return list(dict.fromkeys(skill.category for skill in load_taxonomy()))


def extract_skills(text: str) -> dict[str, list[str]]:
    """Return {category: [skill, ...]} for every taxonomy skill mentioned in `text`.

    Categories with no matches are omitted. Order follows the taxonomy file, so the
    output is stable and easy to compare in tests.
    """
    # Emails and links are contact details, not skills: "github.com/someone/docker-tools"
    # says nothing about Docker experience.
    text = URL_RE.sub(" ", EMAIL_RE.sub(" ", text))

    matches = [
        (match.start(), match.end(), skill)
        for skill in load_taxonomy()
        for pattern in skill.patterns
        for match in pattern.finditer(text)
    ]
    # Longest match wins: "GitHub" inside "GitHub Actions" is part of a longer skill name,
    # not a separate mention (the same idea that keeps "Java" out of "JavaScript").
    matches.sort(key=lambda m: m[0] - m[1])
    kept: list[tuple[int, int]] = []
    found_names: set[str] = set()
    for start, end, skill in matches:
        if any(s <= start and end <= e and e - s > end - start for s, e in kept):
            continue
        kept.append((start, end))
        found_names.add(skill.name)

    found: dict[str, list[str]] = {}
    for skill in load_taxonomy():
        if skill.name in found_names:
            found.setdefault(skill.category, []).append(skill.name)
    return found


def flatten(skills_by_category: dict[str, list[str]]) -> list[str]:
    """Flatten {category: [skills]} into one list, preserving order."""
    return [skill for skills in skills_by_category.values() for skill in skills]
