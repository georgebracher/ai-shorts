"""ffmpeg errors carry ffmpeg's own message, and the take's loudness is measured once (audit claude-016)."""
import numpy as np
import pytest

from ai_shorts import audio, face
from ai_shorts.audio import SR, Envelope, silence_intervals


def speech_with_pauses() -> np.ndarray:
    """1 s tone, 0.5 s near-silence, 1 s tone, 0.3 s near-silence, 0.5 s tone."""
    rng = np.random.default_rng(0)
    parts = []
    for loud, secs in [(True, 1.0), (False, 0.5), (True, 1.0), (False, 0.3), (True, 0.5)]:
        t = np.arange(int(SR * secs)) / SR
        parts.append(0.3 * np.sin(2 * np.pi * 220 * t) if loud else 0.0005 * rng.standard_normal(len(t)))
    return np.concatenate(parts).astype(np.float32)


def test_frame_grab_failure_says_what_ffmpeg_said(tmp_path):
    with pytest.raises(RuntimeError, match="No such file"):
        face.grab_gray(tmp_path / "missing.mp4", 0.5)


def test_silences_come_from_the_one_loudness_pass(monkeypatch):
    samples = speech_with_pauses()
    expected = silence_intervals(samples)
    assert [(round(a, 1), round(b, 1)) for a, b in expected] == [(1.0, 1.5), (2.5, 2.8)]
    passes = []
    real = audio.frame_db
    monkeypatch.setattr(audio, "frame_db", lambda *a, **k: passes.append(1) or real(*a, **k))
    env = Envelope(samples)
    assert silence_intervals(samples, env=env) == expected
    assert len(passes) == 1
