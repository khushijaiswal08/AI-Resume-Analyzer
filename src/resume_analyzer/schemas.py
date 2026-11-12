"""Response models for the v2 analysis layers.

They live in their own module (not models.py) so every layer module can import its result
type without importing models.py, which imports this file: no import cycles.
All offsets are Python string indexes into `AnalysisResult.resume_text`.
"""

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["pass", "warn", "fail"]


class Snippet(BaseModel):
    """A piece of the resume text: `resume_text[start:end] == text`."""

    start: int
    end: int
    text: str


class Issue(BaseModel):
    """A problem found in a bullet. `code` is stable and machine-readable."""

    code: str
    message: str


class BulletItem(BaseModel):
    """One experience/project bullet with its 0-100 quality score."""

    text: str
    start: int
    end: int
    section: str
    score: int = Field(ge=0, le=100)
    rating: Literal["strong", "ok", "weak"]
    word_count: int
    issues: list[Issue]
    hint: str | None = None  # a template to follow, never invented facts or numbers


class BulletReport(BaseModel):
    """All bullets plus a summary. `average_score` is None when no bullets were found."""

    count: int
    average_score: int | None
    strong: int
    ok: int
    weak: int
    items: list[BulletItem]


class ATSCheck(BaseModel):
    """One line of the parse-ability checklist."""

    id: str
    title: str
    status: Status
    detail: str
    fix: str | None = None
    evidence: list[Snippet] = Field(default_factory=list)


class ATSChecks(BaseModel):
    """Parse-ability checklist. `score` = (pass + half of warn) / total, as 0-100."""

    score: int = Field(ge=0, le=100)
    passed: int
    warned: int
    failed: int
    items: list[ATSCheck]


class JDRequirement(BaseModel):
    """One skill asked for by the job description and how the resume covers it."""

    skill: str
    category: str
    priority: Literal["required", "preferred"]
    weight: int
    status: Literal["matched", "missing", "covered_by_alternative"]
    demonstrated: bool | None = None  # only for matched skills: used in experience/projects?
    alternatives: list[str] = Field(default_factory=list)  # "X or Y" partners in the JD
    where_to_add: list[str] = Field(default_factory=list)  # resume sections to put it in
    hint: str | None = None


class YearsAsk(BaseModel):
    """A "N years" phrase from the JD."""

    years: int
    text: str


class JDAnalysis(BaseModel):
    """Weighted JD match: required skills count double. Percentages are None if nothing to score."""

    weighted_percent: int | None
    required_percent: int | None
    preferred_percent: int | None
    required_count: int
    preferred_count: int
    requirements: list[JDRequirement]
    years_asked: list[YearsAsk]
    years_required: int | None
    resume_years_estimate: float | None
    seniority: Literal["entry", "mid", "senior", "lead"] | None
    notes: list[str]


class LearnNext(BaseModel):
    """A missing role skill with a hint about what the candidate already knows."""

    skill: str
    priority: Literal["core", "bonus"]
    related_you_have: list[str]
    hint: str


class RoleFit(BaseModel):
    """How well the resume's skills cover a target role's profile."""

    role_id: str
    role_name: str
    fit_percent: int = Field(ge=0, le=100)
    core_matched: list[str]
    core_missing: list[str]
    bonus_matched: list[str]
    bonus_missing: list[str]
    learn_next: list[LearnNext]


class RoleInfo(BaseModel):
    """Entry of `GET /api/roles`."""

    id: str
    name: str
    description: str
    core: list[str]
    bonus: list[str]


class RepeatedVerb(BaseModel):
    """An action verb that starts several bullets."""

    verb: str
    count: int
    alternatives: list[str]


class BuzzwordCount(BaseModel):
    term: str
    count: int


class Readability(BaseModel):
    """Tone and readability metrics. Rates are percentages, density is per 100 words."""

    bullet_count: int
    avg_bullet_words: float | None
    passive_count: int
    passive_rate_percent: int | None
    passive_examples: list[Snippet]
    buzzwords: list[BuzzwordCount]
    buzzword_density: float
    repeated_verbs: list[RepeatedVerb]
    notes: list[str]


class SkillUse(BaseModel):
    """Where one skill appears in the resume."""

    skill: str
    category: str
    mentions: int
    in_skills_section: int
    in_experience: int
    in_projects: int
    elsewhere: int
    status: Literal["demonstrated", "listed_only", "mentioned"]
    locations: list[Snippet]  # up to 3 mentions, for highlighting


class SkillEvidence(BaseModel):
    """Skill depth signals. `listed_only` skills appear in the skills list but nowhere else."""

    demonstrated: int
    listed_only: int
    mentioned: int
    listed_only_skills: list[str]
    skills: list[SkillUse]


class EvidenceItem(BaseModel):
    """A snippet that earned or cost points for a criterion."""

    start: int
    end: int
    text: str
    kind: Literal["earned", "lost"]
    note: str | None = None


class CriterionEvidence(BaseModel):
    """Evidence for one ATS score criterion, in the same order as `ats_score.breakdown`."""

    id: str
    criterion: str  # same label as ats_score.breakdown[].criterion
    snippets: list[EvidenceItem]
    missing: list[str]  # things that are absent and so cannot be highlighted


class RedactedPreview(BaseModel):
    """The exact text an LLM would receive: after redaction, nothing else."""

    text: str
    jd_text: str | None
    emails: int
    phones: int
    urls: int
    llm_configured: bool
    note: str


class ReadinessComponent(BaseModel):
    id: str
    label: str
    score: int
    weight: int  # effective share of the composite, in percent; weights sum to 100
    note: str


class Readiness(BaseModel):
    """Composite view that sits beside (never replaces) the v1 ATS score."""

    score: int = Field(ge=0, le=100)
    label: str
    components: list[ReadinessComponent]
    explanation: str


class BulletRewrite(BaseModel):
    """An LLM rewrite of one weak bullet that passed the grounding checks."""

    original: str
    rewrite: str
    score_before: int
    start: int
    end: int
