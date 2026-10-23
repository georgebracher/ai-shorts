"""Every piece of information sits inside the area TikTok and Reels leave clear."""
from PIL import Image

from ai_shorts.config import Config
from ai_shorts.layout import face_target, fit_video, inside
from ai_shorts.overlay import Overlay
from ai_shorts.spec import load_spec, parse_spec_text
from ai_shorts.timeline import chunk_captions
from conftest import SCRIPT
from test_script_captions import real_captions

CFG = Config()
SAFE = CFG.safe_rect
INFO = CFG.info_rect      # the safe area made symmetric about x=540


def overlay_for(spec, chunks=(), cfg=CFG, face=None):
    return Overlay(cfg, spec, [10.0 + i for i in range(len(spec.steps))], [5.0] * len(spec.stats),
                   list(chunks), [[1.0] * max(1, len(b.items)) for b in spec.beats], face)


def test_safe_numbers():
    assert SAFE == (60, 220, 940, 1440)
    assert INFO == (140, 220, 940, 1440) and (INFO[0] + INFO[2]) / 2 == 540


def test_001_every_text_box_inside_safe_area():
    # real captions from George's first take, plus the 001 title, beats, stats and steps
    ov = overlay_for(load_spec(SCRIPT), chunk_captions(real_captions(), CFG.caption_max_words,
                                                       CFG.caption_max_chars))
    kinds = {name.split()[0] for name, _ in ov.boxes}
    assert kinds == {"title", "card", "step", "stat", "beat", "caption"}
    outside = [(name, box) for name, box in ov.boxes if not inside(box, INFO)]
    assert outside == []


def rows(boxes):
    """Boxes that sit side by side (same kind, same top) form one row."""
    out: dict[tuple, list] = {}
    for name, box in boxes:
        out.setdefault((name.split()[0], round(box[1])), []).append(box)
    return out


def test_every_info_box_centred_on_frame_centre():
    ov = overlay_for(load_spec(SCRIPT), chunk_captions(real_captions(), CFG.caption_max_words,
                                                       CFG.caption_max_chars))
    off = {}
    for key, boxes in rows(ov.boxes).items():
        mid = (min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2
        if abs(mid - 540) > 2:
            off[key] = mid
    assert off == {}
    assert all(inside(b, INFO) for _, b in ov.boxes)


def test_long_content_still_inside_safe_area():
    steps = "\n".join(f"  - label: Step {i} has a rather long label that has to wrap somewhere\n"
                      f"    trigger: {w}" for i, w in enumerate(["one", "two", "three", "four", "five"], 1))
    spec = parse_spec_text(
        "---\nslug: x\ntitle: A much longer question title that cannot fit on one line at all?\n"
        f"steps:\n{steps}\nstats:\n  - Extremely long label for a stat 1,234,567\n  - B 2\n  - C 3\n"
        "beats:\n  - kind: chips\n    items: [Supercalifragilistic, Antidisestablishment, Pneumonia]\n"
        "  - kind: counter\n    value: 1000000\n    label: a counter with a long label\n"
        "---\nbody\n")
    ov = overlay_for(spec)
    assert [(n, b) for n, b in ov.boxes if not inside(b, INFO)] == []
    for key, boxes in rows(ov.boxes).items():
        assert abs((min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2 - 540) <= 2, key


def test_georges_face_lands_inside_safe_area_and_above_captions():
    fit = fit_video(CFG, 1080, 1920)               # his portrait phone recordings
    assert inside(fit.face, INFO)
    assert abs((fit.face[0] + fit.face[2]) / 2 - 540) <= 2         # centred on the frame
    assert fit.face[3] <= CFG.seam - CFG.caption_half
    assert fit.face[1] >= CFG.title_band[1]                    # not under the title strip
    assert fit.face[3] - fit.face[1] >= 0.97 * face_target(CFG)  # as big as the room allows


def test_outside_safe_area_only_video_gradient_or_brand_mark():
    ov = overlay_for(load_spec(SCRIPT))
    frame = ov.draw(ov.state(20.0))                      # steps showing
    x0, y0, x1, _ = ov.window
    assert y0 == CFG.window_inset                        # red border above the window too
    assert frame.getpixel((540, CFG.window_inset // 2))[3] == 255
    inner = range(x0 + CFG.window_radius, x1 - CFG.window_radius, 11)
    for y in range(y0 + CFG.window_border + 4, CFG.safe_top, 7):   # top band: video shows through
        for x in inner:
            assert frame.getpixel((x, y))[3] == 0, (x, y)
    bx0, by0, bx1, by1 = ov.brand_box
    brand_ink = 0
    shadow_fade = 32       # the info card's soft shadow fades out in the band's first 32 px
    for y in range(CFG.safe_bottom + shadow_fade, CFG.height, 5):  # gradient (+ grain) or brand
        want = ov.gradient_at(y)
        for x in range(0, CFG.width, 9):
            px = frame.getpixel((x, y))
            if bx0 <= x <= bx1 and by0 <= y <= by1:
                brand_ink += px[:3] != want[:3]
                continue
            assert px[3] == 255 and all(abs(a - b) <= CFG.grain for a, b in zip(px[:3], want[:3])), (x, y)
    assert brand_ink > 0
    assert by0 > CFG.safe_bottom                        # the brand mark is decoration, not info
    assert abs((bx0 + bx1) / 2 - 540) <= 2


def test_brand_mark_is_his_name_not_a_link():
    assert CFG.brand_mark == "George Bracher"
    assert not any(ch in CFG.brand_mark for ch in "@./:")


def test_grain_is_static_and_subtle():
    a = overlay_for(load_spec(SCRIPT)).base
    b = overlay_for(load_spec(SCRIPT)).base
    assert a.tobytes() == b.tobytes()                   # same seed: no flicker between frames
    red = Image.new("RGB", (1, 1), CFG.red).getpixel((0, 0))
    patch = [a.getpixel((x, 1000))[:3] for x in range(5, 18)]   # red margin beside the card
    assert len(set(patch)) > 1                           # textured
    assert all(abs(p[0] - red[0]) <= CFG.grain for p in patch)


def test_debug_layer_tints_unsafe_zones_only():
    cfg = Config(debug_safe=True)
    ov = overlay_for(load_spec(SCRIPT), cfg=cfg, face=fit_video(cfg, 1080, 1920).face)
    layer = ov.debug
    assert layer.getpixel((10, 10))[3] > 0                     # top bar tinted
    assert layer.getpixel((1000, 800))[3] > 0                  # right-hand buttons tinted
    assert layer.getpixel((300, 600))[3] == 0                  # safe area clear
    plain = overlay_for(load_spec(SCRIPT))
    assert plain.debug is None


def test_partial_rows_stay_centred_while_items_arrive():
    """Mid-reveal (one chip in a row, one stat card, one counter) nothing sits off-centre."""
    spec = load_spec(SCRIPT)
    times = [[1.0, 2.0, 3.0, 4.0], [5.0], [6.0]]
    ov = Overlay(CFG, spec, [20.0, 21, 22, 23], [9.0, 11.0], [], times)
    for t in (1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 9.5, 11.5):     # after each arrival settles
        state = ov.state(t)
        for key, boxes in rows(ov.visible_boxes(state)).items():
            mid = (min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2
            assert abs(mid - 540) <= 2, (t, key, mid)
    assert len(ov.visible_boxes(ov.state(1.5))) == 1          # really mid-reveal
