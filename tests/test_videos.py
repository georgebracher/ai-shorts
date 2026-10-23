"""The evidence scripts under videos/: 001's citation checker and 003's clip judge, with synthetic
payloads and fake clients only. Nothing here reaches OpenRouter or Anthropic (audit N9)."""
import importlib.util
import json
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
V001 = ROOT / "videos" / "001-aeo-baseline"
BASELINE = V001 / "results" / "baseline-2026-10-18"
V003 = ROOT / "videos" / "003-clip-detector-coin-flip"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


check = _load("aeo_check", V001 / "check.py")
judge = _load("clip_judge", V003 / "judge.py")
REDIRECT = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/"


class Boom(BaseException):
    """An interruption (like Ctrl-C), not a failed call."""


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Any real HTTP attempt is recorded and refused; tests that talk to a fake swap it in."""
    tried = []

    def refuse(*a, **k):
        tried.append(a)
        raise AssertionError("network used")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(urllib.request, "build_opener", refuse)
    return tried


def _rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def payload(model: str, content: str = "", urls=(), cost=0.01, reasoning: bool = False) -> dict:
    msg = {"role": "assistant", "content": content,
           "annotations": [{"type": "url_citation", "url_citation": {"url": u, "title": ""}} for u in urls]}
    if reasoning:
        msg["reasoning"] = "readable thinking"
        msg["reasoning_details"] = [
            {"type": "reasoning.encrypted", "data": "OPAQUE-BLOB", "format": "f", "index": 0},
            {"type": "reasoning.text", "text": "readable thinking", "signature": "OPAQUE-SIG", "index": 1}]
    return {"model": model, "choices": [{"message": msg, "finish_reason": "stop"}], "usage": {"cost": cost}}


class _Reply:
    def __init__(self, data: bytes):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.data


class FakeOpenRouter:
    """Stands in for urlopen inside check.ask_one: answers every call by model and records it."""

    def __init__(self, cost=0.01, fail=(), interrupt=None, delay=0.0):
        self.cost, self.fail, self.interrupt, self.delay = cost, set(fail), interrupt, delay
        self.calls, self.lock = [], threading.Lock()

    def __call__(self, req, timeout=None):
        body = json.loads(req.data)
        q, model = body["messages"][0]["content"], body["model"]
        with self.lock:
            self.calls.append((q, model))
            n = len(self.calls)
        time.sleep(self.delay)   # real calls take seconds, so parallel ones overlap
        if (q, model) == self.interrupt:
            raise Boom()
        if model in self.fail or q in self.fail:
            raise urllib.error.URLError("connection refused")
        cost = self.cost(q, model) if callable(self.cost) else self.cost
        site = "mysite.co.uk" if model.startswith("google/") else "rightmove.co.uk"
        return _Reply(json.dumps(payload(model, "It is [1].", [f"https://www.{site}/{n}"], cost,
                                         reasoning=True)).encode())


def _spent(api, cost) -> float:
    return sum(cost(q, m) if callable(cost) else cost for q, m in api.calls)


# --- 001: what counts as cited ---

def test_perplexity_counts_only_the_results_its_answer_marks():
    urls = [f"https://site{i}.example/" for i in range(1, 6)]
    raw = payload("perplexity/sonar-pro", "Prices rose [2]. Since [2019] they [4][2] doubled [9] [0].", urls)
    cited, returned = check.cited_from(raw)
    assert cited == [urls[1], urls[3]]   # [2019], [9] and [0] fall outside the 1-based list of five
    assert returned == urls
    older = {"model": "perplexity/sonar", "citations": urls[:3],
             "choices": [{"message": {"content": "See [3]."}}]}
    assert check.cited_from(older) == ([urls[2]], urls[:3])
    other = payload("openai/gpt-6-sol", "No markers at all.", urls[:2])   # annotations back the answer
    assert check.cited_from(other) == (urls[:2], urls[:2])


def test_count_uses_stored_gemini_redirects_and_stays_offline(tmp_path, monkeypatch, capsys, no_network):
    run = tmp_path / "run"
    run.mkdir()
    row = {"question": "q", "engine": "gemini", "model": "google/gemini-3.5-flash-lite", "cost": 0.02,
           "cited": [], "cites_site": False, "resolved": {REDIRECT + "a": "https://www.mysite.co.uk/page"},
           "raw": payload("google/gemini-3.5-flash-lite", "", [REDIRECT + "a", REDIRECT + "b"])}
    with open(run / "answers.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    check.count(run, "mysite.co.uk")
    out = capsys.readouterr().out
    assert no_network == []   # the unresolved redirect "b" stays as it is
    assert "mysite.co.uk cited in 1" in out and "vertexaisearch.cloud.google.com" in out

    looked_up = []

    class Opener:
        def open(self, req, timeout=None):
            looked_up.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 302, "Found", {"Location": "https://other.example/x"}, None)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a: Opener())
    check.count(run, "mysite.co.uk", resolve_missing=True)
    assert looked_up == [REDIRECT + "b"]
    assert "other.example" in capsys.readouterr().out


# --- 001: spending, saving, resuming, exit codes ---

@pytest.mark.parametrize("cap", [0.4, 1.0, 1.7, 3.0])
def test_the_cap_never_lets_a_call_start_past_it(tmp_path, monkeypatch, capsys, cap):
    api = FakeOpenRouter(cost=0.30, delay=0.02)   # each answer costs less than the reserve
    monkeypatch.setattr(urllib.request, "urlopen", api)
    code = check.ask(["q1", "q2", "q3"], "mysite.co.uk", tmp_path / "run", cap, "key")
    assert _spent(api, 0.30) <= cap
    assert code == 1   # twelve calls never fit under these caps
    if cap < check.RESERVE:
        assert api.calls == []


def test_a_dear_answer_or_a_failed_call_stops_new_calls(tmp_path, monkeypatch, capsys):
    api = FakeOpenRouter(cost=lambda q, m: 5.0 if m.startswith("openai/") else 0.1, delay=0.02)
    monkeypatch.setattr(urllib.request, "urlopen", api)
    code = check.ask(["q1", "q2"], "mysite.co.uk", tmp_path / "a", 3.0, "key")
    assert {q for q, _ in api.calls} == {"q1"}   # q1's four fit the cap at the reserve; q2 never starts
    assert code == 1

    down = FakeOpenRouter(fail={"q1", "q2"})   # failed calls may have been billed: they keep their reserve
    monkeypatch.setattr(urllib.request, "urlopen", down)
    code = check.ask(["q1", "q2"], "mysite.co.uk", tmp_path / "b", 1.0, "key")
    assert len(down.calls) == 2 and code == 1


def test_answers_are_saved_as_they_land_and_resume_asks_only_whats_missing(tmp_path, monkeypatch, capsys):
    run, qs = tmp_path / "run", ["q1", "q2", "q3"]
    api = FakeOpenRouter(interrupt=("q2", "google/gemini-3.5-flash-lite"))
    monkeypatch.setattr(urllib.request, "urlopen", api)
    with pytest.raises(Boom):
        check.ask(qs, "mysite.co.uk", run, 10, "key")
    saved = [(r["question"], r["engine"]) for r in _rows(run / "answers.jsonl")]
    assert len(saved) == 7 and ("q2", "gemini") not in saved   # q1's four and q2's other three

    with pytest.raises(SystemExit, match="--resume"):
        check.ask(qs, "mysite.co.uk", run, 10, "key")   # an existing run is never overwritten
    assert len(_rows(run / "answers.jsonl")) == 7

    again = FakeOpenRouter()
    monkeypatch.setattr(urllib.request, "urlopen", again)
    assert check.ask(qs, "mysite.co.uk", run, 10, "key", resume=True) == 0
    assert sorted(q for q, _ in again.calls) == ["q2", "q3", "q3", "q3", "q3"]
    rows = _rows(run / "answers.jsonl")
    assert Counter((r["question"], r["engine"]) for r in rows) == Counter(
        {(q, e): 1 for q in qs for e in check.ENGINES})
    with open(run / "answers.csv", encoding="utf-8", newline="") as f:
        table = f.read().splitlines()
    assert table[0] == "question,engine,model,cites_mysite,domains_cited"   # the baseline's columns
    assert [line.split(",")[:2] for line in table[1:]] == [[q, e] for q in qs for e in check.ENGINES]
    assert all(line.split(",")[3] == ("yes" if line.split(",")[1] == "gemini" else "no") for line in table[1:])


def test_saved_payloads_drop_opaque_reasoning_but_count_the_same(tmp_path, monkeypatch, capsys):
    run = tmp_path / "run"
    monkeypatch.setattr(urllib.request, "urlopen", FakeOpenRouter())
    check.ask(["q1"], "mysite.co.uk", run, 10, "key")
    with open(run / "answers.jsonl", encoding="utf-8") as f:
        text = f.read()
    assert "OPAQUE" not in text and "readable thinking" in text
    for r in _rows(run / "answers.jsonl"):
        assert check.cited_from(r["raw"])[0] == r["cited"]


def test_ask_exits_nonzero_when_a_call_fails(tmp_path, monkeypatch, capsys):
    questions = tmp_path / "questions.txt"
    questions.write_text("q1\n", encoding="utf-8")
    monkeypatch.setattr(urllib.request, "urlopen", FakeOpenRouter(fail={"perplexity/sonar-pro"}))
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-key")
    monkeypatch.setattr(sys, "argv", ["check.py", "ask", str(questions), "--site", "mysite.co.uk",
                                      "--out", str(tmp_path / "run"), "--cap", "10"])
    assert check.main() == 1
    out = capsys.readouterr()
    assert "3 answered, 1 failed, 0 not started" in out.out and "INCOMPLETE" in out.err


# --- 001: the published baseline ---

def test_baseline_recounts_to_the_published_numbers(capsys):
    check.count(BASELINE, "southcoasthouseprices.co.uk")
    out = capsys.readouterr().out
    for line in ("200 answers (0 failed or skipped), $7.19", "southcoasthouseprices.co.uk cited in 0",
                 " 104  rightmove.co.uk", "  37  zoopla.co.uk", "  21  housesforsaletorent.co.uk",
                 "  20  ons.gov.uk", "  19  onthemarket.com"):
        assert line in out


def test_baseline_rows_match_their_payloads_and_carry_no_opaque_reasoning(tmp_path):
    rows = _rows(BASELINE / "answers.jsonl")
    for i, r in enumerate(rows, 1):
        cited, returned = check.cited_from(r["raw"])
        assert r["returned"] == returned, f"row {i}"   # row 180 kept a blanked result here (audit N3)
        assert r["cited"] == [(r["resolved"] or {}).get(u, u) for u in cited], f"row {i}"
        for block in r["raw"]["choices"][0]["message"].get("reasoning_details") or []:
            assert "signature" not in block and not (block["type"].endswith(".encrypted") and "data" in block)
    with open(V001 / "questions.txt", encoding="utf-8") as f:
        questions = [q.strip() for q in f if q.strip()]
    check.write_csv(rows, "southcoasthouseprices.co.uk", tmp_path / "answers.csv", questions)
    assert (tmp_path / "answers.csv").read_bytes() == (BASELINE / "answers.csv").read_bytes()


# --- 003: the judge ---

class FakeClaude:
    """Stands in for anthropic.Anthropic(): replies by transcript, or from a fixed list."""

    def __init__(self, replies=None, interrupt_at=None):
        self.replies, self.interrupt_at, self.calls = replies, interrupt_at, 0
        self.messages = self

    def create(self, **kw):
        self.calls += 1
        if self.calls == self.interrupt_at:
            raise Boom()
        if self.replies is not None:
            r = self.replies[(self.calls - 1) % len(self.replies)]
        else:
            text = kw["messages"][0]["content"]
            r = "I'd say 70" if "odd" in text else "80" if "good" in text else "20"
        if isinstance(r, Exception):
            raise r
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=r)])


@pytest.mark.parametrize("text, expected", [
    ("70", 70), (" 70\n", 70), ("0", 0), ("100", 100),
    ("48 examples suggest 70", None), ("-5", None), ("101", None), ("70%", None),
    ("about 70", None), ("", None), ("70.5", None)])
def test_judge_takes_only_a_bare_integer(text, expected):
    assert judge.score(FakeClaude([text]), "system", {"game": "g", "transcript": "t"}) == expected


def test_auc_needs_both_classes():
    assert judge.auc([(90, True), (10, False), (50, True), (50, False)]) == 0.875
    for one_class in ([(50, True), (60, True)], [(50, False)], []):
        with pytest.raises(ValueError, match="both kept and rejected"):
            judge.auc(one_class)


def test_pick_takes_at_most_four_from_any_one_stream():
    big = [{"stream": "big", "kept": k, "transcript": f"{i}"} for i in range(100) for k in (True, False)]
    small = [{"stream": f"s{s}", "kept": k, "transcript": f"{s}-{i}"} for s in range(12) for i in range(2)
             for k in (True, False)]
    chosen = judge.pick(big + small, 48)
    assert len(chosen) == 48 and sum(c["kept"] for c in chosen) == 24
    assert max(Counter(c["stream"] for c in chosen).values()) <= 4   # the README's promise
    plain = [{"kept": k, "transcript": f"{i}"} for i in range(30) for k in (True, False)]
    assert len(judge.pick(plain, 48)) == 48   # no stream field: no limit


def _graded(tmp_path) -> Path:
    clips = ([{"game": "g", "transcript": f"good {i}", "kept": True} for i in range(6)]
             + [{"game": "g", "transcript": f"bad {i}", "kept": False} for i in range(6)]
             + [{"game": "g", "transcript": "odd one", "kept": True}])
    path = tmp_path / "graded.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(c) + "\n" for c in clips)
    return path


def test_judge_test_reports_failures_and_saves_every_score(tmp_path, monkeypatch, capsys):
    client = FakeClaude()
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=lambda: client))
    out = tmp_path / "scores.jsonl"
    monkeypatch.setattr(sys, "argv", ["judge.py", "test", str(_graded(tmp_path)), "--examples", "4",
                                      "--out", str(out)])
    assert judge.main() == 1   # one clip failed
    printed = capsys.readouterr()
    assert "test: 9 calls" in printed.err   # 13 clips, 4 examples
    assert "9 attempted, 8 scored, 1 failed, 0 not attempted" in printed.out
    assert "AUC 1.000 on the 8 scored" in printed.out
    saved = _rows(out)
    assert client.calls == len(saved) == 9
    assert [r["reply"] for r in saved if r["keep_probability"] is None] == ["I'd say 70"]


def test_judge_test_obeys_max_calls_and_keeps_work_when_stopped(tmp_path, monkeypatch, capsys):
    client = FakeClaude()
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=lambda: client))
    graded = _graded(tmp_path)
    argv = ["judge.py", "test", str(graded), "--examples", "4", "--max-calls", "5", "--out"]
    monkeypatch.setattr(sys, "argv", argv + [str(tmp_path / "a.jsonl")])
    judge.main()
    assert client.calls == 5 and len(_rows(tmp_path / "a.jsonl")) == 5
    assert "test: 5 calls" in capsys.readouterr().err

    stopped = FakeClaude(interrupt_at=4)
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=lambda: stopped))
    monkeypatch.setattr(sys, "argv", argv + [str(tmp_path / "b.jsonl")])
    with pytest.raises(Boom):
        judge.main()
    assert len(_rows(tmp_path / "b.jsonl")) == 3   # the three that landed before the stop

    down = FakeClaude([RuntimeError("overloaded")])
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=lambda: down))
    monkeypatch.setattr(sys, "argv", argv[:-3] + ["--out", str(tmp_path / "c.jsonl")])
    assert judge.main() == 1
    assert down.calls == judge.ERRORS_IN_A_ROW
    assert "3 attempted, 0 scored, 3 failed, 6 not attempted" in capsys.readouterr().out
