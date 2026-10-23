import pytest

from ai_shorts.audio import tighten_words
from ai_shorts.text import normalize_text, normalize_word
from ai_shorts.transcribe import Word
from ai_shorts.trim import Segment, TimeMap, build_segments


def W(text, a, b, kept=True):
    return Word(text, a, b, kept)


def test_normalise_numbers_and_symbols():
    assert normalize_word("1.") == ["one"]
    assert normalize_word("122") == ["one", "hundred", "and", "twenty", "two"]
    assert normalize_word("$7.") == ["seven", "dollars"]
    assert normalize_word("twenty-two,") == ["twenty", "two"]
    assert normalize_word("can't") == ["cant"]
    assert normalize_text("a hundred and twenty-two") == normalize_word("122")


def test_cuts_leading_trailing_silence_and_long_pause():
    words = [W("a", 2.0, 2.4), W("b", 2.5, 2.9), W("c", 5.0, 5.4)]  # 2.1 s pause before c
    segs = build_segments(words, duration=10.0, pad=0.12, max_pause=0.6, fps=30)
    assert len(segs) == 2
    assert segs[0].start == pytest.approx(1.8667, abs=1e-3)   # 2.0 - 0.12, snapped to 1/30
    assert segs[0].end == pytest.approx(3.0333, abs=1e-3)     # 2.9 + 0.12
    assert segs[1].start == pytest.approx(4.8667, abs=1e-3)
    assert segs[1].end == pytest.approx(5.5333, abs=1e-3)
    for s in segs:   # every edge sits on the frame grid
        assert s.start * 30 == pytest.approx(round(s.start * 30))
        assert s.end * 30 == pytest.approx(round(s.end * 30))


def test_short_pause_is_kept():
    words = [W("a", 1.0, 1.4), W("b", 1.9, 2.3)]   # 0.5 s pause
    assert len(build_segments(words, 5.0)) == 1


def test_dropped_word_forces_cut_and_padding_stops_at_it():
    words = [W("a", 1.0, 1.4), W("x", 1.45, 1.8, kept=False), W("b", 1.85, 2.2)]
    segs = build_segments(words, 5.0, pad=0.12)
    assert len(segs) == 2
    assert segs[0].end <= 1.45 + 1 / 60       # never runs into the dropped word
    assert segs[1].start >= 1.8 - 1 / 60


def test_time_map_round_trip_and_cut_points():
    tm = TimeMap([Segment(1.0, 3.0), Segment(5.0, 6.0)])
    assert tm.duration == pytest.approx(3.0)
    assert tm.to_output(1.0) == pytest.approx(0.0)
    assert tm.to_output(2.5) == pytest.approx(1.5)
    assert tm.to_output(5.5) == pytest.approx(2.5)
    assert tm.to_output(4.0) == pytest.approx(2.0)   # inside the cut -> the join
    for t_out in (0.0, 0.7, 1.99, 2.0, 2.4, 2.99):
        assert tm.to_output(tm.to_source(t_out)) == pytest.approx(t_out)


def test_remap_words_onto_output_timeline():
    words = [W("a", 1.1, 1.5), W("x", 2.0, 2.5, kept=False), W("b", 5.2, 5.6)]
    tm = TimeMap([Segment(1.0, 1.6), Segment(5.0, 5.8)])
    out = tm.remap_words(words)
    assert [w.text for w in out] == ["a", "b"]
    assert (out[0].start, out[0].end) == pytest.approx((0.1, 0.5))
    assert (out[1].start, out[1].end) == pytest.approx((0.8, 1.2))


def test_tighten_pulls_word_edges_out_of_silence():
    w = [W("in", 19.8, 20.4), W("old", 21.5, 22.6)]
    tighten_words(w, [(18.0, 20.25), (22.1, 23.0)])
    assert w[0].start == pytest.approx(20.25)
    assert w[1].end == pytest.approx(22.1)


def test_long_silence_inside_a_stretched_word_is_cut():
    # whisper stretched "who" over a 2.7 s pause (George's real take, 138.5-141.2 s)
    words = [W("count", 137.5, 138.2), W("who", 138.2, 142.9), W("gets", 142.9, 143.2)]
    plain = build_segments(words, 200.0)
    assert len(plain) == 1
    segs = build_segments(words, 200.0, silences=[(138.52, 141.21), (142.0, 142.3)])
    assert len(segs) == 2                                  # the 0.3 s silence stays
    assert segs[0].end == pytest.approx(138.64, abs=0.02)
    assert segs[1].start == pytest.approx(141.1, abs=0.02)
    assert sum(s.length for s in segs) == pytest.approx(plain[0].length - 2.46, abs=0.05)


def quiet_except(*loud):
    """A fake loudness envelope: sound only inside the given (start, end) spans."""
    return lambda t: not any(a <= t <= b for a, b in loud)


def test_cut_moves_off_a_word_tail_into_silence():
    # George's "$7." ends at 147.24 by whisper, but the sound runs to 147.68
    words = [W("me", 146.6, 146.74), W("$7.", 146.74, 147.24), W("Four,", 153.25, 153.56)]
    seg = build_segments(words, 200.0, quiet=quiet_except((146.6, 147.67)))[0]
    assert seg.end == pytest.approx(147.7, abs=0.04)        # was 147.37: clipped the word


def test_cut_steps_back_into_the_dip_when_the_next_word_follows_at_once():
    # "weeks" fades out at 160.62, the stray "One" starts at 160.68 (whisper: 160.70)
    words = [W("weeks.", 159.98, 160.70), W("One,", 160.70, 160.80, kept=False)]
    seg = build_segments(words, 200.0, quiet=quiet_except((159.98, 160.62), (160.68, 160.95)))[0]
    assert 160.62 <= seg.end <= 160.68


def test_start_moves_back_to_catch_a_word_onset():
    words = [W("idea.", 178.58, 178.94), W("It's", 179.76, 180.04), W("write", 180.04, 180.2)]
    words[0].kept = False
    seg = build_segments(words, 200.0, quiet=quiet_except((179.45, 180.2)))[0]
    assert seg.start == pytest.approx(179.42, abs=0.04)     # sound starts 179.45, not 179.64
