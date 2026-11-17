import time

import pytest

from resume_analyzer.redaction import redact


def test_redacts_email_phone_and_url_with_counts():
    text, counts = redact(
        "Mail a.b+cv@example.com or call (555) 010-1234. Site: https://example.com/me"
    )
    assert "example.com" not in text
    assert "555" not in text
    assert "[EMAIL]" in text and "[PHONE]" in text and "[URL]" in text
    assert (counts.emails, counts.phones, counts.urls) == (1, 1, 1)


@pytest.mark.parametrize(
    "phone",
    [
        "555-010-1234",
        "555.010.1234",
        "555 010 1234",
        "+1 555 010 1234",
        "+91 98765 43210",
        "(555) 010-1234",
        "5550101234",
        "(555)-010-1234",
        "555.010-1234",
        "555–010–1234",  # en dashes, as Word auto-formats them
        "+1 (555) 010‑1234",  # non-breaking hyphen
        # Indian formats a resume really uses
        "98765 43210",
        "98765-43210",
        "098765 43210",
        "91 98765 43210",
        "919876543210",
        "+91-98765-43210",
        "(+91) 98765-43210",
        "(+91) 98765 43210",
        "0141-2345678",
        "0141 2345678",
        "(0141) 2345678",
        "011-23456789",
        # Other groupings seen on real resumes
        "011 2345 6789",
        "(011) 4567 8901",
        "022-2345-6789",
        "0141-234-5678",
        "9876 543210",
        "9876-543210",
        "+91 - 98765 - 43210",
        "98765 - 43210",
        "+91 98765 43210",  # narrow no-break space
        "(+91) 11 2345 6789",
        "(+91) 80-2345-6789",
        "+41 44 123 45 67",
        "+7 495 123-45-67",
    ],
)
def test_phone_formats(phone):
    text, counts = redact(f"Phone: {phone}")
    assert counts.phones == 1
    assert text == "Phone: [PHONE]"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/x",
        "www.example.com",
        "github.com/someone",
        "example.org/path",
        "testy-sample.me",
        "fakename.dev",
        "JaneDoe.com/work",
        "someone.github.io",
    ],
)
def test_url_formats(url):
    text, counts = redact(f"See {url} for more")
    assert counts.urls == 1
    assert text == "See [URL] for more"


@pytest.mark.parametrize(
    "safe",
    [
        "Worked 2019-2023 on 3 projects",
        "Improved accuracy by 12.5% and CGPA 8.6/10",
        "Skills: Node.js, ASP.NET/C#, Vue.js",
        "Served 40,000 requests per day",
        "Built APIs with Node.js and ASP.NET; tutored B.Sc. students",
        "Salary band 50000 60000 and IDs 10000 20000",  # 5+5 digits not starting with 6-9
        "Batch 2023 2027, CGPA 8.46/10, roll 0141 and 1234567",
        # Salary ranges and amounts that look like a 5+5 mobile
        "Rs.60000-80000",
        "Rs. 60000 80000",
        "Salary 70000-90000 per month",
        "Stipend: 60000-80000",
        "70000.50000",
        "₹ 60000 80000",
        # Zero-led reference numbers
        "Ref: 011-20231117",
        "Invoice 000-123456",
        # Degrees and versions that are not links or emails
        "Education: B.tech in Computer Science (CGPA 8.46/10)",
        "M.tech in AI",
        "python@3.12 and Meeting@10.30am and Qty 3@4.5 each",
    ],
)
def test_ordinary_text_is_untouched(safe):
    text, counts = redact(safe)
    assert text == safe
    assert counts.model_dump() == {"emails": 0, "phones": 0, "urls": 0}


def test_email_domain_is_not_double_counted_as_url():
    _, counts = redact("someone@example.com")
    assert counts.emails == 1
    assert counts.urls == 0


def test_redaction_of_several_indian_numbers_in_one_line():
    text, counts = redact("Call 98765 43210 or (+91) 91234-56789 or 0141-2345678 today")
    assert text == "Call [PHONE] or [PHONE] or [PHONE] today"
    assert counts.phones == 3


# Runs that used to make the email and URL patterns quadratic: one small upload could keep the
# server busy for minutes. Every repeat in the patterns is now bounded, so each of these takes
# a few hundredths of a second. The 2-second limit is generous so slow CI machines do not flake.
@pytest.mark.parametrize(
    "hostile",
    [
        "a." * 25_000,
        "a-" * 25_000,
        "a.b" * 16_000,
        "x" * 50_000 + "@",
        ("a." * 30 + "b ") * 800,
        "a.b@c." * 9_000,
        "9" * 50_000,
        "98765 " * 10_000,
        "0141-" * 10_000,
    ],
    ids=[
        "dots",
        "dashes",
        "dotted-words",
        "long-local-part",
        "labels",
        "emails",
        "digits",
        "mobiles",
        "landlines",
    ],
)
def test_redaction_is_fast_on_hostile_input(hostile):
    started = time.perf_counter()
    redact(hostile)
    assert time.perf_counter() - started < 2.0


