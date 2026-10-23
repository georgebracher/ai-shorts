"""Stage 4b: draw the overlay for any output time.

Each frame is a 1080x1920 RGBA image: a red header holding the title, a
transparent window over George, captions straddling the seam, and the red panel
below. The panel's info area holds, in turn: beats (hook graphics) -> stats ->
steps. Everything that carries information sits inside the platforms' shared
safe area (config.safe_*); outside it there is only plain red. `state(t)` reduces a time to
what is on screen; identical states reuse the previous frame's bytes, so the
cost is only in frames where something moves.
"""
import re
from functools import lru_cache
from itertools import combinations

import numpy as np
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter, ImageFont

from .config import Config
from .spec import Spec
from .timeline import Chunk, display_word, warn

STEP_MAX, STEP_MIN = 74, 26
CHIP_MAX, CHIP_MIN = 76, 34
INSET = 12           # step pill padding inside the safe area


@lru_cache(maxsize=128)
def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def rgba(color: str, alpha: float = 1.0) -> tuple[int, int, int, int]:
    r, g, b = ImageColor.getrgb(color)[:3]
    return r, g, b, round(255 * alpha)


def mix(a: str, b: str, k: float) -> tuple[int, int, int, int]:
    """Solid colour k of the way from b to a (drawing with alpha onto the
    overlay would punch a see-through hole, not blend)."""
    ca, cb = ImageColor.getrgb(a)[:3], ImageColor.getrgb(b)[:3]
    return tuple(round(x * k + y * (1 - k)) for x, y in zip(ca, cb)) + (255,)


def ease(p: float) -> float:
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def with_alpha(img: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return img
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda v: round(v * a)))
    return out


