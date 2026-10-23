"""End to end: fake raw clip -> CLI render -> check the file like a viewer would.

Slow (whisper + full render, ~30 s). Uses the real CLI as George would run it. Needs macOS
`say` for the fake clip and a whisper backend (see the README); skipped without them.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ai_shorts.config import DEFAULT, FFMPEG, MLX_WHISPER
from ai_shorts.media import ffprobe_json, leftover_tags, probe
from make_clip import make_clip

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "001-aeo-baseline.md"
WHISPER = Path(MLX_WHISPER).exists() or shutil.which(MLX_WHISPER) or importlib.util.find_spec("whisper")
pytestmark = pytest.mark.skipif(not (shutil.which("say") and WHISPER),
                                reason="needs macOS say and mlx_whisper or openai-whisper")

# `python -m ai_shorts` with one change: the work dir (caches, transcript, report.json) lands in
# the test's temp folder, not the repo's out/work. pipeline.PROJECT_ROOT is where work_dir() looks.
CLI = ("import sys; from pathlib import Path; import ai_shorts.pipeline as p; "
       "p.PROJECT_ROOT = Path(sys.argv.pop(1)); from ai_shorts.__main__ import main; sys.exit(main())")


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("smoke")
    raw = make_clip(SCRIPT, tmp / "raw.mov")
    out = tmp / "out.mp4"
    proc = subprocess.run([sys.executable, "-c", CLI, str(tmp), "render", "--video", str(raw),
                           "--script", str(SCRIPT), "--out", str(out)],
                          cwd=ROOT, capture_output=True, text=True, timeout=900)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    work = Path(next(line.split("work dir ")[1] for line in proc.stdout.splitlines() if "work dir " in line))
    assert work.is_relative_to(tmp)
    report = json.loads((work / "report.json").read_text())
    return raw, out, report


def frame_at(video, t):
    data = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
                           "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True, check=True, timeout=60).stdout
    return np.frombuffer(data, np.uint8).reshape(DEFAULT.height, DEFAULT.width, 3)


def test_raw_clip_really_has_location(rendered):
    raw, _, _ = rendered
    tags = ffprobe_json(raw)["format"]["tags"]
    assert any("location" in k for k in tags) and "creation_time" in tags


def test_output_format(rendered):
    raw, out, _ = rendered
    info = ffprobe_json(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920)
    assert v["r_frame_rate"] == "30/1" and v["avg_frame_rate"] == "30/1"
    assert v["codec_name"] == "h264" and v["pix_fmt"] == "yuv420p"
    assert v.get("color_transfer") == "bt709" and v.get("color_primaries") == "bt709"
    a = [s for s in info["streams"] if s["codec_type"] == "audio"]
    assert len(a) == 1 and a[0]["codec_name"] == "aac"
    assert probe(out).duration < probe(raw).duration - 3   # silences, pause and flub cut


def test_no_metadata_survives(rendered):
    _, out, _ = rendered
    assert leftover_tags(out) == {}
    info = ffprobe_json(out)
    tags = json.dumps([info["format"].get("tags", {})] + [s.get("tags", {}) for s in info["streams"]])
    for needle in ("location", "creation_time", "iso6709", "apple", "make", "model"):
        assert needle not in tags.lower()
    raw_bytes = out.read_bytes()   # nothing hiding in atoms ffprobe does not show
    for needle in (b"51.4779", b"ISO6709", b"\xa9xyz", b"com.apple"):
        assert needle not in raw_bytes


def test_flubbed_take_dropped(rendered):
    _, _, report = rendered
    assert report["restarts"] >= 1
    kept = report["kept_text"].lower().replace(",", "").replace(".", "")
    assert kept.count("cited in") == 1  # whisper hears the synthetic "got" as "god" at times; "cited in" is stable
    assert len(report["dropped_words"]) >= 4


def test_loudness_near_target(rendered):
    _, out, _ = rendered
    proc = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", str(out), "-af",
                           "ebur128", "-f", "null", "-"], capture_output=True, text=True, timeout=120)
    integrated = float(proc.stderr.rsplit("I:", 1)[1].split("LUFS")[0])
    assert abs(integrated - DEFAULT.loudness_lufs) < 0.7


def ink(img, y0, y1, x0, x1):
    """Fraction of a box that is drawn on: off-white text, the dimmed tint and the highlight all
    have green over 150, every palette's background, accent and cards stay under it (teal-navy's
    accent is 121, red's tint 162 counts as ink). 21 Oct 2026: the old "> 90" was written for the
    red panel and read the teal background as drawn on."""
    band = img[y0:y1, x0:x1].astype(int)
    return (band[..., 1] > 150).mean()


def test_steps_appear_in_order(rendered):
    _, out, report = rendered
    times = report["step_times"]
    assert None not in times and times == sorted(times) and len(set(times)) == 4
    rows, (bx0, bx1) = report["layout"]["step_rows"], report["layout"]["step_badge_x"]
    assert len(rows) == 4
    badge = lambda img, k: ink(img, rows[k][0], rows[k][1], bx0, bx1) > 0.05
    assert all(badge(frame_at(out, report["output_duration"] - 0.2), k) for k in range(4))
    for k, t in enumerate(times):
        before, after = frame_at(out, max(0, t - 0.15)), frame_at(out, t + 0.4)
        assert not badge(before, k), f"step {k + 1} visible before trigger"
        assert badge(after, k), f"step {k + 1} missing after trigger"
        if k + 1 < len(rows):
            assert not badge(after, k + 1), f"step {k + 2} early"


def test_hook_beats_fill_then_clear(rendered):
    _, out, report = rendered
    chips, *counters = report["beat_times"]
    assert chips and len(chips) == 4 and chips == sorted(chips)
    assert all(c and c[0] > chips[-1] for c in counters)
    assert counters[0][0] < counters[1][0] < report["beats_clear"]
    _, y = report["layout"]["beat_parts"][0]           # first chip row; a lone chip sits centred
    box = lambda img: ink(img, y + 20, y + 70, 480, 600)
    assert box(frame_at(out, max(0, chips[0] - 0.15))) < 0.05
    assert box(frame_at(out, chips[0] + 0.4)) > 0.5
    assert box(frame_at(out, report["beats_clear"] + 0.5)) < 0.05


def test_contact_sheet_written(rendered):
    _, out, report = rendered
    sheet = Image.open(report["contact_sheet"])
    assert sheet.size[0] > 1000 and sheet.size[1] > 1000


def test_no_face_falls_back_to_config_box(rendered):
    _, _, report = rendered                        # the test pattern has no face in it
    assert report["face"]["source"] == "config" and report["face"]["hits"] == 0
