"""Layer 8: privacy view.

Shows the exact text an LLM would receive, so a user can verify the redaction guardrail
without trusting a claim. It works with no API key: it is the output of the same `redact()`
that runs before every real LLM call.
"""

from resume_analyzer.models import RedactionCounts
from resume_analyzer.redaction import redact
from resume_analyzer.schemas import RedactedPreview

NOTE_ACTIVE = (
    "This is the resume text an AI model receives. Emails, phone numbers and links are "
    "replaced by [EMAIL], [PHONE] and [URL] before sending. Your name and other text are "
    "not removed. The prompt also contains a list of skill names found in your resume."
)
NOTE_INACTIVE = (
    "No AI key is configured on this server, so nothing is sent to any AI model. This is "
    "what would be sent if one were: emails, phone numbers and links are replaced, but your "
    "name and other text are not."
)


def build_redacted_preview(
    text: str, jd_text: str | None, *, llm_configured: bool
) -> RedactedPreview:
    """Redact the resume (and JD) and report how much was removed, resume and JD combined."""
    redacted, counts = redact(text)
    redacted_jd, jd_counts = redact(jd_text) if jd_text else (None, RedactionCounts())
    return RedactedPreview(
        text=redacted,
        jd_text=redacted_jd,
        emails=counts.emails + jd_counts.emails,
        phones=counts.phones + jd_counts.phones,
        urls=counts.urls + jd_counts.urls,
        llm_configured=llm_configured,
        note=NOTE_ACTIVE if llm_configured else NOTE_INACTIVE,
    )
