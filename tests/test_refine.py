"""Re-listening where whisper ran a word over a pause (and swallowed a false start)."""
from ai_shorts.refine import splice, suspect_spans
from ai_shorts.transcribe import Word


def W(t, a, b):
    return Word(t, a, b)


# George's real take: whisper wrote "Three, count who gets cited." with "who" over 4.7 s;
# alone, the stretch reads "3. Note... 3. Count who gets cited."
FIRST_PASS = [W("hour.", 128.1, 128.64), W("Three,", 136.81, 137.48), W("count", 137.48, 138.18),
              W("who", 138.18, 142.90), W("gets", 142.90, 143.20), W("cited.", 143.20, 143.66),
              W("This", 143.92, 144.30), W("baseline.", 144.84, 145.34)]
SILENCES = [(128.76, 129.73), (138.52, 141.21)]
SECOND_LISTEN = [W("3.", 136.30, 137.40), W("Note...", 138.00, 138.58), W("3.", 141.16, 141.74),
                 W("Count", 142.32, 142.58), W("who", 142.58, 142.90), W("gets", 142.90, 143.18),
                 W("cited.", 143.18, 143.64), W("This", 143.92, 144.30)]


def test_stretched_word_over_a_pause_is_suspect():
    assert suspect_spans(FIRST_PASS, SILENCES) == [(1, 3, 5)]   # "Three," .. "who" .. "cited."


def test_second_listen_is_spliced_in_for_that_sentence_only():
    asked = []

    def relisten(a, b):
        asked.append((a, b))
        return [w for w in SECOND_LISTEN if a <= (w.start + w.end) / 2 <= b]

    words, n = splice(FIRST_PASS, SILENCES, relisten)
    assert n == 1
    a, b = asked[0][0], asked[-1][1]
    assert 136.4 <= a <= 136.81 and 143.66 <= b <= 143.92           # whole sentence, not the next
    # heard island by island around the 2.7 s silence inside "who" (21 Oct 2026)
    assert len(asked) == 2 and asked[0][1] < 139.0 and asked[1][0] > 140.9
    # re-heard up to the stretched word; "gets cited." kept from the first pass
    assert [w.text for w in words] == ["hour.", "3.", "Note...", "3.", "Count", "who", "gets",
                                       "cited.", "This", "baseline."]
    assert words[6].start == 142.90 and words[7].start == 143.20


def test_nothing_heard_means_the_words_were_hallucinated():
    stray = [W("weeks.", 159.98, 160.70), W("One,", 160.70, 160.80), W("four", 161.62, 164.64),
             W("questions.", 165.48, 165.50), W("Will", 166.52, 166.88)]
    words, n = splice(stray, [(160.97, 166.48)], lambda a, b: [])
    assert n == 1 and [w.text for w in words] == ["weeks.", "questions.", "Will"]


def test_clean_transcript_is_left_alone():
    words, n = splice(FIRST_PASS[:3], SILENCES, lambda a, b: 1 / 0)
    assert n == 0 and words == FIRST_PASS[:3]


def test_a_word_stretched_over_speech_is_suspect():
    # DJI_0349 (21 Oct 2026): "your" ran 3.05 s over a whole unheard take ("3. Count who gets
    # sighted.") with only 0.78 s of silence inside, so step three played twice
    from ai_shorts.refine import suspect_spans
    from ai_shorts.transcribe import Word
    words = [Word("That's", 137.54, 137.75), Word("your", 140.89, 143.94), Word("baseline.", 143.94, 144.38)]
    silences = [(137.75, 140.89), (141.36, 141.54), (141.59, 141.85), (143.13, 143.47)]
    assert suspect_spans(words, silences)



def test_a_named_noise_before_an_unsure_word_is_suspect():
    # DJI_0353 (21 Oct 2026): a throat clear became "Then" (0.2 s), silence, then an unsure "I"
    from ai_shorts.refine import suspect_spans
    from ai_shorts.transcribe import Word
    words = [Word("face.", 13.26, 13.68), Word("Then", 25.14, 25.34), Word("I", 25.88, 26.58, prob=0.32),
             Word("checked", 26.58, 26.88)]
    assert suspect_spans(words, [(13.68, 25.0), (25.34, 25.88)])
    # a step cue after a finished sentence is not a noise: "did. [pause] 1."
    cue = [Word("did.", 29.0, 29.3), Word("1.", 30.0, 30.4, prob=0.27), Word("Film", 30.5, 30.8)]
    assert not suspect_spans(cue, [(29.3, 30.0)])


def test_words_the_second_listen_covers_are_not_kept_twice():
    # 003: first pass "coin" over 2.5 s; second listen "coin" + "flip." up to 42.65 s; the first
    # pass's own "flip." (42.46) stayed as a duplicate and the cut dropped the real "coin flip"
    from ai_shorts.refine import splice
    from ai_shorts.transcribe import Word
    first = [Word("a", 39.82, 39.96), Word("coin", 39.96, 42.46), Word("flip.", 42.46, 42.74),
             Word("50", 43.02, 43.64)]
    second = [Word("a", 39.83, 39.99), Word("coin", 39.99, 40.11), Word("flip.", 40.11, 42.65)]
    words, n = splice(first, [(40.5, 41.4)], lambda a, b: [w for w in second if a <= (w.start + w.end) / 2 <= b])
    assert n == 1 and [w.text for w in words] == ["a", "coin", "flip.", "50"]


def test_an_unsure_word_with_a_gap_inside_is_suspect():
    # 003 pickup: "One. One. Show..." with the second "one" written into an unsure "Show"
    from ai_shorts.refine import suspect_spans
    from ai_shorts.transcribe import Word
    words = [Word("1.", 66.52, 67.56), Word("Show", 69.76, 70.8, prob=0.49), Word("Claude", 70.8, 71.24)]
    assert suspect_spans(words, [(70.2, 70.56)])
    assert not suspect_spans([Word("Show", 69.76, 70.8, prob=0.95), Word("Claude", 70.8, 71.2)], [(70.2, 70.56)])


def test_an_edge_just_outside_a_silence_is_tightened():
    from ai_shorts.audio import tighten_words
    from ai_shorts.transcribe import Word
    w = [Word("Check", 98.06, 98.74)]
    tighten_words(w, [(98.07, 98.55)])
    assert w[0].start == 98.55


def test_a_broken_off_word_before_a_long_pause_is_heard_as_its_own_island():
    # 003: "It was a co- [1.5 s] coin flip." The second island is heard as "coin flip" on its own
    from ai_shorts.refine import islands, splice
    from ai_shorts.transcribe import Word
    assert islands(39.0, 43.0, [(40.4, 41.8)]) == [(39.0, 40.55), (41.65, 43.0)]
    first = [Word("It", 39.5, 39.66), Word("was", 39.66, 39.82), Word("a", 39.82, 39.96),
             Word("coin", 39.96, 42.46), Word("flip.", 42.46, 42.74)]
    alone = {0: [Word("It", 39.5, 39.66), Word("was", 39.66, 39.82), Word("a", 39.82, 39.96), Word("coin", 40.0, 40.3)],
             1: [Word("coin", 41.9, 42.2), Word("flip.", 42.2, 42.6)]}
    words, n = splice(first, [(40.4, 41.8)], lambda a, b: alone[0] if b < 41 else alone[1])
    assert [w.text for w in words] == ["It", "was", "a", "coin", "coin", "flip."]
