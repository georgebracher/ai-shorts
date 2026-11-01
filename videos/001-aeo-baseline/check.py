"""Ask four AI answer engines the same questions and count which websites they cite.

    export OPENROUTER_API_KEY=...
    python check.py ask questions.txt --site example.co.uk --out results/my-run --cap 10
    python check.py ask questions.txt --site example.co.uk --out results/my-run --cap 10 --resume
    python check.py count results/my-run --site example.co.uk

One file, standard library only (Python 3.11+). Every engine is reached through OpenRouter with web
search on, one new chat per question. Questions go one after another, each to all four engines at
once, so 50 questions land within about ten minutes. Each answer is appended to answers.jsonl the
moment it lands, so a stopped run keeps what it paid for and --resume asks only what is missing;
answers.csv is written beside it. `count` re-scores a saved run without paying or going online.

--cap is a ceiling on what one `ask` spends. Every call holds back RESERVE dollars before it starts
and starts only if the money spent plus everything held still fits under the cap. A finished call
is charged what OpenRouter reports; a failed one stays charged at RESERVE, since it may have been
billed. The run can pass the cap only if a single answer costs more than RESERVE, and then only by
that excess on the calls already running (four at most). `ask` exits 1 if any call failed or the
cap stopped it.

"Cited" means the answer itself references the page. ChatGPT's, Claude's and Gemini's annotations
each back a piece of the answer, so they all count. Perplexity hands back every search result it
saw (about 28 an answer) and marks the ones it used with [n] in the text, so only those count.
Counting every Perplexity result is how a first reading put Rightmove in 122 of these 200 answers
instead of 104 (fixed 20 Oct 2026).
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

ENGINES = {  # the panel used for the 18 Oct 2026 baseline, about $0.14 a question across all four
    "chatgpt": "openai/gpt-6-sol",
    "claude": "anthropic/claude-sonnet-5.5",
    "gemini": "google/gemini-3.5-flash-lite",
    "perplexity": "perplexity/sonar-pro",
}
RESERVE = 0.50    # held against the cap for each call until OpenRouter reports its cost (baseline's dearest: $0.12)
API = "https://openrouter.ai/api/v1/chat/completions"


def ask_one(model: str, question: str, key: str) -> dict:
    body = {"model": model, "messages": [{"role": "user", "content": question}], "usage": {"include": True}}
    if not model.startswith("perplexity/"):   # Sonar searches by itself and rejects the plugin
        body["plugins"] = [{"id": "web", "engine": "native"}]
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST",
                                 headers={"authorization": f"Bearer {key}", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read())


class _NoFollow(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def resolve(url: str) -> str:
    """Gemini cites through vertexaisearch redirects: follow one hop to the real page."""
    if "vertexaisearch.cloud.google.com" not in url:
        return url
    try:
        urllib.request.build_opener(_NoFollow).open(urllib.request.Request(url, method="HEAD"), timeout=20)
    except urllib.error.HTTPError as e:
        return e.headers.get("Location") or url
    except Exception:  # noqa: BLE001
        return url
    return url


def cited_from(raw: dict) -> tuple[list[str], list[str]]:
    """(cited, returned) URLs from an OpenRouter payload; see the top of the file for the rule."""
    msg = (raw.get("choices") or [{}])[0].get("message") or {}
    anns = [u for u in ((a.get("url_citation") or {}).get("url") or a.get("url")
                        for a in msg.get("annotations") or []) if u]
    plain = [u for u in raw.get("citations") or [] if isinstance(u, str)]   # older Perplexity payloads
    returned = list(dict.fromkeys(anns + plain))
    if str(raw.get("model") or "").startswith("perplexity/"):
        listed, used = anns or plain, []
        for m in re.findall(r"\[(\d+)\]", msg.get("content") or ""):
            i = int(m) - 1   # 1-based; a year in brackets falls outside the list and is ignored
            if 0 <= i < len(listed) and listed[i] not in used:
                used.append(listed[i])
        return used, returned
    return returned, returned


def slim(raw: dict) -> dict:
    """The payload minus opaque reasoning: encrypted reasoning data and signatures. Nobody but the
    model maker can read them, nothing here counts them, and they were a fifth of the baseline's
    size. Each block keeps its type, format and index, and the readable reasoning stays."""
    for choice in raw.get("choices") or []:
        for block in ((choice or {}).get("message") or {}).get("reasoning_details") or []:
            if isinstance(block, dict):
                block.pop("signature", None)
                if str(block.get("type") or "").endswith(".encrypted"):
                    block.pop("data", None)
    return raw


def domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


class Budget:
    """Spending for one `ask`: money OpenRouter reported, plus RESERVE for every call still running."""

    def __init__(self, cap: float):
        self.cap, self.reported, self.unknown, self.held = cap, 0.0, 0.0, 0.0
        self.lock = threading.Lock()

    def reserve(self) -> bool:
        with self.lock:
            if self.reported + self.unknown + self.held + RESERVE > self.cap:
                return False
            self.held += RESERVE
            return True

    def settle(self, cost: float | None) -> None:
        """Swap a call's reserve for its reported cost; with no reported cost it stays at RESERVE."""
        with self.lock:
            self.held -= RESERVE
            if cost is None:
                self.unknown += RESERVE
            else:
                self.reported += cost


