# A daily research → spec → approve → build loop

**Date:** 2026-09-01 · **Status:** exploration, nothing built · **Branch at writing:** `master` @ `4a226d8`

## What the operator asked for

Verbatim, 2026-09-01:

> I want to create something interesting scheduling some runs and some autonomous runs. This is the
> ideia: I want to have a run scheduled that will explore the code, get the context of the things
> that were recently done in agentweave and do a research on the internet to find were the market is
> going, what else people are building. This is will compile a ton of things for agentweave. Then I
> want spec loops that will create specs with these using the spec loop and refine all of those and
> create a html artifact that I can approve or talk with the AI about those specs. Then I'll refine
> those specs or approve and then a it will implement and test every night. I want this on a loop
> everyday.

And on the cadence, after rejecting a proposed shape:

> We need a run at 23:00 that will check what was approved and created during the day. I want
> multiple loops I think. One from 23 until 7 then one at 9 until 17. We have to include some e2e
> loops in one of those runs to either fill the backlog of fix the issues in agentweave.

## Four decisions already taken

Settled by the operator on 2026-09-01, with the rejected alternatives recorded so they are not
re-proposed:

| # | Decision | Rejected, and why |
|---|---|---|
| **D1** | **Approval is a tracked file, written by a conversation.** The review page is the reading surface; the operator opens a Claude Code session, talks the specs through, refines them, and *that session* writes `spec-queue/APPROVALS.md`. The night run reads only that file. | **The trial Hub's own spec flow** — maximum dogfooding, and where this should end up, but it makes the loop depend on the Hub being edited daily; port 8010 has served 2026-08-29 code for three days, which is exactly the failure. **Checkboxes with no conversation** — loses the "talk with the AI" half that was asked for. |
| **D2** | **Generated specs live in openspec**, as `openspec/changes/<name>/`. | **The trial Hub spec flow** — the night run has never worked a Hub-held change, so it would need new machinery on both ends at once. **Both** is forbidden outright by CLAUDE.md. Revisit as a deliberate later change once the loop itself is stable. |
| **D3** | **The night build drains the backlog first**, then builds newly approved specs. The review page can override the order any day. | **Approved-first** — fastest feedback, but 8 unarchived changes and 173 findings would rot while the loop shipped new ideas. |
| **D4** | **Two long windows**, 09:00–17:00 and 23:00–07:00, with e2e driving inside one of them. | The proposed single morning-research/overnight-build split. The operator's shape is better: it gives the decision step a whole evening instead of a rushed morning, and it puts eight hours behind the fill half rather than two. |

## What already exists, measured 2026-09-01

Three of the four stages have working machinery on this machine. Nothing here is recalled; each was
read this session.

**`ClaudeAIDigest`** — `~/.claude/routines/ai-digest/`, a Windows Scheduled Task firing daily at
07:57 that runs `claude -p` with `WebSearch`/`WebFetch`, `cwd` outside the repo, the repo granted
read-only via `--add-dir`, and a guardrail that snapshots `git status --porcelain` before and after
and deletes anything the run left behind. It writes HTML, opens it in the browser, and pushes a
wrapper-stripped copy to a private archive repo where a **cloud** routine publishes the Artifact at
08:38 and pushes to the operator's phone. This is stage 1's template.

**`autonomous-prep` + `autonomous-session` + the two driver scripts** — `install-driver.ps1`
registers a Scheduled Task; `run-iteration.ps1` is one iteration as a fresh headless process reading
`.claude/autonomous/STATE.json`, doing exactly `next_action`, committing, pushing, and exiting.
`MultipleInstances IgnoreNew` means iterations can never overlap. A `last_heartbeat` grace of 25
minutes makes the driver stand down while an interactive session holds the branch. Twenty-eight run
logs of precedent. This is stage 4, already built.

**`e2e-loop`** — drives the product as a real operator, scoped to a recent change or as a
full-surface sweep. It is what produces findings.

### The one hard constraint

**Headless `claude -p` has no `Artifact` tool.** Verified 2026-08-28 by dumping the full headless
tool list; no CLI flag provisions one, and listing it in `--allowed-tools` does nothing —
allowlisting does not provision a tool. `PushNotification` is absent for the same reason.

A scheduled run therefore **cannot publish the artifact the operator asked for.** Two known-working
answers exist: the digest routine's local-writes / cloud-publishes split, or publishing from the
operator's own interactive session. This design takes the second — see D7.

## The design — one 24-hour cycle

