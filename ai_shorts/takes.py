"""Stage 3a: pick one take of every script sentence George actually said.

He may paraphrase, repeat lines, and restart lines out of order. So:

1. Split the transcript into units: sentence-sized runs of words (break after
   . ? ! and at pauses over UNIT_PAUSE).
2. Split the script into sentences (a lone step word like "One." joins the
   sentence after it; any other lone word joins the one before).
3. Match each unit to the script with a fuzzy local alignment (content words
   count more than filler, numbers normalised, "write move" == "Rightmove"),
   giving the script tokens it covers. A unit may cover several sentences.
4. Choose a chain of units that moves forward through the script (a longest-
   path DP). Each script sentence is covered by one take; a sentence may run
   across consecutive units. A take counts as complete if it covers at least
   COMPLETE of the best take of that sentence; between complete takes the later
   one wins, so the last good take of every line is kept. Units that would go
   backwards (a stray restart after a later line) or match nothing are dropped.
   Cuts follow the recording, so a complete retake of line A said after line B
   cannot replace the take of A before B: it is dropped with a warning.
"""
from dataclasses import dataclass, field

from .text import ends_sentence, normalize_word, same, same_join, tokens_with_owner
from .timeline import warn
from .transcribe import Word

UNIT_PAUSE = 1.0     # seconds of silence that end a unit even without punctuation
COMPLETE = 0.8       # coverage (vs the best take of a sentence) that counts as complete
MIN_MATCH = 1.0      # matched weight for a unit to count as a take at all
MIN_SHARE = 0.35     # share of the unit's own words that must match the script
LATE = 1e-4          # tie-break per unit index and sentence covered: later takes win ties

# Filler words: they match cheaply and prove little about which line is being said.
STOP = set("""a an the and or but of on in to for at with from by as is are was were be been
being it its this that thats these those there here so if then than i im ive id me my mine
you youre your we our they their he his she her them do does did dont not no just about
very really get got can cant will would could should""".split())


def weight(tok: str) -> float:
    return 0.3 if tok in STOP else 1.0


@dataclass
class Place:
    """One way a unit can line up with the script."""
    lo: int                                # script token span covered
    hi: int
    sent_lo: int                           # script sentence span covered
    sent_hi: int
    cover: dict[int, float]                # sentence -> matched weight


@dataclass
class Unit:
    words: list[int]                       # indices into the transcript words
    places: list[Place] = field(default_factory=list)
    chosen: Place | None = None

    @property
    def candidate(self) -> bool:
        return bool(self.places)


def split_units(words: list[Word], pause: float = UNIT_PAUSE,
                triggers: set[str] = frozenset()) -> list[list[int]]:
    units, cur = [], []
    for i, w in enumerate(words):
        if cur and w.start - words[i - 1].end > pause:
            units.append(cur)
            cur = []
        cur.append(i)
        if ends_sentence(w.text):
            units.append(cur)
            cur = []
    if cur:
        units.append(cur)
    # a lone step word ("1.", "Two.") starts the unit after it; a lone content
    # word ("Zero.") finishes the one before, unless a long pause separates them;
    # a lone filler word ("this.") stays on its own and drops unless it matches
    out: list[list[int]] = []
    carry: list[int] = []
    for k, u in enumerate(units):
        u = carry + u
        carry = []
        if len(u) == 1:
            nxt = units[k + 1] if k + 1 < len(units) else None
            tok = normalize_word(words[u[0]].text)
            if tok and tok[0] in triggers and nxt and words[nxt[0]].start - words[u[0]].end <= pause:
                carry = u
                continue
            content = bool(tok) and not all(t in STOP for t in tok)
            if out and content and words[u[0]].start - words[out[-1][-1]].end <= pause \
                    and tok[0] not in triggers:
                out[-1] += u
                continue
        out.append(u)
    if carry:
        out.append(carry)
    return out


def script_sentences(script_words: list[str], triggers: set[str] = frozenset()) -> list[int]:
    """Sentence index for every script word."""
    spans, cur = [], []
    for i, w in enumerate(script_words):
        cur.append(i)
        if ends_sentence(w):
            spans.append(cur)
            cur = []
    if cur:
        spans.append(cur)
    merged: list[list[int]] = []
    carry: list[int] = []
    for k, sp in enumerate(spans):
        sp = carry + sp
        carry = []
        if len(sp) == 1 and k + 1 < len(spans):
            word = normalize_word(script_words[sp[0]])
            if word and word[0] in triggers:        # "One." belongs to the step it starts
                carry = sp
                continue
            if merged:                              # "Zero." finishes the line before it
                merged[-1] += sp
                continue
        merged.append(sp)
    if carry:
        merged.append(carry)
    sent = [0] * len(script_words)
    for k, sp in enumerate(merged):
        for i in sp:
            sent[i] = k
    return sent


