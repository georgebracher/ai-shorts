"""Synthesise a fake raw recording: test-pattern video + macOS `say` reading the
script, with a flubbed take of one sentence, a long pause, dead air at both ends
and phone-style location/creation metadata that the render must strip.

    .venv/bin/python tests/make_clip.py scripts/001-aeo-baseline.md /tmp/raw-test.mov
"""
import subprocess
import sys
from pathlib import Path

from ai_shorts.config import FFMPEG
from ai_shorts.spec import load_spec

FLUB_LINE = "Rightmove got cited in a hundred and four of them."
FLUB = "Rightmove got cited in a hundred, [[slnc 500]] "
PAUSE_AFTER = "In fairness, it's a day old."


def say_text(body: str) -> str:
    text = " ".join(body.split())
    assert FLUB_LINE in text and PAUSE_AFTER in text, "script changed; update make_clip"
    text = text.replace(FLUB_LINE, FLUB + FLUB_LINE)
    text = text.replace(PAUSE_AFTER, PAUSE_AFTER + " [[slnc 2200]]")
    return f"[[slnc 1500]] {text} [[slnc 1500]]"


def make_clip(script: Path, dst: Path, voice: str = "Daniel") -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    aiff = dst.with_suffix(".aiff")
    txt = dst.with_suffix(".txt")
    txt.write_text(say_text(load_spec(script).body))
    subprocess.run(["say", "-v", voice, "-f", str(txt), "-o", str(aiff)], check=True, timeout=300)
    subprocess.run([
        FFMPEG, "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30",
        "-i", str(aiff), "-shortest",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-metadata", "location=+51.4779-000.0015/",
        "-metadata", "creation_time=2026-10-18T09:30:00Z",
        "-metadata", "com.apple.quicktime.location.ISO6709=+51.4779-000.0015+046.000/",
        "-metadata", "com.apple.quicktime.make=Apple",
        "-movflags", "use_metadata_tags",
        str(dst)], check=True, timeout=300)
    return dst


if __name__ == "__main__":
    print(make_clip(Path(sys.argv[1]), Path(sys.argv[2])))
