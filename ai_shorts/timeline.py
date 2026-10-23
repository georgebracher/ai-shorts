"""Stage 4a: when things appear. Step triggers, stat callouts, caption chunks.

All times here are OUTPUT times (after trimming).
"""
from dataclasses import dataclass

from .spec import Beat, Stat, Step
from .text import ONES, TENS, ends_clause, ends_sentence, normalize_text, normalize_word, tokens_with_owner
from .transcribe import Word


LISTENERS: list = []   # a render puts its report's list here, so these warnings are kept as well as logged


def warn(msg: str) -> None:
    print(f"[ai-shorts] WARNING: {msg}", flush=True)
    for keep in LISTENERS:
        keep(msg)


def step_times(words: list[Word], steps: list[Step],
               script_words: list[str] | None = None) -> list[float | None]:
    """When each step's trigger word is spoken, strictly in order.

    First choice: the trigger's position in the script (the first occurrence after
    the previous step's), mapped to the transcript word aligned there. This stops
    "Two hundred answers" firing step two before step one. Fallback: the first
    spoken word equal to the trigger after the previous step, but not one said in a
    later step's line. A trigger never heard ("First," for "One.") whose place in the
    script is known shows where its line starts, with a warning: on fill_missing's
    timer a missed first trigger cleared the hook at 1.0 s and hid the stats, and
    the fallback took the "one" of "Day one" at the end (audit claude-010, 20 Oct 2026).
    """
    stoks = tokens_with_owner(script_words) if script_words else []
    pos: list[int | None] = []          # script token of each trigger, in order
    prev_s = -1
    for step in steps:
        trig = normalize_word(step.trigger)
        s = None
        if stoks and len(trig) == 1:
            # the trigger must be a whole script word: "a hundred" is not "one"
            s = next((k for k in range(prev_s + 1, len(stoks))
                      if stoks[k][0] == trig[0]
                      and normalize_word(script_words[stoks[k][1]]) == trig), None)
        pos.append(s)
        if s is not None:
            prev_s = s

    def first_aligned(lo: int, hi: int, after: float) -> float | None:
        w = next((w for w in words if w.script_lo is not None and lo <= w.script_lo < hi
                  and w.start > after), None)
        return w.start if w else None

    times: list[float | None] = []
    prev_t = -1.0
    for k, step in enumerate(steps):
        trig, s, t = normalize_word(step.trigger), pos[k], None
        nxt = next((p for p in pos[k + 1:] if p is not None), len(stoks))
        if s is not None:
            w = next((w for w in words if w.script_lo is not None
                      and w.script_lo <= s <= w.script_hi and w.start > prev_t), None)
            t = w.start if w else None
        if t is None and trig:
            limit = first_aligned(nxt, len(stoks), prev_t) if s is not None else None
            w = next((w for w in words if w.start > prev_t and (limit is None or w.start < limit)
                      and normalize_word(w.text) == trig), None)
            t = w.start if w else None
        if t is None and s is not None:
            t = first_aligned(s + 1, nxt, prev_t)
            if t is not None:
                warn(f"trigger '{step.trigger}' for step '{step.label}' never heard; "
                     f"shown where its line starts ({t:.1f} s)")
        times.append(t)
        if t is not None:
            prev_t = t
    return times


def fill_missing(times: list[float | None], gap: float = 1.0) -> list[float]:
    """A step whose trigger was never heard still shows, `gap` after the one before, or
    before any step was heard, `gap` ahead of the first that was: counting from 0 s put
    a missed first step at 1.0 s, over the hook (audit claude-010, 20 Oct 2026)."""
    first = next((k for k, t in enumerate(times) if t is not None), None)
    out, prev = [], 0.0
    for k, t in enumerate(times):
        if first is not None and k < first:
            t = max(0.0, times[first] - gap * (first - k))
        elif t is None or t < prev:
            t = prev + gap
        out.append(t)
        prev = t
    return out


def flatten(words: list[Word]) -> list[tuple[str, Word]]:
    """Every normalised token of the spoken words, with the word it came from."""
    return [(tok, words[wi]) for tok, wi in tokens_with_owner([w.text for w in words])]


_UNITS = set(ONES)
_TENS = {t for t in TENS if t != "_"}
_SCALES = {"hundred", "thousand"}
_DIGITS = set(ONES[:10])


def _number_joins(toks: list[str]) -> list[bool]:
    """Per token: does it carry on the number the token before it is in? "two" "hundred",
    "twenty" "two", "hundred" "and" "one", "seven" "point" "two" "five" are one number each."""
    joins, decimal = [False] * len(toks), False
    for i in range(1, len(toks)):
        a, b = toks[i - 1], toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        number = a in _UNITS or a in _TENS or a in _SCALES
        if b in _SCALES:
            j = number
        elif b == "point":
            j = number and nxt in _DIGITS
        elif b == "and":
            j = a in _SCALES and (nxt in _UNITS or nxt in _TENS)
        elif b in _UNITS or b in _TENS:
            j = a in _SCALES or (a == "and" and joins[i - 1]) or \
                (a in _TENS and b in _DIGITS and b != "zero") or \
                ((a == "point" or decimal) and joins[i - 1] and b in _DIGITS)
        else:
            j = False
        decimal = j and (b == "point" or decimal)
        joins[i] = j
    return joins


