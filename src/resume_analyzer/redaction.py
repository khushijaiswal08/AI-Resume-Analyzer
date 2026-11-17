"""Remove contact details (emails, phone numbers, URLs) before text is sent to an LLM.

Redaction runs *before* prompt building, so the LLM never sees this data.

What it covers, honestly: email addresses, links, Indian phone numbers (mobile and landline, with
or without +91), "+" international numbers and US-style 3-3-4 numbers. Other national formats
(for example "020 7946 0958") and personal details such as names and addresses are NOT removed.
Every repeat in the patterns is bounded, so a crafted upload cannot make them slow.
"""

import re

from resume_analyzer.models import RedactionCounts

# --- Emails -------------------------------------------------------------------------------------
# Every repeat is bounded (RFC 5321 limits: 64-character local part, 63-character DNS labels).
# Unbounded repeats make a long run such as "a.a.a.a..." re-scan to the end of the run from
# every start position. That is quadratic: one small upload could keep the server busy for minutes.
# The last label must be letters, so "python@3.12" and "Meeting@10.30am" are not emails.
EMAIL_RE = re.compile(r"\b[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){0,7}\.[A-Za-z]{2,24}\b")

# Addresses the bounded pattern cannot match (local part over 64 characters, a label over 63, or
# nine or more labels) are caught by a token check instead, so nothing is left half-visible.
# It is linear: the text is split on whitespace once and each token is examined once.
_TOKEN_RE = re.compile(r"\S+")


def _is_oversized_address(token: str) -> bool:
    at = token.find("@")
    if at < 1 or at == len(token) - 1:
        return False
    local, host = token[:at], token[at + 1 :]
    if "." not in host:
        return False
    return (
        len(local) > 64
        or len(host) > 253
        or host.count(".") >= 8
        or any(len(label) > 63 for label in host.split("."))
    )


def _redact_oversized_addresses(text: str) -> tuple[str, int]:
    if "@" not in text:
        return text, 0
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        if _is_oversized_address(match.group()):
            count += 1
            return EMAIL_TOKEN
        return match.group()

    return _TOKEN_RE.sub(replace, text), count


# --- URLs ---------------------------------------------------------------------------------------
URL_RE = re.compile(
    r"""
    (?:https?://|www\.)\S+                                   # explicit scheme or www.
    | \b(?:linkedin|github|gitlab|behance|kaggle|medium)\.com(?:/\S*)?   # common profile hosts
    # Bare domain with a common TLD, with or without a path: example.com/me, JaneDoe.com,
    # testy-sample.me, someone.github.io. The TLD must be lowercase and is case-sensitive, so
    # "ASP.NET/C#" is not a URL; "Node.js" and "8.6/10" have no listed TLD. "B.tech" and
    # "M.tech" (degrees) are skipped by the first lookahead. Labels are bounded for the same
    # reason as in EMAIL_RE.
    | (?-i:(?![A-Za-z]{1,2}\.tech\b)\b[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){0,6}
         \.(?:com|org|net|io|dev|ai|in|co|edu|me|app|tech)\b(?:/\S*)?)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# --- Phone numbers ------------------------------------------------------------------------------
# One separator between digit groups: a space (including no-break and thin spaces), a dot or any
# dash, optionally with one space on each side of a dot or dash ("98765 - 43210"). Real resumes
# mix them ("555.010-1234"), and word processors turn "-" into Unicode dashes (U+2010-2015,
# U+2212).
_SEP = r"(?:[ \t]?[.\-‐-―−][ \t]?|[ \t   ])"

# A date written without separators ("20231117") is not the tail of a landline.
_NOT_A_DATE = r"(?!(?:19|20)\d{2}(?:0[1-9]|1[0-2])\d{2}(?!\d))"

# Indian mobiles start with 6-9. With no "+91"/"91"/"0" prefix, two round numbers such as
# "60000-80000" (a salary range) or "70000 90000" are left alone, as is anything after a
# currency sign or "Rs".
_NOT_MONEY = r"(?<![₹$€£])(?<!Rs\.)(?<!Rs )(?<!Rs\. )(?<!INR )(?<![₹$€£] )"
_NOT_ROUND_5_5 = rf"(?!\d{{2}}0{{3}}{_SEP}?\d{{2}}0{{3}}(?!\d))"
_NOT_ROUND_4_6 = rf"(?!\d{{2}}00{_SEP}?\d{{4}}00(?!\d))"

PHONE_RE = re.compile(
    rf"""
    (?<!\w)
    (?:
        \+\d{{1,3}}{_SEP}?(?:\(\d{{1,4}}\){_SEP}?)?\d{{2,5}}{_SEP}?\d{{3,5}}(?:{_SEP}?\d{{2,5}})?(?:{_SEP}\d{{2}}){{0,2}}
      | \(\+?\d{{1,3}}\){_SEP}?\d{{2,5}}{_SEP}?\d{{3,5}}(?:{_SEP}?\d{{2,5}})?  # (+91) 98765-43210
      | \(\d{{3}}\){_SEP}?\d{{3}}{_SEP}?\d{{4}}            # (555) 010-1234, (555)-010-1234
      | \d{{3}}{_SEP}\d{{3}}{_SEP}\d{{4}}                  # 555-010-1234, 555.010 1234
      | \d{{10}}                                         # 5550101234
    )
    (?!\w)
    |
    # Indian formats. Only digits are checked at the edges, so a number glued to words by PDF
    # text extraction ("Phone9876543210Email") is still found.
    (?<!\d)
    (?:
        (?:\+?91{_SEP}?|0)[6-9]\d{{4}}{_SEP}?\d{{5}}       # +91 98765 43210, 919876543210
      | (?:\+?91{_SEP}?|0)[6-9]\d{{3}}{_SEP}?\d{{6}}       # 4+6 grouping with a prefix
      | [6-9]\d{{9}}                                     # 9876543210, even when glued to a word
      | {_NOT_MONEY}{_NOT_ROUND_5_5}[6-9]\d{{4}}{_SEP}\d{{5}}   # 98765 43210
      | {_NOT_MONEY}{_NOT_ROUND_4_6}[6-9]\d{{3}}{_SEP}\d{{6}}   # 9876 543210
      | 0(?!0)\d{{2,4}}{_SEP}{_NOT_A_DATE}\d{{6,8}}            # 0141-2345678, 011 23456789
      | 0(?!0)\d{{2,4}}{_SEP}\d{{3,4}}{_SEP}\d{{3,4}}          # 011 2345 6789, 0141-234-5678
      | \(0(?!0)\d{{2,4}}\){_SEP}?(?:\d{{6,8}}|\d{{3,4}}{_SEP}\d{{3,4}})   # (0141) 2345678
    )
    (?!\d)
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
    text, oversized = _redact_oversized_addresses(text)
    text, emails = EMAIL_RE.subn(EMAIL_TOKEN, text)
    text, urls = URL_RE.subn(URL_TOKEN, text)
    text, phones = PHONE_RE.subn(PHONE_TOKEN, text)
    return text, RedactionCounts(emails=emails + oversized, phones=phones, urls=urls)
