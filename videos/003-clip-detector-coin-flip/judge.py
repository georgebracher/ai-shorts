"""Grade stream clips the way your editor would, from his past grades.

    pip install anthropic
    export ANTHROPIC_API_KEY=...
    python judge.py score graded.jsonl new.jsonl                         # a keep probability for each new clip
    python judge.py test graded.jsonl --examples 48 --out test.jsonl     # how well it predicts held-out grades (AUC)

graded.jsonl: one clip per line, {"game": "...", "transcript": "...", "kept": true|false, "stream": "..."}.
"stream" is optional; with it, no stream gives more than 4 of the examples.
new.jsonl: the same without "kept".

The model only sees the game name and the speech transcript, never the video. The examples are
the editor's own decisions, half kept and half rejected, spread across streams; on real grades
48 examples were enough (AUC 0.76 on 287 held-out clips, 0.763 on a rerun). Rebuilding the
examples from his latest grades each day is all the learning there is.

A reply counts as a score only if it is a whole number from 0 to 100 and nothing else; anything
else is a failed clip, reported, never guessed at. `test` makes one call per held-out clip (it says
how many before it starts; --max-calls lowers that) and saves each score to --out as it lands.
Either command exits 1 if any clip failed.
"""
import argparse
from collections import Counter
import json
import random
import re
import sys
from pathlib import Path

MODEL = "claude-opus-5"   # the model the 0.76 was measured with
TRANSCRIPT_CHARS = 600
PER_STREAM = 4            # most examples from any one stream, when clips say which stream they came from
ERRORS_IN_A_ROW = 3       # API errors in a row that stop a `test` run (a bad key, an outage)
PROMPT = Path(__file__).with_name("prompt.txt").read_text(encoding="utf-8")
INTRO, ASK = PROMPT.split("{examples}")


def fmt(clip: dict) -> str:
    return f"Game: {clip.get('game')}\nTranscript: {(clip.get('transcript') or '')[:TRANSCRIPT_CHARS]}"


def system_prompt(examples: list[dict]) -> str:
    body = "\n\n".join(f"<example verdict=\"{'KEPT' if c['kept'] else 'REJECTED'}\">\n{fmt(c)}\n</example>"
                       for c in examples)
    return INTRO + body + ASK


