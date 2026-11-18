# 008: Is AI code reliable?

Claude built the [free courses on my site](https://georgebracher.com/courses/) and every one of its
own checks passed: 11 unit tests, 1,037 answer checks with 0 wrong, and 20 out of 20 browser checks
in Chrome's and Safari's engines. Then I gave it to Codex, a different AI, with a written ticket
(it's in [009](../009-how-do-i-use-claude-code/ticket.md)) and told it to break it.

It found four bugs, all in the Stop button:

| What you did | What happened |
|---|---|
| Pressed Stop while your answer was being checked | Nothing. Run and Stop were both off until the 15 second limit. |
| Pressed Stop on a SQL query that never ends | Stop stayed greyed out until SQL's own guard gave up. |
| Pressed Stop before Python had finished loading | Your endless loop ran anyway once Python was ready. |
| Moved to the next step while a check was running | The old check kept running in the background. |

My own tests did press Stop, on an endless loop while it was running. Just never at those moments.
All four were fixed the same afternoon, each with a browser test.

## The tests

These are the browser tests from the site's repo, run with [Playwright](https://playwright.dev/python/)
against any copy of the courses, including the live one. The only change from the private copy is
that they download `courses.json` from the site they're testing.

| File | Checks | What it does |
|---|---|---|
| [`courses_e2e.py`](courses_e2e.py) | 20 | Claude's original checks: a first step, a wrong answer, a syntax error, input(), Stop on a running loop, the 15 s limit, SQL, hints, progress after reload, phone width. |
| [`courses_adversarial_e2e.py`](courses_adversarial_e2e.py) | 48 | Break it like a beginner: typing ahead, endless output, deep recursion, `os._exit`, bare `except`, a step from every SQL lesson, `DROP TABLE`, every step type, storage that throws (private windows). Codex's first run went 47 of 48. |
| [`courses_cancel_e2e.py`](courses_cancel_e2e.py) | 9 | Stop during a check, during SQL, during loading, and moving away mid-check. |

48 plus 9 is the 57 new tests in the video, each passing in both engines.

```
pip install playwright && playwright install chromium webkit
python courses_cancel_e2e.py https://georgebracher.com chromium
python courses_cancel_e2e.py https://georgebracher.com webkit
```

Each prints PASS or FAIL per check. Read the counts, not the exit code.

The page is [georgebracher.com/008](https://georgebracher.com/008/). The script is
[`scripts/008-is-ai-code-reliable.md`](../../scripts/008-is-ai-code-reliable.md).
