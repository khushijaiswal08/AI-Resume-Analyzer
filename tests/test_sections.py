import pytest

from resume_analyzer.sections import detect_sections
from tests.conftest import SAMPLE_RESUME


def test_detects_sections_in_sample():
    assert detect_sections(SAMPLE_RESUME) == [
        "summary",
        "experience",
        "education",
        "skills",
        "projects",
    ]


def test_heading_variants_and_decoration():
    text = "PROFESSIONAL SUMMARY\n## Work Experience\nTechnical Skills:\n--- Certifications ---"
    assert detect_sections(text) == ["summary", "experience", "skills", "certifications"]


def test_sentences_mentioning_section_words_are_not_headings():
    text = "I gained a lot of experience improving my communication skills in projects."
    assert detect_sections(text) == []


def test_output_order_is_canonical_not_document_order():
    assert detect_sections("Education\nSkills\nExperience") == ["experience", "education", "skills"]


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Skills: Python, SQL", ["skills"]),
        ("Technical Skills: Python", ["skills"]),
        ("Education: B.Sc. Computer Science, Sample University", ["education"]),
        ("Work Experience & Internships", ["experience"]),
        ("Education and Certifications", ["education", "certifications"]),
        ("Experience—", ["experience"]),
        ("– Projects –", ["projects"]),
    ],
)
def test_inline_combined_and_dash_decorated_headings(line, expected):
    assert detect_sections(line) == expected


def test_long_sentences_are_not_split_into_headings():
    sentence = "I am good at Python and skills and education and many more things"
    assert detect_sections(sentence) == []
    assert detect_sections("Note: my skills and education are listed further below") == []
