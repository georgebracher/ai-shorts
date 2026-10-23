"""Second audit (23 Oct 2026): caches keyed on everything that made them, and a render that never
changes what it was handed."""
from pathlib import Path

import numpy as np

from ai_shorts import audio, pickups, pipeline, selfcheck
from ai_shorts.config import Config
from ai_shorts.media import SourceInfo


def test_a_reused_output_name_gets_a_fresh_self_check(tmp_path, monkeypatch):
    """claude-001: the old render's audio and transcript under the same name must not be reused."""
    heard_in = []
    monkeypatch.setattr(selfcheck, "cached_wav", lambda video, wav: wav)
    monkeypatch.setattr(selfcheck, "load_wav", lambda wav: np.zeros(10, np.float32))
    monkeypatch.setattr(selfcheck, "transcribe", lambda wav, d, *a: heard_in.append(d) or [])
    monkeypatch.setattr(selfcheck, "compare", lambda *a: [])
    out = tmp_path / "001 v3 medium - AI Shorts.mp4"
    out.write_bytes(b"first render")
    selfcheck.check_render(out, [], tmp_path, Config())
    out.write_bytes(b"second render, same name")
    selfcheck.check_render(out, [], tmp_path, Config())
    assert heard_in[0] != heard_in[1]


def test_clean_speech_is_keyed_on_the_cleaner(tmp_path, monkeypatch):
    """k3-007: another DeepFilterNet venv (or changed code) cleans again instead of reusing."""
    made = []

    def fake_run(cmd, timeout=1800, **kw):
        Path(cmd[-1]).write_bytes(b"wav")
        made.append(cmd[0])

    monkeypatch.setattr(audio, "run", fake_run)
    a, b = tmp_path / "py-a", tmp_path / "py-b"
    a.write_text(""), b.write_text("")
    first = audio.clean_speech(tmp_path / "take.mp4", tmp_path, str(a))
    assert audio.clean_speech(tmp_path / "take.mp4", tmp_path, str(a)) == first      # cached
    assert audio.clean_speech(tmp_path / "take.mp4", tmp_path, str(b)) != first      # new cleaner


def test_a_render_leaves_the_callers_config_alone(tmp_path, monkeypatch):
    """k3-010: palette, framing and grade apply to this render only."""
    script = Path(__file__).resolve().parent.parent / "scripts" / "001-aeo-baseline.md"
    monkeypatch.setattr(pipeline, "_run", lambda *a, **k: {})
    cfg = Config()
    before = (cfg.palette, cfg.bg_stops, cfg.red, cfg.framing, cfg.grade)
    pipeline.run_pipeline(tmp_path / "take.mp4", script, cfg=cfg, palette="red-black", framing="wide",
                          grade="strong", preview_at=[1.0])
    assert (cfg.palette, cfg.bg_stops, cfg.red, cfg.framing, cfg.grade) == before


def test_a_pickup_at_the_start_adds_no_empty_main_piece(tmp_path, monkeypatch):
    """codex-011: insertion at 0 s (or two at one time) must not hand concat a zero-length input."""
    cmds = []
    info = SourceInfo(30.0, 1920, 1080, 59.94, True, False)
    monkeypatch.setattr(pickups, "probe", lambda v: info)
    monkeypatch.setattr(pickups, "heard", lambda *a: [])
    monkeypatch.setattr(pickups, "insertion_time", lambda *a: 0.0)
    monkeypatch.setattr(pickups, "file_key", lambda v: str(v))

    def fake_run(cmd, timeout=1800, **kw):
        cmds.append(cmd)
        Path(cmd[-1]).write_bytes(b"mp4")

    monkeypatch.setattr(pickups, "run", fake_run)
    main, pick = tmp_path / "main.MP4", tmp_path / "pick.MP4"
    spec = type("S", (), {"steps": [], "words": []})()
    pickups.place_pickups([main, pick], spec, Config(), lambda v: tmp_path, tmp_path / "placed")
    cmd = cmds[0]
    assert "-to" not in cmd                                   # no main piece before the pickup
    assert cmd.count("-i") == 2 and "concat=n=2" in " ".join(cmd)
