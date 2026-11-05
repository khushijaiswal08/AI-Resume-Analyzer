"""The analysis pipeline: parse -> redact -> sections/skills/match -> score -> (optional) LLM.

Deterministic steps run first and always succeed on valid input. The LLM step is optional,
runs on redacted text only, and its output is checked by guardrails before it is returned.
"""

import logging
import re
import time

from resume_analyzer.config import Settings
from resume_analyzer.llm.base import LLMClient, LLMError
from resume_analyzer.llm.prompts import SYSTEM_INSTRUCTION, build_analysis_prompt
from resume_analyzer.matching import extract_jd_skills, match_skills
from resume_analyzer.models import (
    AnalysisResult,
    InterviewQuestion,
    LLMInsights,
    LLMResult,
)
from resume_analyzer.parsing import ParseError, extract_text
from resume_analyzer.redaction import redact
from resume_analyzer.scoring import score_resume
from resume_analyzer.sections import detect_sections
from resume_analyzer.skills import extract_skills, flatten

logger = logging.getLogger(__name__)

MAX_SUGGESTIONS = 8
MAX_QUESTIONS = 10
MAX_ITEM_CHARS = 300

NO_KEY_REASON = "LLM not configured (GEMINI_API_KEY is not set); deterministic results only."


class JobDescriptionTooLongError(ParseError):
    """The pasted job description is over the character limit."""

    status_code = 413


