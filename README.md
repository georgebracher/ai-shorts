# ai-shorts

Turns a talking-head recording and its script into a captioned 1080x1920, 30 fps short with no
manual editing. You read the script to camera; the pipeline does the rest.

It edits my videos on TikTok and Instagram ([@georgebracher.ai](https://www.tiktok.com/@georgebracher.ai)).
`videos/` holds what each one promises: the questions, code and every answer behind 001, the clip
judging prompt behind 003.

## What it does

- Transcribes the take with word timestamps (mlx_whisper on a Mac, OpenAI's whisper on an NVIDIA
  GPU) and caches the transcript per input file.
- Cuts dead air at both ends and shortens every pause over 0.6 s to about a quarter of a second.
- Keeps one take of each line. Each sentence you said is matched to the script, paraphrase
  allowed, and the edit walks forward through the script keeping the last complete take of each
  line. Restarts and repeats of the line you are on are dropped. Where whisper ran a word over a
  restart, that stretch is transcribed again on its own.
- Finds your face with OpenCV's Haar frontal-face detector on about one frame a second, takes the
  median box and sets one static crop for the whole video (no tracking). The crop puts your eyes
  a third of the way down the video window and centres your face on the frame. Where the source
  does not cover the window, its edges are extended and blurred.
- Draws the template: the title on a strip over the video, word-level captions on the seam with
  the current word highlighted, and an info card below with hook beats (chips and counters), stat
  cards and numbered steps that appear as you say them. A small wordmark sits at the bottom.
- Takes caption words from what you said, with names and numbers spelled from the script
  ("write move" becomes Rightmove).
- Cleans the voice (DeepFilterNet if installed, then EQ), levels it to -16 LUFS with a -1.5 dB
  true peak, and encodes H.264 + AAC with every metadata tag stripped. It reads the finished file
  back and refuses to keep it if any tag survived (phones put GPS in them).
- Writes a 12-frame contact sheet PNG.
- Self-check: transcribes the finished video and lists anything worth a listen before posting:
  a word said twice, captions that were not heard, speech with no caption, a word stretched over
  a pause.

Colours, fonts, sizes, timings, the safe area and the framing, palette and grade presets all live
in `ai_shorts/config.py`.

## Run it

```
.venv/bin/python -m ai_shorts render --video raw.mov --script scripts/001-aeo-baseline.md
```

On Windows the python is `.venv\Scripts\python`. Options:

- `--video PATH`: the recording. Repeat it for pickups (below).
- `--script PATH`: the script (format below).
- `--framing tight|close|medium|wide`: how much of you the window shows. `medium` (default):
  head, shoulders and some chest. `close`: head and the top of the shoulders. `tight`: your face
  fills the window. `wide`: more chest and wall.
- `--grade none|light|medium|strong`: warms and deepens a flat-lit shoot. It changes the video
  only, never the graphics. Default `none`.
- `--palette NAME`: template colours. `teal-navy` (default), `red`, `red-black`,
  `charcoal-orange`, `navy`, `forest`, `sunset`, `purple-blue`.
- `--preview-at SECONDS`: draws a still of the finished frame at that output time instead of
  rendering; repeat it for more stills. They go in the work dir (its path is in the log).
  Transcription and the edit still run; the encode does not.
- `--debug-safe`: tints the zones the apps cover and outlines the face box it found.
- `--out PATH`: writes the video there instead of the default name, with its contact sheet
  beside it.

Fluffed a line and already moved on? Film just that line again with the same camera settings and
pass both files, main take first: `--video main.MP4 --video pickup.MP4`. Each pickup is placed
into the main take right after the old take of its line (one hardware HEVC encode, cached in
`out/placed/`), so the edit sees an ordinary retake and keeps the pickup. A pickup whose size,
frame rate or HDR differs from the main take stops the run.

`python -m ai_shorts tower --video RAW [--video PICKUP] --script SCRIPT [--framing F] [--grade G]`
does the same render on another machine over ssh (see Setup), copies the video and contact sheet
back to where a local render puts them and the report to `out/tower/`. `--force` renders even
when the machine's busy check says it is in use. `--palette`, `--preview-at`, `--debug-safe` and
`--out` are local only.

## Output

- The video: `~/Downloads/<slug> v<N> <framing> - AI Shorts.mp4`, with `<grade> grade` after the
  framing when a grade is set. N is one above any render of that slug in `~/Downloads` or anywhere
  under `~/Downloads/AI Shorts/<slug>/`, so numbers never repeat and moving old renders into that
  folder keeps the count. An existing file is never overwritten.
- The contact sheet: `~/Downloads/AI Shorts/<slug>/contact sheets/`, or beside `--out`.
- `--debug-safe` writes `<slug> v<N> safe-zones debug - AI Shorts.mp4` into
  `~/Downloads/AI Shorts/<slug>/`, numbered after the latest render (v1 if there is none yet).
- Work files go to `out/work/<take>-<hash>/` in the repo: the audio, transcripts, face samples,
  each render's ffmpeg log and its report in `reports/<render>.json` (kept and dropped words, the
  cut list, when each step, stat and beat appears, layout boxes, face detection, warnings and the
  self-check; `report.json` is the latest). The cache key is the take's name, size and first
  megabyte, so a moved or copied take keeps its cache. Renders of the same take can run at once:
  each reserves its output name first and never overwrites a finished file.
- The log prints `WARNING` lines (a trigger never heard, no reliable face, a box outside the safe
  area, DeepFilterNet missing) and `CHECK` lines from the self-check. Neither stops the run, so
  read them before posting.

## Script format

A script is a text file with YAML front matter. `scripts/` has real ones.

```
---
slug: 001-aeo-baseline           # names the output files
title: Will AI ever cite my website?
steps:                           # numbered steps, each shown when its trigger is said
  - label: Write the questions down first
    trigger: one
beats:                           # hook graphics; they clear when the first stat or step lands
  - kind: chips                  # each chip pops in when its own word is said
    items: [ChatGPT, Claude, Gemini, Perplexity]     # or {label, trigger}
  - kind: counter                # counts up from 0 when the trigger is said
    value: 50
    label: questions
    trigger: fifty questions     # default: the value
stats:
  - Rightmove 104                # "label value": pops in when the value is said
  - {label: Claude, value: "3 in 4", trigger: three times out of four}
---
The words you read to camera.
```

- `slug` and `title` are required. Other front matter keys, such as a `sources:` note, are kept
  and ignored.
- Steps appear in order. A trigger is matched at its place in the script first, so "two hundred"
  in an earlier line does not fire step two. A step whose trigger is never heard still shows, at
  the start of its own line when that line was heard (otherwise one second after the step before
  it), and the log warns.
- A stat without a `trigger` pops in when its value is said, or failing that the first word of
  its label. A stat that is never heard does not appear, and the log warns.
- A beat whose triggers are never heard does not appear, and the log warns.
- The body is the script you read. Captions follow what you actually said; the body gives the
  spelling of names and numbers and the order of lines for picking takes.

## Setup

You need Python 3.11 or newer, ffmpeg with ffprobe, Arial Bold and Arial Black, and a whisper
backend. Two setups are supported. `ai_shorts/transcribe.py` picks the backend by what it finds:
the `mlx_whisper` command if there is one, otherwise OpenAI's whisper on an NVIDIA GPU.

### Apple Silicon Mac

```
brew install python@3.13 ffmpeg pipx
pipx install mlx-whisper
python3.13 -m venv .venv
.venv/bin/pip install -e '.[test]'
```

The `mlx_whisper` command is looked up in this order: the path in `AI_SHORTS_MLX_WHISPER`, then
PATH, then `~/.local/bin/mlx_whisper`, which is where pipx puts it. Keep it in its own pipx
environment: it brings torch and numba, which the render venv does not need. Tested with
mlx-whisper 0.4.3. The first transcription downloads `mlx-community/whisper-large-v3-turbo` from
Hugging Face (over 1.5 GB).

Arial Bold and Arial Black ship with macOS in `/System/Library/Fonts/Supplemental`, and so does
`say`, which the end-to-end test uses.

### Windows with an NVIDIA GPU

```
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cu126
.venv\Scripts\python -m pip install -e ".[cuda,test]"
```

Install torch from PyTorch's CUDA 12.6 index first: the PyPI wheel for Windows is CPU only, and
the whisper fallback loads its model on `cuda`. The `cuda` extra adds openai-whisper (20240930 or
newer, for the `turbo` model). The first transcription downloads that model (about 1.5 GB) to
`~/.cache/whisper`. The fonts come from `C:\Windows\Fonts` (`arialbd.ttf`, `ariblk.ttf`).

### Word list

Captions tell ordinary words from names with Webster's Second International word list (public
domain), which every Mac has as `/usr/share/dict/web2`. The code uses, in order: the file
`AI_SHORTS_WORDS` names, `data/words.txt.gz` in the checkout, `/usr/share/dict/web2`, then
`/usr/share/dict/words`. On Windows, copy `web2` from a Mac (gzipped or not) to one of those. Without
any, the render warns and a capitalised word opening a line can be taken for a name.

