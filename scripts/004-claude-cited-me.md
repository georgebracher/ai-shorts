---
slug: 004-claude-cited-me
title: Which AI reads your site first?
steps:
  - label: Find the AI bots in your logs
    trigger: one
  - label: Count each bot's visits
    trigger: two
  - label: Ask the same questions again
    trigger: three
  - label: See who cites you
    trigger: four
stats:
  - {label: Claude, value: "3", trigger: three times}
  - {label: The rest, value: "0", trigger: still zero}
sources: southcoasthouseprices weekly-2026-10-19 (19 Oct 01:15 UTC, 8 h after the baseline; the 9 baseline questions on the two places with pages under four weeks old, Bosham and Emsworth; credits ran out mid-run, 25 of 36 cells answered, 9 failed with HTTP 402, 2 never asked. Claude cited the site in 3 of its 6 answers, all Bosham, one with it as the first source; ChatGPT 0 of 6, Gemini 0 of 7, Perplexity 0 of 6). Cloudflare crawler counts for the 24 h to 19 Oct 00:45 UTC, recounted 22 Oct after the bot-filter fix (a floor), ClaudeBot 32 (the script's number; Claude-User's 7 left out because it only fires on someone's request and our own 50 Claude questions sit in that window), GPTBot 15 + OAI-SearchBot 2 = 17, PerplexityBot 1. GPTBot fetched /bosham/ twice in that window, before ChatGPT's 0 of 6. Body lines match the take filmed 1 Nov where he reworded them, and the take says Claude's bots for ClaudeBot's 32
---
In my first video, four AIs gave two hundred answers. My site got zero.
Eight hours later, Claude cited it. Three times.
ChatGPT, Gemini and Perplexity? Still zero.
So I checked who'd actually been reading it.
One. Find the AI bots in your logs. I use Cloudflare.
Two. Count each bot's visits. On day one Claude's crawler came thirty-two times. OpenAI's, seventeen. Perplexity's, once.
Three. Ask the same questions again.
Four. See who cites you. Claude cited me three out of six times. All about Bosham, and once cited first.
Is that why? Maybe not. OpenAI's bot read that page too and still didn't cite it. Three answers isn't a trend.
A full re-check's coming. I'll post what it finds.
The answers are in the repo. Please don't DM me.
