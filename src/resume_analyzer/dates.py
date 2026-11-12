"""Date helpers: date-format styles (ATS checks) and a rough years-of-experience estimate."""

import re
from datetime import date

from resume_analyzer.sections import Line

_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
_YEAR = r"(?:19|20)\d{2}"
_DASH = r"(?:-|‐|‑|‒|–|—|to)"

MONTH_NAME_STYLE = "month name"
# Each style is a different way of writing a date. Using more than one is inconsistent.
STYLE_PATTERNS = {
    MONTH_NAME_STYLE: re.compile(rf"\b{_MONTH}\.?,?\s+{_YEAR}\b", re.IGNORECASE),
    "numeric (01/2022)": re.compile(rf"\b(?:0?[1-9]|1[0-2])/{_YEAR}\b"),
    "ISO (2022-01)": re.compile(rf"\b{_YEAR}-(?:0[1-9]|1[0-2])\b"),
}

_NUM_MONTH = r"(?:0?[1-9]|1[0-2])"
_ISO_MONTH = r"(?:0[1-9]|1[0-2])"

# One endpoint of a range. Named groups: month name (m), numeric month (n) and year (y).
# The first endpoint's groups end in 1, the second's in 2.
_START = (
    rf"(?:(?P<m1>{_MONTH})\.?,?\s+(?P<y1a>{_YEAR})"  # Jan 2021
    rf"|(?P<n1>{_NUM_MONTH})/(?P<y1b>{_YEAR})"  # 06/2018
    rf"|(?P<y1c>{_YEAR})-(?P<i1>{_ISO_MONTH})(?!\d)"  # 2018-06
    rf"|(?P<y1d>{_YEAR}))"  # 2018
)
_END = (
    rf"(?:(?P<m2>{_MONTH})\.?,?\s+(?P<y2a>{_YEAR})"
    rf"|(?P<n2>{_NUM_MONTH})/(?P<y2b>{_YEAR})"
    rf"|(?P<y2c>{_YEAR})-(?P<i2>{_ISO_MONTH})(?!\d)"
    rf"|(?P<y2d>{_YEAR})"
    rf"|(?P<now>Present|Current|Now|Ongoing|Today))"
)

# "Jan 2021 - Mar 2023", "2020 - Present", "2019 to 2021", "06/2018 - 08/2018", "2018-06 - 2018-08"
# The "-" between ISO endpoints is ambiguous ("2018-06-2018-08"), so spaces around it are optional
# but the month part of an ISO date is always tried first.
RANGE_RE = re.compile(rf"(?<![\d/-]){_START}\s*{_DASH}\s*{_END}", re.IGNORECASE)


def date_styles(text: str) -> dict[str, int]:
    """Count dates written in each style. Years on their own are neutral and not counted."""
    counts = {name: len(pattern.findall(text)) for name, pattern in STYLE_PATTERNS.items()}
    # "Jan 2022" and "January 2022" are two styles of the month-name format.
    abbreviated = full = 0
    for match in STYLE_PATTERNS[MONTH_NAME_STYLE].finditer(text):
        word = re.match(r"[A-Za-z]+", match.group()).group().lower()
        if word == "may":
            continue  # May is both the short and the full form
        if len(word) <= 3 or word == "sept":
            abbreviated += 1
        else:
            full += 1
    del counts[MONTH_NAME_STYLE]
    counts["abbreviated month (Jan 2022)"] = abbreviated
    counts["full month (January 2022)"] = full
    return {name: count for name, count in counts.items() if count}


def has_date_range(line: str) -> bool:
    """True if the line contains a date range such as "2021 - 2024" (a job/degree header)."""
    return RANGE_RE.search(line) is not None


def _endpoint(match: re.Match[str], side: str, default_month: int) -> int:
    """Month index (year * 12 + month) of one range endpoint; side is "1" (start) or "2" (end)."""
    groups = match.groupdict()
    year = next(int(groups[k]) for k in groups if k.startswith(f"y{side}") and groups[k])
    name = groups[f"m{side}"]
    numeric = groups[f"n{side}"] or groups[f"i{side}"]
    if name:
        month = _MONTHS.index(name[:3].lower()) + 1
    elif numeric:
        month = int(numeric)
    else:
        month = default_month  # year only: Jan for a start, Dec for an end
    return year * 12 + month


def estimate_years(lines: list[Line], today: date | None = None) -> float | None:
    """Approximate years of work experience from date ranges in the experience section.

    Overlapping ranges are merged so two part-time jobs are not double counted.
    Returns None when no ranges are found. Year-only dates count Jan to Dec, so this
    is an estimate, and the UI should call it that.
    """
    today = today or date.today()
    spans: list[tuple[int, int]] = []
    for line in lines:
        if line.section != "experience":
            continue
        for match in RANGE_RE.finditer(line.text):
            start = _endpoint(match, "1", 1)
            end = today.year * 12 + today.month if match["now"] else _endpoint(match, "2", 12)
            if end >= start:
                spans.append((start, end))
    if not spans:
        return None
    spans.sort()
    merged = [spans[0]]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    months = sum(end - start for start, end in merged)
    return round(months / 12, 1)
