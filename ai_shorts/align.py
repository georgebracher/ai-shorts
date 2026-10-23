"""Stage 3a (second half): line the kept words up with the script, token by token.

Walk the transcript tokens with a pointer into the script. Normally each token
matches the next script token. When the speaker jumps BACK in the script (a
restart after a flub), every kept token since the restart point is an earlier
take and is dropped, so only the last take survives. Jumps forward are allowed
(whisper missed a word, or a line was skipped). Tokens matching nothing are
ad-libs or fillers: kept, unless they sit inside an abandoned take or are
leading/trailing chatter separated from the script by a pause.
"""
from dataclasses import dataclass

from .text import same, same_join, tokens_with_owner
from .takes import script_sentences, select_takes
from .transcribe import Word

LOOKBACK = 80    # script tokens to search back for a restart
LOOKAHEAD = 8    # script tokens to search ahead for a skip
NEED = 3         # consecutive matches that confirm a jump


def match_at(T: list[str], S: list[str], t: int, j: int) -> tuple[int, int] | None:
    """Does transcript token t match script token j? Returns tokens consumed (dt, ds).

    Also matches split/merged words: "right"+"move" == "rightmove" and back.
    """
    if t >= len(T) or j >= len(S):
        return None
    if same(T[t], S[j]):
        return 1, 1
    # a split word ("right"+"move"), but never when the second half already is the word:
    # "it"+"played" passed for "played" and the caption lost "it" (DJI_0350, 21 Oct 2026)
    if t + 1 < len(T) and same_join(T[t] + T[t + 1], S[j]) and not same(T[t + 1], S[j]):
        return 2, 1
    if j + 1 < len(S) and same_join(T[t], S[j] + S[j + 1]):
        return 1, 2
    return None


def run_score(T, S, t, j, n=NEED + 1) -> int:
    score = 0
    while score < n:
        m = match_at(T, S, t, j)
        if not m:
            break
        t, j, score = t + m[0], j + m[1], score + 1
    return score


@dataclass
class Alignment:
    script_idx: list[int | None]   # per transcript token
    dropped: list[bool]            # per transcript token
    merges: list[tuple[int, int]]  # (t, t+1) token pairs that formed one script word
    restarts: int


def align_tokens(T: list[str], S: list[str], unit_of: list[int] | None = None,
                 unit_start: dict[int, int] | None = None) -> Alignment:
    """unit_of: the unit each token belongs to. A restart only drops tokens of its
    own unit; picking between whole takes is takes.select_takes' job.
    unit_start: script token where each kept unit's sentence begins. The pointer moves
    up to it at the unit's first token, so a paraphrased line cannot strand it: on
    DJI_0349 (21 Oct 2026) "Write the questions before." lost the pointer, LOOKAHEAD
    never reached "Two.", and every later line was cut as trailing chatter."""
    n = len(T)
    unit_of = unit_of or [0] * n
    unit_start = unit_start or {}
    sidx: list[int | None] = [None] * n
    dropped = [False] * n
    merges, restarts = [], 0
    pos = t = 0
    while t < n:
        if (t == 0 or unit_of[t] != unit_of[t - 1]) and unit_of[t] in unit_start:
            # land on the unit's first word nearest its sentence; failing that, within
            # LOOKAHEAD of it, since the selector anchors on the first content word and a
            # lead-in ("My" before "site? Zero.") must still be able to match
            a = unit_start[unit_of[t]]
            lo = max(pos, a - LOOKAHEAD)
            hits = [j for j in range(lo, min(len(S), a + LOOKAHEAD + 1)) if match_at(T, S, t, j)]
            pos = min(hits, key=lambda j: abs(j - a)) if hits else lo
        m = match_at(T, S, t, pos)
        if m:
            dt, ds = m
            for k in range(dt):
                sidx[t + k] = pos
            if dt == 2:
                merges.append((t, t + 1))
            t, pos = t + dt, pos + ds
            continue
        best = None
        left = sum(1 for k in range(t, n) if unit_of[k] == unit_of[t])  # tokens left in this unit
        for j in range(max(0, pos - LOOKBACK), min(len(S), pos + LOOKAHEAD + 1)):
            if j == pos:
                continue
            if j < pos:
                # A restart drops what came before it, so it must prove itself: NEED matches (fewer
                # only where the script itself ends), and enough speech left to re-cover what it
                # drops. A trailing echo ("...weekly reports today.") once erased the whole sentence.
                need = max(1, min(NEED, len(S) - j))
                if left + 1 < pos - j:
                    continue
            else:
                need = max(1, min(NEED, len(S) - j, n - t))
            sc = run_score(T, S, t, j)
            if sc >= need:
                key = (sc, -abs(j - pos), j > pos)
                if best is None or key > best[0]:
                    best = (key, j)
        if best is None:
            t += 1          # unmatched: ad-lib or filler
            continue
        j = best[1]
        if j < pos:
            first, k = None, t - 1
            while k >= 0 and unit_of[k] == unit_of[t] and \
                    (dropped[k] or sidx[k] is None or sidx[k] >= j):
                if sidx[k] is not None and not dropped[k]:
                    first = k
                k -= 1
            if first is not None:
                restarts += 1
                for k in range(first, t):
                    dropped[k] = True
        pos = j
    return Alignment(sidx, dropped, merges, restarts)


