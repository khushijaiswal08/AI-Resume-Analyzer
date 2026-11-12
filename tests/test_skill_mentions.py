from resume_analyzer.skills import extract_skills, find_skill_mentions, flatten


def test_mentions_have_exact_offsets_in_text_order():
    text = "I use Python and Docker; later Python again."
    mentions = find_skill_mentions(text)
    assert [(m.name, text[m.start : m.end]) for m in mentions] == [
        ("Python", "Python"),
        ("Docker", "Docker"),
        ("Python", "Python"),
    ]


def test_longest_match_wins_and_urls_are_blanked_but_offsets_stay_valid():
    text = "GitHub Actions at github.com/x/docker-tools then Docker"
    mentions = find_skill_mentions(text)
    assert [m.name for m in mentions] == ["GitHub Actions", "Docker"]
    assert text[mentions[1].start : mentions[1].end] == "Docker"


def test_extract_skills_is_consistent_with_mentions():
    text = "Python, JS, FastAPI, k8s, Docker"
    assert set(flatten(extract_skills(text))) == {m.name for m in find_skill_mentions(text)}


def test_mentions_are_capped_per_document():
    from resume_analyzer.skills import MAX_MENTIONS

    mentions = find_skill_mentions("Python, " * (MAX_MENTIONS + 200))
    assert len(mentions) == MAX_MENTIONS
