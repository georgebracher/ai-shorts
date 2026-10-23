from ai_shorts.align import apply_alignment
from ai_shorts.spec import Beat, Chip, load_spec
from ai_shorts.timeline import beat_times, find_phrase, flatten
from ai_shorts.transcribe import Word
from conftest import SCRIPT, words_from


def start_of(words, text):
    return next(w.start for w in words if w.text == text)


def test_real_script_beats_on_whisper_style_words():
    spec = load_spec(SCRIPT)
    whisper = (spec.body.replace("ChatGPT,", "chat GPT,").replace("fifty", "50")
               .replace("Two hundred", "200"))
    words, _ = apply_alignment(words_from(whisper), spec.words)
    chips, fifty, two_hundred = beat_times(words, spec.beats)
    assert chips == [start_of(words, "ChatGPT,"), start_of(words, "Claude,"),
                     start_of(words, "Gemini"), start_of(words, "Perplexity")]
    assert fifty == [start_of(words, "50")]
    assert two_hundred == [start_of(words, "200")]


def test_phrase_matches_split_and_merged_words():
    flat = flatten([Word("chat", 0, 1), Word("GPT", 1, 2), Word("right", 2, 3), Word("move", 3, 4)])
    assert find_phrase(flat, ["chatgpt"]) == (0, 2)
    assert find_phrase(flat, ["rightmove"]) == (2, 4)
    flat = flatten([Word("ChatGPT", 0, 1)])
    assert find_phrase(flat, ["chat", "gpt"]) == (0, 1)


def test_beats_match_in_order_and_missing_parts():
    words = words_from("Claude said fifty. Then ChatGPT and Claude spoke. fifty more.")
    beats = [Beat("chips", "ChatGPT", [Chip("ChatGPT", "ChatGPT"), Chip("Bard", "Bard"),
                                       Chip("Claude", "Claude")]),
             Beat("counter", "fifty", value="50"),
             Beat("counter", "nine thousand", value="9000")]
    chips, counter, never = beat_times(words, beats)
    t_gpt = start_of(words, "ChatGPT")
    assert chips[0] == t_gpt
    assert chips[1] == t_gpt + 0.3                      # unheard chip follows the one before
    assert chips[2] == [w.start for w in words if w.text == "Claude"][1]   # the later Claude
    assert counter == [start_of(words, "fifty")]        # the later "fifty", not "fifty."
    assert counter[0] > chips[2]                        # in order: after the chips
    assert never is None


def test_a_number_never_matches_inside_a_bigger_one():
    # audit codex-004 (20 Oct 2026): a stat for 2 fired on the "two" of "200", not the later "Two"
    from ai_shorts.spec import Stat
    from ai_shorts.timeline import stat_times
    words = words_from("200 answers. Two of them failed.")
    assert stat_times(words, [Stat("Failed", "2")]) == [start_of(words, "Two")]
    assert beat_times(words, [Beat("counter", "two", value="2")]) == [[start_of(words, "Two")]]
    for said, value, heard in [("twenty-two and two", "2", "two"),         # not the end of 22
                               ("four hundred, then four.", "4", "four."),  # not the start of 400
                               ("a hundred and one, then one.", "1", "one."),
                               ("200 thousand, then 200.", "200", "200."),
                               ("7.25 or 7.2", "7.2", "7.2")]:
        words = words_from(said)
        assert stat_times(words, [Stat("Never said", value)]) == [start_of(words, heard)], said
    words = words_from("Two hundred and fifty answers")        # 250 is not 200
    assert stat_times(words, [Stat("Never said", "200")]) == [None]
