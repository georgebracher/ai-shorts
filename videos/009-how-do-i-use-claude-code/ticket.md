# Ticket: audit the public courses page (does it work, does it leak)

<!--
  The real ticket Claude wrote for Codex on 11 Nov 2026, from georgebracher.com/009/.
  Edited for privacy only: my file paths, machine names, and the list of private names and
  accounts in Part B are swapped for generic ones. Everything else is as sent. Steal it.
-->

Repo: georgebracher-com (run `git -C` against it, confirm with `git rev-parse --show-toplevel`).
Written 11 Nov 2026 by Claude (Opus 5.5) for Codex (GPT-6 Astra, effort xhigh).

## What shipped

georgebracher.com/courses/ went live on 11 Nov 2026 (commit 2e4a4d4). It is George's private offline course pack
(three courses: Python from zero, Read the code your AI writes, SQL from zero; 33 lessons, 400 steps) rebuilt to run
in a stranger's browser:

- `site/courses/index.html`: page shell, styles, static course list for search engines, JSON-LD.
- `site/courses/app.js`: the pack's own front end, with its server calls answered in the tab (see the
  `web_runtime` section near the top: PY worker controller, runs, input() by replay, Stop, 15 s limit, localStorage,
  PostHog `track`).
- `site/courses/worker.js`: Pyodide 0.29.5 in a Web Worker, loads `engine.py`, sqlite3 on demand.
- `site/courses/engine.py`: the pack's checker (copied from its serve.py) plus a sandbox-free `execute`.
- `site/courses/courses.json`: built by `tools/build_courses.py` from the offline pack's
  `engine/courses.json` with a list of exact text swaps (SWAPS, BODIES, LEFTOVERS).
- `site/courses/pyodide/0.29.5/`: self-hosted upstream Pyodide files plus NOTICE.txt.
- `site/_headers`: /courses/* CSP (`'wasm-unsafe-eval'`, `worker-src 'self'`), immutable cache on pyodide/.
- Wiring: `site/index.html` card, `site/007/index.html`, `site/llms.txt`, `site/sitemap.xml`, `site/privacy/`.
- Tests: `tests/test_courses.py` (pytest), `tests/courses_fixtures.py` + `tests/courses_pyodide.mjs` (1037 fixtures:
  every step's solution, accepted alternatives and known-wrong tries, checked in CPython and in Pyodide under Node),
  `tests/courses_e2e.py` (Playwright, 20 browser checks against a URL).

Claude's own checks so far: pytest 11 passed; fixtures 1037, 0 wrong in both engines; e2e 20/20 in chromium and
webkit on localhost and on the live site. Treat these as claims to re-run, not as facts.

## Part A: does it work

1. Re-run the declared checks and read the output, not the exit code:
   `python3 -m pytest -q tests` (system python3 has pytest; the .venv does not), then
   `node tests/courses_pyodide.mjs`.
2. Serve `site/` locally (`python3 -m http.server 8765 -d site`, foreground with a timeout or kill it after) and run
   `python3 tests/courses_e2e.py http://localhost:8765 chromium`, then `webkit`. Note: local http.server does not
   apply `_headers`, so CSP is only tested live; run e2e against `https://georgebracher.com` too (it opts out of
   analytics via `localStorage.gbc_no_analytics`).
3. Try to break it the way a beginner would, in a real browser via Playwright. At least:
   - input(): typing ahead before the prompt shows, typing more lines than the program asks for, input() inside a
     loop, a program that prints random numbers then asks for input (replay must keep the same seed).
   - Stop and the 15 s limit during a run, during a check, and while waiting for input; then Run again at once.
   - Huge output (`while True: print("x")`), deep recursion, `import os; os._exit(0)`, `sys.exit()`, bare
     `except:` around an endless loop, writing files then running again (fresh folder each run?).
   - SQL: a step from each SQL lesson, a syntax error, `DROP TABLE` then Run again (is the DB fresh?).
   - Progress: finish a step, reload, clear localStorage, private window (storage throws).
   - Every step type in the data (`code`, `choice`, `predict`, any others in courses.json) renders and can be passed.
   - Phone width 390 px: no sideways scroll, footer does not cover the editor or buttons.
4. Spot-check that the checker is the pack's: diff the shared functions in `site/courses/engine.py` against
   the offline pack's `engine/serve.py` (they were meant to be copied verbatim).
5. Live headers: `curl -sI https://georgebracher.com/courses/` and `/courses/pyodide/0.29.5/pyodide.asm.wasm`.
   Exactly one Content-Security-Policy header on /courses/, wasm served as `application/wasm`, cache rule present.

## Part B: does it leak anything of George's

The site is public. Look for anything that is George's private life or setup rather than the course. Check three
places: the repo working tree, the committed history (`git log -p` for commit 2e4a4d4 and later), and what the live
site actually serves (fetch it, do not trust the repo).

Look for at least:
- Names and handles: his usernames, any email address, other people's names from his life. A test name used in
  the lessons is fine. "George" only where the page speaks as George on purpose.
- Paths and machines: home folder paths, download folders, the offline pack's own name, his machine names,
  hostnames, IPs, ports of his own services.
- Accounts and secrets: tokens, API keys, PostHog keys other than the site's existing public project key, chat bot
  names or chat ids, hosting accounts, GitHub orgs other than the public one, client or company names.
- His location (must not appear in public content), his employer, anything from his other private repos.
- courses.json strings in all fields (not only `body`: hints, solutions, tests, files, db seed data, alt answers).
  The Read-the-code course was re-voiced into George's first person (his own tools and computers come up as
  examples); judge whether each of those gives away more than a reader needs.
- `engine.py`, `app.js`, `worker.js`, `index.html` comments, which mention the offline pack and George's computer.
- The pyodide/ folder: only upstream files plus NOTICE.txt, nothing extra.
- Analytics: confirm `track()` never sends code, typed input or output (only step key, ok, hint number), and that
  nothing else posts typed text anywhere (search for fetch/XHR/sendBeacon/WebSocket in app.js and worker.js).

`tools/build_courses.py` is in the repo (not served). It names the source path and quotes the private wording it
replaces. Say whether that is acceptable in a public GitHub repo, or whether the repo is private (check with
`gh repo view --json visibility` using the account that owns this project).

## Rules

- Audit first. Fix only clear bugs or clear leaks, each with a test or a re-run that shows the fix. For anything that
  is a judgment call (wording, what counts as too personal), list it, do not change it.
- Course text changes go through `tools/build_courses.py` (SWAPS/BODIES) and a rebuild, never hand edits to
  courses.json. Rebuild then re-run the fixtures.
- No deploy, no push, no commits unless George says so. No secrets in output. Delete to the trash, never `rm -rf`.
  No em dashes in any text you write.
- Network commands in the foreground with a timeout.

## Report back

Write `docs/tickets/2026-11-11-codex-courses-audit-REPORT.md`:
1. Each check you ran, the command, and the result you read (counts, not "passed").
2. Bugs found: steps to reproduce, severity, fixed or not, and the test that proves it.
3. Leaks found: exact string, file or URL, why it matters, fixed or not.
4. Judgment calls for George, one line each.
5. `git status --short` at the end, with every changed file named.
