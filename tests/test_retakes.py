from ai_shorts.align import apply_alignment
from ai_shorts.spec import load_spec
from conftest import SCRIPT, words_from

SCRIPT_TEXT = ("Two hundred answers. Rightmove got cited a hundred and twenty-two times. "
               "My new site? Zero.")


def kept(words):
    return " ".join(w.text for w in words if w.kept)


def test_partial_take_dropped_keeps_last():
    said = words_from("200 answers. Rightmove got cited 100 and, | Rightmove got cited 122 times. My new site? 0.")
    words, restarts = apply_alignment(said, SCRIPT_TEXT.split())
    assert restarts == 1
    assert kept(words) == "200 answers. Rightmove got cited 122 times. My new site? 0."


def test_full_repeat_and_filler_dropped():
    said = words_from("200 answers. Rightmove got cited 122 times. sorry, again. "
                      "Rightmove got cited 122 times. My new site? 0.")
    words, restarts = apply_alignment(said, SCRIPT_TEXT.split())
    assert restarts == 1
    assert kept(words) == "200 answers. Rightmove got cited 122 times. My new site? 0."


def test_two_false_starts():
    said = words_from("200 answers. Right move got | Rightmove got cited | Rightmove got cited 122 times. "
                      "My new site? 0.")
    words, _ = apply_alignment(said, SCRIPT_TEXT.split())
    assert kept(words) == "200 answers. Rightmove got cited 122 times. My new site? 0."


def test_split_word_is_rejoined_with_script_spelling():
    said = words_from("200 answers. right move got cited 122 times.")
    words, restarts = apply_alignment(said, SCRIPT_TEXT.split())
    assert restarts == 0
    assert kept(words) == "200 answers. Rightmove got cited 122 times."


def test_clean_read_of_real_script_drops_nothing():
    # the script says "Rightmove ... a hundred and four" twice; that is not a retake
    spec = load_spec(SCRIPT)
    said = words_from(spec.body.replace("One.", "1.").replace("a hundred and four", "104"))
    words, restarts = apply_alignment(said, spec.words)
    assert restarts == 0
    assert all(w.kept for w in words)


def test_restarted_line_in_real_script():
    spec = load_spec(SCRIPT)
    line = "Two. Ask all four in the same hour and save every answer."
    flubbed = spec.body.replace(line, "Two. Ask all four in the same | " + line)
    words, restarts = apply_alignment(words_from(flubbed), spec.words)
    assert restarts == 1
    assert kept(words) == " ".join(spec.words)


def test_leading_and_trailing_chatter_dropped():
    said = words_from("okay rolling | 200 answers. Rightmove got cited 122 times. | was that alright?")
    words, _ = apply_alignment(said, SCRIPT_TEXT.split())
    assert kept(words) == "200 answers. Rightmove got cited 122 times."


def test_ad_lib_inside_script_is_kept():
    said = words_from("200 answers. Honestly, Rightmove got cited 122 times.")
    words, _ = apply_alignment(said, SCRIPT_TEXT.split())
    assert kept(words) == "200 answers. Honestly, Rightmove got cited 122 times."


def test_lone_filler_word_does_not_join_the_take_before():
    # whisper heard the onset of a stray restart as "this." right after a kept line
    said = words_from("200 answers. Rightmove got cited 122 times. this. My new site? Zero.")
    words, _ = apply_alignment(said, SCRIPT_TEXT.split())
    assert kept(words) == "200 answers. Rightmove got cited 122 times. My new site? Zero."


SHORT = "Today we publish weekly reports.".split()


def test_trailing_echo_never_erases_a_complete_line():
    # audit codex-001 (20 Oct 2026): a last word matching the script's first word counted as a
    # restart and the whole sentence came out as "today."
    words, restarts = apply_alignment(words_from("Today we publish weekly reports today."), SHORT)
    assert restarts == 0
    assert kept(words) == "Today we publish weekly reports today."  # the echo stays as an ad-lib


def test_short_trailing_restart_keeps_the_complete_take():
    words, _ = apply_alignment(words_from("Today we publish weekly reports. Today we"), SHORT)
    assert kept(words) == "Today we publish weekly reports."


def test_full_retake_after_a_complete_take_still_replaces_it():
    words, restarts = apply_alignment(
        words_from("Today we publish weekly reports today we publish weekly reports."), SHORT)
    assert restarts == 1
    assert kept(words).lower() == "today we publish weekly reports."


def test_an_extra_word_is_not_glued_onto_the_next_one():
    words, _ = apply_alignment(words_from("The first time it played step three twice."),
                               "The first cut played step three twice.".split())
    assert kept(words) == "The first time it played step three twice."
