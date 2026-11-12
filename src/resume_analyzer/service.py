"""The analysis pipeline: parse -> redact -> sections/skills/match -> score -> (optional) LLM.

Deterministic steps run first and always succeed on valid input. The LLM step is optional,
runs on redacted text only, and its output is checked by guardrails before it is returned.
"""

import logging
import re
import time

from resume_analyzer.ats_checks import run_ats_checks
from resume_analyzer.bullets import analyze_bullets
from resume_analyzer.config import Settings
from resume_analyzer.dates import estimate_years
from resume_analyzer.evidence import build_evidence
from resume_analyzer.jd import analyze_jd
from resume_analyzer.llm.base import LLMClient, LLMError
from resume_analyzer.llm.guard import MAX_ITEM_CHARS  # noqa: F401  (re-exported for tests)
from resume_analyzer.llm.guard import clean as _clean
from resume_analyzer.llm.prompts import SYSTEM_INSTRUCTION, build_analysis_prompt
from resume_analyzer.matching import extract_jd_skills, match_skills
from resume_analyzer.models import (
    AnalysisResult,
    InterviewQuestion,
    LLMInsights,
    LLMResult,
)
from resume_analyzer.parsing import ParseError, extract_text
from resume_analyzer.privacy import build_redacted_preview
from resume_analyzer.readability import analyze_readability
from resume_analyzer.readiness import build_readiness
from resume_analyzer.redaction import redact
from resume_analyzer.rewrites import ground_rewrites, pick_weakest
from resume_analyzer.roles import get_role, role_fit
from resume_analyzer.schemas import BulletItem
from resume_analyzer.scoring import score_resume
from resume_analyzer.sections import detect_sections, split_lines
from resume_analyzer.skill_evidence import build_skill_evidence
from resume_analyzer.skills import extract_skills, find_skill_mentions, flatten

logger = logging.getLogger(__name__)

MAX_SUGGESTIONS = 8
MAX_QUESTIONS = 10
MAX_FIRST_IMPRESSION_SENTENCES = 3

NO_KEY_REASON = "LLM not configured (GEMINI_API_KEY is not set); deterministic results only."


class JobDescriptionTooLongError(ParseError):
    """The pasted job description is over the character limit."""

    status_code = 413


class UnknownRoleError(ParseError):
    """The `role` form field is not an id from `GET /api/roles`."""

    status_code = 422


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
    role: str | None = None,
) -> AnalysisResult:
    """Analyse an uploaded file (PDF/DOCX/TXT bytes). Raises ParseError subclasses on bad input."""
    started = time.perf_counter()
    jd_text = _validate_jd(jd_text, settings.max_jd_chars)
    role = _validate_role(role)
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
    result = analyze_text(parsed.text, jd_text, llm_client=llm_client, warnings=warnings, role=role)
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


def _validate_role(role: str | None) -> str | None:
    """Blank means no role; anything else must be a known role id."""
    if role is None or not role.strip():
        return None
    role = role.strip()
    if get_role(role) is None:
        raise UnknownRoleError(f"Unknown role '{role[:40]}'. Use an id from GET /api/roles.")
    return role


