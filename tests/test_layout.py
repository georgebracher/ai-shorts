"""The panel template: big readable steps, no lone words, everything inside the panel."""
from ai_shorts.config import Config
from ai_shorts.overlay import Overlay, balanced_groups, font, has_orphan, wrap_balanced
from ai_shorts.spec import load_spec, parse_spec_text
from conftest import SCRIPT

CFG = Config()


def overlay_for(spec):
    return Overlay(CFG, spec, [10.0 + i for i in range(len(spec.steps))],
                   [5.0] * len(spec.stats), [], [[1.0] * max(1, len(b.items)) for b in spec.beats])


def test_balanced_wrap_never_leaves_a_lone_word():
    f = font(CFG.font_bold, 64)
    assert wrap_balanced("Publish, then re-ask every two weeks", f, 900) == [
        "Publish, then re-ask", "every two weeks"]
    assert not has_orphan(wrap_balanced("Ask all four AIs in the same hour", f, 900))
    assert wrap_balanced("Short one", f, 900) == ["Short one"]


def test_balanced_groups_prefers_even_rows():
    assert balanced_groups([300, 300, 300, 300], 2, 20, 980) == [2]
    assert balanced_groups([900, 900], 2, 20, 500) is None


def test_001_steps_are_big_and_fill_the_panel():
    # inside the platforms' safe area the four steps get ~450 px of height: 50 px text
    ov = overlay_for(load_spec(SCRIPT))
    top, bottom = ov.area
    assert ov.step_size >= 48
    rows = [(r["y"], r["y"] + r["h"]) for r in ov.step_rows]
    assert rows[0][0] >= top and rows[-1][1] <= bottom
    assert all(a[1] < b[0] for a, b in zip(rows, rows[1:]))           # no overlap
    used = sum(b - a for a, b in rows) / (bottom - top)
    assert used > 0.75                                                 # fills the panel


def test_long_step_lists_shrink_but_fit_without_orphans():
    steps = "\n".join(f"  - label: Step number {i} has quite a long label to wrap around\n"
                      f"    trigger: {w}" for i, w in enumerate(["one", "two", "three", "four", "five"], 1))
    spec = parse_spec_text(f"---\nslug: x\ntitle: A much longer question title that needs two lines?\n"
                           f"steps:\n{steps}\n---\nbody\n")
    ov = overlay_for(spec)
    assert ov.step_rows[-1]["y"] + ov.step_rows[-1]["h"] <= ov.area[1]


def test_a_layout_too_big_for_the_card_warns(capsys):
    # audit k3-008 (20 Oct 2026): nine long steps at the 26 px floor came out as overlapping rows
    # with no warning; only the last row crossed the safe area, so that check missed the rest
    label = "Step number {i} has quite a long label that has to wrap onto a second line"
    steps = "\n".join(f"  - label: {label.format(i=i)}\n    trigger: t{i}" for i in range(1, 10))
    chips = "\n".join(f"  - kind: chips\n    items: [Longer chip {i}a, Longer chip {i}b, Longer chip {i}c]"
                      for i in range(1, 7))
    for front, kind in ((f"steps:\n{steps}", "step"), (f"beats:\n{chips}", "beat")):
        spec = parse_spec_text(f"---\nslug: x\ntitle: T\n{front}\n---\nbody\n")
        ov = overlay_for(spec)
        assert ov.fit_problems and all(p.startswith(kind) for p in ov.fit_problems), ov.fit_problems
        out = capsys.readouterr().out
        assert "WARNING" in out and kind in out
    assert overlay_for(load_spec(SCRIPT)).fit_problems == []         # 001 fits: no warning
    assert capsys.readouterr().out == ""


def test_001_beats_inside_panel_and_chips_balanced():
    ov = overlay_for(load_spec(SCRIPT))
    top, bottom = ov.area
    for p in ov.beat_parts:
        h = p["img"].height if p["kind"] == "chip" else p["img"][1]
        assert top <= p["y"] and p["y"] + h <= bottom
    chip_rows = {}
    for p in ov.beat_parts:
        if p["kind"] == "chip":
            chip_rows.setdefault(p["y"], []).append(p)
    assert sorted(len(r) for r in chip_rows.values()) == [2, 2]       # 2 + 2, not 3 + 1
    assert ov.chip_size >= 48


def test_beats_clear_when_stats_or_first_step_arrive():
    ov = overlay_for(load_spec(SCRIPT))
    assert ov.beats_clear == 5.0
    beats, beats_out = ov.state(2.0)[3:5]
    assert beats_out == 0 and all(shown == 1 for shown, _ in beats)
    beats, beats_out = ov.state(5.5)[3:5]
    assert beats_out == 1


def test_counter_counts_up():
    ov = overlay_for(load_spec(SCRIPT))
    counts = [ov.state(t)[3][-1][1] for t in (1.0, 1.2, 1.5, 3.0)]
    assert counts[0] == 0 and counts[0] < counts[1] < counts[2] <= counts[3] == 200


def test_off_centre_faces_stay_inside_the_frame():
    # audit codex-002 (20 Oct 2026): a face near the left of a landscape clip put the picture
    # past the frame's right edge (a -299 px border); now the face centres and blur fills the gap
    from ai_shorts.config import FRAMINGS, Config
    from ai_shorts.layout import fit_video
    cfg = Config()
    boxes = [(0.05, 0.25, 0.25, 0.70), (0.75, 0.25, 0.95, 0.70), (0.40, 0.25, 0.60, 0.70),
             (0.02, 0.10, 0.12, 0.30), (0.30, 0.20, 0.70, 0.60)]
    for src in [(1920, 1080), (3840, 2160), (1728, 3072), (1080, 1920)]:
        for box in boxes:
            for framing in FRAMINGS:
                f = fit_video(cfg, *src, box, framing)
                assert f.place_x >= 0 and f.place_x + f.crop_w <= cfg.width, (src, box, framing)
                assert f.crop_x >= 0 and f.crop_x + f.crop_w <= f.scaled_w, (src, box, framing)
                assert abs((f.face[0] + f.face[2]) / 2 - cfg.center_x) <= 1, (src, box, framing)


def test_a_stat_said_after_the_steps_closes_the_video():
    # 003 (21 Oct 2026): "three times out of four" came after step four and its card was never seen
    from ai_shorts.spec import parse_spec_text
    spec = parse_spec_text("---\nslug: x\ntitle: T\nsteps:\n  - {label: A, trigger: one}\n"
                           "stats:\n  - {label: Detector, value: '50/50', trigger: coin}\n"
                           "  - {label: Claude, value: '3 in 4', trigger: three}\n---\nx\n")
    ov = Overlay(CFG, spec, [10.0], [5.0, 20.0], [])
    assert ov.outro_at == 20.0
    assert ov.state(15.0)[2] == 1.0                 # stats gone while the steps show
    late = ov.state(25.0)
    assert late[2] == 0.0 and late[6] == 1.0        # back for the close, steps faded
    assert len(ov.visible_boxes(late)) == 2
