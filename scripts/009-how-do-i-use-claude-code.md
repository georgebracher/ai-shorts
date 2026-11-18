---
slug: 009-how-do-i-use-claude-code
title: How do I use Claude Code?
steps:
  - label: One project per window
    trigger: one
  - label: A rules file it reads first
    trigger: two
  - label: A handoff note for next time
    trigger: three
  - label: Tickets, not chats
    trigger: four
stats:
  - {label: Words in the ticket, value: "1,073", trigger: a thousand words}
  - {label: Bugs it found, value: "4", trigger: four bugs}
sources: George's own setup, described as method only (no tooling, paths or machines named). One project per window; his standing rules say one project per editor pane, and a session loads only the project he names. Rules file; his global rules file is capped at 8,192 bytes (8,189 on 16 Nov) and its Learning section says "merge new rules into old ones", hence "every new rule has to push out an old one". Handoff note; every registered project keeps docs/NEXT-SESSION.md (39 projects on 16 Nov) with the next action, blockers and checks, read at session start. Tickets; for big or outside jobs Claude writes a ticket another session or another AI (Codex) runs cold. The example ticket is georgebracher-com docs/tickets/2026-11-11-codex-courses-audit.md, 1,073 words (wc -w), sections What shipped, Part A does it work, Part B does it leak, Rules, Report back; a privacy-edited copy is public at https://georgebracher.com/009/ticket.md. Quote; "Treat these as claims to re-run, not as facts." (exact). Report back asks for "the result you read (counts, not "passed")". Rules section forbids deploy, push and commits, and says list judgment calls rather than change them, hence "what it's not allowed to touch". It found four Stop/cancel bugs (report section 2), the subject of 008, so 009 posted after 008. Demand 16 Nov; "how to use claude code" 434 Bing searches over 25 weeks, Google suggests it. Page: https://georgebracher.com/009/
---
How do I use Claude Code? AI writes all my code, so this is how I keep it on track.
One. One project per window. It only loads the project I name.
Two. A rules file it reads first. Mine's capped, so every new rule has to push out an old one.
Three. A handoff note. It writes down where it stopped, so the next session doesn't start from zero.
Four. Tickets, not chats. For big jobs it writes a ticket, so another session, or another AI, can pick it up cold.
What goes in a ticket? What was built, what to check, what it's not allowed to touch, and how to report back.
The one for my courses was about a thousand words. One line in it: "Treat these as claims to re-run, not as facts."
That ticket found the four bugs in my Stop button.
Biggest lesson? Make it give you numbers, not "passed".
The tickets are on my site. Steal it.
