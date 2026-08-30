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
