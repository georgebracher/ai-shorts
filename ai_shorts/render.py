"""Stage 5: cut, frame, overlay and encode in one ffmpeg run.

Video: source -> 30 fps -> keep the EDL frames -> scale so George's face fits
between the title strip and the captions (blurred copy fills whatever the source
does not cover) -> video box is 0..seam on 1080x1920 ->
overlay the Pillow frames piped in as raw RGBA.
Audio: the same EDL ranges (8 ms fades at each cut), gain + limiter + linear loudnorm.
Every metadata tag from the source is dropped (phones store GPS in them).
"""
import json
import os
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from .config import FFMPEG, GRADES, Config
from .layout import VideoFit
from .media import SourceInfo, leftover_tags, run
from .overlay import Overlay
from .trim import Segment

TONEMAP = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
           "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,")


FEATHER = 60      # px over which George's picture blends into the extended fill
FILL_BLUR = 24    # gaussian sigma of the extended fill


def covers_window(cfg: Config, fit: VideoFit) -> bool:
    return fit.crop_w >= cfg.width and fit.crop_h >= fit.box_h and fit.place_x == 0 and fit.place_y == 0


def write_fill_mask(cfg: Config, fit: VideoFit, path: Path) -> Path:
    """Alpha mask for George's picture inside the window: opaque in the middle,
    fading to clear over FEATHER px at every edge that meets the extended fill."""
    W, H = cfg.width, fit.box_h
    x0, y0 = fit.place_x, fit.place_y
    x1, y1 = x0 + fit.crop_w, y0 + fit.crop_h
    xs, ys = np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32)

    def ramp(v, a, b, lim):
        lo = np.ones_like(v) if a <= 0 else np.clip((v - a) / FEATHER, 0, 1)
        hi = np.ones_like(v) if b >= lim else np.clip((b - 1 - v) / FEATHER, 0, 1)
        return lo * hi

    mask = np.outer(ramp(ys, y0, y1, H), ramp(xs, x0, x1, W))
    Image.fromarray((mask * 255).astype(np.uint8), "L").save(path)
    return path


def video_chain(cfg: Config, segs: list[Segment], src: SourceInfo, fit: VideoFit) -> str:
    """Filter graph for the picture. Inputs: 0 source, 1 overlay frames, and 2 the
    fill mask when George's picture does not cover the whole window."""
    eps = 0.25 / cfg.fps
    keep = "+".join(f"gte(t\\,{s.start - eps:.4f})*lt(t\\,{s.end - eps:.4f})" for s in segs)
    W = cfg.width
    head = (f"[0:v]fps={cfg.fps},select='{keep}',setpts=N/{cfg.fps}/TB,"
            + (TONEMAP if src.hdr else ""))
    fg = (f"scale={fit.scaled_w}:{fit.scaled_h}:flags=lanczos,"
          f"crop={fit.crop_w}:{fit.crop_h}:{fit.crop_x}:{fit.crop_y}")
    if GRADES[cfg.grade]:
        fg += "," + GRADES[cfg.grade]
    if covers_window(cfg, fit):
        picture = head + fg + ",format=gbrp[win];"
    else:
        # Portrait sources framed wide are narrower than the window: extend the
        # picture's own edges outward (the wall continues), blur only that
        # extension, and blend the seam through a feathered mask. No zoomed ghost.
        r = W - fit.place_x - fit.crop_w
        b = fit.box_h - fit.place_y - fit.crop_h
        picture = (head + fg + ",format=gbrp,"
                   f"pad={W}:{fit.box_h}:{fit.place_x}:{fit.place_y},"
                   f"fillborders=left={fit.place_x}:right={r}:top={fit.place_y}:bottom={b}:mode=smear,"
                   "split=2[ext][ext2];"
                   f"[ext2]gblur=sigma={FILL_BLUR}[soft];"
                   "[2:v]format=gray[mask];"
                   "[ext]format=gbrap[exta];[exta][mask]alphamerge[sharp];"
                   "[soft][sharp]overlay=0:0:shortest=1,format=gbrp[win];")
    return (picture
            + f"[win]pad={W}:{cfg.height}:0:{fit.box_top}:color=black[base];"
            f"[1:v]format=rgba[ov];"
            f"[base][ov]overlay=0:0:format=gbrp:shortest=1,"
            f"scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
            f"setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv[vout]")


def audio_chain(segs: list[Segment], tail: str, label: str = "0:a") -> str:
    fade = 0.008
    parts = [f"[{label}]asplit={len(segs)}" + "".join(f"[s{i}]" for i in range(len(segs)))]
    for i, s in enumerate(segs):
        parts.append(f"[s{i}]atrim=start={s.start:.4f}:end={s.end:.4f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d={fade},afade=t=out:st={max(0, s.length - fade):.4f}:d={fade}[c{i}]")
    parts.append("".join(f"[c{i}]" for i in range(len(segs)))
                 + f"concat=n={len(segs)}:v=0:a=1,{tail}[aout]")
    return ";".join(parts)