def pick(graded: list[dict], n: int, seed: int = 0) -> list[dict]:
    """n examples, half kept and half rejected, at most PER_STREAM from any one stream (clips without
    a "stream" field are not limited), shuffled so verdicts interleave. Fewer if the limit runs out."""
    rng = random.Random(seed)
    pools = [[c for c in graded if c["kept"]], [c for c in graded if not c["kept"]]]
    for pool in pools:
        rng.shuffle(pool)
    want, chosen, per_stream = [n // 2, n // 2], [], Counter()
    left = [iter(pool) for pool in pools]
    while any(want):
        moved = False
        for side in (0, 1):   # alternate kept and rejected, so neither side uses up the streams first
            if not want[side]:
                continue
            for c in left[side]:
                stream = c.get("stream")
                if stream is None or per_stream[stream] < PER_STREAM:
                    chosen.append(c)
                    if stream is not None:
                        per_stream[stream] += 1
                    want[side] -= 1
                    moved = True
                    break
        if not moved:
            break
    rng.shuffle(chosen)
    return chosen


def reply(client, system: str, clip: dict) -> str:
    m = client.messages.create(
        model=MODEL, max_tokens=2000, extra_body={"output_config": {"effort": "low"}},
        # the examples are the same for every clip, so they are cached after the first call
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": fmt(clip)}])
    return "".join(b.text for b in m.content if b.type == "text")


def parse(text: str) -> int | None:
    """The prompt asks for only the integer: that, or None. "48 examples suggest 70" is not a 48."""
    m = re.fullmatch(r"\s*(\d{1,3})\s*", text or "")
    return int(m[1]) if m and int(m[1]) <= 100 else None


def score(client, system: str, clip: dict) -> int | None:
    return parse(reply(client, system, clip))


def auc(pairs: list[tuple[float, bool]]) -> float:
    """Chance that a kept clip scores above a rejected one (ties count half). 0.5 is a coin flip."""
    kept = [s for s, k in pairs if k]
    binned = [s for s, k in pairs if not k]
    if not kept or not binned:
        raise ValueError(f"AUC needs both kept and rejected clips; got {len(kept)} kept, {len(binned)} rejected")
    wins = sum((a > b) + 0.5 * (a == b) for a in kept for b in binned)
    return wins / (len(kept) * len(binned))


def load(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run_test(client, system: str, held: list[dict], out: Path) -> tuple[list[tuple[int, bool]], Counter]:
    """Score each held-out clip, appending it to `out` as it lands; stops after ERRORS_IN_A_ROW API errors."""
    pairs, tally, in_a_row = [], Counter(), 0
    with open(out, "x", encoding="utf-8") as f:
        for clip in held:
            tally["attempted"] += 1
            row = dict(clip)
            try:
                text = reply(client, system, clip)
                in_a_row = 0
            except Exception as e:  # noqa: BLE001
                text, in_a_row = None, in_a_row + 1
                row["error"] = f"{e.__class__.__name__}: {e}"
            p = None if text is None else parse(text)
            row["keep_probability"] = p
            if p is None:
                tally["failed"] += 1
                row["reply"] = text
                row.setdefault("error", "the reply is not a whole number from 0 to 100")
            else:
                pairs.append((p, clip["kept"]))
            f.write(json.dumps(row) + "\n")
            f.flush()
            if in_a_row >= ERRORS_IN_A_ROW:
                print(f"stopping: {in_a_row} API errors in a row, the last: {row['error']}", file=sys.stderr)
                break
    return pairs, tally


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("graded", type=Path)
    s.add_argument("new", type=Path)
    s.add_argument("--examples", type=int, default=48)
    t = sub.add_parser("test")
    t.add_argument("graded", type=Path)
    t.add_argument("--examples", type=int, default=48)
    t.add_argument("--out", type=Path, required=True, help="new file: one line per scored clip, written as it lands")
    t.add_argument("--max-calls", type=int, help="most API calls to make (default: one per held-out clip)")
    a = ap.parse_args(argv)
    if a.cmd == "test" and a.out.exists():
        ap.error(f"{a.out} already exists; pick a new --out")
    try:
        import anthropic
    except ImportError:
        ap.error("judge.py needs the anthropic package: pip install anthropic")
    client = anthropic.Anthropic()
    graded = load(a.graded)
    examples = pick(graded, a.examples)
    kept = sum(c["kept"] for c in examples)
    print(f"{len(examples)} examples: {kept} kept, {len(examples) - kept} rejected"
          + (f" (asked for {a.examples}: not enough clips, or the {PER_STREAM}-per-stream limit)"
             if len(examples) < a.examples // 2 * 2 else ""), file=sys.stderr)
    system = system_prompt(examples)
    if a.cmd == "score":
        failed = 0
        for clip in load(a.new):
            text = reply(client, system, clip)
            p = parse(text)
            failed += p is None
            print(json.dumps({**clip, "keep_probability": p, **({"reply": text} if p is None else {})}))
        if failed:
            print(f"{failed} clips failed: the reply was not a whole number from 0 to 100", file=sys.stderr)
        return 1 if failed else 0
    used = {id(c) for c in examples}
    held = [c for c in graded if id(c) not in used]
    calls = len(held) if a.max_calls is None else max(0, min(a.max_calls, len(held)))
    if calls < len(held):   # a random subset, kept in file order, so a short run is still a fair sample
        keep = set(random.Random(1).sample(range(len(held)), calls))
        held = [c for i, c in enumerate(held) if i in keep]
    print(f"test: {calls} calls to {MODEL}, one per held-out clip ({len(graded) - len(examples)} held out), "
          f"saved to {a.out} as they land", file=sys.stderr)
    pairs, tally = run_test(client, system, held, a.out)
    print(f"{tally['attempted']} attempted, {len(pairs)} scored, {tally['failed']} failed, "
          f"{calls - tally['attempted']} not attempted")
    try:
        print(f"AUC {auc(pairs):.3f} on the {len(pairs)} scored held-out clips ({len(examples)} examples)")
    except ValueError as e:
        print(f"no AUC: {e}")
        return 1
    return 1 if tally["failed"] or tally["attempted"] < calls else 0


if __name__ == "__main__":
    sys.exit(main())