def find_phrase(flat: list[tuple[str, Word]], target: list[str], k0: int = 0) -> tuple[int, int] | None:
    """First run of tokens from k0 spelling `target`. Compared with spaces removed,
    so "chat" "gpt" matches "chatgpt" and "200" matches "two hundred". A run never
    starts or ends inside a spoken number: a stat for 2 fired on the "two" of "200"
    (audit codex-004, 20 Oct 2026)."""
    joined = "".join(target)
    if not joined:
        return None
    joins = _number_joins([t for t, _ in flat])
    for k in range(k0, len(flat)):
        if joins[k]:
            continue
        acc = ""
        for end in range(k, min(len(flat), k + len(target) + 3)):
            acc += flat[end][0]
            if acc == joined:
                if end + 1 < len(flat) and joins[end + 1]:
                    break
                return k, end + 1
            if not joined.startswith(acc):
                break
    return None


def stat_times(words: list[Word], stats: list[Stat]) -> list[float | None]:
    """Each stat pops in when its value is said ("122", "zero"), in order. A stat can
    name its own trigger instead ("three times out of four" for "3 in 4"): without
    one, a value said differently fell back to the label's first word, and 003's
    "Detector" card would have popped on "I built a clip detector". A stat never heard
    is not shown, with a warning (it vanished silently before audit k3-007, 20 Oct 2026)."""
    flat, times, k0 = flatten(words), [], 0
    for st in stats:
        if st.trigger:
            hit = find_phrase(flat, normalize_text(st.trigger), k0)
        else:
            hit = find_phrase(flat, normalize_word(st.value), k0) or \
                find_phrase(flat, normalize_text(st.label)[:1], k0)
        times.append(flat[hit[0]][1].start if hit else None)
        if hit:
            k0 = hit[1]
        else:
            warn(f"stat '{st.label}' ({st.value}) never heard; not shown")
    return times


def beat_times(words: list[Word], beats: list[Beat], gap: float = 0.3) -> list[list[float] | None]:
    """Per beat, the times its parts appear (one per chip; one for a counter).
    Matched in order through the video. A beat whose triggers are never heard
    is None (not shown); a single unheard chip shows `gap` after the one before."""
    flat, k0, out = flatten(words), 0, []
    for b in beats:
        triggers = [c.trigger for c in b.items] if b.kind == "chips" else [b.trigger]
        times: list[float | None] = []
        for trig in triggers:
            hit = find_phrase(flat, normalize_text(trig), k0)
            times.append(flat[hit[0]][1].start if hit else None)
            if hit:
                k0 = hit[1]
        found = [t for t in times if t is not None]
        if not found:
            out.append(None)
            continue
        filled, prev = [], found[0] - gap
        for t in times:
            prev = prev + gap if t is None else t
            filled.append(prev)
        out.append(filled)
    return out


@dataclass
class Chunk:
    words: list[Word]

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end


# Words a caption chunk should not end on ("ON THE" / "SOUTH COAST").
WEAK = {"a", "an", "the", "and", "or", "but", "of", "on", "in", "to", "for", "at",
        "with", "from", "by", "my", "your", "our", "their", "his", "her", "its", "is"}


def _chars(ws: list[Word]) -> int:
    return len(" ".join(display_word(w.text) for w in ws))


def _split_phrase(ph: list[Word], max_words: int, max_chars: int) -> list[list[Word]]:
    chunks, cur = [], []
    for w in ph:
        if cur and (len(cur) >= max_words or _chars(cur + [w]) > max_chars):
            weak = cur[-1].text.lower().strip(",.;:") in WEAK
            if weak and len(cur) < 3 and len(cur) < max_words and _chars(cur + [w]) <= max_chars + 6:
                cur.append(w)            # "WRITE THE QUESTIONS" beats "WRITE THE" / "QUESTIONS"
                continue
            carry = []
            while len(cur) >= 3 and cur[-1].text.lower().strip(",.;:") in WEAK:
                carry.insert(0, cur.pop())       # never strand a single word
            chunks.append(cur)
            cur = carry
        cur.append(w)
    if cur:
        chunks.append(cur)
    # never leave one word dangling at the end of a phrase
    if len(chunks) >= 2 and len(chunks[-1]) == 1:
        prev = chunks[-2]
        if len(prev) < max_words and _chars(prev + chunks[-1]) <= max_chars + 4:
            prev += chunks.pop()
        elif len(prev) >= 3:
            chunks[-1].insert(0, prev.pop())
    return chunks


def chunk_captions(words: list[Word], max_words: int = 4, max_chars: int = 20,
                   gap: float = 0.35) -> list[Chunk]:
    """Group words into 2-4 word caption chunks.

    Phrases end at sentence punctuation, or at a comma / pause once they have two
    words. Each phrase fills chunks up to max_words / max_chars, never ending a
    chunk on a weak word ("the", "on") and never leaving a lone last word. A lone
    word only stands alone when it is a whole sentence ("One.").
    """
    phrases, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        pause = nxt is not None and nxt.start - w.end > gap
        if nxt is None or ends_sentence(w.text) or (len(cur) >= 2 and (ends_clause(w.text) or pause)):
            phrases.append(cur)
            cur = []
    return [Chunk(c) for ph in phrases for c in _split_phrase(ph, max_words, max_chars)]


def display_word(text: str) -> str:
    """Caption style: upper case, keep ? and ! but drop . , ; :"""
    return text.upper().strip(".,;:\"").replace('"', "")
