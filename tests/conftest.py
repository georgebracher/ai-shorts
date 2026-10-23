"""Shared test helpers. The repo root and tests/ are on the import path through
pyproject.toml ([tool.pytest.ini_options] pythonpath), not through sys.path edits."""
from pathlib import Path

import pytest

from ai_shorts.transcribe import Word

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "001-aeo-baseline.md"
# the script as it stood when the real takes (DJI_0348, IMG_5328) were recorded: their fixtures align to this
RECORDED_SCRIPT = ROOT / "tests" / "fixtures" / "001-aeo-baseline-recorded.md"


@pytest.fixture(autouse=True)
def writes_stay_in_tmp(tmp_path, monkeypatch):
    """Anything a test runs in-process writes under its tmp_path: the pipeline's work dirs and
    placed pickups (PROJECT_ROOT/out) and the review and archive folders (~/Downloads).
    next_version()'s default folders are bound when pipeline.py loads, so tests pass theirs in."""
    from ai_shorts import pipeline, remote
    review = tmp_path / "Downloads"
    for mod in (pipeline, remote):
        monkeypatch.setattr(mod, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(mod, "REVIEW_DIR", review)
        monkeypatch.setattr(mod, "OUTPUT_ROOT", review / "AI Shorts")


def words_from(text: str, start: float = 0.0, dur: float = 0.3, gap: float = 0.05) -> list[Word]:
    """Evenly timed Words for a sentence; a '|' token inserts a 1.5 s pause."""
    out, t = [], start
    for tok in text.split():
        if tok == "|":
            t += 1.5
            continue
        out.append(Word(tok, t, t + dur))
        t += dur + gap
    return out
