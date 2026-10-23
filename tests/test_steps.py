from ai_shorts.align import apply_alignment
from ai_shorts.spec import Stat, Step, load_spec
from ai_shorts.timeline import fill_missing, stat_times, step_times
from conftest import SCRIPT, words_from

STEPS = [Step("a", "one"), Step("b", "two"), Step("c", "three")]


def start_of(words, text, nth=0):
    hits = [w.start for w in words if w.text == text]
    return hits[nth]


def test_real_script_steps_fire_in_order_on_the_step_words():
    spec = load_spec(SCRIPT)
    said = words_from(spec.body.replace("a hundred and twenty-two", "122"))
    words, _ = apply_alignment(said, spec.words)
    times = step_times(words, spec.steps, spec.words)
    # "Two hundred answers" and "122" (one hundred...) come first but must not fire
    assert times == [start_of(words, "One."), start_of(words, "Two.", 0),
                     start_of(words, "Three."), start_of(words, "Four.")]
    assert times == sorted(times)


def test_whisper_digits_fire_via_script_alignment():
    spec = load_spec(SCRIPT)
    said = words_from(spec.body.replace("One.", "1.").replace("Two.", "2.")
                      .replace("Three.", "3.").replace("Four.", "4."))
    words, _ = apply_alignment(said, spec.words)
    times = step_times(words, spec.steps, spec.words)
    assert times == [start_of(words, "1."), start_of(words, "2."),
                     start_of(words, "3."), start_of(words, "4.")]


def test_fallback_without_script_is_ordered_whole_words():
    words = words_from("two cats. one. then 122 things. two. and three.")
    times = step_times(words, STEPS)
    assert times == [start_of(words, "one."), start_of(words, "two.", 0), start_of(words, "three.")]


def test_missing_trigger_still_shows_after_previous():
    words = words_from("one. something else. three.")
    times = step_times(words, STEPS)
    assert times[1] is None
    shown = fill_missing(times)
    assert shown[1] == shown[0] + 1.0       # one second after step one
    assert shown[2] == times[2]
    assert shown == sorted(shown)


def test_stats_fire_on_their_values():
    words = words_from("Rightmove got cited a hundred and twenty-two times. My new site? Zero.")
    t = stat_times(words, [Stat("Rightmove", "122"), Stat("My site", "0")])
    assert t == [start_of(words, "a"), start_of(words, "Zero.")]


def test_an_unheard_stat_warns(capsys):
    # audit k3-007 (20 Oct 2026): a stat whose value was never said vanished with no warning
    words = words_from("Rightmove got cited a hundred and twenty-two times.")
    assert stat_times(words, [Stat("Rightmove", "122"), Stat("My site", "0")]) == [start_of(words, "a"), None]
    out = capsys.readouterr().out
    assert "WARNING" in out and "'My site'" in out


HOOK = "I asked fifty questions. Two hundred answers. My new site? Zero. "
LINES = ("One. Write the questions down before you start. Two. Ask all four at once. "
         "Three. Count who gets cited. Day one, it's me nil.")


def test_a_missed_first_trigger_shows_where_its_line_starts(capsys):
    # audit claude-010 (20 Oct 2026): "First," for "One." put step one on the 1 s timer, which
    # cleared the hook at 1.0 s and hid the stats; or the fallback took the "one" of "Day one"
    script = (HOOK + LINES).split()
    said = words_from(HOOK + LINES.replace("One.", "First,"))
    words, _ = apply_alignment(said, script, 0.6, {"one", "two", "three"})
    times = step_times(words, STEPS, script)
    assert times == [start_of(words, "Write"), start_of(words, "Two."), start_of(words, "Three.")]
    assert fill_missing(times) == times
    out = capsys.readouterr().out
    assert "WARNING" in out and "'one'" in out


def test_a_missed_first_step_is_not_put_on_a_timer_from_the_start():
    # without a script to place it, it shows just before the first step that was heard
    assert fill_missing([None, 30.0, 40.0]) == [29.0, 30.0, 40.0]
    assert fill_missing([None, None, 30.0]) == [28.0, 29.0, 30.0]
    assert fill_missing([None, 0.5]) == [0.0, 0.5]


def test_warnings_from_other_stages_reach_the_render_report():
    """takes, timeline and overlay warn through timeline.warn; a render's report keeps them."""
    from ai_shorts import timeline
    kept: list[str] = []
    timeline.LISTENERS[:] = [kept.append]
    try:
        timeline.warn("stat 'X' (1) never heard; not shown")
    finally:
        timeline.LISTENERS.clear()
    assert kept == ["stat 'X' (1) never heard; not shown"]
