"""Pydantic models for everything the analyzer returns, plus the LLM output contract."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from resume_analyzer.schemas import (
    ATSChecks,
    BulletReport,
    BulletRewrite,
    CriterionEvidence,
    JDAnalysis,
    Readability,
    Readiness,
    RedactedPreview,
    RoleFit,
    SkillEvidence,
)

Difficulty = Literal["easy", "medium", "hard"]


class CriterionScore(BaseModel):
    """One line of the ATS score breakdown."""

    criterion: str
    score: int
    max: int
    reason: str


class ATSScore(BaseModel):
    """Deterministic, explainable score. `total` is always the sum of the breakdown scores."""

    total: int = Field(ge=0, le=100)
    breakdown: list[CriterionScore]


class JDMatch(BaseModel):
    """How well the resume's skills cover the skills found in the job description."""

    match_percent: int = Field(ge=0, le=100)
    matched: list[str]
    missing: list[str]


class InterviewQuestion(BaseModel):
    """A tailored interview question tied to one skill."""

    question: str
    skill: str
    difficulty: Difficulty = "medium"

    @field_validator("difficulty", mode="before")
    @classmethod
    def _normalise_difficulty(cls, value: object) -> object:
        # Models often answer "Medium" or " hard "; accept those instead of failing validation.
        return value.strip().lower() if isinstance(value, str) else value


class RewriteSuggestion(BaseModel):
    """The LLM's rewrite of one bullet we sent it. `original` must match a bullet we sent."""

    original: str
    rewrite: str


class LLMInsights(BaseModel):
    """The exact JSON shape we ask the LLM for. Anything else fails validation and is retried.

    `first_impression` and `bullet_rewrites` are optional so older/shorter answers stay valid.
    """

    summary: str = ""
    suggestions: list[str] = Field(default_factory=list)
    interview_questions: list[InterviewQuestion] = Field(default_factory=list)
    first_impression: str = ""
    bullet_rewrites: list[RewriteSuggestion] = Field(default_factory=list)


class LLMResult(BaseModel):
    """LLM section of the response. `used=False` always comes with a `reason`."""

    used: bool = False
    reason: str | None = None
    summary: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    interview_questions: list[InterviewQuestion] = Field(default_factory=list)
    first_impression: str | None = None  # 3-sentence "recruiter's first impression"
    bullet_rewrites: list[BulletRewrite] = Field(default_factory=list)  # grounded rewrites only


class RedactionCounts(BaseModel):
    """How many pieces of PII were removed before any LLM call."""

    emails: int = 0
    phones: int = 0
    urls: int = 0


class AnalysisResult(BaseModel):
    """Full response of `POST /api/analyze` and of the CLI's JSON output."""

    skills: dict[str, list[str]]
    sections: list[str]
    word_count: int
    ats_score: ATSScore
    jd_match: JDMatch | None = None
    llm: LLMResult
    redaction: RedactionCounts
    warnings: list[str] = Field(default_factory=list)
    # --- v2 additions (all deterministic except llm.*; offsets index into resume_text) ---
    resume_text: str = ""
    bullets: BulletReport | None = None
    ats_checks: ATSChecks | None = None
    jd_analysis: JDAnalysis | None = None  # only when a job description was given
    role_fit: RoleFit | None = None  # only when a role was chosen
    readability: Readability | None = None
    skill_evidence: SkillEvidence | None = None
    evidence: list[CriterionEvidence] = Field(default_factory=list)
    redacted_preview: RedactedPreview | None = None
    readiness: Readiness | None = None


class HealthResponse(BaseModel):
    """Response of `GET /api/health`."""

    status: str = "ok"
    llm_configured: bool
    version: str = ""
