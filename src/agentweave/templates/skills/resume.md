---
name: resume
description: Rehydrate context from a handoff file written by /handoff and continue the work. Use at the start of a fresh session, after clearing or compacting, or when the user says "resume", "pick up where we left off", "continue from the handoff", or points at a handoff file. Pairs with /handoff.
---

Restore working context from a durable handoff, verify that it still describes reality, and
continue from its first valid next step.

## 1. Locate the handoff

Use a path supplied by the user. Otherwise inspect all supported locations:

```bash
cat .handoffs/LATEST.md .claude/handoffs/LATEST.md .agents/handoffs/LATEST.md 2>/dev/null
ls -t .handoffs/*.md .claude/handoffs/*.md .agents/handoffs/*.md 2>/dev/null | head -5
```

Read the newest artifact. If handoffs exist in multiple directories, reconcile timestamps and say
that the chain is split. Follow `Previous handoff` only when the current next step needs older
context.

If no handoff exists, say so and ask what to work on. Do not invent state from Git history.

## 2. Verify against the repository

Run:

```bash
git branch --show-current
git log --oneline -5
git status --short
```

Compare this with the handoff's Git state:

- Same branch, HEAD, and dirty paths: proceed.
- HEAD moved forward: inspect `git log <handoff-sha>..HEAD --stat` and determine which next steps are
  already complete.
- Different branch: report it before changing anything and obtain direction if the intended branch
  is ambiguous.
- Touched files are now clean or missing: determine whether they were committed, moved, reverted,
  or stashed; do not guess.

Verify that paths under `Files touched` and `Read on resume` still exist.

## 3. Reload only immediate context

Read the files listed under `Read on resume` plus files needed by next step 1. Do not bulk-load every
artifact mentioned in the handoff.

Re-establish `Constraints and user directives` and `Dead ends` before taking action. Treat quoted
directives as binding until the user withdraws them.

## 4. Confirm and continue

Briefly report:

1. Current state.
2. Drift since the handoff, or that the tree matches.
3. Constraints still in force.
4. The concrete next action.

Then perform that action. Ask first only when the handoff contains an open user question or drift
makes the recorded next step unsafe or ambiguous.

When this session later needs compaction, use `/handoff` again so the next artifact is rebuilt from
live state rather than from a chain of summaries.
