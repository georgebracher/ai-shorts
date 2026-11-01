"""Captions are what George said, with names and numbers spelled from the script.

The fixture is the real whisper output for George's first take of 001 (made
with the old "Glossary:" prompt, so it also carries the "Glossary &" echoes).
"""
from pathlib import Path

from ai_shorts.align import apply_alignment
from ai_shorts.captions import caption_words, numerals
from ai_shorts.spec import load_spec
from ai_shorts.timeline import chunk_captions, display_word
from ai_shorts.transcribe import Word, drop_noise, load_words
from conftest import RECORDED_SCRIPT as SCRIPT, words_from

FIXTURE = Path(__file__).parent / "fixtures" / "IMG_5328-transcript.json"
SPEC = load_spec(SCRIPT)


def real_captions():
    words = drop_noise(load_words(FIXTURE), SPEC.words)
    words, _ = apply_alignment(words, SPEC.words)
    return caption_words([w for w in words if w.kept], SPEC.words)


def text(caps):
    return " ".join(w.text for w in caps)


def test_real_take_captions_are_what_he_said():
    # whisper heard "Mine costs $7", lost "Day" under the "Glossary" echo, and heard
    # "WriteMove's 822" for "it's Rightmove a hundred and twenty-two": the name and the
    # number are fixed from the script, nothing whisper did not hear is added
    assert text(real_captions()) == (
        "I asked ChatGPT, Claude, Gemini and Perplexity 50 questions about house prices on "
        "the south coast. 200 answers. Rightmove got cited 122 times. My new site? Zero. In "
        "fairness, it's a day old. So this is how I'm testing if AI will ever cite it. 1. Write "
        "the questions down before you publish anything, so you can't move the goalposts later. "
        "2. Ask all four in the same hour and save every answer. 3. Count who gets cited. That's "
        "your baseline. Mine costs $7. 4. Publish pages that answer those exact questions, then "
        "ask again every two weeks. Will it work? No idea. 1. Rightmove's 122, me, nil. The "
        "code's in the repo below. You don't need to DM me for it.")


def test_real_take_mishearings_are_gone():
    shown = [" ".join(display_word(w.text) for w in c.words)
             for c in chunk_captions(real_captions())]
    joined = " | ".join(shown)
    for bad in ("GLOSSARY", "&", "WRITEMOVE", "822"):
        assert bad not in joined, bad
    assert "RIGHTMOVE'S 122" in joined


def test_real_take_timings_are_whispers_and_in_order():
    heard = drop_noise(load_words(FIXTURE), SPEC.words)
    caps = real_captions()
    assert [w.start for w in caps] == sorted(w.start for w in caps)
    assert caps[0].start >= heard[0].start and caps[-1].end <= heard[-1].end
    rightmove = next(w for w in caps if w.text == "Rightmove")     # 2nd word of line 3
    assert rightmove.start == next(w.start for w in heard if w.text == "Rightmove")


def test_noise_and_prompt_echo_dropped_unless_scripted():
    words = [Word("Glossary", 0, 1), Word("&", 1, 1), Word("hello", 1, 2)]
    assert [w.text for w in drop_noise(words, ["hello"])] == ["hello"]
    assert [w.text for w in drop_noise(words, ["the", "glossary", "hello"])] == ["Glossary", "hello"]


SCRIPT_LINE = "Two hundred answers. Rightmove got cited a hundred and twenty-two times. My new site? Zero."


def test_ad_lib_falls_back_to_whisper():
    caps = caption_words(words_from("200 answers. Honestly, Rightmove got cited 122 times."),
                         SCRIPT_LINE.split())
    assert text(caps) == "200 answers. Honestly, Rightmove got cited 122 times."


def test_misheard_name_takes_script_spelling_ordinary_words_do_not():
    heard = words_from("200 answers. Right moov got sighted 122 times.")
    caps = caption_words(heard, SCRIPT_LINE.split())
    assert text(caps) == "200 answers. Rightmove got sighted 122 times."
    rm = next(w for w in caps if w.text == "Rightmove")
    assert (rm.start, rm.end) == (heard[2].start, heard[3].end)     # timed by the heard words


def test_homophone_names_and_wrong_numbers_fixed():
    line = "Day one, it's Rightmove a hundred and twenty-two, me nil.".split()
    caps = caption_words(words_from("It's write move 822 to my zero."), line)
    assert text(caps) == "It's Rightmove 122 to my zero."
    caps = caption_words(words_from("I asked chat GPT and Claude."), "I asked ChatGPT and Claude.".split())
    assert text(caps) == "I asked ChatGPT and Claude."


def test_paraphrase_is_captioned_as_said():
    script = "Mine cost seven dollars. You don't need to DM me for it.".split()
    caps = caption_words(words_from("Mine cost me $7. Please don't DM me."), script)
    assert text(caps) == "Mine cost me $7. Please don't DM me."


