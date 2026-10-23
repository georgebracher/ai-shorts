"""Frame geometry shared by the ffmpeg graph, the overlay and the tests."""
from dataclasses import dataclass

from .config import FRAMINGS, Config


def _even(x: float) -> int:
    return max(2, int(round(x / 2)) * 2)


@dataclass
class VideoFit:
    scaled_w: int      # source scaled to this size
    scaled_h: int
    crop_x: int        # crop of the scaled source shown in the video box
    crop_y: int
    crop_w: int
    crop_h: int
    box_top: int       # video box: window_inset..seam (red border above, like the sides)
    box_h: int
    place_x: int       # where the crop sits in the box; the blurred copy fills the rest
    place_y: int
    face: tuple[float, float, float, float]   # the face box used, on the output frame
    scale: float = 1.0                        # source -> output scale


def face_room(cfg: Config) -> tuple[float, float]:
    """Vertical room for head and face: below the title strip, above the captions."""
    return cfg.title_band[1] + 8, cfg.seam - cfg.caption_half


def face_target(cfg: Config, framing: str | None = None) -> float:
    """Face height (forehead to chin) the framing aims for."""
    f = FRAMINGS[framing or cfg.framing]
    if f.face_share is not None:
        return f.face_share * (cfg.seam - cfg.window_inset)
    top, bottom = face_room(cfg)                     # tight: fill the room, keep hair clear
    return (bottom - top) * cfg.face_fill / (1 + cfg.headroom)


def eye_target(cfg: Config, framing: str | None = None) -> float:
    """Frame y of the eye line: a share of the way down the visible window
    (below the title strip, above the seam)."""
    f = FRAMINGS[framing or cfg.framing]
    top = cfg.title_band[1]
    return top + f.eye_line * (cfg.seam - top)


def fit_video(cfg: Config, src_w: int, src_h: int,
              face_box: tuple[float, float, float, float] | None = None,
              framing: str | None = None) -> VideoFit:
    """Scale the source so the face (plus a little headroom for hair) fills the
    room between the title strip and the captions, centred on that room and on
    the frame centre (x=540). One static crop for the whole video. Where the
    source runs out (little headroom above George, or a portrait clip narrower
    than the frame) the blurred copy behind shows instead; never over the face."""
    box_top = cfg.window_inset
    box_h = cfg.seam - box_top
    l, t, r, b = face_box or cfg.face_box
    room_top, room_bottom = face_room(cfg)
    preset = FRAMINGS[framing or cfg.framing]
    s = face_target(cfg, framing) / ((b - t) * src_h)
    s = max(min(s, cfg.max_upscale), box_h / src_h)      # no soft upscales, no gaps
    sw, sh = _even(src_w * s), _even(src_h * s)
    face_cx = (l + r) / 2 * sw
    # Face centre lands on x=540; show the source wherever it covers the frame, blur elsewhere.
    # Audit codex-002 (20 Oct 2026): clamping the crop instead pushed an off-centre face's
    # picture past the frame edge (a -299 px border on a landscape clip).
    left_edge = int(round(cfg.center_x - face_cx))         # frame x of the scaled source's left edge
    px = max(0, left_edge)
    cw = min(cfg.width, left_edge + sw) - px
    cw -= cw % 2
    cx = px - left_edge
    face_h = (b - t) * sh
    if preset.face_share is None:
        # tight: head (hair) to chin centred in the room
        face_top = (room_top + room_bottom) / 2 - (face_h * (1 + cfg.headroom)) / 2 + cfg.headroom * face_h
    else:
        # eyes on the eye line, but hair always clear of the title strip
        face_top = eye_target(cfg, framing) - cfg.eye_in_face * face_h
        face_top = max(face_top, room_top + cfg.headroom * face_h)
    top = int(round(face_top - t * sh))              # frame y of the scaled source's top edge
    if top + sh < cfg.seam:          # never run out at the bottom, next to the captions
        top = cfg.seam - sh
    crop_y, place_y = max(0, box_top - top), max(0, top - box_top)
    crop_h = min(sh - crop_y, box_h - place_y)
    face = (px + l * sw - cx, top + t * sh, px + r * sw - cx, top + b * sh)
    return VideoFit(sw, sh, cx, crop_y, cw, crop_h, box_top, box_h, px, place_y, face, round(s, 4))


def inside(box, rect) -> bool:
    x0, y0, x1, y1 = box
    l, t, r, b = rect
    return x0 >= l and y0 >= t and x1 <= r and y1 <= b
