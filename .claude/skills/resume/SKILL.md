---
name: resume
description: Rehydrate context from the latest numbered handoff file written by /handoff and continue the work. Picks the highest handoff number in the chain. Use at the start of a fresh session, after clearing or compacting, or when the user says "resume", "pick up where we left off", "continue from the handoff", or points at a handoff file. Pairs with /handoff.
---

Restore working context from a durable handoff file, verify it still describes reality, and
continue.

**Usage:** `/resume` (loads the highest-numbered handoff) or `/resume <path-to-handoff.md>`.

Agent-agnostic: the handoff is plain markdown, so a session started by one CLI agent can be
resumed by another. The handoff records the exact **model** and **agent** that wrote it —
note it if the tooling assumptions differ from yours, and say so out loud when the model
changed, since that is the most common reason the previous session's style or judgment does
not match what you would have done.

## Step 1 — Locate the latest handoff

If a path was given as an argument, use it. Otherwise list every known location — the
previous session may have run under a different agent:

```bash
ls .handoffs/handoff-*.md .claude/handoffs/handoff-*.md .agents/handoffs/handoff-*.md 2>/dev/null
```

**The latest handoff is the one with the highest `NNNN` in its filename.** That number is
authoritative. Do not sort by mtime — mtimes do not survive a clone, copy, or checkout — and
do not trust a `LATEST.md` pointer if one is lying around from an older convention; a stale
pointer is exactly how a resumed session loads the wrong history. If you find a `LATEST.md`
that disagrees with the numbering, say so and go with the number.

Then read that file, plus — if you need more than its own contents give you — the one it
names under `**Previous handoff:**`. Follow the chain back only as far as the current next
step requires, usually zero or one hop. Pay attention to `## Corrections to the previous
handoff`: earlier files are never edited, so a correction lives only in the later one.

**Chains not yet adopted:** a directory whose handoffs are all named `YYYY-MM-DD-HHMM-slug.md`
with no number predates the current convention and has not been migrated yet. Resume from the
one with the newest date in its filename (`LATEST.md`, if present, is a hint — verify it
against the dates rather than trusting it). The next `/handoff` run will adopt that same file
as `handoff-0001` and continue from `0002`; mention this so the user knows the chain is about
to be established. If numbered and unnumbered files coexist, the migration already happened —
numbered always wins, and the unnumbered leftovers are pre-chain history.

If handoffs turn up in more than one directory, say so — the chain has been split, and the
highest number in one directory may not be the newest *work*. Reconcile by date and by the
`Iteration commits:` shas before trusting either.

If no handoff exists anywhere, say so plainly and ask what the user wants to work on. Do not
invent context or guess from git history alone.

## Step 2 — Verify the handoff against reality

A handoff is a snapshot; the tree may have moved. Check before trusting it:

```bash
git branch --show-current
git log --oneline -5
git status --short
```

Compare against the handoff's `## Git state` and its `**Iteration commits:**` range:

- **Same branch, HEAD equals the handoff's HEAD, same dirty files** → trustworthy, proceed.
- **HEAD moved forward** → someone (possibly another session, possibly another agent)
  committed since. Run `git log <handoff-sha>..HEAD --stat` and reconcile: the handoff's
  "next steps" may already be done. Flag anything that no longer applies.
- **The iteration commits are absent from history** → the work was rebased, amended, or
  dropped. Establish what happened before writing anything on top of it.
- **Different branch** → say so before doing anything. Confirm which branch the work belongs on.
- **Files listed as touched are now clean/absent** → the work was committed, stashed, or
  reverted. Determine which; do not assume.

Also verify the paths in `## Files touched` and `## Read on resume` still exist.

State any drift you found in one or two lines. Silent reconciliation is how a resumed session
redoes finished work.

## Step 3 — Reload only what the next step needs

Read the files under `## Read on resume`, plus any file that next-step-1 will edit.

**Do not** bulk-read everything the handoff mentions. The point of a fresh window is that it
is fresh — refilling it with context you will not use recreates the exact problem the handoff
solved. Load lazily; you can always read more later.

## Step 4 — Re-establish the guardrails

Before touching anything, internalize `## Constraints and user directives` and `## Dead ends`
from the handoff. These are the two sections whose loss causes the most damage: without them
a resumed session cheerfully violates a stated rule or re-tries a known failure. Treat quoted
user directives as still binding — they were not withdrawn, just forgotten.

## Step 5 — Confirm and continue

Report back, briefly:

1. **Which handoff** — number, filename, and the model/agent that wrote it.
2. **Where we are** — one or two sentences from `## Current state`.
3. **Drift** — anything that changed since the handoff, or "tree matches the handoff".
4. **Constraints still in force** — the quoted directives, condensed to a list.
5. **Next action** — restate next-step-1 concretely, as you are about to do it.

Then do it. If the handoff has entries under `## Open questions for the user`, or if drift
means the recorded next step no longer makes sense, ask **before** starting work rather than
proceeding on a guess.

If the previous iteration was substantial and has not been reviewed, offer `/review-iteration`
before building on top of it — this window is fresh, which is exactly when a review is cheap
and honest. Building on unreviewed work is how a defect gets buried under three more commits.

## Chaining

When this resumed session in turn fills up, run `/handoff` again. It commits the iteration
and writes the **next** numbered file — it never touches this one — so state is always
re-derived from the live session plus a durable, append-only chain, never from a summary of
a summary. That is what stops quality decaying across a long chain of sessions, and it holds
across agent and model switches too.
