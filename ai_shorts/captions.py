"""Caption words: what George SAID, with names and numbers spelled right.

Captions follow the kept transcript, because he paraphrases ("Mine cost me $7",
"Please don't DM me") and the captions must match his voice. Whisper does mishear
names and numbers, so two narrow fixes use the script:

  names    a heard word, or two adjacent ones, that closely matches a name in the
           script takes the script's spelling: "write move" / "right move" /
           "WriteMove's" -> "Rightmove", "chat GPT" -> "ChatGPT".
  numbers  a heard numeral that lines up with a script number but says a
           different value takes the script's value ("822" where the script has
           "a hundred and twenty-two" -> "122"). Spelled-out numbers with
           "hundred"/"thousand" become numerals.
  misheard an ordinary word the alignment could not match, straight after a matched
           word, that sounds like one of the next two script words ("gets sated." for
           "gets cited.", "My cite" for "My new site"). A real paraphrase ("all" for
           "every") does not sound alike and keeps what he said.

Nothing is ever added that whisper did not hear.
"""
from dataclasses import replace
import os
import re
from pathlib import Path
from difflib import SequenceMatcher
from functools import lru_cache

from .config import PROJECT_ROOT
from .text import ONES, TENS, ends_sentence, normalize_word, sound_key, tokens_with_owner
from .transcribe import Word

NAME_MATCH = 0.8      # similarity for a heard word to take a script name's spelling
SOUND_MATCH = 0.75    # similarity of spoken forms for a misheard word to take the script's