def load_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _drop_torn_line(path: Path) -> None:
    """A run killed mid-write can leave half a line; cut it so the next answer starts on its own line."""
    with open(path, "rb") as f:
        data = f.read()
    if data and not data.endswith(b"\n"):
        print(f"{path}: dropping a half-written last line", file=sys.stderr)
        with open(path, "r+b") as f:
            f.truncate(data.rfind(b"\n") + 1)


def write_csv(rows: list[dict], site: str, path: Path, questions: list[str] = ()) -> None:
    """The baseline's table: one row per answer, in question order (the questions file's, then any
    others as they appear), then engine order, so a re-check lines up with the baseline row by row."""
    qs = {q: i for i, q in enumerate(dict.fromkeys([*questions, *(r["question"] for r in rows)]))}
    es = {e: i for i, e in enumerate(ENGINES)}
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["question", "engine", "model", f"cites_{site.split('.')[0]}", "domains_cited"])
        for r in sorted((r for r in rows if "error" not in r),
                        key=lambda r: (qs[r["question"]], es.get(r["engine"], len(es)))):
            w.writerow([r["question"], r["engine"], r["model"], "yes" if r["cites_site"] else "no",
                        "; ".join(dict.fromkeys(domain(u) for u in r["cited"]))])


def ask(questions: list[str], site: str, out: Path, cap: float, key: str, resume: bool = False) -> int:
    """Ask every engine every question not yet answered in `out`; 1 if any call failed or never started."""
    path = out / "answers.jsonl"
    if out.exists() and any(out.iterdir()) and not resume:
        raise SystemExit(f"{out} already holds a run: pass --resume to finish it, or pick a new --out")
    out.mkdir(parents=True, exist_ok=True)
    done = set()
    if path.exists():
        _drop_torn_line(path)
        done = {(r["question"], r["engine"]) for r in load_rows(path) if "error" not in r}
    budget, lock, tally = Budget(cap), threading.Lock(), Counter()

    def one(f, q: str, engine: str, model: str) -> None:
        """One call, journaled the moment it lands. Never raises an Exception: a failure is counted."""
        t0, cost = time.time(), None
        try:
            raw = ask_one(model, q, key)
            if not isinstance(raw, dict) or "error" in raw or not raw.get("choices"):
                cost = (raw.get("usage") or {}).get("cost") if isinstance(raw, dict) else None
                raise ValueError(f"no answer in the payload: {str(raw)[:200]}")
            cost = (raw.get("usage") or {}).get("cost")
            cited, returned = cited_from(raw)
            resolved = {u: real for u in cited if (real := resolve(u)) != u}   # kept: Gemini's redirects expire
            cited = list(dict.fromkeys(resolved.get(u, u) for u in cited))
            row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "question": q,
                   "engine": engine, "model": model, "served_model": raw.get("model"), "cited": cited,
                   "returned": returned, "resolved": resolved, "cites_site": any(domain(u) == site for u in cited),
                   "cost": cost, "secs": round(time.time() - t0, 1), "raw": slim(raw)}
            line = json.dumps(row) + "\n"
        except Exception as e:  # noqa: BLE001
            budget.settle(cost)
            with lock:
                tally["failed"] += 1
                print(f"FAILED {engine}: {q}: {e.__class__.__name__}: {e}", file=sys.stderr)
            return
        budget.settle(cost)
        with lock:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
            tally["answered"] += 1

    stopped = False
    try:
        with open(path, "a", encoding="utf-8") as f, ThreadPoolExecutor(len(ENGINES)) as pool:
            for q in questions:
                running = []
                for engine, model in ENGINES.items():
                    if (q, engine) in done:
                        tally["already"] += 1
                    elif stopped or not budget.reserve():
                        stopped = True
                        tally["skipped"] += 1
                    else:
                        running.append(pool.submit(one, f, q, engine, model))
                for job in running:   # one question at a time, its four engines together
                    job.result()
    finally:
        rows = load_rows(path)
        write_csv(rows, site, out / "answers.csv", questions)
    report(rows, site)
    extra = f", plus ${budget.unknown:.2f} held for calls with no reported cost" if budget.unknown else ""
    print(f"this run: {tally['answered']} answered, {tally['failed']} failed, {tally['skipped']} not started "
          f"(cap ${cap:.2f}), {tally['already']} already saved; ${budget.reported:.2f} spent{extra}")
    if tally["failed"] or tally["skipped"]:
        print(f"INCOMPLETE: {tally['failed'] + tally['skipped']} answers missing; "
              f"run again with --resume to ask only those", file=sys.stderr)
        return 1
    return 0


