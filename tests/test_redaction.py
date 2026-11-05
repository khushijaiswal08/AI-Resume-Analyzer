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
