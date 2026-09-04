---
name: resume
description: Rehydrate context from the latest numbered handoff file written by /handoff and continue the work. Picks the highest handoff number in the chain. Use at the start of a fresh session, after clearing or compacting, or when the user says "resume", "pick up where we left off", "continue from the handoff", or points at a handoff file. Pairs with /handoff.
---

Restore working context from a durable handoff file, verify it still describes reality, and
continue.

**Usage:** `/resume` (loads the highest-numbered handoff) or `/resume <path-to-handoff.md>`.

Agent-agnostic: the handoff is plain markdown, so a session started by one CLI agent can be
resumed by another. The handoff's `**Agent:**` field records the model, the CLI and the
posture that wrote it — note it if the tooling assumptions differ from yours, and say so out
loud when the model changed, since that is the most common reason the previous session's style
or judgment does not match what you would have done.

## Step 1 — Locate the latest handoff

If a path was given as an argument, use it. Otherwise list every known location — the previous
session may have run under a different agent:

```bash
ls .handoffs/handoff-*.md .claude/handoffs/handoff-*.md .agents/handoffs/handoff-*.md 2>/dev/null
```

**The highest `NNNN` is the newest handoff.** Numbering is the authority: file mtimes do not
survive a clone, a copy, or a checkout.

If a `LATEST.md` pointer exists, read it as a **cross-check, not as the answer**. If it
disagrees with the highest number, say so and prefer the number — a stale or unreachable
pointer is a known failure mode, especially where the pointer is tracked in version control
and the handoff it names is not.

Then read that file. If you need more history, follow its `**Previous handoff:**` link — only
as far as the current next-step requires, usually zero or one hop.

Two things to flag rather than silently absorb:

- **Handoffs in more than one directory** → the chain has been split, and the newest file may
  not be the newest *work*. Reconcile before trusting either.
- **A gap in the numbering, or handoffs that stop partway** → check whether the missing ones
  are untracked rather than absent. A partially tracked chain hands a clone the newest
  *tracked* handoff, which reads as entirely legitimate while being weeks stale.

If no handoff exists anywhere, say so plainly and ask what the user wants to work on. Do not
invent context or guess from git history alone.

## Step 2 — Verify the handoff against reality

A handoff is a snapshot; the tree may have moved. Check before trusting it:

```bash
git branch --show-current
git log --oneline -5
git status --short
```

Compare against the handoff's `## Git state`:

- **Same branch, same HEAD, same dirty files** → trustworthy, proceed.
- **HEAD moved forward** → someone (possibly another session, possibly another agent)
  committed since. Run `git log <handoff-sha>..HEAD --stat` and reconcile: the handoff's
  "next steps" may already be done. Flag anything that no longer applies.
- **Different branch** → say so before doing anything. Confirm which branch the work belongs on.
- **Files listed as touched are now clean/absent** → the work was committed, stashed, or
  reverted. Determine which; do not assume.

Also verify the paths in `## Files touched` and `## Read on resume` still exist.

**Check what the previous session left running.** Read `## Environment left running` and
confirm each entry is still in the state the handoff claims — a server it started may have
died, or may still be holding the port you are about to bind. Starting a second one is the
common failure. An unattended job left enabled is the expensive one.

**Verify claims, do not inherit them.** A handoff records what the previous session *believed*
it had finished. Where the next step builds on that, confirm the work still functions rather
than trusting the claim — especially anything the handoff's own `## Verification` section
lists as not tested.

State any drift you found in one or two lines. Silent reconciliation is how a resumed session
redoes finished work.

## Step 3 — Reload only what the next step needs

Read the files under `## Read on resume`, plus any file that next-step-1 will edit.

**Do not** bulk-read everything the handoff mentions. The point of a fresh window is that it
is fresh — refilling it with context you will not use recreates the exact problem the handoff
solved. Load lazily; you can always read more later.

## Step 4 — Re-establish the guardrails

Before touching anything, internalize `## Constraints and user directives` from the handoff,
and read **`<handoff-dir>/DEAD-ENDS.md`** if it exists.

These are what a fresh window loses most damagingly: without them a resumed session cheerfully
violates a stated rule or re-pays for a known failure. Treat quoted user directives as still
binding — they were not withdrawn, just forgotten.

`DEAD-ENDS.md` is the durable ledger; the handoff's own `## Dead ends` section holds only what
that session hit. Read both, and **verify before trusting a ledger entry that carries an old
date** — a stale entry is worse than a missing one, because it is believed.

## Step 5 — Confirm and continue

Report back, briefly:

1. **Where we are** — one or two sentences from `## Current state`.
2. **Drift** — anything that changed since the handoff, or "tree matches the handoff".
3. **Environment** — what the handoff left running and whether it is still up.
4. **Constraints still in force** — the quoted directives, condensed to a list.
5. **Next action** — restate next-step-1 concretely, as you are about to do it.

Then do it. If the handoff has entries under `## Open questions for the user`, or if drift
means the recorded next step no longer makes sense, ask **before** starting work rather than
proceeding on a guess. A question the handoff says has gone unanswered across several sessions
should be put to the user directly now, not carried forward again.

## Chaining

When this resumed session in turn fills up, run `/handoff` again. It will read this handoff
and carry forward what is still true — so state is always re-derived from the live session
plus a durable file, never from a summary of a summary. That is what stops quality decaying
across a long chain of sessions, and it holds across agent switches too.

Durable tool and environment facts do not ride the chain at all: they go to `DEAD-ENDS.md`
once and stay there.
