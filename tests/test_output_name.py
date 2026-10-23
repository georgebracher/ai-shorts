from ai_shorts.pipeline import next_version, render_name


def test_name_puts_what_differs_first():
    assert render_name("001-x", 4, "close") == "001-x v4 close - AI Shorts.mp4"
    assert render_name("001-x", 4) == "001-x v4 - AI Shorts.mp4"


def test_version_counts_review_and_archive_and_old_names(tmp_path):
    review, archive = tmp_path / "Downloads", tmp_path / "Downloads" / "AI Shorts"
    (archive / "001-x" / "old renders").mkdir(parents=True)
    assert next_version("001-x", review, archive) == 1
    (review / "001-x v3 close - AI Shorts.mp4").touch()
    (review / "002-y v9 close - AI Shorts.mp4").touch()                 # another video
    (review / "001-x v8 close contact sheet.png").touch()               # not a render
    assert next_version("001-x", review, archive) == 4
    (archive / "001-x" / "old renders" / "AI Shorts 001-x - v7 wide.mp4").touch()   # old naming
    assert next_version("001-x", review, archive) == 8


def test_debug_view_takes_no_version_number(tmp_path):
    # audit claude-009: a debug render with nothing rendered yet was "v1 safe-zones debug" and the
    # first real render became v2
    review, archive = tmp_path / "Downloads", tmp_path / "Downloads" / "AI Shorts"
    (archive / "001-x").mkdir(parents=True)
    (archive / "001-x" / "001-x v1 safe-zones debug - AI Shorts.mp4").touch()
    assert next_version("001-x", review, archive) == 1
    (review / "001-x v1 medium - AI Shorts.mp4").touch()
    (archive / "001-x" / "001-x v1 medium safe-zones debug - AI Shorts.mp4").touch()
    assert next_version("001-x", review, archive) == 2


def test_tests_never_read_the_real_downloads(tmp_path):
    # audit codex-010: the old helper always globbed ~/Downloads; now both folders are passed in
    assert next_version("zzz-not-a-video", tmp_path, tmp_path) == 1
