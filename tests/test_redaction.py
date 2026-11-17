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
