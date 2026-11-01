"""Raw talking-head file + script -> finished vertical video. Stages in order."""
import hashlib
import json
import re
import time
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

from .align import apply_alignment
from .audio import Envelope, cached_wav, clean_speech, load_wav, silence_intervals, tighten_words
from .config import FFMPEG, GRADES, PALETTES, PROJECT_ROOT, Config
from .contact import contact_sheet
from .face import detect_face
from .layout import fit_video, inside
from .media import file_key, probe, run
from .pickups import place_pickups
from .selfcheck import check_render
from .overlay import Overlay
from .refine import relistener, splice
from .render import render
from .spec import Spec, load_spec
from . import timeline
from .timeline import beat_times, chunk_captions, fill_missing, stat_times, step_times
from .captions import caption_words
from .text import normalize_word
from .transcribe import Word, drop_noise, transcribe
from .trim import TimeMap, build_segments


# Renders George is to watch land in ~/Downloads itself, newest first in his listing, named so the
# part that tells them apart comes first. Rejected ones move to AI Shorts/<slug>/old renders;
# accepted ones stay put. The per-video folder holds raw footage, old renders and contact sheets
# (George, 21 Oct 2026: a render inside a subfolder is a render he never sees).
REVIEW_DIR = Path.home() / "Downloads"
OUTPUT_ROOT = REVIEW_DIR / "AI Shorts"


DEBUG_LABEL = "safe-zones debug"


def render_name(slug: str, n: int, label: str = "") -> str:
    return f"{slug} v{n}{' ' + label if label else ''} - AI Shorts.mp4"


def next_version(slug: str, review: Path = REVIEW_DIR, archive: Path = OUTPUT_ROOT) -> int:
    """One above any render of this video in the review folder or anywhere under its archive
    folder, so numbers never repeat. Counts the old names too ("AI Shorts <slug> - v9 wide.mp4").
    A debug view carries the number of the render it shows and takes none of its own (audit
    claude-009: one made before any render was v1, so the first real render became v2)."""
    s = re.escape(slug)
    pats = [re.compile(rf"^{s} v(\d+)(?: [^/]+)? - AI Shorts\.mp4$"),
            re.compile(rf"^AI Shorts {s} - v(\d+)(?: [^/]+)?\.mp4$")]
    seen = [p for p in [*review.glob("*.mp4"), *(archive / slug).rglob("*.mp4")]
            if DEBUG_LABEL not in p.name]
    nums = [int(m.group(1)) for p in seen for pat in pats if (m := pat.match(p.name))]
    return max(nums, default=0) + 1


