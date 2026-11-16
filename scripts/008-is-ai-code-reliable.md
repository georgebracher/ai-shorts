---
slug: 008-is-ai-code-reliable
title: Is AI code reliable?
steps:
  - label: Don't let it mark its own homework
    trigger: one
  - label: '"It passed" is a claim'
    trigger: two
  - label: Break it like a beginner
    trigger: three
  - label: Every bug gets a test
    trigger: four
stats:
  - {label: Bugs found, value: "4", trigger: four bugs}
  - {label: New tests, value: "57", trigger: fifty-seven}
sources: georgebracher-com docs/tickets/2026-11-11-codex-courses-audit.md (ticket, written by Claude for Codex, GPT-6 Astra, effort xhigh) and docs/tickets/2026-11-11-codex-courses-audit-REPORT.md. Claude built the courses page (2e4a4d4, live 11 Nov 14:05 +07). Claude's own checks before the audit; pytest 11 passed, 1,037 fixtures 0 wrong in CPython and Pyodide, e2e 20/20 in chromium and webkit on localhost and live. Ticket line; "Treat these as claims to re-run, not as facts." Ticket Part A step 3 is "Try to break it the way a beginner would" (input typed early, endless loops, Stop). Codex re-ran every declared check (all passed again), then its adversarial test went 47/48, failing Stop during checking. Report section 2, four bugs, all Stop/cancel; (1) Stop disabled while the answer is being checked, Run and Stop both off until the 15 s timeout; (2) SQL query can't be stopped; (3) Stop before Python finishes loading, the cancelled loop still runs after boot (2 pending jobs live); (4) navigating away leaves the checker running. The original e2e did press Stop (tests/courses_e2e.py line 80, Stop on an endless loop during a run), never during checking, SQL or loading, hence "never at the wrong moment". Fix 740af1f, 11 Nov 17:08 +07, same afternoon, live and e2e-checked (georgebracher-com handoff). New tests; tests/courses_adversarial_e2e.py 48 plus tests/courses_cancel_e2e.py 9 = 57, each passing in chromium and webkit. "Over a thousand checks" is said instead of 1,037 to dodge the whisper number bug (170 heard as "170. 70." on 006). Demand 16 Nov (georgebracher-com kb/research/demand-2026-11-16.json); Google suggests "is ai code reliable" and "how to check ai generated code"; "codex vs claude" 49 Bing searches over 25 weeks, "ai code review" 37.
---
Is AI code reliable? Claude built the courses on my site, and all its tests passed.
Over a thousand checks. Zero wrong. Then I gave it to Codex and told it to break it.
One. Don't let it mark its own homework. A different AI checks it.
Two. "It passed" is a claim. Run every test again and read what it says.
Three. Break it like a beginner would. Endless loops, typing too early, hitting Stop.
Four. Every bug it finds gets a test, so it can't come back.
What did it find? Four bugs, all in the Stop button.
Hit Stop while it's marking your answer, and nothing happens. Stop it before Python loads, and it runs your endless loop anyway.
My tests did press Stop. Just never at the wrong moment.
Fixed the same afternoon, with fifty-seven new tests.
So is AI code reliable? Once a second AI has had a go at it. The courses are on my site. Go and try to break them.