def apply_alignment(words: list[Word], script_words: list[str], max_pause: float = 0.6,
                    triggers: set[str] = frozenset()) -> tuple[list[Word], int]:
    """Pick one take per script line (takes.select_takes), then line the kept
    words up with the script token by token: drops restarts inside a unit,
    records script positions, rejoins split words. Returns (words, restarts)."""
    sel = select_takes(words, script_words, triggers)
    unit_of = [0] * len(words)
    for k, u in enumerate(sel.units):
        for i in u.words:
            unit_of[i] = k
    chosen = set(sel.chosen)
    for k, u in enumerate(sel.units):
        if k not in chosen:
            for i in u.words:
                words[i].kept = False

    kept = [i for i, w in enumerate(words) if w.kept]
    ktoks = tokens_with_owner([words[i].text for i in kept])
    ttoks = [(t, kept[o]) for t, o in ktoks]                     # owners as global indices
    stoks = tokens_with_owner(script_words)
    word_sent = script_sentences(script_words, triggers)
    sent_start: dict[int, int] = {}
    for si, (_, owner) in enumerate(stoks):
        sent_start.setdefault(word_sent[owner], si)
    unit_start = {k: sent_start[u.chosen.sent_lo] for k, u in enumerate(sel.units) if u.chosen}
    al = align_tokens([t for t, _ in ttoks], [s for s, _ in stoks],
                      [unit_of[wi] for _, wi in ttoks], unit_start)

    for (tok, wi), si, dr in zip(ttoks, al.script_idx, al.dropped):
        w = words[wi]
        if dr:
            w.kept = False
        if si is not None:
            w.script_lo = si if w.script_lo is None else min(w.script_lo, si)
            w.script_hi = si if w.script_hi is None else max(w.script_hi, si)

    # Whisper split one script word ("Rightmove" -> "right" "move"): rejoin it
    # with the script's spelling so the caption reads right.
    absorbed = set()
    for a, b in al.merges:
        wa, wb = ttoks[a][1], ttoks[b][1]
        if wa != wb and wb not in absorbed:
            script_word = script_words[stoks[al.script_idx[a]][1]]
            core = script_word.strip(".,;:!?\"'()")
            tail = words[wb].text[len(words[wb].text.rstrip(".,;:!?")):]
            words[wa].text = core + tail
            words[wa].end = words[wb].end
            words[wa].kept = words[wa].kept and words[wb].kept
            absorbed.add(wb)
    words = [w for i, w in enumerate(words) if i not in absorbed]

    drop_edge_chatter(words, max_pause)
    return words, sel.retakes + al.restarts


def drop_edge_chatter(words: list[Word], max_pause: float) -> None:
    """Unmatched words before the first / after the last script word, cut off
    by a pause ("okay, rolling", "was that alright?"), are not part of the video."""
    matched = [i for i, w in enumerate(words) if w.kept and w.script_lo is not None]
    if not matched:
        return
    first, last = matched[0], matched[-1]
    for i in range(first - 1, -1, -1):
        if words[i + 1].start - words[i].end > max_pause:
            for k in range(i + 1):
                words[k].kept = False
            break
    for i in range(last + 1, len(words)):
        if words[i].start - words[i - 1].end > max_pause:
            for k in range(i, len(words)):
                words[k].kept = False
            break