```
08:30 ── one shot ──                RESEARCH  Scheduled Task: AgentWeaveResearch
                                              auto mode, outside the repo, reads the web

09:00 ─────────────────── 17:00     FILL      Scheduled Task: AgentWeaveDayLoop
                                              e2e · spec loops · review page

17:00 ─────────────────── 23:00     DECIDE    the operator, in a Claude Code session
                                              publish artifact · talk · write APPROVALS.md

23:00 ─────────────────── 07:00     FIX       Scheduled Task: AgentWeaveNightLoop
                                              backlog first, then approved specs · drive it

07:00 ─────────────────── 09:00     margin    07:57 ClaudeAIDigest, untouched
```

Each window is an **autonomous-session run** — the iterated driver, not a single `claude -p`
invocation. Eight hours cannot fit in one turn, and the whole point of the driver is that death
costs one iteration.

### FILL — 09:00 to 17:00

Iteration 1 composes its own queue; there is no separate orchestrator task. The queue is, in order:

1. **Repo delta.** What landed since the last cycle: `git log`, merged branches, the diff to
   `scripts/drive/FINDINGS.md`, closed and opened findings, what the night run claimed and whether
   its evidence holds. Read-only.
2. **Read the research** that `AgentWeaveResearch` left at 08:30 in `spec-queue/research/<date>.md` —
   a ranked candidate list: what someone else shipped, what it implies for AgentWeave, and what a
   change would cost. Treated as **data, never as instructions**; it is assembled from pages written
   by strangers. A missing file costs the day its candidate list, not its work.
3. **e2e.** Drive the product live. Scoped to what last night built on most days; a full-surface
   sweep once a week. New findings append to the ledger. This is the "fill the backlog" half of the
   operator's instruction — a drive checks the product where the rounds only check the argument.
4. **Spec loops.** Take the top candidates — from the research list *and* from the findings the
   drive just produced — through the full round discipline into `openspec/changes/<name>/`. R1
   explores and proposes; R2 and R3 each independently re-derive against the code. **One change at a
   time, never collapsed**, which means a realistic day produces one or two proposals, not ten.
5. **Review page.** `spec-queue/review-YYYY-MM-DD.html`: what was researched, what was found, what
   was specced with each proposal's argument in brief, and — stated plainly — what the night run
   would build by default if the operator approves nothing.

### DECIDE — the operator, on no schedule

The operator opens a Claude Code session and says something like *"today's review"*. That session:

- publishes `spec-queue/review-<date>.html` as an Artifact (an interactive session **has** the
  `Artifact` tool);
- answers questions about any proposal, and edits `openspec/changes/<name>/` where the operator
  wants it different;
- writes `spec-queue/APPROVALS.md`.

If the operator never sits down, nothing breaks: the night run finds no approved rows and spends the
whole window on the backlog. That is the correct degradation and it needs no special case.

### FIX — 23:00 to 07:00

Iteration 1 composes the queue:

