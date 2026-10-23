from ai_shorts.spec import load_spec
from ai_shorts.timeline import WEAK, chunk_captions, display_word
from conftest import SCRIPT, words_from


def texts(chunks):
    return [" ".join(w.text for w in c.words) for c in chunks]


def test_chunks_cover_every_word_in_order():
    words = words_from(load_spec(SCRIPT).body)
    chunks = chunk_captions(words)
    assert [w for c in chunks for w in c.words] == words


def test_chunk_sizes_and_lone_words():
    chunks = chunk_captions(words_from(load_spec(SCRIPT).body))
    for c in chunks:
        assert 1 <= len(c.words) <= 4
        if len(c.words) == 1:   # only a whole short sentence stands alone ("One.")
            assert c.words[0].text.endswith((".", "?", "!"))
    assert "One." in texts(chunks)


def test_no_chunk_ends_on_a_weak_word():
    chunks = chunk_captions(words_from(load_spec(SCRIPT).body))
    for c in chunks[:-1]:
        last = c.words[-1].text.lower().strip(",.;:")
        assert last not in WEAK or c.words[-1].text[-1] in ".?!,", texts([c])


def test_sentence_end_breaks_chunk():
    assert texts(chunk_captions(words_from("Two hundred answers. Rightmove got cited."))) == [
        "Two hundred answers.", "Rightmove got cited."]


def test_pause_breaks_chunk():
    assert texts(chunk_captions(words_from("my new | site is live"))) == ["my new", "site is live"]


def test_five_words_never_split_four_plus_one():
    sizes = [len(c.words) for c in chunk_captions(words_from("count who gets cited today"))]
    assert 1 not in sizes


def test_display_word():
    assert display_word("goalposts,") == "GOALPOSTS"
    assert display_word("website?") == "WEBSITE?"


def test_a_word_said_as_scripted_is_never_respelled_as_a_name():
    # audit codex-003 (20 Oct 2026): "clause" is close enough to "Claude" to take its spelling, so
    # a correct "explain this clause." was captioned "explain this Claude."
    from ai_shorts.align import apply_alignment
    from ai_shorts.captions import caption_words
    line = "Ask Claude to explain this clause."
    said = lambda ws: " ".join(w.text for w in ws)
    words, _ = apply_alignment(words_from(line), line.split())
    assert said(caption_words(words, line.split())) == line
    assert said(caption_words(words_from(line), line.split())) == line      # not aligned either
    # where the script has the name, the close spelling still becomes it
    words, _ = apply_alignment(words_from("Ask clause to explain this clause."), line.split())
    assert said(caption_words(words, line.split())) == line


def test_the_word_list_is_read_and_closed():
    # audit k3-012 (20 Oct 2026): the word list came from a bare open() left for the garbage
    # collector to close; it has been read under `with` since the list shipped (21 Oct 2026)
    import gc
    import warnings
    from ai_shorts.captions import _dictionary
    _dictionary.cache_clear()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        words = _dictionary()
        gc.collect()
    assert "check" in words
    assert not [w for w in caught if issubclass(w.category, ResourceWarning)]


def test_the_word_list_is_found_where_there_is_one(tmp_path, monkeypatch, capsys):
    """The list is not in the package (it stays out of the public repo): the first of WORD_LISTS
    that exists is used, plain or gzipped, and none at all warns instead of failing (23 Oct 2026)."""
    import gzip
    from ai_shorts import captions
    plain, packed = tmp_path / "words", tmp_path / "words.txt.gz"
    plain.write_text("Check\nwrite\n")
    packed.write_bytes(gzip.compress(b"move\n"))
    for lists, want in (([tmp_path / "none", plain, packed], {"check", "write"}), ([packed, plain], {"move"})):
        monkeypatch.setattr(captions, "WORD_LISTS", lists)
        captions._dictionary.cache_clear()
        assert captions._dictionary() == want
    monkeypatch.setattr(captions, "WORD_LISTS", [tmp_path / "none"])
    captions._dictionary.cache_clear()
    assert captions._dictionary() == frozenset() and "WARNING: no word list" in capsys.readouterr().out
    captions._dictionary.cache_clear()
