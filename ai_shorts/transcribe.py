"""Stage 2: word-timestamped transcript, cached in the work dir: mlx_whisper on the Mac,
OpenAI whisper on the tower's GPU (the same model and decoding, the same JSON shape)."""
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import MLX_WHISPER
from .media import run
from .text import normalize_word


@dataclass
class Word:
    text: str
    start: float
    end: float
    kept: bool = True
    script_lo: int | None = None   # span of script tokens this word matched
    script_hi: int | None = None
    prob: float = 1.0              # whisper's confidence in the word


# Whisper text that is never speech. v1 prompted whisper with "Glossary: <names>"
# and it echoed "Glossary &" into the pauses, which kept them from being cut and
# put "GLOSSARY" in the captions. The prompt is gone (captions take spelling from
# the script now); this guard cleans transcripts made before that.
PROMPT_ECHO = {"glossary"}


def drop_noise(words: list[Word], script_words: list[str]) -> list[Word]:
    """Remove punctuation-only words ("&") and prompt echoes not in the script."""
    in_script = {t for w in script_words for t in normalize_word(w)}
    out = []
    for w in words:
        toks = normalize_word(w.text)
        if not toks or (set(toks) <= PROMPT_ECHO and not set(toks) & in_script):
            continue
        out.append(w)
    return out


def transcribe(wav: Path, work: Path, model: str, language: str = "en",
               prompt: str = "") -> list[Word]:
    out_json = work / "transcript.json"
    stamp = work / "transcript.key"
    # Each 30 s window is heard on its own. Carrying the last window's text forward let a run of
    # repeated step numbers ("3. 3. 3.", "4. 4.") turn into a loop that swallowed the closing lines
    # (DJI_0349, 21 Oct 2026); heard fresh, the same audio came back word for word.
    mlx = Path(MLX_WHISPER).exists() or bool(shutil.which(MLX_WHISPER))
    key = {"model": model, "prompt": prompt, "language": language, "context": False,
           "wav_size": wav.stat().st_size}
    if not mlx:              # the tower's transcripts say which whisper made them (the Mac's keys stay as they were)
        key["backend"] = "openai-whisper"
    key = json.dumps(key)
    if not (out_json.exists() and stamp.exists() and stamp.read_text() == key):
        # the old key goes first: a run stopped part way must not leave this transcript under it
        stamp.unlink(missing_ok=True)
        # whisper writes under this run's own name (no dot: mlx_whisper swaps the suffix for .json),
        # then it is renamed: another render of the take may be reading transcript.json meanwhile
        tmp = work / f"transcript-{os.getpid()}.json"
        try:
            if not mlx:
                _openai_whisper(wav, tmp, language, prompt)
            else:
                cmd = [MLX_WHISPER, "--model", model, "--language", language,
                       "--word-timestamps", "True", "--condition-on-previous-text", "False",
                       "--output-format", "json",
                       "--output-dir", str(work), "--output-name", tmp.stem,
                       "--verbose", "False"]
                if prompt:
                    cmd += ["--initial-prompt", prompt]
                run(cmd + [str(wav)], timeout=3600)
            os.replace(tmp, out_json)
        finally:
            tmp.unlink(missing_ok=True)
        stamp.write_text(key)
    return load_words(out_json)



_ow_model = None


def _openai_whisper(wav: Path, out_json: Path, language: str, prompt: str) -> None:
    """The tower's backend: OpenAI's own whisper on CUDA, the code mlx_whisper is ported from, so
    the same decoding (greedy, temperature fallback, DTW word times) and the same JSON as the Mac.
    faster-whisper was tried first (21 Oct 2026): it dropped punctuation and cue words ("4.", "Count")
    that every threshold here was tuned with, and its own decoder broke on the tower's PyAV."""
    global _ow_model
    if _ow_model is None:
        import whisper
        _ow_model = whisper.load_model("turbo", device="cuda")
    from .audio import load_wav
    result = _ow_model.transcribe(load_wav(wav), language=language, word_timestamps=True,
                                  condition_on_previous_text=False, initial_prompt=prompt or None,
                                  fp16=True, verbose=None)
    segs = [{"start": s["start"], "end": s["end"], "text": s["text"],
             "words": [{"word": w["word"], "start": w["start"], "end": w["end"],
                        "probability": w["probability"]} for w in s.get("words", [])]}
            for s in result["segments"]]
    out_json.write_text(json.dumps({"text": result["text"], "segments": segs}))

def load_words(path: Path) -> list[Word]:
    data = json.loads(Path(path).read_text())
    words = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            text = w["word"].strip()
            if text:
                words.append(Word(text, float(w["start"]), float(w["end"]),
                                  prob=float(w.get("probability", 1.0))))
    return words
