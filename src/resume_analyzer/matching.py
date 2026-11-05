"""Compare resume skills with the skills a job description asks for."""

from resume_analyzer.models import JDMatch
from resume_analyzer.skills import extract_skills, flatten


def extract_jd_skills(jd_text: str) -> list[str]:
    """Skills mentioned in the job description, using the same taxonomy as the resume."""
    return flatten(extract_skills(jd_text))


def match_skills(resume_skills: list[str], jd_skills: list[str]) -> JDMatch:
    """Split JD skills into matched/missing and compute the match percentage.

    The percentage is "share of JD skills the resume mentions". If the JD contains no
    recognised skills, the percentage is 0 (the caller adds a warning).
    """
    resume_set = {skill.lower() for skill in resume_skills}
    matched = [skill for skill in jd_skills if skill.lower() in resume_set]
    missing = [skill for skill in jd_skills if skill.lower() not in resume_set]
    percent = round(100 * len(matched) / len(jd_skills)) if jd_skills else 0
    return JDMatch(match_percent=percent, matched=matched, missing=missing)
