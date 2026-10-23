"""CLI: python -m ai_shorts render --video RAW --script scripts/<slug>.md [--out PATH]"""
import argparse
import sys
from pathlib import Path

from .config import FRAMINGS, GRADES, PALETTES, Config
from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="ai_shorts")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render", help="raw talking-head recording -> finished 1080x1920 short")
    r.add_argument("--video", required=True, type=Path, action="append",
                   help="raw recording; repeat it for pickups, in filming order (the last take of a line wins)")
    r.add_argument("--script", required=True, type=Path, help="scripts/<slug>.md")
    r.add_argument("--out", type=Path, help='default: ~/Downloads/"<slug> v<N> <framing> - AI Shorts.mp4"')
    r.add_argument("--debug-safe", action="store_true",
                   help="tint the zones TikTok/Reels cover and outline the face box")
    r.add_argument("--framing", choices=sorted(FRAMINGS),
                   help=f"how much of you the window shows (default {Config().framing})")
    r.add_argument("--grade", choices=list(GRADES),
                   help="colour grade for a flat-lit shoot (default none)")
    r.add_argument("--palette", choices=list(PALETTES), help=f"template colours (default {Config().palette})")
    r.add_argument("--preview-at", type=float, action="append",
                   help="output seconds to draw as stills instead of rendering (repeatable)")
    return ap


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["tower"]:          # render on the tower from the Mac (ai_shorts/remote.py)
        from .remote import main as tower
        return tower(argv[1:])
    args = build_parser().parse_args(argv)
    run_pipeline(args.video, args.script, args.out, debug_safe=args.debug_safe,
                 framing=args.framing, grade=args.grade, palette=args.palette, preview_at=args.preview_at)
    return 0


if __name__ == "__main__":
    sys.exit(main())