### Other platforms

Untested. On Linux the fonts are looked up at the macOS paths, and transcription needs either the
`mlx_whisper` command or CUDA.

### ffmpeg

`ai_shorts/config.py` uses `AI_SHORTS_FFMPEG` and `AI_SHORTS_FFPROBE` when they are set, then
`ffmpeg` and `ffprobe` on PATH, then `/opt/homebrew/bin`. On Windows, put a build that includes
ffprobe on PATH or set the two variables. HDR takes (HLG or PQ) are tone-mapped with `zscale`, so
the build needs libzimg: check that `ffmpeg -hide_banner -filters` lists `zscale` (Homebrew's
does). Pickups are re-encoded with the hardware HEVC encoder, `hevc_videotoolbox` on the Mac and
`hevc_nvenc` on Windows.

### Speech clean-up (optional)

Each take's sound can go through DeepFilterNet before the voice EQ and loudness pass.
DeepFilterNet's torch and numpy pins break the render venv, so it gets a venv of its own, outside
this one, and `AI_SHORTS_DF_PYTHON` points at that venv's python:

```
python3.12 -m venv ../ai-shorts-df
../ai-shorts-df/bin/pip install deepfilternet torch torchaudio soundfile
export AI_SHORTS_DF_PYTHON="$(realpath ../ai-shorts-df/bin/python)"
```

