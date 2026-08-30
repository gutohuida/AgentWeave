# Autonomous run log — 2026-08-30, decided work and drive

**Brief:** `.claude/autonomous/STATE.json` · **Branch:** `autonomous/2026-08-30-decided-work-and-drive`
**Cut from:** `master` at `7224d42` · **Stop at:** 2026-08-30T12:00+01:00
**Runner:** `claude` (Opus 5), posture `unattended-full-access`

Newest entry at the **bottom**.

---

## Iteration 0 — prepared 2026-08-30 ~02:00, by the interactive session

Not a work iteration. What was removed from the run's path before it started.

### What the operator decided while awake

Four decisions were taken in the session that prepared this run, and all four are written into
`scripts/drive/FINDINGS.md` so the loop implements rather than re-litigates:

1. **F14 + F60** — park the task at ask time **and** flag the timeout outcome, in one change.
   F60's parked half stops being parked and ships with F14.
2. **F115 part (2)** — detect at the tool-event parse point, and name the recorded fact for exactly
   what it catches: *a file tool wrote outside the workspace*, never "escapes".
3. **The drive is guaranteed.** The operator extended the stop from 10:00 to 12:00 specifically to
   make room for it, so it is time-boxed by the 08:00 rule rather than conditional on the queue
   emptying.
4. **Delete the merged branches.** Done — `autonomous/2026-08-29-decided-fixes-and-drive` and
   `f131-continue-starts-what-it-names` are gone from local and origin.

### What was created so the loop would not have to

- **The F131 spec loop, all three rounds, merged to master** (`7224d42`). F131-IMPL is the first
  queue item and its proposal, design, spec delta and `tasks.md` are already on the branch it will
  cut from. Without this the run would have had to re-do a loop that was already finished on a
  branch it would never have seen.
- **F115's decision, the field research, and a variant the operator raised** — appended to F115:
  that "a worktree is not a sandbox" is the explicit industry consensus, that containment is
  buyable (`@anthropic-ai/sandbox-runtime`) rather than buildable, and that an agent writing into
  *another agent's* worktree is worse than writing into the operator's, because
  `snapshot_worktree` auto-commits it onto the wrong agent's branch under that agent's name.
- **F66 closed.** Its status line claimed it was waiting on an operator decision. It was not — the
  question was answered in code four days earlier by `2026-08-27-every-run-knows-its-task`. Left
  as-is it would have cost this run an iteration.

### Environment, measured rather than assumed

| Check | Result |
|---|---|
| CI on `894d5b2` | **all nine jobs green** (run 33271924205), verified job-by-job |
| Code changed since that commit | **none** — `git diff --name-only 894d5b2..7224d42 -- hub/hub hub/tests src tests` is empty, so CI still describes this tree |
| Hub suite | 3555 passed / 84 skipped / 1 xpassed / **0 failed**, 13:38. The F109 flake did **not** fire |
| CLI suite | 440 passed / 3 skipped |
| Gates | `ruff` clean · `black` 520 files unchanged · `mypy` clean |
| Hubs responding | 8010 (operator's trial) and 8011 both `{"status":"ok"}` at 01:56 |
| `openspec validate --strict` | `continue-starts-what-it-names` valid |
| Drive harnesses | 39 under `scripts/drive/` |

One thing that was **red and is now fixed**, worth carrying: CI failed on the first merge tonight,
in `test_request_strictness.py`, with *"found no request body models at all"*. Not a product
regression — the probe walked `app.routes` directly, which finds nothing on the Starlette CI
resolves (1.6.0 nests routes under `_IncludedRouter`) while the dev machine's 0.52.1 flattens them.
`hub/tests/_routing.py` already existed for exactly that split. **If a route-table walk ever returns
zero, suspect the Starlette version before suspecting the code.**

### Five pre-authorised decisions

`decisions_for_user` D1–D5 cover: a task `blocked` while its run is `running`; whether new state is
a column or derived; where a detected outside-workspace write is recorded; that F129+F132 gets
**round 1 only** and is not to be built unattended; and which drive findings to fix versus file.
Each carries the cost if the default is wrong.

### Queue

27 items. F131-IMPL, then four-item spec loops for F14+F60, F115, F130, F127, F111+F3 and F113,
then F129+F132 **round 1 only**, then the drive. Ordered so stopping anywhere leaves complete
changes rather than half-written proposals.

**Ready.** Nothing is waiting on the operator.

---

## Iteration 1 — 2026-08-30 02:10 → 03:0x — F131-IMPL

**Queue item:** `F131-IMPL`. Its spec loop was already complete on master
(`openspec/changes/continue-starts-what-it-names`), so this was implementation only, working
`tasks.md` in order. Seven task groups, seven commits, all pushed.

### What was wrong

`POST /conversations/{id}/continue` is addressed to one conversation and derived
`started = result.waiting_reason is None` — which answers *"did a turn begin for this agent"*.
`schedule_agent` builds its turn from the oldest eligible entry across the agent's **whole** queue,
so the conversation that starts is frequently not the one addressed. The operator pressed Continue
on A, was told A started, and B ran: no run, no output, no error in A, and the obvious next act is
to press it again.

### What shipped

| Group | What |
|---|---|
| 1 | The reproduction, passing against unmodified code |
| 2–3 | The route: compare `result.response.conversation_id` to the addressed one, mirroring `agent_trigger.py:1353`; `started_conversation_id` as its own field; **two** distinct waiting reasons |
| 4 | `checkpoint_cutover.py`'s `auto_continue` diagnostic — the silent case, and the misattributed one |
| 5 | The UI's third case: the server's reason, plus the conversation that ran, **by label** |
| 6 | The drive harnesses flipped to the fixed direction |
| 7 | Gates, the full suites, and a live drive |

### The reproduction that matters is not the one F131 filed

F131 pressed Continue on a conversation with **nothing** queued for it. That path is unreachable
from the shipped UI — the button renders only when a queued entry names the conversation on screen.
The reachable path is the one the new test and the new drive build: the pressed conversation **has**
an entry and another conversation of the same agent has an **older** one, so every client-side gate
is satisfied and the substitution happens anyway. The two cases also need different answers, because
telling a conversation that queued nothing that its input is "waiting behind other input" reports a
queue position that does not exist. Both are now recorded in `FINDINGS.md` under F131.

### Getting two entries queued at once is the whole difficulty of driving this

Every ordinary route into the queue schedules the agent immediately, and every run end re-drains it,
so an entry cannot simply be parked next to another. **A cutover with auto-continue off is the one
operator act that queues without scheduling.** Two of them, on two predecessors of the same agent,
build the state exactly. That is what
`scripts/drive/t_f131_start_reported_to_its_own_input.py` does, and it is worth remembering for any
future drive that needs a queue that is not moving.

### The drive found the harness wrong, not the product

First live run: **14/15**. The failing assertion was "no run for the conversation that was pressed",
checked *after* waiting for idle — by which time the re-drain had correctly delivered that entry and
run it. Correct behaviour, wrong assertion. It is now measured at the instant of the press, and the
delivery afterwards is asserted **on purpose** as step 6: the wait ending is what made "waiting
behind other input" a true statement rather than a polite one. Second run: **17/17**.

### Verification

| Check | Result |
|---|---|
| Live drive, `t_f131_start_reported_to_its_own_input.py`, own Hub on 8011 | **17/17** |
| New backend tests fail without the fix | 4 of 5 in the new file, 2 of 3 in `test_checkpoint_cutover.py` |
| New UI test fails without the fix | 1 of 3 (the new case) |
| `ruff` / `black` / `mypy` / `npm run lint` | clean |
| CLI suite | 440 passed / 3 skipped |
| UI suite | 1449 passed across 140 files |
| Hub suite | filled in below when it returned |
| `openspec validate --strict` | change and capability both valid |

**The Hub on 8011 was restarted before the drive.** It had been up since 2026-08-29 18:06, so it was
serving code older than this iteration's edits. A drive against a stale build attributes behaviour
to code you did not change — the most expensive failure mode there is here.

---

## Iteration 2 — 2026-08-30 03:05 → 03:3x — finishing F131-IMPL's tail

**Takeover.** Iteration 1 ended mid-closeout: the driver log records it holding at 02:36 with the
Hub suite at 55%, and it never came back. Its seven implementation commits are all on the branch and
pushed; what died with it was the last row of `tasks.md` — the suite result, the gates, the archive
— plus an uncommitted spec sync and an uncommitted log entry. This iteration is that tail, nothing
more. `next_action` still said "start F131-IMPL"; the work was done, the closing was not.

### Reconciliation

| Claim in STATE.json | Actual | Verdict |
|---|---|---|
| branch `autonomous/2026-08-30-decided-work-and-drive` | same | ✓ |
| `iteration: 1`, `current: F131-IMPL` | HEAD `ec80d7a`, seven F131 commits | ✓ work done, state not advanced |
| working tree | dirty: log entry, heartbeat, and the spec sync | expected mid-closeout debris, kept |

### I re-drove it rather than trusting the claim

Iteration 1 reported 17/17 and then died, so the number had no witness. **The Hub on 8011 was gone**
— the process died with its parent — so this was not even a stale-build question; there was nothing
serving. Started a fresh one from source at `ec80d7a` and ran the harness again:
**17/17**, with real conversations (`conv-2687025b6656` starting while `conv-a8ea44ca2beb` was
pressed), a real run for the one *not* pressed, none for the one that was, and the pressed entry
still queued at the instant of the press. Iteration 1's claim stands, now on its own evidence.

### The unfinished tasks, closed

| Task | Result |
|---|---|
| 7.1 Hub suite | **3563 passed / 84 skipped / 1 xpassed / 0 failed** in 22:05. Baseline was 3555 passed — the difference is exactly the eight tests this change added, and nothing regressed. The F109 flake did not fire |
| 7.3 gates | `ruff` clean · `black` 521 unchanged · `mypy` clean · `npm run lint` clean |
| 7.5 live drive | **17/17**, re-driven this iteration on a Hub started from current source |
| 7.6 `FINDINGS.md` | already written by iteration 1 (`ec80d7a`); verified present, both corrections recorded |
| 7.7 validate, sync, archive | `continue-starts-what-it-names` valid · `agent-conversation-workspace` valid · delta synced · archived as `2026-08-30-continue-starts-what-it-names` |

Also re-run rather than inherited: CLI suite **440 passed / 3 skipped**, UI suite **1449 passed
across 140 files**, and `AW_CHECK_UI_BUNDLE=1 test_ui_build_stamp.py` **13 passed** — the strict
form, which is what actually proves `hub/hub/static/ui` was built from the committed source rather
than merely carrying a stamp.

### One thing worth carrying

`pytest --timeout=300` is not available here — `pytest-timeout` is not installed, and the run exits
`4` with *"unrecognized arguments"* before a single test runs. Cost one wasted suite launch. Bound a
long suite with the tool's own backgrounding, not with a plugin flag this repo does not have.


---

## Iteration 3 — 2026-08-30 03:35 → 03:4x — F14-R1

**Queue item:** `F14-R1`, round 1 of three on the F14+F60 spec loop. Explore the code, write the
proposal, implement nothing. `openspec/changes/a-task-waits-while-its-run-waits/` — proposal,
design, delta, tasks — committed at `d8882c0` and pushed.

### Reconciliation

| Claim in STATE.json | Actual | Verdict |
|---|---|---|
| branch `autonomous/2026-08-30-decided-work-and-drive` | same | ✓ |
| `iteration: 2`, HEAD `7bb95a4` "release the branch after iteration 2" | same, tree clean | ✓ |
| `next_action`: start F14-R1, do not revisit F131-IMPL | F131 archived under `openspec/changes/archive/2026-08-30-continue-starts-what-it-names/` | ✓ nothing to take over this time |

### What the proposal says

Both halves of the operator's decision in one change. **(a)** the park moves from
`run_divergence.evaluate_run_end` — `block_task_for_question`'s only caller today — to the moment
`ask_user` blocks, in the agent-facing question routes. **(b)** when the tool's wait expires and the
agent proceeds anyway, the Hub is told, the task returns to `in_progress`, and the question keeps a
durable mark that its wait ended unanswered; the task then carries a derived, **permanent**
statement that the work proceeded without an answer.

Delta is `task-lifecycle-governance` alone: three MODIFIED requirements ("A task is recorded as
waiting because the system observed it", "Only an unanswered blocking question makes a task wait",
"Starting work is gated on its prerequisites") and two ADDED.

### The two things the queue entry told round 1 to settle

**(i) `blocked` while the run is `running`.** Checked every reader of task status rather than the
three the entry named. Seven are already safe and the proposal records *why*, so rounds 2 and 3 can
attack the reasoning instead of rebuilding it: `evaluate_run_end` (the runtime park is
`origin=runtime`, so `run_advanced_its_task` still answers False, and the already-blocked branch
returns None into a status check that returns None), `bind_run_to_task:430`, `CLAIMABLE_STATUSES`,
the loop board, `_free_agents`, `scheduler.py:642` (already reads `("in_progress", "blocked")`
together), and `LIVE_STATUSES` (a decided exclusion, widened in window, not changed in kind).

One is **wrong**: `dependency_state` (`tasks.py:317`) derives `running_on_regressed` from
`response.status == "in_progress"` alone, so a parked task whose prerequisite regressed reads
`gated` — "has not started" — about work that has started and is waiting. `blocked` is reachable
only from `in_progress`, so it has always started. Wrong today; this change widens the window from
"after the run ends" to "the whole wait", so it is fixed here.

**(ii) The `blocked → completed` timeout path.** The answer is that the edge stays absent.
`task-lifecycle-governance:413` already forbids it, in a sentence written for exactly F60's record
— *"no recorded history states a task was completed while still waiting on a person who never
answered"*. F60 escaped it only because the task never entered `blocked` at all. Half (a) puts it
there, and then half (b) is what the requirement **forces**, not an addition beside it: the wait has
to end explicitly, through `in_progress`, before the work can be recorded as done.

### Two things the exploration found that the recorded decision did not anticipate

Both are the round earning its cost, and both would have shipped as defects.

1. **The dependency gate runs on `blocked → in_progress`** (`task_transition_service.py:371-383` —
   its own comment names the resume edge). `release_block_for_question` swallows the refusal, so
   today an answer can silently fail to release a task whose prerequisite regressed while it
   waited. Short window, nobody has hit it. After (a) the window is the whole wait, and after (b)
   the release is what lets the agent finish — so a refusal answers `update_task(completed)` with
   `409` from `blocked`, for work the agent has actually completed, with no action available to it.
   Resuming a wait is therefore ungated, derived from the task's status inside the transition
   service rather than from a flag a caller can forget.

2. **`unanswered_blocking_question` would match a question whose wait already ended.** It selects
   `blocking AND NOT answered AND NOT declined`. A run that timed out, proceeded, and then ended
   *without* moving its task would be parked as "waiting on a person" — recording a wait that had
   already finished and suppressing a divergence that is real. The predicate gains
   `wait_ended_at IS NULL`, and both its readers inherit it.

### Decided rather than left open

* **Who says the wait ended.** The Hub cannot observe it: it knows the run is running and the
  question is unanswered, but not whether the tool is still waiting. `QUESTION_ANSWER_TIMEOUT` is
  the tool's own, resolved in `mcp_server.py` with a 240 default the Hub never sees (it sets
  `AW_QUESTION_TIMEOUT` only when `Agent.question_timeout_seconds` is non-null). So the tool reports
  both ends: `wait_seconds` at ask time, recorded as `wait_expires_at`, and an expiry report the Hub
  refuses if that deadline has not passed. A missed report leaves the task `blocked` — today's
  behaviour, and the right one for a run that died rather than proceeded.
