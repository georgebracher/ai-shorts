"""Stage 7: hear the finished video and say where it does not match the captions.

21 Oct 2026: 003 v6 played "one one" and "three three" and cut off "coin flip". Contact
sheets and transcribing single lines missed all three; George heard them. Now the whole
finished audio is transcribed and compared with the captions: a word said twice in a row
that the captions say once, caption words never heard (cut off), and heard words with no
caption (a stray take or noise) are warnings in the log and the report.
"""
import hashlib
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

from .audio import SR, cached_wav, load_wav
from .config import Config
from .media import file_key
from .text import tokens_with_owner
from .transcribe import Word, transcribe


def _tokens(words: list[Word]) -> list[tuple[str, float]]:
    return [(t, words[i].start) for t, i in tokens_with_owner([w.text for w in words])]


LOUD, UNWORDED = 0.3, 0.28     # share of speech loudness, and how long of it with no word on it
STRETCH, STRETCH_QUIET = 1.2, 0.5   # a word this long with this much silence inside it


def compare(captions: list[Word], heard: list[Word], samples=None) -> list[str]:
    """Differences worth a human ear, with output times. With the audio `samples`, speech-loud
    sound no heard word covers is flagged too: whisper heard 003 v6's doubled "three" as one word,
    the audio still had 0.34 s of it (harmless gaps on 001-003 measured 0.22 s at most)."""
    cap, got = _tokens(captions), _tokens(heard)
    problems = []
    cap_pairs = {(a[0], b[0]) for a, b in zip(cap, cap[1:]) if a[0] == b[0]}
    for a, b in zip(got, got[1:]):
        if a[0] == b[0] and (a[0], b[0]) not in cap_pairs:
            problems.append(f"{b[1]:5.1f}s said twice: '{a[0]} {b[0]}'")
    ops = SequenceMatcher(None, [t for t, _ in cap], [t for t, _ in got], autojunk=False).get_opcodes()
    for op, i1, i2, j1, j2 in ops:
        if op == "delete" and i2 - i1 >= 2:
            problems.append(f"{cap[i1][1]:5.1f}s captioned but not heard: '{' '.join(t for t, _ in cap[i1:i2])}'")
        elif op == "insert" and j2 - j1 >= 2:
            problems.append(f"{got[j1][1]:5.1f}s heard but not captioned: '{' '.join(t for t, _ in got[j1:j2])}'")
        elif op == "replace" and (j2 - j1) - (i2 - i1) >= 2:
            problems.append(f"{got[j1][1]:5.1f}s heard more than captioned: "
                            f"'{' '.join(t for t, _ in got[j1:j2])}' for '{' '.join(t for t, _ in cap[i1:i2])}'")
        elif op == "replace" and i2 - i1 >= 2 and not {t for t, _ in cap[i1:i2]} & {t for t, _ in got[j1:j2]}:
            problems.append(f"{got[j1][1]:5.1f}s captioned '{' '.join(t for t, _ in cap[i1:i2])}' "
                            f"but heard '{' '.join(t for t, _ in got[j1:j2])}' (cut off?)")
    if samples is not None and heard:
        x = samples.astype(float)
        x = x / 32768 if np.abs(x).max() > 1.5 else x
        speech = np.concatenate([x[int(w.start * SR):int(w.end * SR)] for w in heard])
        ref, hop = float(np.sqrt((speech ** 2).mean())), int(0.02 * SR)
        for a, b in zip(heard, heard[1:]):
            gap = x[int(a.end * SR):int(b.start * SR)]
            loud = sum(1 for i in range(0, len(gap) - hop, hop)
                       if np.sqrt((gap[i:i + hop] ** 2).mean()) > LOUD * ref) * 0.02
            if loud >= UNWORDED:
                problems.append(f"{a.end:5.1f}s {loud:.2f}s of speech-loud sound with no words "
                                f"between '{a.text}' and '{b.text}' (a stray take?)")
        # a word stretched over a pause: whisper's tell for a broken-off line and its retake
        # (003 v10, 21 Oct 2026: "It was a... [cough, pause] it was a coin flip" came back as one
        # 2 s "coin" with a second of silence inside it, and every other check passed)
        from .audio import silence_intervals
        sil = silence_intervals(x)
        for w in heard:
            inside = sum(max(0.0, min(w.end, s1) - max(w.start, s0)) for s0, s1 in sil)
            if w.end - w.start >= STRETCH and inside >= STRETCH_QUIET:
                problems.append(f"{w.start:5.1f}s '{w.text}' runs {w.end - w.start:.1f}s over "
                                f"{inside:.1f}s of silence (a broken-off line and a retake?)")
    seen, out = set(), []
    for p in problems:                      # a doubled word also shows as a one-token insert: once is enough
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def check_render(video: Path, captions: list[Word], work: Path, cfg: Config) -> list[str]:
    # keyed on the finished file itself: a reused output name (--out, a freed version number, a tower
    # retry) must not reuse the old render's audio and transcript (audit2 claude-001, 23 Oct 2026)
    d = work / f"self-check-{video.stem}-{hashlib.sha1(file_key(video).encode()).hexdigest()[:10]}"
    d.mkdir(parents=True, exist_ok=True)
    wav = d / "audio.wav"
    cached_wav(video, wav)       # a whole one is reused; a cut-short leftover is extracted again
    return compare(captions, transcribe(wav, d, cfg.whisper_model, cfg.language), load_wav(wav))