def reserve(path: Path) -> bool:
    """Create `path` empty unless something is there, so the name is this render's alone even with
    another render of the video running (audit codex-007). False if it was taken."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "x"):
            return True
    except FileExistsError:
        return False


def claim(path: Path) -> Path:
    """Reserve exactly this name, or refuse: a render is never overwritten."""
    if reserve(path):
        return path
    # a render killed outright (ssh dropped on the tower) cannot give its reservation back
    held = path.is_file() and path.stat().st_size == 0
    raise FileExistsError(f"refusing to overwrite {path}" + (
        " (empty: another render is writing it, or one was killed; delete it to retry)" if held else ""))


def release(path: Path) -> None:
    """Give back a reserved name the render never filled."""
    try:
        if path.stat().st_size == 0:
            path.unlink()
    except FileNotFoundError:
        pass


def output_path(slug: str, cfg: Config) -> Path:
    """The next free name for a render of this video, reserved."""
    n = next_version(slug, REVIEW_DIR, OUTPUT_ROOT)
    if cfg.debug_safe:   # a debug view is named after the latest render, not a new version
        return claim(OUTPUT_ROOT / slug / render_name(slug, max(1, n - 1), DEBUG_LABEL))
    label = cfg.framing + (f" {cfg.grade} grade" if cfg.grade != "none" else "")
    while not reserve(out := REVIEW_DIR / render_name(slug, n, label)):
        n += 1           # another render of this video took that number first
    return out


def relisten_drops(before: list[Word], after: list[Word]) -> list[Word]:
    """First-pass words the re-listen took out and did not hear again: a stretch heard as nothing
    was whisper writing over silence, and those words were dropped too (audit claude-012)."""
    kept, old = {id(w) for w in after}, {id(w) for w in before}
    again = Counter(tuple(normalize_word(w.text)) for w in after if id(w) not in old)
    gone = []
    for w in before:
        if id(w) in kept:
            continue
        k = tuple(normalize_word(w.text))
        if again[k]:
            again[k] -= 1                # heard again, maybe with better timing: not a drop
        else:
            gone.append(w)
    return gone


def work_dir(src: Path) -> Path:
    # Name, size and first megabyte, not the path: moving the raw file into a folder, or copying it
    # to the tower, keeps its cache.
    key = hashlib.sha1(file_key(src).encode()).hexdigest()[:10]
    d = PROJECT_ROOT / "out" / "work" / f"{src.stem}-{key}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def preview_frames(video: Path, fit, overlay, tmap, times: list[float], cfg: Config, work: Path,
                   stem: str) -> list[Path]:
    """Frames of the finished video at output times: George's graded, cropped picture where the
    render puts it, the template drawn over it (palette choices without a render)."""
    from PIL import Image
    paths = []
    for t in times:
        vf = (f"scale={fit.scaled_w}:{fit.scaled_h}:flags=lanczos,"
              f"crop={fit.crop_w}:{fit.crop_h}:{fit.crop_x}:{fit.crop_y}")
        if GRADES[cfg.grade]:
            vf += "," + GRADES[cfg.grade]
        raw = work / f"preview-{t:.2f}.png"
        run([FFMPEG, "-v", "error", "-y", "-ss", f"{tmap.to_source(t):.3f}", "-i", str(video),
             "-frames:v", "1", "-update", "1", "-vf", vf, str(raw)])
        canvas = Image.new("RGBA", (cfg.width, cfg.height), (0, 0, 0, 255))
        pic = Image.open(raw).convert("RGBA")
        # where the picture stops short of the window, stretch its edge the way the render's
        # fill does, so a still does not show black where the video never would
        win = Image.new("RGBA", (cfg.width, fit.box_h), (0, 0, 0, 255))
        win.paste(pic.crop((0, 0, pic.width, 1)).resize((pic.width, max(1, fit.place_y))), (fit.place_x, 0))
        win.paste(pic, (fit.place_x, fit.place_y))
        if fit.place_x:
            win.paste(win.crop((fit.place_x, 0, fit.place_x + 1, fit.box_h)).resize((fit.place_x, fit.box_h)), (0, 0))
        right = fit.place_x + pic.width
        if right < cfg.width:
            win.paste(win.crop((right - 1, 0, right, fit.box_h)).resize((cfg.width - right, fit.box_h)), (right, 0))
        canvas.paste(win, (0, fit.box_top))
        canvas.alpha_composite(overlay.draw(overlay.state(t)))
        out = work / f"{stem} {t:.1f}s.png"
        canvas.convert("RGB").save(out)
        paths.append(out)
    return paths


def log(msg: str) -> None:
    print(f"[ai-shorts] {msg}", flush=True)


def run_pipeline(video: Path, script: Path, out: Path | None = None,
                 cfg: Config | None = None, debug_safe: bool = False,
                 framing: str | None = None, grade: str | None = None, palette: str | None = None,
                 preview_at: list[float] | None = None) -> dict:
    # a copy: palette, framing and grade below must not leak into the caller's Config (a batch
    # reusing one would render the second video in the first one's colours; audit2 k3-010)
    cfg = replace(cfg) if cfg else Config()
    cfg.palette = palette or cfg.palette
    for k, v in PALETTES[cfg.palette].items():
        setattr(cfg, k, v)
    cfg.debug_safe = cfg.debug_safe or debug_safe
    if framing:
        cfg.framing = framing
    if grade:
        cfg.grade = grade
    t0 = time.time()
    videos = [Path(v).expanduser() for v in (video if isinstance(video, (list, tuple)) else [video])]
    script = Path(script).expanduser()
    spec = load_spec(script)
    sheets = None
    if preview_at:              # stills only: nothing goes out under a render's name
        out = None
    elif out is None:
        out = output_path(spec.slug, cfg)
        sheets = OUTPUT_ROOT / spec.slug / "contact sheets"
    else:
        out = claim(Path(out).expanduser())
    try:
        return _run(videos, spec, cfg, out, sheets, t0, preview_at)
    except BaseException:
        if out:
            release(out)        # a failed render gives its name back
        raise
    finally:
        timeline.LISTENERS.clear()


def _run(videos: list[Path], spec: Spec, cfg: Config, out: Path | None, sheets: Path | None, t0: float,
         preview_at: list[float] | None) -> dict:
    warnings: list[str] = []

    def warn(msg: str) -> None:      # the report keeps them too: a run that warns still ends "done"
        warnings.append(msg)
        log(f"WARNING: {msg}")

    timeline.LISTENERS[:] = [warnings.append]   # takes, timeline and overlay warn through timeline.warn

    video = videos[0]
    if len(videos) > 1:
        video = place_pickups(videos, spec, cfg, work_dir, PROJECT_ROOT / "out" / "placed")
        log(f"placed {len(videos) - 1} pickup(s) into the main take: {video.name}")
    src = probe(video)
    if not src.has_audio:
        raise ValueError(f"{video} has no audio track")
    work = work_dir(video)
    log(f"framing: {cfg.framing}")
    log(f"source {src.width}x{src.height} {src.fps:.2f}fps {src.duration:.1f}s"
        f"{' HDR' if src.hdr else ''}; work dir {work}")

    # 2. transcribe
    wav = cached_wav(video, work / "audio.wav")
    heard = transcribe(wav, work, cfg.whisper_model, cfg.language)
    words = drop_noise(heard, spec.words)
    log(f"transcribed {len(heard)} words ({len(heard) - len(words)} noise)")

    # 3. tighten to real speech, drop retakes, cut pauses
    samples = load_wav(wav)
    env = Envelope(samples)                      # one loudness pass for the silences and the cuts
    silences = silence_intervals(samples, env=env)
    tighten_words(words, silences)
    first_pass = words
    words, relistened = splice(words, silences, relistener(wav, work, cfg.whisper_model, cfg.language))
    gone = relisten_drops(first_pass, words)
    if relistened:
        words = drop_noise(words, spec.words)
        tighten_words(words, silences)
        log(f"re-listened to {relistened} sentence(s) where whisper ran a word over a pause")
    words, restarts = apply_alignment(words, spec.words, cfg.max_pause, {s.trigger for s in spec.steps})
    dropped = [w.text for w in sorted(gone + [w for w in words if not w.kept], key=lambda w: w.start)]
    segs = build_segments(words, src.duration, cfg.pad, cfg.max_pause, cfg.fps, silences,
                          env.quiet, env.loud)
    if not segs:
        raise RuntimeError("nothing left to keep: no speech matched")
    tmap = TimeMap(segs)
    out_words = tmap.remap_words(words)
    log(f"{restarts} restart(s), dropped {len(dropped)} words; "
        f"{len(segs)} segments, {src.duration:.1f}s -> {tmap.duration:.1f}s")

    # 4. timeline + overlay
    raw_steps = step_times(out_words, spec.steps, spec.words)
    steps_at = fill_missing(raw_steps)
    stats_at = stat_times(out_words, spec.stats)
    beats_at = beat_times(out_words, spec.beats)
    cap_words = caption_words(out_words, spec.words)   # script spelling, whisper timing
    chunks = chunk_captions(cap_words, cfg.caption_max_words, cfg.caption_max_chars)
    for s, t in zip(spec.steps, raw_steps):
        if t is None:
            warn(f"trigger '{s.trigger}' for step '{s.label}' never heard; shown on a timer")
    for b, t in zip(spec.beats, beats_at):
        if t is None:
            warn(f"beat '{b.trigger}' never heard; not shown")
    det = detect_face(video, segs, work)
    if det["face"]:
        log(f"face found on {det['hits']}/{det['samples']} sampled frames")
    else:
        warn(f"no reliable face ({det['hits']}/{det['samples']} frames); using config.face_box")
    fit = fit_video(cfg, src.width, src.height, tuple(det["face"]) if det["face"] else None)
    if not inside(fit.face, cfg.info_rect):
        warn(f"George's face box {[round(v) for v in fit.face]} is outside the safe "
             f"area {cfg.info_rect}; check config.face_box against this recording")
    overlay = Overlay(cfg, spec, steps_at, stats_at, chunks, beats_at, fit.face)
    unsafe = [name for name, box in overlay.boxes if not inside(box, cfg.info_rect)]
    if unsafe:
        warn(f"outside the safe area: {unsafe}")
    if any(t and t[0] >= overlay.beats_clear for t in beats_at):
        warn("a beat lands after the stats / first step and will not be seen")

    if preview_at:      # stills of the finished look, no render
        stem = f"{spec.slug} preview {cfg.palette}"
        return {"previews": preview_frames(video, fit, overlay, tmap, preview_at, cfg, work, stem)}

    # 5. render
    t_render = time.time()
    clean = clean_speech(video, work, cfg.df_python) if cfg.clean_audio else None
    if cfg.clean_audio and clean is None:
        warn("DeepFilterNet not installed here; the sound is not cleaned up")
    # the log (and the fill mask beside it) named after the render: renders of one take share a work dir
    render(video, src, segs, overlay, tmap.duration, out, cfg, work / f"{out.stem} ffmpeg.log", fit, clean)
    render_s = time.time() - t_render

    # 6. contact sheet
    sheet_dir = sheets or out.parent        # an explicit --out keeps its sheet beside it
    sheet_dir.mkdir(parents=True, exist_ok=True)
    sheet = contact_sheet(out, sheet_dir / (out.stem + " contact sheet.png"), cfg)

    # 7. hear the finished video: doubled words, cut-off words, stray takes
    problems = check_render(out, [w for c in chunks for w in c.words], work, cfg)

    report = {
        "output": str(out), "contact_sheet": str(sheet), "work_dir": str(work),
        "source_duration": src.duration, "output_duration": tmap.duration,
        "restarts": restarts, "dropped_words": dropped,
        "segments": [asdict(s) for s in segs],
        "step_times": raw_steps, "step_times_shown": steps_at, "stat_times": stats_at,
        "beat_times": beats_at, "beats_clear": overlay.beats_clear, "layout": overlay.layout(),
        "face_box": [round(v) for v in fit.face], "safe_rect": list(cfg.safe_rect), "info_rect": list(cfg.info_rect),
        "face": {"source": "detected" if det["face"] else "config", "samples": det["samples"],
                 "hits": det["hits"], "median_px": det["median_px"], "sample_size": det["sample_size"],
                 "face_src_frac": det["face"] or list(cfg.face_box),
                 "face_out_height": round(fit.face[3] - fit.face[1]),
                 "face_share_of_window": round((fit.face[3] - fit.face[1]) / fit.box_h, 3)},
        "framing": cfg.framing, "grade": cfg.grade, "crop": asdict(fit),
        "captions": [" ".join(w.text for w in c.words) for c in chunks],
        "kept_text": " ".join(w.text for w in out_words),
        "render_seconds": round(render_s, 1), "total_seconds": round(time.time() - t0, 1),
        "self_check": problems, "warnings": warnings,
    }
    text = json.dumps(report, indent=2)
    saved = work / "reports" / f"{out.stem}.json"     # one per render: renders of one take share a work dir
    saved.parent.mkdir(exist_ok=True)
    saved.write_text(text)
    (work / "report.json").write_text(text)          # the latest, where remote.py and the smoke test read it
    log(f"done in {report['total_seconds']}s (render {report['render_seconds']}s): {out}")
    log(f"contact sheet: {sheet}")
    log(f"report: {saved}")
    for p in problems:
        log(f"CHECK {p}")
    log("self-check: the finished audio matches the captions" if not problems else
        f"self-check: {len(problems)} thing(s) to listen to before posting")
    return report