* **The mark is permanent**, not cleared by a later answer. F60 measured the operator answering five
  minutes after the run ended, choosing the option the agent did *not* ship; clearing the mark then
  would erase the record of the unilateral call at the moment it becomes most misleading.
* **The release rule for a batch is not touched.** `run-task-binding:684` requires answering *any*
  recorded question to release, so answering one of four returns the task to `in_progress` while its
  run waits for the rest. That is the strongest argument for keeping `awaiting_answer_reason` rather
  than folding it into the status, and the proposal says so instead of quietly re-deciding a shipped
  requirement.

### Adjacent defect, recorded and not fixed

`scheduler._pending_loop_request` (`scheduler.py:376-382`) selects the loop's outstanding question
with `Question.answered == False` and **no `declined` exclusion**, so a question the operator
explicitly closed is still reported as what the loop is waiting on. Every other reader of that
predicate excludes `declined`. Out of scope — it is a loop stop reason, not a task status — and
written into `design.md` so it is not lost.

### Verification

A proposal round produces no runnable behaviour, so verification is what it can be, and is stated as
such rather than dressed up:

| Check | Result |
|---|---|
| `openspec validate a-task-waits-while-its-run-waits --strict` | valid |
| Every code claim read at source | yes — `run_task_binding.py`, `run_divergence.py`, `task_transitions.py`, `task_transition_service.py`, `tasks.py`, `agent_actions.py`, `questions.py`, `mcp_server.py`, `scheduler.py`, `jobs.py`, `models.py` |
| Cited line numbers re-checked after writing | yes — three were stale and were corrected in `tasks.md` |
| Shipped requirements read before proposing against them | `task-lifecycle-governance` 407/439/474/509/535/1193, `run-task-binding` 594/618/639/663 |
| Tree clean, committed, pushed | `d8882c0` |

**Not verified, on purpose:** nothing was run. Rounds 2 and 3 exist to attack the argument above,
and `F14-IMPL` is where a reproduction has to pass against unmodified code before anything changes.

## Iteration 4 — 2026-08-30 03:50 → 04:1x — F14-R2

**Queue item:** `F14-R2`, round 2 of three. An independent re-derivation of
`openspec/changes/a-task-waits-while-its-run-waits/` against the code — not a re-read of round 1.
Committed at `19f5af2`. No code touched, which is what a proposal round should leave behind.

### Reconciliation

| Claim in STATE.json | Actual | Verdict |
|---|---|---|
| branch `autonomous/2026-08-30-decided-work-and-drive` | same | ✓ |
| `iteration: 3`, HEAD `3b2330e` "release the branch after iteration 3" | same, tree clean | ✓ |
| `next_action`: F14-R2, round 2 only, do not implement or start R3 | done as stated | ✓ |

Time at start 03:50, so the 08:00 rule did not apply.

### The finding that pays for the round

**The proposal ungates `blocked -> in_progress` and breaches a shipped requirement in a capability
it does not touch.** `task-dependencies` carries the scenario *Resuming is gated the same way as
starting* (`openspec/specs/task-dependencies/spec.md:76-80`) under the requirement *An unmet
dependency prevents starting and nothing else* (`:42`), and its archived design D1 draws the edge
into the diagram explicitly. Round 1 modified the **duplicate** statement of the same rule — the
placement half in `task-lifecycle-governance:1193` — and left the original standing. Archived as it
was, the corpus would have said the resumption is refused in one capability and "SHALL NOT be gated"
in another.

`openspec validate --strict` passed on it in round 1 and passes on it now: **it does not compare
capabilities.** That is the mechanism by which this class of defect survives a round, and it is
worth remembering for every future loop — a green `--strict` says nothing about whether a delta
contradicts a capability it did not edit.

Fixed by adding `specs/task-dependencies/spec.md` to the change, MODIFYing that requirement, and
rewriting design D5 to say a shipped rule is being reversed rather than a gap being filled.

### The rule survives, with an argument round 1 did not have

Round 1's justification was one sentence: the gate asks whether work may *start*, and `blocked` is
reachable only from `in_progress`. True, and the weakest of the three arguments available.

1. **Every refusal at that edge is necessarily a change that happened after the task started.** The
   way *into* `in_progress` is the gated edge, so a waiting task cleared the gate on the way in. A
   prerequisite can only be unmet on the way out because it left `approved` during the wait, or was
   declared during the wait. The first is the shipped requirement *A dependency that regresses after
   a dependent has started does not halt it* (`task-dependencies:105`) — "the dependent SHALL
   continue". **The current code breaches that requirement at this edge.** So the ungating restores
   a shipped requirement rather than trading one away, which inverts round 1's framing of its own
   change.
2. **The scheduler already decided this, the other way from the transition service.**
   `scheduler.candidate_is_startable` (`hub/hub/scheduler.py:619-625`) exempts `blocked` from the
   very same `dependency_gate.evaluate` call, in round 1's own words: *"Gating it would be asking
   whether work that is not about to start is allowed to start."* Board and gate contradict each
   other today at exactly one edge, and `task-dependencies` human check 13.1 is that the firing and
   the board never disagree about a queue item.
3. **The cost, now stated instead of discovered later.** A dependency *declared* while a task waits
   (`task-dependencies:262` — "the existing gate SHALL apply to B unchanged") will no longer stop it
   resuming. Small — the work is already under way, so the gate could only have prevented the record
   of it, not the work — but it is a real consequence and it now has a task (7.6) and a scenario.

### Seven more corrections

* **Task 2.8 asserted the opposite of what the code does.** It said an `under_review` task's
  blocking question records `blocked_task_id` without transitioning. `block_task_for_question`
  records it on the non-transitioning branch *only* when the task is already `blocked`
  (`run_task_binding.py:625-628`) — and that is correct, because `run-task-binding:663` is scoped to
  a task *already waiting*. Assertion inverted; design D2's "reused unchanged" survives intact.
* **Tasks 3.5 and group 7 are coupled in both directions.** Teaching the board to read a waiting
  task as `running_on_regressed` — "flagged, not stopped" — while the gate can still stop it
  permanently makes the board state something false; ungating without the board fix leaves a
  resumable task drawn as `gated`. Neither half is shippable alone.
* **Four comments state the retired fact, not two.** Round 1 named the two backend ones and missed
  `hub/ui/src/api/tasks.ts:34-43` and `hub/ui/src/components/tasks/TaskCard.tsx:115-119`.
* **The park has no commit.** `ask_question_for_actor` commits and refreshes before returning
  (`questions.py:193-195`), so the park is a second write; in the batch route it would have been
  flushed by accident by the next question's create. And nothing said what the route returns if the
  park raises — the question is committed by then, so a failed park must not cost the agent its
  question. Both written into 2.2.
* **A shipped test asserts the old rule.** `hub/tests/test_dependency_gate.py:185`
  `test_the_blocked_resume_edge_is_gated_the_same_way`, plus that module's docstring and section
  comment, plus two gate docstrings (`dependency_gate.py:7-9`,
  `task_transition_service.py:370-378`). Named in a new task 7.5 so implementation overturns it
  deliberately rather than meeting a red suite.
* **The two clocks cannot cross, and D4's refusal depends on it.** The Hub stamps `wait_expires_at`
  while serving the ask; the tool computes its deadline *after* that request returns
  (`mcp_server.py:354`) and sleeps before its first poll. So the tool's real expiry is always later
  than the Hub's recorded one, and "refuse a report that arrives before the deadline" is safe rather
  than a race. Round 1 relied on this without stating it.
* **The UI needs no behavioural change for half (a)**, and the reason deserves a test rather than an
  assumption: `TaskCard` already coalesces (`blocked_reason ?? awaitingAnswer`), so a task that is
  now both `blocked` and carrying `awaiting_answer_reason` renders one wait, not two. New task 2.6a.

### Confirmed rather than rebuilt

So round 3 spends its budget on something else: the transition map needs no edit and
`blocked -> completed` stays absent; `_guard_run_holds_the_task` fires only on `-> in_progress` and
`-> completed`, so it does not touch the park and takes its no-op branch on the expiry release
because the run is already bound; the batch parks once and records the rest through the
already-blocked branch; `release_reason` is reached on both existing exits (`tasks.py:1183`, shared
by the operator and agent PATCH routes, and `run_task_binding.py:687`); `expired` rather than
`unanswered` is the right list at `mcp_server.py:411`, and a decline leaves the wait early so it is
never marked; and all seven "safe" rows of the blocked-while-running table re-derived and hold.

### Verification

| Check | Result |
|---|---|
| `openspec validate a-task-waits-while-its-run-waits --strict` | valid, with both deltas |
| Every claim read at source | yes — `run_task_binding.py`, `task_transition_service.py`, `task_transitions.py`, `dependency_gate.py`, `scheduler.py`, `jobs.py`, `mcp_server.py`, `questions.py`, `agent_actions.py`, `tasks.py`, `models.py`, `TaskCard.tsx`, `api/tasks.ts`, `test_dependency_gate.py` |
| Shipped requirements read before contradicting them | `task-dependencies` 42/76/105/262, `task-lifecycle-governance` 413/1193, `run-task-binding` 594/618/639/663 |
| Cited line numbers re-checked after writing | yes — two were off by one and were corrected |
| Code changed | none, deliberately — this is a proposal round |
| Tree clean, committed, pushed | `19f5af2` |

**Flagged for the operator as `D6` in `decisions_for_user`:** this change now modifies a shipped
requirement in a second capability. R3 sees it next, and the operator sees it before `F14-IMPL`.

---

## Iteration 5 — F14-R3 — 2026-08-30T04:25:39+01:00

**Unit of work:** round 3 of the F14+F60 spec loop, at
`openspec/changes/a-task-waits-while-its-run-waits/`. Independent re-derivation against the code,
not a re-read of round 2. Commit `ff16cd8`. No code changed — this is a proposal round.

