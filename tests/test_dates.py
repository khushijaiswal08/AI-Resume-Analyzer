from datetime import date

from resume_analyzer.dates import date_styles, estimate_years, has_date_range
from resume_analyzer.sections import split_lines

TODAY = date(2026, 6, 1)


def years(text: str) -> float | None:
    return estimate_years(split_lines(text), today=TODAY)


def test_date_styles_are_counted_separately():
    styles = date_styles("Jan 2022 - Mar 2023, January 2020, 05/2019, 2018-07, and 2017")
    assert styles == {
        "numeric (01/2022)": 1,
        "ISO (2022-01)": 1,
        "abbreviated month (Jan 2022)": 2,
        "full month (January 2022)": 1,
    }


def test_plain_years_are_neutral():
    assert date_styles("2019 - 2021 and 2022 - Present") == {}


def test_has_date_range():
    assert has_date_range("Engineer (2021 - 2024)")
    assert has_date_range("Jan 2021 to Present")
    assert not has_date_range("Built 2 services in 2021")


def test_estimate_years_merges_overlaps():
    text = "Experience\nA (2020 - 2022)\nB (2021 - 2023)\n"
    # 2020 Jan .. 2023 Dec = 4 years once merged (not 2 + 3)
    assert years(text) == 3.9


def test_estimate_years_present_and_months():
    assert years("Experience\nDev, Jan 2025 - Present\n") == 1.4  # Jan 2025 .. Jun 2026
    assert years("Experience\nDev, Jan 2021 - Jun 2021\n") == 0.4


def test_estimate_ignores_other_sections_and_returns_none_without_ranges():
    assert years("Education\nB.Sc. (2015 - 2019)\n") is None
    assert years("Experience\nNo dates here\n") is None


def test_numeric_and_iso_ranges_are_date_ranges():
    assert has_date_range("Engineer, Example Co 06/2018 - 08/2018")
    assert has_date_range("Engineer, Example Co 2018-06 - 2018-08")
    assert has_date_range("Engineer, Example Co 06/2018 - Present")
    assert not has_date_range("Shipped build 2018-06 and 06/2018")


def test_numeric_dated_header_counts_towards_years_and_is_not_a_bullet():
    from resume_analyzer.bullets import extract_bullets

    text = (
        "Experience\nEngineer, Example Co 01/2020 - 12/2021\n"
        "Analyst, Sample Ltd 2018-01 - 2019-12\n"
    )
    assert years(text) == 3.8
    assert extract_bullets(split_lines(text)) == []
