"""Small text guardrails shared by the LLM output checks."""

import re
import unicodedata

from resume_analyzer.redaction import redact
from resume_analyzer.skills import extract_skills, flatten

MAX_ITEM_CHARS = 300
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")  # \d also matches non-ASCII digits such as "５"
# Quantities written as words. "a" and "an" are left out on purpose: they are everywhere.
_NUMBER_WORDS = (
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety "
    "hundred hundreds thousand thousands million millions billion billions dozen dozens "
    "half halves quarter quarters third thirds double doubled triple tripled quadruple "
    "quadrupled twice thrice"
).split()
_NUMBER_WORD_RE = re.compile(r"\b(?:" + "|".join(_NUMBER_WORDS) + r")\b", re.IGNORECASE)


def clean(text: str) -> str:
    """Trim, re-redact (defence in depth) and cap one LLM string at MAX_ITEM_CHARS."""
    text, _ = redact(" ".join(text.split()))
    if len(text) > MAX_ITEM_CHARS:
        text = text[: MAX_ITEM_CHARS - 1].rstrip() + "…"
    return text


def numbers_in(text: str) -> set[str]:
    """Every quantity in `text`: digit runs ("85", "0.84", "2,000"), number words ("doubled",
    "three") and other numeric characters such as "½" (stored as their value, "0.5").

    This check is best-effort. It catches the usual ways of slipping in an invented figure,
    but it cannot catch every phrasing (for example "a handful of"). It is one layer of
    defence: rewrites are always shown next to the original so a person can compare.
    """
    found = set(_NUMBER.findall(text))
    found |= {word.lower() for word in _NUMBER_WORD_RE.findall(text)}
    for char in text:
        if char.isdecimal():
            continue  # digits are already covered by _NUMBER
        value = unicodedata.numeric(char, None)  # "½" -> 0.5, "Ⅻ" -> 12, "②" -> 2
        if value is not None:
            found.add(f"{value:g}")
    return found


def skills_in(text: str) -> set[str]:
    """Every taxonomy skill (all categories) the deterministic extractor finds in `text`."""
    return set(flatten(extract_skills(text)))
