# Handoff: the loop became a flow, and three loop bugs died on the way

**Date:** 2026-08-21T14:05:00+01:00 · **Branch:** `autonomous/2026-08-20-open-specs` · **HEAD:** `1e06755`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive)
**Previous handoff:** `.claude/handoffs/handoff-0068-2026-08-21-1315-two-runs-landed-eight-sections-and-the-driver-lost-40-percent.md`
**Status:** chunk complete. **4 unpushed** at the time of writing (`bb95e66`, `d7cee5d`, `c2dda7c`,
`1e06755`).

**AMENDED 14:12, minutes after writing.** The operator installed the run-3 driver at **14:04:36, every
20 minutes**, while this file was being written. So two statements below were true when written and
are now false: the working tree is **not clean** (iteration 1 is mid-flight), and next step 1's
"driver is not installed" is **done**. The driver question in next step 1 is still open on its
merits — 20 minutes is the same interval that lost run 2 about 40% of its firings — but it is now a
question about a *running* driver, not an unarmed one.

**What iteration 1 is doing:** implementing `task-dependencies` 1.6–1.8, the reviewer field. That is
the stranded work task 10.0 was added to surface, so the gate worked — the run found it on its first
firing rather than closing the change without it.

## Goal

Continue the spec work while autonomous runs implement. The session began as `/resume` from handoff
0065 and ran 09:00–14:05 **alongside run 2**, which was changing code on the same branch.

The *why* governing judgement calls is unchanged: this is the dogfooding migration CLAUDE.md
describes, so friction found while using the product is a **deliverable**, not a distraction. Two of
today's three bug fixes came from exactly that.

## Current state

### Three live bugs found, reproduced by execution, and fixed

Not reasoned about — **run first, then fixed**. That order is the session's main methodological
finding and it is worth keeping.

| Bug | Reproduction | Fix |
|---|---|---|
| **The spin.** A loop whose tasks all reached `completed` fired forever, spawning an agent per tick to do nothing | `test_loop_whose_tasks_are_all_completed_but_unapproved_skips_instead_of_spinning` | `_loop_stall_reason` — a firing that would claim nothing on a non-drained queue is **skipped, not stopped** (`7d4ff6e`) |
| **`revision_needed` unclaimable.** A reviewer who correctly sent work back stalled the loop | `test_revision_needed_is_claimable_so_a_returned_review_resumes` | joined `CLAIMABLE_LOOP_TASK_STATUSES` (`824d843`) |
| **Fast cron manufactures work.** No already-running guard in the firing path | measured: 5 firings during 1 turn → **5 queued briefings for the same task** | **proposed, not fixed** — group 1 of `loop-notices-and-reacts` |

I also **miscounted the status gap and shipped the error in a docstring**: I wrote that `completed`
and `under_review` were *"the only two"* statuses in neither `CLAIMABLE_LOOP_TASK_STATUSES` nor
`TERMINAL_FOR_BINDING`. There were **three** — `revision_needed` was the other. The test now
*derives* the gap from `TRANSITIONS` instead of listing it, so a status added to the machine and
placed in neither set fails a test rather than becoming a loop that fires forever.

### Item 10 of the operator's twelve is closed — it was already built

`send_message` with `recipient == sender` and an explicit `conversation_id` **works today**, verified
by execution: `solo` sent from `conv-thinking` and it landed in `conv-building`. Nothing was built
for it — there is no self-send guard, and naming a conversation routes on the conversation rather
than on who is asking. A self-loop is also **bounded**: `hop_depth` comes from the sending run's
`turn_depth + 1` with no exemption, so at `hop_budget = 6` a run at depth 6 sends fine, the entry
lands at depth 7 and stays durable, and `schedule_agent` refuses with `"hop budget exhausted"` —
refusal at *delivery*, not at send, so nothing is lost if the budget is later raised.

Both are locked down in `hub/tests/test_agent_message_routing.py`.

### The loop became a flow — three explorations and one proposal

