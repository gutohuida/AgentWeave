# 2026-08-26 — Driving everything, end to end, unattended

Write-up for the overnight autonomous drive on `autonomous/2026-08-26-drive-everything-and-fix-it`
(queue items Q1–Q9, `.claude/autonomous/STATE.json`). Findings are numbered F51–F60, continuing the
series opened by the 2026-08-23 stress test in `scripts/drive/FINDINGS.md`. This document ranks
each finding by what it actually cost, states what's fixed vs. still open, and — per the method's
own instruction — records what held, not only what broke.

## How far the run got

Q1 (cold start), Q2 (spec flow to tasks), Q3 (fix pass 1), Q4 (run-boundary checkpoint hook), Q5
(review/evidence/approval/integration), Q7 (F50, pre-authorised) all closed. Q6 (fix pass 2) is
blocked-on-operator: every decision-free item in it is done (F54, F55, F59 fixed and closed); the
two that remain (F53, F58) each have a decision-free half already fixed, and a genuine design
decision left for the operator. Q8 (operator-in-the-loop surfaces) drove the Claude manual-permission
leg and the `ask_user` timeout live and clean, plus an organic (not self-triggered) observation of
the Codex leg's `decide_approval` routing through the same `permission_requests` surface — structural
confirmation, not a formally closed rep. Q9 (this document, plus the full sweep) is closed: every
suite is green, recorded below. Q10 (tidy) is still open, time permitting.

## Ranked by cost

### 1. F58 (A) — approving one task merges the agent's entire branch history, not the reviewed commit

`task_integration.py`'s own docstring and its own regression test both assert the guarantee "what
merges is the commit the evidence names, not the agent's branch" — the test was green and the
guarantee was false. Live reproduction: approving one `FR-2` task's evidence pulled in a different,
*unapproved* `FR-3` task's test file and five scratch scripts via `git merge --no-ff`. Cost: this
means every prior "approved and merged" task in a project's history may have silently carried
unreviewed sibling work along with it — the highest-severity item this whole run found, precisely
because it undermines trust in *past* approvals, not just future ones.

**Status:** decision-free half fixed (`f20e181`) — every merge now records and surfaces
`rode_along_commits` as a visible amber warning, so the operator can at least see what actually
shipped. The root cause (merge-the-branch vs. merge-the-commit semantics) is unresolved by design —
three fix shapes were sketched (tighter cherry-pick range, true single-commit patch-apply, per-task
worktrees) and none chosen; it changes conflict semantics and needs the operator's call. Recorded in
`decisions_for_user`.

### 2. F52 (A, downgraded from an initial A) — the "workspace" permission posture never sees a git command; commits are refused silently

Two real unattended loop runs on `ledger-stress`, each with a real correct-looking fix and real
passing tests, both failed to commit — and nothing on the board said why; zero
`permission_requests`/`permission_denied` rows exist despite Claude Code refusing every git call,
including a bare `git --version`. Initially filed as data-loss risk. Corrected the same iteration
once `worktrees.snapshot_worktree` was read: it runs unconditionally at the end of *every* turn and
auto-commits any dirty state regardless of the agent's own git success — so the feared consequence
(code lost, evidence chain undercut) does not happen. Cost is real but smaller than first measured:
an agent burns a whole turn fighting a tool it cannot use, not risking work. Isolated reproduction
of the CLI-level refusal itself failed on every axis tried (six configurations, all succeeded where
two production runs failed) — still unexplained, see `dead_ends`.

**Status:** the wasted-turn half fixed live (`auto_snapshot_notice`, `68459ea`) and verified. The
underlying CLI-level git refusal is unfixed, unexplained, and correctly rescoped to a B/C item for a
future Q6-style pass — not a blocker.

### 3. F60 (A) — an `ask_user` timeout resolves itself mid-turn; the task reads `completed` with no trace a judgment call was made without the operator

Driven live per the method's own directive to leave a question deliberately unanswered. The 240s
`QUESTION_ANSWER_TIMEOUT` expired inside the tool call; the agent reasoned about it correctly, picked
its own answer, made the fix, and — in the *same* turn — marked the task `completed` before the run
ended, so `evaluate_run_end`'s `block_task_for_question` had nothing left to park. The question row
itself is permanently orphaned (`answered=0, blocked_task_id=None`) and, live-confirmed, can still be
`PATCH`ed with an answer the agent never picked, five minutes after the run ended, with a `200` and
no warning — a question record that can permanently contradict the code that actually shipped. This
sharpens **F14** (a blocked task still reads `in_progress`/`blocked_reason=None`, reconfirmed exactly
as documented during the same drive) by showing what happens *after* the block resolves on its own.