On Windows the python is `..\ai-shorts-df\Scripts\python.exe`. The code is written against
DeepFilterNet 0.5.6, whose `torchaudio.backend.common` import `ai_shorts/audio.py` stands in for,
so current torchaudio works. Without `AI_SHORTS_DF_PYTHON` the render logs a warning and skips the
clean-up; the EQ and loudness pass still run.

### Rendering on another machine (optional)

`python -m ai_shorts tower` renders on a Windows machine with an NVIDIA GPU over ssh and brings
the result back. Its settings are private, so they live outside the repo in
`~/.config/ai-shorts/remote.toml` (or the file `AI_SHORTS_REMOTE` names). The keys are documented
at the top of `ai_shorts/remote.py`: ssh host, folders, an optional DeepFilterNet python, an
optional busy check and an optional Cloudflare R2 bucket for footage. Run it from a git checkout:
it sends every tracked file, uncommitted edits included. The render machine needs an ssh server
with the cmd shell, `py -3.12`, ffmpeg on PATH and an NVIDIA GPU; the first run makes its venv
there (CUDA torch, openai-whisper, boto3). Footage through R2 also needs boto3 on the sending
machine: `.venv/bin/pip install -e '.[remote]'`.

## Tests

```
.venv/bin/python -m pytest --deselect tests/test_smoke.py
```

The fast suite takes a few seconds. It covers script parsing, trim and time-map maths, take
selection and captions on real whisper transcripts of recorded takes, step, stat and beat timing,
the layout inside the safe area, the framing maths, and face detection on a grayscale still of a
real face (`tests/fixtures/face-gray.npy.gz`). Tests write only under pytest's temp folders.

```
.venv/bin/python -m pytest tests/test_smoke.py
```

The end-to-end test builds a fake raw clip (a test pattern plus macOS `say` reading the script,
with a flubbed line, a long pause and fake GPS tags), renders it through the CLI and checks the
result the way a viewer would: format, no metadata, the flub cut, loudness, and the steps and
beats on screen at the right times. It runs whisper and a full render, and skips without `say` and
a whisper backend.

## Limits

- Supported on an Apple Silicon Mac and on Windows with an NVIDIA GPU. Other platforms are
  untested.
- English only: `language` in `config.py` is `en`, and number matching uses English number words.
- Face detection finds frontal faces only. A face in profile, mostly covered, or smaller than
  about a tenth of the frame width is missed. When too few sampled frames agree, the crop falls
  back to `face_box` in `config.py`, a box measured on one phone take, and the log says so. Check
  the contact sheet.
- The crop is static, so if you move around a lot you drift in the frame.
- Take selection only moves forward through the script. A line you redo after moving on to later
  lines is dropped, and so is a full retake that loses to an earlier take of the line; both give a
  warning. Film the line as a pickup if the dropped take is the better one.
- The safe area (x 60-940, y 220-1440 on the 1080x1920 frame) is my own estimate of what TikTok
  and Instagram Reels leave clear of their buttons and captions, not a published spec, and the
  apps change. Information is laid out inside a copy made symmetric about the centre
  (x 140-940); video and decoration may run under the app UI. Check a test upload.

## Licence

MIT. See LICENSE.
