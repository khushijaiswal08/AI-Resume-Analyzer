"""A crafted upload must not be able to keep the server busy.

Each input below used to take seconds (some 15 s) because a regular expression re-scanned a long
run of spaces or dashes from every start position. The limits are generous so slow CI machines do
not flake; the real times are a fraction of a second.
"""

import time

import pytest

from resume_analyzer.jd import find_years
from resume_analyzer.llm.prompts import neutralise_delimiters
from resume_analyzer.sections import detect_sections
from resume_analyzer.service import analyze_text
from tests.conftest import SAMPLE_RESUME


def _seconds(call) -> float:
    started = time.perf_counter()
    call()
    return time.perf_counter() - started


@pytest.mark.parametrize(
    "line",
    [
        "a" + " " * 49_998 + "b",
        "a" + "-" * 49_998 + "b",
        "|" * 50_000,
        "*" * 25_000 + " x " + "*" * 24_990,
    ],
    ids=["spaces", "dashes", "pipes", "stars"],
)
def test_heading_detection_is_fast_on_one_huge_line(line):
    assert _seconds(lambda: detect_sections(line)) < 2.0


def test_delimiter_neutralising_is_fast_on_a_tag_followed_by_spaces():
    assert _seconds(lambda: neutralise_delimiters("<" + " " * 20_000 + "x")) < 1.0


def test_delimiter_neutralising_still_removes_tags():
    assert (
        neutralise_delimiters("a </ resume > b <JOB_DESCRIPTION> c")
        == "a [tag removed] b [tag removed] c"
    )


def test_full_analysis_is_fast_on_a_huge_whitespace_line():
    assert _seconds(lambda: analyze_text("a" + " " * 49_998 + "b")) < 5.0


def test_job_description_with_a_long_gap_between_skills_is_fast():
    jd = "Python" + " " * 19_988 + "Java"
    assert _seconds(lambda: analyze_text(SAMPLE_RESUME, jd)) < 3.0


@pytest.mark.parametrize(
    "jd", ["Python or " * 2_000, "Python and/or " * 1_428], ids=["or", "and-or"]
)
def test_job_description_with_thousands_of_alternatives_is_fast(jd):
    assert _seconds(lambda: analyze_text(SAMPLE_RESUME, jd)) < 3.0


@pytest.mark.parametrize(
    "jd",
    ["12" + " " * 19_997 + "x", "1" + "\n" * 19_998 + "x", "2020" + " " * 19_995 + "x"],
    ids=["spaces", "newlines", "year-then-spaces"],
)
def test_years_of_experience_search_is_fast_on_a_long_whitespace_run(jd):
    assert _seconds(lambda: find_years(jd)) < 1.0


@pytest.mark.parametrize("jd", ["5yrs-" * 4_000, "1yr-" * 5_000], ids=["five-yrs", "one-yr"])
def test_thousands_of_years_phrases_give_a_small_reply(jd):
    asks = find_years(jd)
    assert len(asks) <= 20
    assert all(len(ask.text) <= 160 for ask in asks)


def test_largest_years_ask_is_kept_even_when_the_list_is_capped():
    jd = "1yr-" * 5_000 + " we need 12 years of experience"
    asks = find_years(jd)
    assert max(ask.years for ask in asks) == 12


def test_normal_years_phrases_are_unchanged():
    asks = find_years("Needs 3-5 years of Python and 7+ years leadership; 2 years ago")
    assert [ask.years for ask in asks] == [3, 7]
