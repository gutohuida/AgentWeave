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

## Iteration 9 — F115-R2 — 2026-08-30T06:50:15+01:00 → 08:05+01:00

Branch verified against `STATE.json` before anything: `autonomous/2026-08-30-decided-work-and-drive`
at `23467c8`, clean, matching `origin`. Heartbeat was 06:07, 43 minutes stale, so the branch was
free. Claimed with a heartbeat commit, then straight into the round.

The unit was **round 2 of the F115 spec loop** — an *independent* re-derivation of
`openspec/changes/a-write-outside-the-workspace-is-recorded/` against the code, not a re-read of
round 1's reasoning. The clock was checked at the start (06:50, stamped from PowerShell) rather than
estimated: the 08:00 rule permits starting a round before 08:00 and forbids leaving a half-written
proposal, and rounds in this loop have run 20–35 minutes. This one ran to 08:05, which is over — the
rule was honoured by finishing rather than by abandoning, since a reverted round would have thrown
away six corrections.

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

### The next unit is the drive, not F115-R3

The 08:00 rule is now past and it is unconditional: **`E2E-DRIVE`**, full-surface sweep, own Hub on
8011, Haiku for every agent turn, D5 for fix-versus-file, no job left enabled. F115-R3 stays queued
behind it and is the operator's to schedule.

R3, when it runs, has a sharpened target rather than a blank one: the D9 narrowing is a judgement
round 2 made, not a derivation — a record the operator never sees is not the record F115 asked for,
but that is an argument, and R3 should attack it. The other two open items are whether anything
constructs a `tool_use` `RunEvent` without going through `tool_use_event` (which would falsify D2's
one-population-site claim), and whether the extractor really returns on the tool name before
touching the input, since it now runs for every tool call of every run.
