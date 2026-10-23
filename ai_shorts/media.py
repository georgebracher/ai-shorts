"""Thin ffmpeg / ffprobe helpers."""
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import FFMPEG, FFPROBE


def run(cmd: list[str], timeout: float = 1800, text: bool = True, **kw) -> subprocess.CompletedProcess:
    """`text=False` for raw frames on stdout; a failure still quotes the tool's stderr."""
    proc = subprocess.run(cmd, capture_output=True, text=text, timeout=timeout, **kw)
    if proc.returncode != 0:
        err = proc.stderr if text else proc.stderr.decode(errors="replace")
        raise RuntimeError(f"{Path(cmd[0]).name} failed ({proc.returncode}):\n{err[-3000:]}")
    return proc


def ffprobe_json(path: str | Path) -> dict:
    out = run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format",
               "-show_streams", "-show_chapters", str(path)], timeout=60).stdout
    return json.loads(out)


@dataclass
class SourceInfo:
    duration: float
    width: int          # after rotation
    height: int
    fps: float
    has_audio: bool
    hdr: bool


def probe(path: str | Path) -> SourceInfo:
    info = ffprobe_json(path)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if v is None:
        raise ValueError(f"{path} has no video stream")
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []):
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    if abs(rot) % 180 == 90:
        w, h = h, w
    num, den = (v.get("avg_frame_rate") or "0/1").split("/")
    fps = float(num) / float(den) if float(den) else 0.0
    return SourceInfo(
        duration=float(info["format"]["duration"]),
        width=w, height=h, fps=fps,
        has_audio=any(s["codec_type"] == "audio" for s in info["streams"]),
        hdr=v.get("color_transfer") in ("arib-std-b67", "smpte2084"),
    )


# Tags that are allowed to survive: container brand fields and per-stream
# language/handler names carry nothing about the device or place.
HARMLESS_TAGS = {"major_brand", "minor_version", "compatible_brands",
                 "language", "handler_name", "vendor_id"}


def leftover_tags(path: str | Path) -> dict:
    """Every metadata tag in the file that is not on the harmless list."""
    info = ffprobe_json(path)
    found = {}
    for k, v in (info["format"].get("tags") or {}).items():
        if k.lower() not in HARMLESS_TAGS:
            found[f"format:{k}"] = v
    for s in info["streams"]:
        for k, v in (s.get("tags") or {}).items():
            if k.lower() not in HARMLESS_TAGS:
                found[f"stream{s['index']}:{k}"] = v
    if info.get("chapters"):
        found["chapters"] = len(info["chapters"])
    return found


def file_key(path: Path) -> str:
    """Name, size and the first megabyte: the same on the Mac and the tower, so a take copied
    across keeps its caches (mtime does not survive the copy)."""
    import hashlib
    path = Path(path)
    with open(path, "rb") as f:
        head = hashlib.sha1(f.read(1 << 20)).hexdigest()[:12]
    return f"{path.name}|{path.stat().st_size}|{head}"
