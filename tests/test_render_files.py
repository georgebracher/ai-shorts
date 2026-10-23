"""What render() leaves on disk, with the encoder stubbed: it never replaces a finished file
(audit codex-007) and a failed render leaves no partial file (audit claude-013)."""
import io
from pathlib import Path

import pytest

from ai_shorts import render as render_mod
from ai_shorts.config import Config
from ai_shorts.layout import fit_video
from ai_shorts.media import SourceInfo
from ai_shorts.trim import Segment

CFG = Config()
SRC = SourceInfo(2.0, 1728, 3072, 30.0, True, False)
FIT = fit_video(CFG, 1728, 3072, (0.361, 0.2717, 0.6418, 0.5199), "medium")   # needs the fill mask


class Frames:
    def __init__(self, interrupt_at: int | None = None):
        self.interrupt_at, self.n = interrupt_at, 0

    def frame_bytes(self, t: float) -> bytes:
        self.n += 1
        if self.n == self.interrupt_at:
            raise KeyboardInterrupt
        return b"\0" * 16


@pytest.fixture
def ffmpeg(monkeypatch):
    """Stand-in encoder: writes its output file at once and exits with `code`."""
    state = {"code": 0, "tags": {}, "procs": []}

    class Proc:
        def __init__(self, cmd, **kw):
            self.cmd, self.killed = cmd, False
            Path(cmd[-1]).write_bytes(b"new render")
            self.stdin = io.BytesIO()
            state["procs"].append(self)

        def wait(self, timeout=None):
            return state["code"]

        def kill(self):
            self.killed = True
    monkeypatch.setattr(render_mod.subprocess, "Popen", Proc)
    monkeypatch.setattr(render_mod, "loudness_chain", lambda *a: "anull")
    monkeypatch.setattr(render_mod, "leftover_tags", lambda path: state["tags"])
    return state


def go(tmp_path: Path, out: Path, frames=None):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    log = work / f"{out.stem} ffmpeg.log"
    render_mod.render(tmp_path / "take.mp4", SRC, [Segment(0.0, 1.0)], frames or Frames(), 0.2, out, CFG, log, FIT)
    return work


# ---------- codex-007 ----------

def test_render_fills_its_reserved_name(tmp_path, ffmpeg):
    out = tmp_path / "x v1 medium - AI Shorts.mp4"
    out.touch()                                   # the pipeline's empty reservation
    go(tmp_path, out)
    assert out.read_bytes() == b"new render"


def test_render_never_replaces_a_finished_file(tmp_path, ffmpeg):
    out = tmp_path / "x v1 medium - AI Shorts.mp4"
    out.write_bytes(b"finished")                  # another render got there first
    with pytest.raises(FileExistsError):
        go(tmp_path, out)
    assert out.read_bytes() == b"finished"


def test_render_work_files_are_named_after_the_render(tmp_path, ffmpeg):
    out = tmp_path / "x v1 medium - AI Shorts.mp4"
    work = go(tmp_path, out)
    assert not (work / "fill-mask.png").exists()  # shared by every render of the take
    assert [p.name for p in work.glob("*.png")] == ["x v1 medium - AI Shorts fill-mask.png"]


# ---------- claude-013 ----------

@pytest.mark.parametrize("code, tags", [(1, {}),                                       # encoder failed
                                        (0, {"format:location": "+51.4779-000.0015/"})])  # metadata gate
def test_a_failed_render_leaves_no_partial_file(tmp_path, ffmpeg, code, tags):
    ffmpeg.update(code=code, tags=tags)
    out = tmp_path / "x v1 medium - AI Shorts.mp4"
    out.touch()
    with pytest.raises(RuntimeError):
        go(tmp_path, out)
    assert not list(tmp_path.glob("*.partial.mp4"))   # the metadata case is the file still carrying tags
    assert out.read_bytes() == b""                    # the reservation is the pipeline's to give back


def test_an_interrupted_render_stops_ffmpeg_and_leaves_no_partial_file(tmp_path, ffmpeg):
    out = tmp_path / "x v1 medium - AI Shorts.mp4"
    with pytest.raises(KeyboardInterrupt):
        go(tmp_path, out, Frames(interrupt_at=3))
    assert ffmpeg["procs"][0].killed
    assert not list(tmp_path.glob("*.partial.mp4"))
