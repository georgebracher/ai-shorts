# 004: Which AI reads your site first?

In [001](../001-aeo-baseline/) four AIs gave 200 answers and my new site got zero. Eight hours later
Claude cited it three times, so I went and looked at who'd actually been reading it. This folder has
those answers and the crawler counts.

## The answers

At 01:15 UTC on 19 Oct 2026 my scheduled citation run asked nine of the baseline's questions, word
for word, about Bosham and Emsworth, through the same four models. It ran out of OpenRouter credit
part way. Of 36 possible answers, 25 came back, 9 failed with HTTP 402 and 2 were never asked (Gemini
and Perplexity on "Does Emsworth flood?").

| Engine | Answers | Citing my site |
|---|---|---|
| Claude | 6 | 3 |
| ChatGPT | 6 | 0 |
| Gemini | 7 | 0 |
| Perplexity | 6 | 0 |

Claude's three were all about Bosham. It only got to answer one Emsworth question before the credit
ran out.

| Question | Where my site came in its sources |
|---|---|
| What is the average house price in Bosham? | 3rd of 3 |
| Is Bosham an expensive place to live? | 3rd of 7 |
| How many houses sell in Bosham each year? | 1st of 2 |

## The crawlers

Cloudflare's count for the 24 hours to 00:45 UTC on 19 Oct, successful requests only:

| AI | Crawler | Requests |
|---|---|---|
| Claude | ClaudeBot | 32 |
| ChatGPT | GPTBot 15, OAI-SearchBot 2 | 17 |
| Perplexity | PerplexityBot | 1 |

Gemini isn't in the table because Google doesn't crawl under a Gemini name. Googlebot came 50 times,
for whatever that's worth.

What those numbers don't tell you:

- 32 is ClaudeBot alone, though I say "Claude's bots" in the video. Claude-User came another 7 times,
  but that one only fires when someone asks Claude something, and my own 50 baseline questions to
  Claude sit in the same 24 hours. So I left it out.
- Half of the 32 were robots.txt (9) and the sitemap (7).
- The path list only has the busiest paths. It covers 26 of ClaudeBot's 35 requests, counting two
  redirects and a 404, and `/bosham/` isn't one of the 26. So I can't show ClaudeBot read the page
  Claude cited.
- Treat the counts as a floor. My counter kept only Cloudflare's top 500 request groups, which
  dropped crawlers with one or two hits. These come from a recount on 22 Oct after I fixed that.

## Is that why?

Maybe not. GPTBot read `/bosham/` twice in that window and ChatGPT still didn't cite it. Three answers
isn't a trend either, least of all from a run that fell over part way. The full re-check runs on
2 Nov 2026 and goes in [`../001-aeo-baseline/results/`](../001-aeo-baseline/results/).

## Files

- `questions.txt`: the nine questions, all from [001's list](../001-aeo-baseline/questions.txt).
- `results/weekly-2026-10-19/answers.jsonl`: every answer with its raw API response, in the same
  format as 001, plus the failed calls. The encrypted reasoning some models send back is removed, and
  each failed call keeps only the error's message. Gemini's redirects are stored with each answer.
- `results/weekly-2026-10-19/answers.csv`: the same thing as a table.
- `crawlers-24h-to-2026-10-19.csv`: requests per crawler and status.
- `crawler-paths-24h-to-2026-10-19.csv`: requests per crawler and path, busiest paths only.

## Check it yourself

From this folder, offline and free:

```
python ../001-aeo-baseline/check.py count results/weekly-2026-10-19 --site southcoasthouseprices.co.uk
```

It should say 25 answers, 9 failed or skipped, and my site cited in 3.

For the crawlers I use Cloudflare's GraphQL Analytics API: `httpRequestsAdaptiveGroups`, filtered with
`userAgent_like` on each bot's name, grouped by user agent, status and path. Set the limit high, or
you'll make my mistake.
