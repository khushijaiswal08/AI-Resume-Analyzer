from resume_analyzer.bullets import analyze_bullets
from resume_analyzer.readability import analyze_readability, find_passive
from resume_analyzer.sections import split_lines
from tests.conftest import read_eval


def run(text: str):
    return analyze_readability(text, analyze_bullets(split_lines(text)))


def bullets(*items: str) -> str:
    return "Experience\n" + "\n".join(f"- {item}" for item in items) + "\n"


def test_passive_detection_and_false_friends():
    assert find_passive("The model was deployed on AWS").group(1) == "deployed"
    assert find_passive("Reports were quickly reviewed by the lead")
    assert find_passive("A tool was built by me")
    assert find_passive("I was interested in data") is None  # adjective, not passive
    assert find_passive("Deployed the model on AWS") is None


def test_passive_rate_and_examples_have_valid_offsets():
    text = bullets(
        "Models were deployed to production for 4 internal teams every single week.",
        "Built a dashboard that tracks 12 sales metrics for the whole organisation.",
        "Reports are generated nightly by a scheduled job across 3 regions at once.",
    )
    result = run(text)
    assert result.passive_count == 2 and result.passive_rate_percent == 67
    for example in result.passive_examples:
        assert text[example.start : example.end] == example.text
    assert any("passive voice" in note for note in result.notes)


def test_repeated_verbs_with_alternatives():
    text = bullets(
        *[f"Developed feature number {i} for the platform with 3 teams in total." for i in range(4)]
    )
    result = run(text)
    (repeat,) = result.repeated_verbs
    assert repeat.verb == "Developed" and repeat.count == 4
    assert "Built" in repeat.alternatives and "Developed" not in repeat.alternatives
    assert any("'Developed' starts 4 bullets" in note for note in result.notes)


def test_two_repeats_are_not_flagged_and_unknown_verbs_get_generic_alternatives():
    assert (
        run(
            bullets("Developed a thing for 3 teams.", "Developed another thing for 4 teams.")
        ).repeated_verbs
        == []
    )
    text = bullets(*["Analysed dataset number " + str(i) + " for 3 teams." for i in range(3)])
    assert run(text).repeated_verbs[0].alternatives  # "Analysed" is not in the bank: generic list


def test_buzzword_density_counts_whole_text():
    text = "Summary\nA dynamic, passionate and motivated self-starter.\n" + bullets(
        "Built 4 things for 3 teams."
    )
    result = run(text)
    assert {item.term for item in result.buzzwords} == {
        "dynamic",
        "passionate",
        "motivated",
        "self-starter",
    }
    assert result.buzzword_density > 1 and any("buzzwords per 100 words" in n for n in result.notes)


def test_bullet_length_note():
    short = run(bullets("Built things.", "Fixed bugs.", "Wrote docs."))
    assert short.avg_bullet_words == 2.0 and any("short" in note for note in short.notes)


def test_no_bullets_gives_none_metrics():
    result = run("Skills\nPython\n")
    assert result.bullet_count == 0 and result.avg_bullet_words is None
    assert result.passive_rate_percent is None and result.passive_examples == []


def test_strong_sample_is_clean_and_weak_sample_is_noisy():
    strong = run(read_eval("samples/ada_testwell_ml.txt"))
    weak = run(read_eval("quality_samples/weak_pat_generic.txt"))
    assert strong.buzzword_density == 0 and not any("buzzwords" in n for n in strong.notes)
    assert weak.buzzword_density > 1 and weak.passive_count >= 1
