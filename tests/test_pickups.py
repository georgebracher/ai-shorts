"""Pickups go back where they belong (21 Oct 2026, 003's "forty" pickup was ignored)."""
import subprocess

import pytest

from ai_shorts.__main__ import build_parser
from ai_shorts.config import FFMPEG
from ai_shorts.pickups import insertion_time
from ai_shorts.align import apply_alignment
from conftest import words_from

SCRIPT = ("One. Show Claude forty-eight clips. Two. Ask it to grade the next one. "
          "Three. Check it against his picks.").split()


def test_pickup_lands_after_the_old_take_of_its_line():
    main = words_from("One. Show Claude forty clips. | Two. Ask it to grade the next one. | "
                      "Three. Check it against his picks.")
    pickup = words_from("One. Show Claude forty-eight clips.")
    t = insertion_time(main, pickup, SCRIPT, {"one", "two", "three"})
    two = next(w for w in main if w.text == "Two.")
    clips = next(w for w in main if w.text == "clips.")
    assert clips.end < t < two.start


def test_placed_pickup_wins_as_the_later_take():
    main = words_from("One. Show Claude forty clips. | Two. Ask it to grade the next one.")
    pickup = words_from("One. Show Claude forty-eight clips.")
    t = insertion_time(main, pickup, SCRIPT, {"one", "two", "three"})
    shift = max(w.end for w in pickup) + 0.5
    placed = [w for w in main if w.end <= t] + \
        [type(w)(w.text, w.start + t, w.end + t) for w in pickup] + \
        [type(w)(w.text, w.start + shift, w.end + shift) for w in main if w.start >= t]
    words, _ = apply_alignment(placed, SCRIPT, 0.6, {"one", "two", "three"})
    kept = " ".join(w.text for w in words if w.kept)
    assert "forty-eight" in kept and "forty clips" not in kept and "Two." in kept


def test_cli_takes_several_videos():
    args = build_parser().parse_args(["render", "--video", "a.MP4", "--video", "b.MP4", "--script", "s"])
    assert [str(v) for v in args.video] == ["a.MP4", "b.MP4"]


def test_a_one_word_tail_does_not_push_the_pickup_a_line_late():
    # DJI_0354: "...My Editor Already Graded" (no full stops) also matched step two's "grade"
    main = words_from("One. Show Claude forty clips my editor already graded. | "
                      "Two. Ask it to grade the next clip the same way. | Three. Check it.")
    pickup = words_from("1. Show Claude 48 Clips My Editor Already Graded")
    script = ("One. Show Claude forty-eight clips my editor already graded. "
              "Two. Ask it to grade the next clip the same way. Three. Check it.").split()
    t = insertion_time(main, pickup, script, {"one", "two", "three"})
    assert t < next(w for w in main if w.text == "Two.").start
