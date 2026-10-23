"""Find George's face so the crop adapts to any camera.

Samples about one frame a second across the kept ranges, finds the face on each
with OpenCV's bundled Haar frontal-face cascade (local, free, no model download),
and takes a robust median box, ignoring misses and outliers. The crop that uses
it is static for the whole video: no tracking, no zoom wobble.

A Haar box is square (cheek to cheek, brow to chin). The layout talks about the
face from forehead to chin, so the box is converted with ratios measured on
George's iPhone take against a hand-measured box.
"""
import json
import os
import statistics
from pathlib import Path

import cv2
import numpy as np

from .config import FFMPEG
from .media import run
from .trim import Segment

CASCADE = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
SAMPLE_W = 540          # detect on frames scaled to this width
SCALE_FACTOR, MIN_NEIGHBORS = 1.1, 6
MIN_SIDE = 0.1          # smallest face searched for, as a share of the sample width
EVERY = 1.0             # seconds between samples
MAX_SAMPLES = 60
FACE_H = 1.32           # forehead-to-chin height per Haar box side
FACE_W = 0.84           # face width per Haar box side
MIN_HITS, MIN_SHARE = 3, 0.4
ENOUGH = 8              # this many agreeing hits is a face whatever the share: DJI_0353 (21 Oct
                        # 2026, blue top, pale wall) found him on 14 of 53 frames, all agreeing


def sample_times(segments: list[Segment], every: float = EVERY, max_n: int = MAX_SAMPLES) -> list[float]:
    """Source times about `every` seconds apart inside the kept ranges."""
    times = []
    for s in segments:
        t = s.start + min(every / 2, s.length / 2)
        while t < s.end:
            times.append(round(t, 2))
            t += every
    if len(times) > max_n:
        step = len(times) / max_n
        times = [times[int(k * step)] for k in range(max_n)]
    return times


def grab_gray(video: Path, t: float, width: int = SAMPLE_W) -> np.ndarray:
    out = run([FFMPEG, "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
               "-vf", f"scale={width}:-2,format=gray", "-f", "rawvideo", "-"], timeout=60, text=False).stdout
    return np.frombuffer(out, np.uint8).reshape(len(out) // width, width)


_cascade = None


def detect(gray: np.ndarray) -> tuple[float, float, float] | None:
    """Largest frontal face as (centre x, centre y, side), in sample pixels."""
    global _cascade
    if _cascade is None:
        _cascade = cv2.CascadeClassifier(CASCADE)
    w = gray.shape[1]
    found = _cascade.detectMultiScale(cv2.equalizeHist(gray), scaleFactor=SCALE_FACTOR,
                                      minNeighbors=MIN_NEIGHBORS,
                                      minSize=(int(w * MIN_SIDE), int(w * MIN_SIDE)))
    if len(found) == 0:
        return None
    x, y, fw, fh = max(found, key=lambda f: f[2] * f[3])
    return float(x + fw / 2), float(y + fh / 2), float((fw + fh) / 2)


def robust_box(hits: list[tuple[float, float, float] | None]) -> tuple[float, float, float] | None:
    """Median face over the samples. Misses are ignored; boxes far from the
    median (another face, a false hit) or a very different size are dropped
    before the final median. None if too few samples agree."""
    found = [h for h in hits if h is not None]
    if len(found) < MIN_HITS or (len(found) < MIN_SHARE * len(hits) and len(found) < ENOUGH):
        return None
    mx = statistics.median(h[0] for h in found)
    my = statistics.median(h[1] for h in found)
    md = statistics.median(h[2] for h in found)
    keep = [h for h in found if abs(h[0] - mx) <= 0.25 * md and abs(h[1] - my) <= 0.25 * md
            and 0.75 <= h[2] / md <= 1.33]
    if len(keep) < MIN_HITS or (len(keep) < MIN_SHARE * len(hits) and len(keep) < ENOUGH):
        return None
    return (float(statistics.median(h[0] for h in keep)), float(statistics.median(h[1] for h in keep)),
            float(statistics.median(h[2] for h in keep)))


def face_fractions(box: tuple[float, float, float], frame_w: int, frame_h: int) -> tuple[float, float, float, float]:
    """Haar (cx, cy, side) in pixels -> forehead-to-chin box as frame fractions."""
    cx, cy, d = box
    return (float((cx - FACE_W * d / 2) / frame_w), float((cy - FACE_H * d / 2) / frame_h),
            float((cx + FACE_W * d / 2) / frame_w), float((cy + FACE_H * d / 2) / frame_h))


def detect_face(video: Path, segments: list[Segment], work: Path) -> dict:
    """Face box for the whole video (cached in the work dir). 'face' is the
    forehead-to-chin box as source fractions, or None if nothing reliable."""
    times = sample_times(segments)
    cache = work / "faces.json"
    # what decides the raw boxes: a cache made with other settings would hold other boxes
    detector = {"cascade": os.path.basename(CASCADE), "width": SAMPLE_W, "scale": SCALE_FACTOR,
                "neighbors": MIN_NEIGHBORS, "min_side": MIN_SIDE}
    hits, size = None, None
    try:
        old = json.loads(cache.read_text())
    except (OSError, ValueError):       # none yet, or cut off mid-write: detect again
        old = {}
    if old.get("times") == times and old.get("detector") == detector and "detections" in old:
        # raw detections, so a rule or calibration change still applies
        hits = [tuple(h) if h else None for h in old["detections"]]
        size = tuple(old["sample_size"]) if old.get("sample_size") else None
    if hits is None:
        hits = []
        for t in times:
            gray = grab_gray(video, t, SAMPLE_W)
            size = gray.shape[::-1]
            hits.append(detect(gray))
    box = robust_box(hits)
    data = {"times": times, "detector": detector, "samples": len(times),
            "hits": sum(h is not None for h in hits),
            "sample_size": list(size) if size else None,
            "detections": [list(h) if h else None for h in hits],
            "median_px": [round(v, 1) for v in box] if box else None,
            "face": [round(v, 4) for v in face_fractions(box, *size)] if box else None}
    tmp = cache.with_name(f"faces-{os.getpid()}.partial.json")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, cache)
    return data
