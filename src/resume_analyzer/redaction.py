"""Remove contact details (emails, phone numbers, URLs) before text is sent to an LLM.

Redaction runs *before* prompt building, so the LLM never sees this data.
"""

import re

from resume_analyzer.models import RedactionCounts

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")

URL_RE = re.compile(
    r"""
    (?:https?://|www\.)\S+                                   # explicit scheme or www.
    | \b(?:linkedin|github|gitlab|behance|kaggle|medium)\.com(?:/\S*)?   # common profile hosts
    # Bare domain with a common TLD, with or without a path: example.com/me, JaneDoe.com,
    # testy-sample.me, someone.github.io. The TLD must be lowercase and is case-sensitive, so
    # "ASP.NET/C#" is not a URL; "Node.js" and "8.6/10" have no listed TLD.
    | (?-i:\b[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:com|org|net|io|dev|ai|in|co|edu|me|app|tech)
         \b(?:/\S*)?)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# One separator between digit groups: a space, dot or any dash. Real resumes mix them
# ("555.010-1234") and word processors turn "-" into Unicode dashes (U+2010-2015, U+2212).
_SEP = r"[ \t.\-\u2010-\u2015\u2212]"

PHONE_RE = re.compile(
    rf"""
    (?<![\w])
    (?:
        \+\d{{1,3}}{_SEP}?(?:\(\d{{1,4}}\){_SEP}?)?\d{{2,5}}{_SEP}?\d{{3,5}}(?:{_SEP}?\d{{2,5}})?
      | \(\d{{3}}\){_SEP}?\d{{3}}{_SEP}?\d{{4}}            # (555) 010-1234, (555)-010-1234
      | \d{{3}}{_SEP}\d{{3}}{_SEP}\d{{4}}                  # 555-010-1234, 555.010 1234
      | \d{{10}}                                         # 5550101234
    )
    (?![\w])
    """,
    re.VERBOSE,
)

EMAIL_TOKEN = "[EMAIL]"
PHONE_TOKEN = "[PHONE]"
URL_TOKEN = "[URL]"


def redact(text: str) -> tuple[str, RedactionCounts]:
    """Replace emails, URLs and phone numbers with placeholder tokens.

    Order matters: emails first (so their domain is not treated as a URL), then URLs
    (so digits inside a URL are not treated as a phone number), then phones.
    """
    text, emails = EMAIL_RE.subn(EMAIL_TOKEN, text)
    text, urls = URL_RE.subn(URL_TOKEN, text)
    text, phones = PHONE_RE.subn(PHONE_TOKEN, text)
    return text, RedactionCounts(emails=emails, phones=phones, urls=urls)