**Status:** unresolved. One half is decision-free (refuse, or at minimum flag, a `PATCH` to a
question whose run has already ended) and doesn't need operator input. The other half — how a task
that shipped on an unanswered question should be surfaced durably once it has already left
`in_progress` — is bundled with F14's own eventual design fix, which was never explicitly flagged for
the operator before now. Both recorded in `decisions_for_user`.

### 4. F56 (A) — one review target with no evidence permanently wedges an agent's entire inbound queue

A single stale queue entry — `TriggerAgentError` raised before `InboundQueueEntry` reaches
`state='delivered'` — leaves that entry `queued` forever at `delivery_attempts=0`, because the
attempt-counting/abandon logic only runs for a `Run` that was actually created. `schedule_agent`
always retries the same oldest queued entry first, so it wedges *every* later request to that agent
behind a nonsensical `waiting_reason` naming an unrelated, already-completed task.

**Status:** fixed live (`turn_scheduler.py`), regression-tested, mutation-checked, restarted onto and
reconfirmed on the trial Hub. Not separately re-poisoned against the freshly-restarted process — a
judgment call, recorded rather than left implicit.

### 5. F51 (A) — "start exploration" orphans its own document; the agent writes a second one

Reproducing the UI's own two-call flow (`POST .../project/documents` then `POST .../agent/trigger`
with `spec_document` set) exactly, live: the agent could not find the just-created document by the
path it was given and created a second one instead.

**Status:** fixed (`ccb8902`, `15da184`), tested, mutation-checked, verified live.

### 6. F54 (A) — a 409 on job creation has already committed an enabled, spendable job

`create_job` committed the `AIJob` row *before* checking the spec-document conflict, so a client that
correctly treated a `409` as a no-op left a real, enabled, cron-scheduled job running unnoticed —
measured live at roughly eight minutes before the mandatory job sweep caught it.

**Status:** fixed (moved the conflict check ahead of row creation), regression-tested,
mutation-checked, live-reverified against the running trial Hub.

### 7. F57 (A) — a rejection has no way to record why

`update_task`'s MCP tool never exposed a `notes` parameter at all, despite the REST route always
supporting it — a real `critic` rejection with substantial line-by-line reasoning left `notes` and
`deliverables` both `null` on the task row; every word of the reasoning lived only in the run's own
transcript.

**Status:** fixed, tested, mutation-checked, verified live.

### 8. F50 (B) — a checkpoint that failed its own probe is briefed to the reviewer as though it passed

`render_checkpoint` surfaced neither `status` nor `probe_status`. Pre-authorised fix, chosen over
parking it: render the failure rather than skip the checkpoint, since the computed half is the Hub's
own and stays accurate.

**Status:** fixed (`3defb1e`), tested; `openspec validate loop-becomes-a-flow --strict` stays valid.

### 9. F53 (B) — archiving a loop that adopted a document permanently orphans both

Even a loop that never fired a single turn permanently claims its document's `loop_id` on archive,
with no operator API to recover either the document claim or the tasks it "adopted."

**Status:** decision-free half fixed (`2239f38`) — archived loops are now excluded from the conflict
check, so a *new* loop can claim the document again. The deeper question — what should happen to a
dead loop's already-adopted, possibly-started tasks — is unresolved and needs the operator's call
(two shapes sketched, neither chosen).

### 10. F55 / F59 (B) — the same clock-tie tie-break bug, in two tables

Windows clock resolution on this machine returns identical `datetime.now(timezone.utc)` values
across consecutive calls with no delay; `ORDER BY created_at DESC` with a non-monotonic secondary
sort (a random `short_id()`) can silently pick the wrong "latest" row on a tie. First found in
`latest_checkpoint_for_loop` (F55), then rediscovered in the unrelated `EvidenceReview` "latest"
logic (F59) — same shape, different table, both from an unprovoked, intermittent test failure rather
than a hunt.

**Status:** both fixed with the same pattern (a monotonic sequence column, matching
`TaskTransition.sequence`'s existing shape), mutation-checked, live-verified against the restarted
trial Hub.

## Full verification sweep (Q9)

Run at the tail of the drive, on the branch tip that carries every fix above, measured 2026-08-26
06:31–06:48 (this session's own clock, PowerShell-stamped, not Git Bash's):

| Check | Result |
|---|---|
| `py -3.11 -m pytest hub/tests/ -q` | **3147 passed, 84 skipped, 1 xpassed, 0 failed** (950.60s / 15:50) |
| `py -3.11 -m pytest tests/ -q` | **440 passed, 3 skipped** (22.00s) |
| `py -3.11 -m ruff check src/ hub/ tests/` | All checks passed |
| `black --check src/ hub/hub/ hub/tests/ tests/ --target-version py311` | 485 files unchanged |
| `npx openspec validate --changes --strict` | `change/loop-becomes-a-flow` — 1 passed, 0 failed |

Against `green_at_arming` (3127 hub / 440 CLI, both 0 failed): hub's passing count rose by 20 —
consistent with the regression tests this run's own fixes added (F50 through F60's decision-free
halves), not a discrepancy. Nothing failed anywhere. `hub/ui/src` was not touched this run, so the
UI lint/build/refresh steps do not apply — nothing to stamp or commit there.

