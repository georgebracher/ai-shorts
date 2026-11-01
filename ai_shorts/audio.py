"""Audio helpers: extract a mono wav and find real silences.

Whisper's word starts drift 0.3-0.6 s early into silences, which would hide
pauses from the trimmer. An energy pass finds the actual quiet stretches and
pulls word edges back onto the speech.
"""
import hashlib
import os
import wave
from pathlib import Path

import numpy as np

from .config import FFMPEG
from .media import run

SR = 16000


def extract_wav(src: str | Path, dst: str | Path) -> Path:
    """Mono 16 kHz wav. Written under a temporary name and renamed only once it is whole, so a run
    killed mid-extraction never leaves a short audio.wav that later runs reuse (audit codex-006)."""
    dst = Path(dst)
    tmp = dst.with_name(f"{dst.stem}-{os.getpid()}.partial.wav")
    try:
        run([FFMPEG, "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(SR),
             "-c:a", "pcm_s16le", str(tmp)])
        if not wav_complete(tmp):
            raise RuntimeError(f"ffmpeg wrote an incomplete wav from {src}")
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)
    return dst


def wav_complete(path: str | Path) -> bool:
    """True when the wav's data chunk holds every byte its header promises. ffmpeg fills the sizes
    in last, so a file it never finished claims more than it has."""
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"RIFF" or f.read(8)[4:] != b"WAVE":
                return False
            while len(head := f.read(8)) == 8:
                size = int.from_bytes(head[4:], "little")
                if head[:4] == b"data":
                    return 0 < size <= os.fstat(f.fileno()).st_size - f.tell()
                f.seek(size + size % 2, 1)
    except OSError:
        pass
    return False


def cached_wav(src: str | Path, dst: str | Path) -> Path:
    """The work dir's wav, extracted again when it is missing or cut short."""
    return Path(dst) if wav_complete(dst) else extract_wav(src, dst)


def load_wav(path: str | Path) -> np.ndarray:
    with wave.open(str(path), "rb") as f:
        data = f.readframes(f.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0


def frame_db(samples: np.ndarray, hop: float = 0.01, win: float = 0.02) -> np.ndarray:
    h, w = int(SR * hop), int(SR * win)
    n = max(0, (len(samples) - w) // h + 1)
    if n == 0:
        return np.zeros(0)
    idx = np.arange(w)[None, :] + h * np.arange(n)[:, None]
    rms = np.sqrt(np.mean(samples[idx] ** 2, axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-5))


class Envelope:
    """Loudness every 10 ms and the quiet threshold, for placing cuts."""

    def __init__(self, samples: np.ndarray, hop: float = 0.01):
        self.hop, self.db = hop, frame_db(samples, hop)
        if len(self.db):
            floor, speech = np.percentile(self.db, 5), np.percentile(self.db, 95)
            self.thr = floor + 0.3 * (speech - floor) if speech - floor >= 15 else -np.inf
            self.voice = speech - 20       # a breath stays under this, a spoken "s" does not
        else:
            self.thr = self.voice = -np.inf

    def quiet(self, t: float) -> bool:
        i = int(round(t / self.hop))
        return i < 0 or i >= len(self.db) or self.db[i] < self.thr

    def loud(self, t: float) -> bool:
        i = int(round(t / self.hop))
        return 0 <= i < len(self.db) and self.db[i] >= self.voice


def silence_intervals(samples: np.ndarray, min_len: float = 0.12,
                      hop: float = 0.01, env: Envelope | None = None) -> list[tuple[float, float]]:
    """Quiet stretches, using a threshold set between noise floor and speech level. Pass the
    take's `env` to reuse its loudness pass instead of measuring the whole take again."""
    env = env or Envelope(samples, hop)
    hop = env.hop
    quiet = env.db < env.thr         # thr is -inf where there is no clear silence anywhere
    out, start = [], None
    for i, q in enumerate(np.append(quiet, False)):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * hop >= min_len:
                out.append((start * hop, i * hop))
            start = None
    return out


def tighten_words(words, silences, min_word: float = 0.04, tol: float = 0.06) -> None:
    """Move word edges that sit inside a silence onto the speech (in place). An edge up to
    `tol` outside a silence counts as inside: 003 (21 Oct 2026) had "Check" start 10 ms before
    a half-second silence, so the cut started early and kept a stray "three" before it."""
    for w in words:
        for s0, s1 in silences:
            if s0 - tol <= w.start < s1 and s1 < w.end - min_word:
                w.start = s1
            if s0 < w.end <= s1 + tol and s0 > w.start + min_word:
                w.end = s0


# DeepFilterNet (AI speech clean-up) in its own venv: 0.5.6 imports torchaudio.backend.common, which
# newer torchaudio dropped, and reads audio through torchaudio, so stand in for the one import and
# read/write with soundfile. Input: 48 kHz mono wav (the model's rate).
DEEPFILTER_CODE = (
    "import sys, types; c = types.ModuleType('torchaudio.backend.common'); "
    "c.AudioMetaData = type('AudioMetaData', (), {}); "
    "sys.modules['torchaudio.backend'] = types.ModuleType('torchaudio.backend'); "
    "sys.modules['torchaudio.backend.common'] = c; "
    "import soundfile as sf, torch; from df.enhance import enhance, init_df; "
    "m, s, _ = init_df(); a, sr = sf.read(sys.argv[1], dtype='float32'); "
    "assert sr == s.sr(), sr; out = enhance(m, s, torch.from_numpy(a)[None]); "
    "sf.write(sys.argv[2], out[0].cpu().numpy(), sr)")


def clean_speech(src: Path, work: Path, df_python: str) -> Path | None:
    """The whole take's audio through DeepFilterNet (cached), or None where it is not installed.
    21 Oct 2026: on headphones an echoey room sounded "loud and tinny"; of five options George took
    DeepFilterNet + EQ, which cut the echo tail by ~7.5 dB and the noise floor by ~16 dB."""
    if not df_python or not Path(df_python).exists():
        return None
    # keyed on what made it: another DeepFilterNet venv or a changed DEEPFILTER_CODE cleans again
    # (audit2 k3-007); the old unkeyed clean-48k.wav is simply not reused
    key = hashlib.sha1(f"{df_python}|{DEEPFILTER_CODE}".encode()).hexdigest()[:10]
    out = work / f"clean-48k-{key}.wav"
    if not out.exists():
        # this run's own temporary names: another render of the take may be cleaning it too
        raw = work / f"source-48k-{os.getpid()}.wav"
        tmp = work / f"clean-48k-{os.getpid()}.partial.wav"
        try:
            run([FFMPEG, "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "48000", str(raw)])
            run([df_python, "-c", DEEPFILTER_CODE, str(raw), str(tmp)], timeout=3600)
            tmp.replace(out)
        finally:
            raw.unlink(missing_ok=True)
            tmp.unlink(missing_ok=True)
    return out

