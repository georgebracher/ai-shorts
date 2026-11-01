"""Word normalisation shared by the aligner, step triggers and stats.

Whisper writes "1." for "One." and "122" for "a hundred and twenty-two", so both
sides are reduced to the same lowercase word tokens before comparing.
"""
import re
from difflib import SequenceMatcher
from functools import lru_cache

ONES = ("zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
CURRENCY = {"$": "dollars", "£": "pounds", "€": "euros"}
# Whisper's spellings of what this series says most: 004 (1 Nov 2026), "See who sights you" in his
# last clean take read as a worse take than an earlier "See who cites you".
SAME_SOUND = {"sight": "site", "cite": "site", "sights": "sites", "cites": "sites",
              "sighted": "cited", "sited": "cited"}


def number_words(n: int) -> list[str]:
    if n < 20:
        return [ONES[n]]
    if n < 100:
        t, o = divmod(n, 10)
        return [TENS[t]] + ([ONES[o]] if o else [])
    if n < 1000:
        h, r = divmod(n, 100)
        return [ONES[h], "hundred"] + (["and"] + number_words(r) if r else [])
    if n < 1_000_000:
        th, r = divmod(n, 1000)
        rest = []
        if r:
            rest = (["and"] if r < 100 else []) + number_words(r)
        return number_words(th) + ["thousand"] + rest
    return [str(n)]


def normalize_word(raw: str) -> list[str]:
    """One raw word -> zero or more comparable tokens."""
    w = raw.lower().replace("’", "'").replace("‘", "'").strip()
    suffix = []
    for sym, name in CURRENCY.items():
        if w.startswith(sym):
            w, suffix = w[1:], [name]
    w = w.replace(",", "") if re.fullmatch(r"[\d,]+(\.\d+)?%?[.!?]*", w) else w
    if "%" in w:
        w, suffix = w.replace("%", ""), ["percent"] + suffix
    out = []
    for part in re.split(r"[-/–—\s]+", w):
        part = part.replace("'", "")
        part = re.sub(r"[^a-z0-9.]", "", part).strip(".")
        if not part:
            continue
        if re.fullmatch(r"\d+", part):
            out += number_words(int(part))
        elif re.fullmatch(r"\d+\.\d+", part):
            a, b = part.split(".")
            out += number_words(int(a)) + ["point"] + [ONES[int(d)] for d in b]
        else:
            out += [SAME_SOUND.get(p, p) for p in part.split(".") if p]
    return out + suffix


def tokens_with_owner(words: list[str]) -> list[tuple[str, int]]:
    """Normalise a word list into (token, index of the word it came from)."""
    toks = []
    for i, w in enumerate(words):
        toks += [(t, i) for t in normalize_word(w)]
    # "a hundred" is said the same as "one hundred"
    for k in range(len(toks) - 1):
        if toks[k][0] == "a" and toks[k + 1][0] in ("hundred", "thousand"):
            toks[k] = ("one", toks[k][1])
    return toks


def normalize_text(text: str) -> list[str]:
    return [t for t, _ in tokens_with_owner(text.split())]


@lru_cache(maxsize=65536)
def same(a: str, b: str) -> bool:
    """Exact for short words, fuzzy (ratio >= 0.8) for longer ones."""
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    return SequenceMatcher(None, a, b).ratio() >= 0.8


@lru_cache(maxsize=65536)
def same_join(a: str, b: str) -> bool:
    """Stricter match for a word whisper split or merged ("write"+"move" vs
    "rightmove"): at most two letters' difference and a high ratio, so "times"+"my"
    does not pass for "times"."""
    if a == b:
        return True
    if len(a) < 6 or len(b) < 6 or abs(len(a) - len(b)) > 2:
        return False
    return SequenceMatcher(None, a, b).ratio() >= 0.85


@lru_cache(maxsize=65536)
def sound_key(word: str) -> str:
    """Rough consonant skeleton so homophones line up: "write move" and
    "Rightmove" both give "rtmv". Only used to recognise names."""
    s = re.sub(r"[^a-z]", "", word.lower())
    for a, b in (("wr", "r"), ("igh", "i"), ("gh", ""), ("ph", "f"), ("ck", "k"),
                 ("qu", "kw"), ("x", "ks"), ("kn", "n")):
        s = s.replace(a, b)
    s = re.sub(r"c(?=[eiy])", "s", s).replace("c", "k")
    key = s[:1] + re.sub(r"[aeiouy]", "", s[1:])
    return re.sub(r"(.)\1+", r"\1", key)


def ends_sentence(word: str) -> bool:
    return word.rstrip("\"')").endswith((".", "?", "!"))


def ends_clause(word: str) -> bool:
    return word.rstrip("\"')").endswith((",", ";", ":"))