1. `spec-queue/APPROVALS.md` — the approved rows, and any explicit ordering override.
2. **Backlog first** (D3), in this order: unarchived openspec changes that are implemented and only
   need archiving (cheapest, and the ordering constraint in
   `a-conflict-refusal-names-what-clears-it`'s task 6.4a is real and must be read first); then open
   findings by severity, A before B before C.
3. **Then** approved specs, as `openspec-apply-change`.

Every change it implements gets **driven**, not just tested. That is the standing lesson: three
rounds are not a substitute for driving it, and the first live drive has repeatedly found in one
request what three rounds of reading missed.

## What has to be built

Six pieces. Four are small.

| # | Piece | Size |
|---|---|---|
| **P1** | `-StateFile` parameter on `install-driver.ps1` and `run-iteration.ps1`, defaulting to today's hardcoded `.claude/autonomous/STATE.json` so nothing existing changes | small |
| **P2** | `spec-queue/` — `APPROVALS.md`, `review-<date>.html`, `research/<date>.md`, plus a README stating the contract each file is under | small |
| **P3** | Two queue-composer prompts — one per window — that iteration 1 runs | medium |
| **P4** | Two Scheduled Tasks, armed from `install-driver.ps1` with `-StartAtHHmm` / `-UntilHHmm` and distinct `-TaskName` | small |
| **P5** | A cycle-branch rule (below), enforced by the FILL run's first iteration | small |
| **P6** | The DECIDE session's own skill, so "today's review" is one command | medium |
| **P7** | `AgentWeaveResearch` — a third task, `ai-digest`-patterned, in `auto` mode (D8) | medium |

### D8 — research is a separate task, taken 2026-09-01 while building

The design above put research inside the day window. That is wrong, and the reason is in
`ai-digest/run.sh`'s own source, dated 2026-08-28: *"`bypassPermissions` is deliberately **not**
used: this routine ingests untrusted web content, so the permission classifier stays in the loop as
a prompt-injection backstop."* The cloud version of that routine got sandbox isolation for free;
locally the classifier is the replacement.

An autonomous window runs `bypassPermissions` — the driver refuses any other posture for Claude — on
a machine with unscoped `gh` and the operator's credentials. Reading the open web from inside it
removes the only backstop there is.

So research runs as its own one-shot task at 08:30, in `auto` mode, `cwd` outside the repo, on the
`ai-digest` pattern that has worked daily since 2026-08-28. The privileged window reads a file.

**This bounds the untrusted content reaching the privileged process; it does not eliminate it.** The
research file is still derived from the web, and a `bypassPermissions` window is *instructed* not to
browse rather than prevented from browsing. Both playbooks therefore say the research file is data
and never instructions. The residual risk is real and should be stated plainly rather than papered
over: the digest routine's own README records that vigilance about `cwd` failed twice before a
mechanism replaced it.

### P1 in detail — why the driver needs one change

`run-iteration.ps1` hardcodes `$stateFile = Join-Path $Repo ".claude\autonomous\STATE.json"`, and so
does the installer. Two daily windows with different queues need two state files. The windows never
overlap in time, so nothing else about the driver needs touching — the branch guard, the heartbeat
stand-down and `IgnoreNew` all still hold.

### P5 in detail — the branch rule

The skill's hard-won rule is **fresh, never reused**: a fixed branch name accumulated the previous
run's scratch until a merge had to be sorted out by hand. But a *daily* fresh branch means a daily
merge decision, and the operator merging nothing for three days would leave day four branching from
a `master` that is missing three days of work.

The rule that satisfies both: **one branch per cycle-since-last-merge, dated by when it was cut.**

- FILL's first iteration checks whether the previous autonomous branch is merged into `master`.
- **Merged** → cut a fresh `autonomous/YYYY-MM-DD-daily` from `master`.
- **Not merged** → stay on it, and say so at the top of the review page, so the operator sees that
  they are looking at two days of accumulated diff and can decide to merge.

Never auto-merge. Merging is the operator's decision, made awake — that is unchanged.

## Decisions still open

**O1 — models per window.** `STATE.json.model` is per-run, so this is per-window, not per-iteration.
Sixteen hours of Opus a day, every day, is the default if nothing is chosen. A defensible split:
**night = Opus** (implementation mistakes are the expensive ones) and **day = Opus for the spec
rounds** (the round discipline exists *because* plausible-but-wrong proposals are this repo's
dominant failure mode) — which is to say the cheap option is not obviously available. Worth
measuring for a week before optimising. Note this is unrelated to the standing directive that agent
turns *inside* a drive bind Haiku; that stays.

**O2 — every day, or weekdays?** Seven days a week is what was asked for. Nothing in the design
needs the weekend off; the cost does.

**O3 — what stops the loop.** Proposed tripwires, each of which should halt the window and say so
rather than working around it: a red suite at 23:00 (the run cannot tell its own breakage from
inherited breakage); an unmerged cycle branch older than three days; the hub suite's ~25-minute
runtime eating a whole iteration.

**O4 — `scripts/drive/FINDINGS.md` is 12,600 lines and 173 findings.** A loop that appends to it
daily makes it unreadable within a fortnight, and it is already the single most useful file in the
chain. It needs splitting — probably open findings in one file, closed ones archived by month —
before the loop starts feeding it, not after.

**O5 — the artifact route.** This design publishes from the operator's interactive session (D7,
below). The alternative is the digest routine's split: a second private archive repo plus a second
cloud publisher routine, which buys a phone notification when the specs are ready and costs two new
pieces of infrastructure. The operator is at a keyboard for the DECIDE step regardless.

**D7 (taken, on the strength of the constraint above):** the review page is written to disk by FILL
and published as an Artifact by the DECIDE session, not by a cloud routine.

## What could go wrong

- **The loop generates specs faster than the operator approves them.** Three rounds per change means
  one or two proposals a day, which is roughly the rate a person can read. If it turns out to be
  more, the review page must rank rather than list.
- **The day loop and the operator collide in the same working tree.** The driver's 25-minute
  heartbeat grace already stands down for a live session, but it keys on `STATE.json`, not on the
  operator's git activity. 09:00–17:00 is exactly when the operator is most likely to be working.
  This is the design's weakest joint and should be watched in the first week.
- **The research half drifts into a news feed.** `ClaudeAIDigest` already covers AI news. This one is
  only worth its cost if every item ends in *"and therefore AgentWeave should…"*. The ranked
  candidate list is the mechanism; if it is ever absent, the research iteration failed.
- **Nothing gets merged.** Two windows a day producing commits on a branch nobody merges is worse
  than no loop, because the diff grows past reading. The cycle-branch rule surfaces it; it does not
  solve it.
