"""Stage 0: pickups. A line re-filmed after the main take goes back where it belongs.

The take selector only walks forward through both the recording and the script, so a
pickup of step one filmed after step four could never replace the old take: that would
mean dropping everything in between (DJI_0353 + DJI_0354, 21 Oct 2026: the pickup that
fixed "forty" to "forty-eight" was ignored). Instead each pickup is placed into the main
take, in the pause right after the old take of the last line it covers. The selector then
sees an ordinary retake and keeps the later, pickup one. The placed source is one encode
(hardware HEVC, 10-bit), cached by its inputs.
"""
import hashlib
import os
from pathlib import Path
import sys

from .audio import cached_wav
from .config import FFMPEG, Config
from .media import file_key, probe, run
from .spec import Spec
from .takes import select_takes
from .transcribe import Word, drop_noise, transcribe


# the Mac's hardware HEVC encoder, or the tower's NVIDIA one
HEVC = ["-c:v", "hevc_nvenc", "-preset", "p5"] if sys.platform == "win32" else ["-c:v", "hevc_videotoolbox"]
EMPTY = 0.05   # seconds: a main piece shorter than this is left out of the join


def insertion_time(main: list[Word], pickup: list[Word], script_words: list[str],
                   triggers: set[str]) -> float:
    """Source time in the main take to place the pickup at: mid-pause after the main take's
    chosen take of the last script sentence the pickup covers."""
    # the last sentence it really covers: a one-word tail into the next line does not count
    # (DJI_0354's "Graded" matched step two's "grade" and the pickup landed a line late)
    covered = []
    for u in select_takes(pickup, script_words, triggers, quiet=True).units:
        if u.chosen:
            top = max(u.chosen.cover.values())
            covered += [s for s, c in u.chosen.cover.items() if c >= 0.5 * top]
    if not covered:
        raise ValueError("the pickup matches no script line")
    last = max(covered)
    sel = select_takes(main, script_words, triggers, quiet=True)   # the render's own pass warns
    ends = [max(u.words) for u in sel.units if u.chosen and u.chosen.sent_hi <= last]
    if not ends:
        return 0.0
    i = max(ends)
    if i + 1 < len(main):
        return round((main[i].end + main[i + 1].start) / 2, 3)
    return round(main[i].end + 0.3, 3)


def heard(video: Path, work: Path, cfg: Config, spec: Spec) -> list[Word]:
    wav = cached_wav(video, work / "audio.wav")
    return drop_noise(transcribe(wav, work, cfg.whisper_model, cfg.language), spec.words)


def place_pickups(videos: list[Path], spec: Spec, cfg: Config, work_of, folder: Path) -> Path:
    """One source: the main take with every pickup placed after the line it replaces."""
    main, pickups = videos[0], videos[1:]
    infos = [probe(v) for v in videos]
    for v, info in zip(pickups, infos[1:]):
        if (info.width, info.height, round(info.fps, 2), info.hdr) != \
                (infos[0].width, infos[0].height, round(infos[0].fps, 2), infos[0].hdr):
            raise ValueError(f"{v.name} ({info.width}x{info.height} {info.fps:.2f} fps) does not match "
                             f"{main.name}: film pickups with the same camera settings")
    triggers = {s.trigger for s in spec.steps}
    main_words = heard(main, work_of(main), cfg, spec)
    at = sorted((insertion_time(main_words, heard(p, work_of(p), cfg, spec), spec.words, triggers), k)
                for k, p in enumerate(pickups))
    key = hashlib.sha1("|".join([file_key(v) for v in videos] + [f"{t:.3f}" for t, _ in at]
                                + [HEVC[1]]).encode()).hexdigest()[:10]
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{main.stem}+{len(pickups)}-{key}.mp4"
    if out.exists():
        return out
    # pieces in output order: main up to the first placement, a pickup, main on, ...
    # a pickup at 0 s, two at one time, or one at the very end leaves no main piece between them, and
    # an empty piece is not given to concat (audit2 codex-011)
    inputs, prev = [], 0.0
    for t, k in at:
        if t - prev > EMPTY:
            inputs += ["-ss", f"{prev:.3f}", "-to", f"{t:.3f}", "-i", str(main)]
        inputs += ["-i", str(pickups[k])]
        prev = t
    if infos[0].duration - prev > EMPTY:
        inputs += ["-ss", f"{prev:.3f}", "-i", str(main)]
    n = inputs.count("-i")
    graph = "".join(f"[{i}:v:0][{i}:a:0]" for i in range(n)) + f"concat=n={n}:v=1:a=1[v][a]"
    tmp = out.with_name(f"{out.stem}.{os.getpid()}.partial.mp4")   # two renders may place the same pickups
    try:
        run([FFMPEG, "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
             *HEVC, "-b:v", "80M", "-pix_fmt", "p010le", "-tag:v", "hvc1",
             "-c:a", "aac", "-b:a", "320k", str(tmp)], timeout=3600)
        tmp.replace(out)
    finally:
        tmp.unlink(missing_ok=True)
    return out
