"""--framing on the CLI, and the fill used when George's picture is narrower than the window."""
import numpy as np
from PIL import Image

from ai_shorts.__main__ import build_parser
from ai_shorts.config import Config
from ai_shorts.layout import fit_video
from ai_shorts.render import FEATHER, covers_window, video_chain, write_fill_mask
from ai_shorts.media import SourceInfo
from ai_shorts.trim import Segment

CFG = Config()
FACE = (0.361, 0.2717, 0.6418, 0.5199)        # George's DJI take
SRC = SourceInfo(189.3, 1728, 3072, 59.94, True, False)


def test_cli_framing_flag():
    p = build_parser()
    assert p.parse_args(["render", "--video", "a", "--script", "b"]).framing is None   # config default
    assert p.parse_args(["render", "--video", "a", "--script", "b", "--framing", "wide"]).framing == "wide"


def test_tight_keeps_the_v8_graph():
    fit = fit_video(CFG, 1728, 3072, FACE, "tight")
    assert covers_window(CFG, fit)
    graph = video_chain(CFG, [Segment(1, 2)], SRC, fit)
    assert "fillborders" not in graph and "[2:v]" not in graph


def test_medium_extends_the_picture_and_feathers_the_seam(tmp_path):
    fit = fit_video(CFG, 1728, 3072, FACE, "medium")
    assert not covers_window(CFG, fit)
    graph = video_chain(CFG, [Segment(1, 2)], SRC, fit)
    assert "fillborders" in graph and "mode=smear" in graph and "alphamerge" in graph
    mask = np.asarray(Image.open(write_fill_mask(CFG, fit, tmp_path / "m.png")))
    assert mask.shape == (fit.box_h, CFG.width)
    mid = fit.place_y + fit.crop_h // 2
    assert mask[mid, 540] == 255                                     # George: fully sharp
    assert mask[mid, fit.place_x - 1] == 0                           # beyond his picture: fill
    assert 0 < mask[mid, fit.place_x + FEATHER // 2] < 255           # the seam blends
    assert mask[mid, fit.place_x + FEATHER + 2] == 255


def test_grade_only_touches_the_picture_and_is_off_by_default():
    from ai_shorts.config import GRADES
    fit = fit_video(CFG, 1728, 3072, FACE, "tight")
    assert "eq=" not in video_chain(CFG, [Segment(1, 2)], SRC, fit)
    graded = Config(grade="medium")
    graph = video_chain(graded, [Segment(1, 2)], SRC, fit)
    assert GRADES["medium"] in graph and graph.index("eq=") < graph.index("[win]")
    assert build_parser().parse_args(["render", "--video", "a", "--script", "b", "--grade", "medium"]).grade == "medium"


def test_cleaned_sound_is_cut_like_the_source():
    from ai_shorts.render import audio_chain
    segs = [Segment(1, 2), Segment(3, 4)]
    assert audio_chain(segs, "anull").startswith("[0:a]asplit=2")
    assert audio_chain(segs, "anull", "3:a").startswith("[3:a]asplit=2")
    assert "atrim=start=3.0000:end=4.0000" in audio_chain(segs, "anull", "3:a")
