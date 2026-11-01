"""Stage 2b: re-listen where whisper glossed over a restart.

Long-form whisper sometimes swallows a false start: George said "Three, no...",
paused, then "Three, count who gets cited", and whisper wrote one sentence with
"who" stretched over the pause. The tell is a word that runs across a long
measured silence. For each such sentence, transcribe just that stretch of audio
again and splice the words back in; the take selector then sees the false start
as its own (dropped) take. If the second listen hears nothing, the original
words were hallucinated over silence and go.

A word far longer than speech is the same tell even with little silence in it:
DJI_0349 (21 Oct 2026) said "3. Count who gets sighted. 3. Count who gets sighted.
That's your baseline." and the first pass wrote one take, with "your" stretched 3.05 s
over the second. The cut kept that audio, so step three played twice.
"""
from collections.abc import Callable
import os
from pathlib import Path

from .audio import wav_complete
from .config import FFMPEG
from .media import run
from .takes import split_units
from .text import ends_sentence
from .transcribe import Word, load_words, transcribe

STRETCHED = 1.0     # a word at least this long...
GAP = 0.8           # ...with at least this much silence inside it is suspect
LONG = 1.6          # and any word this long is: DJI_0349's "your" ran 3.05 s over a whole
                    # unheard take with only 0.78 s of silence in it (median word 0.4 s)
BURST, UNSURE = 0.45, 0.5   # a word this short, then silence, then a word whisper is this unsure of
MARGIN = 0.3        # audio either side of the sentence when re-listening


def suspect_spans(words: list[Word], silences: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    """(first word, last stretched word, last word) indices for every sentence
    containing a word stretched over a pause. Words after the last stretched one
    are left as the first pass heard them (it had more context, so spelled them
    better)."""
    def stretched(w: Word) -> bool:
        inside = sum(max(0.0, min(w.end, s1) - max(w.start, s0)) for s0, s1 in silences)
        return w.end - w.start >= LONG or (w.end - w.start >= STRETCHED and inside >= GAP)

    units = split_units(words)
    unit_of = {i: k for k, u in enumerate(units) for i in u}
    spans = []
    for unit in units:
        hits = [i for i in unit if stretched(words[i])]
        if hits:
            spans.append((unit[0], hits[-1], unit[-1]))
    # A noise whisper named: DJI_0353 (21 Oct 2026) cleared his throat, whisper called it "Then",
    # put the real "Then I" on an unsure "I" after the silence, and the throat clear played at 8 s.
    # Heard again on its own, the stretch put "Then" on the voice.
    for i in range(1, len(words)):
        p, w = words[i - 1], words[i]
        quiet = sum(max(0.0, min(w.start, s1) - max(p.end, s0)) for s0, s1 in silences)
        # mid-sentence only: "...did. [pause] 1." is a step cue, not a noise
        if w.prob < UNSURE and p.end - p.start <= BURST and quiet >= 0.3 and not ends_sentence(p.text):
            spans.append((units[unit_of[i - 1]][0], i, units[unit_of[i]][-1]))
    # An unsure word with a real silence inside: 003's pickup said "One. One. Show Claude..." and
    # whisper wrote the second "one" into "Show" (0.36 s gap inside it), so both ones played.
    for i, w in enumerate(words):
        inside = sum(max(0.0, min(w.end, s1) - max(w.start, s0)) for s0, s1 in silences
                     if s0 > w.start + 0.02 and s1 < w.end - 0.02)
        if w.prob < UNSURE and inside >= 0.25:
            spans.append((units[unit_of[i]][0], i, units[unit_of[i]][-1]))
    merged: list[tuple[int, int, int]] = []
    for a, b, z in sorted(spans):
        if merged and a <= merged[-1][2]:
            pa, pb, pz = merged[-1]
            merged[-1] = (pa, max(pb, b), max(pz, z))
        else:
            merged.append((a, b, z))
    return merged


ISLAND_GAP = 0.6     # a silence this long inside a re-listened stretch splits it
ISLAND_PAD = 0.15


def islands(lo: float, hi: float, silences) -> list[tuple[float, float]]:
    """The stretch [lo, hi] cut at every silence longer than ISLAND_GAP, each piece padded a little.
    003 (21 Oct 2026): "It was a co- [throat clear, 1.5 s] coin flip." heard as one stretch came back
    as "coin" + a 2.5 s "flip.", one take, so the broken-off "co-" stayed in the cut. Heard island by
    island, the second piece is "coin flip" and the first "coin" is an abandoned take the edit drops."""
    cuts = [(max(lo, s0), min(hi, s1)) for s0, s1 in silences if min(hi, s1) - max(lo, s0) > ISLAND_GAP]
    out, t = [], lo
    for s0, s1 in sorted(cuts):
        if s0 > t:
            out.append((max(lo, t - ISLAND_PAD), min(hi, s0 + ISLAND_PAD)))
        t = s1
    if t < hi:
        out.append((max(lo, t - ISLAND_PAD), hi))
    return out or [(lo, hi)]


def splice(words: list[Word], silences, relisten: Callable[[float, float], list[Word]]) -> tuple[list[Word], int]:
    """Replace each suspect sentence with what a second listen hears.
    Returns (new words, number of sentences re-listened)."""
    spans = suspect_spans(words, silences)
    if not spans:
        return words, 0
    out, last = [], 0
    for a, b, z in spans:
        out += words[last:a]
        lo = max(words[a].start - MARGIN, words[a - 1].end if a else 0.0)
        end = words[z].end + MARGIN                # listen to the whole sentence...
        if z + 1 < len(words):
            end = min(end, words[z + 1].start)
        hi = words[b].end                          # ...but take words up to the stretched one
        heard = [w for i0, i1 in islands(lo, end, silences) for w in relisten(i0, i1)]
        took = [w for w in heard if lo <= (w.start + w.end) / 2 <= hi]
        out += took
        last = b + 1
        # first-pass words the second listen already covers go: 003 (21 Oct 2026) kept a
        # re-heard "flip." running to 42.65 s and the first pass's "flip." at 42.46 s, the
        # duplicate read as a retake and the cut took "coin flip" with it. Covered means a third of
        # the word: 004 (1 Nov 2026) lost "bot's" to a re-heard "each" that overlapped it by 0.07 s
        if took:
            while last < len(words) and took[-1].end - words[last].start > (words[last].end - words[last].start) / 3:
                last += 1
    out += words[last:]
    return out, len(spans)


def relistener(wav: Path, work: Path, model: str, language: str) -> Callable[[float, float], list[Word]]:
    """Transcribe a stretch of the work wav (cached per stretch) on the source timeline."""
    def relisten(start: float, end: float) -> list[Word]:
        tag = f"relisten-{start:08.2f}-{end:08.2f}"
        clip_dir = work / tag
        clip_dir.mkdir(exist_ok=True)
        clip = clip_dir / "clip.wav"
        if not wav_complete(clip):   # written whole then renamed, so a stopped run leaves nothing to trust
            tmp = clip_dir / f"clip.{os.getpid()}.wav"
            run([FFMPEG, "-y", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                 "-i", str(wav), str(tmp)])
            os.replace(tmp, clip)
        heard = transcribe(clip, clip_dir, model, language)
        return [Word(w.text, w.start + start, w.end + start) for w in heard]
    return relisten