The thread ran: *who guarantees the review handoff* → *a review is a task, not a message* → *the loop
becomes a flow*. Each superseded part of the last, and the supersessions are recorded rather than
silently overwritten.

**`loop-becomes-a-flow` is proposed (0/60) and validates.** A flow is **a loop that declares a
document** — three tiers, one row, no new table. `AIJob.agent` stays `NOT NULL` and becomes the
default rather than the mandate, which makes the regression bar sayable in one sentence: *a flow with
one agent behaves identically to a loop today*, and the existing loop suite passing unmodified is the
proof.

**20 of `agent-loops`' 25 requirements are untouched by it.** That count is the evidence this is the
extension the operator's *"improve the loop, do not rebuild it"* decision asked for.

### Two changes were revised mid-flight, and both needed rescuing

- **`task-dependencies` gained a reviewer field** (1.6–1.8) *after* group 1 had closed and after the
  worker had passed it. They were stranded — present, unchecked, invisible. **Task 10.0 now gates the
  change on them.** Not renumbered into a later group, because commit messages say *"Land
  task-dependencies S3 section 9"* and renumbering a landed section would break real traceability to
  fix a bookkeeping problem.
- **`loop-notices-and-reacts` was rescoped 64 → 44 tasks.** The whole review-handoff half is gone
  (detection, re-brief, reminder bound, exhaustion) and its `loop-review-handoff` capability was
  deleted. It was at 0/44 so nothing was lost — but left as it was, the next worker would have built
  the thing we decided against.

### Machine state

| | |
|---|---|
| Branch | `autonomous/2026-08-20-open-specs` (the runs push it; `master` is 16 ahead of `origin/master` and **must not be pushed** per STATE.json) |
| Run 2 | **over.** `stop_at` 13:00 passed; driver self-unregistered as designed |
| Run 3 | **LIVE.** Armed in STATE.json (`stop_at` 19:00) and installed at 14:04:36, `PT20M`. First firing took the stranded reviewer field. Next firing 14:24:36 |
| Hub, port 8010 | untouched all session. No Hub started, no browser opened, no port bound |
| This repo as a project | still **not** registered |

## Files touched

All committed. `git status --short` empty, `git diff --stat HEAD` empty.

**Code and tests**

- `hub/hub/scheduler.py` — added `_loop_stall_reason`; the busy-skip branch in `_do_fire_job`;
  `revision_needed` added to `CLAIMABLE_LOOP_TASK_STATUSES` with the reasoning. **Finished.** *(Note:
  run 2 also edited this file — `dependency_gate` import and the actor-aware claim are theirs.)*
- `hub/tests/test_scheduler.py` — the spin reproduction, the derived-gap helper
  `_statuses_in_neither_set()`, and two new gap tests. **Finished.**
- `hub/tests/test_agent_message_routing.py` — two tests for item 10 (self-message routing, hop
  bound). **Finished.**

**Explorations** (all new, all finished)

- `openspec/explorations/2026-08-20-who-guarantees-the-review-handoff.md` — §7's fork resolved; §9
  settles the firing cadence and tick recording.
- `openspec/explorations/2026-08-21-a-review-is-a-task-not-a-message.md` — supersedes the above's R1–R3.
- `openspec/explorations/2026-08-21-the-loop-becomes-a-flow.md` — the 25-requirement audit, the three
  tiers, and `create_flow`.
- `openspec/explorations/2026-08-20-the-loop-under-dependencies.md` — **edited**: §3 marked verified
  then fixed; L0, L3, L5 struck through.
- `openspec/explorations/2026-08-20-an-agent-messaging-its-other-conversation.md` — **edited**: status
  is now ANSWERED, with the verified findings.

**openspec changes**

- `openspec/changes/loop-becomes-a-flow/` — **new**: proposal, design (D1–D8), tasks (12 groups / 60),
  and four spec deltas (`agent-flows` new; `agent-loops`, `conversation-checkpoint`,
  `agent-tool-surface` modified). Validates.