def _letters(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _trailing_punct(text: str) -> str:
    return text[len(text.rstrip(".,;:!?")):]


WORD_LISTS = [Path(p) for p in [os.environ.get("AI_SHORTS_WORDS", "")] if p] + [
    PROJECT_ROOT / "data" / "words.txt.gz",   # a copy of web2 kept beside the code for machines without one
    Path("/usr/share/dict/web2"), Path("/usr/share/dict/words")]


@lru_cache(maxsize=1)
def _dictionary() -> frozenset[str]:
    """Ordinary English words, lowercased: Webster's Second International (public domain; every Mac
    has it as /usr/share/dict/web2). The first of WORD_LISTS that exists, plain or gzipped. Without
    one, a capitalised sentence opener reads as a name: on a machine with no /usr/share/dict, "Check"
    opening a step did, and "checked" was captioned "Check" (21 Oct 2026)."""
    import gzip
    for path in WORD_LISTS:
        if path.is_file():
            with (gzip.open(path, "rt", encoding="utf-8") if path.suffix == ".gz"
                  else open(path, encoding="utf-8")) as f:
                return frozenset(w.strip().lower() for w in f)
    print("[ai-shorts] WARNING: no word list (set AI_SHORTS_WORDS, see the README); "
          "capitalised sentence openers will read as names", flush=True)
    return frozenset()


def script_names(script_words: list[str]) -> dict[str, str]:
    """Names in the script: mixed-case words (ChatGPT), all-caps (AI, DM), words
    capitalised somewhere other than the start of a sentence (Claude), or a
    capitalised sentence opener that is not an ordinary dictionary word
    (Rightmove, but not Write). Maps the bare lowercase form to the spelling."""
    names: dict[str, str] = {}
    prev = "."
    for w in script_words:
        core = w.strip(".,;:!?\"'()")
        bare = _letters(core.removesuffix("'s"))
        mixed = any(c.isupper() for c in core[1:])
        opener = ends_sentence(prev)
        capital = core[:1].isupper() and not core.startswith("I'") and \
            (not opener or (len(bare) >= 5 and bare not in _dictionary()))
        if bare and len(bare) >= 2 and (mixed or capital) and core != "I":
            names[bare] = core.removesuffix("'s")
        prev = w
    return names


def _name_for(bare: str, names: dict[str, str]) -> str | None:
    """Script spelling of the name this heard form is, if any: same letters, close
    spelling, or the same sound ("write move" ~ "Rightmove")."""
    if bare in names:
        return names[bare]
    if len(bare) < 5:
        return None
    for n, spelling in names.items():
        if len(n) < 5:
            continue
        key = sound_key(n)
        if SequenceMatcher(None, bare, n).ratio() >= NAME_MATCH or (len(key) >= 4 and sound_key(bare) == key):
            return spelling
    return None


def _as_scripted(words: list[Word], script_words: list[str], names: dict[str, str]) -> list[tuple[bool, bool]]:
    """Per heard word: (lined up with a script word of the same letters, or unaligned but an
    ordinary word the script uses). Such a word is what he said, not a misheard name."""
    stoks = tokens_with_owner(script_words)
    ordinary = {_letters(w) for w in script_words} - set(names)
    out = []
    for w in words:
        said = _letters(w.text)
        if w.script_lo is not None and w.script_hi is not None:
            owners = sorted({stoks[k][1] for k in range(w.script_lo, w.script_hi + 1)})
            out.append((said == _letters("".join(script_words[o] for o in owners)), False))
        else:
            out.append((False, said in ordinary))
    return out


def fix_names(words: list[Word], names: dict[str, str], script_words: list[str] | None = None) -> list[Word]:
    # A heard word the script itself says keeps its spelling: "clause" is close enough to "Claude",
    # and "explain this clause." was captioned "explain this Claude." (audit codex-003, 20 Oct 2026)
    scripted = _as_scripted(words, script_words, names) if script_words else [(False, False)] * len(words)
    out, i = [], 0
    while i < len(words):
        w = words[i]
        if i + 1 < len(words) and not ends_sentence(w.text) and _trailing_punct(w.text) == "" and \
                not (scripted[i][0] and scripted[i + 1][0]):
            pair = _letters(w.text) + _letters(words[i + 1].text.removesuffix("'s"))
            name = _name_for(pair, names)
            alone = _name_for(_letters(w.text), names) or \
                _name_for(_letters(words[i + 1].text.rstrip(".,;:!?").removesuffix("'s")), names)
            if name and not alone:          # "write move", but not "and Perplexity"
                nxt = words[i + 1].text
                tail = ("'s" if nxt.rstrip(".,;:!?").endswith("'s") else "") + _trailing_punct(nxt)
                out.append(Word(name + tail, w.start, words[i + 1].end))
                i += 2
                continue
        core = w.text.rstrip(".,;:!?")
        possessive = core.endswith("'s")
        bare = _letters(core.removesuffix("'s"))
        name = _name_for(bare, names)
        if name and _letters(name) != bare and any(scripted[i]):
            name = None                     # a close spelling, but he said the script's own word
        if name:
            out.append(Word(name + ("'s" if possessive else "") + _trailing_punct(w.text), w.start, w.end))
        else:
            out.append(Word(w.text, w.start, w.end))
        i += 1
    return out


NUMBER_WORDS = {w: i for i, w in enumerate(ONES)} | {w: 10 * i for i, w in enumerate(TENS) if w != "_"}


def _num_parts(text: str) -> list[str] | None:
    """'twenty-two,' -> ['twenty', 'two']; None if not a number word."""
    parts = re.sub(r"[^a-z-]", "", text.lower()).split("-")
    ok = all(p in NUMBER_WORDS or p in ("hundred", "thousand", "and", "a") for p in parts)
    return parts if parts and parts[0] and ok else None


def _parse(parts: list[str]) -> int | None:
    """None unless the words build one number: "fifty-fifty" is two fifties, not 100
    (DJI_0353, 21 Oct 2026, captioned "100-100")."""
    total, cur, last = 0, 0, None        # last: the size of the previous number word
    for p in parts:
        if p == "and":
            continue
        if p == "a":
            cur = cur or 1
        elif p == "hundred":
            cur, last = (cur or 1) * 100, None
        elif p == "thousand":
            total, cur, last = total + (cur or 1) * 1000, 0, None
        elif p in NUMBER_WORDS:
            n = NUMBER_WORDS[p]
            if last is not None and (last < 10 or n >= 10):   # only "twenty" + "two" chains
                return None
            cur, last = cur + n, n
        else:
            return None
    return total + cur


def _script_number_at(script_words: list[str], idx: int) -> int | None:
    """Value of the spelled-out number run in the script around word idx."""
    if _num_parts(script_words[idx]) is None:
        return None
    a = idx
    while a > 0 and _num_parts(script_words[a - 1]) is not None and not _trailing_punct(script_words[a - 1]):
        a -= 1
    b = idx
    while b + 1 < len(script_words) and _num_parts(script_words[b + 1]) is not None \
            and not _trailing_punct(script_words[b]):
        b += 1
    parts = [p for w in script_words[a:b + 1] for p in _num_parts(w)]
    return _parse(parts)


def fix_numbers(words: list[Word], script_words: list[str]) -> list[Word]:
    """A heard numeral mostly lined up with a script number but with another value
    (whisper's "822" for "a hundred and twenty-two") takes the script's value."""
    wt = tokens_with_owner([w.text for w in words])
    st = tokens_with_owner(script_words)
    matched: dict[int, list[int]] = {}
    sm = SequenceMatcher(None, [t for t, _ in wt], [t for t, _ in st], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                matched.setdefault(wt[i1 + k][1], []).append(st[j1 + k][1])
    out = []
    for wi, w in enumerate(words):
        m = re.fullmatch(r"(\D*?)(\d+(?:,\d{3})*)(\D*)", w.text)
        hits = matched.get(wi, [])
        n_tok = len(normalize_word(w.text))
        if m and hits and len(hits) >= 0.6 * n_tok:
            value = _script_number_at(script_words, hits[-1])
            heard = int(m.group(2).replace(",", ""))
            if value is not None and value != heard:
                out.append(Word(f"{m.group(1)}{value}{m.group(3)}", w.start, w.end))
                continue
        out.append(w)
    return out


def numerals(caps: list[Word]) -> list[Word]:
    """Turn spelled-out runs with a 'hundred'/'thousand' in them into digits:
    'a hundred and twenty-two,' -> '122,'. Single words ('four') are left alone."""
    out, i = [], 0
    while i < len(caps):
        j, parts = i, []
        while j < len(caps) and (p := _num_parts(caps[j].text)) is not None:
            parts += p
            j += 1
            if _trailing_punct(caps[j - 1].text):
                break
        while parts and parts[-1] in ("and", "a"):     # "... and" belongs to the sentence
            parts.pop()
            j -= 1
        if j - i >= 2 and ("hundred" in parts or "thousand" in parts):
            value = _parse(parts)
            if value is not None:
                out.append(Word(f"{value}{_trailing_punct(caps[j - 1].text)}",
                                caps[i].start, caps[j - 1].end))
                i = j
                continue
        out.append(caps[i])
        i += 1
    return out


def _spoken(text: str) -> str:
    """Rough spoken form: soft c reads as s, ph as f, ck as k, aw as au, a final silent e
    and the e of -ed drop ("cited" ~ "sited", "clawed" ~ "Claude")."""
    s = re.sub(r"c(?=[eiy])", "s", _letters(text))
    s = s.replace("ph", "f").replace("ck", "k").replace("aw", "au")
    s = re.sub(r"ed$", "d", s)
    return re.sub(r"(?<=[^aeiou])e$", "", s)


def fix_misheard(words: list[Word], script_words: list[str]) -> list[Word]:
    """DJI_0349 (21 Oct 2026) captioned "COUNT WHO GETS SATED": whisper's word, because only
    names and numbers took the script's spelling."""
    stoks = tokens_with_owner(script_words)
    out = list(words)
    for i, w in enumerate(words):        # matched, same letters, other spelling: "clip's" -> "clips"
        if w.script_lo is not None and w.script_lo == w.script_hi:
            core = script_words[stoks[w.script_lo][1]].strip(".,;:!?\"'()")
            if _letters(core) == _letters(w.text) and core.lower() != w.text.rstrip(".,;:!?").lower() and \
                    sum(1 for _, o in stoks if o == stoks[w.script_lo][1]) == 1:
                out[i] = replace(w, text=core + _trailing_punct(w.text))
    # Each run of unmatched words after a matched one, against the script words up to the next
    # match (or two past the run's length when there is none), in order: "Send him only the
    # clip's clawed rates." for "Only send him the clips Claude rates." left "the clip's clawed"
    # unmatched in one run (DJI_0353, 21 Oct 2026).
    i = 1
    while i < len(words):
        if words[i].script_lo is not None or words[i - 1].script_hi is None:
            i += 1
            continue
        run_end = i
        while run_end < len(words) and words[run_end].script_lo is None:
            run_end += 1
        lo = words[i - 1].script_hi + 1
        hi = words[run_end].script_lo if run_end < len(words) else lo + (run_end - i) + 2
        hi = min(hi, len(stoks), lo + (run_end - i) + 6)      # a short gap, never a jump
        j0 = lo
        for k in range(i, run_end):
            said, best = _spoken(words[k].text), None
            for j in range(j0, hi):
                owner = stoks[j][1]
                if sum(1 for _, o in stoks if o == owner) != 1:
                    continue
                # about the same length ("right" is not "Rightmove": names pair up in fix_names),
                # not the same word with an ending ("checked" is not "Check", 003 on the tower;
                # "sighted" still becomes "cited", 001), and never a script contraction over what
                # he said ("cannot" stays "cannot")
                said_l, meant_l = _letters(words[k].text), _letters(script_words[owner])
                if "'" in script_words[owner] or abs(len(meant_l) - len(said_l)) > 2 or \
                        (said_l != meant_l and (said_l.startswith(meant_l) or meant_l.startswith(said_l))):
                    continue
                score = SequenceMatcher(None, said, _spoken(script_words[owner])).ratio()
                if len(_letters(script_words[owner])) >= 4 and score >= SOUND_MATCH and \
                        (best is None or score > best[0]):
                    best = (score, owner, j)
            if best:
                core = script_words[best[1]].strip(".,;:!?\"'()")
                if core.lower() != words[k].text.rstrip(".,;:!?").lower():
                    out[k] = replace(words[k], text=core + _trailing_punct(words[k].text))
                j0 = best[2] + 1
        i = run_end
    return out


def tidy(caps: list[Word]) -> list[Word]:
    """Whisper's "50 -50" rejoins as "50-50"; a step number said as its own sentence is a
    digit, so "Two." does not sit between "1." and "3." (DJI_0350, 21 Oct 2026)."""
    out: list[Word] = []
    for w in caps:
        if out and re.match(r"^-\d", w.text):
            out[-1] = Word(out[-1].text + w.text, out[-1].start, w.end)
            continue
        bare = _letters(w.text)
        alone = (not out or ends_sentence(out[-1].text)) and ends_sentence(w.text)
        if alone and bare in NUMBER_WORDS and 0 < NUMBER_WORDS[bare] < 10:
            w = Word(f"{NUMBER_WORDS[bare]}{_trailing_punct(w.text)}", w.start, w.end)
        out.append(w)
    return out


def caption_words(words: list[Word], script_words: list[str]) -> list[Word]:
    """The words to caption, in time order, on the same timeline as `words`."""
    caps = fix_misheard(words, script_words)
    caps = fix_names(caps, script_names(script_words), script_words)
    caps = fix_numbers(caps, script_words)
    return tidy(numerals(caps))
