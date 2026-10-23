---
slug: 001-aeo-baseline
title: Will AI ever cite my website?
steps:
  - label: Write the questions down first
    trigger: one
  - label: Ask all four AIs in the same hour
    trigger: two
  - label: Count who gets cited
    trigger: three
  - label: Publish, then re-ask every two weeks
    trigger: four
beats:
  - kind: chips
    items: [ChatGPT, Claude, Gemini, Perplexity]
  - kind: counter
    value: 50
    label: questions
    trigger: fifty questions
  - kind: counter
    value: 200
    label: answers
    trigger: two hundred answers
stats:
  - Rightmove 104
  - My site 0
sources: southcoasthouseprices baseline-2026-10-18 (50 questions x 4 engines, 200 answers, $7.20). Rightmove is cited in 104 answers; 122 was the count before the 20 Oct fix, which had counted every source Perplexity returned rather than the ones its answer used
---
I asked ChatGPT, Claude, Gemini and Perplexity fifty questions about house prices on the south coast.
Two hundred answers.
Rightmove got cited in a hundred and four of them.
My new site? Zero.
In fairness, it's a day old.
So this is how I'm testing if AI will ever cite it.
One. Write the questions down before you publish anything, so you can't move the goalposts later.
Two. Ask all four in the same hour and save every answer.
Three. Count who gets cited. That's your baseline. Mine cost seven dollars.
Four. Publish pages that answer those exact questions, then ask again every two weeks.
Will it work? No idea. Day one, it's Rightmove a hundred and four, me nil.
The code's in the repo below. Please don't DM me.
