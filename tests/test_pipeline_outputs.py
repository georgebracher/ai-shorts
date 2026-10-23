"""Whole pipeline with the slow stages stubbed (whisper, face detection, encode, contact sheet,
self-check): output names, reservations and reports. The take is a 4 s synthetic wav, and every
folder is under tmp_path."""
import json
import wave
from pathlib import Path

import numpy as np
import pytest

from ai_shorts import pipeline
from ai_shorts.audio import SR
from ai_shorts.config import Config
from ai_shorts.media import SourceInfo
from ai_shorts.transcribe import Word

SCRIPT = "---\nslug: 009-test\ntitle: Test video\n---\nHello there friend. Second line here.\n"
HEARD = [("Hello", 0.2, 0.5), ("there", 0.55, 0.85), ("friend.", 0.9, 1.3),
         ("Second", 1.8, 2.1), ("line", 2.15, 2.45), ("here.", 2.5, 2.9)]


def write_wav(path: Path, seconds: float = 4.0) -> Path:
    t = np.arange(int(SR * seconds)) / SR
    pcm = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())
    return path


class Run:
    """Stubs for the slow stages. `heard` is what whisper writes; `during` runs while the take is
    being transcribed (another render starting meanwhile); `fail` makes the encode raise."""

    def __init__(self, tmp_path: Path, monkeypatch):
        self.review = tmp_path / "Downloads"
        self.archive = self.review / "AI Shorts"
        self.review.mkdir()
        self.heard, self.relisten, self.during, self.fail = list(HEARD), (lambda a, b: []), None, None
        self.logs = []
        real_next = pipeline.next_version
        monkeypatch.setattr(pipeline, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(pipeline, "REVIEW_DIR", self.review)
        monkeypatch.setattr(pipeline, "OUTPUT_ROOT", self.archive)
        monkeypatch.setattr(pipeline, "next_version", lambda slug, *a: real_next(slug, self.review, self.archive))
        monkeypatch.setattr(pipeline, "probe", lambda v: SourceInfo(4.0, 1080, 1920, 30.0, True, False))
        monkeypatch.setattr(pipeline, "transcribe", self._transcribe)
        monkeypatch.setattr(pipeline, "relistener", lambda *a: self.relisten)
        monkeypatch.setattr(pipeline, "detect_face", lambda v, segs, work: {
            "face": None, "hits": 0, "samples": 0, "median_px": None, "sample_size": None})
        monkeypatch.setattr(pipeline, "render", self._render)
        monkeypatch.setattr(pipeline, "contact_sheet", lambda out, dst, cfg: dst)
        monkeypatch.setattr(pipeline, "check_render", lambda *a: [])
        self.script = tmp_path / "009-test.md"
        self.script.write_text(SCRIPT)
        self.take = write_wav(tmp_path / "take.wav")

    def _transcribe(self, wav, work, model, language):
        if self.during:
            during, self.during = self.during, None
            during()
        return [Word(t, a, b) for t, a, b in self.heard]

    def _render(self, video, src, segs, overlay, duration, out, cfg, log, fit, clean):
        self.logs.append(log)
        if self.fail:
            raise self.fail
        out.write_text(f"render {len(self.logs)}")

    def __call__(self, **kw) -> dict:
        return pipeline.run_pipeline(self.take, self.script, cfg=Config(df_python=""), **kw)


@pytest.fixture
def run(tmp_path, monkeypatch):
    return Run(tmp_path, monkeypatch)


def test_harness_renders(run):
    report = run()
    assert Path(report["output"]).name == "009-test v1 medium - AI Shorts.mp4"
    assert Path(report["output"]).read_text() == "render 1"
    assert report["kept_text"] == "Hello there friend. Second line here."


# ---------- reports (claude-012) ----------

STRETCHED = [("Hello", 0.2, 0.5), ("there", 0.55, 0.85), ("friend.", 0.9, 2.6),   # 1.7 s: re-listened
             ("Second", 2.8, 3.1), ("line", 3.15, 3.45), ("here.", 3.5, 3.9)]


def test_each_render_keeps_its_own_report(run):
    first, second = run(), run(framing="wide")
    work = Path(first["work_dir"])
    for r in (first, second):
        assert json.loads((work / "reports" / f"{Path(r['output']).stem}.json").read_text())["output"] == r["output"]
    # report.json stays the latest, where remote.py and the smoke test read it
    assert json.loads((work / "report.json").read_text())["output"] == second["output"]


def test_report_keeps_the_warnings(run):
    warnings = run()["warnings"]
    assert any("DeepFilterNet" in w for w in warnings)
    assert any("no reliable face" in w for w in warnings)


def test_words_the_relisten_took_out_count_as_dropped(run):
    run.heard = STRETCHED                        # and the second listen hears nothing there
    report = run()
    assert report["kept_text"] == "Second line here."
    assert report["dropped_words"] == ["Hello", "there", "friend."]


def test_words_the_relisten_heard_again_are_not_dropped(run):
    run.heard = STRETCHED
    again = [Word("Hello", 0.2, 0.5), Word("there", 0.55, 0.85), Word("friend.", 0.9, 1.3)]
    run.relisten = lambda a, b: [w for w in again if a <= w.start < b]
    report = run()
    assert report["kept_text"] == "Hello there friend. Second line here."
    assert report["dropped_words"] == []


# ---------- names (claude-009) ----------

def test_a_debug_view_first_leaves_v1_for_the_first_render(run):
    debug = Path(run(debug_safe=True)["output"])
    assert debug == run.archive / "009-test" / "009-test v1 safe-zones debug - AI Shorts.mp4"
    assert Path(run()["output"]).name == "009-test v1 medium - AI Shorts.mp4"


# ---------- two renders at once (codex-007) ----------

def test_a_render_started_meanwhile_takes_the_next_number(run):
    other = {}
    run.during = lambda: other.update(run())     # a second render of the take starts mid-way
    first = run()
    assert Path(first["output"]).name == "009-test v1 medium - AI Shorts.mp4"
    assert Path(other["output"]).name == "009-test v2 medium - AI Shorts.mp4"
    assert Path(other["output"]).read_text() == "render 1"   # each keeps its own file
    assert Path(first["output"]).read_text() == "render 2"


def test_renders_of_one_take_keep_separate_work_files(run):
    run()
    run()
    assert len(set(run.logs)) == 2               # the ffmpeg log (and the fill mask beside it)


def test_a_failed_render_gives_its_name_back(run):
    run.fail = RuntimeError("encoder failed")
    with pytest.raises(RuntimeError):
        run()
    assert not list(run.review.glob("*.mp4"))    # no empty reservation left in Downloads
    run.fail = None
    assert Path(run()["output"]).name == "009-test v1 medium - AI Shorts.mp4"


def test_an_explicit_out_is_never_overwritten(run, tmp_path):
    out = tmp_path / "mine.mp4"
    out.write_text("finished")
    with pytest.raises(FileExistsError):
        run(out=out)
    assert out.read_text() == "finished"
    out.write_text("")                           # held by a render that is running, or was killed
    with pytest.raises(FileExistsError, match="delete it to retry"):
        run(out=out)
