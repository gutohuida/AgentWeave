# Autonomous run — stress-test remediation

Branch `autonomous/2026-08-24-stress-test-remediation`, cut from
`fix/2026-08-23-design-audit-remediation` at `969b7b9`. The queue is the mechanical half of
`scripts/drive/FINDINGS.md`, the findings from the 2026-08-23 stress-test drive. The two
architectural changes from that drive are specified, validated, and deliberately left for an
attended session.

---

## Iteration 1 — Q1, backend papercuts (F4, F6/F18, F7, F8, F16, S2)

Started 2026-08-23 23:59 local. Branch and `git log` matched STATE.json: `88a6262` on
`autonomous/2026-08-24-stress-test-remediation`, clean tree, `969b7b9` three commits back as
`parent_sha` records. No reconciliation needed. STATE.json carried no `last_heartbeat` at all —
iteration 0 had never run — so this iteration wrote the first one.

### What landed

**F4 — a fresh project does not adopt the main branch it can already see.**
`POST /projects/open` now calls `_adopt_detected_main_branch`, which takes what
`task_integration.detect_main_branch` reports and writes it to `project.main_branch`, then drains
approved work that skipped for want of a branch through the existing
`_integrate_what_was_waiting_for_a_branch`. Three constraints in the implementation, each of which
is the interesting part:

- **Only into a null.** Re-opening is the ordinary way a project is reached after the first time,
  and a branch the operator chose is a statement. Overwriting it with whatever `detect_main_branch`
  currently prefers would be worse than the bug.
- **Never fatal.** A repository the Hub cannot read leaves the project opening with no branch,
  which is exactly the status quo. Failing the open instead would turn a git problem into an
  unopenable project.
- **The suggestion route keeps existing.** It is still a suggestion and still changes nothing; its
  docstring is updated, because it used to be the *only* way `main_branch` ever became non-null and
  that sentence is now false.

