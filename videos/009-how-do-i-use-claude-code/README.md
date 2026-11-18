# 009: How do I use Claude Code?

AI writes all my code. Four habits keep it on track:

1. **One project per window.** Every session starts with nothing loaded and only loads the project I name.
2. **A rules file it reads first.** Mine's capped at 8,192 bytes, so a new rule has to push out an old one or merge into it.
3. **A handoff note.** Every project keeps one file with where it stopped, what's blocked and what's been checked. The next session reads it first.
4. **Tickets, not chats.** For big jobs Claude writes a ticket that another session, or another AI, can pick up cold.

## The ticket

[`ticket.md`](ticket.md) is the real one Claude wrote for Codex on 11 Nov 2026 to audit my free
courses. It's 1,073 words in the original, and it found the four Stop button bugs in
[008](../008-is-ai-code-reliable/). It's edited for privacy only: my file paths, machine names and
the list of private names it was told to hunt for are generic now. Everything else is as sent.
Steal it, and swap my project for yours.

The lines that did the most work:

- "Treat these as claims to re-run, not as facts."
- "the result you read (counts, not "passed")"
- "For anything that is a judgment call (wording, what counts as too personal), list it, do not change it."

The page is [georgebracher.com/009](https://georgebracher.com/009/). The script is
[`scripts/009-how-do-i-use-claude-code.md`](../../scripts/009-how-do-i-use-claude-code.md).
