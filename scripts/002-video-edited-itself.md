---
slug: 002-video-edited-itself
title: Can code edit my videos for me?
steps:
  - label: Film it in one go, mistakes and all
    trigger: one
  - label: Transcribe every word with a timestamp
    trigger: two
  - label: Keep the last good take of each line
    trigger: three
  - label: Cut the gaps, add captions and graphics
    trigger: four
stats:
  - Minutes filmed 3
  - Seconds posted 60
  - Restarts 5
sources: 001 take 2 (DJI_0349, 21 Oct 2026) render log and report.json - 198.7 s raw, 60.0 s posted, 5 restarts, 62 words dropped; step three played twice in v15/v16 until the long-word re-listen fix (tests/test_refine.py)
---
My last video took three minutes to film.
I posted sixty seconds of it.
Five restarts. I fluffed the very first line.
I didn't edit any of it. The code did.
One. Film the whole script in one go. Mess up, pause, say the line again.
Two. Whisper writes down every word and when I said it. Free, on my laptop.
Three. Match each line to the script and keep the last good take.
Four. Cut the gaps, then add the captions and the graphics.
Is it perfect? No. The first cut played step three twice and I only caught it on rewatch.
That bug's a test now, so it can't happen again.
The code's in the repo. Please don't DM me.
