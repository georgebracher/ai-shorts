"""Automatic face framing: robust median over samples, and the static crop."""
import gzip
import io
import json
import os
from pathlib import Path

import numpy as np
import pytest

from ai_shorts import face
from ai_shorts.config import FRAMINGS, Config
from ai_shorts.face import FACE_H, detect, detect_face, face_fractions, robust_box, sample_times
from ai_shorts.layout import eye_target, face_target, fit_video, inside
from ai_shorts.trim import Segment

CFG = Config()
FIX = json.loads((Path(__file__).parent / "fixtures" / "DJI_0348-face.json").read_text())
# one still of George from the DJI_0348 take: grayscale, head and shoulders, 260x280
FACE_STILL = Path(__file__).parent / "fixtures" / "face-gray.npy.gz"
STILL_FACE = (136.5, 118.5, 123.0)          # Haar (centre x, centre y, side) found on it, in pixels
# the recording itself is not in the repo; point this at it to run the full sampling check
DJI_VIDEO = Path(os.environ.get("AI_SHORTS_DJI_0348", "")).expanduser()
WINDOW_H = CFG.seam - CFG.window_inset                      # 903 px of video window


def test_median_ignores_misses_and_outliers():
    face = (270.0, 380.0, 180.0)
    hits = [face, None, (272, 378, 182), (268, 383, 178), None,
            (90, 700, 60),                 # a false hit elsewhere in the frame
            (271, 381, 320),               # same place, wildly wrong size
            (269, 379, 181)]
    assert robust_box(hits) == pytest.approx((270.0, 380.0, 180.0), abs=1.5)


def test_too_few_agreeing_samples_means_no_face():
    assert robust_box([None] * 8 + [(270, 380, 180)] * 2) is None       # 2 hits of 10
    assert robust_box([(270, 380, 180), (90, 700, 60), (500, 100, 90), None, None]) is None


def test_haar_box_becomes_forehead_to_chin():
    l, t, r, b = face_fractions((270.0, 380.0, 180.0), 540, 960)
    assert (l + r) / 2 == pytest.approx(0.5) and (t + b) / 2 == pytest.approx(380 / 960)
    assert (b - t) * 960 == pytest.approx(FACE_H * 180)


def test_sample_times_cover_kept_ranges_about_once_a_second():
    times = sample_times([Segment(10.0, 13.0), Segment(20.0, 20.4)])
    assert times == [10.5, 11.5, 12.5, 20.2]
    many = sample_times([Segment(0.0, 500.0)])
    assert len(many) == 60 and many == sorted(many)


def check_crop(fit, framing=None):
    l, t, r, b = fit.face
    target = face_target(CFG, framing)
    assert abs((l + r) / 2 - 540) <= 2                         # centred on the frame
    assert b - t >= target * 0.97 or fit.scale == CFG.max_upscale
    assert inside(fit.face, CFG.info_rect)                     # inside the safe area
    assert t >= CFG.title_band[1]                              # below the title strip
    assert b <= CFG.seam - CFG.caption_half                    # above the captions
    assert t - CFG.headroom * (b - t) >= CFG.title_band[1]     # hair clears the title strip
    assert fit.scale <= CFG.max_upscale


def test_framing_presets():
    assert set(FRAMINGS) == {"tight", "close", "medium", "wide"} and CFG.framing == "medium"
    assert face_target(CFG, "close") == pytest.approx(0.47 * WINDOW_H)
    assert face_target(CFG, "medium") == pytest.approx(0.36 * WINDOW_H)
    assert face_target(CFG, "wide") == pytest.approx(0.28 * WINDOW_H)
    assert (face_target(CFG, "tight") > face_target(CFG, "close")
            > face_target(CFG, "medium") > face_target(CFG, "wide"))


def test_dji_tight_is_v8():
    fit = fit_video(CFG, *FIX["source"], tuple(FIX["face"]), "tight")
    check_crop(fit, "tight")
    assert round(fit.face[3] - fit.face[1]) == 527                 # v8's face height
    assert fit.crop_w == 1080 and fit.place_x == 0                  # fills the window
    old = fit_video(CFG, *FIX["source"])                           # v7: the iPhone box
    real_before = (FIX["face"][3] - FIX["face"][1]) * 3072 * old.scale
    assert real_before < 400


