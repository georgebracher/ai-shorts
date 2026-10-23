"""Remote render settings come from a private file outside the repo, never from the code."""
import pytest

from ai_shorts.remote import R2, load_settings, win


def test_settings_load_with_r2(tmp_path):
    p = tmp_path / "remote.toml"
    p.write_text('host = "box"\ncode = "C:/c"\nraw = "D:/r"\nout = "D:/o"\n'
                 '[r2]\naccount = "a"\nbucket = "b"\nkey_id = "echo k"\nsecret = "echo s"\nenv_file = "C:/c/.r2"\n')
    s = load_settings(p)
    assert (s.host, s.code, s.df_python, s.busy) == ("box", "C:/c", "", "")
    assert s.r2 == R2("a", "b", "echo k", "echo s", "C:/c/.r2")


def test_settings_without_r2(tmp_path):
    p = tmp_path / "remote.toml"
    p.write_text('host = "box"\ncode = "C:/c"\nraw = "D:/r"\nout = "D:/o"\n')
    assert load_settings(p).r2 is None


def test_missing_settings_say_where(tmp_path):
    with pytest.raises(SystemExit, match="no settings at"):
        load_settings(tmp_path / "nope.toml")


def test_win_paths():
    assert win("D:/ai-shorts/raw/a.MP4") == r"D:\ai-shorts\raw\a.MP4"