Started 04:05 local, well inside the 08:00 rule. Branch and `git log` matched STATE.json exactly
(`6d03795` at head, tree clean); nothing to reconcile.

### The three that change the shape of the change

**1. The guard's threshold was supplied by the party the guard exists to check.** D3 had the ask
carry `wait_seconds`, justified by "the Hub does not know the effective value and cannot compute the
deadline". That is false. `agent_trigger.py:955` builds the child environment from the Hub's own
`os.environ`, `:973-974` overwrite `AW_QUESTION_TIMEOUT` from `Agent.question_timeout_seconds` when
set, and `mcp_server.py:834`'s `_configured_wait` falls back to 240 and to 240 again for anything
outside `[10, 600]` — every input is Hub-side. And `mcp_server.py:801-802` already restates two
constants under the comment "A test asserts the two agree", which is this codebase's sanctioned
answer to the stdlib-only import rule, so the stated cost of restating was not a real objection
either.

The sharper half is not the cost. `wait_seconds` would have arrived on the **agent-facing** ask
schema, over the run's own credential — the same channel and the same caller as the expiry report.
A run wanting to park and instantly unpark sends the floor and reports immediately. The proposal's
crux says the refusal "is what keeps this a report of a fact rather than a lever" and
`task-lifecycle-governance:445` is the requirement it keeps; a threshold chosen by the guarded party
keeps neither. Now computed Hub-side while serving the ask. Tasks 4.3/4.4 replaced; `mcp_server.py`'s
ask is untouched by this change.

The column survives, and round 3 gave it the reason it never had: `Agent.question_timeout_seconds`
is operator-editable while the run waits, so a deadline recomputed later would describe a wait that
never happened. That is the one place this change knowingly declines D2's prefer-derived default,
and it now says so.

**2. One tool call bypasses the entire change.** `task-lifecycle-governance:445` forbids leaving the
waiting status by assertion as well as entering it. Only entering is enforced — `tasks.py:1157`
refuses a non-operator setting `blocked`, and `mcp_server.py`'s `TaskStatus` withholds it. Nothing
guards the way out: `TRANSITIONS["blocked"]["in_progress"]` is `_BOTH`, the PATCH route applies no
check, and `in_progress` is in `TaskStatus` and named in `update_task`'s docstring as an ordinary
option.

Today that is latent, because a task reaches `blocked` only once its run has ended — the agent that
could assert its way out is gone. **Ask-time parking removes precisely that protection**, and the
tool's own closing line ("Continue as best you can") supplies the motive: wait out 240s, do the work,
get a 409 on `blocked -> completed`, then call `update_task(in_progress)` and complete. The task
finishes with no `wait_ended_at` and no statement — F60, through the door this change opens, past
the refused endpoint, the recorded deadline and the permanent mark alike. Group 7's ungating removes
the last incidental obstacle, since the dependency gate was the only thing that ever refused this
edge. New D10, new group 2b, two new scenarios.

This is the same shape as 2026-08-28: rounds 1 and 2 both breached a requirement that had already
shipped, and the breach was in what the code *permits*, not in what the proposal *says*.

**3. "Every reader of task status was checked" missed the module whose whole job is that question.**
`task_attribution` is not in the proposal's blocked-while-running table, and it is the one surface
with a shipped scenario keyed on `blocked` by name (`agent-loops`, *A task waiting on a person*).
`attribute` (`task_attribution.py:176-188`) consults `live.task_ids` **only inside its `unstaffable`
branch**; a `blocked` task is never unstaffable and `jobs.py:352` passes empty staffing besides, so
the fall-through reaches `CAPACITY_ASSIGNED` — whose own comment reads "nothing is running" — for the
whole wait, about an agent mid-turn on that exact task. The requirement contains both halves of the
collision: "whether an agent is mid-turn on a task is answered by the runs the system started" and
the blocked scenario. They cannot collide today. Decided for `working`, with the scenario split in
two. New D11, new group 3a.

### Four more

* **Two different cases merged into "the report never arrives".** The proposal and the ADDED
  requirement both name two causes — tool died, run killed — and conclude "nobody proceeded". There
  is a third: **sent and did not land**, which task 5.5 *requires* be swallowed. Then the agent did
  proceed, the task is left `blocked`, and `update_task(completed)` is refused — which is not
  "today's behaviour" and is the stranding D5 ungates the resume to prevent, arriving by a different
  door. `expire_permission_request` (`agent_actions.py:766`) solves the identical problem one router
  away and states the design in a line: *"The run reports and the run's end sweeps."* This change
  took one half. New group 5a adds the sweep, at a boundary already past the deadline so it can
  never fire early.
