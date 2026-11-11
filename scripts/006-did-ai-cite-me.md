---
slug: 006-did-ai-cite-me
title: Did AI ever cite my website?
steps:
  - label: Ask the same questions, word for word
    trigger: one
  - label: Count your rivals too
    trigger: two
  - label: Check the places with no page
    trigger: three
  - label: Split it by AI
    trigger: four
stats:
  - {label: Rightmove, value: "100", trigger: a hundred me}
  - {label: Me, value: "71", trigger: seventy-one}
sources: southcoasthouseprices monthly-2026-11-02 against baseline-2026-10-18, same 50 questions (wording compared, 0 differences), same 4 models (served_model the same). Baseline 18 Oct 17:14 UTC, first answer of the re-check 2 Nov 01:19 UTC, 14 days 8 hours. Restarts and a Mac copy of the job asked each of the 200 cells four times (three tower passes, one Mac pass, 800 answers, none failed); the whole run cost 48.71 USD, planned about 18 (aeo-sitekit a22de19, SCHP handoff). First pass is the like-for-like, 71 of 200 cite the site, Rightmove 100 (baseline 0 and 104). Passes give the site 71, 81, 83, 81 and Rightmove 100, 102, 100, 92. The public feed counts a cell at its latest answer, 81 of 200. Recounted 2 Nov from the raw payloads with videos/001-aeo-baseline/check.py's cited_from rule (Gemini from its raw annotations), 316 in all, 0 mismatches against the logged flag, no raw file missing. By engine over 800 answers, Claude 137/200, Gemini 108/200, ChatGPT 53/200, Perplexity 18/200. No page, West Thorney (no sales) and Apuldram (2 sales in two years, page held; /appledram/ and /apuldram/ both 404, neither in the sitemap), 1 of 160, and that one answer cited /chichester/. The 8 places with pages, 315 of 640. Google AI Overview was not in the baseline; on these 50 questions, 200 cells, 189 answered, 170 with an overview, 0 cite the site, read by the kit's fixed reader (67aa91f, rows rebuilt b8448dd) and by a separate search of each saved page's source block. The site does show in ordinary results under the overview on chidham-and-hambrook-q2, which is not a citation. 89 of the 170 saved pages stop at the old 300k cap, but the source blocks sit near the front. Across all questions the feed reads Google 1 of 101 (q8, left the plan 2 Nov). Visitors from PostHog 18 Oct to 2 Nov, $pageview on the host, headless left out, 109 views, referrers direct 69, own site 28, Google 12, none from the AI list or AI utm tags; apps that strip the referrer would show as direct, hence "that I can see". Questions written before publishing; the 29 Oct demand check found no Google suggestion for "is bosham an expensive place to live". These are API models, not the consumer apps
---
Launch day, four AIs, two hundred answers about south coast house prices. Rightmove a hundred and four, me, zero.
Two weeks later I asked again.
Rightmove a hundred. Me, seventy-one.
A bug asked everything four times, which cost me forty-eight dollars. Seventy-one, eighty-one, eighty-three, eighty-one.
One. Same questions, word for word, or the number means nothing.
Two. Count your rivals as well. Rightmove barely shifted.
Three. Check places with no page. Two villages, one citation in a hundred and sixty. Everywhere else, about half.
Four. Split by AI. Claude, seven answers in ten. Perplexity, less than one.
Is that the pages? Maybe. Those two villages barely sell a house.
Google's AI Overviews? Zero, out of a hundred and seventy.
Visitors from AI that I can see? Zero. I wrote those questions, and I might be the only one asking.
The answers are in the repo. Please don't DM me.
