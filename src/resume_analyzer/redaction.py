"""Remove contact details (emails, phone numbers, URLs) before text is sent to an LLM.

Redaction runs *before* prompt building, so the LLM never sees this data.

What it covers, honestly: email addresses, links, Indian phone numbers (mobile and landline, with
or without +91), "+" international numbers and US-style 3-3-4 numbers. Other national formats
(for example "020 7946 0958") and personal details such as names and addresses are NOT removed.
A zero-led reference number such as a roll number can look like a landline and be redacted.
Every repeat in the patterns is bounded, so a crafted upload cannot make them slow.
"""

import re

from resume_analyzer.models import RedactionCounts

# --- Emails -------------------------------------------------------------------------------------
# Every repeat is bounded (RFC 5321 limits: 64-character local part, 63-character DNS labels).
# Unbounded repeats make a long run such as "a.a.a.a..." re-scan to the end of the run from
# every start position. That is quadratic: one small upload could keep the server busy for minutes.
# The last label must not start with a digit, so "python@3.12" and "Meeting@10.30am" are not
# emails. It has no closing "\b", so an address glued to following text by PDF extraction
# ("jane@gmail.com9876543210") is still removed.
EMAIL_RE = re.compile(r"\b[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){0,7}\.(?!\d)[\w-]{2,24}")

# Addresses the bounded pattern cannot match (local part over 64 characters, a label over 63, or
# nine or more labels) are caught by a piece check instead, so nothing is left half-visible.
# The text is split at whitespace and at delimiters such as | , ; : ( ) < > [ ] quotes and "/",
# so one glued header line is judged piece by piece. It is linear: every character is visited
# once.
_PIECE_RE = re.compile(r"""[^\s|,;:()<>\[\]"'/\\]+""")


def _is_oversized_address(piece: str) -> bool:
    at = piece.rfind("@")
    if at < 1 or at == len(piece) - 1:
        return False
    local, host = piece[:at], piece[at + 1 :]
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

    return _PIECE_RE.sub(replace, text), count


# --- URLs ---------------------------------------------------------------------------------------
URL_RE = re.compile(
    r"""
    (?:https?://|www\.)\S+                                   # explicit scheme or www.
    | \b(?:linkedin|github|gitlab|behance|kaggle|medium)\.com(?:/\S*)?   # common profile hosts
    # Bare domain with a common TLD, with or without a path: example.com/me, JaneDoe.com,
    # testy-sample.me, someone.github.io. The TLD must be lowercase and is case-sensitive, so
    # "ASP.NET/C#" is not a URL; "Node.js" and "8.6/10" have no listed TLD. The degrees "B.tech"
    # and "M.tech" are skipped by the first lookahead. Labels are bounded for the same reason as
    # in EMAIL_RE.
    | (?-i:(?![BbMm]\.tech\b)\b[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){0,6}
         \.(?:com|org|net|io|dev|ai|in|co|edu|me|app|tech)\b(?:/\S*)?)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# --- Phone numbers ------------------------------------------------------------------------------
# One separator between digit groups: a space (including no-break, thin and ideographic spaces),
# a dot or any dash, optionally with one space on each side of a dot or dash ("98765 - 43210").
# Real resumes mix them ("555.010-1234"), and word processors turn "-" into Unicode dashes
# (U+2010-2015, U+2212). The patterns are compiled with re.VERBOSE, which drops plain spaces, so
# a space inside a character class is the only way to write one.
_SP = r"[ \t  -   　]"
_SEP = rf"(?:{_SP}?[.\-‐-―−]{_SP}?|{_SP})"

# A date written without separators ("20231117") is not the tail of a landline.
_NOT_A_DATE = r"(?!20(?:1[5-9]|2\d|3[0-5])(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?!\d))"

# Indian mobiles start with 6-9. With no "+91"/"91"/"0" prefix, two round numbers such as
# "60000-80000" (a salary range) are left alone, as is anything after a currency sign or "Rs".
_NOT_MONEY = r"(?<![₹$€£])(?<!Rs\.)(?<!Rs[ ])(?<!Rs\.[ ])(?<!INR[ ])(?<![₹$€£][ ])"
_NOT_ROUND_5_5 = rf"(?!\d{{2}}0{{3}}{_SEP}?\d{{2}}0{{3}}(?!\d))"
_NOT_ROUND_4_6 = rf"(?!\d{{2}}00{_SEP}?\d{{4}}00(?!\d))"

PHONE_RE = re.compile(
    rf"""
    (?<!\w)
    (?:
        \+\d{{1,3}}{_SEP}?\d{{1,2}}(?:{_SEP}\d{{2}}){{3,4}}  # +33 1 23 45 67 89
      | \+\d{{1,3}}{_SEP}?(?:\(\d{{1,4}}\){_SEP}?)?\d{{2,5}}{_SEP}?\d{{3,5}}
        (?:{_SEP}?\d{{2,5}})?(?:{_SEP}\d{{2}}){{0,2}}      # +91 98765 43210, +41 44 123 45 67
      | \(\+\d{{1,3}}\){_SEP}?\d{{2,5}}{_SEP}?\d{{3,5}}(?:{_SEP}?\d{{2,5}})?  # (+91) 98765-43210
      | \(\d{{3}}\){_SEP}?\d{{3}}{_SEP}?\d{{4}}            # (555) 010-1234, (555)-010-1234
      | \d{{3}}{_SEP}\d{{3}}{_SEP}\d{{4}}                  # 555-010-1234, 555.010 1234
      | \d{{10}}                                         # 5550101234
      | {_NOT_MONEY}{_NOT_ROUND_5_5}[6-9]\d{{4}}{_SEP}\d{{5}}   # 98765 43210
      | {_NOT_MONEY}{_NOT_ROUND_4_6}[6-9]\d{{3}}{_SEP}\d{{6}}   # 9876 543210
      | 0(?!0)\d{{2,4}}{_SEP}{_NOT_A_DATE}\d{{6,8}}            # 0141-2345678, 011 23456789
      | 0(?!0)\d{{2,4}}{_SEP}\d{{3,4}}{_SEP}\d{{3,4}}          # 011 2345 6789, 0141-234-5678
      | \(0(?!0)\d{{2,4}}\){_SEP}?(?:\d{{6,8}}|\d{{3,4}}{_SEP}\d{{3,4}})  # (0141) 2345678
    )
    (?!\w)
    |
    # Indian mobiles with a country code or trunk "0", or ten digits in a row. Only digits are
    # checked at the edges, so a number glued to words by PDF text extraction
    # ("Phone9876543210Email") is still found.
    (?<!\d)
    (?:
        (?:\+?91{_SEP}?|0)[6-9]\d{{4}}{_SEP}?\d{{5}}       # +91 98765 43210, 919876543210
      | (?:\+?91{_SEP}?|0)[6-9]\d{{3}}{_SEP}?\d{{6}}       # 4+6 grouping with a prefix
      | [6-9]\d{{9}}                                     # 9876543210, even when glued to a word
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

    Order matters: oversized addresses, then ordinary emails (so their domain is not treated as
    a URL), then URLs (so digits inside a URL are not treated as a phone number), then phones.
    """
    text, oversized = _redact_oversized_addresses(text)
    text, emails = EMAIL_RE.subn(EMAIL_TOKEN, text)
    text, urls = URL_RE.subn(URL_TOKEN, text)
    text, phones = PHONE_RE.subn(PHONE_TOKEN, text)
    return text, RedactionCounts(emails=emails + oversized, phones=phones, urls=urls)