- `openspec/changes/loop-notices-and-reacts/` — **new this session, then rescoped**. 9 groups / 44
  tasks. Withdrawn decisions kept as numbered `WITHDRAWN` stubs. `specs/loop-review-handoff/` deleted.
- `openspec/changes/task-dependencies/` — **edited**: tasks 1.6–1.8, task 10.0, design D10 (the loop's
  claim) and D11 (the reviewer field), plus `specs/agent-loops/spec.md` and a reviewer requirement in
  `specs/task-dependencies/spec.md`.

**Run state**

- `.claude/autonomous/STATE.json` — **edited**: run 3, `stop_at` 19:00, `run3_brief`, `run3_hazards`
  (4), `run3_available_work`, amended `run2_outcome`, and a `next_action` that hands over judgement
  rather than a queue.

## Key decisions

Operator decisions this session, each with its rejected alternatives recorded in the exploration or
design that owns it.

1. **Skip a stalled firing, never stop it.** Stopping sets `job.enabled = False` and calls
   `remove_job`, so the operator resolving the situation afterwards cannot revive it. *This one
   reasoning recurred all session* and settled three separate questions.
2. **No events; keep the cron.** The latency gap is invisible at a loop's timescale, and unfired
   wakers are a bug this codebase has already shipped and measured (`redrain_queued_agents`, *"a
   limit protecting nobody"*).
3. **Busy ticks record nothing; stalled ticks count in place.** The line is *"something changed"*
   versus *"the same thing is still true"*. Precedent: `InboundQueueEntry.delivery_attempts`.
4. **Tick interval `*/5 * * * *`.** There was no default to change — `create_loop` requires `cron`.
5. **R4, the review-wait timeout: decided against, not deferred.** A timeout must choose an *action*,
   and stopping, reassigning and nudging are each worse than waiting visibly.
6. **The status vocabulary folds into `loop-notices-and-reacts`** rather than becoming its own change.
7. **A review is a task, not a message** — and specifically **Shape B**: `completed` becomes claimable
   by a non-author. *Rejected:* a second task row, which regresses (a review task's completion needs
   reviewing) and needs a `kind` column `Task` does not have.
8. **The flow re-briefs nobody.** It fires the reviewer. This is what killed R1–R3.
9. **Reviewer resolution is a ladder whose bottom rung needs no configuration** — declared reviewer,
   else anyone not running and holding no active task, else surface.
10. **A flow may start every task whose dependencies are met.** Width comes from the graph, not a
    setting — which does **not** reverse the max-concurrent-runs withdrawal, because that was a
    project-level policy and this is the shape of the decomposition the operator approved.
11. **Three configurations, not three objects**, plus **`create_flow`** as a third verb, plus **the
    briefing states the tier**.
12. **The checkpoint lineage is the flow's** — one chain, many authors.
13. **The reviewer field is a portable hint, not an agent identity** — *"the file is the portable
    truth; the database is machine-local state"*, and an agent name is a roster row on one machine.
14. **Run 3 gets hazards, not a queue** — citing run 2's own call to take section 9 over section 8.

## Constraints and user directives (verbatim)

From this session:

- *"Now that I think about it I don't want to end up in a old problem where having a squad to develop
  is a price that you need to pay before even starting development... Needing to decide everything up
  front is not what I would like. I see a couple of ways to resolve this. At spec time define who is
  testing what. At soon as the agent finishes he picks one available agent that is not assigned to
  any task. A test should be a task on the board and be assigned to agents as well."*
- *"So we have to make distinctions between jobs, loops and flow. I imagine the flow being the overall
  architecture that will progress us from 0 to spec fulfilled. Maybe the loop can be something that
  can live inside a flow... a job is something that is run a part from it no sequence just one task
  from time to time."*
- *"How does an agent that only sees one mcp tool that have different uses know the difference on how
  to use the endpoint for looping or flow?"*
- *"we need to transform the loop into a flow with more functionalities... the deterministic scheduler
  of a flow of tasks."*
- *"Don't need to push."* (about `master`)
- Via AskUserQuestion: **"Let the run choose, with the hazards written down"**, **until ~19:00**,
  **own-label**, **5 minutes**, **"Add a reviewer field to task-dependencies now"**, **parallel
  ("the document declared the width")**, **"Nothing"** for an unfilled charter scope.

Standing, still in force:

- Never touch the Hub on **port 8010**. Stage paths explicitly; never `git add -A`.
- Never mark a task complete on the strength of a plan existing.
- `hub/hub/mcp_server.py` may import **only** stdlib + fastmcp. `approve_tool_call` has **no return
  annotation**.
- `hub/hub/static/ui` is a committed build artefact — after `npm run build`, run
  `py -3.11 scripts/refresh_ui_bundle.py`.
- Keep the two `spec_manifest.py` twins in sync by hand.
- From memory: commit each completed checkpoint without asking; specs carry test guides split into
  agent-verifiable and human-only.
- From STATE.json: **do not push `master`**; do not archive any change; do not bulk-reindex `spec/`;
  do not attempt human-only tasks.

## Dead ends

- **`openspec validate` reads only the FIRST LINE of a requirement body when checking for
  SHALL/MUST.** Seven requirements failed with SHALL in the second sentence. Put the normative clause
  first. This cost two round trips.
- **Renumbering task groups with a regex over `## N.` collides** when two groups transiently share a
  number — it silently produced two `## 6.` headers, twice. Renumber highest-first *and* verify with a
  group/task consistency check afterwards.
- **`git stash` in a tree an autonomous run is also editing.** I used it to prove a failure was
  pre-existing; it swept up the worker's uncommitted `document-adoption` work and reverted it for ~5
  seconds. It recovered cleanly — that was luck, not care. **Do not use `git stash` on this branch.**
- **PowerShell here-string syntax (`-m @'...'@`) in the Bash tool** silently commits with `@` as the
  subject line. Use a real heredoc. *(Inherited from 0068 and hit again anyway.)*
- **I ran the Hub suite with the wrong interpreter all session.** `python -m pytest` (the hermes venv)
  fails 3 `test_pty_runner` tests and skips 13; `py -3.11` — what the driver uses — passes all 29 and
  skips 84. I called them "pre-existing environment failures" **twice** while the workers' baselines
  reported 0 failed. **Use `py -3.11` for anything whose number will be compared to a run's.**
- **I asserted `black` and skipped `ruff`** because `ruff` was not importable from the venv python. It
  was importable from `py -3.11` the whole time, and an `I001` sat in `test_scheduler.py` for hours.

## Verification

**Ran, and passed** (all with `py -3.11` unless noted):

- `cd hub && py -3.11 -m pytest tests/test_pty_runner.py -q` → **29 passed**.
- Full Hub suite (venv python, before the ruff fix) → **2715 passed**, 13 skipped, 1 xpassed, 3
  failed — the 3 being the interpreter artefact above.
- `py -3.11 -m pytest tests/ -q` (CLI) → **402 passed, 5 skipped**. *(Prep baseline was 404/3; same
  407 total, two now skipping — most likely the `pip install -e .` I ran mid-session.)*
- `npx vitest run` → **1172 passed / 118 files**. `npx tsc --noEmit` → clean.
- `py -3.11 -m ruff check hub/` → **clean** (after `1e06755`). `black --check` → 393 files unchanged.
- `openspec validate --all --strict` → **41 passed, 0 failed**.
- `hub/tests/test_scheduler.py` → 28 passed. `test_agent_message_routing.py` → 13 passed.

**NOT tested — do not claim otherwise:**

- **The full Hub suite has not been run under `py -3.11`.** The 2715 figure is the venv python's. The
  three reds are explained, but the run-comparable number is unmeasured.
- **No Hub was started and no browser opened.** Every UI fix from handoff 0063 remains jsdom-only.
- **Nothing in `loop-becomes-a-flow` or `loop-notices-and-reacts` is implemented.** 0/60 and 0/44.
- **The busy-guard fix is proposed, not built.** The 5-briefings pile-up is live today.
- **Handoff 0068's next-step 3 is still open** — the query-counting test for `task-dependencies` 7.3,
  the one ticked box whose property was never measured.

## Git state

- **Branch:** `autonomous/2026-08-20-open-specs`. **HEAD:** `cac830b` (this handoff).
- **Working tree was clean at `1e06755`; it is now dirty** — `hub/hub/spec_payload.py` and
  `hub/tests/test_spec_payload.py`, run 3's iteration 1 writing the reviewer field. Not mine, and not
  to be reverted or stashed. **Do not `git stash` on this branch** — see Dead ends.
- **4 unpushed:** `bb95e66`, `d7cee5d`, `c2dda7c`, `1e06755`. Run 3 will push them on its first
  iteration, or `git push` does it now.
- `master` is **16 ahead of `origin/master`** and STATE.json says do not push it.
- This session added 20 commits; run 2 added the rest.

## Next steps

1. **Decide the driver question — the driver is already running at 20 minutes.** Handoff 0068
   next-step 2 says *"Fix
   `run-iteration.ps1` before arming any run 3"* — it is **not done**, and my "clear to fire" verdict
   did not account for it. What I verified: the invocation at `run-iteration.ps1:115` **is**
   synchronous, so the "wrapper exits early" diagnosis looks imprecise — but the symptom (40% of
   firings skipped) is real and consistent with iterations outlasting the interval, since STATE.json
   requires the full Hub suite and that alone is ~14 minutes. The second half of 0068's complaint is
   plainly true: **backdating `last_heartbeat` is an instruction to the agent** (lines 93–98), not
   something the script guarantees, so a died-or-livelocked iteration leaves a fresh heartbeat and the
   next firing stands down. Either fix the script, or install with a longer interval:
   ```powershell
   powershell -File .claude\skills\autonomous-session\scripts\install-driver.ps1 -UntilHHmm "19:00" -EveryMinutes 30
   ```
2. **Run the full Hub suite under `py -3.11`** — `cd hub && py -3.11 -m pytest tests/ -q` — so there
   is one number comparable to run 2's 2718.
3. **Push the four stragglers:** `git push` on this branch.
4. **Or implement `loop-notices-and-reacts`** — 0/44, backend only, nothing unlanded blocking it, and
   the flow needs its shared firing decision. Start at group 1.1 (the busy-guard reproduction test).
5. **Or review `loop-becomes-a-flow`** before any run starts it. It is the largest thing proposed and
   the operator has not read it.

## Open questions for the user

- **Fix `run-iteration.ps1`, or just lengthen the interval?** Next step 1.
- **Is `loop-becomes-a-flow` right?** Unreviewed, 60 tasks, and everything downstream assumes it.
- **Section 8, the board** — build it flow-agnostic now, or wait for the flow?
- **Register this repo as a project?** Open since handoff 0064.
- **Retire `openspec/specs/`?** Open since 0062. **Delete `proj-adf8a200`?** Open since 0063.
- **What band does `blocked` belong to** in the status vocabulary? The one classification existing
  code does not answer (`loop-notices-and-reacts` task 3.4).

## Read on resume

- `.claude/autonomous/STATE.json` — **first, if arming or diagnosing a run.** `run3_hazards` and
  `run3_available_work` are the current picture.
- `openspec/explorations/2026-08-21-the-loop-becomes-a-flow.md` — the 25-requirement audit (§3), the
  three tiers (§8), and what is still open (§9).
- `openspec/changes/loop-becomes-a-flow/design.md` — D1–D8, if implementing or reviewing.
- `openspec/changes/loop-notices-and-reacts/tasks.md` — the 44 that are ready to build now.
- `hub/hub/scheduler.py:240-360` — `CLAIMABLE_LOOP_TASK_STATUSES`, `_claim_loop_task`,
  `_loop_stall_reason`. Every loop finding this session rests on these.
- `.claude/skills/autonomous-session/scripts/run-iteration.ps1` — only for next step 1.