@pytest.mark.parametrize(
    "glued",
    ["Phone9876543210Email", "+919876543210Jaipur", "Mob:9876543210Email:jane"],
)
def test_phone_glued_to_words_by_pdf_extraction_is_still_redacted(glued):
    text, counts = redact(glued)
    assert counts.phones == 1
    assert not any(ch.isdigit() for ch in text)


@pytest.mark.parametrize(
    "address",
    [
        "a" * 65 + "@gmail.com",  # local part over 64 characters
        "firstname.lastname.department.division.company.region.country.team.group@gmail.com",
        "jane@a.a.a.a.a.a.a.a.a.com",  # nine labels
        "jane@" + "d" * 64 + ".com",  # label over 63 characters
    ],
)
def test_oversized_email_addresses_are_fully_redacted(address):
    text, counts = redact(f"mail {address} now")
    assert text == "mail [EMAIL] now"
    assert counts.emails == 1


@pytest.mark.parametrize(
    "hostile",
    [
        "a@" * 25_000,
        "@" * 50_000,
        "a" * 70 + "@x" * 8_000,
        "0141 " * 10_000,
        "+91 " * 12_000,
        "1" + " " * 49_998,
    ],
    ids=[
        "many-ats",
        "only-ats",
        "long-then-ats",
        "area-codes",
        "country-codes",
        "digit-then-spaces",
    ],
)
def test_redaction_is_fast_on_more_hostile_input(hostile):
    started = time.perf_counter()
    redact(hostile)
    assert time.perf_counter() - started < 2.0


# --- Regressions found by independent review of the second round ---------------------------


@pytest.mark.parametrize(
    "glued",
    ["jane.doe@gmail.com9876543210", "jane.doe@gmail.com2024", "jane.doe@gmail.com_x"],
)
def test_email_glued_to_following_text_is_still_redacted(glued):
    text, counts = redact(glued)
    assert "@" not in text and "gmail" not in text
    assert counts.emails == 1


def test_glued_header_line_keeps_phone_and_url_counts():
    header = (
        "Mansarovar,Jaipur,Rajasthan-302020|+91-9876543210|Phone9876543210|"
        "khushi.jaiswal@gmail.com|linkedin.com/in/khushi-jaiswal"
    )
    text, counts = redact(header)
    assert (counts.emails, counts.phones, counts.urls) == (1, 2, 1)
    assert text.startswith("Mansarovar,Jaipur,Rajasthan-302020|")


def test_url_containing_an_at_sign_is_a_url_not_an_email():
    url = "https://medium.com/@john.doe/how-i-built-an-explainable-resume-analyzer-with-fastapi-and-python-3b9a1c2d4e5f"
    text, counts = redact(url)
    assert text == "[URL]"
    assert (counts.emails, counts.urls) == (0, 1)


def test_oversized_address_starting_with_an_at_sign_is_removed():
    text, counts = redact("@" + "a" * 70 + "@gmail.com")
    assert "aaaa" not in text
    assert counts.emails == 1


@pytest.mark.parametrize(
    "safe",
    [
        "(1) 2019-2021",
        "(1) 100000 users",
        "(3) 12345",
        "Table (3) 2020-2021 results",
        "References: (1) 2019-2023 B.Tech, (2) 2023-2025 M.Tech",
        "Stipend: Rs. 62500-87500",
        "Rs 62500-87500",
        "INR 62500-87500",
        "₹ 62500 - 87500",
        "CTC Rs. 65500 - 75500 pm",
        "Credential ID: UC-5d2c48c0-b065-9454-1840-dc0dafed5668",
    ],
)
def test_review_round_two_false_positives_stay_fixed(safe):
    text, counts = redact(safe)
    assert text == safe
    assert counts.model_dump() == {"emails": 0, "phones": 0, "urls": 0}


@pytest.mark.parametrize(
    "landline",
    ["Ph: 022 20350636", "Ph: 022-20990695", "Ph: 011-20120512", "Tel: 080-20450315"],
)
def test_landline_tails_that_only_look_like_dates_are_still_redacted(landline):
    text, counts = redact(landline)
    assert counts.phones == 1
    assert not any(ch.isdigit() for ch in text)


@pytest.mark.parametrize(
    "phone",
    ["+33 1 23 45 67 89", "+33 6 12 34 56 78", "+91 98 76 54 32 10", "+91 98765 43210"],
)
def test_pair_grouped_and_unicode_spaced_numbers(phone):
    text, counts = redact(f"Call {phone}")
    assert text == "Call [PHONE]"


@pytest.mark.parametrize("site", ["ab.tech/portfolio", "Website: ab.tech", "me.tech/resume"])
def test_real_tech_domains_are_still_links(site):
    _, counts = redact(site)
    assert counts.urls == 1


def test_non_ascii_top_level_domain_email_is_redacted():
    text, counts = redact("jane@example.рф")
    assert text == "[EMAIL]" and counts.emails == 1
