---
name: status
description: Compile today's progress into a Progress.md entry — reads git log + recent changes and writes the "Keep Thinking" evolution story judges want to see. Playbook §16.1.
---

# /status

Runs at end of day (or on demand). Turns the work Grace already did today
into the source material for the Progress.md "Keep Thinking" narrative and
the README v0→v5 section.

## Steps

1. `git log --since="5am today" --pretty=format:"%h %s"` to list today's
   commits.
2. `git diff --stat HEAD@{5am}` to see what files changed and by how much.
3. Scan for new/changed files in `app/agents/`, `app/tools/`,
   `.claude/skills/` — these signal capability expansion.
4. Review the playbook's day-by-day plan (§11) against actual progress.
5. Append a dated section to `Progress.md` with the sections below.

## Output format (append to Progress.md)

```
## {YYYY-MM-DD} — {one-line headline}

**Shipped today**
- {bullet list of completed capabilities, not just files}

**What evolved (Keep Thinking)**
- {what we thought we'd build this morning vs. what we actually built}
- {surprises from real testing or user research}

**Cut from today's plan**
- {bullet list of what moved to tomorrow and why}

**Tomorrow's top 3**
1. {}
2. {}
3. {}

**Open questions / risks**
- {}
```

## Don'ts

- Don't pad entries. A 3-bullet day is fine if that's the real shape.
- Don't write WHAT the code does (the diff shows that). Write WHY the
  day's direction makes sense in the arc of the project.
- Don't invent user quotes or testimonials. If Grace ran a user test,
  reference the actual notes — otherwise leave it out.