## What held

- **F9, driven to a real landing commit.** Approval-to-merge was exercised live end to end this run,
  not just claimed: a real commit landed in the subject repository, identified by id, with the
  operator able to see which commit landed where.
- **F10's apparent recurrence, ruled out.** A queue self-drain looked like F10 (reviewer blind to the
  work under review) reappearing; traced to the rows and confirmed the review turn correctly used a
  plain non-structured checkout path for a non-review turn, and a *separate* self-directed review via
  raw git succeeded on its own. Worktree isolation is doing its job on the case that matters.
- **Manual permission mode, Claude leg.** A real `PermissionRequest` for an `Edit` call appeared
  within seconds of the agent attempting it, was answered through the real operator API
  (`POST /permission-requests/{id}/decide`), and the run picked the decision up and continued to a
  clean completion — the mechanism the whole feature depends on works exactly as designed, live, not
  simulated.
- **`record_evidence` from a Haiku agent.** F21 once found this broken; this run found a workable
  path through it once the document path was supplied correctly — a different obstacle than F21's,
  not a contradiction of it, but real forward evidence the surface is usable from a cheap model.
- **`auto_snapshot_notice` (F52's correction).** Discovering that `snapshot_worktree` runs
  unconditionally at the end of every turn, regardless of the agent's own git success, was itself a
  "what held" result: the feared data-loss consequence does not happen, by design, even when an
  agent's own commits are refused.
- **The environmental-axis check.** `PYTHONIOENCODING=utf-8 py -3.11 -m pytest tests/ -q`: 440
  passed, 3 skipped, 21.46s — identical to baseline, no regression surfaced under this axis today
  (the CLI suite only; `hub/tests/` was not re-run under the variation this run — see below).
- **Job-sweep discipline held for the whole run.** Every mandatory sweep this run performed found all
  jobs across all projects `enabled: 0` at the moment it checked — the standing "never leave a job
  enabled" rule was honoured at every checkpoint it was checked.

## An organic, unplanned data point on Q8's Codex leg

While reconciling state at the start of this iteration, a **real, live Codex (`gpt-5.4-mini`)
manual-permission-mode run was found already in progress** on `proj-8605b92d0028`
(`run-3e08cae3629d`, `reviewer` agent, `task-9b0b4a141b21`) — a genuine `codex.exe app-server`
process (PID 16912), started roughly three minutes after the previous iteration finished, and
entirely outside this iteration's own actions. Seven real `permission_requests` rows exist for it
(`a command` / `a file change`), most `allowed` through the same `POST /permission-requests/{id}/decide`
surface used for the Claude leg — this alone answers the structural half of Q8's remaining question:
**yes, `codex_appserver.decide_approval` routes through the identical `permission_requests` table and
API as Claude's `--permission-prompt-tool`**, confirmed by the schema and the decided rows, not by
inference.

This was deliberately **not interfered with**: the pending request at the time was left unanswered
by this iteration, and no competing trigger was issued against the same agent/task while it was in
flight, since its origin (a genuinely-human operator testing live, vs. some other automated process —
`decided_by` is a hardcoded `"operator"` label on the decide endpoint and does not distinguish the
two) could not be established with confidence, and interfering with someone else's in-flight run
carries real cost for no benefit. The run finished on its own by the time this document was written:
`status='failed'`, `error='turn timed out with no turn/completed notification'`, and its final
permission request `expired` rather than being decided — a *different* failure mode than F60's
"resolves itself and completes anyway," worth noting but not chased further this iteration, since it
was not a controlled, self-triggered repro.

**This is weaker evidence than a self-driven rep** (per the method's own reminder to say when a test
is contaminated) — it confirms the plumbing exists and is reachable, but the *specific* behaviour Q8
asked for (does Codex's decide-approval path diverge from Claude's in any way beyond routing) is
still open for a clean, deliberately-triggered rep in a future iteration.

## What to distrust

- F60's live reproduction is a single Haiku run; whether Codex reaches the same
  "resolves-the-question-itself-mid-turn" shape, or genuinely blocks differently, is unverified.
- The `PYTHONIOENCODING=utf-8` check only covered `tests/` (443 tests) this run; `hub/tests/` (3127
  tests) under the same axis remains unverified as of this document.
- The organic Codex permission-mode observation above is real but not self-triggered — treat it as a
  structural confirmation, not a full closure of Q8's Codex leg.
- F52's isolated CLI-level git-refusal root cause is still unexplained after six repro attempts; do
  not assume it is understood just because its consequence (F52's original A-severity claim) was
  downgraded.
