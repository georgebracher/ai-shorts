"""George's second take of 001 (21 Oct 2026, DJI landscape 4K): paraphrased lines, a 25 s pause
after step one, "3. 3. 3." and "4. 4." restarts. Two failures it caught: the token pointer lost
its place on a paraphrase and every line after step one was cut, and whisper (carrying context
between windows) looped "10. 10. 10." over the closing lines. The fixture is the transcript
heard window by window."""
from pathlib import Path

from ai_shorts.align import apply_alignment
from ai_shorts.spec import load_spec
from ai_shorts.transcribe import load_words

FIX = Path(__file__).parent / "fixtures"
SPEC = load_spec(FIX / "001-aeo-baseline-take2.md")


def kept_text():
    words, _ = apply_alignment(load_words(FIX / "DJI_0349-transcript.json"), SPEC.words)
    return " ".join(w.text for w in words if w.kept)


def test_every_line_survives_in_order():
    kept = kept_text()
    lines = ["I asked ChatGPT", "200 answers.", "1. Write the questions", "2. Ask all four",
             "3. Count who", "It cost me $7.", "4. Publish pages", "Will it work?", "please don't dm me"]
    at = [kept.find(line) for line in lines]
    assert all(i >= 0 for i in at), dict(zip(lines, at))
    assert at == sorted(at)


def test_last_take_of_each_line_wins():
    kept = kept_text()
    assert kept.count("I asked ChatGPT") == 1 and "Claude, Gemini and Perplexity" in kept
    assert kept.count("Publish pages") == 1 and "those exact questions" in kept
    assert "3. 3." not in kept and "4. 4." not in kept


def test_misheard_words_are_captioned_as_scripted():
    from ai_shorts.captions import caption_words
    words, _ = apply_alignment(load_words(FIX / "DJI_0349-transcript.json"), SPEC.words)
    caps = " ".join(c.text for c in caption_words([w for w in words if w.kept], SPEC.words))
    assert "My site, zero." in caps and "Count who gets cited." in caps
    assert "if AI will ever cite it." in caps          # the script really says "cite" here