def count(run: Path, site: str, resolve_missing: bool = False) -> None:
    """Re-score a saved run from its payloads (the parsing above, not whatever was stored).
    Offline: redirects come from each answer's stored "resolved"; --resolve looks up the rest."""
    rows = load_rows(run / "answers.jsonl")
    for r in rows:
        if "raw" in r:
            cited, r["returned"] = cited_from(r["raw"])
            known = r.get("resolved") or {}
            r["cited"] = list(dict.fromkeys(known.get(u) or (resolve(u) if resolve_missing else u)
                                            for u in cited))
            r["cites_site"] = any(domain(u) == site for u in r["cited"])
    report(rows, site)


def report(rows: list[dict], site: str) -> None:
    ok = [r for r in rows if "error" not in r]
    per_domain = Counter(d for r in ok for d in {domain(u) for u in r["cited"]})
    print(f"{len(ok)} answers ({len(rows) - len(ok)} failed or skipped), "
          f"${sum(r.get('cost') or 0 for r in ok):.2f}")
    if no_cost := sum(r.get("cost") is None for r in ok):
        print(f"  ({no_cost} answers had no reported cost and count as $0 here)")
    print(f"{site} cited in {sum(r['cites_site'] for r in ok)}")
    print("most cited (answers citing each domain at least once):")
    for d, n in per_domain.most_common(10):
        print(f"  {n:4d}  {d}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask", help="ask every engine every question")
    a.add_argument("questions", type=Path, help="one question per line")
    a.add_argument("--site", required=True, help="your domain, e.g. example.co.uk")
    a.add_argument("--out", required=True, type=Path)
    a.add_argument("--cap", type=float, required=True, help="most this ask may spend, in dollars")
    a.add_argument("--resume", action="store_true", help="finish a stopped run in --out")
    c = sub.add_parser("count", help="re-score a saved run")
    c.add_argument("run", type=Path)
    c.add_argument("--site", required=True)
    c.add_argument("--resolve", action="store_true", help="look up Gemini redirects not stored with the run")
    args = ap.parse_args(argv)
    if args.cmd == "count":
        count(args.run, args.site.removeprefix("www."), args.resolve)
        return 0
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        ap.error("set OPENROUTER_API_KEY")
    with open(args.questions, encoding="utf-8-sig") as f:
        questions = [q.strip() for q in f if q.strip()]
    try:
        return ask(questions, args.site.removeprefix("www."), args.out, args.cap, key, args.resume)
    except KeyboardInterrupt:
        print(f"interrupted: the answers that landed are in {args.out / 'answers.jsonl'}; "
              f"run again with --resume", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