# ---------- wrapping ----------
def wrap(text: str, fnt, width: int) -> list[str]:
    """Greedy wrap."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if fnt.getlength(trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    return lines + ([cur] if cur else [])


def balanced_groups(widths: list[float], n: int, gap: float, limit: float) -> list[int] | None:
    """Split items into n consecutive groups, avoiding one-item groups when the
    whole has more than n items, then minimising the widest group.
    Returns break indices, or None if nothing fits."""
    best = None
    for breaks in combinations(range(1, len(widths)), n - 1):
        bounds = list(zip((0,) + breaks, breaks + (len(widths),)))
        group_w = [sum(widths[a:b]) + gap * (b - a - 1) for a, b in bounds]
        if max(group_w) > limit:
            continue
        lonely = sum(1 for a, b in bounds if b - a == 1) if len(widths) > n else 0
        key = (lonely, max(group_w))
        if best is None or key < best[0]:
            best = (key, list(breaks))
    return None if best is None else best[1]


def wrap_balanced(text: str, fnt, width: int) -> list[str]:
    """Same line count as a greedy wrap, but even lines and no lone last word
    ("Publish, then re-ask every two / weeks" -> "... re-ask / every two weeks")."""
    words = text.split()
    n = len(wrap(text, fnt, width))
    if n <= 1:
        return [text]
    breaks = balanced_groups([fnt.getlength(w) for w in words], n, fnt.getlength(" "), width)
    if breaks is None:
        return wrap(text, fnt, width)
    bounds = zip([0] + breaks, breaks + [len(words)])
    return [" ".join(words[a:b]) for a, b in bounds]


def has_orphan(lines: list[str]) -> bool:
    return len(lines) > 1 and any(" " not in ln for ln in lines)


def split_number(value: str) -> tuple[str, int | None, str]:
    """'$7' -> ('$', 7, ''), '42%' -> ('', 42, '%'), 'n/a' -> ('n/a', None, '')."""
    m = re.fullmatch(r"(\D*)([\d,]+)(\D*)", value.strip())
    if not m:
        return value, None, ""
    return m.group(1), int(m.group(2).replace(",", "")), m.group(3)


class Overlay:
    def __init__(self, cfg: Config, spec: Spec, step_times: list[float],
                 stat_times: list[float | None], chunks: list[Chunk],
                 beat_times: list[list[float] | None] | None = None,
                 face_box: tuple[float, float, float, float] | None = None):
        self.cfg, self.spec = cfg, spec
        self.step_times, self.stat_times, self.chunks = step_times, stat_times, chunks
        self.beat_times = beat_times or [None] * len(spec.beats)
        self.W, self.H = cfg.width, cfg.height
        self.L, self.T, self.R, self.B = cfg.info_rect   # x 140-940: symmetric about 540
        self.CX = cfg.center_x                           # everything centres on the frame
        self.boxes: list[tuple[str, tuple]] = []  # every information box, for the safe-area test
        # the info card fills the safe area under the captions; content sits inside it
        self.card = (self.L, cfg.seam + cfg.caption_half + 4, self.R, self.B - 4)
        self.CL, self.CR = self.card[0] + cfg.card_pad, self.card[2] - cfg.card_pad
        self.area = (self.card[1] + cfg.card_pad, self.card[3] - cfg.card_pad)
        self.base = self._base()
        self.step_rows = self._step_sprites()
        self.stat_cards = self._stat_sprites()
        self.beat_parts = self._beat_sprites()
        self.fit_problems = self._fit_problems()
        for p in self.fit_problems:
            warn(p)
        self._caption_boxes()
        self.debug = self._debug_layer(face_box) if cfg.debug_safe else None
        firsts = [x for x in stat_times if x is not None] + list(step_times[:1])
        self.beats_clear = min(firsts) if firsts else float("inf")
        # A stat said after the steps began (003's "three times out of four") is a closing card:
        # the steps fade and the whole stat row comes back with it. Before 21 Oct 2026 such a
        # stat was drawn under the steps and never seen.
        first_step = step_times[0] if step_times else float("inf")
        late = [x for x in stat_times if x is not None and x > first_step]
        self.outro_at = min(late) if late else None
        self._last_state, self._last_bytes = None, b""

    # ---------- static pieces ----------
    def _base(self) -> Image.Image:
        """Everything static. Red surfaces with grain; a window for George's video
        (red border all round, rounded corners, thin off-white stroke) with
        the title on a semi-transparent strip; the info card with a soft shadow;
        under the safe area a red gradient and the brand mark (decoration only)."""
        c = self.cfg
        W, H, seam = self.W, self.H, c.seam
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        if c.bg_stops:                       # a palette's gradient over the whole frame
            for y in range(H):
                d.line([0, y, W, y], fill=self.stops_at(y))
        else:
            d.rectangle([0, 0, W, self.B - 1], fill=rgba(c.red))
            for y in range(self.B, H):
                d.line([0, y, W, y], fill=self.gradient_at(y))
        # punch the video window
        r = c.window_radius
        self.window = (c.window_inset, c.window_inset, W - c.window_inset, seam)
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).rounded_rectangle(self.window, radius=r, fill=255)
        img.putalpha(ImageChops.subtract(img.getchannel("A"), mask))
        # title strip across the window
        t0, t1 = c.title_band
        strip = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(strip).rectangle([self.window[0], t0, self.window[2] - 1, t1 - 1],
                                        fill=rgba(c.red, c.title_strip_alpha))
        img.alpha_composite(strip)
        # info card: soft shadow, darker fill, thin tint border
        x0, y0, x1, y1 = self.card
        if c.card_shadow:
            sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(sh).rounded_rectangle([x0, y0 + 8, x1, y1 + 8], radius=c.card_radius,
                                                 fill=(40, 0, 6, c.card_shadow))
            img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(12)))
        fill = mix(c.red_dark, c.red, c.card_darken)
        d.rounded_rectangle(self.card, radius=c.card_radius, fill=fill,
                            outline=mix(c.red_tint, "#%02x%02x%02x" % fill[:3], 0.55) if c.card_border else None,
                            width=c.card_border or 1)
        self.boxes.append(("card", self.card))
        self._add_grain(img)
        # border round the window (drawn after the grain so the line stays clean)
        if c.window_border:
            d.rounded_rectangle(self.window, radius=r, outline=rgba(c.text_color), width=c.window_border)
        if c.brand_mark:
            bf = font(c.font_bold, 34)
            d.text((W / 2, c.brand_y), c.brand_mark, font=bf, fill=rgba(c.red_tint), anchor="mm")
            self.brand_box = d.textbbox((W / 2, c.brand_y), c.brand_mark, font=bf, anchor="mm")
        # title
        width = self.R - self.L
        lines, f, line_h = None, None, 0
        for size in range(56, 27, -2):        # one line if possible, else two
            f = font(c.font_heavy, size)
            line_h = round(size * 1.12)
            lines = [self.spec.title] if f.getlength(self.spec.title) <= width else \
                wrap_balanced(self.spec.title, f, width)
            if len(lines) <= 2 and len(lines) * line_h <= (t1 - t0) - 8:
                break
        y = t0 + ((t1 - t0) - len(lines) * line_h) / 2
        for line in lines:
            d.text((self.CX, y + line_h / 2), line, font=f, fill=rgba(c.text_color), anchor="mm")
            self.boxes.append(("title", d.textbbox((self.CX, y + line_h / 2), line, font=f, anchor="mm")))
            y += line_h
        return img

    def _add_grain(self, img: Image.Image) -> None:
        """Static luminance noise on every drawn (red) pixel; same seed every render."""
        g = self.cfg.grain
        if not g:
            return
        a = np.asarray(img).astype(np.int16)
        noise = np.random.default_rng(self.cfg.grain_seed).integers(-g, g + 1, a.shape[:2], dtype=np.int16)
        drawn = a[..., 3] > 0
        for ch in range(3):
            a[..., ch] = np.where(drawn, np.clip(a[..., ch] + noise, 0, 255), a[..., ch])
        img.paste(Image.fromarray(a.astype(np.uint8), "RGBA"))

    def stops_at(self, y: int) -> tuple[int, int, int, int]:
        """Background colour at row y from the palette's evenly spaced stops."""
        stops = [ImageColor.getrgb(s)[:3] for s in self.cfg.bg_stops]
        k = y / max(1, self.H - 1) * (len(stops) - 1)
        i = min(int(k), len(stops) - 2)
        f = k - i
        return tuple(round(a + (b - a) * f) for a, b in zip(stops[i], stops[i + 1])) + (255,)

    def gradient_at(self, y: int) -> tuple[int, int, int, int]:
        """Bottom band colour: panel red at the safe edge to red_dark at the frame foot."""
        top, bot = ImageColor.getrgb(self.cfg.red)[:3], ImageColor.getrgb(self.cfg.red_dark)[:3]
        k = (y - self.B) / max(1, self.H - 1 - self.B)
        return tuple(round(a + (b - a) * k) for a, b in zip(top, bot)) + (255,)

    def _step_layout(self, size: int):
        """Per row: (font size, lines, height) at a base size, shrinking a row
        a little rather than leaving one word on its own line."""
        c = self.cfg
        badge, pad = self._badge(size), round(size * 0.22)
        text_w = (self.CR - INSET) - (self.CL + INSET + badge + 16)
        rows = []
        for step in self.spec.steps:
            s = size
            lines = wrap_balanced(step.label, font(c.font_bold, s), text_w)
            while has_orphan(lines) and s > size * 0.86:
                s -= 2
                lines = wrap_balanced(step.label, font(c.font_bold, s), text_w)
            rows.append((s, lines, max(badge, len(lines) * round(s * 1.12)) + 2 * pad))
        return rows

    @staticmethod
    def _badge(size: int) -> int:
        return round(size * 1.0)

    def _step_sprites(self) -> list[dict]:
        """Two sprites per step (current, past) at fixed slots that fill the area."""
        c, steps = self.cfg, self.spec.steps
        if not steps:
            return []
        top, bottom = self.area
        min_gap = 8
        for size in range(STEP_MAX, STEP_MIN - 1, -2):
            rows = self._step_layout(size)
            if sum(h for *_, h in rows) + min_gap * (len(rows) - 1) <= bottom - top:
                break
        badge = self._badge(size)
        bx = self.CL + INSET
        text_x = bx + badge + 16
        spare = (bottom - top) - sum(h for *_, h in rows)
        gap = min(40, spare / (len(rows) + 1))
        y = top + (spare - gap * (len(rows) - 1)) / 2
        out = []
        for i, (s, lines, h) in enumerate(rows):
            f, line_h = font(c.font_bold, s), round(s * 1.12)
            sprites = {}
            for mode in ("current", "past"):
                img = Image.new("RGBA", (self.W, h), (0, 0, 0, 0))
                d = ImageDraw.Draw(img)
                by = (h - badge) // 2
                if mode == "current":
                    d.rounded_rectangle([self.CL, 0, self.CR - 1, h - 1], radius=22,
                                        fill=rgba(c.text_color))
                    d.ellipse([bx, by, bx + badge, by + badge], fill=rgba(c.accent_text or c.red))
                    num_col, txt_col = rgba(c.text_color), rgba(c.accent_text or c.red)
                else:
                    d.ellipse([bx, by, bx + badge, by + badge], outline=rgba(c.red_tint), width=4)
                    num_col = txt_col = rgba(c.red_tint)
                d.text((bx + badge / 2, by + badge / 2), str(i + 1),
                       font=font(c.font_heavy, round(badge * 0.55)), fill=num_col, anchor="mm")
                ty = (h - len(lines) * line_h) / 2
                for line in lines:
                    d.text((text_x, ty + line_h / 2), line, font=f, fill=txt_col, anchor="lm")
                    ty += line_h
                sprites[mode] = img
            out.append({"y": round(y), "h": h, **sprites})
            self.boxes.append((f"step {i + 1}", (self.CL, round(y), self.CR, round(y) + h)))
            y += h + gap
        self.step_badge_x = (bx, bx + badge)
        self.step_size = size
        return out

    def _card_sizes(self, w: int, h: int, value: str, label: str) -> tuple[int, int]:
        """Largest value and label font sizes that fit one card."""
        c = self.cfg
        size = round(h * 0.5)
        while font(c.font_heavy, size).getlength(value) > w - 50 and size > 30:
            size -= 4
        label_size = min(60, max(30, round(h * 0.19)))
        while font(c.font_bold, label_size).getlength(label) > w - 36 and label_size > 20:
            label_size -= 2
        return size, label_size

    def _card(self, w: int, h: int, value: str, label: str,
              sizes: tuple[int, int] | None = None) -> Image.Image:
        """Dark red card: big number, label under it. `sizes` lets a row share one size."""
        c = self.cfg
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=28, fill=rgba(c.red_dark))
        size, label_size = sizes or self._card_sizes(w, h, value, label)
        d.text((w / 2, h * 0.43), value, font=font(c.font_heavy, size),
               fill=rgba(c.text_color), anchor="mm")
        if label:
            d.text((w / 2, h * 0.80), label, font=font(c.font_bold, label_size),
                   fill=rgba(c.red_tint), anchor="mm")
        return img

    def _stat_sprites(self) -> list[dict]:
        stats = self.spec.stats
        if not stats:
            return []
        gap, n = 24, len(stats)
        card_w = (self.CR - self.CL - gap * (n - 1)) // n
        top, bottom = self.area
        card_h = min(400, round((bottom - top) * 0.85), round(card_w * 1.0))
        y = top + (bottom - top - card_h) // 2
        # one value size and one label size for the row: "Restarts" next to "Minutes filmed"
        # came out a size bigger (002, 21 Oct 2026)
        fits = [self._card_sizes(card_w, card_h, st.value, st.label) for st in stats]
        sizes = (min(f[0] for f in fits), min(f[1] for f in fits))
        cards = []
        for i, st in enumerate(stats):
            x = self.CL + i * (card_w + gap)
            cards.append({"img": self._card(card_w, card_h, st.value, st.label, sizes), "x": x, "y": y})
            self.boxes.append((f"stat {i + 1}", (x, y, x + card_w, y + card_h)))
        return cards

    def _chip_block(self, bi: int, size: int) -> dict:
        """One chips beat as a block: pills in balanced rows, centred."""
        c, width = self.cfg, self.CR - self.CL
        f = font(c.font_heavy, size)
        pad_x, chip_h, gap = round(size * 0.55), round(size * 1.8), round(size * 0.3)
        imgs = []
        for chip in self.spec.beats[bi].items:
            cf = f
            while cf.getlength(chip.label) + 2 * pad_x > width and cf.size > 20:
                cf = font(c.font_heavy, cf.size - 2)     # one very long chip shrinks alone
            w = round(cf.getlength(chip.label)) + 2 * pad_x
            img = Image.new("RGBA", (w, chip_h), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([0, 0, w - 1, chip_h - 1], radius=chip_h // 2, fill=rgba(c.text_color))
            d.text((w / 2, chip_h / 2), chip.label, font=cf, fill=rgba(c.accent_text or c.red), anchor="mm")
            imgs.append(img)
        widths = [im.width for im in imgs]
        breaks = []
        if sum(widths) + gap * (len(widths) - 1) > width:
            for n_rows in range(2, len(imgs) + 1):     # fewest rows that fit, balanced
                found = balanced_groups(widths, n_rows, gap, width)
                if found is not None:
                    breaks = found
                    break
        parts, y = [], 0
        for a, b in zip([0] + breaks, breaks + [len(imgs)]):
            row_w = sum(widths[a:b]) + gap * (b - a - 1)
            x = self.CX - row_w / 2
            for k in range(a, b):
                parts.append((bi, k, imgs[k], round(x), y, "chip"))
                x += widths[k] + gap
            y += chip_h + gap
        return {"h": y - gap, "parts": parts}

    def _beat_sprites(self) -> list[dict]:
        """Lay beats out as blocks spread down the area, chips as big as fit.
        Consecutive counters share a row."""
        if not self.spec.beats:
            return []
        width = self.CR - self.CL
        top, bottom = self.area
        for size in range(CHIP_MAX, CHIP_MIN - 1, -4):
            blocks = []
            for bi, beat in enumerate(self.spec.beats):
                if beat.kind == "chips":
                    blocks.append(self._chip_block(bi, size))
                elif blocks and "counters" in blocks[-1]:
                    blocks[-1]["counters"].append(bi)
                else:
                    blocks.append({"counters": [bi]})
            for blk in blocks:
                if "counters" in blk:
                    n, gap = len(blk["counters"]), 24
                    w = (width - gap * (n - 1)) // n
                    blk["h"] = h = min(240, round(w * 0.75), round(size * 3.6))
                    blk["parts"] = [(bi, 0, (w, h), self.CL + k * (w + gap), 0, "counter")
                                    for k, bi in enumerate(blk["counters"])]
            if sum(b["h"] for b in blocks) + 16 * (len(blocks) + 1) <= bottom - top:
                break
        spare = (bottom - top) - sum(b["h"] for b in blocks)
        gap = max(0, spare / (len(blocks) + 1))
        y, parts = top + gap, []
        for blk in blocks:
            for bi, pi, img, x, dy, kind in blk["parts"]:
                py = round(y + dy)
                parts.append({"beat": bi, "part": pi, "img": img, "x": x, "y": py, "kind": kind})
                w, h = (img.width, img.height) if kind == "chip" else img
                self.boxes.append((f"beat {bi + 1}.{pi + 1}", (x, py, x + w, py + h)))
            y += blk["h"] + gap
        self.chip_size = size
        return parts

    def _fit_problems(self) -> list[str]:
        """Steps, beats and stats each show together: every piece must sit inside the card's content
        area without overlapping another. The fonts stop shrinking at a floor, and nine long steps
        came out as eight overlapping rows with no warning (audit k3-008, 20 Oct 2026)."""
        top, bottom = self.area
        out = []
        for kind, size in (("step", getattr(self, "step_size", None)), ("beat", getattr(self, "chip_size", None)),
                           ("stat", None)):
            boxes = [(n, b) for n, b in self.boxes if n.split()[0] == kind]
            outside = [n for n, (x0, y0, x1, y1) in boxes
                       if x0 < self.CL - 1 or x1 > self.CR + 1 or y0 < top - 1 or y1 > bottom + 1]
            hits = {n for (a, p), (b, q) in combinations(boxes, 2)
                    if p[0] < q[2] and q[0] < p[2] and p[1] < q[3] and q[1] < p[3] for n in (a, b)}
            parts = ([f"outside: {', '.join(outside)}"] if outside else []) + \
                ([f"overlapping: {', '.join(n for n, _ in boxes if n in hits)}"] if hits else [])
            if parts:
                at = f" even at {size} px" if size else ""
                out.append(f"{kind}s do not fit the info card{at}: {'; '.join(parts)}; shorten or cut the {kind}s")
        return out

    def _caption_layout(self, chunk_i: int):
        """Font, stroke, baseline and word x positions for one caption chunk,
        shrunk until it fits the safe width, centred on the safe centre."""
        c = self.cfg
        words = [display_word(w.text) for w in self.chunks[chunk_i].words]
        size = c.caption_size
        while True:
            f = font(c.font_heavy, size)
            stroke = max(4, round(size * 0.12))
            space = f.getlength(" ")
            total = sum(f.getlength(w) for w in words) + space * (len(words) - 1)
            if total + 2 * stroke <= self.R - self.L - 2 or size <= 30:   # 2 px: glyph edges round past the box
                break
            size -= 2
        cap_top = f.getbbox("HG", anchor="ls")[1]
        baseline = c.seam - cap_top / 2
        xs, x = [], self.CX - total / 2
        for w in words:
            xs.append(x)
            x += f.getlength(w) + space
        return words, f, stroke, baseline, xs

    def _caption_boxes(self) -> None:
        d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        for i in range(len(self.chunks)):
            words, f, stroke, baseline, xs = self._caption_layout(i)
            bbs = [d.textbbox((x, baseline), w, font=f, anchor="ls", stroke_width=stroke)
                   for w, x in zip(words, xs)]
            self.boxes.append((f"caption {i + 1}", (min(b[0] for b in bbs), min(b[1] for b in bbs),
                                                    max(b[2] for b in bbs), max(b[3] for b in bbs))))

    def _debug_layer(self, face_box) -> Image.Image:
        """Zones the apps cover tinted magenta; the strip left unused to keep the
        information symmetric tinted lighter; info box and face box outlined."""
        img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        sl, st, sr, sb = self.cfg.safe_rect
        tint = (255, 0, 200, 90)
        d.rectangle([0, 0, self.W, st - 1], fill=tint)
        d.rectangle([0, sb, self.W, self.H], fill=tint)
        d.rectangle([0, st, sl - 1, sb - 1], fill=tint)
        d.rectangle([sr, st, self.W, sb - 1], fill=tint)
        d.rectangle([sl, st, self.L - 1, sb - 1], fill=(255, 0, 200, 40))
        d.rectangle([self.L, self.T, self.R - 1, self.B - 1], outline=(255, 0, 200, 255), width=3)
        d.line([self.CX, 0, self.CX, self.H], fill=(0, 255, 255, 160), width=2)
        if face_box:
            d.rectangle([round(v) for v in face_box], outline=(0, 255, 255, 255), width=4)
        return img

    def layout(self) -> dict:
        """Where things sit, for tests and the report."""
        return {"area": list(self.area),
                "step_rows": [[r["y"], r["y"] + r["h"]] for r in self.step_rows],
                "step_badge_x": list(getattr(self, "step_badge_x", (0, 0))),
                "step_font": getattr(self, "step_size", None),
                "chip_font": getattr(self, "chip_size", None),
                "beat_parts": [[p["x"], p["y"]] for p in self.beat_parts],
                "boxes": [[name, [round(v) for v in box]] for name, box in self.boxes]}
    # ---------- per frame ----------
    def state(self, t: float) -> tuple:
        a = self.cfg.anim
        q = lambda p: round(ease(p), 3)
        steps = tuple(q((t - st) / a) for st in self.step_times)
        first_step = self.step_times[0] if self.step_times else float("inf")
        back = q((t - self.outro_at) / a) if self.outro_at is not None else 0.0
        stats_out = max(0.0, q((t - first_step) / a) - back)
        stats = tuple(0.0 if st is None else q((t - st) / a) for st in self.stat_times)
        beats_out = q((t - self.beats_clear) / a)
        beats = []
        if beats_out < 1:
            for p in self.beat_parts:
                times = self.beat_times[p["beat"]]
                if times is None:
                    beats.append((0.0, 0))
                    continue
                t0 = times[p["part"]]
                shown = q((t - t0) / a)
                count = 0
                if p["kind"] == "counter":
                    _, n, _ = split_number(self.spec.beats[p["beat"]].value)
                    count = round((n or 0) * ease((t - t0) / self.cfg.count_up))
                beats.append((shown, count))
        return steps, stats, stats_out, tuple(beats), beats_out, self._caption_state(t), back

    def _caption_state(self, t: float):
        for i, ch in enumerate(self.chunks):
            nxt = self.chunks[i + 1].start if i + 1 < len(self.chunks) else None
            hold_until = nxt if (nxt is not None and nxt - ch.end < 0.6) else ch.end + 0.25
            if ch.start <= t < hold_until:
                active = max(k for k, w in enumerate(ch.words) if w.start <= t or k == 0)
                return i, active
        return None

    @staticmethod
    def _width(item: dict) -> int:
        img = item["img"]
        return img.width if isinstance(img, Image.Image) else img[0]

    def _row_xs(self, items: list[dict], shown: list[float]) -> list[float]:
        """x for each item in a row so whatever is visible is centred on x=540.
        A newly appearing item grows into the row, so the others slide over
        smoothly instead of the row sitting off-centre in its final slots."""
        ws = [self._width(it) for it in items]
        gap = items[1]["x"] - items[0]["x"] - ws[0] if len(items) > 1 else 0
        vis = [(i, min(1.0, max(0.0, s))) for i, s in enumerate(shown) if s > 0]
        total = sum(ws[i] * s for i, s in vis) + gap * sum(s for _, s in vis[1:])
        xs, x = [0.0] * len(items), self.CX - total / 2
        for k, (i, s) in enumerate(vis):
            if k:
                x += gap * s
            xs[i] = x
            x += ws[i] * s
        return xs

    def beat_rows(self) -> list[list[int]]:
        """Indices of beat parts that share a row, in order."""
        rows: dict[tuple, list[int]] = {}
        for i, p in enumerate(self.beat_parts):
            rows.setdefault((p["kind"], p["y"]), []).append(i)
        return list(rows.values())

    def visible_boxes(self, state: tuple) -> list[tuple[str, tuple]]:
        """Boxes of the beats and stats on screen in this state (for the centring test)."""
        steps, stats, stats_out, beats, beats_out, cap, back = state
        out = []
        if beats_out < 1:
            for row in self.beat_rows():
                items = [self.beat_parts[i] for i in row]
                shown = [beats[i][0] for i in row]
                for it, x, sh in zip(items, self._row_xs(items, shown), shown):
                    if sh >= 1:
                        out.append((f"beat-row{items[0]['y']}", (x, it["y"], x + self._width(it),
                                                                 it["y"] + 1)))
        if stats_out < 1 and self.stat_cards:
            for card, x, p in zip(self.stat_cards, self._row_xs(self.stat_cards, list(stats)), stats):
                if p >= 1:
                    out.append(("stats", (x, card["y"], x + card["img"].width, card["y"] + 1)))
        return out

    def draw(self, state: tuple) -> Image.Image:
        steps, stats, stats_out, beats, beats_out, cap, back = state
        img = self.base.copy()
        # beats: hook graphics until the stats or first step arrive
        if beats_out < 1:
            for row in self.beat_rows():
                items = [self.beat_parts[i] for i in row]
                xs = self._row_xs(items, [beats[i][0] for i in row])
                for i, part, x in zip(row, items, xs):
                    shown, count = beats[i]
                    if shown <= 0:
                        continue
                    if part["kind"] == "chip":
                        sprite = part["img"]
                    else:
                        beat = self.spec.beats[part["beat"]]
                        pre, n, post = split_number(beat.value)
                        text = beat.value if n is None else f"{pre}{count:,}{post}"
                        sprite = self._card(*part["img"], text, beat.label)
                    img.alpha_composite(with_alpha(sprite, shown * (1 - beats_out)),
                                        (round(x), part["y"] + round((1 - shown) * 36)))
        # stats, until the steps take over the area
        if stats_out < 1 and self.stat_cards:
            xs = self._row_xs(self.stat_cards, list(stats))
            for card, p, x in zip(self.stat_cards, stats, xs):
                if p > 0:
                    img.alpha_composite(with_alpha(card["img"], p * (1 - stats_out)),
                                        (round(x), card["y"] + round((1 - p) * 40)))
        # steps: the latest started one is current, earlier ones are past; all fade for a closing stat
        started = [i for i, p in enumerate(steps) if p > 0] if back < 1 else []
        cur = started[-1] if started else None
        keep = 1 - back
        for i in started:
            row, p = self.step_rows[i], steps[i]
            if i == cur:
                img.alpha_composite(with_alpha(row["current"], p * keep), (round((1 - p) * 90), row["y"]))
            else:
                handover = steps[i + 1]   # crossfade current -> past as the next slides in
                if handover < 1:
                    img.alpha_composite(with_alpha(row["current"], (1 - handover) * keep), (0, row["y"]))
                img.alpha_composite(with_alpha(row["past"], handover * keep), (0, row["y"]))
        if cap is not None:
            self._draw_caption(img, *cap)
        if self.debug is not None:
            img.alpha_composite(self.debug)
        return img

    def _draw_caption(self, img: Image.Image, chunk_i: int, active: int) -> None:
        c = self.cfg
        words, f, stroke, baseline, xs = self._caption_layout(chunk_i)
        d = ImageDraw.Draw(img)
        for k, (w, x) in enumerate(zip(words, xs)):
            col = c.highlight_color if k == active else "#FFFFFF"
            d.text((x, baseline), w, font=f, fill=rgba(col), anchor="ls",
                   stroke_width=stroke, stroke_fill=rgba(c.caption_outline))

    def frame_bytes(self, t: float) -> bytes:
        st = self.state(t)
        if st != self._last_state:
            self._last_state, self._last_bytes = st, self.draw(st).tobytes()
        return self._last_bytes
