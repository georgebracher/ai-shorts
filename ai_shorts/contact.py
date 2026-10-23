"""Stage 6: a 12-frame contact sheet PNG for a quick look at a render."""
import io
from pathlib import Path

from PIL import Image, ImageDraw

from .config import FFMPEG, Config
from .media import probe, run
from .overlay import font

COLS, ROWS, THUMB_W, THUMB_H, GUTTER, LABEL = 4, 3, 270, 480, 12, 34


def grab(video: Path, t: float) -> Image.Image:
    data = run([FFMPEG, "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
                "-frames:v", "1", "-vf", f"scale={THUMB_W}:{THUMB_H}",
                "-f", "image2pipe", "-c:v", "png", "-"], timeout=60, text=False).stdout
    return Image.open(io.BytesIO(data)).convert("RGB")


def contact_sheet(video: Path, dst: Path, cfg: Config) -> Path:
    dur = probe(video).duration
    n = COLS * ROWS
    sheet = Image.new("RGB", (COLS * (THUMB_W + GUTTER) + GUTTER,
                              ROWS * (THUMB_H + LABEL + GUTTER) + GUTTER), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    f = font(cfg.font_bold, 22)
    for i in range(n):
        t = (i + 0.5) * dur / n
        x = GUTTER + (i % COLS) * (THUMB_W + GUTTER)
        y = GUTTER + (i // COLS) * (THUMB_H + LABEL + GUTTER)
        sheet.paste(grab(video, t), (x, y))
        d.text((x + 4, y + THUMB_H + 6), f"{t:5.1f}s", font=f, fill=(230, 230, 230))
    sheet.save(dst)
    return dst
