"""Layer 2: parse-ability checks.

Applicant tracking systems read the *extracted text* of a resume. Layouts that look nice
(columns, tables, icons) often come out scrambled. These checks look for the signals such
a mess leaves behind in the extracted text and explain each one. They are heuristics, not
the behaviour of any real ATS.
"""

import re

from resume_analyzer.dates import date_styles
from resume_analyzer.redaction import EMAIL_RE, PHONE_RE
from resume_analyzer.schemas import ATSCheck, ATSChecks, Snippet
from resume_analyzer.scoring import IDEAL_WORDS
from resume_analyzer.sections import Line

CORE_SECTIONS = ("experience", "education", "skills")
# Warn only outside a tolerance band around the ideal range (IDEAL_WORDS), which is the
# range the advice quotes, so the score breakdown and this check give the same target.
WORDS_TOO_SHORT, WORDS_SHORT = 120, 250
WORDS_LONG, WORDS_TOO_LONG = 1100, 1800
WORDS_PER_PAGE = 500
MIN_WORDS_FOR_TEXT = 50
LONG_LINE_CHARS = 160
CONTACT_WITHIN_LINES = 8
MAX_EVIDENCE = 5

# Decorative glyphs, arrows, a private-use range (icon fonts) and the replacement character
# U+FFFD (a sign the extractor could not decode a symbol). Written as escapes so they are visible.
ODD_GLYPH_RE = re.compile("[●▪▫◦▸►■□❖✔✓☑★☆➤➜→❯-�]")
GAP_RE = re.compile(r"\S(?: {3,}|\t+)\S")  # a wide gap inside a line: typical of columns
SECTION_ORDER_HINT = "Experience usually comes before Education unless you graduated recently."


def _snippet(line: Line) -> Snippet:
    return Snippet(start=line.start, end=line.end, text=line.text[:160])


def _check(
    id_: str,
    title: str,
    status: str,
    detail: str,
    fix: str | None = None,
    evidence: list[Snippet] | None = None,
) -> ATSCheck:
    return ATSCheck(
        id=id_,
        title=title,
        status=status,
        detail=detail,
        fix=fix,
        evidence=(evidence or [])[:MAX_EVIDENCE],
    )


def _contact_checks(text: str, lines: list[Line]) -> list[ATSCheck]:
    email, phone = EMAIL_RE.search(text), PHONE_RE.search(text)
    checks = [
        _check("email", "Email address", "pass", "An email address was found.")
        if email
        else _check(
            "email",
            "Email address",
            "fail",
            "No email address found in the extracted text.",
            "Put a plain-text email near the top; do not hide it in an image or header.",
        ),
        _check("phone", "Phone number", "pass", "A phone number was found.")
        if phone
        else _check(
            "phone",
            "Phone number",
            "warn",
            "No phone number found.",
            "Add a phone number in plain text, e.g. +91 555 010 1234.",
        ),
    ]
    first_lines = "\n".join(line.text for line in lines[:CONTACT_WITHIN_LINES])
    if (email or phone) and not (EMAIL_RE.search(first_lines) or PHONE_RE.search(first_lines)):
        checks.append(
            _check(
                "contact_position",
                "Contact details at the top",
                "warn",
                "Contact details are not in the first lines of the text.",
                "Move them to the very top so parsers find them first.",
            )
        )
    return checks


def _headings_check(sections: list[str]) -> ATSCheck:
    missing = [name for name in CORE_SECTIONS if name not in sections]
    if not missing:
        return _check(
            "headings",
            "Standard section headings",
            "pass",
            "Experience, Education and Skills headings found.",
        )
    status = "warn" if len(missing) == 1 else "fail"
    return _check(
        "headings",
        "Standard section headings",
        status,
        f"Missing standard heading(s): {', '.join(missing)}.",
        "Use plain headings such as 'Experience', 'Education' and 'Skills'; "
        "creative names confuse parsers.",
    )


def _order_check(lines: list[Line], sections: list[str]) -> ATSCheck:
    first_heading = {}
    for line in lines:
        if line.is_heading and line.section not in first_heading:
            first_heading[line.section] = line
    problems = []
    education, experience = first_heading.get("education"), first_heading.get("experience")
    if education and experience and education.start < experience.start:
        problems.append("Education comes before Experience. " + SECTION_ORDER_HINT)
    if "summary" in first_heading and any(
        other.start < first_heading["summary"].start
        for name, other in first_heading.items()
        if name != "summary"
    ):
        problems.append("Summary is not the first section.")
    if problems:
        return _check("section_order", "Section order", "warn", " ".join(problems))
    return _check("section_order", "Section order", "pass", "Sections are in a conventional order.")


