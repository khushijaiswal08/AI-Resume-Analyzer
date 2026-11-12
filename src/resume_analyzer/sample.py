"""The fictional sample resume and job description behind the "Try a sample" button."""

from importlib import resources

from pydantic import BaseModel

SAMPLE_ROLE_ID = "ml-engineer"
SAMPLE_FILENAME = "ada_testwell_sample.txt"


class SampleResponse(BaseModel):
    """Response of `GET /api/sample`. Post `resume_text` as a .txt upload to analyse it."""

    name: str
    filename: str
    resume_text: str
    job_description: str
    role_id: str


def load_sample() -> SampleResponse:
    """Read the packaged sample files (fictional person, example.com email, 555 phone)."""
    data = resources.files("resume_analyzer").joinpath("data")
    return SampleResponse(
        name="Ada Testwell (fictional ML engineer)",
        filename=SAMPLE_FILENAME,
        resume_text=data.joinpath("sample_resume.txt").read_text("utf-8"),
        job_description=data.joinpath("sample_jd.txt").read_text("utf-8"),
        role_id=SAMPLE_ROLE_ID,
    )
