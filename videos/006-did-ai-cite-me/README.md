# 006: Did AI ever cite my website?

In [001](../001-aeo-baseline/) I asked four AIs 50 questions about south coast house prices on the day
[southcoasthouseprices.co.uk](https://southcoasthouseprices.co.uk/) launched. Rightmove was cited in
104 of the 200 answers and my site in none. Two weeks later I asked again. This is what came back.

## The re-check

On 2 Nov 2026, 14 days and 8 hours after the baseline, the same 50 questions went to the same four
models, word for word (0 differences against `questions.txt`, and every answer was served by the same
model as in the baseline).

| | Baseline, 18 Oct | Re-check, 2 Nov |
|---|---|---|
| rightmove.co.uk | 104 | 100 |
| southcoasthouseprices.co.uk | 0 | 71 |

The re-check's answers are in [`../001-aeo-baseline/results/`](../001-aeo-baseline/results/), in the
same format as the baseline, so the same `check.py` recounts them offline:

```
python check.py count results/recheck-2026-11-02-pass1 --site southcoasthouseprices.co.uk
```

## Why there are four passes

A bug. Restarts on my scheduled job, plus a copy of it that ran on another machine, asked every one
of the 200 questions four times: 800 answers, none failed. The whole run cost $48.71 against a plan
of about $18. I kept all four, one folder each, numbered in the order each question was asked:

| Pass | My site | Rightmove |
|---|---|---|
| 1 | 71 | 100 |
| 2 | 81 | 102 |
| 3 | 83 | 95 |
| 4 | 81 | 97 |

Pass 1 is the like-for-like with the baseline, so that's the one the video leads with. Passes 3 and 4
overlapped in time, so which answer counts as the third or fourth for a question is by timestamp.

## What the 800 answers say

- **Places with no page.** Two of the ten places have no page: West Thorney (no sales to write about)
  and Apuldram (two sales in two years). Over all four passes they got 1 citation in 160 answers, and
  that one cited the Chichester page. The eight places with pages got 315 of 640, about half.
- **Split by AI.** Claude cited the site in 137 of its 200 answers, Gemini 108, ChatGPT 53 and
  Perplexity 18.
- **Rivals.** Rightmove went from 104 to 100. It barely moved.

Is that the pages, then? Maybe. The two villages without pages barely sell a house, so they're
harder questions for anyone.

## Google AI Overviews

Google wasn't in the baseline, so this isn't a before and after. On the same 50 questions, asked
four times, Google answered 189 of 200 searches, showed an AI Overview on 170 and cited my site in
none of them. The site does turn up in the ordinary results under the overview for one Chidham and
Hambrook question, which isn't a citation. These are read from the saved result pages, which aren't
published here.

## Visitors from AI

From launch to the re-check (18 Oct to 2 Nov), the site had 109 page views, not counting headless
browsers: 69 direct, 28 from its own pages, 12 from Google, none from an AI app or an AI tag in the
link. Apps that strip the referrer would show up as direct, so it's zero that I can see. I wrote
these questions before the site existed, and I might be the only one asking them.

## Caveats

- These are the API models through OpenRouter with web search on, not the consumer apps.
- One answer per question per pass. Answers vary run to run, which the four passes show.
- Gemini's links are redirects. They were resolved when the answers came in and stored with each
  answer. Two Gemini answers had two redirects to the same page, and those were looked up again on
  11 Nov.
