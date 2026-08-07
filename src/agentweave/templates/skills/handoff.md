---
name: handoff
description: Compact the session by writing a durable, structured handoff file to disk before clearing or compacting. Use when context is filling up, when finishing a work chunk, before clearing/compacting the session, or when the user says "handoff", "save context", "compact", "wrap up this session", or "I'm going to start a fresh session". Pairs with /resume.
---

Write a durable handoff artifact so this session's state survives a context reset.

The file on disk is the real memory. Re-derive it from the live repository and conversation; do
not summarize an older summary from memory.

## 1. Choose the move

- Finished a chunk and the next step is different work: write a full handoff, then recommend a
  fresh context.
- Mid-task with substantial stale debugging context: write a full handoff, then recommend compacting
  with explicit steering.
- Context is still small and relevant, and the user did not ask for a handoff: do nothing.
- The user explicitly asked for a handoff: always write one.

State the choice in one line before proceeding. Do not clear or reset context yourself.

## 2. Gather hard state

Run the equivalent commands for the current shell:

```bash
git branch --show-current
git status --short
git log --oneline -8
git diff --stat HEAD
git log origin/$(git branch --show-current)..HEAD --oneline
```

Find the newest previous handoff across every supported location:

```bash
cat .handoffs/LATEST.md .claude/handoffs/LATEST.md .agents/handoffs/LATEST.md 2>/dev/null
ls -t .handoffs/*.md .claude/handoffs/*.md .agents/handoffs/*.md 2>/dev/null | head -5
```

If a previous handoff exists, read it and carry forward only facts that remain true.

## 3. Write the handoff

Keep using the existing handoff directory so the chain is not split. If none exists, create
`.handoffs/`.

Write `YYYY-MM-DD-HHMM-<short-slug>.md` using the real current time. Write or replace `LATEST.md`
in that directory with only the new handoff's relative path.

Use every section below. Write `None.` rather than omitting an empty section.

```markdown
# Handoff: <one-line title>

**Date:** <ISO datetime> · **Branch:** <branch> · **HEAD:** <short sha>
**Agent:** <agent/runtime that wrote this>
**Previous handoff:** <relative path or "none — first handoff">
**Status:** <in progress | blocked | chunk complete>

## Goal
The outcome and why it matters.

## Current state
What works, what is incomplete, and the exact boundary.

## Files touched
Every changed path and what changed.

## Key decisions
Each decision, its reason, and rejected alternatives.

## Constraints and user directives (verbatim)
Exact quotes of instructions that remain binding.

## Dead ends
Failed approaches and symptoms.

## Verification
Exact commands and results, followed by what was not tested.

## Git state
Branch, HEAD, dirty paths, and upstream state from live commands.

## Next steps
Numbered; step 1 must be directly executable with no hidden decision.

## Open questions for the user
Anything that genuinely requires user direction.

## Read on resume
Three to six paths needed for the immediate next action.
```

## 4. Validate and report

Re-read the artifact and confirm:

- Every path exists or is explicitly marked to be created.
- Files touched accounts for `git status --short` and `git diff --stat`.
- No fact depends on this conversation being visible later.
- User directives are quoted, verification distinguishes tested from untested, and next step 1 is
  executable by a different agent.

Report the handoff path, a short digest, and exactly one recommendation: start fresh and run
`/resume`, or compact with explicit steering.
