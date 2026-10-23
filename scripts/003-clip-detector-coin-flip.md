---
slug: 003-clip-detector-coin-flip
title: Can AI pick my best stream clips?
steps:
  - label: Show Claude 48 clips my editor graded
    trigger: one
  - label: Ask it to grade the next clip the same way
    trigger: two
  - label: Check it against what he actually picked
    trigger: three
  - label: Only send him the clips Claude rates
    trigger: four
beats:
  - kind: counter
    value: 14
    label: signals
    trigger: fourteen signals
  - kind: counter
    value: 336
    label: graded clips
    trigger: three hundred and thirty-six
stats:
  - {label: Detector, value: "50/50", trigger: coin flip}
  - {label: Claude, value: "3 in 4", trigger: three times out of four}
sources: my stream pipeline's measurements (videos/003-clip-detector-coin-flip/README.md) - 14-signal clipper; on 336 real editor grades the detector predicted him at AUC 0.498 (learned weights 0.505) after a quarter of learning; claude-opus-5 with 48 graded examples scored 287 held-out clips at AUC 0.76 (rerun 0.763); the judge now chooses what reaches the editor. AUC 0.76 read aloud as "three times out of four".
---
I built a clip detector for my streams.
Fourteen signals. Laughter, loudness, chat spikes, my face.
Then I checked it against three hundred and thirty-six clips my editor had already said yes or no to.
It was a coin flip. Fifty-fifty.
So I tried something lazier.
One. Show Claude forty-eight clips my editor already graded.
Two. Ask it to grade the next clip the same way.
Three. Check it against what he actually picked.
Four. Only send him the clips Claude rates.
Give it a clip he kept and a clip he binned, and Claude picks the right one three times out of four.
My detector spent three months learning from his grades. It learned nothing.
The prompt's in the repo. Please don't DM me.