@pytest.mark.parametrize("framing,share", [("medium", 0.36), ("wide", 0.28)])
def test_dji_talking_head_framings(framing, share):
    fit = fit_video(CFG, *FIX["source"], tuple(FIX["face"]), framing)
    check_crop(fit, framing)
    l, t, r, b = fit.face
    h = b - t
    assert h / WINDOW_H == pytest.approx(share, abs=0.01)           # face share of the window
    eyes = t + CFG.eye_in_face * h
    assert eyes == pytest.approx(eye_target(CFG, framing), abs=3)   # a third down the window
    assert b + 0.55 * h <= CFG.seam                                 # shoulders in frame
    assert fit.scale < 1                                            # DJI: downscaled, sharp


@pytest.mark.parametrize("framing", ["tight", "medium", "wide"])
def test_small_face_in_low_res_source_is_not_upscaled_soft(framing):
    fit = fit_video(CFG, 720, 1280, (0.47, 0.40, 0.53, 0.44), framing)   # tiny, far away
    assert fit.scale == CFG.max_upscale
    check_crop(fit, framing)


@pytest.mark.parametrize("framing", ["tight", "medium", "wide"])
def test_landscape_source_crop_is_centred_on_the_face(framing):
    fit = fit_video(CFG, 1920, 1080, (0.30, 0.25, 0.42, 0.70), framing)  # face left of centre
    check_crop(fit, framing)


def face_still() -> np.ndarray:
    return np.load(io.BytesIO(gzip.decompress(FACE_STILL.read_bytes())), allow_pickle=False)


def test_haar_finds_a_real_face():
    gray = face_still()
    assert gray.shape == (280, 260) and gray.dtype == np.uint8
    hit = detect(gray)
    assert hit is not None
    side = STILL_FACE[2]
    assert hit == pytest.approx(STILL_FACE, abs=0.1 * side)


def test_detect_face_on_real_frames_without_footage(tmp_path, monkeypatch):
    # every sampled frame is the still, so the whole path runs: sampling, Haar, median, fractions, cache
    gray = face_still()
    monkeypatch.setattr(face, "grab_gray", lambda video, t, width=face.SAMPLE_W: gray)
    segs = [Segment(0.0, 6.0)]
    det = detect_face(Path("not-read.mp4"), segs, tmp_path)
    assert det["samples"] == 6 and det["hits"] == 6
    assert det["sample_size"] == [260, 280]
    l, t, r, b = det["face"]
    cx, cy, side = STILL_FACE
    assert (l + r) / 2 == pytest.approx(cx / 260, abs=0.04)
    assert (t + b) / 2 == pytest.approx(cy / 280, abs=0.04)
    assert (b - t) * 280 == pytest.approx(FACE_H * side, rel=0.1)

    def no_footage(*a, **k):
        raise AssertionError("cache not used")
    monkeypatch.setattr(face, "grab_gray", no_footage)
    assert detect_face(Path("not-read.mp4"), segs, tmp_path)["face"] == det["face"]   # from faces.json


@pytest.mark.skipif(not DJI_VIDEO.is_file(), reason="set AI_SHORTS_DJI_0348 to the DJI_0348 recording")
def test_real_dji_detection_matches_fixture(tmp_path):
    segs = [Segment(102.73, 109.03), Segment(141.37, 147.70)]
    det = detect_face(DJI_VIDEO, segs, tmp_path)
    assert det["hits"] >= 0.8 * det["samples"]
    assert det["face"] == pytest.approx(FIX["face"], abs=0.02)


def test_enough_agreeing_hits_is_a_face_even_at_a_low_share():
    # DJI_0353 (21 Oct 2026): 14 agreeing hits of 53 samples fell back to config.face_box
    from ai_shorts.face import robust_box
    hits = [(270.0, 120.0, 60.0)] * 14 + [None] * 39
    assert robust_box(hits) is not None
    assert robust_box([(270.0, 120.0, 60.0)] * 5 + [None] * 48) is None