def local_alignments(T: list[str], S: list[str], tok_sent: list[int]) -> list[list[tuple[int, int]]]:
    """Fuzzy local alignments of unit tokens T inside script tokens S
    (Smith-Waterman: matches score by weight, paraphrase gaps cost a little).
    The script repeats phrases ("Rightmove ... 122" is in two lines), so this
    returns the best alignment ending in EACH script sentence, and the chain
    picks the one that fits. Each is a list of matched (t, s) pairs."""
    GAP, MISS = 0.25, 0.35
    m, n = len(T), len(S)
    H = [[0.0] * (n + 1) for _ in range(m + 1)]
    back: list[list[tuple | None]] = [[None] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            opts = [(0.0, None)]
            if same(T[i - 1], S[j - 1]):
                opts.append((H[i - 1][j - 1] + weight(S[j - 1]), ("m", i - 1, j - 1)))
            else:
                opts.append((H[i - 1][j - 1] - MISS, ("x", i - 1, j - 1)))
            if i >= 2 and same_join(T[i - 2] + T[i - 1], S[j - 1]):
                opts.append((H[i - 2][j - 1] + weight(S[j - 1]), ("m2", i - 2, j - 1)))
            if j >= 2 and same_join(T[i - 1], S[j - 2] + S[j - 1]):
                opts.append((H[i - 1][j - 2] + weight(S[j - 2]) + weight(S[j - 1]),
                             ("m3", i - 1, j - 2)))
            opts.append((H[i - 1][j] - GAP, ("g", i - 1, j)))
            opts.append((H[i][j - 1] - GAP, ("g", i, j - 1)))
            H[i][j], back[i][j] = max(opts, key=lambda o: o[0])
    best_end: dict[int, tuple[float, int, int]] = {}
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            sc, sent = H[i][j], tok_sent[j - 1]
            if sc > 0 and (sent not in best_end or sc > best_end[sent][0]):
                best_end[sent] = (sc, i, j)
    out, seen = [], set()
    for _, i, j in sorted(best_end.values(), reverse=True):
        pairs = []
        while i > 0 and j > 0 and H[i][j] > 0 and back[i][j] is not None:
            kind, pi, pj = back[i][j]
            if kind == "m":
                pairs.append((i - 1, j - 1))
            elif kind == "m2":
                pairs += [(i - 1, j - 1), (i - 2, j - 1)]
            elif kind == "m3":
                pairs += [(i - 1, j - 1), (i - 1, j - 2)]
            i, j = pi, pj
        key = tuple(sorted(pairs))
        if key and key not in seen:
            seen.add(key)
            out.append(sorted(pairs))
    return out


@dataclass
class Selection:
    units: list[Unit]
    chosen: list[int]          # indices into units, in order
    retakes: int               # runs of dropped units that were takes of script lines


def select_takes(words: list[Word], script_words: list[str],
                 triggers: set[str] = frozenset(), quiet: bool = False) -> Selection:
    stoks = tokens_with_owner(script_words)
    S = [t for t, _ in stoks]
    word_sent = script_sentences(script_words, triggers)
    tok_sent = [word_sent[o] for _, o in stoks]

    # The script's one-word sentences ("No.", "Zero."): said alone between pauses they are a
    # whole line, though filler weight (0.3) keeps them under MIN_MATCH. DJI_0350 (21 Oct 2026)
    # lost "Is it perfect? No." to that.
    lone = {}
    for k, (tok, owner) in enumerate(stoks):
        before = script_words[owner - 1] if owner else "."
        if ends_sentence(script_words[owner]) and ends_sentence(before) and \
                sum(1 for _, o in stoks if o == owner) == 1:
            lone.setdefault(tok, []).append(k)

    units = [Unit(ws) for ws in split_units(words, UNIT_PAUSE, triggers)]
    for u in units:
        utoks = tokens_with_owner([words[i].text for i in u.words])
        T = [t for t, _ in utoks]
        if not T:
            continue
        if len(T) == 1 and T[0] in lone:
            for k in lone[T[0]]:
                u.places.append(Place(k, k, tok_sent[k], tok_sent[k], {tok_sent[k]: weight(T[0])}))
        own = sum(weight(t) for t in T)
        for pairs in local_alignments(T, S, tok_sent):
            s_idx = sorted({s for _, s in pairs})
            got = sum(weight(S[s]) for s in s_idx)
            if got < MIN_MATCH or got < MIN_SHARE * own:
                continue
            while len(s_idx) > 1 and weight(S[s_idx[0]]) < 1:   # spans start and end on
                s_idx.pop(0)                                   # content words, so filler
            while len(s_idx) > 1 and weight(S[s_idx[-1]]) < 1:  # at the edges cannot bleed
                s_idx.pop()                                    # into the next sentence
            cover: dict[int, float] = {}
            for s in s_idx:
                cover[tok_sent[s]] = cover.get(tok_sent[s], 0.0) + weight(S[s])
            u.places.append(Place(s_idx[0], s_idx[-1], tok_sent[s_idx[0]], tok_sent[s_idx[-1]], cover))

    best_cover: dict[int, float] = {}
    for u in units:
        for p in u.places:
            for s, c in p.cover.items():
                best_cover[s] = max(best_cover.get(s, 0.0), c)

    def credit(p: Place) -> float:
        return sum(best_cover[s] if c >= COMPLETE * best_cover[s] else c for s, c in p.cover.items())

    # Longest path through (unit, placement) nodes, forward through the script.
    # A sentence may continue into the very next candidate unit (a line said in
    # two breaths); otherwise each node must start on a later sentence.
    cands = [k for k, u in enumerate(units) if u.candidate]
    rank = {k: n for n, k in enumerate(cands)}
    nodes = [(k, p) for k in cands for p in units[k].places]
    score: list[float] = []
    prev: list[int | None] = []
    for a, (k, p) in enumerate(nodes):
        # per sentence covered: two lines said in one breath would lose the tie to an earlier
        # take that had a pause between them (005, 1 Nov 2026, "Whole sentences..." + "That's...")
        here = credit(p) + LATE * k * len(p.cover)
        best, arg = here, None
        for b in range(a):
            k2, p2 = nodes[b]
            if k2 >= k:
                continue
            onward = p.sent_lo > p2.sent_hi
            continues = p.sent_lo == p2.sent_hi and rank[k] == rank[k2] + 1 and p.lo > p2.hi
            if (onward or continues) and score[b] + here > best:
                best, arg = score[b] + here, b
        score.append(best)
        prev.append(arg)
    chosen: list[int] = []
    if nodes:
        a = max(range(len(nodes)), key=lambda x: (score[x], nodes[x][0]))
        while a is not None:
            k, p = nodes[a]
            units[k].chosen = p
            chosen.append(k)
            a = prev[a]
        chosen.reverse()

    keep = set(chosen)
    # A complete take of a line that is not in the edit while an earlier take of it is: line A said
    # again after line B (cuts follow the recording, so it cannot go back in front of B), or a later
    # full retake losing to an earlier take said in two breaths (003, 23 Oct 2026: "3." then the
    # rest, which George had approved). Dropped silently before audit codex-005 (20 Oct 2026); a
    # pickup file is the way to use it. `quiet` is for pickups.py's placement pass, so a pickup run
    # does not report the main take's drops twice (once on each timeline).
    kept_at: dict[int, int] = {}
    for k in chosen:
        for s in units[k].chosen.cover:
            kept_at[s] = max(kept_at.get(s, -1), k)
    for k in cands:
        if not quiet and k not in keep and any(c >= COMPLETE * best_cover[s] and kept_at.get(s, -1) < k
                                 for p in units[k].places for s, c in p.cover.items()):
            said = " ".join(words[i].text for i in units[k].words)
            warn(f"the complete take at {words[units[k].words[0]].start:.1f} s (\"{said[:40]}\") is not in "
                 f"the edit: an earlier take of that line is. If the later one is better, film the line "
                 f"as a pickup (a second --video)")

    retakes, in_run = 0, False
    for k in cands:
        if k in keep:
            in_run = False
        elif not in_run:
            retakes, in_run = retakes + 1, True
    return Selection(units, chosen, retakes)