def analyze_text(
    text: str,
    jd_text: str | None = None,
    *,
    llm_client: LLMClient | None = None,
    warnings: list[str] | None = None,
    role: str | None = None,
) -> AnalysisResult:
    """Run the full pipeline on already-extracted resume text.

    Order matters for the "LLM never changes a score" rule: every number is computed first,
    then the LLM is asked for words, then the (already final) numbers are returned.
    """
    warnings = list(warnings or [])
    role = _validate_role(role)
    redacted_text, redaction = redact(text)

    sections = detect_sections(text)
    skills = extract_skills(text)
    skill_list = flatten(skills)
    word_count = len(text.split())
    lines = split_lines(text)
    mentions = find_skill_mentions(text)

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

    # --- v2 deterministic layers (pure functions, no LLM) ---
    bullets = analyze_bullets(lines)
    ats_checks = run_ats_checks(text, lines, sections)
    skill_evidence = build_skill_evidence(text, mentions, lines)
    jd_analysis = analyze_jd(jd_text, skill_evidence, estimate_years(lines)) if jd_text else None
    role_info = get_role(role) if role else None
    role_result = role_fit(role_info, skill_list) if role_info else None
    readability = analyze_readability(text, bullets)
    evidence = build_evidence(
        text=text,
        lines=lines,
        sections=sections,
        mentions=mentions,
        ats_score=ats_score,
        jd_match=jd_match,
    )
    if jd_analysis is not None and jd_analysis.weighted_percent is not None:
        fit_percent, fit_label = jd_analysis.weighted_percent, "Job match"
    elif role_result is not None:
        fit_percent, fit_label = role_result.fit_percent, "Role fit"
    else:
        fit_percent, fit_label = None, None
    readiness = build_readiness(
        ats_total=ats_score.total,
        bullet_average=bullets.average_score,
        parse_score=ats_checks.score,
        fit_percent=fit_percent,
        fit_label=fit_label,
    )
    preview = build_redacted_preview(text, jd_text, llm_configured=llm_client is not None)

    llm = run_llm(
        llm_client,
        redacted_text=redacted_text,
        redacted_jd=redacted_jd,
        allowed_skills=_unique([*skill_list, *jd_skills]),
        warnings=warnings,
        weak_bullets=pick_weakest(bullets.items),
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
        resume_text=text,
        bullets=bullets,
        ats_checks=ats_checks,
        jd_analysis=jd_analysis,
        role_fit=role_result,
        readability=readability,
        skill_evidence=skill_evidence,
        evidence=evidence,
        redacted_preview=preview,
        readiness=readiness,
    )


def run_llm(
    llm_client: LLMClient | None,
    *,
    redacted_text: str,
    redacted_jd: str | None,
    allowed_skills: list[str],
    warnings: list[str],
    weak_bullets: list[BulletItem] | None = None,
) -> LLMResult:
    """Ask the LLM for insights and apply guardrails. Never raises: failures become a reason."""
    if llm_client is None:
        return LLMResult(used=False, reason=NO_KEY_REASON)

    weak_bullets = weak_bullets or []
    # Bullets come from the original text, so they are redacted before they go in the prompt.
    prompt = build_analysis_prompt(
        redacted_text,
        redacted_jd,
        allowed_skills,
        [redact(bullet.text)[0] for bullet in weak_bullets],
    )
    try:
        insights = llm_client.generate_json(
            prompt, LLMInsights, system_instruction=SYSTEM_INSTRUCTION
        )
    except LLMError as exc:
        return LLMResult(used=False, reason=f"LLM unavailable: {exc}")
    except Exception as exc:  # a bug in a client must not break the deterministic results
        logger.exception("Unexpected LLM client failure")
        return LLMResult(used=False, reason=f"LLM unavailable ({type(exc).__name__}).")

    return apply_guardrails(insights, allowed_skills, warnings, weak_bullets)


def apply_guardrails(
    insights: LLMInsights,
    allowed_skills: list[str],
    warnings: list[str],
    weak_bullets: list[BulletItem] | None = None,
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
    impression, ungrounded_impression = _ground_summary(_clean(insights.first_impression), allowed)
    if ungrounded_impression:
        warnings.append(
            "Removed first-impression sentence(s) mentioning skills not found in the resume "
            f"or job description: {_names(ungrounded_impression)}."
        )
    sentences = re.split(r"(?<=[.!?])\s+", impression)
    impression = " ".join(sentences[:MAX_FIRST_IMPRESSION_SENTENCES])

    # Rewrites may only reword the bullets we sent, and may not add numbers or skills.
    rewrites = ground_rewrites(
        [(item.original, item.rewrite) for item in insights.bullet_rewrites],
        weak_bullets or [],
        warnings,
    )
    return LLMResult(
        used=True,
        reason=None,
        summary=summary or None,
        suggestions=suggestions[:MAX_SUGGESTIONS],
        interview_questions=questions[:MAX_QUESTIONS],
        first_impression=impression or None,
        bullet_rewrites=rewrites,
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


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
