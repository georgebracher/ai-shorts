"""Stage 1: read a script file (YAML front matter + body text)."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .text import tokens_with_owner


@dataclass
class Step:
    label: str
    trigger: str


@dataclass
class Stat:
    label: str   # "Rightmove"
    value: str   # "122"
    trigger: str = ""   # spoken phrase that pops it in, when the value is not said as written


@dataclass
class Chip:
    label: str
    trigger: str


@dataclass
class Beat:
    """A hook graphic for the empty panel before the stats / first step.

    kind "chips":   labels popping in one by one, each when its own trigger is said.
    kind "counter": a number counting up from 0 when `trigger` is said.
    """
    kind: str
    trigger: str = ""
    items: list[Chip] = field(default_factory=list)
    value: str = ""
    label: str = ""


BEAT_KINDS = ("chips", "counter")


def parse_beat(item: dict) -> Beat:
    if not isinstance(item, dict) or item.get("kind") not in BEAT_KINDS:
        raise ValueError(f"beat needs kind one of {BEAT_KINDS}, got {item!r}")
    if item["kind"] == "chips":
        chips = []
        for c in item.get("items") or []:
            if isinstance(c, dict):
                chips.append(Chip(str(c["label"]), str(c.get("trigger") or c["label"])))
            else:
                chips.append(Chip(str(c), str(c)))
        if not chips:
            raise ValueError("chips beat needs items")
        return Beat("chips", str(item.get("trigger") or chips[0].trigger), chips)
    if "value" not in item:
        raise ValueError("counter beat needs a value")
    value = str(item["value"])
    return Beat("counter", str(item.get("trigger") or value), value=value,
                label=str(item.get("label", "")))


@dataclass
class Spec:
    slug: str
    title: str
    steps: list[Step]
    stats: list[Stat]
    body: str
    beats: list[Beat] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def words(self) -> list[str]:
        return self.body.split()

    def tokens(self) -> list[tuple[str, int]]:
        """Normalised script tokens, each with the index of its body word."""
        return tokens_with_owner(self.words)


def parse_stat(item) -> Stat:
    if isinstance(item, dict):
        return Stat(str(item["label"]), str(item["value"]), str(item.get("trigger", "")))
    label, _, value = str(item).strip().rpartition(" ")
    if not label:
        raise ValueError(f"stat needs 'label value', got {item!r}")
    return Stat(label, value)


def parse_spec_text(text: str) -> Spec:
    if not text.startswith("---"):
        raise ValueError("script must start with YAML front matter (---)")
    _, front, body = text.split("---", 2)
    meta = yaml.safe_load(front) or {}
    for key in ("slug", "title"):
        if not meta.get(key):
            raise ValueError(f"front matter is missing '{key}'")
    steps = [Step(str(s["label"]), str(s.get("trigger", "")).strip().lower())
             for s in meta.get("steps") or []]
    stats = [parse_stat(s) for s in meta.get("stats") or []]
    beats = [parse_beat(b) for b in meta.get("beats") or []]
    known = ("slug", "title", "steps", "stats", "beats")
    extra = {k: v for k, v in meta.items() if k not in known}
    return Spec(str(meta["slug"]), str(meta["title"]), steps, stats, body.strip(), beats, extra)


def load_spec(path: str | Path) -> Spec:
    return parse_spec_text(Path(path).read_text(encoding="utf-8"))
