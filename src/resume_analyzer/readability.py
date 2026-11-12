"""Layer 6: tone and readability.

Passive voice, bullet length, buzzword density and verbs that open too many bullets.
Rules of thumb for resumes, not linguistics: the checks are simple on purpose.
"""

import re
from collections import Counter

from resume_analyzer.schemas import (
    BulletReport,
    BuzzwordCount,
    Readability,
    RepeatedVerb,
    Snippet,
)
from resume_analyzer.scoring import first_word
from resume_analyzer.wordbanks import BUZZ_RE, VERB_ALTERNATIVES

REPEAT_THRESHOLD = 3  # a verb opening this many bullets is flagged
MAX_PASSIVE_EXAMPLES = 3
PASSIVE_RATE_WARN = 25  # percent of bullets
BUZZ_DENSITY_WARN = 1.0  # per 100 words
IDEAL_BULLET_WORDS = (12, 28)
GENERIC_ALTERNATIVES = ["Delivered", "Built", "Improved", "Streamlined"]

# "was built", "were deployed", "is maintained", "been reviewed" (an adverb may sit between).
_IRREGULAR = "built|made|done|given|taken|written|run|led|known|seen|shown|set|kept|held|sent|won"
PASSIVE_RE = re.compile(
    rf"\b(?:was|were|is|are|been|being|be)\s+(?:\w+ly\s+)?((?:\w+ed)|{_IRREGULAR})\b",
    re.IGNORECASE,
)
# "was interested", "is motivated": adjectives that end in -ed, not passive actions.
NOT_PASSIVE = frozenset(
    "interested excited motivated tired pleased experienced qualified skilled dedicated "
    "committed focused determined passionate organized detail-oriented based".split()
)


def find_passive(text: str) -> re.Match[str] | None:
    """The first passive-voice phrase in `text`, or None."""
    for match in PASSIVE_RE.finditer(text):
        if match.group(1).lower() not in NOT_PASSIVE:
            return match
    return None


def _repeated_verbs(openers: list[str]) -> list[RepeatedVerb]:
    counts = Counter(word for word in openers if word)
    repeated = []
    for verb, count in counts.most_common():
        if count < REPEAT_THRESHOLD:
            break
        alternatives = VERB_ALTERNATIVES.get(verb, GENERIC_ALTERNATIVES)
        alternatives = [a for a in alternatives if a.lower() != verb]
        repeated.append(
            RepeatedVerb(verb=verb.capitalize(), count=count, alternatives=alternatives)
        )
    return repeated


def analyze_readability(text: str, bullets: BulletReport) -> Readability:
    """Tone metrics: bullets (passive, length, repeated verbs) and the whole text (buzzwords)."""
    items = bullets.items
    passive = []
    for item in items:
        if find_passive(item.text):
            passive.append(item)
    passive_rate = round(100 * len(passive) / len(items)) if items else None
    avg_words = round(sum(item.word_count for item in items) / len(items), 1) if items else None

    buzz_hits = Counter(match.group().lower() for match in BUZZ_RE.finditer(text))
    words = len(text.split())
    density = round(100 * sum(buzz_hits.values()) / words, 2) if words else 0.0
    repeated = _repeated_verbs([first_word(item.text) for item in items])

    notes: list[str] = []
    if passive_rate is not None and passive_rate > PASSIVE_RATE_WARN:
        notes.append(
            f"{passive_rate}% of bullets use passive voice ('was built'). "
            "Say what you did: 'Built ...'."
        )
    if avg_words is not None and not IDEAL_BULLET_WORDS[0] <= avg_words <= IDEAL_BULLET_WORDS[1]:
        side = "short" if avg_words < IDEAL_BULLET_WORDS[0] else "long"
        notes.append(f"Bullets average {avg_words:g} words, which is {side}; aim for 12-28.")
    if density > BUZZ_DENSITY_WARN:
        notes.append(f"{density:g} buzzwords per 100 words; replace them with concrete examples.")
    for item in repeated:
        notes.append(
            f"'{item.verb}' starts {item.count} bullets. "
            f"Vary it: {', '.join(item.alternatives[:3])}."
        )

    return Readability(
        bullet_count=len(items),
        avg_bullet_words=avg_words,
        passive_count=len(passive),
        passive_rate_percent=passive_rate,
        passive_examples=[
            Snippet(start=item.start, end=item.end, text=item.text)
            for item in passive[:MAX_PASSIVE_EXAMPLES]
        ],
        buzzwords=[
            BuzzwordCount(term=term, count=count) for term, count in buzz_hits.most_common()
        ],
        buzzword_density=density,
        repeated_verbs=repeated,
        notes=notes,
    )
