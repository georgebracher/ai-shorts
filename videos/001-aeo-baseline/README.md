# 001: Will AI ever cite my website?

The first video asks whether a brand-new website can get cited by AI answer engines. This folder
holds everything behind its numbers.

## What I did

On 18 Oct 2026 I launched [southcoasthouseprices.co.uk](https://southcoasthouseprices.co.uk/),
plain-English house price pages for villages around Chichester built from open data. The same day
I asked ChatGPT, Claude, Gemini and Perplexity 50 questions about house prices in ten of those
places. All 200 answers came back within ten minutes.

| | Answers citing it |
|---|---|
| rightmove.co.uk | 104 |
| zoopla.co.uk | 37 |
| housesforsaletorent.co.uk | 21 |
| ons.gov.uk | 20 |
| onthemarket.com | 19 |
| southcoasthouseprices.co.uk | 0 |

It cost $7.19 through OpenRouter.

## Files

- `questions.txt`: the 50 questions, fixed before the run, when only one of the ten places
  (Bosham) had a page. Five questions each: average price, going up or down, expensive or not,
  flooding, sales a year. The wording is frozen so later runs compare like with like.
- `check.py`: asks the questions and counts citations. One file, standard library only.
- `results/baseline-2026-10-18/answers.jsonl`: every answer with its raw API response, so anyone
  can re-count it, with two edits. The encrypted reasoning some models send back is removed: only
  the model's maker can read it, and the count never uses it. Two off-topic search results that
  Perplexity returned but did not use are blanked (`about:blank#unrelated-result-removed`), in the
  raw response and in that answer's `returned` list. Nothing any answer cited was touched.
- `results/baseline-2026-10-18/answers.csv`: the same answers as a table: question, engine, model,
  whether my site was cited, the domains cited.

## How it asks

Every engine goes through OpenRouter with web search on, one new chat per question:

| Engine | Model |
|---|---|
| ChatGPT | `openai/gpt-6-sol` |
| Claude | `anthropic/claude-sonnet-5.5` |
| Gemini | `google/gemini-3.5-flash-lite` |
| Perplexity | `perplexity/sonar-pro` |

These are the API models, not the consumer apps, and each question was asked once. Answers vary
from run to run, so treat any single answer as a sample.

## Where the baseline came from

I collected the baseline on 18 Oct 2026 with the citation checker that runs South Coast House
Prices' own measurement. `check.py` is a standalone port of it: the same four models through
OpenRouter, the same web search setting and, since a recount from the saved payloads on 20 Oct,
the same rule for what counts as cited. The baseline file was converted from those saved payloads,
so its row order and per-question timestamps differ from what `check.py` writes. The questions
were asked one after another within the ten minutes, four engines at a time.

## What counts as cited

A domain counts once per answer if the answer itself references it. ChatGPT, Claude and Gemini
attach each source to the part of the answer it supports, so all of those count. Gemini's links
are redirects, resolved to the real page when the answer came in. Perplexity hands back every
search result it looked at (about 27 an answer) and marks the ones it used with [n] in the text,
so only the marked ones count.

My first count missed that and counted every Perplexity result, which put Rightmove in 122
answers. Re-counting the saved answers on 20 Oct gave 104. The video uses 104.

## Run it yourself

```
export OPENROUTER_API_KEY=...
python check.py ask questions.txt --site yoursite.co.uk --out results/my-run --cap 10
python check.py count results/baseline-2026-10-18 --site southcoasthouseprices.co.uk
```

Expect about $0.14 a question across all four engines. Each answer is saved to `answers.jsonl`
as it lands, and `answers.csv` is written beside it in the baseline's columns. If a run stops part
way, run the same command with `--resume` and it asks only what's missing. Without `--resume`,
`ask` won't touch a folder that already holds a run. It exits with an error if any call failed or
the cap stopped it.

`--cap` limits what one `ask` spends. Before each call it holds back $0.50 (the dearest of the
200 baseline answers cost $0.12) and starts the call only if what's been spent plus everything held
still fits under the cap. Each answer is then charged at the cost OpenRouter reports. A failed call
stays charged at $0.50, since it may have been billed. So a run can only pass the cap if a single
answer costs more than $0.50, and then only by that excess on the calls already running, four at
most. No new call starts after that. For a limit OpenRouter enforces itself, give the run its own
key with a credit limit.

`count` re-scores a saved run from its raw responses without paying for anything or going online.
Gemini's redirects were resolved when the answers came in and are stored with each answer.
`--resolve` looks up any that weren't, though old ones may have expired.

## What happens next

I re-ask the same questions as new pages go up and add each run here as its own folder under
`results/`. The first full re-check is on 2 Nov 2026, two weeks after the baseline.

Will it work? No idea yet.