def build_llm_client(settings: Settings) -> LLMClient | None:
    """Create the Gemini client if an API key is configured, otherwise return None."""
    if settings.gemini_api_key is None:
        return None
    from resume_analyzer.llm.gemini import GeminiClient

    return GeminiClient(
        api_key=settings.gemini_api_key.get_secret_value(),
        model=settings.gemini_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


def analyze_document(
    data: bytes,
    jd_text: str | None,
    *,
    settings: Settings,
    llm_client: LLMClient | None,
) -> AnalysisResult:
    """Analyse an uploaded file (PDF/DOCX/TXT bytes). Raises ParseError subclasses on bad input."""
    started = time.perf_counter()
    jd_text = _validate_jd(jd_text, settings.max_jd_chars)
    parsed = extract_text(
        data,
        max_bytes=settings.max_upload_bytes,
        max_pdf_pages=settings.max_pdf_pages,
        max_chars=settings.max_text_chars,
    )
    warnings = list(parsed.warnings)
    if parsed.truncated:
        warnings.append(
            f"Resume text was longer than {settings.max_text_chars} characters and was truncated."
        )
    result = analyze_text(parsed.text, jd_text, llm_client=llm_client, warnings=warnings)
    # Log sizes, counts and timings only - never resume or JD content.
    logger.info(
        "analyzed type=%s bytes=%d chars=%d words=%d skills=%d jd=%s llm_used=%s ms=%.0f",
        parsed.file_type,
        len(data),
        len(parsed.text),
        result.word_count,
        len(flatten(result.skills)),
        jd_text is not None,
        result.llm.used,
        (time.perf_counter() - started) * 1000,
    )
    return result


def _validate_jd(jd_text: str | None, max_chars: int) -> str | None:
    if jd_text is None or not jd_text.strip():
        return None
    if len(jd_text) > max_chars:
        raise JobDescriptionTooLongError(
            f"Job description is longer than the {max_chars}-character limit."
        )
    return jd_text.strip()


def analyze_text(
    text: str,
    jd_text: str | None = None,
    *,
    llm_client: LLMClient | None = None,
    warnings: list[str] | None = None,
) -> AnalysisResult:
    """Run the full pipeline on already-extracted resume text."""
    warnings = list(warnings or [])
    redacted_text, redaction = redact(text)

    sections = detect_sections(text)
    skills = extract_skills(text)
    skill_list = flatten(skills)
    word_count = len(text.split())

    jd_match = None
    jd_skills: list[str] = []
    redacted_jd = None
    if jd_text:
        jd_skills = extract_jd_skills(jd_text)
        redacted_jd, _ = redact(jd_text)
        if jd_skills:
            jd_match = match_skills(skill_list, jd_skills)
        else:
            # Nothing to compare against: scoring 0/10 would punish the resume for a
            # problem in the JD, so score it as if no JD was given.
            warnings.append(
                "No recognised skills were found in the job description, so JD keyword "
                "coverage was not scored; its weight was redistributed across the other "
                "criteria."
            )
    else:
        warnings.append(
            "No job description provided: the JD keyword weight was redistributed "
            "across the other criteria."
        )

    ats_score = score_resume(
        text=redacted_text,
        sections=sections,
        skill_count=len(skill_list),
        word_count=word_count,
        redaction=redaction,
        jd_match=jd_match,
    )

    llm = run_llm(
        llm_client,
        redacted_text=redacted_text,
        redacted_jd=redacted_jd,
        allowed_skills=_unique([*skill_list, *jd_skills]),
        warnings=warnings,
    )

    return AnalysisResult(
        skills=skills,
        sections=sections,
        word_count=word_count,
        ats_score=ats_score,
        jd_match=jd_match,
        llm=llm,
        redaction=redaction,
        warnings=warnings,
    )


def run_llm(
    llm_client: LLMClient | None,
    *,
    redacted_text: str,
    redacted_jd: str | None,
    allowed_skills: list[str],
    warnings: list[str],
) -> LLMResult:
    """Ask the LLM for insights and apply guardrails. Never raises: failures become a reason."""
    if llm_client is None:
        return LLMResult(used=False, reason=NO_KEY_REASON)

    prompt = build_analysis_prompt(redacted_text, redacted_jd, allowed_skills)
    try:
        insights = llm_client.generate_json(
            prompt, LLMInsights, system_instruction=SYSTEM_INSTRUCTION
        )
    except LLMError as exc:
        return LLMResult(used=False, reason=f"LLM unavailable: {exc}")
    except Exception as exc:  # a bug in a client must not break the deterministic results
        logger.exception("Unexpected LLM client failure")
        return LLMResult(used=False, reason=f"LLM unavailable ({type(exc).__name__}).")

    return apply_guardrails(insights, allowed_skills, warnings)


def apply_guardrails(
    insights: LLMInsights, allowed_skills: list[str], warnings: list[str]
) -> LLMResult:
    """Ground, bound and re-redact LLM output before it reaches the user.

    Appends human-readable warnings to `warnings` whenever something is dropped.
    """
    allowed = {skill.lower(): skill for skill in allowed_skills}

    questions, dropped = _ground_questions(insights.interview_questions, allowed)
    if dropped:
        warnings.append(
            f"Dropped {len(dropped)} interview question(s) about skills not found in the "
            f"resume or job description: {_names(dropped)}."
        )

    suggestions: list[str] = []
    ungrounded_suggestions: list[str] = []
    for item in insights.suggestions:
        text = _clean(item)
        extra = _ungrounded_skills(text, allowed)
        if extra:
            ungrounded_suggestions.extend(extra)
        elif text:
            suggestions.append(text)
    if ungrounded_suggestions:
        warnings.append(
            "Dropped suggestion(s) mentioning skills not found in the resume or job "
            f"description: {_names(ungrounded_suggestions)}."
        )
    if len(suggestions) > MAX_SUGGESTIONS:
        warnings.append(f"LLM returned {len(suggestions)} suggestions; kept {MAX_SUGGESTIONS}.")
    if len(questions) > MAX_QUESTIONS:
        warnings.append(f"LLM returned {len(questions)} questions; kept {MAX_QUESTIONS}.")

    summary, ungrounded_summary = _ground_summary(_clean(insights.summary), allowed)
    if ungrounded_summary:
        warnings.append(
            "Removed summary sentence(s) mentioning skills not found in the resume or job "
            f"description: {_names(ungrounded_summary)}."
        )
    return LLMResult(
        used=True,
        reason=None,
        summary=summary or None,
        suggestions=suggestions[:MAX_SUGGESTIONS],
        interview_questions=questions[:MAX_QUESTIONS],
    )


def _ungrounded_skills(text: str, allowed: dict[str, str]) -> list[str]:
    """Taxonomy skills mentioned in an LLM string that are not in the resume or JD.

    The same deterministic extractor that reads the resume reads the LLM's text, so
    "grounded" means exactly "a skill we found ourselves". Soft skills are skipped: words
    like "communication" or "presentations" appear naturally in advice and are not claims
    about the candidate's technical experience.
    """
    mentioned = extract_skills(text)
    mentioned.pop("soft", None)
    return [skill for skill in flatten(mentioned) if skill.lower() not in allowed]


def _ground_questions(
    questions: list[InterviewQuestion], allowed: dict[str, str]
) -> tuple[list[InterviewQuestion], list[str]]:
    """Keep questions whose tagged skill and question text are grounded.

    Returns (kept, names of the ungrounded skills that caused a drop).
    """
    kept: list[InterviewQuestion] = []
    dropped: list[str] = []
    for question in questions:
        skill = allowed.get(question.skill.strip().lower())
        text = _clean(question.question)
        extra = _ungrounded_skills(text, allowed)
        if skill is None:
            dropped.append(question.skill.strip()[:50] or "(blank)")
        elif extra:
            # Tagged with a real skill but asks about another one (e.g. tag "Python",
            # text "Explain Kubernetes operators"): the tag alone is not enough.
            dropped.extend(extra)
        elif text:
            kept.append(
                InterviewQuestion(question=text, skill=skill, difficulty=question.difficulty)
            )
    return kept, dropped


def _ground_summary(summary: str, allowed: dict[str, str]) -> tuple[str, list[str]]:
    """Remove summary sentences that mention ungrounded skills; return (summary, removed)."""
    kept: list[str] = []
    removed: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", summary):
        extra = _ungrounded_skills(sentence, allowed)
        if extra:
            removed.extend(extra)
        elif sentence:
            kept.append(sentence)
    return " ".join(kept), removed


def _names(skills: list[str]) -> str:
    return ", ".join(sorted(set(skills)))


def _clean(text: str) -> str:
    """Trim, re-redact (defence in depth) and cap one LLM string at MAX_ITEM_CHARS."""
    text, _ = redact(" ".join(text.split()))
    if len(text) > MAX_ITEM_CHARS:
        text = text[: MAX_ITEM_CHARS - 1].rstrip() + "…"
    return text


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
