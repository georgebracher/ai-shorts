"""Retakes said out of order. Cuts follow the recording, so a take of line A said after line B
cannot go back in front of B: the chain keeps the earlier A and says so (audit codex-005,
20 Oct 2026: the drop was silent, and the README promises the last complete take)."""
from ai_shorts.align import apply_alignment
from conftest import words_from

A = "Today we publish weekly reports."
B = "Readers get them every Monday morning."
SCRIPT = f"{A} {B}".split()


def kept(words):
    return " ".join(w.text for w in words if w.kept)


def test_a_complete_retake_after_a_later_line_is_dropped_with_a_warning(capsys):
    words, _ = apply_alignment(words_from(f"{A} | {B} | {A}"), SCRIPT)
    assert kept(words) == f"{A} {B}"
    out = capsys.readouterr().out
    assert "WARNING" in out and "Today we publish" in out


def test_an_incomplete_earlier_take_still_holds_the_line_with_a_warning(capsys):
    # the forward chain keeps "Today we publish" + B over a complete A that would lose B
    words, _ = apply_alignment(words_from(f"Today we publish | {B} | {A}"), SCRIPT)
    assert kept(words) == f"Today we publish {B}"
    assert "WARNING" in capsys.readouterr().out


def test_a_retake_in_order_replaces_the_earlier_one_silently(capsys):
    words, _ = apply_alignment(words_from(f"Today we publish | {A} {B}"), SCRIPT)
    assert kept(words) == f"{A} {B}"
    assert capsys.readouterr().out == ""


def test_a_later_take_of_two_lines_in_one_breath_replaces_an_earlier_take_with_a_pause(capsys):
    """005, 1 Nov 2026: the last and cleanest "Whole sentences... That's the number I trust" was one
    unit and lost the tie-break to an earlier take of the same two lines in two units."""
    C, D = "Seven people read the first issue.", "Nobody wrote back at all."
    script = f"{C} {D} {A} {B}".split()
    one_breath = f"{A} {B}".replace(".", "")
    words, _ = apply_alignment(words_from(f"{C} | {D} | {A} | {B} | {one_breath}"), script)
    assert kept(words) == f"{C} {D} {one_breath}"
    assert capsys.readouterr().out == ""


def test_the_placement_pass_does_not_warn_twice(capsys):
    """pickups.py reads the main take's selection to place a pickup; only the render's own pass
    reports a dropped take, or a pickup run prints the same drop on two timelines (003, 23 Oct)."""
    from ai_shorts.takes import select_takes
    select_takes(words_from(f"{A} | {B} | {A}"), SCRIPT, quiet=True)
    assert capsys.readouterr().out == ""
