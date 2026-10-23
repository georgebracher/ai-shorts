"""Regression: George's proper take of 001 (DJI Osmo, no teleprompter, 189 s).

He paraphrased and did several takes of some lines, and restarted step two
AFTER step four. The real whisper transcript is the fixture (JSON only).
"""
from pathlib import Path

import pytest

from ai_shorts.align import apply_alignment
from ai_shorts.captions import caption_words
from ai_shorts.spec import load_spec
from ai_shorts.timeline import chunk_captions, display_word, step_times
from ai_shorts.transcribe import drop_noise, load_words
from ai_shorts.trim import TimeMap, build_segments
from conftest import RECORDED_SCRIPT as SCRIPT

FIXTURE = Path(__file__).parent / "fixtures" / "DJI_0348-transcript.json"
SPEC = load_spec(SCRIPT)
# the takes a human editor keeps (whisper segment times)
EXPECTED = [(20.9, 39.3), (90.8, 99.2), (102.8, 108.8), (123.8, 128.6),
            (136.8, 147.2), (152.6, 160.7), (176.9, 186.5)]
TOL = 0.3


@pytest.fixture(scope="module")
def edit():
    words = drop_noise(load_words(FIXTURE), SPEC.words)
    words, restarts = apply_alignment(words, SPEC.words, 0.6, {s.trigger for s in SPEC.steps})
    segs = build_segments(words, 189.3)
    tm = TimeMap(segs)
    return words, segs, tm, tm.remap_words(words)


def in_expected(t: float) -> bool:
    return any(a - TOL <= t <= b + TOL for a, b in EXPECTED)


def test_kept_ranges_match_the_human_edit(edit):
    words, segs, _, _ = edit
    for s in segs:                                     # nothing kept outside the takes
        assert in_expected(s.start) and in_expected(s.end), (s.start, s.end)
    for a, b in EXPECTED:                              # every take's edges are cut there
        assert any(abs(s.start - a) <= TOL for s in segs), a
        assert any(abs(s.end - b) <= TOL for s in segs), b
    for w in words:                                    # word by word: kept iff inside a take
        mid = (w.start + w.end) / 2
        assert w.kept == any(a <= mid <= b for a, b in EXPECTED), (w.text, w.start)


def test_earlier_takes_and_stray_restart_gone(edit):
    words, *_ = edit
    kept = [w for w in words if w.kept]
    assert not [w for w in kept if 40 < w.start < 90]           # four "My new site, zero" takes
    assert not [w for w in kept if 112 < w.start < 120]         # first take of step two
    assert not [w for w in kept if 160.6 < w.start < 176]       # stray "One, ask all four..." + 2 takes
    text = " ".join(w.text for w in kept).lower()
    assert text.count("my new site") == 1 and text.count("will it work") == 1
    assert "of them the questions." not in text.split("four,")[-1]


def test_all_four_steps_fire_in_order_on_the_kept_takes(edit):
    _, _, tm, out = edit
    times = step_times(out, SPEC.steps, SPEC.words)
    assert None not in times and times == sorted(times)
    src = [tm.to_source(t) for t in times]
    assert src == pytest.approx([102.84, 123.82, 136.78, 152.60], abs=0.05)


def test_output_length(edit):
    _, _, tm, _ = edit
    assert 45 < tm.duration < 65        # ~62 s on whisper times; the render's silence pass trims more


def test_captions_follow_what_he_said(edit):
    *_, out = edit
    chunks = [" ".join(display_word(w.text) for w in c.words)
              for c in chunk_captions(caption_words(out, SPEC.words))]
    joined = " | ".join(chunks)
    for said in ("MINE COST ME $7", "PLEASE DON'T DM ME", "CANNOT CHANGE", "IT'S RIGHTMOVE 122",
                 "RIGHTMOVE BEING"):
        assert said in joined, said
    for not_said in ("WRITE MOVE", "DAY ONE", "ME NIL", "NEED TO", "FOR IT", "CAN'T MOVE"):
        assert not_said not in joined, not_said


def test_relistening_drops_the_hidden_false_start_of_step_three():
    """Whisper's first pass hid "Three, no..." inside "Three, count who gets cited"
    ("who" ran over a 2.7 s pause). The second listen of that sentence (fixture)
    separates it, and the false start is dropped."""
    from ai_shorts.refine import splice
    clip = Path(__file__).parent / "fixtures" / "DJI_0348-relisten-136.51.json"
    second = [type(w)(w.text, w.start + 136.51, w.end + 136.51) for w in load_words(clip)]
    first = drop_noise(load_words(FIXTURE), SPEC.words)
    # the long-word rule (21 Oct 2026) also re-hears take 1's other multi-second words; only the
    # step-three stretch has a recorded second listen, so elsewhere it hears what the first pass did
    def relisten(a, b):      # windows inside the recorded second listen hear it; elsewhere the first pass
        src = second if 136.4 <= a and b <= 144.0 else first
        return [w for w in src if a <= (w.start + w.end) / 2 <= b]
    words, n = splice(first, [(138.52, 141.21)], relisten)
    assert n >= 1
    words, _ = apply_alignment(words, SPEC.words, 0.6, {s.trigger for s in SPEC.steps})
    kept = [w for w in words if w.kept and 130 < w.start < 150]
    assert kept[0].text == "3." and kept[0].start == pytest.approx(141.2, abs=0.15)
    assert not [w for w in words if w.kept and 136 < w.start < 141]     # "3. No..." gone
    tm = TimeMap(build_segments(words, 189.3))
    times = step_times(tm.remap_words(words), SPEC.steps, SPEC.words)
    assert [tm.to_source(t) for t in times] == pytest.approx([102.84, 123.82, 141.2, 152.60], abs=0.15)
