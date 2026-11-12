"""Small word lists shared by the bullet, readability and LLM-grounding layers.

Plain data in one place so a reviewer can read and argue with every entry.
"""

import re

# Phrases that describe a duty instead of an achievement.
WEAK_PHRASES = (
    "responsible for",
    "worked on",
    "worked with",
    "helped",
    "assisted",
    "involved in",
    "participated in",
    "duties included",
    "tasked with",
    "in charge of",
    "various",
    "etc",
)

# Empty adjectives recruiters skim past; they claim a quality instead of showing it.
BUZZWORDS = (
    "synergy",
    "team player",
    "hard-working",
    "hardworking",
    "go-getter",
    "self-starter",
    "results-oriented",
    "detail-oriented",
    "dynamic",
    "passionate",
    "motivated",
    "proactive",
    "innovative",
    "cutting-edge",
    "think outside the box",
    "rockstar",
    "ninja",
    "guru",
    "best-of-breed",
    "fast learner",
    "quick learner",
)

FIRST_PERSON = ("i", "me", "my", "mine", "myself", "i'm", "i've", "i'd", "i'll")

# Verbs that, as the FIRST word, signal present tense ("Build ...", "Develops ...").
PRESENT_FORMS = frozenset(
    """
    build builds building develop develops developing create creates creating manage manages
    managing lead leads leading design designs designing implement implements implementing
    write writes writing maintain maintains maintaining deploy deploys deploying improve
    improves improving automate automates automating analyze analyzes analyse analyses
    collaborate collaborates collaborating support supports supporting work works working
    """.split()
)

# Irregular past-tense action verbs already in scoring.ACTION_VERBS cover most past tense;
# this extra set catches past forms that are not on that list.
PAST_EXTRA = frozenset("ran spoke made won found gave took began taught drove grew held".split())

# Used for "Developed x6": a few alternatives per overused opener.
VERB_ALTERNATIVES: dict[str, list[str]] = {
    "developed": ["Built", "Engineered", "Implemented", "Prototyped"],
    "built": ["Engineered", "Developed", "Shipped", "Assembled"],
    "created": ["Designed", "Launched", "Established", "Authored"],
    "worked": ["Collaborated", "Contributed", "Partnered", "Delivered"],
    "managed": ["Led", "Coordinated", "Oversaw", "Directed"],
    "implemented": ["Deployed", "Integrated", "Rolled out", "Introduced"],
    "designed": ["Architected", "Modelled", "Drafted", "Planned"],
    "improved": ["Optimized", "Streamlined", "Boosted", "Refined"],
    "led": ["Directed", "Spearheaded", "Headed", "Guided"],
    "used": ["Applied", "Leveraged", "Adopted", "Employed"],
    "helped": ["Enabled", "Supported", "Facilitated", "Contributed to"],
    "made": ["Produced", "Delivered", "Crafted", "Generated"],
    "wrote": ["Authored", "Documented", "Drafted", "Composed"],
    "handled": ["Resolved", "Processed", "Administered", "Owned"],
    "analyzed": ["Evaluated", "Investigated", "Examined", "Assessed"],
    "automated": ["Scripted", "Streamlined", "Orchestrated", "Eliminated manual"],
    "tested": ["Validated", "Verified", "Benchmarked", "Audited"],
}


def phrase_regex(terms: tuple[str, ...]) -> re.Pattern[str]:
    """One case-insensitive regex that matches any term as whole words."""
    ordered = sorted(terms, key=len, reverse=True)  # longest first so "worked on" beats "worked"
    body = "|".join(re.escape(term).replace(r"\ ", r"\s+") for term in ordered)
    return re.compile(rf"(?<![\w-])(?:{body})(?![\w-])", re.IGNORECASE)


WEAK_RE = phrase_regex(WEAK_PHRASES)
BUZZ_RE = phrase_regex(BUZZWORDS)
FIRST_PERSON_RE = phrase_regex(FIRST_PERSON)