One thing the finding's wording gets slightly wrong and which is worth recording: `POST
/projects/open` answers with `ProjectSummary`, and `ProjectSummary` has never carried `main_branch`
at all. The null the drive observed was read through `GET /projects/{id}/settings` and the
suggestion route's `chosen`. The stored value was the defect; the response shape was never part of
it. The tests assert on the stored value accordingly. Whether `ProjectSummary` *should* carry it is
a separate question and was not in scope.

**F8 — two refusals, two standards of helpfulness.** `EvidenceRefusedError` gained an optional
`http_status`, defaulting to `None` meaning "whatever the route would have sent". The
`unknown_decision` refusal sets it to 422 and now names the permitted values the way
`model_catalog.validate_overrides` names `permission_mode`'s four. The two decision routes read
`exc.http_status or 403`, so the two refusals that genuinely are about authority — no grant, and an
agent deciding about its own work — still answer 403. A test pins that, because flattening them
while fixing this would have been an easy and invisible regression.

**F7 — duplicate evidence for one requirement is accepted without comment.** New `duplicate_of()`,
keyed on requirement + task + footprint commit, refusing with `duplicate_evidence` and naming the
existing piece's id. Three implementation notes:

- `record()` now reads the footprint **before** creating the row, because the commit is half the
  key. `capture_footprint` takes an optional `taken=` so the same read serves both and the turn
  does not spend two sets of git calls learning the same answer.
- **Silent where either half of the key is unknown.** A project with no repository has no commit; a
  piece of evidence naming no task has nothing to be a second copy of. Guessing in either case
  would refuse a *first* piece of evidence, which is much worse than accepting a second. This also
  keeps the blast radius small: the suite's default workspace fixture resolves to a non-git
  `tmp_path`, so every existing evidence test is untouched by construction.
- **A rejected piece never matches.** A rejection is a judgement that the demonstration was
  inadequate, and re-recording at the same commit with a better account of it is the honest
  response rather than a duplicate of one.

**F16 — `loop_id` accepted on task creation, never echoed.** One field on `TaskResponse`.
`model_validate(task)` with `from_attributes` picks it up from the column that already existed.

**S2 — `short_id()` widened 8 → 12 hex.** `uuid.uuid4().hex[:12]`, not `str(uuid.uuid4())[:12]` —
the string form has a hyphen at index 8, so slicing it would have cost four characters of entropy
and put a separator inside a segment already joined to its prefix by one. `test_short_id.py` pins
that specifically. No migration: every id column is already `String(64)` and a segment is only ever
generated, never parsed, so the two widths coexist. The stale `"{prefix}-{8hex}"` comment on
`_TASK_ID_RE` is corrected, and the one test asserting `len("task-") + 8` now asserts 12.

**F6/F18 — a task being actively worked shows no assignee.** `bind_run_to_task` sets
`task.assignee = run.agent`, but only where the task holds none. Written there rather than in the
trigger route because it is the one place both paths — the loop's claim and a direct `task_id`
trigger — pass through. A task that binds without starting (gated on a prerequisite) still gets the
assignee: it is being worked on by somebody, and the card saying who is what distinguishes it from
an abandoned one.

### Verification

Every new test was written against the defect, and the F4 set was checked to actually fail with the
fix disabled (1 failed / 2 passed — the two guard tests are meant to pass either way, which is why
only one flipped).

### Continuation

_(filled in below as the run proceeds)_

---

## Iteration 2 — verifying and committing Q1

Started 2026-08-24 01:24 local. **Iteration 1 died before it verified or committed anything.**
Branch and `git log` matched STATE.json (`88a6262`), but the tree carried all of Q1's work
uncommitted: eight modified files, three new test files, and a log entry describing the change as
if it had landed. `last_heartbeat` was 00:56, twenty-eight minutes stale. Nothing was lost — the
edits were all on disk and coherent — but the "### Verification" section iteration 1 wrote is
**false as written**: it claims the F4 set was checked against the defect, which may well have
happened, but the suite it implies was run had not been. This iteration ran it, and it was not
green.

### The two failures the previous iteration never saw

`py -3.11 -m pytest hub/tests/ -q` → **2 failed, 2777 passed**. Both were pre-existing tests
pinning exactly the behaviour Q1 was scoped to change, and both were corrected rather than worked
around:

**`test_agent_evidence_plane.py::test_an_unknown_decision_is_refused`** asserted 403. The queue
says in as many words that the route must return 422, so the assertion is what was wrong. It now
expects 422 and additionally asserts the message names both permitted values, which is the other
half of F8 and was not pinned anywhere on the agent route.

**`test_run_divergence.py::test_escalation_to_an_agent_that_does_not_exist_surfaces`** asserted
`task.assignee is None` after escalation into a name no agent answers to. That assertion held only
because `bind_run_to_task` named nobody — which is the F6/F18 defect. The test's actual claim is
that the task did not move to the ghost, and `is None` was a proxy for it that F6/F18 invalidates.
It now asserts `== "worker"`: still with the agent that ran it, never with the ghost. Note the
neighbouring `test_escalation_reassigns_the_task_and_runs_the_stronger_agent` passes
`assignee="worker"` explicitly to `_bound_run` — that argument exists *because* binding used not to
set one, and is now redundant there. Left alone; removing it is unrelated churn.

Re-run clean: **2779 passed, 84 skipped, 1 xpassed, 0 failed** (13m42s). `ruff check` and
`black --check` over `hub/hub/` and `hub/tests/` both clean.

### Driving the real routes, and what that caught

A passing suite is not proof of behaviour, so F4, F16 and S2 were also driven over real HTTP: a
throwaway harness at `.claude/autonomous/scratch/drive_q1.py` (gitignored — it is a drive, not a
test) boots the actual FastAPI app on a temp SQLite database and reads the JSON a caller gets.
Eight checks, all passing. The trial Hub on 8010 was **not** running and was deliberately not
started; booting one from this checkout is the thing CLAUDE.md forbids.

Two things came out of it that the suite could not have told me:

- **My first repository used `trunk` as its branch and F4 "failed".** It was not a defect —
  `detect_main_branch` walks `MAIN_BRANCH_NAMES`, which is `("main", "master")` and nothing else.
  Worth recording because the adoption inherits that limitation exactly: a project on `develop` or
  `trunk` still opens with `main_branch` null and still needs the operator. F4 is fixed for the two
  names the Hub already knew; it did not widen what the Hub knows, and should not have.
- **The first F8 check passed vacuously.** It posted to
  `/api/v1/projects/{id}/spec/evidence/…/decision` and got 405, because the real path carries a
  second `/project/` segment (`/api/v1/projects/{project_id}/project/spec/evidence/…`). Asserting
  `status_code != 403` against a 405 is a green light for nothing. Removed rather than repaired:
  both decision routes are already driven over HTTP by their own tests, and a third copy of the
  document/requirement/evidence setup would have bought no coverage. A comment in the harness says
  so, because a missing check looks like an oversight and a stated one does not.

Also confirmed by reading rather than assuming: `_task_response` builds via
`TaskResponse.model_validate(task)`, so F16's one added field is genuinely populated from the
column and not silently dropped — which the drive then showed on a live 201.

### Committed

`3b4efd6`, one commit for the whole of Q1, naming all six finding ids.

### Continuation

Q1 is closed. Next is **Q2** — scheduler honesty: F11 (`run_count` incremented above the skip
branches, so it counts considerations not firings), F13 (`PATCH {enabled:true}` on a loop with an
`ending_state` must be refused rather than silently undone a minute later), and F1's backend half
(refuse a cron restricting both day-of-month and day-of-week, which APScheduler ANDs and croniter
ORs). Q3 and Q4 untouched.

---

## Iteration 3 — Q2, scheduler honesty (F11, F13, F1's backend half)

Started 2026-08-24 01:59 local. Branch and `git log` matched STATE.json exactly: `862315a` on
`autonomous/2026-08-24-stress-test-remediation`, clean tree, Q1's `3b4efd6` two commits back. No
reconciliation needed. The previous iteration's closing heartbeat release worked as designed — this
firing picked the work up rather than standing down.

### F11 — `run_count` counted considerations, not runs

`_do_fire_job` stamped `job.last_run` and incremented `job.run_count` in its first four lines,
above every skip branch. Every one of those branches returns, so both fields described "the
scheduler looked at this job". The drive measured `run_count` 9 against 4 firings that actually
spawned an agent, with `last_run` pointing at a skip.

Both statements moved down to sit beside `run.status = "in_progress"` — the line the file's own
existing comment already identifies as the boundary between "considered" and "worked", because
every early return above it overwrites `fired` with `skipped`. Nothing else was needed: the
boundary was already named, the counters were just on the wrong side of it.

**`next_run` deliberately stayed at the top.** The schedule advances whether or not the firing did
anything, and a `next_run` left in the past would be its own lie — a card reading "Next: 4 hours
ago". That asymmetry is the one judgement in this fix, and it is now asserted rather than implied:
the F11 test checks `run_count == 0`, `last_run is None` and `next_run is not None` after the same
three skips.

Two consumers were checked before moving anything. `jobs.py`'s response passes both fields through
untouched. `tasks.py:484` gates loop-queue extension on `job.run_count > 0` — "this loop has
already fired at least once", D10's definition window. That reading gets *more* correct, not less:
a loop that has only ever skipped has not fired, so its creator's window is genuinely still open.
Worth flagging to the operator as a semantic side effect rather than a bug.

A firing that queues an entry and then fails to start a turn still counts. The entry is in the
queue and the job did fire; only the turn did not begin, and `JobRun.status` already says `failed`
for that case. Stated in a comment at the increment.

### F13 — re-enabling a finished loop was accepted and then silently undone

`PATCH /jobs/{id} {"enabled": true}` on a loop carrying an `ending_state` returned 200, left
`enabled: true` next to `stopped_at` and `stop_reason` for one minute, then fired, re-stopped, and
set `enabled` back to false. Now refused, before anything is mutated, with a machine-readable
detail: `code: "loop_ended"`, plus `ending_state`, `stop_reason`, `stopped_at` and the loop id.

**Two decisions worth recording.**

*The status code is 409, not 400 or 403.* This is a conflict with the resource's current state,
which is precisely what 409 means, and Q1 has already shown what a wrong code costs — F8 was a 403
that told an agent it lacked permission when it had sent a malformed enum. A caller reading 409
learns "not in this state", which is true and actionable.

*The message says "create a new loop", not "give this loop work" — which is what the queue item's
own wording suggested.* That wording could not be honoured truthfully. D12 (`tasks.py`'s
`_authorize_loop_task_creation`) closes an ended loop's queue to **every** caller, the operator
included: "It will not be revived — create a new loop and pass this task as one of its
`initial_tasks`". Telling the operator to feed a loop that refuses to be fed would have been a
second wrong answer on the same screen. The refusal is deliberately worded to match D12's, and a
comment at the check says why.

The check turns on `ending_state`, never on `enabled`. D6 rejected a third "paused" state, so a
loop an operator disabled by hand carries `ending_state`, `stop_reason` and `stopped_at` all NULL
and resumes exactly as before. There is a test whose entire job is to fail if the F13 fix ever
takes the pause button with it, and another for a plain job with no `Loop` row at all.

### F1 (backend half) — a cron restricting both day fields can no longer be stored

The premise is now **asserted, not assumed**. `test_the_two_cron_readers_this_repository_holds_
really_do_disagree` runs croniter and APScheduler side by side on `0 0 15 * 5` from a fixed start
and asserts the answers are more than 200 days apart. Measured here: they are. If a dependency bump
ever makes them agree, that test fails and the refusal becomes removable — which is the point of
writing it down as a test rather than as a paragraph.

`scheduler.cron_day_ambiguity_reason(cron)` returns a sentence or `None`. `jobs.py` calls it at
both write sites — create, and update before croniter is even reached, so the rule does not lapse
on an installation without croniter, where the `else` branch still stores the expression. `AIJob(`
has exactly one construction site in the whole Hub, so those two routes are the complete boundary.

**The detector is deliberately the same grammar as `hub/ui/src/lib/cron.ts`'s `parseField`** —
lists, ranges, steps, three-letter aliases — and deliberately no more. `L`, `W`, `#`, `?`, a
wrapping range like `22-2`: all return `None`, which means *undecided*, and undecided never
refuses. croniter and APScheduler stay the authorities on validity; this only ever adds a refusal,
and a validator that guessed at an extension it does not implement would reject schedules that
work. Both halves of that are tested — five ambiguous expressions refused, nine legal ones
accepted, five unreadable ones declined without judgement.

The two "legal" cases most worth having: `0 9 15 * 0-6` and `0 9 15 * 1-7`. A day-of-week that
names all seven days restricts nothing, and `1-7` folds 7 back onto Sunday, so it is seven days and
not eight. A naive `field != "*"` check would have refused both.

**This makes Q3's UI half smaller than it looks.** The backend predicate is exactly
`isAmbiguousDayPair`, so `describeCron` and the new refusal already agree by construction. What Q3
still has to do is route `nextRuns` — the JobForm preview and the JobCard "Next:" — through the
same guard, so the two numeric answers stop being rendered for a shape that can no longer exist.

### Verification

`py -3.11 -m pytest hub/tests/ -q` on the frozen tree: **2814 passed, 84 skipped, 1 xpassed, 0 failed** (15m55s). The 35 new tests are the whole delta from Q1's 2779 — no existing test pinned the old behaviour anywhere, which is the thing the Q1 continuation note warned to check for and the reason the run was repeated after the tree was frozen rather than trusted mid-edit. `uvx ruff check` and
`uvx black --check` over `hub/hub/` and `hub/tests/`: clean.

**And driven over real HTTP**, because a passing suite is not proof of behaviour. A throwaway
harness at `.claude/autonomous/scratch/drive_q2.py` (gitignored, same shape as Q1's) boots the
actual FastAPI app on a temp SQLite database: **19 checks, all passing.** Three things it gave that
the suite could not:

- **F13's ending was produced by the scheduler, not hand-written.** The test fixture sets
  `ending_state` directly; the drive creates a loop with a `stop_at` already in the past, fires it
  through `_fire_job_internal`, and lets the stop branch end it — then re-enables over HTTP and
  reads the 409. That is the measured sequence, not a reconstruction of it.
- **The first `POST /jobs/{id}/run` returned 503.** `run_job` reaches the module singleton
  `get_scheduler()`, not whatever `JobScheduler()` the harness happens to hold, so the "a real
  firing counts once" half of F11 was passing vacuously in a branch that never ran. Publishing the
  instance as `scheduler_module._scheduler_instance` fixed it and the check went green with
  `run_count == 1`. Left as a comment in the harness: this is the second time in two iterations
  that a drive check has "passed" by not executing.
- **The refusal reads correctly on the wire.** `hub/ui/src/api/client.ts` already extracts
  `.message` from an object `detail`, so the 409's structured body renders as prose in the UI
  without a Q3 change.

One wording change came out of reading the output rather than the code: the message first said
"This loop finished", which is wrong for the `stopped` ending — a loop killed by its `stop_at` did
not finish anything. It now says "has ended", which covers both.

**Each new test was watched fail without its fix**, not assumed to. Reverting F11's two
statements back to the top of `_do_fire_job` turns the assertions into `assert 3 == 0` and
`assert 1 == 0`; stubbing out the two `jobs.py` checks turns the six F1/F13 refusal tests into
`201 == 400`, `200 == 400` and `200 == 409`. Both reverts were restored and the suite re-run
green before committing.

### Noticed, not done — an agent reads a structured refusal as a Python dict

`mcp_server._readable_detail` reduces a list detail (Pydantic's shape) to a sentence, but falls
through to `str(detail)` for a dict one — so an agent calling `toggle_job` on an ended loop gets
`{'message': 'This loop has ended ...', 'code': 'loop_ended', ...}` rather than the sentence.
That is not new and not F13's doing: `tasks.py`'s D12 refusal has the same shape and the same
outcome, and `hub/ui/src/api/client.ts` already prefers `detail.message` on the operator side. A
three-line branch in `_readable_detail` would make both legible to an agent. Left out because it
is outside Q2's scope and `mcp_server.py` carries its own stdlib-only contract; recorded here so
it is not lost.

### Committed

One commit for the whole of Q2, naming F11, F13 and F1.

### Continuation

Q2 is closed. Next is **Q3** — the dashboard-truth item, all under `hub/ui/src` and deliberately
one item so the committed bundle is rebuilt exactly once in Q4: F17 (every Hub-managed agent reads
"No activity yet" forever because `last_seen` only comes from a heartbeat row), F19 (prerequisites
are returned by `GET /tasks` and rendered nowhere), F9 (an inline note on approve saying which
commit goes into which branch), F14 ("waiting on you" on a task blocked on an unanswered
`ask_user`, without changing its status), F2 ("server time" → "UTC"), and F1's UI half as described
above. Read `design/IDENTITY.md` before touching any of it. Q4 untouched.

---

## Iteration 4 — Q3, dashboard truth (F17, F19, F9, F14, F2, F1's UI half)

**This entry covers four firings, not one, and says which did what**, because three of them left no
record of their own and inheriting their claims silently would be exactly the kind of dishonesty
this queue item is about.

| Firing | What happened |
|---|---|
| ~04:00–05:09 | Took Q3, implemented all six findings, drove them over HTTP, then died before the full backend suite and before committing. Left 16 modified files, 4 new ones, a drafted commit message and a drafted log entry in `scratch/` — and no log entry, no commit. |
| 05:34–05:55 | Re-verified parts of the tree, refined the drafted entry, died on `API Error: 529 Overloaded`. |
| 06:09–06:12 | Died on 529 before doing anything. |
| 06:14– (this one) | Verified the inherited tree independently, end to end, and committed it. |

`git log` matched STATE.json exactly — `ec633a3`, with Q2's `d706187` one commit back — so nothing
was lost; only the working tree was ahead of the record.

**Reconciled by adopting the work rather than discarding it.** A complete, coherent implementation
is not made wrong by a missing log entry, and re-deriving it would have cost the last usable hour
before 08:00. The adoption was conditional on the work surviving verification *run in this firing*,
which is the section below. Every number there was measured here between 06:14 and 07:00; nothing
is inherited.

### What the six findings became

**F17** — `last_seen` came from `AgentHeartbeat` rows and nothing else, and since the watchdog was
deleted the Hub spawns every agent itself and posts no heartbeats. So the field was permanently
NULL for every managed agent, and the rail read "No activity yet" beside an agent that had just
done nine runs. New `hub/hub/agent_activity.py` derives it in bulk from three sources — `runs`
(`started_at`, `ended_at`, `last_heartbeat_at`), `agent_outputs.timestamp`, and heartbeats, still —
and `agents.py` and `projects.py` both call it, so the rail and the roster cannot disagree about
one agent. Deliberately *not* wired into `heartbeat_is_stale`: "when did this agent last do
something" and "is it healthy right now" are different questions, and a two-hour-old run answers
only the first.

**F6/F18's remaining half** — the task board was the third surface still reading heartbeats alone,
so its cards reported `assignee_status: "idle"` about the agent the rail beside them called
`running`. `_attach_assignee_liveness` copies `agents.py`'s precedence verbatim, stalled case
included.

**F19** — a gated task rendered as an ordinary pending card while the dependency gate silently
refused every attempt to move it. `TaskCard` now carries a badge — neutral for an ordinary gate,
red only for `gated_on_rejected` — with the blocking prerequisites and their statuses in the title.
The distinction is the point: waiting on unapproved work is the system behaving correctly, whereas
a *rejected* prerequisite can never clear on its own.

**F9** — approving cherry-picks the accepted evidence's commit into the project's main branch, and
nothing said so on the successful path. A read-only `GET /tasks/{id}/integration-preview` answers
the same question the merge will ask, from the same source, and the drawer states it beside the
approve control as an inline note — not a dialog, because approval is the designed behaviour and a
confirmation step teaches the operator to dismiss it.

**F14** — a run waiting on `ask_user` does not park its task until it *ends*, so for the whole of
the wait the board said `in_progress` with no reason. `awaiting_answer_reason` is computed per
request, never stored, and the card draws it exactly like a parked one. The status is deliberately
untouched.

**F2** — "server time" → "UTC" on both jobs surfaces. The value was always right; only the word was
wrong, by an hour, every summer, on the operator's own machine.

**F1's UI half** — `cronDayAmbiguity` exports the predicate `describeCron` and `nextRuns` already
declined on, so the form says why the Hub will refuse the expression instead of rendering nothing,
and the card stops dating a pre-refusal job with croniter's OR answer for a schedule APScheduler
ANDs.

### Verification, all of it run in this firing

- `npx tsc --noEmit`: clean.
- `npm run lint`: clean at `--max-warnings 0`.
- `npx vitest run`: **1374 passed, 138 files, 0 failed** (42s).
- `uvx ruff@0.15.22 check src/ hub/ tests/`: clean. `uvx black@26.5.1 --check`: 448 files unchanged.
- `npx openspec validate --changes --strict`: 4 passed.
- **Full backend suite**, `py -3.11 -m pytest hub/tests/ -q`: **2838 passed, 84 skipped, 1 xpassed, 0 failed** (14m44s). `test_dashboard_truth.py` contributes 23 of those, and nothing that existed before regressed.
- **Driven over real HTTP**, because a passing suite is not proof of behaviour:
  `.claude/autonomous/scratch/drive_q3.py` (gitignored) boots the actual FastAPI app on a temp
  SQLite database and reads the JSON a real caller gets — **17 checks, 0 failed**, reproduced here
  rather than taken from the dead firing's transcript. It covers three things the unit tests cannot:
  `last_seen` agreeing across the two routes that render it, `awaiting_answer_reason` produced by
  really calling the questions API mid-run, and the F9 preview walked through all three operator
  states (no evidence, evidence awaiting review, evidence accepted).

**And falsified rather than trusted.** The six changed backend source files were stashed — leaving
`agent_activity.py` on disk but unwired, and every new test in place — and the two backend suites
run against the hole: **17 failed, 37 passed.** The failures cover all four findings the backend
half carries (F17 on both routes, F14, F9, F6/F18) and include
`test_project_summary_reports_running_for_a_run_with_no_heartbeat`, the pre-existing test whose
`last_seen is None` assertion this work moved. Stash popped, re-run, **54 passed**.

The UI half was falsified the same way by the firing that wrote it — the seven changed sources
reverted to `HEAD` with the four test files left in place, 11 failed / 15 passed, restored, 40
passed. That one measurement is inherited rather than re-run here, and it is the only one in this
entry that is.

### Read, not assumed

Two claims in the inherited comments were checked against the code they describe rather than taken
at face value:

- `_attach_assignee_liveness` says its precedence is "copied from `agents.py`, deliberately and
  exactly". It is: `agents.py` sets `effective_status` from the heartbeat and then overwrites it
  with `"running", None` for any agent holding a live `Run`; the new code does the same two things
  in the same order.
- `nextRuns` and `describeCron` really do already decline an ambiguous day pair, so
  `cronDayAmbiguity` is that same predicate exported, not a second copy of it.

### Noticed, not done

**F19's `dependents` half is not implemented.** The queue item says `TaskCard` "renders neither
prerequisites nor dependents"; only the prerequisite side is marked. That is the side that *gates* —
a task with dependents is not itself blocked by them — so the card says what stops this task from
starting and not what this task is stopping. The Dependencies board already draws those edges.
Recorded so the gap is a decision and not an oversight.

**A stalled agent mid-run now reads `running` on a task card**, where it previously read `stalled`.
That is the price of the board and the rail describing one agent the same way, it is tested
(`test_a_live_run_outranks_a_stalled_heartbeat_here_exactly_as_it_does_on_the_roster`), and it is
flagged here rather than left invisible.

### Committed

One commit for the whole of Q3, naming F17, F19, F9, F14, F2 and F1. **No bundle rebuild** — that
is Q4's, deliberately, so `hub/hub/static/ui` is written exactly once. The committed bundle is
therefore stale as of this commit and is *expected* to be.

### Continuation

Q3 is closed. Next is **Q4** — rebuild the bundle and verify everything. Order matters and cost an
earlier session a cycle: **commit the source first, then `cd hub/ui && npm run build`, then
`py -3.11 scripts/refresh_ui_bundle.py`, then commit the stamp**, because git's CRLF normalisation
on commit invalidates a stamp taken before it and `/health` then reports `ui_stale` on a clean tree.
Then the full sweep (backend suite, vitest, ruff, black, openspec validate), a read of the whole
diff since `ec633a3` for accidental legacy revival and debris, and the morning summary at the
`log_file` path.

**One practical note for whoever picks up Q4:** two firings in a row died on `API Error: 529
Overloaded` mid-iteration, at 05:55 and 06:12. Nothing was lost either time, because the tree was
on disk — but it is why Q3 took four firings to close, and it is worth expecting again.

---

## Iteration 5 — Q4, the bundle, the sweep, and the morning summary

The queue is empty. This entry is the one written for you to read first, so it says what landed per
finding, what did not, and what surprised us — and it is the whole run's account, not just this
firing's.

### The bundle, in the order that has now cost three sessions a cycle

`hub/ui/src` changed in `7fcd172` (Q3) with the committed artefact deliberately left stale, so it is
written exactly once. This firing did `npm run build` (clean, `tsc` inside it clean, 14.4s) then
`py -3.11 scripts/refresh_ui_bundle.py`, and committed `hub/hub/static/ui` as `9eb37c8`. One JS
chunk moved (`index-D89EB_De.js` → `index-BEeynRU2.js`); the CSS hash did not change.

**And the ordering warning inherited from two earlier sessions turns out to be aimed at the wrong
field.** Re-running the refresh script after that commit does dirty the stamp again — but the diff
is only `src_commit` and `built_at`. `src_fingerprint` is byte-identical, and `src_fingerprint` is
the *only* field `_compute_ui_staleness_warning` reads (`hub/hub/main.py:163-167`). So committing
the second stamp would achieve nothing except making `src_commit` stale-by-one again on the next
commit, forever. It was reverted, and the check was run rather than assumed:
`_compute_ui_staleness_warning(UI_DIST, UI_SRC)` returns `None` on the committed tree, and
`GET /health` on the real app answers `{"status":"ok"}` with no `ui_stale` key. The
`AW_CHECK_UI_BUNDLE=1` gate passes too (11 passed).

Worth correcting in the handoff vocabulary: what invalidates a stamp is a *source* change, not
git's CRLF normalisation. The advice "commit, then re-stamp" is harmless but unnecessary, and it is
why an earlier session went round twice looking for a staleness that was already gone.

### What landed, per finding

F-numbers are `scripts/drive/FINDINGS.md`; **S2 is from `scripts/drive/SURVEY.md`** — a scale risk read out of the code rather than hit during the drive, which is why it has a different prefix and no reproduction.

| Id | Landed in | What changed |
|---|---|---|
| F4 | `3b4efd6` | `POST /projects/open` adopts the branch `detect_main_branch` already found, into a null only. A git project is no longer degraded until someone visits settings. |
| F6/F18 | `3b4efd6` | `bind_run_to_task` sets `task.assignee`, so a direct trigger names who is working, as the loop's claim already did. |
| F7 | `3b4efd6` | A second piece of evidence for the same requirement + task + commit is refused, naming the piece that already holds it. `digest` was never this check. |
| F8 | `3b4efd6` | A malformed evidence decision is 422 naming `accepted`/`rejected`, not 403. An agent reading the status code no longer concludes it lacks permission. |
| F16 | `3b4efd6` | `TaskResponse` echoes `loop_id`, so a caller can confirm from the create call that the task joined the loop. |
| S2 | `3b4efd6` | `short_id()` widened 8 → 12 hex. No migration; every column was already `String(64)` and a segment is generated, never parsed. |
| F11 | `d706187` | `run_count`/`last_run` are stamped where `run.status` becomes `in_progress`, not above every skip branch. `next_run` deliberately stays where it was. |
| F13 | `d706187` | `PATCH {enabled: true}` on an ended loop is 409 with `code: loop_ended`, instead of 200 that the next firing silently undoes. |
| F1 | `d706187` + `7fcd172` | A cron restricting both day-of-month and day-of-week is refused at create and update, and the form and card say why instead of dating it with croniter's OR answer. |
| F17 | `7fcd172` | `last_seen` derives from runs, outputs *and* heartbeats (`hub/hub/agent_activity.py`). It was heartbeat-only, and only self-registered agents post those — so it was permanently NULL for every agent the product manages. |
| F19 | `7fcd172` | `TaskCard` marks a gated task, with the blocking prerequisites and their statuses in the title. Neutral for an ordinary gate, red only for `gated_on_rejected`. |
| F9 | `7fcd172` | A read-only `GET /tasks/{id}/integration-preview` and an inline note on the approve control naming the commit and the branch. Not a dialog. |
| F14 | `7fcd172` | `awaiting_answer_reason`, computed per request, so a run parked on `ask_user` reads "waiting on you" without the status being touched. |
| F2 | `7fcd172` | "server time" → "UTC" on both jobs surfaces. The value was always right; the word was wrong by an hour, every summer, on your own machine. |

### What did not land, and why

All twenty F-findings plus S2 are accounted for below or in the table above — F1, F2, F4, F6, F7, F8, F9, F11, F13, F14, F16, F17, F18, F19 and S2 landed; F3, F5, F10, F12, F15 and F20 did not.

- **F19's `dependents` half.** The card says what gates it, not what it gates. A task with
  dependents is not blocked by them and the Dependencies board already draws those edges. Recorded
  as a decision in `decisions_for_user`, not an oversight.
- **F5 and F10** — the two architectural changes. Specified, strict-validated, deliberately not
  implemented unattended. That was the whole point of how this queue was scoped.
- **F12** (a loop firing every minute while finished work waits for review) — held out, because
  `loop-becomes-a-flow` fixes its root cause and papering over it now is work thrown away.
- **F3** (`contact_mode` still defaults to `watchdog-spawn`) and **F20** (an unknown deep link falls
  back to Overview) — judged not worth fixing. Say if you disagree.
- **F15 was never in this queue, and was not in `decisions_for_user` either — that was an
  omission, and this is it being closed.** "Stopping an agent does not stop the work":
  `POST /agent/{name}/stop` stops one run correctly, and the queue starts the next one moments
  later, because a peer conversation outlives a per-run stop. There is no "pause this agent" lever
  at all. That is a missing *capability*, not a papercut — it needs a decision about what a paused
  agent does with queued input, so it could not have been taken unattended even if it had been
  listed. It is now in `decisions_for_user`.
- **F4 only recognises `main`/`master`.** `detect_main_branch` walks
  `requirement_evidence.MAIN_BRANCH_NAMES`, which is exactly those two. A project on `develop` or
  `trunk` still opens with `main_branch` null. Widening it was not taken unattended: guessing that a
  one-branch repository's branch is its trunk is plausible, but it is a guess that ends in a
  cherry-pick into that branch.

### Verification run in this firing

- **Full backend suite**, `py -3.11 -m pytest hub/tests/ -q`: **2838 passed, 84 skipped, 1 xpassed, 0 failed** (14m33s). Identical to the Q3 firing's count, which is the right answer — Q4 changed only the built artefact, so a different number would have meant something moved that should not have.
- `npx vitest run`: **1374 passed, 138 files, 0 failed** (42s).
- `npm run lint` at `--max-warnings 0`: clean. `npx tsc --noEmit`: clean (also inside the build).
- `uvx ruff@0.15.22 check src/ hub/ tests/`: clean.
- `uvx black@26.5.1 --check src/ hub/hub/ hub/tests/ tests/`: 448 files unchanged.
- `npx openspec validate --changes --strict`: 4 passed.
- `AW_CHECK_UI_BUNDLE=1 pytest hub/tests/test_ui_build_stamp.py`: 11 passed.

### Driven, not just tested

`.claude/autonomous/scratch/drive_q4.py` (gitignored) boots the real FastAPI app on a temp SQLite
database, seeds a project and a real git repository, and reads the JSON a real caller receives:
**20 checks pass, 1 unreachable.**

It covers what the unit suites cannot: `/health` reporting on the *committed* artefact; F4 read
through **both** surfaces that expose it (`GET /settings` and the suggestion route's `chosen`) plus
the re-open case, where a branch changed to `release` is not overwritten; F1 refused at create *and*
update, with a check that the refused update left the stored cron alone; F13's 409 followed by a
re-read proving the job really stayed disabled; and F8's 422 with the permitted values in the body.

The one unreachable check is F8 on `POST /agent-actions/spec/evidence/{id}/decision`, which 401s on
a missing run credential before it reaches any decision logic. It maps the refusal identically —
`exc.http_status or status.HTTP_403_FORBIDDEN`, `agent_actions.py:959` — read rather than driven,
and stated here as read.

### Cross-surface check the suites do not make

F1 lives in two independent implementations — `cron_day_ambiguity_reason` in Python and
`cronDayAmbiguity` in TypeScript — and a disagreement between them is exactly the "two surfaces,
two answers" the finding was about. Both were run over the same 17 expressions and **agree on every
one**, including the ones designed to catch a sloppy port: `0 0 * * 0-7` (eight accepted values,
still seven days → allow), `0 0 15 * 0,7` (refuse), `0 0 1-31 * 5` (a day-of-month that restricts
nothing → allow), `0 12 * * mon,fri` (allow), and `0 0 L * 5` / `0 0 15 * ?` (unparseable → do not
refuse, leaving croniter and APScheduler the authorities).

### Read of the whole diff

`git diff 3b4efd6^..HEAD`, excluding the bundle: **38 files, +3666/−50**. No file under `src/`
changed at all — the CLI is untouched. No deleted subsystem reappears (`watchdog.py`,
`messaging.py`, `runner.py`, `transport/local.py`, `transport/git.py`, the role subsystem: none
present). No `kimichanges.md`, no `kimiwork.md`, no root `agentweave.yml`, no generated debris. Eight
new files, all of them either a test, the one new module `hub/hub/agent_activity.py`, or this log.

### Two things noticed while reading, neither a defect today

1. **`record_evidence`'s agent route drops `http_status`.** `agent_actions.py:846-849` maps
   `EvidenceRefusedError` to a hard 409 without consulting `exc.http_status`, where the *decide*
   route at `:959` honours it. Correct today — F7's duplicate refusal sets no `http_status` and 409
   is right for a duplicate — but a future refusal on the record path that sets one would be
   silently downgraded. Worth an eye if that field grows callers.
2. **F11 moved a governance boundary as a side effect.** `_authorize_loop_task_creation` gates a
   creator agent's definition window on `job.run_count > 0`. Now that `run_count` counts only real
   firings, a loop that has only ever *skipped* keeps its creator's window open longer. That reads
   as more correct — no agent ran, so nothing has been briefed — which is why it was not
   special-cased. It is in `decisions_for_user` because it is yours to confirm.

### What surprised us

- **The staleness warning was chasing the wrong field**, and two sessions before this one burned a
  cycle on it. `src_fingerprint` is the whole check; `src_commit` and `built_at` are documentation.
- **`ProjectSummary` has never carried `main_branch`**, which briefly read as F4 having failed on
  the real route. The stored value was correct the whole time; the drive was reading a field that
  does not exist on that schema. The F4 regression test's own docstring says so, and it was faster
  to read the test than to re-derive it — an argument for tests that explain themselves.
- **Two firings died mid-iteration on `API Error: 529 Overloaded`** (05:55, 06:12), and Q3 took four
  firings to close as a result. Nothing was lost either time, because every iteration leaves the
  tree on disk and the state in `STATE.json`. The design held.

### Committed

`9eb37c8` (the bundle) plus this entry and the final state. Nothing is uncommitted.

### Continuation

**The queue is empty and `stop_when_queue_empties` is true, so this run is done.** What is waiting
for you is in `decisions_for_user` — read the posture question and the two 2026-08-23 openspec
changes first; `2026-08-23-a-reviewer-can-see-the-work` also unblocks `loop-becomes-a-flow`, which
currently ships a reviewer that cannot read code.
