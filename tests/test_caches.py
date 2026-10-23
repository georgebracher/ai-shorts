"""Work-dir caches: only a complete file that matches what made it is reused (audit codex-006,
claude-011, k3-006). Synthetic wavs and stubbed whisper / ffmpeg frame grabs only."""
import json
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

from ai_shorts import audio, face, pickups
from ai_shorts import transcribe as transcribe_mod
from ai_shorts.audio import SR, load_wav
from ai_shorts.config import Config
from ai_shorts.spec import parse_spec_text
from ai_shorts.transcribe import transcribe
from ai_shorts.trim import Segment


def write_wav(path: Path, seconds: float = 1.0) -> Path:
    t = np.arange(int(SR * seconds)) / SR
    pcm = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())
    return path


def cut_short(src: Path, dst: Path) -> Path:
    """The first half of a wav: its header still promises the whole length."""
    data = src.read_bytes()
    dst.write_bytes(data[:len(data) // 2])
    return dst


# ---------- audio.wav (codex-006) ----------

def test_interrupted_extraction_leaves_nothing_to_trust(tmp_path, monkeypatch):
    full = write_wav(tmp_path / "full.wav")
    work = tmp_path / "work"
    work.mkdir()

    def killed(cmd, **kw):           # ffmpeg stopped half way through writing its output
        cut_short(full, Path(cmd[-1]))
        raise KeyboardInterrupt
    monkeypatch.setattr(audio, "run", killed)
    with pytest.raises(KeyboardInterrupt):
        audio.extract_wav(tmp_path / "take.mp4", work / "audio.wav")
    assert list(work.iterdir()) == []    # no audio.wav, and no partial file either


def test_cut_short_wav_in_the_work_dir_is_extracted_again(tmp_path, monkeypatch):
    take = write_wav(tmp_path / "take.wav", 1.0)
    work = tmp_path / "work"
    work.mkdir()
    cut_short(take, work / "audio.wav")              # left by a run killed before the fix
    heard = []
    monkeypatch.setattr(pickups, "transcribe", lambda wav, *a: heard.append(len(load_wav(wav))) or [])
    spec = parse_spec_text("---\nslug: x\ntitle: X\n---\nHello.\n")
    pickups.heard(take, work, Config(), spec)
    assert heard == [SR]                             # whisper heard the whole second


# ---------- transcript.json ----------

@pytest.fixture
def whisper(tmp_path, monkeypatch):
    """Stub mlx_whisper: writes a one-word transcript naming the language it was asked for, and
    raises after writing when that language is in `fail`."""
    monkeypatch.setattr(transcribe_mod, "MLX_WHISPER", sys.executable)   # the Mac's branch
    calls, fail = [], set()

    def fake_run(cmd, **kw):
        lang = cmd[cmd.index("--language") + 1]
        calls.append(lang)
        name = cmd[cmd.index("--output-name") + 1]
        out = (Path(cmd[cmd.index("--output-dir") + 1]) / name).with_suffix(".json")   # as mlx_whisper names it
        out.write_text(json.dumps({"segments": [{"words": [{"word": lang, "start": 0.0, "end": 0.5}]}]}))
        if lang in fail:
            raise KeyboardInterrupt
    monkeypatch.setattr(transcribe_mod, "run", fake_run)
    return calls, fail


def test_interrupted_transcription_is_not_trusted(tmp_path, whisper):
    calls, fail = whisper
    wav = write_wav(tmp_path / "audio.wav")
    assert [w.text for w in transcribe(wav, tmp_path, "m", "en")] == ["en"]
    fail.add("fr")
    with pytest.raises(KeyboardInterrupt):           # stopped after the transcript, before its key
        transcribe(wav, tmp_path, "m", "fr")
    assert [w.text for w in transcribe(wav, tmp_path, "m", "en")] == ["en"]
    assert calls == ["en", "fr", "en"]


def test_transcription_never_rewrites_the_shared_transcript_in_place(tmp_path, whisper):
    # codex-007: another render of the take may be reading transcript.json meanwhile
    calls, fail = whisper
    wav = write_wav(tmp_path / "audio.wav")
    transcribe(wav, tmp_path, "m", "en")
    fail.add("fr")
    with pytest.raises(KeyboardInterrupt):
        transcribe(wav, tmp_path, "m", "fr")
    assert json.loads((tmp_path / "transcript.json").read_text())["segments"][0]["words"][0]["word"] == "en"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["audio.wav", "transcript.json"]   # no temp left


def test_clean_speech_temporary_files_are_its_own(tmp_path, monkeypatch):
    # codex-007: two renders of one take cleaning its sound at once wrote the same source-48k.wav
    df = write_wav(tmp_path / "python")              # any existing file stands in for DeepFilterNet's python
    work = tmp_path / "work"
    work.mkdir()
    shared = {work / "source-48k.wav", work / "clean-48k.partial.wav"}
    written = []

    def fake_run(cmd, **kw):
        out = Path(cmd[-1])
        assert out not in shared
        written.append(out)
        out.write_bytes(b"wav")
        if cmd[0] == str(df):
            raise RuntimeError("DeepFilterNet failed")
    monkeypatch.setattr(audio, "run", fake_run)
    with pytest.raises(RuntimeError):
        audio.clean_speech(tmp_path / "take.mp4", work, str(df))
    assert len(written) == 2 and list(work.iterdir()) == []   # and nothing left behind


# ---------- faces.json ----------

@pytest.fixture
def frames(monkeypatch):
    """Stub frame grabs (counted) and a detector that always finds the same face."""
    grabs = []
    monkeypatch.setattr(face, "grab_gray", lambda v, t, *a: grabs.append(t) or np.zeros((960, 540), np.uint8))
    monkeypatch.setattr(face, "detect", lambda gray: (270.0, 380.0, 180.0))
    return grabs


def test_face_cache_cut_off_mid_write_is_detected_again(tmp_path, frames):
    (tmp_path / "faces.json").write_text('{"times": [0.5, 1.5], "detec')
    det = face.detect_face(Path("take.mp4"), [Segment(0.0, 3.0)], tmp_path)
    assert det["hits"] == 3 and len(frames) == 3
    assert json.loads((tmp_path / "faces.json").read_text())["hits"] == 3


# ---------- what the caches are keyed on (claude-011, k3-006) ----------

def test_transcript_cache_is_keyed_on_language(tmp_path, whisper):
    # k3-006: fixed in a0dcf4a (the key carries the language); pinned here
    calls, _ = whisper
    wav = write_wav(tmp_path / "audio.wav")
    for lang in ("en", "en", "fr"):
        assert [w.text for w in transcribe(wav, tmp_path, "m", lang)] == [lang]
    assert calls == ["en", "fr"]


def test_face_cache_applies_a_new_calibration(tmp_path, frames, monkeypatch):
    # claude-011: the cache keeps raw Haar boxes since 6e74fda, so FACE_H / FACE_W apply on reuse; pinned here
    segs = [Segment(0.0, 3.0)]
    before = face.detect_face(Path("take.mp4"), segs, tmp_path)["face"]
    monkeypatch.setattr(face, "FACE_H", face.FACE_H * 1.25)
    after = face.detect_face(Path("take.mp4"), segs, tmp_path)["face"]
    assert len(frames) == 3                                  # the second run came from the cache
    assert (after[3] - after[1]) == pytest.approx((before[3] - before[1]) * 1.25, abs=1e-3)


@pytest.mark.parametrize("setting, value", [("SAMPLE_W", 720), ("MIN_NEIGHBORS", 4), ("SCALE_FACTOR", 1.05),
                                            ("MIN_SIDE", 0.08)])
def test_face_cache_is_keyed_on_the_detector_settings(tmp_path, frames, monkeypatch, setting, value):
    segs = [Segment(0.0, 3.0)]
    face.detect_face(Path("take.mp4"), segs, tmp_path)
    face.detect_face(Path("take.mp4"), segs, tmp_path)
    assert len(frames) == 3
    monkeypatch.setattr(face, setting, value, raising=False)   # the raw boxes would differ: detect again
    face.detect_face(Path("take.mp4"), segs, tmp_path)
    assert len(frames) == 6
