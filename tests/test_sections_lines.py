from resume_analyzer.sections import split_lines


def test_split_lines_offsets_and_sections():
    text = "Name\n\nSkills\nPython, SQL\n\n  Experience\n- Built a thing 5 times\n"
    lines = split_lines(text)
    assert [line.text for line in lines] == [
        "Name",
        "Skills",
        "Python, SQL",
        "Experience",
        "- Built a thing 5 times",
    ]
    for line in lines:
        assert text[line.start : line.end] == line.text  # offsets are exact
    assert [line.section for line in lines] == [
        None,
        "skills",
        "skills",
        "experience",
        "experience",
    ]
    assert [line.is_heading for line in lines] == [False, True, False, True, False]


def test_inline_heading_belongs_to_its_section():
    (line,) = split_lines("Skills: Python, SQL")
    assert line.section == "skills" and line.is_heading


def test_crlf_offsets():
    text = "Skills\r\nPython\r\n"
    assert [text[line.start : line.end] for line in split_lines(text)] == ["Skills", "Python"]