* **The predicate has two readers; the concept has five.** D6 added `wait_ended_at IS NULL` to
  `unanswered_blocking_question` and `_attach_awaiting_answer` and stopped. Three more derive
  "somebody is waiting" from `answered = False`: `conversations.py:424` (navigation's attention
  state, which by its own docstring outranks `running`, and whose shipped rationale is *"because a
  waiting run consumes its configured timeout while the operator is unaware of it"* — spent, once
  the run goes back to work), `jobs.py:385` (a loop's open-question count) and `checkpoints.py:293`
  (`open_questions`, read by the successor *agent*). Decided separately: the first two excluded, the
  third **kept and marked**, because a successor must know a decision was already taken without the
  operator. `conversation_attention` contains its own answer — its permission arm already excludes
  `expired` and only the question arm had no expired state to exclude.
* **The mark was narrower than its own requirement.** Keyed on `blocked_task_id`, which
  `block_task_for_question` records only where the task parked. A run bound to an `under_review`
  task waits out the full deadline, decides for itself, and the task carries nothing — F60 with a
  different starting status. Widened to `_attach_awaiting_answer`'s two-arm shape, minus its
  `Run.status == "running"` condition, which belongs to a live wait rather than a permanent record.
* **The run-end fallback does not cover "a question asked in an earlier turn".**
  `unanswered_blocking_question` selects `created_by_run_id == run.id`, and its docstring says why:
  *"A question another run left unanswered is not evidence that this run stopped for it."* An
  earlier turn is an earlier run. The other stated case — a task not `in_progress` at ask time — is
  near-unreachable, since binding drives a task to `in_progress` and the statuses that refuse the
  park have no way back without the operator. The fallback's real remaining job is the one nobody
  listed: a park that raised and was swallowed (task 2.2).

### Confirmed against the code, not overturned

The two soft spots STATE.json named for this round both survive, and one of them properly:

* **the batch releasing on the first answer** is genuinely covered by `awaiting_answer_reason`.
  `block_task_for_question`'s already-blocked branch records `blocked_task_id` on every later
  question of the batch, and `_attach_awaiting_answer`'s first arm (`tasks.py:372`) matches on
  exactly that, with `setdefault` over `ORDER BY created_at, batch_index` naming the earliest still
  unanswered. Round 2's claim holds.
* **`blocked` outside `LIVE_STATUSES`** stays untouched — but the *reason* was broken. The proposal
  left it because "`open_questions` covers the checkpoint case", and D6 has just found that
  `open_questions` will itself misdescribe an expired wait. The two are now linked in writing: if
  6.6 is dropped, this row reopens.
* `_guard_run_holds_the_task` takes its `run.task_id == task.id` no-op branch on the expiry release,
  so a run-attributed `blocked -> in_progress` is not refused there.
* `GET /tasks/transitions/allowed` is hardcoded to `ACTOR_OPERATOR` (`tasks.py:1301`), so group 2b's
  guard does not make the operator's status control offer a move that then fails. Written into 2b.6
  as an assertion rather than left as an assumption.

### Verification

| Check | Result |
|---|---|
| `openspec validate a-task-waits-while-its-run-waits --strict` | valid, with **five** deltas |
| Every `## MODIFIED` header matches a requirement in the corpus verbatim | checked mechanically, all five; the three non-matches are all under `## ADDED` |
| Every claim read at source | `agent_trigger.py`, `launchability.py`, `mcp_server.py`, `agent_actions.py`, `questions.py`, `tasks.py`, `task_attribution.py`, `task_transitions.py`, `task_transition_service.py`, `dependency_gate.py`, `run_task_binding.py`, `run_divergence.py`, `scheduler.py`, `jobs.py`, `conversations.py`, `checkpoints.py`, `test_dependency_gate.py`, `test_task_transitions_api.py` |
| Shipped requirements read before contradicting them | `agent-loops` (capacity, loop state), `agent-conversation-workspace` (attention state), `conversation-checkpoint`, `run-task-binding` 594/618/663, `task-lifecycle-governance` 413/445, `task-dependencies` |
| Cited line numbers re-checked after writing | yes — `mcp_server.py:354`, `tasks.py:1157`, `task_attribution.py:176-188`, `run_task_binding.py:628/687`, `agent_actions.py:766`, `scheduler.py:377-382` |
| Code changed | none, deliberately |
| Tree clean, committed, pushed | `ff16cd8` |

**The change grew from two deltas to five.** That is the honest consequence of round 2's own lesson
— `--strict` does not compare capabilities — applied to the concepts rather than the capability
names. Task 9.5 now names all five and says what to grep for after archiving.

**F14-IMPL is now materially bigger** than when it was queued: eleven task groups rather than eight,
three of them added by this round. The operator sees this before it is built.

---

## Iteration 6 — F14-IMPL — 2026-08-30T04:29–05:37+01:00 — reconstructed

Iteration 6 left no entry of its own: it implemented the whole change and then died at 05:37 with
the Hub suite still running, so the closeout never happened. What follows is reconstructed from its
own commits and its final report in `driver.log`, and is marked as such — the claims below were
verified independently in iteration 7 rather than inherited.

Eighteen commits, `bb3d3e7` … `3cec5a5`, one per task group:

| Group | What shipped |
|---|---|
| 1 | Both defects reproduced against unmodified code, passing first |
| 2 | A blocking ask parks its run's task as it is asked |
| 2b | A run cannot assert its own task out of `blocked` |
| 3 | Four guards for blocked-while-running |
| 3a | A run mid-turn on a blocked task reads `working`, not `assigned` |
| 4 | `wait_expires_at`/`wait_ended_at`, migration `0099`, Hub-side deadline resolver |
| 5 | `POST /questions/wait-ended`, and the release it causes |
| 5a | The run's end sweeps the wait the report never delivered |
| 6 | Five surfaces: two excluded, one kept and marked, one deliberately untouched |
| 7 + 3.5 | The resume edge ungated, and the board that had to agree with it |
| 8 | The permanent "proceeded without your answer" record, backend and UI |

Two things it got wrong and corrected mid-flight, both worth the operator seeing: the 2b guard
initially swallowed `blocked -> completed` into a 403, destroying the "two refusals are
distinguishable" requirement — it is now scoped to edges the map already permits; and the
wait-ended endpoint first rolled back inside its loop, which would have lost earlier questions'
writes, so it now commits per question.

Left open: **9.2** (the full Hub suite) and **9.5** (sync the five deltas and archive).

---

## Iteration 7 — F14-IMPL closeout, 9.2 and 9.5 — 2026-08-30T06:04:52+01:00

**Unit of work:** the tail iteration 6 did not reach. Commits `f860fce` (sync) and `20ff1e8`
(archive). Branch and `git log` matched STATE.json; the only reconciliation needed was that
STATE.json still named iteration 6's `next_action` as if nothing had been built, while 76 of the 78
tasks were already ticked. Nothing was re-run on that account — the two unticked tasks were the work.

### 9.2 — the suite, with the difference counted rather than totalled

The task says the difference "must be exactly the tests this change adds", which a pair of totals
cannot show: a total that moves by the right amount is equally consistent with one test added and
one unrelated test lost. So the **node IDs** were diffed, against a throwaway worktree of the F131
close-out commit `2e5586c`:

| | |
|---|---|
| baseline | 3648 collected = 3563 passed / 84 skipped / 1 xpassed |
| now | 3726 collected = **3641 passed / 84 skipped / 1 xpassed / 0 failed**, 22:46 |

Added, 79: `test_a_task_waits_while_its_run_waits.py` +56, `test_question_wait_resolution.py` +15,
`test_task_attribution.py` +4 (3a), `test_dependency_gate.py` +3 (group 7). Removed, 1:
`test_dependency_gate.py::test_the_blocked_resume_edge_is_gated_the_same_way`, deleted on purpose
because group 7 ungates precisely that edge. Net +78.

**The seventy-ninth was worth the trouble of counting this way.** Per-file arithmetic said 77;
the suite said 78. The extra one is
`test_no_console_flash.py::test_every_spawn_reaches_console_suppression[0099_question_wait_window.py]`
— a parametrisation over the migrations directory, in a file this change never edited, which picked
up group 4's new migration by itself. It is this change's test, arrived at without this change
writing it. A totals-only check would have shown 78 against an expected 77 and had nothing to say
about which of the two numbers was wrong.

Skips and xpasses unchanged; F109 did not fire.

### 9.5 — five deltas, synced mechanically because `--strict` cannot check this

The task's own warning is that `openspec validate --strict` does not compare capabilities, so a
missed delta validates clean. The sync was therefore done by a script that locates each `MODIFIED`
requirement by its **verbatim** header and refuses rather than guesses if the header is absent, then
appends each `ADDED` one; a dry run printed every replacement and its size before anything was
written. All eight resolved: three MODIFIED + two ADDED in `task-lifecycle-governance`, two MODIFIED
in `agent-loops`, one MODIFIED each in `task-dependencies` and `agent-conversation-workspace`, one
ADDED in `conversation-checkpoint`.

Then the four greps 9.5 names, all of which pass: `"Resuming is gated"` gone from the whole corpus;
`"unanswered, non-declined questions"` gone from `agent-loops`; `"holds an unanswered question"`
gone from `agent-conversation-workspace`; and `agent-loops` carrying **two** waiting-on-a-person
capacity scenarios rather than one.

Archived as `openspec/changes/archive/2026-08-30-a-task-waits-while-its-run-waits`, with the
`.openspec.yaml` every other archived change carries and this one had never been given.
`openspec list`: no active changes. `openspec validate --specs --strict`: 43 passed, 0 failed.

**One environment note worth keeping.** `git mv` of the change directory failed with `Permission
denied` twice. The cause was two `find /` processes left running from a badly-scoped search earlier
in this iteration, holding a handle under that path; killing them made the move succeed first try.
On Windows a stray recursive search is not merely slow, it locks directories against `git mv`.

### Verified rather than inherited

The drive was **re-run**, not carried over, on the F131 precedent that a number whose process died
has no witness:

* `t_f14_f60_wait_parks_the_task.py`, **all 15 checks**, against the 8011 Hub confirmed to serve this
  code — process started 05:27:03, newest edited file under `hub/hub` 05:22:44.
* Phase A: the task parked at ask time and read `blocked` while its asker read `running`; the loop
  board read `agent_capacity: "working"`; the rail read `waiting`; a second run's attempt to assert
  the task out of `blocked` was refused; answering released it and left no mark.
* Phase B: the wait expired by itself after ~9s, the agent's completion landed, and the finished
  task carried *"Proceeded without your answer: Which colour should the badge be?"* — which
  answering afterwards did not erase.
* No job left enabled (`Phase A loop`, `enabled=false`, re-checked over the API).

Gates re-run at this head rather than trusted: `ruff check src/ hub/ tests/` clean, `black --check
--target-version py311` 524 files unchanged, `mypy src/` clean.

### Verification

| Check | Result |
|---|---|
| Hub suite | 3641 passed / 84 skipped / 1 xpassed / **0 failed** |
| Test-count difference attributed test by test | yes, by node-ID diff against `2e5586c` |
| Five deltas synced | yes, header-verbatim; four post-sync greps pass |
| Corpus validates | `--specs --strict`, 43 passed / 0 failed |
| Live drive | 15/15, re-driven against a Hub confirmed to serve this code |
| Jobs left enabled | none |
| Tree clean, committed, pushed | `f860fce`, `20ff1e8` |

**F14 and F60 are done.** Next is `F115-R1`, and the 08:00 rule still governs: if a fresh iteration
reads this after 08:00, it starts `E2E-DRIVE` instead.

---

## Iteration 8 — F115-R1 — 2026-08-30T06:35:23+01:00 → 06:46:20+01:00

Branch verified against `STATE.json` before anything: `autonomous/2026-08-30-decided-work-and-drive`
at `480b927`, clean, matching `origin`. Claimed with a heartbeat commit, then straight into the
round.

The unit was **round 1 of the F115 spec loop** — explore the code, then write the proposal. No
implementation. Written at `openspec/changes/a-write-outside-the-workspace-is-recorded/`: proposal,
design (D1–D8, plus five questions handed to rounds 2 and 3), `tasks.md` (40 tasks in 9 groups,
reproduction first), and **three** spec deltas.

### What round 1 found, which is a defect in the finding's argument

F115 argues from a premise that is false, and the premise is load-bearing for where the fix belongs.
The finding says *"in the posture an operator is most likely to be running, nothing shows the path
and nothing constrains it."*

`DEFAULT_CLAUDE_PERMISSION_MODE = WORKSPACE_PERMISSION_MODE` (`hub/hub/runner_commands.py:66`). The
default posture routes every tool call to `mcp_server.approve_tool_call`, and `_decide`
(`hub/hub/mcp_server.py:864-916`) refuses anything resolving outside `AW_WORKSPACE_DIR` on a
`realpath` + `commonpath` + `normcase` comparison. There is a shipped requirement of record for it —
`agent-run-sandboxing`, *"A posture exists in which the workspace boundary is enforced per tool
call"*.

**Measured, not read**, by importing the module and calling it against this checkout:

```
outside abs : {'allow': False, 'reason': "'...\aw-outside\drive-note.txt' is outside your workspace"}
inside rel  : {'allow': True,  'reason': 'inside your workspace'}
traverse .. : {'allow': False, 'reason': "'../drive-note.txt' is outside your workspace"}
read outside: {'allow': False, 'reason': "'...\aw-outside\drive-note.txt' is outside your workspace"}
default posture: workspace | without approver: acceptEdits
```

So the default posture refuses the exact call F115 reproduced, including the `..` traversal variant,
and checks reads as well as writes. And `run-72de0f5c6898` — the run that escaped — was **`manual`**,
the posture in which the *operator* answers. The card named the tool and the full absolute path, and
it was allowed. **The escape was an approval, not a hole in the default.**

This is the sharper variant CLAUDE.md names: an argument can be wrong while everything it argues
about is right. The operator's four decided parts do not move. What moves is the gap's location — not
"the default posture is blind" but "an outside write leaves no trace in **any** posture where it is
possible": `manual` where the operator approved it, full access which checks nothing, and the
`acceptEdits` fallback used where no Hub MCP server is configured to answer
(`runner_commands.py:73`). Plus one surviving even under `workspace` — a shell command that builds
its path at runtime, which `_decide` says of itself is *"a boundary, not a sandbox"*.

**Part (4) could not be written as the operator worded it.** "Native does not confine, Docker does"
is false in both directions: native's default posture *does* check, and native's unchecked postures
exist too. The proposal states it **per posture**, which serves part (4)'s intent — say plainly what
is checked — with a sentence that is true. Per the run's limits, the contradiction is recorded rather
than silently re-decided: a new section `### Round 1 correction, 2026-08-30` sits under F115 in
`scripts/drive/FINDINGS.md`, keeping the decision and correcting the premise.

### The other things the exploration settled

- **Detection cannot happen downstream of `tool_use_event`.** That constructor redacts, stringifies
  and truncates the input to 8 KiB into `payload["input"]` (`hub/hub/runner_events.py:134-155`), so
  by the time an event exists the structured `file_path` may be gone or cut in half. The parse point
  (`runner_parsing.py:264-272`) has `block.get("input", {})` intact. This answers in advance the
  question the R2 queue entry was written to ask.
- **The parser cannot classify, only extract.** Naming *which* workspace was written into needs the
  project root, which a pure line-parser has no business holding. So `ParsedLine` carries the write
  paths and `_flush_line` (`agent_trigger.py:1877`) — which already has `work_dir`, `run_id`,
  `project_id`, `agent` in scope — does the classifying.
- **One boundary, not two.** `AW_WORKSPACE_DIR`, `Run.workspace_dir` and `_execute_run`'s `work_dir`
  are all `effective_work_dir` (`agent_trigger.py:1023`, `:1095`, `:1146`). The detector must use
  that same value; recomputing a workspace from the agent's name would give the product a second
  boundary able to disagree with the first, which `agent-run-sandboxing` already forbids in the
  enforcement case.
- **The kind-and-name vocabulary already exists** (`WorkspaceBranch`, and `workspace-isolation`'s
  *"A reported workspace says which namespace it belongs to"*), and the whole layout is derivable
  from pure helpers in `worktrees.py` — `worktree_path`, `task_worktree_path`, `review_path`. So the
  cross-worktree destination is classifiable with no database and no git.
- **D3 answered without a new table.** The fact goes on `Run` as a nullable JSON column, because
  F71's footprinting reads per run and `EventLog` has no `run_id` column — a run id lives in its JSON
  `data`, so making footprinting read it would be an unindexed scan of a project's whole activity
  history to answer a question about one run. The operator's notice follows the shipped
  `turn_produced_nothing` precedent (`run_divergence.py:622-635`): `persist_event(...,
  severity="warn")`, once per destination per run. `NULL` means *not observed*, `[]` means *observed
  and clean* — no backfill, on migration `0096`'s own precedent.
- **Part (3) annotates, it does not move the footprint.** Footprinting the other tree would be the
  *"silently describes a tree other than the one named"* failure the shipped requirement already
  calls worse than absent evidence, with a choice attached; refusing the evidence would turn an
  observation into the containment this change is forbidden to build, arriving through the evidence
  door.

### Deltas

| Capability | Shape |
|---|---|
| `agent-run-sandboxing` | ADDED ×2 — the detection requirement (every posture, names the destination, bounded, records nothing on an unestablished boundary, with the two out-of-scope vectors written *into* the requirement so the label cannot read as coverage it lacks); and the postures documented by what they check |
| `workspace-isolation` | ADDED — a run's recorded directory says where it started, not where its writes landed |
| `requirement-traceability` | MODIFIED — *"A changed implementation raises a candidate, never an edit"*, taken verbatim and extended: the footprint reports that its run wrote outside it, without moving and without refusing |

### Verification

| Check | Result |
|---|---|
| `openspec validate --strict` | valid |
| `openspec list` | `a-write-outside-the-workspace-is-recorded  0/40 tasks` |
| Round-1 correction measured, not asserted | yes — `_decide` called directly, four cases |
| MODIFIED requirement header verbatim | yes, sliced from `openspec/specs/` by line range rather than retyped |
| Implementation written | **none**, by design — R1 explores and proposes |
| Tree clean, committed, pushed | yes |

### The next unit is F115-R2, and the clock was checked rather than assumed

Round 1 finished at **06:46**, stamped from PowerShell. An earlier draft of this entry said ~07:40
and concluded from it that nothing more could be started before the 08:00 rule bites; that estimate
was made by counting tool calls instead of reading a clock, and it was an hour out. Corrected here
rather than quietly, because the wrong number would have handed the next iteration a decision that
was never actually forced: it would have started the drive with 74 minutes of round-2 time thrown
away.

So the next unit is **`F115-R2`**, and the 08:00 rule still governs it. Rounds 2 and 3 in this loop
have each taken roughly 20–35 minutes (iterations 3–5), so one fits. It must be an *independent*
re-derivation against the code — a fresh process reading the code, not a re-read of this entry's
reasoning, which is the whole reason round 1 stops here instead of continuing into round 2 in the
same context.

R2 already has more to attack than the queue entry anticipated. Its stated question — does the
`tool_use` path carry a usable structured input at the point you would hook — is answered in the
proposal, so R2 should spend its independence elsewhere: on design D5's two-writes split, on whether
`work_dir` can ever differ from `AW_WORKSPACE_DIR` for the same run (a review checkout, a resumed
run, the app-server path), and on the Codex `fileChange` `changes` shape, which D8 admits was read
off the summariser rather than a live transcript.

If a fresh iteration reads this **after 08:00**, it does not start R2. It starts `E2E-DRIVE`.

---

## Iteration 9 — F115-R2 — 2026-08-30T06:50:15+01:00 → 06:59:35+01:00

Branch verified against `STATE.json` before anything: `autonomous/2026-08-30-decided-work-and-drive`
at `23467c8`, clean, matching `origin`. Heartbeat was 06:07, 43 minutes stale, so the branch was
free. Claimed with a heartbeat commit, then straight into the round.

The unit was **round 2 of the F115 spec loop** — an *independent* re-derivation of
`openspec/changes/a-write-outside-the-workspace-is-recorded/` against the code, not a re-read of
round 1's reasoning. The round ran **06:50 → 06:59**, both stamped from PowerShell: nine minutes,
against the 20–35 that rounds in this loop have taken.

A draft of this entry said it ended at 08:05 and queued `E2E-DRIVE` on the strength of that, which
would have thrown away an hour of round-3 time. It was wrong by 66 minutes, and it was wrong the
same way iteration 8's draft was wrong by an hour: **time was estimated by counting tool calls
instead of reading a clock.** Corrected here rather than quietly, and worth saying twice in
consecutive entries because the failure repeated within one night despite being written down. Read
the clock; do not feel the clock.

### The two corrections that change what the change would have shipped

**1. The change covered one of three transports, and the design's own carrier could not reach the
other two.** Round 1 put `write_paths` on `ParsedLine` and classified it in `_flush_line`. Walking
each transport instead of trusting that:

| Transport | Builds events via | Reaches `_flush_line`? |
|---|---|---|
| Claude (PTY) | `parse_claude_line` → `ParsedLine` | yes (`agent_trigger.py:1890`) |
| Codex `exec` (pipe) | `parse_codex_line`, `file_change` branch (`runner_parsing.py:486-499`) | yes, same line |
| Codex `app-server` | `map_item_to_events` → `List[RunEvent]` (`codex_appserver.py:448-459`) | **no** |

`_execute_run` hands the app-server case to `_execute_codex_appserver_run` at `agent_trigger.py:1738`
and returns; that path's sink is `_on_event` (`:2474`), which never sees a `ParsedLine`. And there is
no side channel: `run_turn`'s contract is `Callable[[RunEvent], Awaitable[None]]`
(`codex_appserver.py:916`), so `_on_event` receives only the event, whose `payload["input"]` is the
redacted, stringified, 8 KiB-truncated blob D2 had already ruled out as a source. Meanwhile the Codex
transport that *does* reach `_flush_line` — `parse_codex_line`'s snake_case `file_change` branch —
was named by no task in round 1 at all; task 2.5 named the camelCase app-server branch, the one that
cannot carry the field.

The fix moves the carrier to `RunEvent` (`runner_events.py:111-115`), populated inside
`tool_use_event` itself before it redacts and truncates. One population site, three transports, and
the field is never persisted — `record_agent_output` stores `kind` and `payload` only. `ParsedLine`
is left alone entirely.

**2. It breached a shipped requirement in the capability it adds to.** `agent-run-sandboxing`
already contains, at `openspec/specs/agent-run-sandboxing/spec.md:321`:

> Only refusals SHALL be recorded. An allowed action is the ordinary case, and an event per allowed
> action buries the refusals among them.

D5's operator notice is `persist_event(..., severity="warn")` for a write that was **allowed** —
approved by the operator under `manual`, or never checked at all under full access. Round 1 wrote two
ADDED requirements into that file and never cited the sentence next door constraining what may be
recorded in it. This is the same shape round 2 of the F14 loop found, in the same position: the round
that re-derives the argument is what finds a requirement the change did not think it was near.

The change now carries a **MODIFIED** delta narrowing the sentence to "recorded *as refusals*" and
stating what an allowed action must be to be recorded at all — not the ordinary case, not presented
as a refusal, bounded. The volume argument survives as a constraint rather than being deleted, and
the requirement's own fourth scenario (*"Allowed actions are not recorded **as refusals**"*) already
read narrower than its prose, which is what makes the narrowing a correction rather than a weakening.

### The other four

3. **The write-tool list already exists twice in the product**, and round 1 proposed a third that
   disagrees with both: `runner_commands.py:210` disallows exactly `Edit,Write,NotebookEdit` for a
   read-only agent, `mcp_server.py:858` holds `_PATH_KEYS = ("file_path", "path", "notebook_path")`,
   and round 1's list added `MultiEdit`, which nothing else in this codebase recognises. Dropped,
   with a reconciliation test — restate-and-assert, since `mcp_server.py` may import only stdlib plus
   fastmcp and so cannot import the new module.
4. **D8's open question answered**, from a second source rather than the summariser: the Codex
   `changes` element is `{"path": ..., "diff": ...}`, corroborated by `approval_subject` and
   `test_permission_approver.py:588-604`, which came out of **F107** — found against a live item.
   Its four malformed-input cases are copied into the tasks verbatim.
5. **One migration, not two.** Round 1 asked for a migration at 4.2 and another at 5.2. Head is
   `0099`; both columns ride `0100`, and the two head assertions are named by file and line
   (`test_migrations.py:39`, `test_project_persistence.py:227`).
6. **`_apply_footprint` cannot carry the fact on `Footprint`**, which is built from git alone while
   this fact is database state on `Run` — `restamp_run_footprints` would have to fabricate it. An
   explicit parameter instead.

Plus line-number corrections: `_flush_line` is at `agent_trigger.py:1880` not `1877` (cited three
times), `_apply_footprint` at `requirement_evidence.py:362` not `365`.

### What round 2 re-derived and did *not* overturn

Recorded because a round that only lists what it broke gives the next round no idea what was
actually checked.

- **Round 1's premise correction is itself right** — this was on the queue entry's list explicitly.
  `DEFAULT_CLAUDE_PERMISSION_MODE = WORKSPACE_PERMISSION_MODE` (`runner_commands.py:66`), applied at
  `:220`, with `DEFAULT_CLAUDE_PERMISSION_MODE_WITHOUT_APPROVER = "acceptEdits"` (`:73`) where no Hub
  tool server is configured. The comment at `:56-65` reconstructs the same history independently.
- **`work_dir` cannot differ from `AW_WORKSPACE_DIR` for a run.** `_execute_run` has exactly one
  caller (`:1138`); `effective_work_dir` is assigned on four mutually exclusive branches and written
  to all three of `Run.workspace_dir` (`:1095`), `AW_WORKSPACE_DIR` (`:1023`) and `work_dir`
  (`:1146`). A review turn is one of those branches, not an exception — so a reviewer writing into
  its own agent worktree *is* a write outside its workspace and is correctly recorded as one. Added
  as an explicit task rather than left to be found as a surprise.
- **`EventLog` has no `run_id` column** (`db/models.py:1005-1028`), so D5's argument for the column
  over the event stream stands.

### Verification

| Check | Result |
|---|---|
| `openspec validate --strict` | valid |
| `openspec list` | `a-write-outside-the-workspace-is-recorded  0/47 tasks` (was 40) |
| MODIFIED requirement header verbatim | yes — sliced from `openspec/specs/` by line range with `sed`, not retyped |
| Every correction measured against code | yes; each names the file and line it was read from |
| Implementation written | **none**, by design — R2 re-derives and corrects the proposal |
| Tree clean, committed, pushed | yes |

### The next unit is F115-R3, and there is an hour for it

It is 06:59. The 08:00 rule has **not** bitten, and round 3 has a full hour against a nine-minute
round 2 — so the next unit is `F115-R3`, not the drive. A fresh iteration that reads this **after
08:00** starts `E2E-DRIVE` instead and leaves R3 queued.

R3 has a sharpened target rather than a blank one. The **D9 narrowing is the piece most worth
attacking**: it is a judgement round 2 made, not a derivation. Narrowing a shipped requirement so a
new change stops breaching it is exactly the move that deserves a hostile reading, and the
alternative — emit no operator notification at all, and let the fact live only on the run row — is
defensible. Round 2 rejected it because a record the operator never sees is not the record F115
asked for, but that is an argument.

Two smaller ones, both of which would falsify something round 2 asserted: does anything construct a
`tool_use` `RunEvent` without going through `tool_use_event` (which would break D2's
one-population-site claim, now the whole basis of the three-transport fix), and does the extractor
really return on the tool name before touching the input, now that it runs for every tool call of
every run rather than only inside a parser?


---

## Iteration 10 — 2026-08-30 07:05 to 07:20 — F115-R3, the second independent re-derivation

Branch verified against `STATE.json` before claiming it: `autonomous/2026-08-30-decided-work-and-drive`
at `50bacba`, clean tree, matching what iteration 9 recorded. Clock read from PowerShell at 07:05,
07:09 and 07:16 — the 08:00 rule never came close, and R3 took fifteen minutes against R2's nine.

Round 3 read the code against the proposal without re-reading round 2's reasoning. **Six
corrections.** The change is still not implemented; `F115-IMPL` stays queued.

### 1. The D9 crux — the thing this round was pointed at, and the premise was false

Round 2 found that `agent-run-sandboxing` says *"Only refusals SHALL be recorded"*, concluded this
change's `severity="warn"` notification breaches it because it records an **allowed** write, and
carried a MODIFIED delta narrowing the sentence. `next_action` called that a judgement, not a
derivation, and told R3 to attack it.

The judgement survives. The argument does not, and the delta it produced was three times the size
the correct argument supports.

The reading is disproved by measuring the product rather than re-reading the sentence.
`persist_event` is called 55 times across `hub/hub`, carrying **44 distinct event types**. Exactly
one — `permission_denied` — is a refusal. The other 43 record allowed things: `queue_entry_delivered`,
`question_answered`, `task_created`, `job_fired`, `agent_heartbeat`, `run_interrupted`,
`project_adopted`, `checkpoint_notes_submitted`, and so on. Under round 2's reading the shipped Hub
breaches its own requirement forty-three ways, and has since the requirement was written. A reading
that convicts the entire activity log is not the reading.

Three things agree with the measurement. The requirement's **title** is *A refusal is recorded
wherever it is decided*. Every other sentence in it is about the refusal record. And its own fourth
scenario already says the narrow thing — *"Allowed actions are not recorded **as refusals**"*. Round
2 saw that scenario and argued past it (*"the SHALL sentence is normative and the scenario is
evidence rather than a limit on it"*), which inverts openspec's structure and was only needed because
the prose had been read out of its subject.

So round 2's own question for R3 — narrow the sentence, or drop the operator notification entirely —
was **never a real fork**. Nothing in the corpus forbade the notification, so "live only on the run
row" was never the price of compliance; it would have been a straight downgrade bought to satisfy a
requirement that does not object. The notification stays.

The delta is not deleted, because the prose and its own scenario genuinely disagree by two words and
this change is the reader that tripped over the gap. It keeps *"as refusals"* plus one sentence of
scope. Removed: the paragraph legislating "an allowed action that is not ordinary", which wrote this
change's policy into a requirement about refusals and made it carry a general rule nothing enforces;
and its scenario, which moved to this change's own ADDED requirement as *The record is not a refusal*.

**The shape worth carrying forward.** Round 2 was right to go looking for a breached requirement —
that is the failure the F14 loop found — but on finding a candidate it edited the corpus to fit the
change. The cheaper move was available and not made: read the sentence against the product, and if
the product already breaches it, the reading is wrong rather than the product.

### 2. The detector would have mis-resolved every relative path

D4 described the comparison as `realpath` + `commonpath` + `normcase`, "the same construction
`_decide` uses". Both earlier rounds omitted `_decide`'s **first** line (`mcp_server.py:901`):

```python
absolute = candidate if os.path.isabs(candidate) else os.path.join(root, candidate)
```

Round 1's open question said the `..` case "should be caught by realpath before comparison — assert
it rather than assume it"; round 2 left it open. It is not caught by realpath. `os.path.realpath`
resolves a relative path against the **calling process's** cwd, and the two callers do not share one:
`_decide` *is* the spawned MCP server, whose cwd is the run's workspace — its own shell-branch comment
depends on exactly that — while the detector runs in the Hub, which serves many projects from
wherever uvicorn was started. Without the join, the delta's own scenario *A relative path that
traverses outside is caught* resolves `../../x` against the Hub's launch directory and classifies at
random. Task 3.2 now names the join as load-bearing and requires the test to run from a cwd other
than the fixture workspace, or it proves nothing.

### 3. `.agentweave/` is not "the project's directory"

Both rounds folded everything under the project root that is not a worktree into kind `project`, and
then justified `project` as the mild destination on the grounds that a write there *sits there
visibly*. That is inverted for `<root>/.agentweave/`. `repo_hygiene.EXCLUDE_PATTERNS`
(`hub/hub/repo_hygiene.py:59-80`) lists `.agentweave/worktrees|reviews|tasks|logs|evidence|context`,
and `seed_repo_excludes` writes them into the repository's `info/exclude` on **every turn** —
`resolve_agent_workspace` calls it as its first statement (`worktrees.py:627`). The Hub has told git
to hide that subtree. A write into `.agentweave/evidence/` is a run writing into the Hub's own
record-keeping about runs, appears in no `git status` anywhere, and would have been reported to the
operator as the destination that sits visibly. New `hub` destination kind, in both spec deltas, plus
a test that walks `EXCLUDE_PATTERNS` and asserts no `.agentweave/` pattern ever classifies `project`.

### 4. D3 reconciled the write-tool list against the wrong source

Round 2: *"the list already exists in the product, twice"*, and dropped `MultiEdit` because *"nothing
else in this codebase recognises"* it. Both halves are false.

It exists **three** times, and the third is the concept match: `WRITING_TOOLS` in
`hub/ui/src/components/agents/AgentTimeline.tsx:573` — `{Edit, MultiEdit, Write, NotebookEdit,
apply_patch}` — both providers, already driving the "wrote to N files" summary an operator reads.
`MultiEdit` is also at `AgentTimeline.tsx:558`, `lib/editDiff.ts:20`, and in a test against a real
`MultiEdit`-shaped payload (`agentTimeline.test.tsx:801-827`). It goes back in.

And `runner_commands.py:210` is not a statement of which tools write. Read in place it is
`restrict_spec_writes` — F4/D6, *which tools exist at all* for a spec-authoring agent, applied
unconditionally including under yolo. It is a `--disallowedTools` argument, so Claude-only by
construction: round 2's proposed assertion that every writer appears in it is **false for
`apply_patch`** and would have forced `MultiEdit` out for a reason that does not hold. Filed
separately (task 2.2c, not fixed here): `restrict_spec_writes` omits `MultiEdit` while the UI counts
it as a write, so a spec-restricted agent may be able to write through it.

### 5. D5 had no accumulator and no write point, and the obvious answer loses the record

"At most 20 entries plus a total count" and "once per distinct destination per run" are per-*run*
facts; the only sites that see the calls are per-*event* callbacks each opening their own session.
Neither round said where the state lives or when the column is written.

The precedent D5 cites points at the wrong answer. `turn_produced_nothing` fires from
`evaluate_run_end` (`run_divergence.py:672`) — at the run boundary, having read the whole run back.
Flushing this column the same way is the natural reading of D5 as written, and it loses the entire
record for a run that is killed or whose Hub restarts, which is exactly the population whose stray
writes matter. Decided: accumulate in the enclosing closure (the `nonlocal` shape `sequence` and
`accounting_sample` already use in both functions, serial within a run), and write the column **on
first sight of each destination**, in the same transaction that emits the event. At most one write
per destination, bounded by the same 20; a killed run keeps every destination and the first path into
each; only the exact call count is best-effort.

### 6. New D12 — the detector is structurally silent for a whole class of run

Neither round asked. `resolve_agent_workspace` returns `repo_root` itself on three branches
(`worktrees.py:607-636`): a read-only agent, a project that is not a git repository, and a machine
with no git. `resolve_turn_workspace` routes through it whenever `takes_task_workspace` is false, and
`agent_trigger.py:891` records the consequence in its own words —
`isolated_workspace = workspace if workspace != repo_root else None`.

For such a run the boundary is the whole project, so **nothing inside it is ever an outside write** —
including a write into another agent's worktree, the case this change calls the worst one. Not a
defect to fix here: inventing a narrower boundary for those runs would create the second boundary D4
exists to prevent, and the record is honest. What must not stand is the claim of coverage. D5 makes
`[]` mean *observed, nothing left* — and for a root-workspace run that is simultaneously true and the
least informative sentence the product could emit: the least confined run it has, reporting clean.
The requirement now says so, and D12 records the open product question (should a non-repository run
get a boundary at all?) as not this change's to answer.

### What R3 re-derived and did **not** overturn

- **D2's one-population-site claim holds.** `kind="tool_use"` is constructed in exactly one place in
  `hub/hub` — `runner_events.py:154`, inside `tool_use_event`. Task 2.5c goes from a conditional to
  an answered item with a regression test. One boundary stated: `POST .../output` accepts a
  `tool_use` kind from an agent the Hub did not spawn, which has no `RunEvent` and no workspace.
- **`write_paths` is never persisted.** `record_agent_output` takes `content`, `kind`, `payload`,
  `run_id`, `sequence` and the ids off the event and nothing else.
- **`work_dir` is in scope at both sinks** — `Optional[str]` on `_execute_run` (`:1720-1740`) and
  `_execute_codex_appserver_run` (`:2389-2406`). Round 2's list was right and **incomplete**: D4 also
  needs the project root, and `repo_root` occurs **zero** times in either function (measured across
  lines 1720-2274 and 2389-2752). Both take a new parameter; tasks 4.3/4.3b were written as if it
  were already there.
- **Round 1's default-posture premise correction survives a third reading.**
  `DEFAULT_CLAUDE_PERMISSION_MODE = WORKSPACE_PERMISSION_MODE` (`runner_commands.py:66`), with
  `acceptEdits` as the no-approver fallback (`:73`).
- **The cost objection is moot** (new D13). `tool_use_event` already runs `redact_secrets` and
  `json.dumps(sort_keys=True)` over every input unconditionally (`runner_events.py:142-143`), so a
  membership test is not measurable beside it. Keep the early return because it is what the function
  *is*; drop performance as the reason, or the next reader relaxes it when the cost argument stops
  applying.

### Verification

| Check | Result |
|---|---|
| `openspec validate --strict` | valid |
| Every correction measured against code | yes; each names the file and line it was read from |
| D9 disproof | measured, not argued — 44 `persist_event` types enumerated, 1 refusal |
| MODIFIED delta first line still carries SHALL | yes, unchanged; `--strict` reads only line 1 |
| Files touched | the five change artefacts only; **no code** |
| Implementation written | **none**, by design — R3 corrects the proposal and stops |
| Tree clean, committed, pushed | yes |

### The next unit is F115-IMPL, unless the clock says otherwise

The F115 spec loop is **complete**: three rounds, and each of the three found a real defect. R3
finished at 07:20, so there is roughly forty minutes before the 08:00 rule. `F115-IMPL` is a
substantial implementation — a new module, a migration, two sinks, an evidence change and a live
drive — and it will **not** fit in forty minutes. Starting it and parking it half-done is the one
thing the 08:00 rule forbids.

So a fresh iteration reading this should go **straight to `E2E-DRIVE`** and leave `F115-IMPL` queued
for the operator or a later run. Read the `E2E-DRIVE` queue entry in full: full-surface sweep, own
Hub on **8011** (never 8000, never 8010), Haiku bound for every real agent turn, decision D5 for
fix-versus-file, and **leave no job enabled**. The drive then has the whole window rather than a
remainder of it.

---

## Iteration 11 — 2026-08-30, 07:20 → 07:45 — E2E-DRIVE, first slice

**Unit of work:** `E2E-DRIVE`, the full-surface sweep. Started immediately rather than F115-IMPL,
exactly as iteration 10's `next_action` instructed. The clock was read from PowerShell four times
during the iteration, not inferred from tool-call count.

### The Hub, and the check that it was mine

`http://127.0.0.1:8011`, PID 19460, started 05:27 on `…/Temp/aw0830/aw0830.db`, migration head
`0099`. Confirmed it serves this checkout before trusting a single result:
`find hub/hub src -newermt "2026-08-30 05:27:03" -name '*.py'` returns **nothing**, so no Python
under test has moved since the process started. 8000 and 8010 were never touched.

Test project: **`drive-0830-sweep`** = `proj-1964cdedffe2`, a git repo created this morning at
`C:\Users\huida\Documents\drive-0830-sweep`, outside this repo. Neither protected project was
opened. Every agent turn bound `claude-haiku-4-5-20251001`.

### What was driven

| Row | Verdict |
|---|---|
| 1 Projects · 2 Runners · 3 Agents · 4 Charters | driven, `t_sweep_surface.py`, **0 unexpected** after the harness's own probe was corrected |
| 7 Tasks · 8 Dependencies · 13 Questions (API) · 18 Accounting (API) | driven, same run, 0 unexpected |
| 9 Spec · 10 Evidence · 11 Jobs (API) | driven, `t_sweep_spec.py`, 0 unexpected; F113 re-confirmed |
| **13 Questions (live)** | **PASS** — `ask_user` blocked a real turn in ~20s, the answer released it |
| **14 Permissions (live, Claude)** | **PASS** — `manual` raised a card in ~12s on two runs, `{"allow": true}` cleared it |
| **18 Accounting (live, exhaustion)** | **F133** |
| 5, 6, 12, 15, 16, 17, 19 | not reached this iteration |

### Three findings, all filed rather than fixed

**F133 (B)** — reproduced live, new harness `t_row18_budget_reason.py` (10/11, two Haiku turns).
The scheduler and the queue-status endpoint disagree about which stalled turns count as autonomous:
the scheduler asks whether *the turn it built* holds an operator entry, the endpoint asks whether
*any queued entry for the agent* is operator-origin. So an operator message queued beside a blocked
autonomous one leaves the scheduler still refusing and the panel saying **"2 waiting"** and nothing
else — the exact state `db/models.py:586` records as the defect the `waiting_reason` column exists
to remove. Filed under D5: the narrow repair duplicates the selection logic and the clean one
refactors `schedule_agent`'s hot path, which is two defensible answers.

**F134 (B)** — `{"name":"x","content":""}` on a charter answers 201, and the canonical context every
real turn is built from then ends at a bare `## Charter: x` with nothing beneath it, while `missing`
still reads `[]`. The `else` branch one line down has the better sentence (*"No charter is assigned
to this agent."*, plus `missing.append("charter")`) and cannot be reached, because `if charter:`
tests the row rather than its content. `openspec/specs/agent-charter/spec.md:56-72` governs the
neighbouring case and stops short of this one.

**F135 (C), and its continuation** — four of the sweep's own wrong turns, three of which would have
been filed as product defects by a less suspicious reading. The canonical-context probe called the
charter route with no query parameter; row 13 answered a question a different agent had left open
and called itself passing; row 14 blamed the product for row 13's run still being alive; row 14's
decision body had the wrong shape. All four corrected in place.

**F115 reproduced independently.** Two identical row-14 triggers nine minutes apart wrote to
`.agentweave/worktrees/asker/` once and to the project root once. Both permission cards offered the
absolute path; nothing marked which one left the boundary. Appended to F115 rather than filed anew —
the change's scope is settled (D3) and widening it to the approval surface is the operator's call.

### What held, and is worth not re-deriving

- `GET /fs/list` on a missing path answers 200 with `entries: []` **and a `reason`**, and
  `DirectoryPicker.tsx:158-161` renders it. The "swallowed 404" seam the sweep expected is not there.
- `name_conversation` is a documented no-op once a conversation has a title, so an operator's rename
  survives their next message (`conversations.py:139-149`).
- Clearing a token budget re-drains the queue, from **all three** routes that can change it —
  `accounting.py:61-72`, `inbound_queue.py:96-108`, `projects.py:525-527`.
- The `422` on a malformed permission decision names both the missing field and the forbidden one.
  It is this file's best counter-example to its own usual complaint about illegible 4xx.

### Cleanup

No job enabled anywhere on 8011 (the two that exist are `enabled=False` from iteration 7's F14
drive). No project carries a token budget. All three agents idle, no pending permission card, both
open questions settled. `C:/Users/huida/Documents/drive-2026-08-29` — F115's evidence — was opened
as a project on 8011 by the un-overridable harness before that was fixed, and is **intact**: its
`README.md`, `calc.py` and yesterday's note file are all unchanged and nothing was written to it.

### Next

`E2E-DRIVE` continues. Rows **5, 6, 12, 15, 16, 17 and 19** are unreached, and within row 13 the
timeout half — letting a question expire rather than answering it — was never driven; a question
with `asker_waiting: false` was observed on a completed run, which is the state that half would
examine. The fixture is warm and cheap to reuse: `proj-1964cdedffe2`, three Haiku agents
(`asker`, `driver`, `peer`), worktrees already provisioned for all three.

---

## Iteration 12 — 2026-08-30, 07:50 → 08:15 — E2E-DRIVE, rows 5 and 6 live

**Unit of work:** `E2E-DRIVE`, continued. The 08:00 rule was already in force at 07:50, so no queue
item was opened and no spec-loop round was started; the drive was the whole iteration. The clock was
read from PowerShell five times.

**Reconciliation:** branch, tree and `git log` matched `STATE.json` exactly — `f884959`, clean,
`autonomous/2026-08-30-decided-work-and-drive`. Nothing to reconcile.

### The Hub, and the check that it was mine

`http://127.0.0.1:8011`, PID 19460, started **05:27:03** on `…/Temp/aw0830/aw0830.db` — the same
process iteration 11 used. `find hub/hub src -newermt "2026-08-30 05:27:03" -name '*.py'` returns
nothing, so no Python under test has moved since it started and every result below describes this
checkout. 8000 and 8010 were never touched. Fixture reused: `proj-1964cdedffe2`
(`drive-0830-sweep`), agents `driver` and `peer` on `claude-haiku-4-5-20251001`.

### What was driven

| Row | Verdict |
|---|---|
| 5 Conversations (API) | driven, `t_sweep_conversations.py`, **0 unexpected** |
| 15 Checkpoints (API refusals) | driven, same run, 0 unexpected |
| 6 Inbound queue (API) | driven, `t_sweep_queue.py` — 0 unexpected **once its preconditions were fixed**, and F136 fell out of doing so |
| **5 Conversations (live)** | **PASS** — new `t_row5_conversations.py`, two Haiku turns, 14/14 |
| **6 Inbound queue (live hop chain)** | **PASS** — new `t_row6_hop_chain.py`, 12/12 on the clean run |

### Four findings

**F136 (B) — an unbound self-registered agent is told to install a binary named after itself.**
`launchability.py:36-43` introduces `RUNNER_UNBOUND` *specifically* to end the sentence
`Runner CLI '<agent>' was not found in PATH`, and `get_agent_config`'s docstring says the repair
"fixes both surfaces at once". Both surfaces still produce it. The branch is gated on
`not agent_row.self_registered` (`launchability.py:418`), so it is off for exactly the population
that reaches the unbound state through `POST /agents/register` and on for the one that cannot —
the UI's create route writes `self_registered=False` and demands a launchable runner up front.
Reproduced on `GET /agents/launchability` and on the queue's `waiting_reason` in the same request
cycle. The exemption's two written defences are both measurably false: nothing is refused
(`runnable` is already `false` either way), `collaboration_ready` is `null` rather than "already
saying so", and the test cited as pinning it configures its agent through `session/sync` and so
never reaches the guard. Removing the clause leaves **129 tests green** — measured across
`test_launchability`, `test_agents`, `test_agents_self_registered`, `test_inbound_queue` and
`test_agent_trigger`, then reverted. **Filed, not fixed:** a `contact_mode: "mcp"` agent needs a
third reason rather than "bind a runner in the Hub UI", and that is a design decision.

**F137 (C) — the harness that promised to spend no provider tokens had been spending them.**
`t_sweep_queue.py` names a fixed agent and never checked the three preconditions its own docstring
asserts. On the warm fixture that agent was archived (three false `UNEXPECTED` lines that were the
product refusing correctly), and then, once unarchived, turned out to have Haiku bound — so a file
whose premise is "not a single provider token" started **five real turns**, and silently swapped
what it measured: `"agent is already running"` instead of the never-launchable case. That
substitution is what had been hiding F136. Now asserts exists / open / no-runner and exits rather
than reporting on a situation it does not describe. It also drains its own leftovers now.

**F138 (B) — three harnesses hard-wired to a forbidden project, and one of them writes.**
`t_hop.py`, `t_loop.py` and `t_spec.py` carry `P = "proj-18e5d4e0"` with no `AW_PROJECT` override
and no guard, while five sibling files enforce the same rule explicitly. `aw.py` defaults `AW_HUB`
to **8010** with a live key, so the *bare* invocation of each file is the unsafe one, and
`t_spec.py` PUTs a complete change-spec document. Fixed using the shape the compliant files already
use; both refusal paths verified to exit 1 without issuing a request. No damage occurred — the files
were read before they were run, which is the only reason this is a finding rather than an incident.

**F139 (B) — the agent reached for the host's `SendMessage` and reported AgentWeave's roster as
unreachable.** Told in prose to *"use the send_message tool"*, `driver` called Claude Code's own
`SendMessage`, got `tool completed` with the message going nowhere, then loaded the host's
`ListAgents`, saw Claude Code sessions, and told the operator that `peer` "is not currently
reachable". `peer` was open, idle and bound throughout. The canonical context states the
`mcp__agentweave__` prefix rule once in a header line and then lists every tool bare. The identical
instruction had succeeded nine minutes earlier — nothing in the product decides which tool is
picked. Filed rather than fixed: qualifying the injected names is a decision about which runner the
agent-facing text is written for.

### What held, and is worth not re-deriving

- **A conversation is a real thread.** Two triggers separated by an operator rename resumed the same
  `provider_session_id`, and the agent recalled a codeword planted in turn 1. The operator's title
  survived the next turn, confirming the documented `name_conversation` no-op from the agent side.
- **The hop budget works, end to end.** Depth increments and is attributed to the agent; the
  over-budget entry is held rather than discarded; the **timeline** marks it `hop_budget_exceeded`
  (the queue listing correctly does not carry the field — it is the Continue control's flag); the
  status says "hop budget exhausted"; an operator message is not caught by it; and `release` frees
  exactly one message by resetting `hop_depth` to 0, so the budget still bounds everything after.
- The `release` refusal for an entry that is *not* hop-blocked is the best sentence in FINDINGS.md:
  it names the hop, the budget, the conclusion, and where to look next.

### Three harness lessons, all the same lesson

Every wrong verdict this iteration came from the harness, not the product, and each was the same
mistake in a new place: **guessing a shape instead of reading it.** The chat route returns `entries`
with a `kind`, not `messages` with a `role` — the first row-5 harness read every completed turn as
an empty transcript. `hop_budget_exceeded` is on the timeline, not the queue listing — the first
row-6 harness reported a correctly-held entry as unmarked. And "an entry at hop 1" matched against a
warm fixture's whole history found the *previous* run's entry in 0s and passed while this run's
agent had not sent anything. All three are now filtered, documented in place with file-and-line
references, and the preconditions are asserted rather than stated.

### Cleanup

`hop_budget` restored to 6. No queued entry anywhere on `proj-1964cdedffe2` (the six
`unbound-driver` leftovers were drained by hand and the harness now drains its own). No jobs exist,
enabled or otherwise. No token budget. All five agents idle, no pending permission card, no open
question. `unbound-driver` is left **unbound**, which is `t_sweep_queue.py`'s precondition — do not
bind a runner to that name.

### Next

`E2E-DRIVE` continues. Unreached: rows **15** (checkpoints — drive past the threshold, render,
continue, cut over; F126 and F130 already filed here), **17** (integration), **12** (flows), **16**
(worktrees), **19** (resilience), and within row 13 the timeout half. Read any harness before
believing it — that is now five harness defects in two iterations, and every one of them made the
product look worse than it is.

---

## Iteration 13 - reconstructed, not written by the process that did the work

Iteration 13 pushed **three commits** and then died without writing a log entry or rewriting
`STATE.json`. Reconstructed here from the commits and from state it left behind, so the record is
not a hole:

- `4f9c096` drive(e2e): row 15 live end to end, row 12 flows driven, and **F140**
- `3621cef` drive(e2e): rows 16 and 17 driven live, and **F141**
- `7ec409c` drive(e2e): what is on the other side of F140 - **F142** and **F143**

So rows **12, 15, 16 and 17** were reached and four findings filed. What it did *not* finish:

- `scripts/drive/t_row13_timeout.py` was written and committed but **never run to completion**. The
  proof is that it left `driver.question_timeout_seconds = 60` on the 8011 fixture - a value only
  its step 1 writes and only its `finally` restores. Cleared before this iteration's run so the
  file could capture the true original (`None`) and restore it.
- `STATE.json` was left dirty in the working tree with `last_heartbeat` bumped to `08:48` and no
  other change, and with its trailing newline stripped. Both repaired here.

No product state was left inconsistent: no job enabled, no open question, all agents idle.

---

## Iteration 14 - 2026-08-30, 09:55 -> 10:20 - E2E-DRIVE, rows 13-timeout and 19

**Unit of work:** `E2E-DRIVE`, continued, exactly as `next_action` instructed. The 08:00 rule was
in force throughout, so no queue item was opened and no spec-loop round was started. The clock was
read from PowerShell seven times.

**Reconciliation:** branch and `git log` matched `STATE.json`'s claims about the branch, but
`STATE.json` itself was **behind its own repository** - see the iteration 13 entry above. Its
`current` and `queue[E2E-DRIVE].progress` both still described iteration 11's position while three
of iteration 13's commits sat on the branch. Corrected in this iteration's rewrite.

**The Hub, and the check that it was mine.** `127.0.0.1:8011`, PID 19460, started 05:27:03 on
`.../Temp/aw0830/aw0830.db`. `find hub/hub src -name '*.py' -newermt "2026-08-30 05:27:03"`
returned one file - `hub/hub/launchability.py` - which `git status` reports **clean**: its mtime is
iteration 12's F136 experiment, measured then reverted, so its content is identical to what the
process loaded. No restart needed on that account. The drives below then killed and restarted 8011
three times by design, each time from source in `hub/` on the same database. 8000 and 8010 were
never touched.

### What was driven

| Row | Verdict |
|---|---|
| **13 Questions - the expiry half** | **PASS, 16/17.** First sweep ever to reach it. The one red check was the harness's (F144) |
| **13 Questions - the operator's own route** | **F146** - a blocking question posted by the operator is answered into the void |
| **19 Resilience - crash with a run in flight** | **PASS 4/4, twice** (`peer`, then `asker` after the harness was corrected) - F145 |
| **19 x 13 - crash with `ask_user` blocking** | **PASS 6/6** |
| **19 x 11 - crash mid job firing** | **F147** - reconciliation is right, the history it leaves is wrong |

Row 19 was recorded "not reached" in every prior sweep including iterations 11-13 of this one. It
is reached now, three ways.

### Four findings

**F144 (C)** - row 13's expiry half holds completely: the question blocks, the wait ends at 70s
against a 60s window, the run ends `idle` not `error`, and afterwards the row is
`answered=false / declined=false / asker_waiting=false`, which is exactly what
`QuestionsPanel.tsx` needs to drop it out of the red banner and stamp it "no longer waiting". The
single failing check was looking for `ask_user`'s expiry note in the agent's `/output` transcript -
a surface **F139 already established cannot carry a tool result** (`tool completed`, always). The
note *was* delivered: the agent's own thinking says "the operator did not answer within 60
seconds", and `60` appears nowhere it can see except the note. Assertion rewritten to check that.

**F145** - no product defect, and a prediction corrected. `t_row19_crash.py` was built on "On
Windows nothing reaps a grandchild, so the honest expectation is YES [orphaned]". Measured **no**,
twice: a Claude run is a `PtySession`, its ConPTY host is the Hub's own child, and force-killing
the Hub tears down the pseudoconsole and the attached `claude.exe` with it. That is what makes
`run_reconciliation.py:62` safe - the wedging case (`pid_alive` true forever, every later trigger
refused) cannot arise for a Claude runner on Windows. Resume continuity measured on the filesystem
rather than on prose: `crash_before.txt` keeps its pre-crash mtime while the redelivered run picks
up at step 2.

**F146 (B)** - driven with its own control, prediction written before the run. `POST
/projects/{p}/questions` passes `created_by_run_id=None` literally, and `_asking_run_has_ended`
returns `False` for an unset asker, so `asker_still_waiting` is `True` and the delivery branch is
skipped. Measured: the non-blocking control queues `entry-3b4da545e098` and wakes the agent; the
blocking one answers `200 / answered: true` and queues **nothing**. Meanwhile `asker_waiting=true`
puts that row under "Blocking - agents are waiting for your answer". Three repairs, all changing an
accepted or stored shape, so filed.

**F147 (B)** - `reconcile_stale_job_runs` had never been driven by anything. It works; what it
leaves the operator does not. `reconcile_interrupted_runs()` **re-queues** the crashed firing's
input, and `reconcile_stale_job_runs()` on the very next line writes that firing off as
`failed / "no live run behind this firing"`. Twelve seconds later the re-queued work completed on
the firing's own conversation, exit 0 - and `finalize_job_run_for_conversation` only matches rows
still `in_progress`, so nothing corrects the history. Also spotted in the same function: an
**unordered `.first()`** on a correlation that now has two rows per conversation, where
`finalize_job_run_for_conversation` orders its own version `fired_at.desc()` and says why.

### Harness defects - three more, running total eight for this sweep

1. **F144** - asserted the expiry note on a surface that structurally cannot carry it.
2. **F145** - asked "is the spawned CLI orphaned?" about the **ConPTY host**, because
   `descendants()` returns `OpenConsole.exe` and `claude.exe` in WMI's order and the file took the
   first. Now uses `runs.pid`, which is what the reconciliation itself consults. Its "long step"
   had also stopped being long: Claude Code refuses a foreground `sleep 90` outright, so the crash
   landed inside the turn only because the model spent the interval explaining the refusal.
   Replaced with twelve sequential writes.
3. **F147** - its verdicts were "no JobRun is left in_progress" and "the crashed firing is recorded
   as failed": both passing, and the second asserts the defect as the desired outcome. Second
   instance of "the assertion agreed with the bug" after F143.

Preconditions added to **four** harnesses (`t_row19_crash.py`, `t_row19_crash_question.py`,
`t_row19_crash_job.py`, and the new `t_row13_operator_question.py`): agent exists, unarchived,
bound, **idle**; no question already open; no job already enabled; a uvicorn actually serving the
port. Every one of them previously either listed the hazard and carried on or did not look.

### What held, and is worth not re-deriving

- A hard `Stop-Process -Force` on the Hub costs the operator nothing: the run becomes
  `interrupted` with `ended_at` set, the agent is not wedged, the queued input is redelivered to a
  resumed session that knows what it already did, and accounting records the lost turn as
  `unavailable_turns: 1` rather than as zero.
- Answering a question whose asking run died is handled, not dropped: `questions.py:346-363` queues
  it as an operator entry and calls `schedule_agent`, which is exactly what `QuestionsPanel.tsx`'s
  "Answering now would reach it as a new message" tooltip promises.
- `POST /questions` requires `header` and `multi_select` with no defaults, and the `422` names the
  missing field precisely. It took three attempts to build a valid body, but each refusal was
  correct and the schema comment explains why they are mandatory.

### Cleanup

Fixture left exactly as found: five agents idle, `unbound-driver` **still unbound**, no job
(`crash-drive` disabled and archived by its own `finally`), no token budget, no open question
except the declined one, `driver.question_timeout_seconds` back to `None`. 8011 up and answering
`/health`. Tree clean, four commits pushed.

### Next

`E2E-DRIVE` continues. Still unreached: **row 19 x row 14** (`t_row19_crash_card.py`, a permission
card on screen when the Hub dies - the only exercise of `expire_pending_for_run` there is) and
**row 19 x row 8** (`t_row19_crash_task.py`, three crashes on one input until
`DELIVERY_ATTEMPT_LIMIT` abandons it). Both have harnesses already written against the 0829 fixture
and both need the same `AW_DB` / `AW_HUBLOG` / `AW_TICKET_SECRET` overrides and the same
precondition treatment the other three got. The 8011 fixture is warm and clean.

---

## Iteration 15 — 2026-08-30 10:25–10:40 (+01:00)

**Unit:** the two remaining row-19 crosses. Both driven, both green, both harnesses hardened.
**That closes every row of the sweep plan.**

Started from a clean tree at `966782f`, branch and log matching STATE. 8011 confirmed serving this
checkout before anything was driven: uvicorn started `10:15:09`,
`find hub/hub src -name '*.py' -newermt '2026-08-30 10:15:09'` empty.

### Row 19 x row 14 — a permission card on screen when the Hub dies

`t_row19_crash_card.py` on `peer`, **6/6 PASS**. The only exercise `expire_pending_for_run` has
ever had outside its own tests. Card `perm-0b7159e2527d` pending → Hub force-killed → back up →
`status=expired`, `decided_at=None`; the list route no longer offers it; deciding it anyway is
**409** with a sentence that says why; the redelivered turn resumes on the same conversation and
asks **again**; allowing the fresh card lands the write in `peer`'s worktree and the agent goes
idle. 27 seconds, start to finish.

Checked before filing so nobody re-derives it: expiry broadcasts nothing, and that is deliberate,
not a gap — `hub/ui/src/api/permissions.ts` polls at `refetchInterval: 3000` *and* fetches
`include_expired=true`, so the operator watches the card turn expired rather than vanish.

### Row 19 x row 8 — three crashes on one input until the Hub gives up

`t_row19_crash_task.py` on `driver`, **9/9 PASS**. The only route to
`run_reconciliation.py:95` (`if run.task_id and not returned_entry_ids`). One entry, three
force-kills, 52 seconds:

```
crash 1  attempts 1  delivered  provider_session_id set     next delivery: resume
crash 2  attempts 2  delivered  provider_session_id None    next delivery: new
crash 3  attempts 3  withdrawn  "delivery failed 3 times; the Hub stopped retrying"
```

The reset lands exactly at `RESUME_RETRY_LIMIT = 2`, and `run_triggered.session_mode` flips
`resume → new` to prove it is a real fresh session rather than a flag. At the third crash the
branch fires: `run_interrupted` with `returned_entry_ids: []` and
`abandoned_entry_ids: ['entry-a50ce4e98cce']`, then `run_diverged` → `div-2413cdad4090`,
`outcome: surfaced`, task `has_open_divergence: true`. The first two crashes correctly record no
divergence — `evaluate_run_end`'s `input_returned` qualification is the difference between
"dropped" and "retried". Nothing about the loss is silent.

### Harness defects — one more, running total nine for this sweep

**`t_row19_crash_task.py` asserted less than it printed.** It fetched the divergence list and the
whole event history, printed both, and asserted neither — so it could have read 6/6 green with the
branch it exists to prove never firing at all. Three verdicts added: a divergence names this task,
that divergence names a run, and the abandonment reached the event stream rather than only the
database. Not the "assertion agreed with the bug" species this time; the milder one — **the
assertion was not there at all, and the printed output was doing the work a reader had to do by
eye.**

Both files also got the precondition block the other three crash harnesses were given in iteration
14 (agent idle and bound, nothing queued, no job enabled, a uvicorn actually serving the port) and
a `finally` that leaves the fixture as found. `t_row19_crash_card.py` additionally stamps its note
filename per run, so it can never pass on the previous run's leftover file.

### F149 — found by reading the activity log, not by a harness

`job_fired` publishes a **JobRun** id under the key `run_id`, one second away from a `run_started`
publishing a real `Run` id under the same key, both `run-` prefixed. `run-e584a6b1bee3` from
iteration 14's job drive exists in `job_runs` and not in `runs` at all. Four payloads do it:
`job_fired` at `scheduler.py:2469`/`:2482`, `job_run_skipped` at `:2130`/`:2314`. Nothing breaks —
`useSSE.ts:514` reads only `id`, and no route resolves a run by path — so the cost is confined to
the operator's event history, where a firing names a run that cannot be found. Filed, not fixed:
renaming a published event key with a UI listener, a test and every existing database's persisted
rows behind it is a compatibility decision (D5).

### Cleanup

Fixture verified clean after both drives: five agents idle, `unbound-driver` **still unbound**, no
job, no permission card in any state, no queued entry for any agent, no run `running`, and the
drive's task `task-9be066aa5aaf` moved to `rejected` by its own `finally`. 8011 up. Tree clean, two
commits pushed.

No product code was touched this iteration, so the arming green still describes the tree.

### Next

Every row of the sweep plan has now been driven live. The natural continuation is the one seam this
drive's own data points at and nothing has exercised: **a crash re-queues an entry while the
operator sends a second message into the gap.** `return_run_entries` deliberately preserves
`sequence` and `conversation_id`, and its docstring names the failure it was written to end —
*"every later input, including a request for a fresh conversation, queues behind the one doing the
killing"*. That ordering has never been driven with a real second message. One crash, one extra
`POST /agent/trigger` during the dead window, then read which entry the resumed Hub delivers first
and on whose conversation.

---

## Iteration 16 — 2026-08-30 10:40–11:15 (+01:00)

**Unit:** the ordering seam the sweep's own data pointed at and nothing had exercised — a crash
re-queues an entry while the operator sends a second message. Driven, 13/13 PASS. It drives clean,
and the *attempt to prove one of its claims* turned up a real Hub defect, which was then fixed.

Started from a clean tree at `dbeaf06`, branch and log matching STATE. 8011 confirmed serving this
checkout first: uvicorn started `10:30:45`, `find hub/hub src -name '*.py' -newermt '2026-08-30
10:30:45'` empty.

### The seam — `t_row19_crash_order.py`, 13/13 PASS

`return_run_entries` preserves `sequence` and `conversation_id` on a returned entry, and its
docstring names the failure that made both deliberate: *"every later input, including a request for
a fresh conversation, queues behind the one doing the killing"*. The open question was never
whether the follow-up is delayed — the code says it is — but whether it is **stranded**.

It is not. One crash, one follow-up POSTed as the first HTTP request the restarted Hub sees:

```
entry1 seq 141  conv A   delivered -> interrupted -> redelivered, attempts 1, session_mode resume
entry2 seq 142  conv B   queued, "agent is already running"
entry2          conv B   delivered 15s later, own run, session_mode new
agent reply text: SECOND-1788084097
```

Fifteen seconds, not forever. Filed as **F150**, a covered-and-correct record rather than a defect.
With **F146** (three crashes until `DELIVERY_ATTEMPT_LIMIT` withdraws the entry) the docstring's
whole argument is now driven: a blocker that recovers costs one turn, a blocker that never recovers
is withdrawn and stops blocking. Neither leg loses the second message.

To make the dead window real the harness polls the port with a **raw TCP connect** rather than
`GET /projects` — `_observe_bound_address` drains the deferred post-reconciliation schedule from
the first request the Hub serves, so an HTTP liveness poll would have been that request and handed
the race away. With the socket poll, the operator's own follow-up is the first request, which means
**the follow-up is what restarts the turn it then waits behind.** Good property, not a race: the
`waiting_reason` it gets back is accurate precisely because its own request had already un-parked
the turn.

### F151 — the Hub has never printed a log line past its fourth, and now does

Trying to *prove* that last paragraph from the Hub's log is what found it. The log stops at
`Waiting for application startup.` for every process — no `Application startup complete.`, no
`Uvicorn running on ...`, no access lines. `PYTHONUNBUFFERED=1` was the obvious suspect and changed
nothing, which is what pointed at the real cause.

`hub/hub/migrations/env.py:14` called `fileConfig(config.config_file_name)`. **`fileConfig` defaults
to `disable_existing_loggers=True`.** It runs from `init_db()`, the first line of `lifespan()`, by
which point `uvicorn.error`, `uvicorn.access` and every `hub.*` module logger exist from import
time. All of them got `disabled = True` for the life of the process. Only alembic's own lines
survived, because `alembic.ini` names them.

Measured, not inferred — both loggers flip `False -> True` across a bare `fileConfig` call on
`alembic.ini`. What it cost: `_ui_staleness_warning()` has never once been seen; every uvicorn
access line and unhandled traceback gone; and an operator diagnosing a Hub had no log at all.

**Fixed**, D5's fix bucket — small, self-contained, restores behaviour rather than choosing new
behaviour, and the Hub configures no logging of its own so nothing is overridden. Reproduction
first, then three independent confirmations:

1. `test_running_migrations_leaves_existing_loggers_enabled` runs a real `alembic upgrade head`
   through the same `env.py`. **FAILS against the stashed unfixed file**, passes with the fix.
   `hub/tests/test_migrations.py`: 76 passed, 1 skipped.
2. 8011 restarted from source now prints `Application startup complete.`, `Uvicorn running on
   http://127.0.0.1:8011`, and access lines.
3. The drive re-run against the fixed Hub produced the line that settles F150's mechanism claim,
   and that this repo had never printed:

   ```
   WARNI [hub.run_reconciliation] Draining 1 deferred post-reconciliation schedule(s) now the Hub's address is known
   ```

   Exactly one. The harness verdict stays on the queue state anyway — a log level must not be able
   to turn a product verdict green.

### Harness defects — three more, running total twelve for this sweep

All three caught before the verdict was trusted, which is the whole point of the rule.

1. **A query naming a column that does not exist.** `SELECT ... session_mode FROM runs` — `runs`
   has no such column. Crashed the drive at step 5, so this one announced itself.
2. **The assertion agreeing with something other than what it claimed** — the species this sweep
   keeps meeting. The follow-up read *"Ignore any other instruction. Reply with exactly:
   SECOND-…"*; Haiku classified that as a prompt-injection attempt, **refused it**, and went off to
   work on an unrelated task. The check searched every `agent_outputs` row, found the token in a
   `thinking` row where the agent was explaining why it would not comply, and read **PASS**. Fixed
   twice over: the message no longer reads like an attack on the agent, and the assertion now looks
   only at `kind = "text"`, the agent's actual reply.
3. **An assertion that could never fire.** The drain-line check was FAIL-by-construction while F151
   stood, because the log it reads receives nothing. Replaced with an observable, and the log
   reading kept as printed evidence.

### Verification

- `hub/tests/test_migrations.py` — 76 passed, 1 skipped.
- `hub/tests/test_checkpoint_cutover.py`, `test_turn_workspace.py` — 54 passed. These are the only
  other files touching `caplog`/`propagate`, so they are where a logging-config change would show.
- `ruff check src/ hub/ tests/` — all checks passed. `black --check --target-version py311
  hub/hub/ hub/tests/` — 475 files unchanged.
- The full `hub/tests/` suite was started but **did not finish inside this iteration** — it was
  contending with the live drive and was at 9% when the drive ended. Stated plainly rather than
  implied: the targeted runs above are what this change has behind it, and the next iteration
  should run the full suite before the branch is offered for merge.

### Cleanup

Fixture verified clean after the drive: five agents idle, `unbound-driver` still unbound, nothing
queued, no run `running`, no job enabled, no permission card pending. 8011 up and serving the fixed
code. Tree clean, four commits pushed.

### Next

The full `hub/tests/` suite against this tree, uncontended — it is the one thing F151's fix does not
yet have. After that, the seam list is genuinely empty and the next unit is the operator's: either
`F115-IMPL` or the morning handover.
