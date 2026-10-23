import pytest

from ai_shorts.spec import load_spec, parse_spec_text
from conftest import SCRIPT


def test_real_script_parses():
    spec = load_spec(SCRIPT)
    assert spec.slug == "001-aeo-baseline"
    assert spec.title == "Will AI ever cite my website?"
    assert [s.trigger for s in spec.steps] == ["one", "two", "three", "four"]
    assert spec.steps[0].label == "Write the questions down first"
    assert [(s.label, s.value) for s in spec.stats] == [("Rightmove", "104"), ("My site", "0")]
    assert spec.body.startswith("I asked ChatGPT")
    assert spec.body.endswith("Please don't DM me.")
    assert "sources" in spec.extra


def test_minimal_and_dict_stats():
    spec = parse_spec_text("---\nslug: x\ntitle: T\nstats:\n  - {label: Hits, value: '42%'}\n---\nHello there.\n")
    assert spec.steps == [] and spec.stats[0].value == "42%"
    assert spec.words == ["Hello", "there."]


@pytest.mark.parametrize("text", ["no front matter", "---\ntitle: T\n---\nbody", "---\nslug: s\n---\nbody"])
def test_bad_scripts_rejected(text):
    with pytest.raises(ValueError):
        parse_spec_text(text)


def test_real_script_beats():
    beats = load_spec(SCRIPT).beats
    assert [b.kind for b in beats] == ["chips", "counter", "counter"]
    assert [c.label for c in beats[0].items] == ["ChatGPT", "Claude", "Gemini", "Perplexity"]
    assert [c.trigger for c in beats[0].items] == ["ChatGPT", "Claude", "Gemini", "Perplexity"]
    assert (beats[1].value, beats[1].label, beats[1].trigger) == ("50", "questions", "fifty questions")


def test_beat_forms_and_errors():
    spec = parse_spec_text(
        "---\nslug: x\ntitle: T\nbeats:\n"
        "  - kind: chips\n    items: [{label: GPT-5, trigger: chat gpt}, Claude]\n"
        "  - kind: counter\n    value: '$7'\n---\nbody\n")
    chips, counter = spec.beats
    assert chips.items[0].trigger == "chat gpt" and chips.trigger == "chat gpt"
    assert counter.trigger == "$7" and counter.label == ""
    for bad in ("  - kind: spinner\n", "  - kind: chips\n    items: []\n", "  - kind: counter\n"):
        with pytest.raises(ValueError):
            parse_spec_text(f"---\nslug: x\ntitle: T\nbeats:\n{bad}---\nbody\n")


def test_stat_with_its_own_trigger():
    from conftest import words_from
    from ai_shorts.align import apply_alignment
    from ai_shorts.timeline import stat_times
    spec = parse_spec_text("---\nslug: x\ntitle: T\nstats:\n  - {label: Detector, value: '50/50', trigger: coin flip}\n"
                           "---\nI built a clip detector. It was a coin flip.\n")
    assert spec.stats[0].trigger == "coin flip"
    words, _ = apply_alignment(words_from(spec.body), spec.words)
    t = stat_times(words, spec.stats)[0]
    assert next(w.text for w in words if w.start == t) == "coin"      # not "detector"
