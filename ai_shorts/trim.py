"""Stage 3b: edit decision list (kept source ranges) and the output<->source time map."""
import bisect
from dataclasses import dataclass, replace

from .transcribe import Word


@dataclass
class Segment:
    start: float   # source seconds
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


def build_segments(words: list[Word], duration: float, pad: float = 0.12,
                   max_pause: float = 0.6, fps: int = 30,
                   silences: list[tuple[float, float]] | None = None,
                   quiet=None) -> list[Segment]:
    """Kept speech ranges. A new range starts after a dropped word or a pause
    longer than max_pause; each range gets `pad` either side, never reaching
    into a neighbouring (possibly dropped) word. A measured silence longer than
    max_pause inside a range is cut too: whisper sometimes stretches one word
    over a long pause. With `quiet` (audio.Envelope.quiet), an edge that lands
    on sound moves to the nearest quiet moment. Edges snap to the frame grid so
    audio and video cut on the same instants."""
    runs: list[list[int]] = []
    for i, w in enumerate(words):
        if not w.kept:
            continue
        prev = runs[-1][-1] if runs else None
        if prev is not None and prev == i - 1 and w.start - words[prev].end <= max_pause:
            runs[-1].append(i)
        else:
            runs.append([i])

    segs: list[Segment] = []
    for run in runs:
        a, b = run[0], run[-1]
        before = words[a - 1].end if a > 0 else 0.0
        after = words[b + 1].start if b + 1 < len(words) else duration
        lo = max(words[a].start - pad, before, 0.0)
        hi = min(words[b].end + pad, after, duration)
        if quiet:                          # cut in silence, not on the tail of a word
            lo, hi = snap_start(lo, quiet, before), snap_end(hi, quiet, after)
        lo, hi = round(lo * fps) / fps, round(hi * fps) / fps
        if hi - lo < 1 / fps:
            continue
        if segs and lo <= segs[-1].end:
            segs[-1].end = max(segs[-1].end, hi)
        else:
            segs.append(Segment(lo, hi))
    for s0, s1 in silences or []:
        if s1 - s0 <= max_pause:
            continue
        cut0, cut1 = round((s0 + pad) * fps) / fps, round((s1 - pad) * fps) / fps
        for k, seg in enumerate(segs):
            if seg.start < cut0 and cut1 < seg.end:
                segs[k:k + 1] = [Segment(seg.start, cut0), Segment(cut1, seg.end)]
                break
    return segs


SNAP = 0.4      # furthest a cut moves forward/back to land in silence
NUDGE = 0.15    # how far it may step back into a word's own fade instead
STEP = 0.01


def _on_sound(t: float, quiet, before: bool) -> bool:
    """Is there sound in the 30 ms on the kept side of a cut at t?"""
    ks = range(-3, 1) if before else range(0, 4)
    return any(not quiet(t + k * STEP) for k in ks)


def snap_end(t: float, quiet, limit: float) -> float:
    """Whisper often ends a word early ("$7" stops 0.3 s before George does): if
    the cut lands on sound, move it on to the first quiet moment, never past the
    next word in the transcript; failing that, back into the dip just before."""
    if not _on_sound(t, quiet, before=True):
        return t
    x = t
    while x < min(t + SNAP, limit):
        x += STEP
        if quiet(x):
            return min(x + 0.02, limit)
    x = t
    while x > t - NUDGE:
        x -= STEP
        if quiet(x):
            return x
    return t


def snap_start(t: float, quiet, limit: float) -> float:
    """Same for the start of a range: back to the last quiet moment before the
    word, never before the previous word; failing that, forward to the dip."""
    if not _on_sound(t, quiet, before=False):
        return t
    x = t
    while x > max(t - SNAP, limit):
        x -= STEP
        if quiet(x):
            return max(x - 0.02, limit)
    x = t
    while x < t + NUDGE:
        x += STEP
        if quiet(x):
            return x
    return t


class TimeMap:
    """Maps between output time (the edited video) and source time."""

    def __init__(self, segments: list[Segment]):
        self.segments = segments
        self.offsets = []
        acc = 0.0
        for s in segments:
            self.offsets.append(acc)
            acc += s.length
        self.duration = acc

    def to_source(self, t_out: float) -> float:
        i = max(0, bisect.bisect_right(self.offsets, t_out) - 1)
        s = self.segments[i]
        return min(s.start + (t_out - self.offsets[i]), s.end)

    def to_output(self, t_src: float) -> float:
        """Source time -> output time. Times inside a cut map to the cut point."""
        starts = [s.start for s in self.segments]
        i = bisect.bisect_right(starts, t_src) - 1
        if i < 0:
            return 0.0
        s = self.segments[i]
        if t_src <= s.end:
            return self.offsets[i] + (t_src - s.start)
        return self.offsets[i] + s.length   # in a cut: snap to the join

    def remap_words(self, words: list[Word]) -> list[Word]:
        out = []
        for w in words:
            if not w.kept:
                continue
            a, b = self.to_output(w.start), self.to_output(w.end)
            out.append(replace(w, start=a, end=max(b, a + 0.01)))
        return out