def test_spelled_out_number_becomes_numeral():
    caps = caption_words(words_from("Rightmove got cited a hundred and twenty two times."),
                         SCRIPT_LINE.split())
    assert "122" in text(caps)
    assert [w.text for w in numerals([Word("a", 0, 1), Word("hundred", 1, 2), Word("and", 2, 3),
                                      Word("twenty-two,", 3, 4)])] == ["122,"]
    assert [w.text for w in numerals(words_from("Ask all four and"))] == ["Ask", "all", "four", "and"]


def test_nothing_is_added_that_whisper_did_not_hear():
    heard = words_from("200 answers. My new site? Zero.")            # skipped a whole line
    assert text(caption_words(heard, SCRIPT_LINE.split())) == "200 answers. My new site? Zero."
    heard = words_from("200 answers. Rightmove cited 122 times.")    # "got" not heard
    assert text(caption_words(heard, SCRIPT_LINE.split())) == "200 answers. Rightmove cited 122 times."


def test_wholly_different_speech_is_not_replaced_by_script():
    heard = words_from("200 answers. Look at this mess I made of it. My new site? Zero.")
    caps = caption_words(heard, SCRIPT_LINE.split())
    assert "Rightmove" not in text(caps) and "mess" in text(caps)


def _caps(said: str, script: str) -> str:
    from ai_shorts.align import apply_alignment
    words, _ = apply_alignment(words_from(said), script.split())
    return text(caption_words([w for w in words if w.kept], script.split()))


def test_misheard_ordinary_words_take_the_script_spelling():
    # DJI_0349 (21 Oct 2026): "COUNT WHO GETS SATED", "MY CITE, ZERO"
    assert _caps("Count who gets sated. That's your baseline.",
                 "Count who gets cited. That's your baseline.") == "Count who gets cited. That's your baseline."
    assert _caps("My cite, zero.", "My new site? Zero.") == "My site, zero."


def test_paraphrase_keeps_what_he_said():
    assert _caps("Ask all four in the same hour and save all answers.",
                 "Ask all four in the same hour and save every answer.") == \
        "Ask all four in the same hour and save all answers."
    assert _caps("So this is how I'm testing if AI will ever cite it.",
                 "So this is how I'm testing if AI will ever cite it.").endswith("cite it.")


def test_take_two_and_three_caption_fixes():
    # DJI_0350 / DJI_0353 (21 Oct 2026)
    assert _caps("It was a coin flip. 50 -50.", "It was a coin flip. Fifty-fifty.") == "It was a coin flip. 50-50."
    assert _caps("Four. Only send him the clip's clawed rates.", "Four. Only send him the clips Claude rates.") == \
        "4. Only send him the clips Claude rates."
    assert _caps("One. Film it. Two. Say it.", "One. Film it. Two. Say it.") == "1. Film it. 2. Say it."


def test_two_fifties_are_not_a_hundred():
    from ai_shorts.captions import _parse
    assert _parse(["fifty", "fifty"]) is None and _parse(["twenty", "two"]) == 22
    assert _parse(["a", "hundred", "and", "four"]) == 104 and _parse(["three", "hundred", "and", "thirty", "six"]) == 336


def test_sound_alike_fix_keeps_his_words_and_leaves_names_to_pairs():
    assert _caps("This way you cannot change the goalposts later.",
                 "so you can't move the goalposts later.") == "This way you cannot change the goalposts later."
    assert _caps("Currently, right move is at 104.", "Day one, it's Rightmove a hundred and four.") == \
        "Currently, Rightmove is at 104."
    assert _caps("Send him only the clip's clawed rates.", "Only send him the clips Claude rates.") == \
        "Send him only the clips Claude rates."


def test_an_inflected_word_is_not_swapped_for_the_script_root():
    assert _caps("Then I checked it against 336 clips.", "Then I checked it. Three. Check it against.") \
        .startswith("Then I checked it")


def test_sighted_is_cited_but_checked_is_not_check():
    assert "gets cited." in _caps("Count who gets sighted. That's your baseline.",
                                  "Count who gets cited. That's your baseline.")
    assert _caps("Then I checked it against 336 clips.", "Then I checked it. Three. Check it against.") \
        .startswith("Then I checked it")


def test_a_misheard_place_name_takes_the_script_spelling():
    # whisper heard Bosham as "bosom", 004 (1 Nov 2026)
    assert "All about Bosham" in _caps("All about bosom and once cited first.",
                                       "All about Bosham, and once cited first.")


def test_a_lost_script_stop_comes_back_only_where_the_next_sentence_starts():
    # 004 (1 Nov 2026) read "Claude cited it 3 | times ChatGPT,"
    script = "Claude cited it three times. ChatGPT got zero."
    assert "times. ChatGPT" in _caps("Claude cited it three times ChatGPT got zero", script)
    assert _caps("Claude cited it three times and ChatGPT got zero", script).startswith(
        "Claude cited it three times and")
