---
slug: 007-can-ai-teach-me-python
title: Can AI teach me Python?
steps:
  - label: Make it check your work, not do it
    trigger: one
  - label: Small steps
    trigger: two
  - label: Hints before answers
    trigger: three
  - label: Set it in your own life
    trigger: four
stats:
  - {label: Wrong tries, value: "7", trigger: seven wrong tries}
  - {label: Steps done, value: "55", trigger: fifty-five}
sources: ~/Downloads/"Flight pack 3 Nov" (built 3 Nov in Claude and Codex sessions, so the script says AI, not one model). engine/courses.json, 4 courses, 535 steps (Python from zero 211, Read the code your AI writes 65, SQL from zero 124, Terminal and Git from zero 135), Python from zero 16 lessons, its own estimate 8 to 10 hours. Runs offline (engine/serve.py, local server, Mac sandbox). Lessons run 8 to 23 steps, median 12 over all 41 lessons; the five George did were 8, 12, 12, 12, 12. Every code step has two hints, then the answer (steps' hints and solution fields). Examples about the flight; l04 step 12 "A boarding card", l05 step 10 "A seat calculator". engine/state/progress.json; 55 steps done 3 to 4 Nov (l01 8 of 8, l02 to l04 12 of 12 each, l05 11 of 12). engine/state/usage.jsonl; 60 checks, 39 passed, 10 hints, 5 answers shown. The stuck step; python-zero/l04_text/11 (lesson 4 Working with text, step 12 of 12, "A boarding card"), 4 Nov 07:54 to 08:02 UTC, 7 failed checks, 2 hints, answer shown at 07:59:59, then 4 more failed checks, passed 08:02:30. The fix; f before the quotes, {name} {len(name)} {seat} {hours * 60} inside, double quotes outside because of "It's". "Really good" is George's verdict, 9 Nov. Demand 10 Nov (georgebracher-com kb/research/demand-2026-11-10.json); Google suggests "can ai teach me python"; "f string python" 420 Bing searches over 25 weeks, "how to learn python" 461. The closing line is true only once georgebracher.com hosts the courses in the browser (Python, Read the code and SQL first; Terminal and Git may come later, so the line says "courses", not "all four").
---
My syntax is rusty, because AI writes all my code. So before a long flight I got AI to teach me instead.
Four courses, five hundred and thirty-five steps, and it all runs offline.
One. Make it check your work, not do it. I type, it runs my code and tells me what's wrong.
Two. Small steps. About a dozen a lesson.
Three. Hints before answers.
Four. Set it in your own life. Mine were boarding cards and seat numbers.
Where did I get stuck? Lesson four. A boarding card.
The f goes outside the quotes. The curly brackets go inside. And "it's" means double quotes.
Seven wrong tries. Then it showed me the answer, and I got it wrong four more times.
Fifty-five steps in. Was it any good? Really good.
The courses are on my site, and they run in your browser. You don't have to DM me for those either.
