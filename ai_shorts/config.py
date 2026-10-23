"""Every tunable in one place. Change the brand here."""
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Arial Bold / Arial Black: the Mac's copies, or Windows' on the tower (21 Oct 2026: renders moved
# to the tower so the Mac stops cooking itself).
if sys.platform == "win32":
    FONT_BOLD, FONT_HEAVY = r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\ariblk.ttf"
else:
    FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    FONT_HEAVY = "/System/Library/Fonts/Supplemental/Arial Black.ttf"

# DeepFilterNet lives in its own venv (its torch/numpy pins break the render venv); tower renders
# pass its python from the private remote settings (ai_shorts/remote.py). Unset: no clean-up, a warning.
DF_PYTHON = os.environ.get("AI_SHORTS_DF_PYTHON", "")

# Tools: an AI_SHORTS_* env var wins, then PATH, then the usual Homebrew / uv install spot.
FFMPEG = os.environ.get("AI_SHORTS_FFMPEG") or shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = os.environ.get("AI_SHORTS_FFPROBE") or shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
MLX_WHISPER = (os.environ.get("AI_SHORTS_MLX_WHISPER") or shutil.which("mlx_whisper")
               or str(Path.home() / ".local/bin/mlx_whisper"))


@dataclass(frozen=True)
class Framing:
    """How much of George the video window shows.

    face_share: face height (forehead to chin) as a share of the video window
                height; None fills the room between title strip and captions.
    eye_line:   eyes this far down the visible window (title strip to seam).
    """
    face_share: float | None
    eye_line: float = 1 / 3


FRAMINGS = {
    "tight": Framing(None),     # v8: face fills the room ("I'm just a head")
    "medium": Framing(0.36),    # talking head: head, shoulders, some chest
    "close": Framing(0.47),     # between tight and medium: head and top of the shoulders
    "wide": Framing(0.28),      # more chest and the wall around him
}

# Palettes (21 Oct 2026: one solid red was too much). A palette sets the
# background (`bg_stops`: top to bottom, two or three colours; empty = the original solid red with
# its gradient foot) and the accent family the template already uses: `red` is the accent (title
# strip, panel when solid), `red_dark` the cards, `red_tint` dimmed text and borders.
PALETTES = {
    "red": {},
    # the four finalists after the 21 Oct 2026 colour research (four models on palette, contrast and mood):
    # text accents darkened to 4.5:1+ on the cream current-step row, yellow captions kept
    "red-black": {"bg_stops": ("#C8102E", "#5A0812", "#120406"), "red": "#C8102E",
                  "red_dark": "#6E0A18", "red_tint": "#E8A0A8", "accent_text": "#C8102E"},
    "charcoal-orange": {"bg_stops": ("#29292F", "#19191F", "#101014"), "red": "#E8590C",
                        "red_dark": "#24242B", "red_tint": "#B9B6BE", "accent_text": "#C2410C"},
    "teal-navy": {"bg_stops": ("#134E5A", "#102C40", "#0B1424"), "red": "#087985",
                  "red_dark": "#103849", "red_tint": "#A5C9CF", "accent_text": "#087985"},
    "navy": {"bg_stops": ("#173A70", "#0A1630", "#05080F"), "red": "#2F6FDB",
             "red_dark": "#10264A", "red_tint": "#B7C9E5", "accent_text": "#245FC4"},
    # shown and set aside on 21 Oct 2026
    "forest": {"bg_stops": ("#11664C", "#06281E", "#030C09"), "red": "#1F9E74",
               "red_dark": "#0B3B2C", "red_tint": "#9ED9C3", "accent_text": "#14724F"},
    "sunset": {"bg_stops": ("#D0142C", "#E2561F", "#3A0A12"), "red": "#D63A1E",
               "red_dark": "#7A1A10", "red_tint": "#F5BCA4"},
    "purple-blue": {"bg_stops": ("#5B21B6", "#1E3A8A", "#0B1020"), "red": "#7C3AED",
                    "red_dark": "#2A1A5C", "red_tint": "#C4B5FD"},
}

# Colour grades for George's picture only (never the overlays), per shoot: a flat room with a
# white wall left him pale, while his normal setup has its own lighting and needs none.
# Contrast and darker mids put depth back; warmth pulls green out rather than adding red only.
GRADES = {
    "none": None,
    "light": "eq=contrast=1.06:gamma=0.95:saturation=1.08,colorbalance=rm=0.04:gm=-0.01:bm=-0.03",
    "medium": "eq=contrast=1.10:gamma=0.91:saturation=1.12,colorbalance=rm=0.06:gm=-0.02:bm=-0.04",
    "strong": "eq=contrast=1.14:gamma=0.87:saturation=1.16,colorbalance=rm=0.08:gm=-0.02:bm=-0.05",
}


@dataclass
class Config:
    # Brand: one accent family, three weights (the red defaults; a palette overrides them).
    red: str = "#D0142C"              # the panel
    red_dark: str = "#8C0B1D"         # stat and counter cards
    red_tint: str = "#F2A2AA"         # dimmed (already said) steps
    text_color: str = "#FFF7EF"       # off-white
    highlight_color: str = "#FFD84D"  # current caption word
    caption_outline: str = "#000000"
    palette: str = "teal-navy"       # picked 21 Oct 2026 (option C); render --palette overrides
    bg_stops: tuple = ()             # a PALETTES background: top-to-bottom gradient stops
    accent_text: str = ""            # accent for text on the light current-step row and chips
                                     # (empty = red); 4.5:1 or better against text_color
    font_bold: str = FONT_BOLD
    font_heavy: str = FONT_HEAVY

    # Frame
    width: int = 1080
    height: int = 1920
    fps: int = 30

    # Safe area: TikTok and Instagram Reels draw their UI over everything outside
    # this box (status bar + tabs on top; caption, username, music, nav below;
    # like/comment/share on the right). Every word and every graphic that carries
    # information sits inside it; outside is colour or decoration only.
    safe_left: int = 60
    safe_right: int = 940
    safe_top: int = 220
    safe_bottom: int = 1440

    # Layout (y on the 1920 frame). The safe area limits INFORMATION only: video and
    # decoration may run under the app UI. George's video fills 0..seam; the title
    # sits on a semi-transparent red strip over it; captions centre on the seam; the
    # info panel is below; under it a red gradient and a small brand mark.
    title_band: tuple[int, int] = (220, 300)
    title_strip_alpha: float = 0.82
    seam: int = 925
    caption_half: int = 47       # captions reach this far either side of the seam (measured 41/45)
    brand_mark: str = "George Bracher"   # name only: no URL or @handle (platforms may suppress those)
    brand_y: int = 1820

    # Depth and framing (all drawn in code; set to 0 to turn a piece off)
    grain: int = 5               # +/- levels of static noise on every red surface
    grain_seed: int = 7
    window_inset: int = 22       # George's video window: red margin either side
    window_radius: int = 40      # rounded corners where the video meets the panel
    window_border: int = 3       # thin off-white line around the window
    card_darken: float = 0.45    # info card: this far from red towards red_dark
    card_radius: int = 30
    card_border: int = 2         # thin red_tint line around the card
    card_pad: int = 12           # card edge to its content
    card_shadow: int = 70        # shadow alpha under the card (0 = none)

    # George's face (forehead to chin) is found automatically (face.py). This box,
    # measured on his iPhone take, is only the fallback when detection finds
    # nothing reliable. Fractions of the source frame: (left, top, right, bottom).
    face_box: tuple[float, float, float, float] = (0.27, 0.19, 0.69, 0.56)
    framing: str = "medium"      # a FRAMINGS preset; render --framing overrides
    grade: str = "none"          # a GRADES preset; render --grade overrides
    eye_in_face: float = 0.42    # eyes sit this far down the forehead-to-chin box
    face_fill: float = 0.98      # tight: face height as a share of the room between title strip and captions
    max_upscale: float = 1.15    # never enlarge the source more than this (softness)
    headroom: float = 0.06       # face-heights kept clear above the forehead box (hair) under the title strip

    debug_safe: bool = False     # draw the unsafe zones and the face box on the video

    # Transcription
    whisper_model: str = "mlx-community/whisper-large-v3-turbo"
    language: str = "en"

    # Trim
    pad: float = 0.12            # seconds kept either side of speech
    max_pause: float = 0.6       # longer pauses are cut down to 2 x pad

    # Motion
    anim: float = 0.25           # step / stat / beat entry duration
    count_up: float = 0.7        # counter beats count from 0 over this long

    # Captions
    caption_size: int = 76
    caption_max_words: int = 4
    caption_max_chars: int = 18

    # Encode
    crf: int = 20
    x264_preset: str = "medium"
    loudness_lufs: float = -16.0     # was -14; George found it "kind of loud" (21 Oct 2026)
    true_peak: float = -1.5
    # Speech clean-up (George picked option D, 21 Oct 2026): DeepFilterNet on the take, then this EQ
    # (rumble cut, a little body, harsh upper mids and the hiss shelf down, gentle compression).
    clean_audio: bool = True
    df_python: str = DF_PYTHON
    voice_eq: str = ("highpass=f=80,equalizer=f=180:t=q:w=1:g=2.5,equalizer=f=3200:t=q:w=1:g=-3,"
                     "highshelf=f=8000:g=-2,acompressor=threshold=-20dB:ratio=2.5:attack=10:release=150")

    @property
    def safe_rect(self) -> tuple[int, int, int, int]:
        """What the platforms leave uncovered."""
        return self.safe_left, self.safe_top, self.safe_right, self.safe_bottom

    @property
    def info_rect(self) -> tuple[int, int, int, int]:
        """Where information goes: the safe area made symmetric about the frame
        centre (x 140-940), so everything centres on x=540 and still clears the
        right-hand buttons."""
        return self.width - self.safe_right, self.safe_top, self.safe_right, self.safe_bottom

    @property
    def center_x(self) -> float:
        return self.width / 2


DEFAULT = Config()
