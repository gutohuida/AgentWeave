---
name: daily-review
description: Read the daily loop's review page, talk the proposed specs through with the operator, and record their decisions so tonight's build window can act on them. Publishes the review page as an Artifact, answers questions about any proposal, applies requested edits to openspec/changes/, and writes spec-queue/APPROVALS.md. Use when the operator says "today's review", "daily review", "review the specs", "what did the loop propose", "approve today's specs", or opens a session after the day window has run. This is the human step of the cycle in openspec/explorations/2026-09-01-a-daily-research-spec-and-build-loop.md; the two scheduled windows either side of it are unattended and cannot ask anything.
---

The daily loop's one human step. Everything either side of it runs unattended and cannot ask a
question, so this is where judgement enters.

Contract for every file named here: `spec-queue/README.md`. Playbooks for the windows either side:
`.claude/loops/`.

## Step 1 — Find out what happened, before opening anything

```bash
powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd'"   # Git Bash date is skewed here
ls -t spec-queue/review/*.html | head -3
git branch --show-current
git log --oneline -15
git status --short
```

Then read, in this order:

1. **The newest review page** in `spec-queue/review/`. If it is not today's, say so in your first
   sentence — the operator is about to make decisions and needs to know they are about a day they
   may not remember.
2. **The bottom** of the newest `.claude/autonomous/*-day-log.md`, for what the window actually did
   versus what the page claims.
3. `spec-queue/APPROVALS.md` — is there already a section for today? Someone may have started.

**If there is no review page at all**, do not improvise one. Report what you found — whether the day
window ran, what its log says, whether `AgentWeaveResearch` produced a file in
`~/.claude/routines/agentweave-research/out/` — and stop. A review page invented here has not been
through the rounds and must not reach `APPROVALS.md`.

## Step 2 — Publish it

Publish the review page as an Artifact and give the operator the link. This is the reason the human
step exists in an interactive session at all: **headless `claude -p` has no `Artifact` tool**
(verified 2026-08-28; no CLI flag provisions one), so the window that wrote the page could not
publish it.

The page is already self-contained and theme-aware. Strip the outer
`<!DOCTYPE>/<html>/<head>/<body>` wrapper before publishing — the Artifact runtime supplies its own
skeleton and would nest them — but leave the file on disk intact, since it is also meant to open in
a browser.

Keep the same artifact URL across days if the operator wants one running page; use a fresh one per
day if they would rather have the history. Ask once, then stop asking.

## Step 3 — Talk it through

This is the part that cannot be automated, so do not rush it into a checklist.

For each proposed change, the operator needs enough to decide and no more: **what breaks today,
what the change does about it, what it touches, and what R2 and R3 changed about R1's version.**
That last one is the tell. A change where two independent re-derivations found nothing is either
genuinely clean or was not really re-derived, and the operator is entitled to know which the page
claims.

Answer questions by reading the actual proposal and the actual code — `openspec/changes/<name>/` and
the files it names. Do not answer from the review page alone; it is a summary written by a process
that was optimising for brevity.

When the operator wants a change different:

- **Small correction** — apply it to `openspec/changes/<name>/` now, re-run
  `openspec validate --strict <name>`, and mark the row `APPROVED`. Say in the note what you changed.
- **The argument is wrong** — mark it `REVISING` with what needs re-deriving. Tomorrow's day window
  takes another round. Do not rewrite an argument here and then approve your own rewrite; that is
  the round discipline collapsed to one round, performed by the person who is meant to be checking it.
- **Not now** — `REJECTED`, with the reason. The reason matters: without one it will be re-proposed.

## Step 4 — Write the decisions down

Append today's section to `spec-queue/APPROVALS.md`, newest day first, using the format in
`spec-queue/README.md`. The status token is the authority; there is no checkbox.

```
## <today>

- APPROVED  <change-name>   note
- REVISING  <change-name>   what needs re-deriving
- REJECTED  <change-name>   why
```

Add `ORDER:` only if the operator asked for a different order tonight. Add `NOTHING TONIGHT` if they
want the window to stand down — it stops before spending a model invocation.

**Leave undecided changes out.** Absence is not rejection: a row-less change stays in
`openspec/changes/` and comes back in tomorrow's page. Inventing a decision the operator did not make
is the one failure this step cannot recover from, because the night window treats this file as
authoritative and nobody is awake to contradict it.

Commit it. Then tell the operator, in one short list, exactly what tonight's window will build —
including the backlog items that come first by default, so the order is never a surprise in the
morning.

## Step 5 — The merge question

The cycle branch is merged by the operator, awake. Never automatically, and never by a window.

Check `git branch --merged master` for the cycle branch. If it is unmerged and spans more than a day,
raise it — an accumulating diff that nobody merges is worse than no loop, because it eventually grows
past reading. Offer the merge; do not perform it unasked.

## Limits

- **Push, do not open PRs.**
- Stage explicit paths, never `git add -A`.
- `openspec validate --strict <name>` must pass before any row is marked `APPROVED`.
- Never mark a task complete on the strength of a plan existing.
- Do not touch port 8000. 8010 and 8011 are the trial Hubs.