def _dates_check(text: str) -> ATSCheck:
    styles = date_styles(text)
    if len(styles) > 1:
        names = ", ".join(f"{name} x{count}" for name, count in styles.items())
        return _check(
            "date_formats",
            "Consistent date formats",
            "warn",
            f"Dates are written in {len(styles)} different ways: {names}.",
            "Pick one format (for example 'Jan 2022 - Mar 2024') and use it everywhere.",
        )
    if not styles:
        return _check(
            "date_formats",
            "Consistent date formats",
            "pass",
            "No conflicting month-level date formats found.",
        )
    return _check("date_formats", "Consistent date formats", "pass", "Dates use one format.")


def _columns_check(lines: list[Line]) -> ATSCheck:
    gapped = [line for line in lines if GAP_RE.search(line.text) is not None]
    # Lines were stripped, so also look for gaps in the raw text of tabbed lines: GAP_RE
    # already covers tabs. 3+ lines with a wide gap suggests text laid out in columns.
    if len(gapped) >= 8:
        status = "fail"
    elif len(gapped) >= 3:
        status = "warn"
    else:
        return _check("columns", "Single-column layout", "pass", "No multi-column artifacts found.")
    return _check(
        "columns",
        "Single-column layout",
        status,
        f"{len(gapped)} lines contain wide gaps or tabs, a sign of columns or a table.",
        "Use a single-column layout; parsers read columns line by line and mix them up.",
        [_snippet(line) for line in gapped],
    )


def _tables_check(lines: list[Line]) -> ATSCheck:
    # The first lines often hold "email | phone | city"; pipes there are normal.
    body = lines[CONTACT_WITHIN_LINES:]
    piped = [line for line in body if line.text.count("|") >= 2]
    long_lines = [line for line in lines if len(line.text) > LONG_LINE_CHARS]
    problems = []
    if len(piped) >= 3:
        problems.append(f"{len(piped)} lines use | separators like table cells")
    if len(long_lines) >= 3:
        problems.append(f"{len(long_lines)} lines are over {LONG_LINE_CHARS} characters")
    if not problems:
        return _check(
            "tables", "No table artifacts", "pass", "No table-like or run-on lines found."
        )
    return _check(
        "tables",
        "No table artifacts",
        "warn",
        "; ".join(problems) + ".",
        "Replace tables with simple lines and bullets; keep lines short.",
        [_snippet(line) for line in piped + long_lines],
    )


def _glyph_check(text: str) -> ATSCheck:
    hits = list(ODD_GLYPH_RE.finditer(text))
    if not hits:
        return _check("glyphs", "Plain bullet characters", "pass", "No unusual symbols found.")
    evidence = [Snippet(start=m.start(), end=m.end(), text=m.group()) for m in hits]
    return _check(
        "glyphs",
        "Plain bullet characters",
        "warn",
        f"{len(hits)} unusual symbol(s) (icons, arrows, private-use or broken characters).",
        "Use simple bullets such as - or the standard dot; icons often turn into garbage.",
        evidence,
    )


def _length_check(word_count: int) -> ATSCheck:
    pages = max(1, round(word_count / WORDS_PER_PAGE))
    if word_count < WORDS_TOO_SHORT:
        status, detail = "fail", f"Only {word_count} words, far too short."
    elif word_count < WORDS_SHORT:
        status, detail = "warn", f"{word_count} words is short."
    elif word_count > WORDS_TOO_LONG:
        status, detail = "fail", f"{word_count} words (about {pages} pages) is far too long."
    elif word_count > WORDS_LONG:
        status, detail = "warn", f"{word_count} words (about {pages} pages) is long."
    else:
        return _check("length", "Length", "pass", f"{word_count} words (about {pages} page(s)).")
    return _check(
        "length",
        "Length",
        status,
        detail,
        f"Aim for {IDEAL_WORDS[0]:,}-{IDEAL_WORDS[1]:,} words: one or two pages.",
    )


def _extraction_check(word_count: int) -> ATSCheck:
    if word_count >= MIN_WORDS_FOR_TEXT:
        return _check(
            "text_extraction", "Text is extractable", "pass", "Plenty of text was extracted."
        )
    return _check(
        "text_extraction",
        "Text is extractable",
        "fail",
        f"Only {word_count} words were extracted.",
        "If the file is a scan or an image, export a text-based PDF instead.",
    )


def run_ats_checks(text: str, lines: list[Line], sections: list[str]) -> ATSChecks:
    """Run all parse-ability checks on the raw extracted text."""
    word_count = len(text.split())
    items = [
        _extraction_check(word_count),
        *_contact_checks(text, lines),
        _headings_check(sections),
        _order_check(lines, sections),
        _dates_check(text),
        _columns_check(lines),
        _tables_check(lines),
        _glyph_check(text),
        _length_check(word_count),
    ]
    passed = sum(item.status == "pass" for item in items)
    warned = sum(item.status == "warn" for item in items)
    failed = sum(item.status == "fail" for item in items)
    score = round(100 * (passed + 0.5 * warned) / len(items))
    return ATSChecks(score=score, passed=passed, warned=warned, failed=failed, items=items)
