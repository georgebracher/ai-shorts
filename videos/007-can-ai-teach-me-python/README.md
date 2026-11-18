# 007: Can AI teach me Python?

My syntax is rusty, because AI writes all my code. So before a long flight I had AI write me
coding courses instead: four courses, 535 steps, running offline on my laptop, that check the code
you type instead of writing it for you.

| Course | Steps |
|---|---|
| Python from zero | 211 |
| Read the code your AI writes | 65 |
| SQL from zero | 124 |
| Terminal and Git from zero | 135 |

Over the trip I finished 55 steps (the first four lessons and most of the fifth): 60 checks, 39
passed, 10 hints, 5 answers looked at. That's one learner, me, so it's not a study.

The step I got stuck on was lesson 4's boarding card: 7 wrong tries and 2 hints, then I looked at
the answer and still got it wrong 4 more times. Eight minutes. The fix was an f-string:

```python
print(f"It's {hours * 60} minutes to landing")
```

## Where the code is

Three of the four courses now run free in your browser at
[georgebracher.com/courses](https://georgebracher.com/courses/), with the same checker. Nothing to
install, no account. Terminal and Git comes later. The page runs entirely in your browser, so
everything it runs is public as served:

- [`app.js`](https://georgebracher.com/courses/app.js): the course front end, with Run, Stop, the 15 s limit and input().
- [`worker.js`](https://georgebracher.com/courses/worker.js): Python (Pyodide) in a Web Worker, plus SQLite for the SQL course.
- [`engine.py`](https://georgebracher.com/courses/engine.py): the answer checker, copied from the offline pack.
- [`courses.json`](https://georgebracher.com/courses/courses.json): every lesson, step, hint and answer.

The script is [`scripts/007-can-ai-teach-me-python.md`](../../scripts/007-can-ai-teach-me-python.md),
with every number and where it came from in its `sources` line. [008](../008-is-ai-code-reliable/)
is what happened when a second AI tried to break the browser version.
