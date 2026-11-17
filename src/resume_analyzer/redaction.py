"""Remove contact details (emails, phone numbers, URLs) before text is sent to an LLM.

Redaction runs *before* prompt building, so the LLM never sees this data.
"""

import re

from resume_analyzer.models import RedactionCounts

# Every repeat is bounded (RFC 5321 limits: 64-character local part, 63-character DNS labels).
# Unbounded repeats make a long run such as "a.a.a.a..." re-scan to the end of the run from
# every start position. That is quadratic: one small upload could keep the server busy for minutes.
EMAIL_RE = re.compile(r"\b[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,8}\b")

URL_RE = re.compile(
    r"""
    (?:https?://|www\.)\S+                                   # explicit scheme or www.
    | \b(?:linkedin|github|gitlab|behance|kaggle|medium)\.com(?:/\S*)?   # common profile hosts
    # Bare domain with a common TLD, with or without a path: example.com/me, JaneDoe.com,
    # testy-sample.me, someone.github.io. The TLD must be lowercase and is case-sensitive, so
    # "ASP.NET/C#" is not a URL; "Node.js" and "8.6/10" have no listed TLD. Labels are bounded
    # for the same reason as in EMAIL_RE.
    | (?-i:\b[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){0,6}
         \.(?:com|org|net|io|dev|ai|in|co|edu|me|app|tech)\b(?:/\S*)?)
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
      # Indian numbers. Mobiles start with 6-9 and are usually written 5+5 ("98765 43210"), with
      # an optional "91" country code or a trunk "0". Landlines are a "0" + area code (2-4
      # digits) + 6-8 digits, e.g. "0141-2345678". Brackets are common: "(+91) 98765-43210".
      | (?:\+?91{_SEP}?|0)?[6-9]\d{{4}}{_SEP}?\d{{5}}
      | \(\+?\d{{1,3}}\){_SEP}?[6-9]\d{{4}}{_SEP}?\d{{5}}
      | 0\d{{2,4}}{_SEP}\d{{6,8}}
      | \(0\d{{2,4}}\){_SEP}?\d{{6,8}}
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
