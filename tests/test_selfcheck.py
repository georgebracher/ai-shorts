"""The finished audio against the captions (21 Oct 2026: 003 v6's 'one one', 'three three', cut 'coin flip')."""
from ai_shorts.selfcheck import compare
from conftest import words_from


def test_a_doubled_cue_is_caught():
    caps = words_from("1. Show Claude 48 clips.")
    heard = words_from("1. 1. Show Claude 48 clips.")
    assert any("said twice" in p for p in compare(caps, heard))


def test_a_cut_off_phrase_is_caught():
    caps = words_from("It was a coin flip. 50-50.")
    heard = words_from("It was a 50-50.")
    assert any("not heard" in p and "coin flip" in p for p in compare(caps, heard))


def test_a_stray_take_is_caught_and_a_clean_read_passes():
    caps = words_from("Count who gets cited. That's your baseline.")
    assert compare(caps, words_from("Count who gets cited. That's your baseline.")) == []
    assert compare(caps, words_from("Count who gets sighted. Count who gets cited. That's your baseline."))


def test_a_word_stretched_over_a_pause_is_flagged():
    import numpy as np
    from ai_shorts.audio import SR
    from ai_shorts.transcribe import Word
    t = np.arange(int(4 * SR)) / SR
    x = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    x[int(1.2 * SR):int(2.4 * SR)] = 0                         # a 1.2 s pause inside "coin"
    heard = [Word("It", 0.0, 0.4), Word("coin", 0.5, 2.8), Word("flip.", 2.8, 3.2)]
    assert any("runs" in p for p in compare(words_from("It coin flip."), heard, x))