def measure(src: Path, segs: list[Segment], chain: str, cfg: Config) -> dict:
    ln = f"loudnorm=I={cfg.loudness_lufs}:TP={cfg.true_peak}:LRA=11:print_format=json"
    tail = f"{chain},{ln}" if chain else ln
    proc = run([FFMPEG, "-hide_banner", "-nostats", "-i", str(src), "-filter_complex",
                audio_chain(segs, tail), "-map", "[aout]", "-f", "null", "-"])
    return json.loads(re.findall(r"\{[^{}]*\}", proc.stderr)[-1])


def loudness_chain(src: Path, segs: list[Segment], cfg: Config) -> str:
    """Speech peaks sit far above its average, so loudnorm alone cannot reach
    -14 LUFS without clipping and quietly drops to dynamic mode. Instead: gain
    to target, limit the peaks, measure that, then a linear loudnorm trim."""
    eq = cfg.voice_eq if cfg.clean_audio else ""
    raw = measure(src, segs, eq, cfg)
    gain = cfg.loudness_lufs - float(raw["input_i"])
    limit = 10 ** ((cfg.true_peak - 0.5) / 20)
    for _ in range(3):   # limiting costs some loudness: top the gain up and re-measure
        pre = (f"{eq}," if eq else "") + \
            f"volume={gain:.2f}dB,alimiter=limit={limit:.3f}:attack=5:release=50:level=disabled"
        m = measure(src, segs, pre, cfg)
        err = cfg.loudness_lufs - float(m["input_i"])
        if abs(err) < 0.3:
            break
        gain += err
    return (f"{pre},loudnorm=I={cfg.loudness_lufs}:TP={cfg.true_peak}:LRA=11"
            f":measured_I={m['input_i']}:measured_TP={m['input_tp']}"
            f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
            f":offset={m['target_offset']}:linear=true,aresample=48000")


def render(src: Path, src_info: SourceInfo, segs: list[Segment], overlay: Overlay,
           duration: float, out: Path, cfg: Config, log: Path, fit: VideoFit,
           audio: Path | None = None) -> None:
    """`audio`: a cleaned copy of the take's sound on the same timeline, used instead of src's."""
    ln = loudness_chain(audio or src, segs, cfg)
    masked = not covers_window(cfg, fit)
    label = f"{3 if masked else 2}:a" if audio else "0:a"
    graph = video_chain(cfg, segs, src_info, fit) + ";" + audio_chain(segs, ln, label)
    # this render's own temporary names: another render of the take may be running beside it
    tmp = out.with_name(f"{out.stem}.{os.getpid()}.partial.mp4")
    mask = log.parent / f"{out.stem} fill-mask.png"
    cmd = [FFMPEG, "-y", "-hide_banner", "-nostats",
           "-i", str(src),
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{cfg.width}x{cfg.height}",
           "-framerate", str(cfg.fps), "-i", "pipe:0",
           *([] if covers_window(cfg, fit) else
             ["-loop", "1", "-framerate", str(cfg.fps), "-i", str(write_fill_mask(cfg, fit, mask))]),
           *(["-i", str(audio)] if audio else []),
           "-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-preset", cfg.x264_preset, "-crf", str(cfg.crf),
           "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(cfg.fps),
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-color_range", "tv",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
           "-map_metadata", "-1", "-map_chapters", "-1",
           "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
           "-metadata:s:v:0", "encoder=", "-metadata:s:a:0", "encoder=",
           "-movflags", "+faststart", "-shortest", str(tmp)]
    n_frames = round(duration * cfg.fps)
    try:
        with open(log, "w") as logf:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=logf, stdout=subprocess.DEVNULL)
            try:
                try:
                    for i in range(n_frames):
                        proc.stdin.write(overlay.frame_bytes(i / cfg.fps))
                except BrokenPipeError:
                    pass
                finally:
                    try:
                        proc.stdin.close()
                    except BrokenPipeError:
                        pass
                code = proc.wait(timeout=1800)
            except BaseException:       # stopped part way: ffmpeg first, so its file can go (Windows locks it)
                proc.kill()
                proc.wait()
                raise
        if code != 0:
            raise RuntimeError(f"ffmpeg render failed ({code}); see {log}:\n{log.read_text()[-2000:]}")
        tags = leftover_tags(tmp)
        if tags:
            raise RuntimeError(f"metadata survived in the render, not publishing it: {tags}")
        if out.exists() and out.stat().st_size:     # only the empty reservation may be replaced
            raise FileExistsError(f"refusing to overwrite {out}")
        os.replace(tmp, out)
    finally:
        # a failed render leaves nothing beside the real ones; after a failed metadata check this
        # is the very file still carrying the tags (audit claude-013)
        tmp.unlink(missing_ok=True)
