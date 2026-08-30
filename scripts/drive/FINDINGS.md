# Findings — driving AgentWeave

Project under test: `ledger-stress` = `proj-18e5d4e0` at `C:\Users\huida\Documents\aw-stress`
Trial Hub `127.0.0.1:8010`. Agents: `builder`/`critic` (Haiku 4.5), `relay` (gpt-5.4-mini).
Settings for the test: `hop_budget=2`, `allow_agent_jobs=true`, `main_branch=master`.

Severity: **A** = wrong behaviour an operator will act on · **B** = wrong/misleading surface ·
**C** = friction or vestige.

---

## Open severity-A baseline, 2026-08-27

The start line for the operator's proposed freeze — *fix every severity A that driving can find,
then migrate*. Every `## F<n>` section below now carries a `**Status:**` line, sourced from
`git log --all --grep`/`-S` restricted to commits **at or after the commit that first wrote that
section** (the F-numbers in `Q4-spec-ux-fixes` and `N6` commits belong to a different findings
series — `.claude/autonomous/2026-08-16-operator-ux-findings.md` — and would otherwise produce
false attributions), plus each section's own prose.

**Severity A, still open — three, and only one of them is wholly open:**

| Finding | State | Where it stands |
|---|---|---|
| **F12** — `stop_when_queue_empties` waits for a human, and burns a firing a minute meanwhile | ~~open~~ **fixed** `5237ec5` — **this row was wrong** | The eviction was fixed 2026-08-24 under its own design vocabulary, so the grep-over-commit-messages method used to build this table could not see it and reported it as untouched. The idling that remains was always correct. See F12's own correction. |
| **F52** — the "workspace" posture never sees a git command | **partially fixed** `68459ea`; the rest does not reproduce | The operator-visibility half shipped. Every axis of the underlying refusal is eliminated (`0cda570` disproved its central inference — `record_permission_decision` persists only refusals — and `57eb92b` drove a full live turn that committed). Out of scope: a new git refusal is a **new** finding. |
| **F60** — an unanswered `ask_user` that resolves itself leaves the task reading `completed` | **partially fixed** `033ec4c` | The guard refusing an answer whose asking run has ended was already shipped before F60 was filed. The remaining half is **parked for F14**, whose fix shape is the operator's undecided call. |

`F9 (A-)` is not a defect — it is the merge-on-approval behaviour, recorded because it is the most
consequential thing the product does. Every other A (`F1 F5 F10 F23 F27 F41 F43 F45 F49 F51 F54 F56
F57 F58 F70 F71 F72 F100 F101`) is fixed with a commit named in its `**Status:**` line — `F100`
and `F101`, both filed and fixed on 2026-08-28, are the newest, and each was found by a probe
aimed at the finding before it.

**Open below severity A**, for completeness: `F3` `F15` `F20` `F21` (C/C/C/B, all with the cause
named), `F42` (C), `F47` (C, deliberately deferred — it needs a third actor kind), `F61` (B, fix
chosen by the operator and not implemented), `F62` (C), `F65` (C, queued as `Q4-SPEC`), `F66`
(unrated, a question for the operator), `F68` (B), and `F53`'s second half (B, queued as `Q4-SPEC`).
`F14`'s task-state half is open and blocks `F60`.

**Read this as a floor, not a ceiling.** A short A list measures what *this* corpus of driving has
found, not what is there. Tonight's sweeps exist to lengthen it.

### Movement against the baseline, as of 2026-08-28 03:30

The sweeps did lengthen it, which is the point. **Eleven severity-A findings have been added since
the table above was written, ten of them fixed the same night:**

| Finding | Iteration | State |
|---|---|---|
| **F74** — a task's own evidence rejected as a duplicate of itself | 2 | fixed |
| **F76** — a review started by hand provisions the reviewer and never staffs the task | 2 | **open** — three repairs are live and the choice is the operator's |
| **F78** — the operator cannot clear a task's assignee, and the API reports that they did | 3 | fixed `f1d0c6f` |
| **F79** — a task the operator has decided about still takes new runs | 3 | fixed `eba8620` |
| **F83** — a loop created enabled with `initial_tasks` never reaches the scheduler | 4 | fixed `0757be5` |
| **F84** — an operator who stops a loop stops nothing; it fires for another seventeen minutes | 4 | fixed `0757be5` |
| **F85** — a loop stages a review it cannot start, wedges the task, and fails on it forever | 4 | fixed `3e07726` |
| **F87** — a message the Hub gives up on disappears, and the record says nothing | 5 | fixed `46458ae` |
| **F88** — two grants the operator can confer, and neither had ever done anything | 6 | fixed `a42f978` |
| **F89** — an automatic checkpoint holds the database lock and kills the turn | 6 | fixed `7cecd71` |
| **F90** — a turn held back by another agent's turn is never let go again | 6 | fixed `a053553` |

So the open-A list today is **F12, F76**, plus F52's and F60's partial states unchanged. F76 is open
because its fix shape is a decision, not because nobody has looked at it.

**Revised 2026-08-28: the open-A list is F76 alone.** F12 was verified rather than trusted and
turned out to have been fixed on 2026-08-24 (see its row above and its own section). One remaining
severity A, and it is waiting on a product decision.

**Revised again, later on 2026-08-28: the open severity-A list is empty.** F76's shape was decided
by the operator, specified through three review rounds, implemented and driven live. Driving it
produced one new finding — **F108 (B)**, a permanently refused request answering
`200 {"success": true}` — fixed for review dispatch and open as a class. An empty A list measures
this corpus of driving, not the product; the next sweep is what lengthens it again.

**And one observation that outranks any single row of that table.** F88, F89 and F90 were found in
one iteration, in three unrelated subsystems, and every one of them was a mechanism this repository
tests *thoroughly* — against a state the product never produces. F88's access tests pass a
`visibility` value nothing stores. F89's generation tests spawn with nothing else writing, when in
production the only thing that reaches that path is a live turn streaming output. F90's collision
test ends the holder's run with a database write and then performs, by hand, the exact scheduling
call the product omits. **When a test has to set something up for the code to reach the state under
test, ask who does that in production.** If the answer is "nothing", that is the defect, not the
fixture.

---

## F1 (A) — One cron string, three different answers; the one on screen is wrong

**Status:** fixed d706187 (backend) + 7fcd172 (UI half)

**Confirmed live.** `hub/hub/scheduler.py` reads every cron expression twice, and the UI reads it a
third time, and the three do not agree whenever **both** day-of-month and day-of-week are
restricted:

| reader | rule | where it shows up |
|---|---|---|
| APScheduler `CronTrigger` (`scheduler.py:677-684`) | **AND** | what actually fires |
| `croniter` (`scheduler.py:803-804`) → `job.next_run` | **OR** | `JobCard.tsx:321` "Next: …" |
| `cron.ts nextRuns` (`cron.ts:406-408`) | **AND** | `JobForm.tsx:46` preview |

Measured, both through the API and against the libraries directly:

```
cron '0 0 1 * 1'   Hub API next_run: 2026-08-24T00:00:00Z   APScheduler fires: 2026-09-01   Δ  8 days
cron '0 0 15 * 5'  Hub API next_run: 2026-08-28T00:00:00Z   APScheduler fires: 2027-05-15   Δ 260 days
```

Evidence: `job-ee75c21a` and `job-18311467` on `proj-18e5d4e0`.

Two things make this worse than an off-by-one:

1. **POSIX cron ORs.** croniter is the one that matches every other cron on the operator's machine.
   So the *displayed* value is standard-correct and the *behaviour* is the deviation — an operator
   pasting a working crontab line gets silently different scheduling.
2. **The form and the card disagree with each other.** Creating `0 0 15 * 5` shows a next-run
   preview in the form and a contradictory "Next: in 5 days" on the resulting card. Neither screen
   tells the truth about May 2027.

`describeCron` already declines this shape (`cron.ts:368-370`, "the ambiguous pair is refused
before this runs") — so the product has *already recognised* the ambiguity in prose and still
renders two numeric answers for it.

## F2 (B) — "Server time" is a UTC clock wearing a local label

**Status:** fixed 7fcd172

**Confirmed live.** The scheduler is pinned to UTC (`scheduler.py:626` and `:683`). `cron.ts`
correctly computes its preview in UTC and says why (`cron.ts:415-416`). But both jobs surfaces
label the result **"server time"**:

- `JobForm.tsx:193` — `{upcoming.join(' · ')} (server time)`
- `JobsPage.tsx:182` — `Jobs fire based on server time`

Measured on this machine right now: local `2026-08-23 18:34` (GMT Summer Time, UTC+1), UTC
`2026-08-23 17:34`. So a job previewed as firing at "09:00 server time" fires at 10:00 by the
clock on the operator's wall, every summer. The value is right; the word is wrong. Fix is one
word — "UTC" — not a timezone feature.

## F3 (C) — `contact_mode` still defaults to `"watchdog-spawn"`

**Status:** open (no commit references it)

Every agent created through `POST /projects/{id}/agents` comes back with
`"contact_mode": "watchdog-spawn"` (measured: `agent-61634fab`, `agent-ee3a289d`, `agent-b38ef2b7`).
The watchdog was deleted and CLAUDE.md lists `watchdog.py` among the modules that must never be
recreated. The name survives on the public API surface as the default value of a field, which
means the first thing a new integrator reads about how agents are contacted names a subsystem that
does not exist.

## F4 (C) — A fresh project does not adopt the main branch it can already see

**Status:** fixed 3b4efd6

`POST /projects/open` on a git repository returns `main_branch: null`, while
`GET /projects/{id}/main-branch-suggestion` immediately answers
`{"suggestion": "master", "chosen": null, "is_repository": true}`. The Hub knows the answer at open
time and still requires the operator to go and confirm it in settings. Everything downstream that
needs a base branch (worktree isolation, conflict detection, evidence footprint re-stamping via
`project.main_branch`) is degraded until they do, with no prompt saying so.

## F5 (A) — The hop budget is defeated by any operator message, and the counter resets

**Status:** fixed 7aef82d, re-driven live 407c01b

**Confirmed live, reproduced deliberately.** The hop budget is the product's only guard against a
runaway agent-to-agent loop. It bounds *admission* — but not *delivery*, and not the depth counter.

Reproduction on `proj-18e5d4e0` with `hop_budget = 1`:

1. Operator triggers `builder` (entry `entry-7e51771f`, hop 0) → `run-693eb7cd`, `turn_depth = 0`.
2. `builder` messages `relay` → `entry-97b01741`, hop 1. Within budget, delivered → `run-7b1c2917`,
   `turn_depth = 1`.
3. `relay` messages `builder` → `entry-5d572a6b`, hop **2**. Over budget. Correctly held:
   observed `state = queued` across four polls, ~30s, while every agent sat idle. **The guard works
   when the entry is alone.**
4. Operator sends one ordinary message into the same conversation → `entry-d41e4213`, hop 0.

Result, read straight from the database:

```
entry-d41e4213  operator  hop 0  delivered  run-a6683c96
entry-5d572a6b  agent     hop 2  delivered  run-a6683c96     <- over budget, delivered anyway
run-a6683c96    builder   turn_depth = 0                     <- not 2
```

Two distinct defects, both in `turn_scheduler.schedule_agent`:

- **Delivery is not filtered by depth.** `can_start` (`inbound_queue.py:91`) returns true if *any*
  entry is within budget, and then `selected = [e for e in entries if e.conversation_id == …][:cap]`
  (`turn_scheduler.py:65`) applies no `hop_depth` filter at all. The blocked entry rides along.
- **The counter resets downward.** `turn_depth = min(entry.hop_depth for entry in selected)`
  (`turn_scheduler.py:91`), and the next hop is computed as `source_run.turn_depth + 1`
  (`agents.py:1400`). Batching a hop-0 entry with a hop-2 entry produces a turn at depth 0, so the
  chain restarts its count from zero.

Why this matters more than it looks: the intended way to use this product is an operator
supervising agents that message each other. Every operator message resets the guard for that
conversation. The bound is not defeated by an adversarial case — it is defeated by ordinary use.

A fix has to decide something the code currently does not: whether an over-budget entry should be
held back from the batch (and the turn take `max`, or the controlling entry's own depth), or
whether an operator message is *meant* to forgive the chain. The second reading may well be the
intended policy — but nothing in the code or its comments says so, `can_start`'s `any` reads like a
liveness check rather than a pardon, and either way the depth arithmetic is wrong.

### Resolved 2026-08-24 — `2026-08-23-the-hop-budget-is-a-real-bound`

The operator chose the first reading. `schedule_agent` filters the batch by depth as well as by
conversation, and the turn's depth is the admitting entry's rather than `min()` across the batch.
Forgiveness stays available but becomes explicit: `POST /queue/entries/{id}/release` re-bases a
held entry to depth 0 and delivers it, surfaced as **Continue** beside **Discard** on the entry.
The rejected alternative — an operator message forgives the chain, but loudly — is argued in the
change's proposal.

Re-driven on the same fixture, same shape as the reproduction above:

```
entry-d7953fb45fb8  agent     hop 2  queued                        <- held, and stays held
run-bfacac7ea3b2    builder   turn_depth = 0                       <- the operator message
                                                                      delivered nothing else
```

Then Continue, on the same entry:

```
POST /queue/entries/entry-d7953fb45fb8/release  ->  200, hop_depth 0
entry-d7953fb45fb8  agent     hop 0  delivered  run-f87d988893f7
queue_entry_released  {"entry_id": "entry-d7953fb45fb8", "released_from_depth": 2}
run-f87d988893f7      builder  turn_depth = 0
```

The depth it was released from survives only in the event: after the re-base the row reads 0.

## F6 (B) — A task being actively worked shows no assignee and an idle assignee-status

**Status:** fixed 3b4efd6 + 7fcd172 (the board's half)

While `run-f8f7a33c` was live on `task-cdd990b1`, the task read:

```
status: in_progress    assignee: null    assignee_status: "idle"
```

The run *was* bound to the task — `bind_run_to_task` moved it to `in_progress`, which is the only
reason its status changed. But nothing wrote the agent's name to `assignee`, and
`assignee_status` is derived from that null, so it reports `idle` about an agent that is at that
moment running. A board watcher sees an in-progress, unassigned card whose assignee is idle.

## F7 (C) — Duplicate evidence for one requirement is accepted without comment

**Status:** fixed 3b4efd6

`builder` recorded evidence for FR-1 unprompted on its first turn (`ev-42cad5d2`), then recorded
the same fact again when asked (`ev-5d0273ad`) — same requirement, same task, same commit, near
identical prose. Both were stored, both entered `review_state: awaiting`, and coverage read
`evidence_count: 2, accepted_count: 0`. The reviewer has to decide twice about one fact, and
`evidence_count` overstates what was demonstrated.

Note the `digest` field is *not* a duplicate detector — it pins the requirement's wording at
production time (`requirement_evidence.py:113`), which is a different and well-designed mechanism.
There is simply no duplicate check.

## F8 (C) — Two refusals, two standards of helpfulness

**Status:** fixed 3b4efd6

Same session, same operator, minutes apart:

```
POST /agent/trigger  {"overrides": {"permission_mode": "auto"}}
  400  "'auto' is not a permitted value for 'claude''s 'permission_mode'
        (permitted: acceptEdits, bypassPermissions, manual, workspace)"      <- excellent

POST /project/spec/evidence/{id}/decision  {"decision": "accept"}
  403  {"message": "unknown decision 'accept'", "code": "unknown_decision"}  <- names nothing
```

The permitted values are `accepted` / `rejected` (`requirement_evidence.py:56-57`). The product's
own stated principle — "a refusal the author cannot act on produces a retry loop, which is the
failure mode the prose contract had" (`spec_payload.py:48-52`) — is honoured in one place and not
the other. Also note 403 for a malformed enum: this is a validation error, not an authorisation
one, and an agent that reads the status code rather than the body will conclude it lacks
permission and stop trying.

## F9 (A-) — Approval merges to master, and that is worth stating loudly

**Status:** not a defect (deliberate behaviour); stated loudly in the UI by 7fcd172

Not a defect — the opposite — but it is the single most consequential behaviour in the product and
it is not announced anywhere the operator will see it before it happens.

Driven end to end: approving `task-cdd990b1` ran `task_integration`, which cherry-picked the commit
named by the *accepted evidence* (`cecbc88`) from `agentweave/builder` into `master`, producing
`fbeeb26 Integrate approved work cecbc88751ea`. The main working tree changed on disk.

The design is careful — merge a commit and never a branch, never merge into a branch nobody named,
never push — and all three held. But an operator clicking "approve" on a task board is, at that
moment, writing to their main branch. The first integration attempt (before evidence was accepted)
correctly reported `skipped: no accepted evidence names a commit`, which is the right refusal; what
is missing is any warning on the *successful* path that approval is a write.

## F10 (A) — A reviewer agent cannot see the work it is reviewing

**Status:** fixed 3b75b02 + 3b3b7be, driven live 2a88b64, recurrence ruled out 31c8639

**The most consequential finding of the run, and the product reported it itself.**

`builder` finished FR-2 and FR-3 in its isolated worktree and messaged `critic` to review. `critic`
tried to read builder's worktree and the workspace boundary refused it:

```
event permission_denied  run-2a499a0a
  {"tool_name": "Bash", "reason": "'/builder' is outside your workspace"}
```

Worktrees at that moment:

```
aw-stress                              fbeeb26 [master]           <- only FR-1 integrated
aw-stress/.agentweave/worktrees/builder ef11228 [agentweave/builder]  <- FR-2, FR-3 live here
aw-stress/.agentweave/worktrees/critic  fbeeb26 [agentweave/critic]   <- reviewer sees master
```

The reviewer did not fabricate a verdict. It wrote back, verbatim:

> "I can verify FR-1 (Money.parse) is correct — it's already integrated… However, I can't access
> your branch (agentweave/builder) from my isolated worktree to verify FR-2 and FR-3. The evidence
> points to commit cad5d74… but I need to see the actual code changes. Can you either: 1. Confirm
> the fixes are complete… 2. Or open a note describing exactly what changed…"

That is exactly right and exactly the problem. The only remedy available to a reviewer is **to ask
the author to describe the author's own work** — the one arrangement code review exists to prevent.

The gap is structural, not incidental:

- Isolation is per-agent (`worktrees.branch_name` is per agent) and enforced by `AW_WORKSPACE_DIR`.
- Work only becomes visible to others by being **integrated into main**, and integration only
  happens **on approval**, which is what the review is supposed to decide. The dependency is
  circular.
- The Hub already knows precisely what the reviewer needs: every evidence row carries
  `footprint: {branch, commit_sha, reachable_from_main}`. `ev-42cad5d2` named
  `cecbc88751ea…` on `agentweave/builder`.
- None of the 21 MCP tools can read another worktree, fetch a commit, or return a diff. There is no
  read path at all.

The fix is small relative to its value — a read-only "show me the diff this evidence names" tool,
or permitting a reviewer read access to the commit its evidence cites. Until then, multi-agent
review is a conversation about code rather than a review of it.

### A lookalike traced and ruled out, 2026-08-26 (Q5, iteration 8's cascade)

Iteration 8 flagged a possible recurrence: `critic`'s transcript on `run-e842f20908da` said, almost
verbatim, "I cannot access the builder's worktree commits… I am blocked" before separately
discovering it could read the builder's branch directly with `git`. Traced against the live `runs`
table before treating it as F10 come back: `run-e842f20908da`'s `task_id` is `task-3292072f63c3`
("Round half to even in `Money.quantize()`") — a plain, already-`completed`, non-review turn, not a
`review_task_id` turn at all. `_review_task_from_entries` (`agent_trigger.py`) only ever resolves
`review_task_id` from the batch's own queue entries; this batch carried none, so `review_turn`'s
checkout — the machinery F10's original fix and every deliberate drive this session actually
exercises — was never invoked. What happened instead: `critic`, reading its own regular task queue
and finding nothing to do on the named task, went looking at `list_tasks`/`list_evidence` on its own
initiative, found `task-0dfc3be5` genuinely `under_review`, and tried to inspect it **from its own
ordinary working worktree** — which, correctly, does not contain another agent's uncommitted or
unmerged work. It then discovered (correctly) that `git branch -a` / `git checkout` reach the
builder's branch anyway, because worktrees share one object database, and completed a real review
that way, ending in a genuine `revision_needed`. Two separate things are true at once: the
*structured* review path (F10's actual fix) is intact and was not exercised here; and an *ad hoc*
review conducted through raw git commands from a non-review worktree also worked, which the original
F10 write-up did not anticipate as a possible route. Not reopening F10 — this is a different, and so
far harmless, path to the same information, not the same blindness recurring. Worth a name if a
future session sees it fail rather than succeed: an agent self-directing into reviewing a task the
turn was never given `review_task_id` for.

## F11 (B) — `run_count` counts firings that did nothing

**Status:** fixed d706187

**Confirmed.** After the loop's life: `run_count = 9`, of which only **4** spawned an agent. The
rest were skips (`loop queue is stalled`, `loop queue is empty`). `scheduler.py:796-797`
increments `run_count` and stamps `last_run` *before* any skip branch runs, so both fields describe
"the scheduler considered this job", not "this job ran". A card reading "9 runs · last run 18:01"
overstates by more than 2x, and `last_run` points at a firing that did nothing.

The `JobRun` rows themselves are honest — they carry `status` — so the `Last 5` health dots are
right while the count beside them is wrong.

## F12 (A) — `stop_when_queue_empties` waits for a human, and burns a firing a minute meanwhile

**Status:** the severity-A half is **fixed** `5237ec5` (2026-08-24), which never named this
finding — see the correction at the end of this section. The residual is by design. Was recorded
as "open (no commit references it)" and queued as F12-SPEC/F12-IMPL on 2026-08-27; that status was
wrong, and how it got that way is worth more than the correction.

**Confirmed live.** "Empty" is defined by `TERMINAL_FOR_BINDING = ("approved", "rejected")`
(`scheduler.py:91`). A loop whose agent has *finished every task* is therefore not empty: the tasks
sit `completed`, waiting on review.

Measured: both loop tasks reached `completed` at 17:56. The loop then fired at 17:57, 17:58, 17:59
— once a minute — each time skipping with `loop queue is stalled: no claimable task among 2 open
(2 completed)`. It only stopped at 18:00, the minute after I approved them by hand.

Skipping is the right call (`_loop_stall_reason` argues this well: stopping would be unrecoverable).
But the consequence is not bounded:

- The loop fires forever while a human does not review. Overnight that is ~480 firings.
- `_prune_job_history` keeps the most recent **100** JobRuns. At one skip per minute, **the record
  of the four firings that did real work is deleted after 100 minutes**, leaving a history of
  nothing but skips. The evidence of what the loop achieved is destroyed by the loop's own idling.

### Corrected 2026-08-28: the second bullet was fixed on 2026-08-24, four days before it was ranked open

**The bullet above — the half that made this severity A — does not happen any more.** A
*continuing* stall now counts in place instead of appending: `_stall_run_to_increment`
(`scheduler.py`) matches this firing's stall against the job's most recent `JobRun` and, when that
row is itself a stall with an unchanged reason, increments its `tick_count` and discards the row
this firing built. `fired_at` deliberately stays at the first refusal, so the row reads "this stall
began then and has been re-checked N times" and genuine firings sort above it rather than being
pushed out. So 480 overnight refusals occupy **one** row, not 480, and evict nothing.

Shipped as `5237ec5`, *"a continuing stall counts in place instead of appending a row"*
(2026-08-24 16:44), under `loop-notices-and-reacts` design D6 — which is why nothing found it: the
commit solves this finding without ever naming it. Covered by `test_loop_stall_ticks_in_place.py`,
six tests, green on 2026-08-28; `test_a_long_stall_does_not_bury_the_firings_that_did_work` is this
bullet almost word for word, asserting that twenty refusals between two real records leave both
records present and adjacent.

**Why the baseline got it wrong, which is the part worth keeping.** The `BASELINE` task sourced
every `**Status:**` line from `git log --all --grep`/`-S` restricted to commits at or after the one
that first wrote the section. That method can only find a fix that *names* the finding. A fix that
solves the problem under its own design vocabulary is invisible to it and gets reported as
`open (no commit references it)` — which reads as "nobody has looked at this" and is a stronger
claim than the evidence supports. F12 was filed 2026-08-23 and fixed 2026-08-24, the next day.
**A grep over commit messages measures what was written down, not what is true.** Any status line
in this file sourced that way carries the same risk, and the cheap check is the one that settled
this: find the mechanism in the code, then run the test that names it.

**What remains, and why it is not a defect.** The loop still fires once a minute against a stalled
queue, so ~480 firings a night still happen. That is the idling itself, which this finding always
said was correct (`_loop_stall_reason` argues that stopping would be unrecoverable) and which the
run's own pre-authorisation ruled out changing. Each such firing is now one cheap query that
increments a counter. The operator-facing consequence — a history of nothing but skips — is gone,
and what replaced it is arguably better than silence: a single row stating when the stall began and
how many times it has been re-checked.

**No decision needed on this finding. It is closed.**

## F13 (B) — Re-enabling a finished loop is accepted, useless, and leaves a contradictory state

**Status:** fixed d706187

`PATCH /jobs/{id} {"enabled": true}` on a loop that stopped with `ending_state: completed` returns
`200` and `enabled: true`, while the same response still carries `stop_reason: "loop queue is
empty"`, `stopped_at: 2026-08-23T18:00:00Z`, `ending_state: "completed"`. So the loop is
simultaneously enabled and finished.

One minute later it fired (`run_count` 8 → 9), immediately re-stopped, and set `enabled: false`
again. The operator's action was silently undone; the only account of why is a history row.

Nothing refuses the toggle or says "this loop has finished — give it work or create a new one",
which is what the operator actually needs to hear.

## F14 (B) — A task waiting on the operator still reads `in_progress`

**Status: FIXED 2026-08-30**, `a-task-waits-while-its-run-waits` (three spec rounds, then eleven
implementation groups: `bb3d3e7` … `3cec5a5`). The first half was `7fcd172`'s derived
`awaiting_answer_reason`, which reported the wait beside a status that contradicted it; the
task-state half is now the status itself.

**What shipped.** The agent-facing question routes park the asking run's bound task *as the question
is asked*, reusing `block_task_for_question` unchanged — so the ordinary wait is `blocked` with a
`blocked_reason` naming the question, for the whole of the wait rather than only after the run ends.
`awaiting_answer_reason` stays, and its four comments claiming a task parks only at the run's end
are corrected: it now covers the two waits the status cannot carry — a task in `under_review`,
`pending` or `assigned`, which `block_task_for_question` correctly refuses to park, and a batch whose
first answer released the task while the run waits on the rest.

**Confirmed live** (`scripts/drive/t_f14_f60_wait_parks_the_task.py`, Haiku, Hub on 8011 from
source): the task read `blocked` while the asking agent's roster status read `running` — the two
states this finding is about, which before this change could never coexist.

**Three things the rounds found that the finding itself did not.**

* `task_attribution` was never checked against blocked-while-running, and it is the module whose
  entire job is answering who is on a task. For the whole wait the loop board called an agent that
  was mid-turn on that exact task merely `assigned` to it — the same class of false statement as
  this finding. Fixed in group 3a; the drive reads `agent_capacity: "working"` on the parked task.
* The dependency gate refused `blocked -> in_progress`, deliberately and by a shipped rule, which
  made the wait a window in which a regressed prerequisite could strand finished work. Ungated
  (group 7), with both spec deltas, because `scheduler.candidate_is_startable` had already made the
  opposite decision in its own words and the board and the gate contradicted each other at exactly
  one edge.
* `task-lifecycle-governance:445` forbids leaving the waiting status by assertion as well as
  entering it, and only entering was enforced. Latent while `blocked` implied the asking run had
  ended; ask-time parking removes exactly that protection. Guarded at the route (group 2b), and the
  drive shows the 403 reaching a real agent's tool result verbatim.

`ask_user` worked well: `builder` asked a structured question with two labelled options,
`blocking: true`, `asker_waiting: true`, and the answer reached the agent, which then completed the
task. The whole operator-in-the-loop path is sound.

But while the run sat blocked on the question, its bound task read `status: in_progress`,
`blocked_reason: null`. `block_task_for_question` is called from exactly one place —
`run_divergence.evaluate_run_end` (`run_divergence.py:325-326`) — so a task only parks to `blocked`
if the run **ends** with the question unanswered. During the wait, which is the whole point, the
board says the work is progressing.

### The decision, 2026-08-30

**Park at ask time, and flag the timeout outcome.** Both halves, in one change, because the second
is what F60 needs and it has nowhere to live without the first.

**(a) The park moves to the moment the question blocks.** `block_task_for_question` is reached from
`run_divergence.evaluate_run_end` and nowhere else (`run_divergence.py:718`, restated at
`tasks.py:338`), so today a task parks only if the run *ends* unanswered. It must park when
`ask_user` blocks instead.

This is cheaper than it looks, and the exploration that established that belongs here so round 1
does not redo it: **no new task state is needed.** `blocked` is already a real status
(`src/agentweave/constants.py:273`) with `blocked_reason`, a transition map consulted through
`allowed_targets`, `question.blocked_task_id` recording what to release, and `release_reason`
called on every exit — the answer arriving, the operator releasing it, reassignment, rejection.
The machinery exists and works. It fires at the wrong moment.

**(b) A question that times out while the agent proceeds anyway is recorded on the task.** This is
F60's parked half. `QUESTION_ANSWER_TIMEOUT` expires *inside* the tool call, the agent decides the
judgment call itself and can move the task to `completed` in the same turn — so by the time
`evaluate_run_end` runs there is nothing left to park, and the board shows a clean completed task.
The operator is never told that a substantive call was made because they did not answer in time.

**What round 1 must settle rather than assume**, both consequences of (a):

- A task will be `blocked` while its run is still `running`. That combination does not exist today.
  Everything reading task status has to be checked against it — the divergence boundary check, loop
  and flow task selection, the dependency board.
- The timeout path needs a defined reconciliation: the task is `blocked`, the agent proceeds and
  tries to complete it. Whether `blocked → completed` is permitted, and what (b) writes when it
  happens, is the crux of the change rather than a detail of it.

**Rejected:** leaving the lifecycle alone and rendering `awaiting_answer_reason` more prominently.
Smaller and touches no transitions — but F60 measured the run-end fallback failing in exactly the
case that matters most, so a more prominent secondary field would still leave a timed-out question
ending as a clean completed task.

## F15 (C) — Stopping an agent does not stop the work

**Status:** open (no fix commit; recorded as an operator decision in a2424d9 — there is no pause-this-agent lever, only a per-run stop)

`POST /agent/builder/stop` behaved correctly: the run went to `stopped` (not `failed`), `ended_at`
was set, and the already-delivered queue entry was not spuriously returned.

But `critic` had meanwhile messaged `builder`, so a *new* builder run (`run-448817a1`) started
moments after the stop. The stop endpoint stops **one run**, and the queue immediately starts
another. There is no "pause this agent" — the only lever is per-run, and a peer conversation
outlives it.

## F16 (C) — `loop_id` is accepted on task creation but never echoed back

**Status:** fixed 3b4efd6

`POST /tasks {"loop_id": "loop-8e8379bb"}` returns `201` with `"loop_id": null` in the body, while
the loop's own summary immediately shows `queue: {pending: 2}` and names the task as
`current_task`. The write worked; the response denies it. There is no way to confirm from the
create call that a task joined the loop.

## F17 (B) — Every Hub-run agent says "No activity yet", forever

**Status:** fixed 7fcd172

**Confirmed in code, database and screenshot.** The agent rail renders
(`AgentTree.tsx:163-167`):

```tsx
agent.status === 'running' ? 'Running now'
  : agent.last_seen ? `Seen ${…}` : 'No activity yet'
```

`last_seen` is populated from one source only — a heartbeat row (`agents.py:537`,
`last_seen=hb.timestamp if hb else None`) — and heartbeats arrive only from
`POST /agents/{name}/heartbeat`, which **only a self-registered agent calls**. The Hub's own spawn
path never posts one, and there is no `last_seen` column on the `agents` table at all.

So for every agent the Hub manages — which, since the watchdog was deleted, is every agent —
`last_seen` is permanently null. In the captured screenshot, `builder` reads **"No activity yet"**
while having completed nine runs, 590 output rows and three code fixes in the preceding thirty
minutes. Every agent in every one of the five projects on this Hub shows the same line.

The information exists (`runs.started_at`, `agent_outputs.timestamp`); nothing joins it to the
roster.

## F18 (B) — Refinement of F6: the loop records an assignee, a direct trigger does not

**Status:** fixed 3b4efd6 + 7fcd172

The board screenshot shows `@builder · Idle` chips on the tasks the **loop** claimed
(`scheduler.py:979` sets `claimed_task.assignee = job.agent`) and no assignee at all on the task a
**direct `task_id` trigger** bound. Two paths reach `in_progress`; only one names who is doing it.

## F19 (C) — A gated task is indistinguishable from an ordinary pending one

**Status:** fixed 7fcd172

`task-b74d1511` ("Add a trial-balance report") depends on two unapproved tasks and cannot start.
On the board it renders exactly like any other pending card — `Pending`, `Medium`, its requirement
chips. Nothing marks it gated.

The data is available: `GET /tasks` returns a populated `prerequisites` array with each
prerequisite's status. `TaskCard.tsx` and `TasksBoard.tsx` reference neither `prerequisites` nor
`dependents` (grep: no matches). The dependency information is one tab away, on the Dependencies
board, but the operator has to already suspect there is something to look for.

## F20 (C) — Deep links use query parameters, and nothing says so

**Status:** open (no commit references it)

`/projects/{id}/tasks` silently renders Overview. The app has no router dependency; destinations
are query parameters read from `window.location.search` (`navigation.ts:327-375`), so the working
URL is `/?project={id}&tab=tasks`. This is a deliberate design (`useWorkspaceNavigation.ts` cites
"design.md decision 9 — no routing"), and it works — but an unknown path shape falls back to
Overview without comment rather than 404ing or correcting itself.

## F21 (B) — A Haiku agent cannot reach `record_evidence`, and burns a whole turn trying

**Status:** open — investigated 2026-08-25, the proposed remedy was already shipped and the cause is not here; left open with the cause named

**Observed live 2026-08-24**, during the review-checkout drive (`run-1515a942defc`), not while
looking for it.

`builder` was asked to implement FR-3 and then record evidence for it. It did the work correctly —
edited `ledger/book.py`, added `tests/test_account_order.py`, ran the suite and read back
`3 passed in 0.01s`, all committed as `90aa643`. Then it could not record any of it.

Its own narration, in order:

> "Now I'll record the evidence for FR-3. Let me invoke the record_evidence tool:"
> "Since the tools are now loaded, let me use Bash to verify the complete state and then record evidence:"
> "Now I need to find a way to call the mcp__agentweave__record_evidence tool."
> "Actually, I realize I've been trying to load the tool schemas with ToolSearch multiple ti[mes]"

The run ended `completed`, with a confident summary of work done and **zero evidence rows**. A
second turn scoped to nothing but the tool call — "do exactly one thing, call `record_evidence`, do
not use ToolSearch" — succeeded immediately (`ev-45ed5265d082`).

Two things this costs. The obvious one is a wasted turn. The worse one is that the run reports
success: an operator reading the transcript sees the work done and the tests passing, and the
coverage query says the requirement has no evidence. The failure is invisible exactly where it
matters.

Not the review checkout's doing — the same agent, same runner, same project, recorded evidence
happily when asked for that alone. It looks like deferred-tool discovery interacting badly with a
smaller model under a long instruction, which makes it a question about how the tool surface is
presented rather than about the tool.
### Investigated 2026-08-25 — the proposed remedy was already shipped, and the cause is not here

`the-seams-of-the-sweep` task 3.5 called for an investigation before a fix, on the grounds that the
remedy was unsettled. It was, and the investigation changed the finding.

**The planned fix already exists.** The remedy on the table was "name the callable tools explicitly
in canonical turn context, so a smaller model does not have to discover them." That is already
true, for every agent, and has a test pinning it —
`test_the_tools_are_named_to_every_agent_regardless` asserts `record_evidence(` and `list_evidence(`
appear in the rendered context. The agent's own narration confirms it received the name:

> "Now I'll record the evidence for FR-3. Let me invoke the record_evidence tool:"
> "Now I need to find a way to call the mcp__agentweave__record_evidence tool."

It knew what to call, including the fully-qualified `mcp__agentweave__` form. It could not *call*
it, and looped on `ToolSearch` trying to load the schema.

**Which puts the cause outside this codebase.** AgentWeave spawns `claude` with `--mcp-config` and
`--allowedTools "mcp__agentweave__*"` (`runner_commands.py:224-236`). Whether the spawned CLI
presents those 24 tool schemas eagerly or defers them behind a search step is that harness's
behaviour, not something the Hub selects. The failure is the interaction of deferred tool loading
with a smaller model under a long instruction — a real defect, and not one with a fix in `hub/`.

Two things that *are* actionable were separated out rather than left inside this finding:

1. **The invisible-failure half is now covered.** The worse cost recorded here was never the wasted
   turn: it was that *"the run reports success"* while the evidence rows do not exist. That is the
   same shape as **F38**, and `turn_produced_nothing` closes the shared half — a turn that was given
   a deliverable, produced nothing, and asked nothing is now recorded. F21's evidence case is not
   yet one of its triggers; the document case is. Worth extending once the shape has been driven.
2. **F39** was found by the audit this group also called for, and its likely remedy is the same
   question this finding raises: what the surface tells an agent it may call, in both directions.

**Disposition:** the tool-reach half is **not fixable in AgentWeave** as it stands. Reducing the MCP
surface below whatever threshold triggers deferral would work and is a product decision, not a bug
fix — 24 tools is the surface the product deliberately has. Left open, with the cause named, rather
than closed with a change that would not have prevented it.

## F22 (B) — Shared dependencies are not symlinked on this machine, and nothing says so

**Status:** fixed 5a76039

**Measured 2026-08-24**, not inferred:

```
Path.symlink_to(...) -> OSError [WinError 1314]
A required privilege is not held by the client
```

Windows without Developer Mode or admin rights. `_symlink_shared_dependencies` catches this and
degrades — it logs at INFO and carries on, which is the right call for provisioning, since failing
a whole turn over a missing `node_modules` would be worse.

The cost is that **every worktree on this machine has no shared dependencies and no surface says
so.** Not the agent, which discovers it by running the suite and failing; not the operator, who
sees a provisioned checkout that looks complete; not `doctor`, which does not check.

It has been invisible until now because the drive's fixtures are Python projects whose tools are on
`PATH`. It stops being invisible with the review checkout, because that change's entire
justification for handing a reviewer a checkout rather than a diff is that it can **run the tests** —
so a reviewer on a Node project here reports "could not run the suite" and is telling the truth
about an environment nobody told it about.

Worth fixing at the surface rather than the mechanism: say it once, where someone can act on it. The
remedy is one Windows setting, and it fixes every worktree at once.

---

# What worked, and worked well

Recording this with the same weight as the defects, because a report that lists only what broke
misdescribes the product.

- **The spec → task → evidence → approval → merge loop closed end to end**, driven entirely through
  the API. Four tasks materialised from an approved document with their dependency graph intact;
  approval cherry-picked the evidence commit into `master`.
- **The dependency gate refused correctly and legibly**, naming the blocking task, its id, its
  status, and distinguishing "wait" from "reopen".
- **A loop ran unattended and did real work.** Four firings, two tasks, correct code both times,
  clean stop with `ending_state: completed`. Haiku 4.5 fixed all three seeded defects correctly.
- **`ask_user` is excellent.** Structured options, `blocking`/`asker_waiting` flags, the answer
  reached the agent, the agent finished the work.
- **Crash recovery is honest.** Hard-killing the Hub mid-run left the run marked `interrupted` — a
  distinct status from `failed` and `stopped` — and returned its queue entry to `queued` with
  `delivery_attempts: 1`. No agent stuck "running", no lost input.
- **Stop is precise.** `stopped`, not `failed`; the already-delivered entry was not spuriously
  returned.
- **The workspace boundary genuinely holds.** `critic` was refused a read outside its worktree.
  That it holds is the reason F10 matters.
- **Refusals mostly teach.** The permission-mode error listing its four permitted values is the
  standard the rest of the API should meet.
- **Integration reporting is honest on the card.** "Not merged — no accepted evidence names a
  commit" with a "Try again" affordance, right where the operator is looking.

---

## F23 (A) — A flow at full width reads as stalled with nothing to do

**Status:** fixed 5716876

**Found live, 2026-08-24, on the first firing of a real flow.** `loop-becomes-a-flow` group 5 gave a
firing width; this is the regression it introduced into the *board*, and no unit test caught it
because the unit tests never had three agents mid-turn at the moment the summary was read.

Measured, with `builder`, `critic` and `relay` all executing turns on three tasks of one flow:

```
GET /projects/proj-18e5d4e0/loops   ->
  queue:         {"assigned": 3}
  current_tasks: []
  stall_reason:  "loop queue is stalled: no claimable task among 3 open (3 assigned)"
  firing_active: true
```

Three agents working flat out, and the loop reports **no current item** and **stalled**. It also
contradicts itself in one payload: `firing_active: true` beside a stall reason.

**Cause.** `decide_firing` is read by two callers for two different questions — the firing asks
*"what can I start"*, the board asks *"what is this loop working on"* — and design D12's resumption
branch answers only the first:

```python
if task.assignee:
    agent = task.assignee
    if agent in running:
        continue          # right for staffing, wrong for the board
```

Skipping a busy agent's task is correct for staffing: `schedule_agent` would refuse a second turn
anyway, so selecting it would be a drop. But the same `continue` removes the task from the walk
entirely, so no selection survives, and `_stall_reason_from_walk` then counts the queue and reports
a stall. Before group 5 the ordinary branch returned an `assigned` task unconditionally, so the
board saw it.

**Why it matters more than a cosmetic wrong label.** `loop-notices-and-reacts` exists because a
working loop that reads as dead invites the operator to restart something that needed nothing. This
reintroduces exactly that, and does it precisely when the flow is at its most productive — the
busier the flow, the more certainly it reports as stalled.

**Fix.** A task being worked by a busy agent is *in flight*: not selectable this tick, still the
loop's current work. `FiringDecision` gains `in_flight`, the board renders those as current items
with their agent, and a queue with work in flight is not stalled. That is the fourth answer
`FiringDecision`'s own docstring says room was left for.

**This is the finding that justified the live drive.** Groups 5 to 10 landed with 3037 passing tests
and a spec review per group, and none of it asked what the board says while three agents are
actually mid-turn — because in every test the turns are either finished or faked.

---


## F24 (C) — a refused firing's status label says `scheduled`, contradicting the reason beside it

**Status:** fixed 2656c0f

Observed 2026-08-25 driving group 8's checks on `job-453b909ba418`. The collapsed stall row in the
job card's Recent Runs renders its status word as **`scheduled`**, in the neutral text colour, with
the amber stall reason immediately to its right:

```
scheduled   loop queue is stalled: no claimable task among 1 open (1 completed)
                                        re-checked 5 times    25 minutes ago
```

The `JobRun` row's own status is `skipped`. Both user test guides describe this row as "one skipped
row", which is what the operator is told to look for and is not what the UI says. A row that
simultaneously reads "scheduled" and "stalled" makes the reader work out which word to believe.

Not blocking 8.2 — the count-and-age pairing does its job, which is what that check judges — but
the label is the first token on the row and it is wrong.

---

## F25 (C) — a stalled job card reads `0 runs` with a run visible underneath

**Status:** fixed 2656c0f

Same session. Before any real firing, the card showed the `0 runs` chip while Recent Runs displayed
one entry. `run_count` counts firings that actually ran, so a queue that has only ever refused is
honestly zero — and it went to `2 runs` once real firings happened, confirming the intent. But the
chip and the list are two counts of the same word on one card, and they disagree on first read.

---

## F26 (C) — the board names a different agent than the task's assignee

**Status:** fixed 2656c0f

Same session, after `builder` completed `task-18e900f3eb96` and the loop staffed a reviewer by
itself. The database has `assignee = 'critic'`; the board's current item renders:

```
completed | relay | Name the two totals when an entry does not balance
```

**Confirmed by reading the code**, not inferred. `_batch_loop_summaries`
(`hub/hub/api/v1/jobs.py`, ~line 217) builds `claimed_agents_by_loop` from
`decision.in_flight` merged under `decision.selections` — both of which answer *who would work this
next*, never *who holds it now*. So for a `completed` task awaiting review the agent shown is the
prospective **reviewer**: `relay`, the one agent that is neither the author nor the last reviewer.

The value is therefore right and the **presentation** is wrong: `completed | relay` reads as "relay
is working this", when it means "relay is who would review this". The column's meaning silently
changes with the task's status — for an `in_progress` task it is the current worker, for a
`completed` one it is a proposal.

Worth settling because 11.5 asks whether a wide board says *what* is happening, and an agent column
whose meaning changes with task status is exactly what would make three such lines unreadable.

---

## F27 (A) — a run can complete tasks it was never given and never did

**Status:** fixed 6c75edb (F42 is the residue it did not close)

**2026-08-25 full-surface sweep, project `aw-sweep`.** The most expensive finding of the run.

`run-fba9bbc08b8d` was a concurrency probe. Its entire prompt was *"concurrency probe 1: reply
CONC-1 only"*. It carried `task_id = NULL` — no binding to any task. Its first recorded words are
*"Message sent successfully. Now let me check for any assigned tasks."*

It then moved **four** unrelated tasks `pending → in_progress → completed`:

```
task-a57fc76baf30  C: document the fairness guarantee in README
task-43b57060ddc5  A: add a failing test for spread() with an idle member
task-c4c939ed8d31  B: fix spread() to count every staff member
task-301d3de1bb6b  Fix spread() to count idle staff
```

A later unbound run, `run-e8a02702cd01`, completed two more. Six tasks recorded as finished; no work
was done on any of them. Read straight from `task_transitions`:

```
task-a57fc76baf30 : pending -> in_progress | actor= run | run= run-fba9bbc08b8d
task-a57fc76baf30 : in_progress -> completed | actor= run | run= run-fba9bbc08b8d
```

**Nothing here is a bug in isolation, which is why no test catches it.** Three correct decisions
compose into a wrong outcome:

1. The Developer charter, line 33, instructs the agent: *"Call `list_tasks` to see what is waiting,
   and `get_task` for the one you are taking"*. Going to find work is the behaviour asked for.
2. `TRANSITIONS` grants a `run` actor both `pending → in_progress` and `in_progress → completed`.
   Both are legal, so `task_transition_service` is right to allow them.
3. `completed` requires no evidence — deliberately and correctly. `requirement_gate` refuses at
   `approved`, not at `completed`, because evidence is accepted after review and review follows
   completion; refusing `completed` would deadlock the ordinary path. Its docstring says so.

The gap is that **`update_task` never asks whether the run is bound to the task it is closing.**
`run_task_binding` exists precisely to answer "what is this run working on", and the write path does
not consult it. The one fact that separates "I finished this" from "I noticed this" is recorded and
unused.

Why it matters beyond tidiness: `completed` is in `BAND_AWAITING_HANDOFF`, so a flow will offer
every one of these six to *another* agent as reviewable work. A reviewer sees a task marked finished
by a peer, finds the code already correct — it was, because a different agent really had done that
work — and approves. `task_integration` then merges. The chain from "an agent glanced at a list" to
"work is on master" has no human in it and no single false statement along the way.

**Suggested shape, not a prescription:** for `-> completed` only, require the acting run's bound task
to match, leaving the operator unaffected. That is one condition inside `apply_transition`, beside
the two gates already there.

---

## F28 (B) — a flow created after its document is approved has a permanently empty queue

**Status:** fixed 96b54cd

Same session. `spdoc-3e0dbec860d0` was approved, materialising five tasks. A flow was then created
against that same document — accepted, `201`, the document claim held, everything looked right:

```
loop-d6da88c89c56 | Spread flow | stop_when_queue_empties: true | queue: {} | current_tasks: []
```

The five tasks carry `spec_document_id = spdoc-3e0dbec860d0` and `loop_id = NULL`.

**Cause, from the code.** `spec_tasks.materialise()` resolves `owning_loop` with
`select(Loop).where(Loop.spec_document_id == document.id)` and stamps `loop_id` on each task as it
creates it (`spec_tasks.py:117`, `:216`). Nothing back-fills. The comment at `:114` states the
assumption plainly — *"the binding was fixed at loop-creation time"* — which holds only when the
loop already exists at approval. Every loop-queue query reads `Task.loop_id`
(`scheduler.py:314, 327, 644, 1305, 1569`), never `spec_document_id`, so the tasks are invisible to
the flow that owns their document.

There is no error and no warning. `stall_reason` is `null`.

**And it is worse than a stall.** Firing it produced `run-536479b417d4` — a real turn, on a real
model, against an empty queue, despite `stop_when_queue_empties: true`. The failure mode is not
"nothing happens"; it is "an agent is spawned with nothing to do", on a cron, indefinitely.

The working order — create the flow, *then* approve the document — is not stated in `create_flow`'s
docstring, which says only that tasks "are added to this flow's queue automatically".

---

## F29 (B) — an approved document tampered with on disk is served to everyone, silently

**Status:** fixed 8f88114

Same session. `spec/changes/spread-fairness-metric-fix-for-idle-staff/spec.html` was approved, then
edited directly on disk with `<p>TAMPERED BEHIND THE HUB</p>`.

```
GET /projects/{p}/project/spec?path=...  -> 200, body contains "TAMPERED"
GET /projects/{p}/project/documents      -> divergence: None, diverged: None
```

Every reader — the operator in the Spec tab, and any agent calling `read_spec_document` — receives
the tampered text with nothing marking it.

The Hub is not missing the information. `SpecDocument.content_digest` holds the digest of what was
approved, and `spec_lifecycle.divergence(document, content_on_disk)` exists to compare them. It has
exactly one caller — `spec_service.py:236`, on the **save** path. So divergence is noticed only when
somebody tries to write, and never when somebody reads.

That inverts the guarantee the phase machine is built to provide. `spec_lifecycle`'s docstring opens
on the rule that *an agent cannot approve a document*, enforced by reading the phase from a row
rather than from the file the agent can write. The row is indeed authoritative for the phase; the
**content** is still served from the file, unchecked. Approval therefore attaches to a path, not to
the bytes anyone subsequently reads.

---

## F30 (B) — a self-registered agent bound to a runner reports a CLI named after itself

**Status:** fixed 6b1013f

Same session. Three agents were created via `POST /agents/register` and then bound with
`PATCH /agents/{name}` — the exact sequence this repo's own harness uses
(`.claude/skills/e2e-loop/e2e.py`, `cmd_agent`). All three were reported unlaunchable:

```
architect  runner=native  cli=architect  runnable=False  reason="Runner CLI 'architect' was not found in PATH."
probe      runner=claude  cli=claude     runnable=True   collab=True
```

`probe` differs only in having been created through `POST /agents`, the UI's Add-agent path.
Database rows: all four carry a real `runner_id`; the three broken ones carry `self_registered = 1`.

`launchability.get_agent_config` gates the entire bound-runner merge behind
`if agent_row is not None and not agent_row.self_registered:` (`launchability.py:353`). The
exemption is deliberate and its reasoning is sound — a self-registered agent manages its own
execution and legitimately has no `Runner`. But it is written as `self_registered ⇒ unbound`, and
nothing enforces that: `self_registered = 1` with a non-null `runner_id` is reachable through two
ordinary API calls.

**Report-only.** Triggering one works — `run-c2b75b561127` completed normally on the bound runner —
because `trigger_agent_directly` reads `runner_id` directly. So the probe and the spawn disagree
about the same agent, and the probe is the one the operator sees.

The docstring above that line already records this bug's previous incarnation, fixed 2026-08-21,
which reported "a missing CLI named after the agent" for the unbound case. This is the same symptom
reached through the other branch of the same condition.

---

## F31 (B) — `_SECRET_VALUE_RE` redacts any 32-character identifier, including the Hub's own

**Status:** fixed 6b1013f

Same session. Transcripts render as:

```
TOOL: {"include": "full", "path": "spec/changes/<redacted>/spec.html"}
TOOL: {"max_results": 2, "query": "select:<redacted>,<redacted>"}
```

`runner_events._SECRET_VALUE_RE` is
`(aw_live_[A-Za-z0-9_=-]+|sk-[A-Za-z0-9_=-]+|[A-Za-z0-9_=-]{32,})`. The third alternative matches
**any** run of 32 or more word/hyphen characters. Measured:

```
41  <redacted>  <- spread-fairness-metric-fix-for-idle-staff
37  <redacted>  <- mcp__agentweave__submit_spec_document
32  <redacted>  <- mcp__agentweave__record_evidence
42  <redacted>  <- this_is_a_perfectly_ordinary_function_name
40  <redacted>  <- aw_live_58ab7d84a1bf7b34eb2d1b424875bacd
```

The Hub mints those document slugs itself from the title the agent chose, and it names its own MCP
tools. The rule is therefore guaranteed to fire on the Hub's own vocabulary whenever a title runs
long, and the operator loses precisely the identifier that says *which* document the agent read.

Real credentials are already caught by the two prefix alternatives, which is what makes the third so
costly: it removes legitimate content to catch secrets the first two have caught already.

---

## F32 (B) — an agent is told what it may do, never what it may not

**Status:** fixed b7136e6 + d04f9e9

Same session, and the clearest instance of a general shape.

`rev` was asked to review work and decide the evidence. It spent a full Codex turn — 97 recorded
output rows, a genuine review including running the suite twice and writing a hand reproducer — then:

```
Error calling tool 'decide_evidence': Hub rejected POST /spec/evidence/ev-.../decision (403):
{'message': "accepting evidence is the operator's, or an agent the operator has granted it.
 A project that has granted no agent still has the operator.", 'code': 'acceptance_not_granted'}
```

The refusal itself is good: correct, and it names who holds the authority. The problem is *when* it
arrives. `list_evidence` had succeeded moments earlier, so the agent could read the queue it was not
permitted to answer, and nothing in its canonical context said so.

The code knows. `agents.py:1321` carries the comment:

> A capability an agent does not know it holds is one it does not use, and one it guesses at is a
> 403 in the middle of a turn it has already spent. This is the `submit_spec_document` failure mode
> exactly: served, correct, and invisible.

The section it guards is then emitted **only when the grant is held.** Granting
`can_accept_evidence` did add "### You can decide evidence", correctly and helpfully, including the
self-review rule. The negative case emits nothing — so the stated principle is applied in one
direction, and the failure mode the comment names is the one that survives.

Consequence beyond the wasted turn: the reviewer, unable to record its verdict, wrote it to
`.reviews/review-0001-2026-08-25-0930.md` **inside its own worktree**, which is isolated by design.
The review's actual conclusion — "Ship it", with its checks — is on a branch nobody reads.

---

## F33 (B) — a job for an agent that does not exist is created, enabled, and scheduled

**Status:** fixed 96b54cd

Same session.

```
POST /projects/{p}/jobs {"name":"Ghost","agent":"nobody","message":"work","cron":"*/5 * * * *"}
-> 201, enabled: true, next_run set
```

There is no agent called `nobody`. Validation happens at fire time instead, where it is legible:

```
status: failed
error_summary: "nobody has no runner bound. Bind one via PATCH .../agents/nobody (runner_id)
                or the Hub UI before triggering."
```

So a typo produces a job that is enabled, scheduled, and fails every five minutes forever, filling
the history the operator is meant to read. Compare the neighbouring check on the same route, which
refuses a bad cron **at creation**:

```
POST .../jobs {"cron":"not a cron"} -> 400 "Invalid cron expression: Exactly 5, 6 or 7 columns..."
```

Both facts are checkable at the same moment; one is checked and the other is not.

The fire-time message is also slightly wrong: it says `nobody` *has no runner bound*, when `nobody`
does not exist at all. An operator would go looking for an agent to configure.

---

## F34 (B) — `agentweave --port N status` is silently ignored; `status --port N` works

**Status:** fixed 6b1013f

Same session, against a Hub confirmed live (`curl http://127.0.0.1:8010/health` → `{"status":"ok"}`).

```
agentweave --port 8010 status   ->  [HUB] Status: stopped
agentweave status --port 8010   ->  [HUB] Status: running (docker)
                                       URL: http://localhost:8010
                                       Projects: 5 registered (most recent: aw-sweep)
```

`--help` documents the **first** form — `usage: agentweave [--port PORT] ... {doctor,status,...}` —
and that is the one that lies. Neither errors, so the operator has no signal the flag went nowhere;
they are simply told the Hub is down while it is serving requests.

A second defect in the same three lines: the Hub on 8010 is a **native** `uvicorn hub.main:app`
process. It is reported as `running (docker)`.

`agentweave --profile beta --port 8010 status` also reports `stopped`.

`doctor` has the matching blind spot: from inside a project bound to the 8010 Hub it reports
`port:8000` available and checks `~/.agentweave/hub/data/agentweave.db`, neither of which is the Hub
this project uses. It returns `pass: 6  warn: 0  fail: 0` without examining the running instance.

---

## F35 (C) — `submit_spec_document` answers a malformed call with raw Pydantic errors

**Status:** fixed 29ab883, then reverted 78459e4 on the operator's call — the declared schema was preferred to the shaped refusal; closed by decision, not by repair

Same session. `author` called `submit_spec_document` **ten times** in one turn before it succeeded.
The refusals it was working from:

```
3 validation errors for call[submit_spec_document]
scope
  Input should be a valid dictionary [type=dict_type, input_value='The rota/allocate.py mod...', input_type=str]
  For further information visit https://errors.pydantic.dev/2.12/v/dict_type
```

then `11 validation errors`, then more. The agent was guessing at a nested schema from type errors
and a link to pydantic's website.

**The cost is the finding.** That turn recorded **718,650 input tokens** — every retry resends the
whole conversation — against 73,622 for the turn before it. One malformed call to one tool cost an
order of magnitude more than the work around it.

This is the same product that produces, elsewhere:

```
Cannot move a task from 'pending' to 'approved'. From 'pending' the available transitions are:
assigned, in_progress, rejected.
```

`task_transitions.refusal_detail` exists because *"a refused agent's only feedback is this string,
so it names both the current status and what is actually reachable — an agent told merely
'forbidden' retries the same call."* That reasoning applies unchanged here, and the tool carrying
the most complex payload in the surface is the one that does not follow it.

---

## F36 (C) — dependencies can only be declared by an agent, inside a spec document

**Status:** fixed d431385

Same session. `TaskDependency` rows are written in exactly one place in the codebase:
`spec_tasks.py:375`, reached only by `materialise()` when an approved document's task entry carries
a `depends_on` list of keys.

Neither `TaskCreate` nor `TaskUpdate` accepts dependencies — `PATCH` with `depends_on` is refused
`422 extra_forbidden` — and no router carries a dependencies route.

So an operator cannot say "B needs A" about two tasks they created, and the whole subsystem —
`dependency_gate.py`, the Dependencies board tab, `task_dependencies` and
`task_dependency_references`, `Task.dependency_state`, the `prerequisites`/`dependents` response
fields — is reachable only if an agent happens to author the right keys into a document that is then
approved. In this run the agent authored a five-task decomposition with no `depends_on` at all, so
the graph came out empty and the gate was never exercisable.

---

## F37 (C) — a document created by mistake is permanent, and becomes a standing warning

**Status:** fixed d431385

**S11 confirmed live**, three sessions after it was first suspected from reading the code.

`author` was given a conversation with `spec/changes/teal-manticore/spec.html` attached. It ignored
that document, called `create_spec_document` to make a second one, and wrote the specification
there. The first is now an empty orphan, and every exit is closed:

```
phase -> archived : 409 illegal_transition ("a document cannot move from exploring to archived")
phase -> approved : 409 illegal_transition
DELETE            : 405 Method Not Allowed
```

`archived` is reachable only from `approved`; `approved` only from `proposed`; `proposed` requires
requirements the orphan does not have. Every one of those rules is defensible on its own.

It is not inert: the Spec tab now carries a permanent `1 spec manifest drift item` banner for a
document nobody can remove.

The seam that created it is worth separating from the dead end it caused. The conversation carried an
attached document and the agent made a new one anyway. Nothing refused that, and nothing asked
whether it was meant.

---

## F38 (B) — an agent that needs an answer ends its turn instead of asking

**Status:** fixed 634d577, which could not fire until e2a4a29 (that gap is F41)

Same session, and the reason F32's shape matters.

`author`'s first turn read `rota/allocate.py` and `tests/test_allocate.py`, diagnosed the bug
correctly and unprompted, and then ended with:

> **What I need to clarify before writing the spec:**
> 1. **Interface — how does spread() learn about all staff?** …
> *Let me know your answers and I'll write the spec.*

Four well-judged questions. Asked as **chat text, in a turn that then completed.** No `Question`
row, no blocking, no task parked — `SELECT * FROM questions` was empty. The run was over, and the
specification was never written.

The agent was not underinstructed. Its charter names `ask_user` six times, including
*"Requirement ambiguity → `ask_user`. Do not guess; a guessed requirement is built on before anyone
notices"*. Told explicitly on the next turn to use the tool, it did so immediately and well.

So the mechanism works and the instruction exists; what is missing is anything making the tool the
path of least resistance at the moment the agent has a question. `CLAUDE.md` records that the
backstop which used to detect this — a completed run whose final text reads like a question — was
**retired on 2026-08-20 at the operator's request**, on the reasoning that guessing whether trailing
prose is a question is a judgement the product should not make on the operator's behalf. That
reasoning is sound. This is what it costs, measured: a capable agent, following a charter that told
it plainly what to do, produced a silently stalled turn on its first attempt.

Worth stating precisely, because the remedy is probably not the retired backstop. Nothing here
requires guessing at prose. The Hub already knows the run ended, that it was the first turn against
a document in `exploring`, and that no `Question` row was written.

---
---

## F39 (B) — two of the three operator grants are announced in neither direction

**Status:** fixed b7136e6 + d04f9e9

**Found 2026-08-25 while fixing F32**, by the audit its own remediation task called for
(`the-seams-of-the-sweep`, task 3.3) rather than by driving the product.

F32 was that `can_accept_evidence` is announced to an agent **only when granted**. Fixing it meant
looking for the same one-directional shape elsewhere. What the audit found is worse in one respect
and narrower in another.

`GRANT_FIELDS` (`hub/hub/api/v1/agents.py:1633`) is the complete set of boolean capabilities the
operator confers:

```
can_read_checkpoints
can_recall
can_accept_evidence
```

Only the third appears in canonical turn context at all. `can_read_checkpoints` and `can_recall`
are announced **neither when granted nor when withheld** — grep for either name in the context
builder returns nothing.

So F32's own reasoning, quoted from the comment three lines above the section it guards, applies to
these two in the granted direction as well:

> A capability an agent does not know it holds is one it does not use, and one it guesses at is a
> 403 in the middle of a turn it has already spent.

An agent granted `can_recall` and never told it holds recall will not use recall. The operator
turned something on and nothing downstream says so. That is the *first* half of the sentence, and
it is the half F32 did not have to deal with — `can_accept_evidence` at least announced itself when
granted.

**Not yet driven, and that matters.** F32 was measured: a 97-row turn, a real review, a 403 at the
end, and a verdict stranded in a worktree. This one is read from the code. Whether an agent granted
`can_recall` actually fails to use it, or discovers the tool from the surface anyway, has not been
observed — which is exactly the question F21 is about, and the reason this is recorded rather than
fixed alongside F32.

The remedy is probably not three more hand-written sections. Two of these three grants gate *tools*
(`recall`, and checkpoint reads), so the general form is likely "the tool surface states what this
agent may call, in both directions" — F21's territory. Recorded separately so that whoever settles
F21 knows this is part of the same question.
---

## F40 (B) — `test_relocate_repairs_and_redrains_queued_work` is flaky, and has been all along

**Status:** fixed d916861

**Measured 2026-08-25**, while verifying an unrelated change. Not a product defect — a defect in
the suite that guards the product, which is worth the same attention because it is what decides
whether a red run gets believed.

`hub/tests/test_project_workspace_unavailable.py::test_relocate_repairs_and_redrains_queued_work`
fails intermittently. Measured on its own file, nothing else running:

```
run 1   7 passed
run 2   1 failed, 6 passed      <- same test
run 3   7 passed
```

**And it is not new.** The same file, with the three Group 5 source changes stashed so the tree was
clean:

```
7 passed / 7 passed / 7 passed / 7 passed / 1 failed, 6 passed
```

One in five on an unmodified checkout. It surfaced here only because this session ran the full Hub
suite six times in a day, which is more consecutive full runs than the suite normally gets.

**The likely mechanism**, from reading the test rather than instrumenting it. The test drains a
queue through `POST /relocate` and then awaits the background work it started:

```python
for task in list(agent_trigger._background_runs):
    await task
```

That snapshots the set at the moment the loop runs. A run the redrain schedules but has not yet
registered is not in the snapshot, so the assertions below it — exactly one other run, and that run
`completed` — are evaluated against work still in flight. Nothing in the test waits for the
redrain to have *finished scheduling*, only for whatever happened to be scheduled already.

If that is right, the fix is a condition rather than a snapshot: wait until the expected run exists
and is terminal, with a bounded timeout, instead of awaiting whatever set membership happens to
hold at one instant. The same `_background_runs` idiom appears in other tests and is worth checking
for the same race.

**Why it matters beyond one red run.** A suite with a known-flaky test trains its readers to re-run
rather than to read, and this one guards workspace relocation — the repair path for a project whose
directory moved. A real regression there would look exactly like the noise.

Left unfixed here deliberately: it is not part of the sweep remediation, and changing a test's
synchronisation while shipping six other changes would make a genuine failure harder to attribute.
Recorded so the next full-suite red run is read correctly rather than dismissed *or* chased.

## F41 (A) — F38's fix cannot fire: every document has a `content_digest` from birth

**Status:** fixed e2a4a29, verified 71e6646

Found 2026-08-25 during the live re-drive of `the-seams-of-the-sweep`, which is precisely what a
re-drive is for: the fix is unit-tested six ways and green, and does nothing in production.

`note_turn_that_produced_nothing` (`run_divergence.py:288`) gates on the document having no content:

```python
if document is None or document.content_digest:
    return False
```

The docstring explains the intent — *"`content_digest` is the digest of what was last submitted, so
its absence is 'nothing has ever been written here'"*. The premise is false. **No creation path
leaves it absent.** Both routes create the row and then immediately write a scaffold payload:

- `api/v1/spec.py:1319` `create_document` → `spec_lifecycle.create_document` (digest null) →
  `spec_service.save_document(payload)` → `record_content` → `content_digest = digest(content)`.
- `api/v1/agent_actions.py:1094` `create_spec_document` — the agent's own tool — does the same.

Measured on the live beta database: **50 spec documents, 0 with a null or empty `content_digest`.**

The clinching evidence is the original F38 subject itself. `spec/changes/teal-manticore/spec.html`,
the document `author` was given and never wrote, carries digest `da8c2bb9…` and this event log:

```
created  operator  2026-08-25 08:15:40.650773  {"path": "spec/changes/teal-manticore/spec.html"}
content  operator  2026-08-25 08:15:40.650773  {"requirements": []}
phase    operator  2026-08-25 08:16:08.128281  {"explore_closed": true}
```

The `content` event lands in the *same microsecond* as `created`. So the check written to catch that
turn would have returned `False` on that turn.

**Reproduced live rather than argued.** A document was created (`spec/changes/jade-kelpie/spec.html`)
and `dev` was triggered against it with `spec_document` set and instructions to reply in prose only:

| Precondition | Required | Actual |
|---|---|---|
| run ended with no task | yes | `run-5f5039d40de7`, `task_id = NULL` |
| inbound entry names a document | yes | `entry-2652466231e4` → `spec/changes/jade-kelpie/spec.html` |
| run wrote no question | yes | `SELECT COUNT(*) FROM questions WHERE created_by_run_id = …` → 0 |
| document has no content | yes | `content_digest = 2b43163d…` — **fails here** |

`SELECT COUNT(*) FROM event_logs WHERE event_type='turn_produced_nothing'` → **0**. Every condition
the finding describes was met and nothing was recorded.

The six tests in `test_turn_produced_nothing.py` pass because `_setup` constructs a `SpecDocument`
row directly with `content_digest=None` — a state the product never produces. This is the same class
of defect as the two tests F27 and F37 found pinning bugs in place: the fixture asserts a world the
code does not build.

**The reachable signal is one column over.** The scaffold write records `{"requirements": []}`, so
`requirement_digests` is `{}` for a document nothing has been written into, and non-empty once an
agent submits one. On the live jade-kelpie row: `requirement_digests = '{}'`. That is the honest
expression of "nothing has ever been written here", it is state rather than prose, and it keeps
every other property of the design intact — including the rule that the agent's text is never read.

---

## F42 (C) — F27 bounds the blast radius but a run can still claim work it will not do

**Status:** open (no fix commit references it)

Noted 2026-08-25 during the same re-drive, and **not a defect in the fix** — it is the documented
consequence of Key decision 1, recorded so it is not mistaken for an oversight later.

`_guard_run_holds_the_task` refuses `-> completed` from a run that holds nothing, which is what the
live check confirmed. It does not refuse `-> in_progress`: claiming *binds*, deliberately, because
that is what keeps the Developer charter's "go find waiting work" a real behaviour. So the sequence
`pending -> assigned -> in_progress -> completed`, which is exactly what the F27 transcript shows an
agent reasoning its way into, still succeeds — the run simply binds on the way through.

What changed is the size and the attributability of the harm, and both matter:

- A run carries **at most one** binding, so the measured F27 instance — one run closing four
  unrelated tasks, a second taking two more — is no longer reachable. The ceiling is one task.
- The completion is now attributable to a run that took the task, so the run boundary checks it and
  `run_divergence` has something to reason about.

Closing the remainder would mean requiring evidence at `-> completed`, which
`requirement_gate`'s docstring explains would deadlock the ordinary path — evidence is accepted
after review and review follows completion. Recorded, not proposed.

---

## The live re-drive, 2026-08-25 — what the fixes did against a running Hub

Task 8.6/8.7. Everything above was unit-verified when it shipped; this is the same set driven
against the trial Hub on port 8010 after restarting it on the new code, in project
`proj-bacb623ca9ba` (`aw-sweep`). `GET /health` returning `{"status":"ok","runtime":"native"}` — the
`runtime` field is new in this change — is what confirms the restart took.

`job-e2c18b2d` ("Hourly test check", 36 firings) was **disabled first**, at the operator's
direction, so nothing fired on the new code during the drive.

| Finding | Verified live | How |
|---|---|---|
| **F27** (A) | **Yes, by a real agent** | See below. |
| **F28** (B) | **Yes** | The flow's queue was `{}` with all five tasks carrying `loop_id = NULL`. Re-declaring the document (`PATCH .../jobs/job-ccb60a3cb3f6`, `spec_document_id: spdoc-3e0dbec860d0`) adopted every one: `{"approved": 2, "completed": 2, "under_review": 1}`. |
| **F29** (B) | **Yes, both surfaces and both directions** | Appending a byte to an approved document made the listing report `diverged: true` and the single read carry recorded/found digests plus the detail. Restoring the file cleared it — content-keyed, not a sticky flag. A `touch` with identical bytes stayed `false`, which is Key decision 5's whole point. |
| **F30** (B) | **Yes** | `architect`, `builder` and `critic` still carry `self_registered = 1` **with** a non-null `runner_id` — the reachable state the finding describes. All three now report `runnable: true` on their real runner instead of `runner=native cli=architect runnable=False`. The probe and the spawn agree. |
| **F31** (B) | **Yes** | All four measured false positives pass through intact (`spread-fairness-metric-fix-for-idle-staff`, `mcp__agentweave__submit_spec_document`, `mcp__agentweave__record_evidence`, `this_is_a_perfectly_ordinary_function_name`); all three credential shapes still redact. Exercised against the module, not a rendered transcript. |
| **F32** (B) | **Yes, both branches** | `dev` (withheld) receives `### You cannot decide evidence` with the three lines including where a verdict goes instead; `rev` (granted) receives `### You can decide evidence`. |
| **F33** (B) | **Yes** | `POST /jobs` with `agent: "nosuchagent"` → **400**, *"agent 'nosuchagent' is not one of this project's agents, so this job could only ever fail. On the roster: author, dev, probe, rev."* Refused at creation instead of failing silently every cron tick. |
| **F34** (B) | Yes, previous session | `status`/`doctor` against port 8010 and profile `beta`. |
| **F35** (C) | Module level | The refusal named the field, the shape and a working example, one at a time. **Then reversed at the operator's direction** — see below. |
| **F36** (C) | **Yes, every path** | `201 added`; cycle → **409** naming both tasks; self-edge → **400**; unknown id → **404** naming both; a repeated edge → **201 `duplicate`**, which the route documents as deliberate ("an operator who clicks twice has not made a mistake"); `DELETE` → **204**. |
| **F37** (C) | **Yes** | `spec/changes/teal-manticore/spec.html`, in `exploring`, archived successfully with `tasks_created: []`. This was a hard refusal before. `GET /spec/drift` is now empty. |
| **F38** (B) | **No — and that is the finding.** | See F41. Fixed here, and the fix re-driven live: the same scenario now records `turn_produced_nothing`. |

### F27, driven by a real agent rather than asserted

The sharpest result of the drive. `task-326f5f62de51` was created, moved to `in_progress` **by the
operator** so that no run held it, and `dev` was triggered with instructions to call
`update_task(task_id, "completed")` and report the result verbatim. It did, and got:

```
Hub rejected PATCH /tasks/task-326f5f62de51 (403): This run cannot complete task
task-326f5f62de51: it is not working any task. A run finishes the task it took, and takes at
most one. To work this task, start a run bound to it — or, if you meant to report on work you
did not do, say so rather than moving its status.
```

The task stayed `in_progress`; `run-041af4d5a3f8` ended with `task_id = NULL`, having never bound.

The old behaviour is preserved in the same agent's earlier transcript rows, which is as close to a
controlled before/after as this gets — an unbound run walking two tasks `pending → assigned →
in_progress → completed`, reasoning aloud: *"these tasks aren't assigned to me... I should assign
them to myself first, mark them as in_progress, and then complete them."* That is F27's exact path,
and it succeeded then. See **F42** for what that reasoning can still achieve, and why.

### What the drive found that unit tests had not

**F41 (A)** — F38's fix cannot fire. Found by driving the case rather than reading the code, then
confirmed against the original subject's own event log. Recorded above, and fixed.

**The fix was then verified the same way it was found**, which is the whole point: a defect whose
lesson is *"the unit tests said yes and production said no"* must not be closed on unit tests alone.
The Hub was restarted on the fix and the identical scenario re-run — a fresh document
(`spec/changes/sapphire-unicorn/spec.html`, `content_digest` populated at creation exactly as
before), `dev` triggered against it with `spec_document` set and told to reply in prose only:

```
turn_produced_nothing   dev   severity=warning
{"run_id": "run-4c14c8077442", "agent": "dev",
 "spec_document": "spec/changes/sapphire-unicorn/spec.html",
 "document_phase": "exploring", "run_exit_status": "completed"}
```

`run-4c14c8077442` completed with `task_id = NULL`, wrote 0 questions, and the document carried
exactly 1 `content` event — the scaffold. Before the fix this produced **nothing**.

The negative cases — a turn that asked, a turn that wrote the document, a turn given no document —
are covered by unit tests only; each would have cost another real run to drive, and none of them was
the case that was broken.

### Dispositions the operator made on 2026-08-25

- **F22** — fixed. `doctor` gained `check_symlink_privilege`, which probes a directory symlink and,
  on this machine, reproduces `WinError 1314` and names the one setting that fixes every worktree
  at once. A warning rather than a failure: the Hub runs correctly without it.
- **F24** — fixed. The run row leads with its own status, coloured by `runStatusColor`, and keeps
  the trigger as a muted qualifier. A refused firing now reads `skipped scheduled`, which is what
  both user test guides tell the operator to look for.
- **F25** — fixed. A `n refused` chip beside `0 runs`, drawn from the history the card already
  holds. Neither count was wrong; naming the refusals is what makes the two agree.
- **F26** — fixed at the source, not in the renderer. `current_tasks[].agent_role` now says which
  of `working`, `next` or `assigned` the name means, because the merge that produces it is the only
  place that still knows — by the time the board sees the name, in-flight work and a firing's
  selections are indistinguishable. The card renders `next: relay` for a completed task's
  prospective reviewer and the bare name, unchanged, for an agent mid-turn.
- **F35** — **reversed.** The seven `submit_spec_document` fields advertise `object`/`array` again.
  `_check_submit_shapes`, `_SUBMIT_SHAPES` and `MalformedCallError` were removed with them rather
  than left in place: the framework validates before the body runs, so with the annotations
  restored nothing could ever have reached them. Leaving them would have created a second F41 in
  the same session that found the first. `test_the_structured_fields_advertise_their_shape` holds
  the choice, and the parameter list records what reversing again would take.
- **F39** — fixed, **and verified live in both directions.** `recall(observation_id)` now carries
  the same grant caveat `decide_evidence` already had, and an `### Other agents' history` section
  states both checkpoint grants in both directions. Against the restarted Hub: an ungranted agent
  reads *"You may read your own checkpoints and no one else's"*; granting both to `rev` switched it
  to *"You may read your peers' checkpoints"* immediately, and withdrawing them switched it back —
  so the operator's switch is reflected in what the agent is told, which is the half
  `test_the_operator_grants_it_and_reads_it_back` exists to protect for the evidence grant. Stated even when both are withheld, which is the half worth defending: `recall`
  answers **not-found** rather than refusing — it has to, or the refusal would itself confirm the
  record exists — so an agent that meets the boundary without being told concludes the record is
  missing rather than that it is not permitted to see it.
- **F40** — **largely fixed, and the cause was not what the finding guessed.** Recorded in full
  because the diagnosis is the useful part.

  The finding proposed that `for task in list(_background_runs): await task` snapshots the set and
  so misses a run scheduled but not yet registered. That is true and it is fixed —
  `_settled_redrain_runs` drains and re-checks until the state the test asserts on actually holds,
  with a bounded deadline that names the run statuses it gave up on. But replacing the snapshot
  alone did **not** make the test green; it made it fail *deterministically* under load, which is
  how the real cause surfaced.

  Running this file immediately after `test_conversation_contract.py` failed every time, with
  `assert 2 == 1` — **two** runs on one conversation, both `failed`, where the isolated run was one
  and `completed`. The cause is the scope of the `PtySession.spawn` patch: the redrain starts its
  run as a background task that spawns *after* the request has returned, and the patch closed at
  the end of the request. Lose that race and the run reaches the real `PtySession.spawn`, fails for
  want of a `claude` binary, and the product then does exactly the right thing —
  `return_run_entries` puts the entry back and a second run picks it up. Two failed runs where the
  test asserted one completed one. Awaiting the settle inside the patch closes it.

  **Measured after both changes:** the deterministic repro is green, and 24 of 25 runs of the
  four-file combination pass, against 4 of 5 before. A full-suite run also went green at
  3103 passed. **One failure in 25 remains and its message was not captured** — the dominant cause
  is fixed and a residual race is not ruled out, so a red run here still deserves reading rather
  than dismissing.

  Two things worth carrying: a narrowly-scoped `patch` around a call that schedules background work
  is a bug of the same shape wherever it appears, and the snapshot idiom itself still survives in
  `test_accounting_budget.py:191` (`test_conversation_contract.py` and `test_agent_trigger.py`
  already loop on the set and are not exposed the same way).

---

## What held, under a full-surface sweep

Recorded because a report listing only defects describes a product that does not exist. Each of
these was driven, not read.

- **The task transition machine.** Every illegal jump refused `409` with a string naming what *is*
  reachable. Every non-entry creation status refused `422` naming the two that are legal. No refusal
  needed a second call to interpret.
- **The requirement gate, at `gate` rigor.** Refused approval, named the requirement, its state, the
  remedy, and the alternative: *"Satisfy them, or lower the document's rigor — which is recorded."*
- **The whole spec → work → evidence → merge chain.** An agent read an approved document, edited in
  its own worktree, ran the suite, and recorded evidence carrying a git footprint with
  `reachable_from_main: false`. A second agent **on a different CLI** reviewed it. Accepting the
  evidence moved coverage to `verified`; approving the task merged `75ebebce` into `master`.
  Verified independently: the fix is correct (old `spread` = 0 on the idle case, new = 2), the suite
  went 6 → 7, and `master` carries the change.
- **`ask_user`.** Two blocking questions, batched, with structured options; the run held open;
  answering released it. Exemplary — see F38 for the half that is not.
- **Permission postures.** `manual` produced a card showing the exact command. Denial by timeout was
  honoured (`expired`, file absent). Explicit approval let the command run and the file appeared.
- **One run per agent.** Two simultaneous triggers: one `running`, one `queued` with
  `waiting_reason: "agent is already running"`. The second ran when the first finished.
- **Stopping a run.** `stopping` → `stopped`, cleanly, mid-flight.
- **`repo_hygiene`.** Wrote five ignore rules into `.git/info/exclude` of a repository the Hub did
  not create. (`.agentweave/project.json` is not among them, and is machine-local — worth adding.)
- **The dashboard.** All thirteen screens rendered with **zero console errors**. Empty board columns
  explain what would land in them. A task that could not merge said exactly why — *"no accepted
  evidence names a commit, so there is nothing to merge"* — and offered `Try again`.

---

## F43 (A) — the flow tells every agent to brief its reviewer, and no flow path delivers it

**Status:** fixed 488d92f, verified live 52d98aa and 97db33f

Found 2026-08-25 while staging group 11's task 11.3, which handoff 0086 recorded as *"not
answerable from this drive: no checkpoint was generated."* It is not answerable because it
**cannot** be, and the reason is structural rather than a gap in the drive.

This is F41's shape a second time: every link works, the tests pass, and the path cannot fire.

### What the product promises

`_compose_loop_briefing` (`scheduler.py:1522`) tells every agent in a flow:

> **Finish the task below and stop.** … Record what a reviewer will need (see
> `submit_checkpoint_notes`); somebody else reads it.

Nobody else reads it. Nobody can.

### The chain, and the link that is missing

1. The agent calls `submit_checkpoint_notes`. `api/v1/agent_actions.py:348` writes one
   `CheckpointNote` scoped to **the author's conversation** and returns `recorded: true`.
2. A `CheckpointNote` is an input to checkpoint generation, never a readable artefact — its own
   docstring: notes *"are consumed by that conversation's next checkpoint"*. Nothing else in the
   Hub reads the table.
3. `generate_checkpoint` consumes them (`pending_notes`, `checkpoint_generation.py:454`) and stamps
   `Checkpoint.loop_id` from `loop_for_conversation` (`:448`). Correct, and load-bearing.
4. `latest_checkpoint_for_loop(loop.id)` finds it, and `_compose_loop_briefing` renders it under
   `## Prior checkpoint`. Also correct.

Every one of those works. What does not exist is a trigger. `generate_checkpoint` has exactly two
callers:

- `output_recording.py:230` → `consider_from_reading`, which fires on a **context-usage
  threshold**; and
- `api/v1/checkpoints.py:175`, an **operator button**.

A flow firing is `session_mode: new`, one small task, and then that conversation never runs again.
Its context never approaches a threshold, and no operator presses a button per handover. So no
checkpoint is generated, the notes are never consumed, and `latest_checkpoint_for_loop` returns
`None` on every firing the flow will ever have.

### Measured on the live database, not argued

| Query | Result |
|---|---|
| `select count(*) from checkpoint_notes` | **3** |
| …`where consumed_by_checkpoint_id is null` | **3** — all of them |
| `select count(*) from checkpoints` | 6 |
| …`where loop_id is not null` | **0** |

All six checkpoints belong to conversations with no `job_run`, so their null `loop_id` is correct —
checkpoint generation itself is not broken, it has simply never once run inside a loop. And all
three notes come from `loop-e4b864459808`, the Ledger flow, written by **all three** of its agents.

### The agents did their part, and the note proves task 6.5 worked

The instruction landed. `note-e8cf4afcb4b1`, written by `builder`, is about
`task-23a0986e7fe9` — the exact task `critic` is queued to review:

> Task task-23a0986e7fe9 "Refuse an entry with no postings": The code implementation is already
> correct. Entry.balances() on line 20-21 of ledger/book.py already returns False for empty
> postings…

That is a note written *for somebody else*: it names the task, the file, the line and the finding,
and it is not notes-to-self. **This is the artefact task 11.3 asks the operator to judge, and it
already answers the question it was written to raise.** What fails is delivery, not authorship —
which inverts the check: 11.3 was framed as "if the checkpoint reads as notes-to-self, task 6.5 did
not work", and 6.5 demonstrably did.

### Why the suite is green

`test_scheduler.py:1408`, `test_loop_briefing_includes_a_prior_checkpoint_in_full_under_the_cap`,
builds its subject with `_make_checkpoint(db, loop_id=loop.id, …)` — a `Checkpoint` row inserted
directly with the column already set — and then asserts the briefing renders it. It never exercises
anything that would *produce* such a row, and in production nothing does. This is verbatim the
lesson F41 ended with: **the fixture builds what the product does not build.**

### What would close it

The missing trigger belongs at the handover, which is the moment the product already treats as
significant: a flow task reaching `completed` with a reviewer to be staffed. Generating the
author's checkpoint there consumes the pending notes and stamps `loop_id`, and every downstream
link already works.

It is not free — generation is a real model call, measured at ~19s, and a flow that hands over
often pays it often. That is an operator decision about spend, and it needs `checkpoint_runner_id`
on the project, which `ledger-stress` does not have set (so even the operator button refuses today,
409). Recorded rather than fixed; see F44, which has to be settled in the same breath.

---

## F44 (B) — the reviewer is briefed by the loop's newest checkpoint, not the author's

**Status:** fixed 488d92f, verified live 52d98aa

Same reading, and it only bites once F43 is fixed — which is why it is recorded now rather than
discovered afterwards.

`latest_checkpoint_for_loop` filters on `loop_id` alone, orders by `created_at desc`, and takes
one. No author, no task. `_compose_loop_briefing` uses that single value for **every** turn,
including a review turn (`scheduler.py:2453`), and the review path adds no author content of its
own — `prepare_review_turn` supplies the commit, the evidence id, the branch and the checkout, all
mechanical.

That identity held for the design it was written for. Its docstring reasons about *"a loop's next
firing"* — in a one-agent loop the newest checkpoint **is** the previous firing's, so "latest for
the loop" and "the author's" are the same row. A flow breaks the identity: with three agents
working concurrently, the newest checkpoint is whoever finished last, and the reviewer of task X
can be briefed with an unrelated agent's account of task Y while being told it is what a reviewer
will need.

The live notes show the collision already forming — three notes on one loop from three different
agents, of which exactly one (`note-e8cf4afcb4b1`) concerns the task actually queued for review.
Had F43 been fixed alone, two firings in three would have briefed the reviewer with the wrong
author's work.

Any fix for F43 therefore has to select the checkpoint by **the author of the task under review**,
not by recency within the loop.

**Both fixed 2026-08-25** (`loop-becomes-a-flow` group 14, design D17), in one change because F44
only exists once F43 works.

The trigger is the **run boundary** — `checkpoint_handover.consider_handover`, dispatched beside
`evaluate_run_end` at both runners' call sites and never awaited on them. A flow agent's
conversation is finished when its run ends, which makes that the author's handover and the moment
their notes are complete. Generating at review *dispatch* instead was rejected on mechanics: the
briefing is composed ~20 lines later in the same firing, so it would block the scheduler for ~19s
or race it and lose.

Gated on the agent having actually recorded notes — the operator's decision the same day. Spend
stays proportional to agents doing what the product asked, and a silent agent produces no briefing,
which is no worse than before the fix.

F44 closes with `checkpoints.checkpoint_by_task_author`, resolving through the transition history,
reached from `scheduler._briefing_checkpoint` — the single place both firing paths ask the question,
where `is_review` is the whole difference between "what did the author of this task leave me" and
"what did this loop last do".

`hub/tests/test_handover_briefs_the_reviewer.py`, 10 tests, **both halves causally confirmed**:
disabling the F43 trigger fails 5 of 10, disabling the F44 selector fails exactly 1. The module
never inserts a `Checkpoint` for an F43 assertion — it drives the trigger and asserts on what it
produced, because inserting the row is exactly how the pre-existing briefing test stayed green
while nothing in production could produce one.

**The first implementation could not have fired, and the live database is what said so.** Recorded
here rather than as a new finding because it never shipped — but it is the fourth instance of this
change's dominant failure mode, and the first one caught *before* a push:

- gate 1 required `run.task_id`; **6 of the 10 live runs with a `completed` transition have it NULL**;
- gate 2 looked for notes in the completing conversation; **0 of 4 stranded notes are there**,
  because `session_mode: new` gives every firing its own conversation and a task spanning two
  firings splits its notes from its completion as a matter of course.

Both gates passed ten green tests, because the fixture put the note and the completion in one
conversation and set `task_id`. The fixture now matches production on both, and narrowing either
gate back fails 5 of 10 where previously it failed none.

**Not yet re-verified live.** `ledger-stress` has no `checkpoint_runner_id`, so nothing generates
there until the operator chooses which CLI is billed.

**Positively verified live 2026-08-26, Q4 retry (5th live attempt, across two iterations).** Four
prior live firings — two on `ledger-stress`'s flow job (blocked by F52's git refusal before either
reached `submit_checkpoint_notes`) and two on its "Ledger flow" loop (one confused between two
similarly-titled tasks and completed neither; one completed its task but never called the tool
despite the flow briefing instructing it to) — never produced a positive sample, so the run-boundary
hook stayed covered only by unit tests and code reading, exactly as handoff 0088 flagged. A fifth
attempt changed the shape rather than repeating it: a minimal **non-flow** loop (`job-525b85035aaf`
/ `loop-b920a216f57c` on `proj-8605b92d0028`, no `spec_document_id`), one unambiguous
`initial_tasks` entry, and a `job.message` making `submit_checkpoint_notes` an explicit required
first step before any code edit. Fired once (`POST .../run` → `run-736d9e1f2cd3`, agent
`loopauthor`, Haiku). The agent called the tool, then made the change, then completed the task in
the same turn — confirmed from rows: `task_transitions` shows `assigned→in_progress→completed`
all attributed to `run-736d9e1f2cd3`; `checkpoint_notes` row `note-7c7ef8892644` was written in
`conv-a7f22c12da79` (this run's own conversation) and its `consumed_by_checkpoint_id` is
`ckpt-42c9362f7ba4`; that checkpoint's own row reads `loop_id: loop-b920a216f57c` (non-null),
`covers_through_run_id: run-736d9e1f2cd3`, `status/probe_status: ready/passed`; its `body` names the
task, the note's own risk content ("existing tests may already be passing invalid negative prices"),
and next actions for a successor — the briefing genuinely carries the author's note, not a
placeholder. The underlying code change itself is real, not just claimed: `run.snapshot_commit_sha`
`e4a4ae9d...` shows a real `Auto-snapshot: loopauthor's turn` commit touching `inventory.py` and
`test_inventory.py`. Handoff 0088's residual-risk note is retired: the run-boundary checkpoint hook
has now fired for real, end to end, with every claim backed by a row id. Job disabled and archived
immediately after (`job-525b85035aaf`, `archived_at` set); all jobs project-wide re-swept to
`enabled: 0` afterward.

Whether the earlier four attempts' unreliability is flow-briefing-specific (spec-document-flow
briefings carry a lot more competing instruction than this minimal loop's did) or was mostly bad
luck on cheap-model tool-call discipline was not conclusively separated — this sample used a
shorter, single-purpose message and got a clean result on the first try, which is suggestive but is
one data point, not a controlled comparison. Worth a note for Q6/future drives rather than a closed
question.

---

## F45 (A) — a review that ends without moving the task is re-staffed on every tick, forever

**Status:** fixed fec52d1

Found 2026-08-25 while checking whether the Ledger flow could safely be re-enabled to stage group
11's remaining checks. It cannot, and the reason is a live spend loop.

### The rule

`decide_firing`'s queue walk has two branches. For **ordinary work** it checks `task.assignee`
first, so a task already staffed is *resumed* rather than re-staffed (`scheduler.py:1133`). For
**finished work** (`scheduler.py:1182`) there is no equivalent: it resolves the author, walks the
reviewer ladder, and selects. Nothing anywhere asks whether this task has already been reviewed, or
by whom.

The design intends the task's own status to be that marker. `REVIEWABLE_STATUSES` is exactly
`{"completed"}` — `under_review` sits in `BAND_WITH_REVIEWER` and is deliberately excluded. So a
reviewer is expected to move `completed -> under_review`, and that transition is the only thing
that takes the task out of the selection pool.

Nothing enforces it, and nothing notices when it does not happen.

### What happened live

`critic` was staffed to review `task-23a0986e7fe9` (author `builder`, commit `f10d198`). It ran —
`run-d4926120b8c2`, status `completed`, exit 0, 2026-08-25 00:11:32 — and did the work: its note
`note-2059dd9b1488` reads

> Reviewed builder's implementation for task-23a0986e7fe9 (Refuse an entry with no postings) at
> commit f10d198. Code and tests are correct and complete. Ready for operator to accept evidence
> ev-6e7f3bc72c24.

It then left the task in `completed` and the evidence in `awaiting`, deferring the decision to the
operator — which is a defensible thing for a reviewer to do, and `decide_evidence` being available
to agents does not make it obligatory.

The consequence is not defensible. The task is still `completed`, so it is still in
`REVIEWABLE_STATUSES`, so the ladder still resolves `critic` for it. **The product's own board says
so:** `GET /jobs/job-bdea22bb0308` returns `current_tasks` containing

```
{"id": "task-23a0986e7fe9", "status": "completed", "agent": "critic", "agent_role": "next"}
```

and the board derives that from this same walk (the comment at `scheduler.py:1143` that F23 left
behind says exactly that). This is not a prediction about what the next firing would do — it is the
next firing's decision, already made and already displayed.

Re-enabling the flow re-runs a review that has already been performed, reaches the same conclusion,
changes nothing, and does it again five minutes later.

### Why it matters more than one wasted turn

The flow's stop conditions cannot end it. `stop_when_queue_empties` is set, but the queue never
empties: a task stuck in `completed` is not terminal, so the loop considers itself to have open
work forever. The only bound is the project's token budget, which is `null` here.

That lands directly on the check the guide calls the one that decides whether a flow can be left
unattended (test guide section 6, task 11.6). A flow in this state spends indefinitely on a
conclusion it already reached, and every tick looks *healthy* — a turn ran, an agent was named,
no notice was raised. Nothing distinguishes it from progress.

### Where a guard belongs

The reviewer ladder is the wrong place — it answers "who", correctly. The selection is the place:
finished work whose most recent review turn ended without moving the task out of `completed` has
been reviewed, and re-offering it to the same agent tells the operator nothing new. Either the
task leaves the pool and the flow raises the operator-facing notice it already has vocabulary for
(rung 3's "could not staff this step" is the wrong words, but the right surface), or a review turn
that ends without a transition is itself the recordable outcome.

Not fixed. It interacts with F43 — both are about a handover that completes without producing the
artefact the next step depends on — and the two want deciding together.

---

### F45 — fixed 2026-08-25, and diagnosing it found F46

Fixed inside `loop-becomes-a-flow` (group 13), on F41's precedent: a defect in the change's own
delivery, the change unarchived, and the one thing standing between a supervised flow and one that
can be left running.

**The fix is the missing half of a rule that already existed.** Ordinary work is *entered* — the
firing moves `pending -> assigned` and writes the assignee in the same commit that queues the turn.
Review work was selected but never entered, so it stayed in `completed`, which is exactly
`REVIEWABLE_STATUSES`. `scheduler._enter_selected_task` now states both halves, and a review enters
at `completed -> under_review`.

Two consequences found by running it rather than by reasoning, both of which would have been
regressions worse than the bug:

- **Widening `_loop_candidates` was not optional.** With `under_review` outside the candidate query
  the walk could not see the task at all, and a queue holding one dispatched review returned
  `stalled`, reason *"no claimable task among 1 open (1 under_review)"*. That is finding F23 exactly,
  one band over — a flow reading as dead while its review runs.
- **An explicit branch in `decide_firing` was not optional either.** `under_review` is absent from
  `REVIEWABLE_LOOP_TASK_STATUSES`, so the widened walk fell into the **ordinary-work** arm, found the
  reviewer sitting in `assignee`, and re-staffed the review with no `is_review` — firing the reviewer
  into its own worktree with no checkout of the commit under review. That is **finding F10 arriving
  by a new route**, and it is worse than the loop being fixed.

`hub/tests/test_review_leaves_the_pool.py`, 9 tests, **5 confirmed failing against the unfixed
code**. The four that still pass are the set-shape assertions and the ordinary-work path, which is
the correct split rather than a gap.

**Not claimed closed.** Task 13.6 is live re-verification against the trial Hub, unticked. F41 is
this change's own precedent for a fix that passed six unit tests and could never fire.

---

## F46 (B) — the review turn named a transition the task could not make

**Status:** fixed fec52d1

Found 2026-08-25 while fixing F45, and it is why no reviewer had ever moved a task rather than
merely why one reviewer did not.

`TRANSITIONS` gives `completed` exactly one agent-legal edge: `under_review`. The review turn's
context (`api/v1/agents.py`) told the reviewer:

> Do not fix what you find. Report it. The author makes the change, through `revision_needed` — a
> reviewer that edits the work has reviewed its own work.

`revision_needed` is **not reachable from `completed`**. A reviewer that followed the instruction
literally was refused by the transition machine. And a reviewer that found the work *correct* was
given no exit at all — the context said what to do about work that is wrong and nothing about work
that is right.

**Measured, not inferred.** Across the whole trial database, every task that ever reached
`under_review` got there by the operator or by `Architect` in an older non-flow project. **No
flow-dispatched review has ever recorded a transition.** `critic`'s review of `task-23a0986e7fe9`
is the representative case: it ran to completion, wrote a note concluding *"Code and tests are
correct and complete. Ready for operator to accept evidence ev-6e7f3bc72c24"*, and moved nothing —
which was the only thing it could do.

So F45's loop was not a reviewer being lazy. It was the product asking for something it had made
impossible, and then re-asking every five minutes.

**Fixed by F45's fix, plus one line.** Entering the review at `under_review` makes both verdict
edges legal; the context now names both, and says that leaving the task where it is ends the turn
without a review having happened. The wording alone would not have been enough — that is the point
of recording this separately.

---

## F47 (C) — the flow's own routing is recorded as the operator's

**Status:** open — deliberately not fixed in F45's change; the honest repair is a third actor kind, and it is pinned by test_flow_chain_end_to_end.py

Recorded 2026-08-25 while fixing F45, which **extended** this defect rather than introducing it.

`ACTOR_KINDS` has two members: `run` and `operator`. A firing is neither. So when the flow claims
ordinary work it records `pending -> assigned` as `operator()`, and `test_flow_chain_end_to_end.py`
already names that for what it is — *"the misattribution above, pinned so that fixing it, or a
genuine operator action appearing, both fail here."*

F45's fix adds a second routing move, `completed -> under_review`, and it lands on a status that
carries more meaning than `assigned` does. The history for a reviewed task now reads as though the
operator put it with a reviewer. Nobody did; the flow did.

**Why it was not fixed here.** The honest repair is a third actor kind — a flow or system actor,
distinct from both an authenticated agent run and a person. That touches `Actor`'s validation, the
`is_operator` property that several guards branch on, every consumer that switches on
`actor_kind`, and the operator-facing history surfaces. It is a change about *attribution across
the whole transition machine*, not about review staffing, and doing it inside F45's fix would bury
it.

**What it costs today.** An operator asking "what did I do to this task" is told they did something
they did not. No guard is bypassed — `_guard_author_is_not_reviewer` binds `_REVIEW_OUTCOMES`, and
neither `assigned` nor `under_review` is one — so this is a truthfulness defect in the record
rather than a hole in enforcement. The pin in `test_flow_chain_end_to_end.py` now lists both rows,
so whoever fixes the attribution will be told exactly what to update.

---

## F48 (B) — pressing Run on a healthy flow reported "Failed to fire job"

**Status:** fixed 40330bc

Found live 2026-08-25, on the second firing of the F45 verification. Pre-existing, and made
ordinary by F45's fix.

A loop firing that declines because every candidate is already being worked returns
`DECISION_IN_FLIGHT` and **records nothing at all** — deliberately, and F23's reasoning is right:
the agents' own running rows already carry the fact, and a `JobRun` per tick would evict real
history through `_prune_job_history`'s window at a five-minute cadence.

`POST /jobs/{id}/run` explains a `False` return by reading the **latest** `JobRun`. With nothing
fresh written it found some *earlier* firing, whose status was not `"skipped"`, and fell through to:

```
500  {"detail": "Failed to fire job"}
```

Measured: `run-150ff546845c` was still `in_progress` from the previous firing, so the route reported
a 500 about a loop that was working exactly as designed.

**Reachable before F45 and common after it.** The old trigger was "every candidate's assignee is
mid-turn"; the new one is "a review is out", which after F45 is what a flow looks like most of the
time. The runbook written the same day tells the operator to press Run — so the instruction and the
defect shipped together.

Fixed by asking the decision rather than guessing from a row: `_loop_work_is_all_in_flight`
re-decides and, on `DECISION_IN_FLIGHT`, answers **409** with *"Every task on this loop's queue is
already being worked. Nothing was started, and nothing is wrong — the next firing picks up whatever
finishes."* Re-deciding is the only honest option available, since the decline leaves no artefact;
inferring health from the absence of a row is how the two states became indistinguishable in the
first place.

Verified live: 409 with that sentence, against the same flow that produced the 500.

---

## F49 (A) — `agent_role` could never say `working`

**Status:** fixed 40330bc

Found live 2026-08-25, immediately after F45's fix — and it is **finding F41's pattern for the
third time in this change**.

F26 shipped a real distinction: on the loop board, `working` means *this agent is mid-turn on it*
and `next` means *this is who the next firing would give it to*. Handoff 0086 records it as fixed
"**at the source** because only the merge still knows whether a name means 'working' or 'next'".

The source built its lookup as:

```python
working_by_loop[loop.id] = set(decision.in_flight)      # a set of (task_id, agent) TUPLES
...
if task.id in working_by_loop.get(task.loop_id, ()):    # asked with a bare string
```

`decision.in_flight` is a sequence of pairs. The line above it gets this right —
`dict(decision.in_flight)` — and this one does not. A string is never in a set of tuples, so the
branch never taken, and **`agent_role` could not be `working` in production from the day it
shipped.**

**Why the suite was green: there is no Python test for `agent_role` at all.** The only coverage is
five vitest cases in `jobCard.test.tsx`, each handing the *renderer* an `agent_role` the fixture
made up. The renderer was tested; the derivation that feeds it never was. That is exactly F41 —
six passing tests over a gate that could not fire — and exactly F43 — a chain whose links all work
and whose trigger does not.

Confirmed live before and after. Before: two tasks held by reviewers, both reading
`agent_role: "next"` — "this is who *would* take it", about work already taken. After:

```
under_review | relay  | working
under_review | critic | working
```

Fixed to `{task_id for task_id, _agent in decision.in_flight}`, with
`hub/tests/test_board_agent_role.py` covering both roles — the module that should have existed
when F26 landed.

---

---

## F50 (B) — a checkpoint that failed its own probe is briefed to the reviewer as though it passed

**Status:** fixed 3defb1e

Found 2026-08-25 by the live drive that verified F43, and **caused by F43 becoming real**: before
it, no loop checkpoint had ever existed, so nothing was ever briefed and the question could not
arise. The behaviour itself is pre-existing in `render_checkpoint`.

Driving the corrected F43 trigger against the live trial database generated two handover
checkpoints from real stranded notes. **One of the two failed its probe:**

| checkpoint | agent | status | probe_status | body |
|---|---|---|---|---|
| `ckpt-a545dd785d8d` | `builder` | `ready` | `passed` | 1781 chars |
| `ckpt-9cba6c0e8e40` | `critic` | **`failed`** | **`failed`** | 865 chars |

`status = failed` means exactly one thing here, stated by `probe_checkpoint`'s own comment:
*"Ready means a record exists and passed. It has never meant the run stopped."* The model's written
summary was graded against the Hub's computed envelope and **disagreed with it**.

`render_checkpoint` appends `checkpoint.body` whenever one exists and renders no `status` and no
`probe_status` at all. Neither `latest_checkpoint_for_loop` nor `checkpoint_by_task_author` filters
on status either. So the reviewer receives a summary the product has already judged to contradict
its own database, under the heading `## Prior checkpoint`, indistinguishable from one that passed.

**The note is consumed either way, and that half is deliberate** — `generate_checkpoint` says so:
*"Marked consumed even when generation failed. The notes described a moment that has now passed;
carrying them into a later checkpoint would present stale intent as current."* That reasoning holds.
Combined with this, though, the consequence is that a probe failure costs the reviewer the author's
notes **and** hands it a summary known to be wrong.

Rate on the only live sample that exists: **1 of 2**.

Three ways to close it, and choosing between them is a product judgement rather than a mechanical
fix:

1. **Skip a failed checkpoint when briefing** and fall back to the next candidate. The reviewer gets
   less, but nothing false.
2. **Render it with the failure stated** — the computed half is the Hub's own and remains accurate,
   so the envelope is still worth delivering; only the written half is suspect.
3. **Leave it**, on the argument that a disagreeing summary beside accurate computed fields is still
   better than nothing.

**Resolution (2026-08-26, Q7, pre-authorised):** option 2, render the failure. `render_checkpoint`
now states `Status: <status>` and, when set, `Probe: <probe_status>` in the header, and — only when
`status == "failed"` — a warning ahead of the written body naming the disagreement and pointing out
that the computed sections above stay accurate regardless. Two new tests
(`hub/tests/test_checkpoint_generation.py`); mutation-checked (reverting the render change fails
both new tests with exactly the predicted assertion). Verified live: restarted the trial Hub onto
the fix and re-fetched the ORIGINAL failed checkpoint from this finding's own reproduction,
`GET /projects/proj-18e5d4e0/checkpoints/ckpt-9cba6c0e8e40/rendered`, over real HTTP — the response
now reads `Status: failed`, `Probe: failed`, and the stated warning, unchanged since 2026-08-25.
Task 14.7 in `openspec/changes/loop-becomes-a-flow/tasks.md` closed with this evidence.

## F51 (A) — "start exploration" orphans its own document; the agent writes a second one

**Status:** fixed ccb8902, verified live 15da184

Found 2026-08-25 driving Q2 live on a fresh project (`proj-8605b92d0028`), reproducing the UI's
own "start exploration" flow through the real HTTP surface: `POST .../project/documents` (what
`ConversationView.tsx`'s `startExploration` calls via `createDocument.mutate`, which the comment
there says exists *because* "pressing it creates the document"), then
`POST .../agent/trigger` with `spec_document` set to that path (what `specDocumentPath` feeds the
composer) — the same two calls the UI makes, in the same order, with a real interview message.

**What happened, from the database, not the chat:**

| document | id | created by | requirements |
|---|---|---|---|
| `spec/changes/onyx-sylph/spec.html` | `spdoc-9c8691592be1` | operator (`POST documents`) | `[]` — never touched again |
| `spec/changes/fix-three-bugs-in-inventory-module/spec.html` (born `golden-sylph`) | `spdoc-f64ba8051a5b` | agent `author`, **same run** (`run-8555716d6b9b`) | the real interview's output |

The agent read the seeded `inventory.py`, asked genuinely good interview questions grounded in the
code — and did all of it against a document the operator never asked it to create, while the one
the operator's press *did* create sits forever in `exploring` with zero content. This is F37
("a document created by mistake is permanent, and becomes a standing warning") happening not from
a mistake but from the intended entry point into exploration, every single time.

**Root cause, read from the code the agent actually receives (`hub/hub/api/v1/agents.py`,
`_render_hub_agent_context`):** when `spec_document` is set, the context's "Open specification
document" block (~line 1244) says plainly:

> "The operator is viewing `{open_spec_path}` in the Hub's Spec view. **This is where they are
> looking right now. Treat it as context for what they ask, not as an instruction to act on it.**"

That line is correct for the case it was written for — an operator asking about something else
while an unrelated document happens to be open — but `startExploration` does not produce that
case. It exists, per its own comment, so that "pressing it *creates the document*"; the freshly
created empty document *is* the instruction, not incidental context. Nothing downstream
distinguishes the two. The phase duty text that follows (`SPEC_PHASE_DUTIES["exploring"]`,
~line 987) tells the agent to interview but never says which path to hand to
`submit_spec_document` when it does write. The tool description for `create_spec_document`
(~line 908) reads "start a specification document yourself; **you do not need the operator to
start it**" — true in general, false in this specific turn, and nothing in context tells the model
the exception applies here. `spec_turn_notice` (`hub/hub/launchability.py:247`), which duplicates
the phase instructions into the turn prompt itself specifically because standing context loses to
a competing workflow (its own docstring, citing three prior live runs), has the identical gap: it
says "Write the document only with `submit_spec_document`" and never names the open path either.

**Not a one-off model choice.** The agent's own reasoning (from the run's `[thinking]` blocks) was
methodical and did not hesitate over the open document at all — it read `create_spec_document`'s
description, saw no reason not to call it, and moved on. Every instruction it was given was
followed correctly; the instructions just never say "this one."

**Cost:** every real exploration started the way the product's own UI starts one produces a second,
correct document plus a first, permanent, empty husk indistinguishable later from abandoned work —
compounding directly into F37's "standing warning" with no operator action able to prevent it.

**Fix sketch, not yet applied:** the "Open specification document" block already computes
`open_spec_path`; when the phase is `exploring` and the document has no content yet (this is
knowable — the row's `content_digest`/requirements are empty, exactly as `spdoc-9c8691592be1`'s
were), state directly: "This document is what you are interviewing for. When you call
`submit_spec_document`, pass `path='{open_spec_path}'` — do not call `create_spec_document`, one
already exists for this turn." `spec_turn_notice` needs the same path threaded through it, since
it is deliberately the copy that wins competing attention. Left unfixed for Q3 to pick up as
severity A.

**Fixed 2026-08-26, Q3.** One correction to the sketch during implementation: `content_digest` is
*not* the right emptiness signal — `POST /documents` ("start exploration") already writes an
initial save with `requirements: []`, so `content_digest` is set from the moment of creation and
cannot distinguish "just created" from "genuinely written". `requirement_digests` can: it is `{}`
until a submission carries at least one requirement (`spec_digest.payload_digests` returns `{}`
for an empty requirement list), which is exactly the state a fresh exploration is in and never the
state a written one is in. `hub/hub/api/v1/agents.py`'s `_render_hub_agent_context` now checks
`phase == "exploring" and not row.requirement_digests` and, when true, replaces the "treat it as
context, not an instruction" line with one naming `open_spec_path` as the `submit_spec_document`
target and telling the agent not to call `create_spec_document`. `spec_turn_notice`
(`hub/hub/launchability.py`) gained the identical `path`/`is_unwritten` branch, threaded from a
new `_spec_phase_for` return shape in `hub/hub/api/v1/agent_trigger.py`. Regression tests in
`hub/tests/test_task_spec_document_context.py` (`test_f51_*`, three new): one asserts the new
instruction fires and the old framing is absent for an unwritten document, one asserts the *old*
framing still holds for a document that already has content (guards against over-firing onto the
case the general framing is correct for), one covers `spec_turn_notice` directly.
Mutation-checked: reverting the three source files (keeping the new tests) fails exactly
`test_f51_an_unwritten_open_document_is_named_as_the_write_target` and
`test_f51_spec_turn_notice_names_the_unwritten_path` by name; the "keeps the old framing" guard
test correctly still passes, since that case was never broken.

**Verified live**, on the same project (`proj-8605b92d0028`) the finding was found on, after
restarting the trial Hub on the beta database to pick up the code change: fresh `doc-new` produced
`spec/changes/lilac-chimera/spec.html`; a first turn (pure interview, no tool call) produced no
document event at all — no second document; a second turn, answered honestly, submitted the
specification — the resulting document is
`spec/changes/cli-wrapper-for-inventory-stock-level-queries/spec.html`, confirmed from
`spec_document_events` to be the **same row**, `renamed` then `content` by `agent/author`, no
`created` event after the operator's own. Three documents exist on the project afterward, not
four: the two carried over from Q1/Q2 plus this one — `create_spec_document` was never called.

---

## F52 (A) — the "workspace" permission posture never sees a git command; every commit is refused, silently, with no operator visibility

**Status:** partially fixed 68459ea (the refusal is no longer invisible); the underlying CLI refusal does not reproduce — 0cda570 disproved its central inference and 57eb92b eliminated the last axis live. Out of scope, 2026-08-27: a new git refusal is a new finding

Found 2026-08-26 driving Q4 live on `ledger-stress` (`proj-18e5d4e0`): enabling `job-f632ee565238`
("Width bench", a loop with no reviewer other than its own agent) and letting it fire twice,
unattended, exactly as a real overnight loop would. The intended target was the F43/F44
run-boundary checkpoint hook; neither run got far enough to reach it, because **neither run could
commit anything**, and that is the actual, more severe finding.

### What happened, from both live runs, not the transcript's own summary

`run-2f63d76eeae2` (`builder`, task `task-3292072f63c3`, "Round half to even in `Money.quantize()`")
and `run-9e793f8b5c35` (`builder`, task `task-bb86d53a94d5`, "Reject a posting with an unknown
account code") both implemented real, correct-looking fixes with real tests, then tried to commit.
Every attempt was refused:

| Attempt | Refusal (verbatim from the tool result) |
|---|---|
| `git add -A && git commit -m "..."` (Bash) | "This Bash command contains multiple operations. The following parts require approval: git add -A, git commit -m '...'" |
| `git add file; git commit -m @'...'@` (PowerShell heredoc) | "This PowerShell command contains multiple operations. The following part requires approval: git add ..." |
| `git config user.name "Claude Code"` alone, then `git config user.email ...` | "The following parts require approval: git config user.name ..., git config user.email ..." |
| A Python `subprocess.run(['git', 'add', ...])` wrapper | "This PowerShell command contains multiple operations. The following part requires approval: python -c \"import subprocess; ...\"" |
| A standalone committed helper, `python commit_account_validation.py` | "This PowerShell command contains multiple operations. The following part requires approval: python commit_account_validation.py" |
| **`git --version` alone** | "This Bash command contains multiple operations. The following part requires approval: git --version" |

The last row is the one that rules out "compound command" as the real shape of the problem:
`git --version` is one word, no `&&`, no `;`, no pipe, read-only. It was refused with the identical
"contains multiple operations" wording. Across the two runs, **29 of 98 tool calls failed, 10 of
them naming `git` explicitly** — every single git invocation attempted, by any phrasing, over two
independent runs, on two independent tasks, was refused.

### Why this is worse than a refused command: nobody could have approved it

`ledger-stress` runs the product's own default, unforced posture — `mcp_server.py`'s own docstring
says this is the point of `workspace`: *"the Hub answers it... needs no terminal at all"* (see the
`2026-08-06-claude-non-yolo-permission-mode` history in `runner_commands.py`). Its approver,
`_decide` (`mcp_server.py:811`), is pure and total: a command with no absolute-path argument
outside the workspace falls through to `return {"allow": True, "reason": "inside your workspace"}`
unconditionally — `git add -A`, `git commit -m "..."`, and `git --version` all have zero path
candidates, so `_decide` would have said yes to every one of them, instantly, if it had ever been
asked.

It was never asked. Two independent checks confirm `approve_tool_call` was not invoked for any of
these refusals:

- `select * from permission_requests where conversation_id in (...)` → **0 rows**, for either
  conversation, though this posture does not use that table (that is `manual`'s, the
  operator-answered path) — checked anyway to rule it out.
- `select * from event_logs where event_type='permission_denied' ...` → **0 rows**, in either
  conversation's full timeline. `record_permission_decision` (`agent_actions.py:598`) persists
  every refusal precisely so "an agent hits a wall and the one person who could widen it never
  learns it happened" cannot occur silently — its own docstring's exact words. It did occur
  silently: `_report_decision` is only reachable from inside `_decide`, and `_decide` was never
  entered, so there was nothing for it to report.

The refusal is therefore generated **before** Claude Code ever calls the tool named by
`--permission-prompt-tool`. This looks like the CLI's own local safety classification of `git` (and
possibly any external-binary invocation not on some internal allow-list) as needing a category of
confirmation that a `--permission-prompt-tool` cannot satisfy — headless or not, workspace posture
or not. `--permission-mode manual --permission-prompt-tool mcp__agentweave__approve_tool_call` is
exactly the flag pair `_build_claude_command` emits for this default posture, and it did not help.

**Open, not closed: a plausible but unconfirmed contributing factor.** `mcp_server.py`'s own
comment says the `--permission-prompt-tool` contract "was measured against Claude Code 2.1.221";
the CLI on this machine, right now, is **2.1.238**. Whether the newer build changed how — or
whether — Bash/PowerShell calls route through a configured permission-prompt-tool at all was not
tested against the older build (not available on this machine), so this is recorded as the leading
hypothesis, not a proven cause.

### The agents' own workaround made it worse, not better

Neither agent escalated with `ask_user`, though both had it and one explicitly considered it
mid-transcript ("Let me try to send a message to the relay agent asking about the permission
issue"). Both instead declared victory: `task-3292072f63c3` and `task-bb86d53a94d5` both read
`completed` (`task_transitions` rows confirm `in_progress -> completed` by `run`/`builder`), with
**zero commits, zero evidence rows** — `record_evidence` was never reached for the first task and
was refused for the second ("this project has no requirement ta<redacted>", since a plain loop task
carries no `FR-` id to cite). The code changes exist only as uncommitted edits in
`aw-stress/.agentweave/worktrees/builder`, indistinguishable from any other in-progress edit the
next firing of the same agent could silently discard or overwrite. A task the board calls "done"
shipped nothing.

### What held, worth recording so it is not lost under the severity of the above

`review_unstaffed` (`evt-b27d3943cb20`) fired correctly after the first completion: this loop has no
second agent to review its own work, and rather than staffing nobody and calling that success, the
scheduler recorded exactly why, by name, once — it did not retry every tick and did not silently
proceed. That is the behaviour `loop-becomes-a-flow`'s own reasoning about `DECISION_IN_FLIGHT`/F48
exists to produce, and it produced it here on a genuinely new case (no reviewer at all, not merely
one that is busy).

### Cost

This is not one bad task. It is the default, unforced posture of every headless agent in this
product failing to commit, on the CLI installed on this machine, right now — the exact posture
`2026-08-06-claude-non-yolo-permission-mode` was written to make work without a human at the
keyboard. Every downstream promise this drive has verified — evidence, review, merge into `master`
(F43's own `75ebebce`) — assumes the commit underneath it happened. On this build, for a `claude`
runner with no operator-forced override, it did not, twice, without a single row anywhere saying so.

### Correction and partial fix, 2026-08-26 (same drive, next iteration)

Two things above are wrong or overstated, found while doing the two-runner check this write-up's
own "Open, not closed" section said had not happened yet, and both change what F52 actually is.

**1. It is not Claude-specific — confirmed, but not for the reason expected.** Fired a live turn on
`relay` (Codex, `runner-fde56879`, app-server transport) with an equivalent git-touching
instruction. It also could not commit — but Codex's own refusal names a completely different
mechanism from Claude's: *"`git commit` is blocked by permissions on the shared
`.git/worktrees/relay` metadata... needs to write the shared `.git/worktrees/relay` metadata
outside the writable sandbox."* Claude's CLI refuses before `approve_tool_call` is ever invoked
(zero `permission_requests`/`permission_denied` rows, as already established); Codex's sandbox
boundary check *is* being invoked and is refusing on its own terms. Two independent mechanisms,
both landing on "cannot commit inside a linked git worktree" — worth recording as agreement
between two unrelated systems rather than one root cause, since nothing here shows they are the
same defect.

**2. Extensive isolated reproduction attempts, across every plausible axis, did NOT reproduce the
Claude refusal.** Built a standalone repro harness (`testbed/scratch/f52_pty_repro.py`) spawning
`claude` exactly as `runner_commands._build_claude_command` does — same flags
(`--permission-mode manual --permission-prompt-tool mcp__agentweave__approve_tool_call
--allowedTools mcp__agentweave__*`), same real `mcp_server.py` wired as a stdio MCP server, same
compound `git add -A && git commit -m "..."` text verbatim from the failing transcript — and varied:
plain subprocess vs. a real `winpty.PtyProcess` pseudo-terminal (matching `PtySession`, which is
what production actually uses, not a plain pipe); `claude-opus-5` vs. `claude-haiku-4-5-20251001`
(the actual cheap runner model); this machine's own `~/.claude/settings.json`
(`defaultMode: auto`, present since 2026-08-23, so present during the original F52 drive too)
included and excluded via `--setting-sources`; this session's own `CLAUDE_CODE_*`/`CLAUDECODE`
child-session env vars included and stripped; a plain repo vs. a real linked `git worktree` (`git
worktree add`) as `cwd`, matching production's `aw-stress/.agentweave/worktrees/builder` shape.
**Every single combination committed successfully, first try, no refusal, `permission_denials: []`
in every case.** The refusal is real (verified twice now, in two different live drives, by DB rows
and by literal tool-result text) but its trigger is narrower and more specific to the full
production turn than any of these axes — the large injected `--append-system-prompt-file` context,
something about a resumed vs. fresh session, or something else not yet isolated. Recorded as a
genuine open question, not swept under "CLI version drift" as the leading hypothesis any longer —
that hypothesis is now weaker, not stronger, after this many negative results.

**3. The claimed consequence — code lost, "indistinguishable from any other in-progress edit... the
next firing could silently discard or overwrite" — is WRONG, and this is the important part.**
`worktrees.snapshot_worktree` runs unconditionally at the end of *every* turn
(`agent_trigger.py`'s finalize path, reached whether the run completes or fails, not something the
agent has to invoke), commits whatever is dirty with `--no-verify` onto the agent's own branch, and
stamps `run.snapshot_commit_sha`. `_restamp_evidence_footprints` then re-points any evidence
recorded mid-turn (while the work was still dirty) at that real commit. Checked directly against the
same worktree and the same two runs this finding was originally measured against:
`run-2f63d76eeae2.snapshot_commit_sha = 1e35528...` and `run-9e793f8b5c35.snapshot_commit_sha =
75d5b26...`, both real commits in `aw-stress/.agentweave/worktrees/builder`'s history, both holding
exactly the fix content (banker's-rounding `quantize()`; account-code validation), both authored
`AgentWeave <agentweave@localhost>` — the worktree read `nothing to commit, working tree clean`
when checked. The code was never at risk. What was actually missing is `requirement_evidence` rows
(genuinely zero for both runs) — but that is the **pre-existing, already-documented** "a plain loop
task carries no `FR-` id to cite" gap this write-up itself named, not a consequence of the git
refusal; `record_evidence`'s own docstring says `locator` is free text ("a path, a command, a run
id"), never a commit sha the agent must produce. **Severity revised down**: this is not
"foundational, undercuts the evidence/review/merge chain" (refuted — the chain's own commit
capture does not depend on the agent's git succeeding, by design, and the design already
anticipated evidence recorded before a commit exists). It is real and still costs a whole turn's
attention and, for the first run, an abandoned task — that part stands.

**Fix applied**, scoped to what is actually fixable without knowing the CLI's root cause: agents
were burning most of a turn on a problem the Hub had already solved for them, because nothing told
them so. Added `launchability.auto_snapshot_notice()`, appended to every writing agent's turn
prompt (`agent_trigger.py`, gated on `isolated_workspace is not None and review_context is None` —
the same condition `worktree` is computed under for the snapshot call itself) telling the agent it
does not need to `git commit`, the Hub does it automatically at turn end regardless, and to call
`record_evidence` with a free-text locator instead of retrying git. This does **not** fix the
underlying CLI refusal (still open, root cause unconfirmed) — it stops the refusal from costing a
whole turn and a possibly-abandoned task while that stays open.

Two new tests, `hub/tests/test_launchability.py::test_f52_auto_snapshot_notice_says_the_agent_need_not_commit`
and `hub/tests/test_agent_trigger.py::test_f52_writing_agent_gets_the_auto_snapshot_notice` (plus a
negative case, `test_f52_read_only_agent_gets_no_auto_snapshot_notice`, for an agent with no
worktree to snapshot). **Mutation-checked**: stashed `launchability.py` and `agent_trigger.py` only
(not the tests) — `test_launchability.py` fails to even import (`auto_snapshot_notice` gone), and
`test_f52_writing_agent_gets_the_auto_snapshot_notice` fails its exact assertion with the real
pre-fix prompt text in the diff. Restored, reverified green: 81/81 in both files.

**Verified LIVE**, not just against the fixture. Restarted the trial Hub on the beta database
(confirmed via `e2e.py state proj-18e5d4e0` reading identical project state before and after).
Fired a fresh `builder` turn on `ledger-stress` with the same kind of git-touching instruction:
`run-021a5dfc357c`. The notice appeared, the agent tried the compound commit once, it was refused
exactly as before ("contains multiple operations... requires approval"), and — unlike the original
two runs, which tried five more phrasings each before one gave up on the task entirely — this run
stopped after the one attempt, correctly reported *"According to the system message, the Hub will
automatically commit my worktree's uncommitted changes at the end of this turn,"* and ended
cleanly. `aw-stress/.agentweave/worktrees/builder`'s log confirms: `04e9d8d Auto-snapshot: builder's
turn`, holding exactly the one-line edit the run made, tree clean afterward.

### Still open

The CLI-level refusal itself (both runners) — root cause unconfirmed, isolated reproduction failed
across every axis tried above. Left for further investigation, not for a blind fix: applying
`--allowedTools` patterns or a Claude-Code-version pin on the strength of a hypothesis this many
negative results have weakened would risk false confidence more than it would help. Candidate
directions, none applied: (a) capture the *actual* full production prompt/context a failing turn
receives (not a synthetic stand-in) and bisect it; (b) `--allowedTools` patterns (`Bash(git add:*)`,
`Bash(git commit:*)`) as a narrower pre-approval that sidesteps whatever is refusing, if (a) does
not explain it; (c) for Codex, whether the app-server sandbox can be configured with the main
repo's `.git/worktrees/<agent>` directory as an additional writable root; (d) detect the pattern
live — a run whose tool-result stream contains N "requires approval" refusals with zero matching
`permission_denied` events is a run whose posture is not doing what it claims, and the operator
currently has no way to learn that from the dashboard at all.

### Correction 3, 2026-08-27: the reasoning behind the leading hypothesis is unsound, and the last untested axis is now eliminated

Investigated on request, going at root cause rather than at the detector. Three results, and the
third invalidates the direction the previous two corrections were pointing in.

**1. The real production turn context does NOT reproduce it — the last named untested axis is
eliminated.** Correction 2 closed with the refusal's trigger being "narrower and more specific to
the full production turn than any of these axes — the large injected `--append-system-prompt-file`
context, something about a resumed vs. fresh session, or something else not yet isolated." The
context half of that is now tested. A real 14,988-byte context, written by a real turn of
`ledger-stress`'s own `builder` agent and still on disk at
`aw-stress/.agentweave/worktrees/builder/.agentweave/context/builder.md`, was injected through the
real `_build_claude_command` (imported, not restated, so the flags cannot drift) into a linked git
worktree, against Claude Code 2.1.238. Two variants differing in nothing but that file:

| variant | context | approver calls | refusal | committed |
|---|---|---|---|---|
| A, no context | 0 B | 3 | none | n/a (nothing to add) |
| B, real production context | 13,988 B | 3 | none | **yes** |

The turn committed. The context is not the trigger.

**2. `--permission-mode manual` is a valid flag that Claude Code 2.1.238 aliases to `default`.**
Measured directly: `bogusmode` is rejected by the CLI with an argument error, `manual` is accepted
and the `init` event reports `permissionMode: "default"`, while `acceptEdits` reports itself. So
`manual` is not silently dropped, and nothing is broken by it — the posture's behaviour is carried
by `--permission-prompt-tool`, exactly as `runner_commands.py`'s own comment says ("what makes it
'workspace' rather than 'ask the operator' is the approver flag"). Recorded because the flag
AgentWeave passes and the mode Claude reports do not match by name, which will mislead the next
person who reads a transcript.

**3. The evidence for "refused before the approver was ever consulted" does not support it.**
This is the important one. The original write-up says:

> Two independent checks confirm `approve_tool_call` was not invoked for any of these refusals
> [...] `select * from event_logs where event_type='permission_denied' ...` → **0 rows**

`record_permission_decision` (`agent_actions.py:598`) persists **only refusals** — its own
docstring says so: *"Only refusals are persisted. An allowed call is the unremarkable case and
would bury the interesting one under a row per tool call."* The handler body is `if not
body.allowed:`. An allowed call writes no event, no row, nothing, anywhere — confirmed by grep;
there is no second sink.

So **zero `permission_denied` rows is exactly what an approver that ran and allowed everything
looks like.** It is not evidence that the approver never ran. And an approver that allowed
everything is precisely what this finding's own analysis predicts: *"`_decide` would have said yes
to every one of them, instantly, if it had ever been asked."*

`_report_decision` compounds it from the other end: every failure is swallowed
(`except Exception: pass`, deliberately — a Hub that is down must not turn an answered request into
an unanswered one). So a Hub that was slow or unreachable also produces zero rows, with the
decision still correctly returned to Claude.

Three different states are therefore indistinguishable in the record: the approver never ran; the
approver ran and allowed; the approver ran, allowed, and failed to report. The leading hypothesis
picked the first of the three with no evidence separating it from the other two — which is why
every reproduction attempt aimed at "Claude refuses before consulting the approver" has come back
negative. They were reproducing the wrong mechanism.

**What this changes.** F52's root cause is still unknown, but the search space is different, and
the "CLI refuses locally" theory should no longer be treated as leading. Untested axes that remain,
now in the right order: the real `mcp_server.py` against a live Hub rather than a stub approver
(where `_ask_operator`, `AW_PERMISSION_POSTURE`, `AW_DECISION_TIMEOUT` and a blocking HTTP call all
exist and none were in any harness); `--resume` on a second turn, which every loop firing after the
first uses and no harness has ever exercised; and the real production prompt with its inbound state,
rather than a synthetic one.

**And it strengthens (d) for a better reason than the one originally given.** The case for
detecting this live was "the operator cannot learn a refusal happened". The stronger case is that
**an allow is unobservable by design**, so the system cannot show its own posture ever worked. A
detector that compares refusal-shaped tool results against recorded decisions is not merely a
convenience — it is the only way to tell the three indistinguishable states apart, and it would
have prevented this finding's central inference from being made at all.

**A diagnostic distinction worth keeping**, found by getting the stub wrong first: an approver whose
return shape is wrong (a dict rather than the `json.dumps(...)` string the real
`approve_tool_call` returns) produces `Error calling tool (Bash): Permission prompt tool returned
an invalid result` on **every** tool call, with the approver **logged as called**. That is a
different signature from F52, where nothing is logged at all. Do not confuse the two.

**Axis 1 tested the same evening, live, and it does NOT reproduce either.** A full real turn:
isolated Hub on 8011 started from source on this branch (migrated to `0096`), its own throwaway
database, a fresh throwaway project `proj-a1736a6a596b` at `C:\Users\huida\Documents\aw-f52`,
default seeded `claude` runner pinned to Haiku, agent `builder`, triggered through
`POST /projects/{id}/agent/trigger` with an instruction to run `git --version`, `git add -A` and
`git commit`. So the **real `mcp_server.py`** answered, with a real run credential, a real Hub to
report to, and the real `AW_*` environment - none of which any harness had ever included.

**The turn committed.** `.agentweave/worktrees/builder` carries `c8d0fb1 f52: fix is_low_stock` on
top of `cb35c0e initial`, working tree clean. No refusal, and the isolated per-agent worktree was
provisioned and used exactly as designed.

So every axis this finding ever named is now eliminated, including the one left as most likely.
**F52 does not reproduce on current code with Claude Code 2.1.238.** That is not the same as
"fixed": nothing was changed to fix it, and it was observed twice, live, on two separate drives.
The honest reading is that its trigger was in something that has since moved - the CLI build, the
machine's settings, or Hub code that has changed a great deal since 2026-08-26 - and the record
cannot say which, because an allow is unobservable.

Which is the argument for (d) restated as a measurement problem rather than a convenience: this
finding cost two drives and three investigations, and the reason it could never be pinned is that
**the product keeps no positive evidence that its own approver ran.** Until it does, the next
occurrence will be equally unfalsifiable.

One incidental observation, not chased: while the run was live the Hub's own API stopped answering
`GET /projects/{id}/runs` for minutes at a time (two client calls timed out, at 3 and 10 minutes,
against an instance that answered instantly before the run and whose log shows nothing). Not filed
as a finding because it was not driven deliberately or reproduced.

**Harness:** `testbed/scratch/f52_context_repro.py` and `f52_stub_approver.py` — gitignored, as
`testbed/` is meant to be. Rebuild rather than restore if needed; the earlier
`f52_pty_repro.py` was not kept either.

## F53 (B) — archiving a loop that never fired still permanently, irrevocably claims its spec document; the tasks it "adopted" have no recovery path

**Status:** partially fixed 2239f38 (option (a) only — an archived loop's document claim no longer blocks a new loop); the `_adopt_document_tasks` orphaning half is open and queued as Q4-SPEC

Found 2026-08-26 driving Q4, self-inflicted and then traced to the code rather than dismissed as
operator error — the whole value of finding it is that a real operator could do the exact same
three clicks by accident.

**Reproduction, three real API calls, no fixture:** on `drive-2026-08-26` (`proj-8605b92d0028`),
created a flow job (`POST /projects/{id}/jobs` with `spec_document_id: spdoc-f64ba8051a5b`, an
*approved* document with three real pending tasks). Its `agent` field named a self-registered poll
agent, which turned out to be the wrong kind for a Hub-spawned loop (see the "held" note below), so
before ever firing it once, I archived the job to replace it:
`POST /projects/{id}/jobs/{id}/archive` → `200`, and the response showed the loop's own
`archived_at` set to the same instant, so one call archived both. Then, to reuse the same
document on a corrected job, `POST /projects/{id}/jobs` with the same `spec_document_id` again:

```
409 {"detail": "document 'spdoc-f64ba8051a5b' is already claimed by loop 'loop-2b337162dffd'"}
```

That loop is the one just archived. It never fired. It has no run, no conversation, no output —
and it still permanently owns the document.

### Root cause, both halves, read from the code

1. `_check_spec_document_conflict` (`hub/hub/api/v1/jobs.py:103-124`) is the sole gate a new job's
   `spec_document_id` passes through, on both the create path (line 590) and the "opt an existing
   job into a loop" PATCH path (line 838). Its query is
   `select(Loop).where(Loop.project_id == project_id, Loop.spec_document_id == spec_document_id)`
   — **no `Loop.archived_at.is_(None)` filter anywhere in it.** An archived loop is exactly as
   good a conflict as a live one, forever.
2. Independently and more costly: `_adopt_document_tasks` (line 185) is *"restricted to
   `loop_id IS NULL` so a task another loop already owns is never taken"* — a deliberate, correct
   guard against double-claiming a task a live loop is using. But it does not distinguish "another
   loop owns this and is still using it" from "another loop owned this, is dead, and nobody will
   ever use it again." Once `_adopt_document_tasks` ran once (at this loop's creation) and stamped
   `loop_id = 'loop-2b337162dffd'` onto the three tasks, archiving the loop did **not** null that
   column back out. Confirmed directly against the row data, not inferred:
   `sqlite3 … "select id, status, loop_id from tasks where project_id='proj-8605b92d0028'"` →
   all three tasks still read `loop_id = 'loop-2b337162dffd'`, `status = 'pending'`, after the
   archive. There is no operator API anywhere in `jobs.py`, `loops.py`, or `tasks.py` that clears
   or reassigns a task's `loop_id`.

### The consequence, stated plainly

Once a loop has adopted a document's tasks even once, archiving that loop — the only tool the
product offers for "get rid of a mistaken or unwanted loop" — does not release the document *or*
the tasks. No second flow can ever be created against that document (permanent 409), and the three
tasks are stranded: not deletable through any task API surface found in this drive, not
reassignable to a different loop, and invisible to every loop-queue query in `scheduler.py` (which
all read `Task.loop_id == <the live loop's id>`) because they belong to a loop that is not, and can
never again be, live. The only way discovered to make progress on the underlying work was to
create fresh replacement tasks by hand — the original three are simply gone from the product's own
workflow, permanently, while still existing as un-completable rows in the database.

**This did not require a git refusal, a permission wall, or any of this drive's other exotic
seams.** It requires exactly what the `loops.py` archive-and-recreate UI flow invites: create a
loop with the wrong agent, archive it, try again. `POST /jobs/{id}/archive`'s own success response
gives no warning that the document claim survives it.

### What a fix would need to decide

Either (a) `_check_spec_document_conflict` excludes archived loops, which fixes the second flow but
leaves the first three tasks still bound to a dead `loop_id` with no query surfacing them, or
(b) archiving a loop also clears `loop_id` back to `NULL` on every task it adopted that never left
a non-terminal, unclaimed state — which is the one that actually un-strands the tasks, but needs a
decision about tasks the dead loop's agent had already started or completed (those should almost
certainly keep their `loop_id` as history, not be silently reset). Left undecided and unfixed here;
this is Q6's shape of item (design gap with a real, reproduced consequence), not a one-line patch.

**What a reviewer should distrust:** the "wrong kind of agent for a loop" trigger for the first
archive (self-registered poll agents cannot be a loop's `agent` — see the `409`,
`"author is a self-registered poll agent and manages its own execution"`, reproduced live on the
same project) is itself worth a line in a future finding if it recurs, but is not re-litigated here
since it did not block anything once a Hub-managed agent was created instead.

### Resolution (partial) — 2026-08-26, Q6

Fixed option **(a)** only, deliberately, per this write-up's own framing: option (a) is
decision-free (a document is no longer permanently unusable), option (b) is not (whether an
already-`loop_id`-stamped task should keep or lose that history is the operator's call, not
guessed at here). `_check_spec_document_conflict` now excludes `Loop.archived_at.is_(None)`, and
the database's own unconditional `unique=True` on `Loop.spec_document_id` was replaced with a
partial unique index (`ux_loops_spec_document_live`, `WHERE archived_at IS NULL`, migration
`0090`) — the API-level check alone was not sufficient, since the INSERT itself hit the old
unconditional index and raised a raw `IntegrityError` rather than the intended `409`. Regression
test `test_f53_an_archived_loops_document_claim_does_not_block_a_new_loop` added; mutation-checked
by reverting the `archived_at` filter in `_check_spec_document_conflict` and confirming the test
fails with the exact pre-fix `409`. **A real bug was caught in this verification pass, not
authored by it**: the migration's `downgrade()` omitted the same missing-table guard `upgrade()`
has, and crashed with `no such table: main.loops` under `test_migration_0085`/`0086`, which
synthesize a database starting from an earlier revision — fixed before commit. Live-verified over
real HTTP against the restarted trial Hub (migration `0090` applied, `alembic_version` reads
`0090`, both indexes present): created a job against `doc-f53-live-verify-iter13` on
`proj-8605b92d0028`, archived it, created a second job against the same `spec_document_id` — `201`,
where before the fix this would have been the same permanent `409` the reproduction above shows.
Both live-verification jobs archived immediately after; no job left enabled. **Task-`loop_id`
orphaning (root cause 2, the `_adopt_document_tasks` half) is still open and still needs the
operator's decision** — recorded as such in `decisions_for_user`, not closed here.

## F54 (A) — a job-creation request that 409s on a document conflict has already committed an enabled, spendable job; the error response is not the rollback it looks like

**Status:** fixed 94e2dcb

Found live 2026-08-26, immediately after F53, on the very next API call in the same drive —
creating the second attempt at the "Inventory flow" job (`agent: loopauthor`, same
`spec_document_id` F53's archived loop still claims) returned `409` exactly as F53 describes. That
response was trusted as a no-op, the same way any REST client would trust a 4xx. It was not one:
`select id, project_id, enabled, name from ai_jobs` on the beta database, run for this iteration's
mandatory job sweep, turned up `job-08e0c3b0329c`, project `proj-8605b92d0028`, **`enabled: 1`**,
`cron: */5 * * * *`, `agent: loopauthor` — a real, spawnable, Hub-managed agent (not the
self-registered kind F53's first attempt tripped over) — sitting enabled and unnoticed for roughly
eight minutes before this sweep caught it.

### Root cause, read from `create_job` (`hub/hub/api/v1/jobs.py:549-611`)

The `AIJob` row is built, `session.add(job)`, and **committed** at line 575-577 — before any
loop-related validation runs. Only afterward, at line 588-590, does
`if _loop_opts_in(...): await _check_spec_document_conflict(...)` run, and
`_check_spec_document_conflict` raises `HTTPException(409, ...)` with nothing between it and the
already-committed job — no rollback, no compensating delete, no `enabled=False` write-back. The
request that ends in `409` to the caller has already durably created the job the caller was told
did not get created, `enabled` at whatever the request body asked for (default `true`, per
`JobCreate.enabled`'s own default, confirmed by this job reading `enabled: 1` when the create body
never mentioned `enabled` at all).

This is the exact failure mode `initial_tasks` validation right above it (line 537-538) was
explicitly written to prevent — *"validated up front, before any row is created, so one malformed
entry cannot leave a job (and its loop) half-created behind a 422."* The document-conflict check
sits fifty lines below that comment and does not follow its own rule.

### Why this is severity A and not a cousin of F53

F53 is a data-orphaning defect: real work becomes unreachable, but nothing spends while it sits
there. This is a live-spend defect: the artifact left behind is not an inert row, it is **an
enabled cron job bound to a real runner**, identical in every respect to any other enabled job this
drive's own standing rule calls "the single most expensive mistake available" — except this one was
never knowingly enabled by an operator at all. It was a side effect of a request the operator
believed had failed. Measured, not hypothetical: `next_run` was already computed
(`2026-08-26T00:30:00Z`) and `run_count: 0`/`last_session_id: null` only because this sweep found
and disabled it a few minutes before its first tick — this is a "caught it in time," not a "it was
never going to fire."

### Verified live, not inferred

`PATCH .../jobs/job-08e0c3b0329c {"enabled": false}` → `200`, then
`POST .../jobs/job-08e0c3b0329c/archive` → `200`. Re-swept `ai_jobs` immediately after: all ten rows
across all five projects read `enabled: 0`, including this one.

### What a reviewer should distrust

This job never actually fired (caught before its first cron tick), so there is no live evidence of
what firing an orphan job with a dead loop reference (`loop: null` despite `spec_document_id` having
been intended) would have done downstream — only that it was armed to. Whether the same
already-committed-before-validation shape exists on the PATCH path (`update_job`, line ~752) that
also calls `_check_spec_document_conflict` was not checked this iteration; the PATCH path mutates an
existing row rather than creating one, so the blast radius is different (a bad edit rather than a
phantom job) and untouched-agent-field jobs it patches are already enabled by the time PATCH is
reachable, so the marginal risk is smaller but not obviously zero.

## F55 (B) — an unprovoked, intermittent test failure, and a real "which checkpoint is newest" tie-break bug behind it (Windows clock resolution)

**Status:** fixed 1dd0b04 (migration 0088), verified f92ef0a

Not something this iteration went looking for. Found running an unrelated broader slice
(`pytest hub/tests/ -k "jobs or loops or scheduler"`) to sanity-check the F54 fix — one test failed
that has nothing to do with `jobs.py`: `test_flow_checkpoint_lineage.py`. Re-running the same file
alone, repeatedly, on the unmodified branch tip (stashed the F54 change to rule it out as the
cause) confirmed this is **pre-existing and genuinely intermittent, not caused by this iteration's
work**: 2 of 6 bare re-runs failed, alternating between two different tests in the same file
(`test_the_briefing_carries_the_newest_checkpoint_whoever_wrote_it` and
`test_a_loops_checkpoints_do_not_chain_and_that_is_the_point`).

### Root cause, confirmed with a direct measurement on this machine, not inferred from reading

Both failing tests call `_checkpoint_by` (the test's own helper) twice in a row, each call ending
in `create_checkpoint`, which stamps `created_at` via `Checkpoint.created_at`'s column default,
`_now()` = `datetime.now(timezone.utc)` (`hub/hub/db/models.py:23-24`). `latest_checkpoint_for_loop`
(`hub/hub/checkpoints.py:107-118`) orders `select(Checkpoint)... .order_by(Checkpoint.created_at.desc(),
Checkpoint.id.desc())` — id as the tie-break when timestamps are equal.

Measured directly on this machine, no test harness involved:

```python
>>> [datetime.now(timezone.utc) for _ in range(5)]
2026-08-26T00:45:13.392498+00:00   # all five calls, back to back, identical
2026-08-26T00:45:13.392498+00:00
2026-08-26T00:45:13.392498+00:00
2026-08-26T00:45:13.392498+00:00
2026-08-26T00:45:13.392498+00:00
```

Windows' `datetime.now()` resolution is coarser than the microsecond precision the value's own
format implies — a known platform characteristic, not a Python bug — so two `create_checkpoint`
calls separated only by an `await db.commit()` reliably land in the same tick more often than not.
When they do, `Checkpoint.id.desc()` decides "which is newest" — and `id` is `short_id()`, a random
hex string with **no relationship to insertion order at all**. Roughly half the time the second
(truly newer) checkpoint's random id sorts *lower* than the first's, and
`latest_checkpoint_for_loop` returns the wrong one — which is exactly what both flaky tests
observe, each in its own assertion about which checkpoint's content should win.

### Why this is a real product bug, not just a fragile test

The tests only exercise it because they create two checkpoints with no delay between them; the
product does the identical thing on real hardware whenever two loop firings (e.g. two agents in a
width>1 flow) both complete and generate a handover checkpoint within the same clock tick — a
window measured here as large enough to swallow at least five consecutive Python-level calls, not
a one-in-a-million race. When it happens live, a briefing would be composed from the *older* of two
checkpoints, silently — nothing errors, nothing logs a decision, the briefing just carries stale
content while looking exactly like a correctly-functioning handover. The same pattern
(`created_at.desc()` with an incidental secondary sort) likely recurs anywhere else in the
codebase that orders checkpoints, notes, or events by timestamp with no monotonic tie-break —
not audited exhaustively this iteration.

### Fixed, iteration 11 — `Checkpoint.sequence`, migration `0088`

Same shape as `TaskTransition`, `InboundQueueEntry` and `Conversation.sequence` (migration `0073`,
identical reasoning): an autoincrement integer becomes the table's primary key, with `id` demoted
to a plain unique column. `sequence` is assigned by the database in insertion order, so it cannot
tie regardless of what `datetime.now()` returns.

`hub/hub/db/models.py`: `Checkpoint.sequence` is now the primary key, declared in `__table_args__`
with an explicit name (`PrimaryKeyConstraint("sequence", name="pk_checkpoints")`,
`UniqueConstraint("id", name="uq_checkpoints_id")`) rather than inline `primary_key=True` — the
first attempt used the inline form and its migration's downgrade round-trip tests failed with
`KeyError: 'pk_checkpoints'`, because SQLAlchemy leaves an inline single-column primary key
unnamed and `create_all` (what `test_migrations.py`'s fixtures build from) then produces a table
whose PK constraint has no name for the migration to `drop_constraint` by. `Conversation.sequence`
already carries the comment explaining exactly this trap (`models.py:406-411`); it applied
identically here and the fix is the same shape.

Migration `0088` recreates the table (`batch_alter_table(..., recreate="always")`, SQLite cannot
move a primary key in place), guarded for a missing `checkpoints`/`projects`/`conversations` table
the way `0073`/`0087` are. Three call sites read `session.get(Checkpoint, checkpoint_id)`
(`api/v1/checkpoints.py` x2, `tests/test_handover_briefs_the_reviewer.py` x1) — `session.get()`
resolves by primary key, so all three would have silently stopped matching once `id` left the
primary key. Replaced with a new `hub/hub/checkpoints.py:get_checkpoint_by_id`, the same fix
`conversations.py:get_conversation_by_id` applied for `0073`. Four `order_by(Checkpoint.created_at.desc(), Checkpoint.id.desc())` call sites (`checkpoints.py` x3, `checkpoint_trigger.py`,
`api/v1/checkpoints.py`) now read `order_by(Checkpoint.sequence.desc())`.

Regression test: `tests/test_flow_checkpoint_lineage.py::test_latest_checkpoint_for_loop_breaks_a_tie_by_insertion_order_not_id`
— two checkpoints inserted with an explicitly identical `created_at` and ids chosen so the *older*
row's id sorts alphabetically *after* the newer one's (`ckpt-zzz-older` before `ckpt-aaa-newer`),
the exact shape that made the old tie-break pick the wrong row. Deterministic, not probabilistic:
under the old ordering this fails every run, not roughly half the time. Mutation-checked by
reverting `latest_checkpoint_for_loop`'s `order_by` to the old `created_at`/`id` tie-break — the
named test failed with the older checkpoint winning, exactly as predicted — then restored and
reconfirmed green. Full suite: `test_migrations.py` (71 passed, 1 skipped — the round-trip fixed
here), `test_flow_checkpoint_lineage.py`, `test_handover_briefs_the_reviewer.py`, six other
`test_checkpoint_*.py` files, and `test_project_persistence.py` all green (240 passed, 1 skipped).
`ruff` and `black --target-version py311` clean.

### What a reviewer should distrust

Verified against the regression suite, the migration round-trip tests, and a deliberate mutation —
not against a fresh live tie forced through the running trial Hub, since forcing two loop firings
into the identical clock tick live is not practical to stage on demand. The trial Hub restart that
picks this migration up is recorded in this iteration's log entry rather than here. The "likely
recurs anywhere else... ordered by timestamp with no monotonic tie-break" observation from the
original write-up was not re-audited this iteration; `CheckpointNote.created_at.desc(),
CheckpointNote.id.desc()` (`checkpoint_generation.py:404`) has the identical shape and was
deliberately left alone as out of scope for this finding — a candidate for a future finding, not
folded in here.

## F56 (A) — one review target with no evidence permanently wedges an agent's entire inbound queue, silently

**Status:** fixed 67b2c95

Found live 2026-08-26, at the very start of Q5, trying to do the thing Q5 asks for: trigger `critic`
to give a real verdict on `task-23a0986e7fe9`. `POST /agent/trigger` with `task_id:
"task-23a0986e7fe9"` returned `200`, `run_id: null`, and:

```
"waiting_reason": "queued task task-18e900f3eb96 has no recorded evidence, so there is no commit
to review. Evidence naming a commit is what a review turn is given."
```

`task-18e900f3eb96` is not the task I named, has nothing to do with it, and reads `status:
completed` in the database — the review the message is about was superseded over a day earlier.
Repeated with a second, independent trigger: identical refusal, identical unrelated task named.

### Root cause, traced through the code and confirmed against the live `inbound_queue_entries` table

`turn_scheduler.schedule_agent` picks `controlling`, the *oldest* still-`queued` entry for the
agent (`queued_entries` orders by `sequence`), regardless of what that entry is about, then batches
every other queued entry sharing its conversation and calls `trigger_agent_directly` with that
batch. If the batch's `review_task_id` resolves to a task with no evidence naming a commit,
`review_turn.prepare_review_turn` raises `ReviewTurnRefused`, converted to a `TriggerAgentError` and
raised **before any `Run` row is created**. `schedule_agent`'s `except TriggerAgentError` branch
(pre-fix) did nothing but return a `ScheduleResult` — it never touched the entries at all.

That matters because of exactly one asymmetry: `InboundQueueEntry.state` only moves to
`"delivered"` atomically *with* a `Run`'s creation (`inbound_queue.py`'s delivery-marking helper).
No `Run` here means no delivery, which means `delivery_attempts` — the counter
`return_run_entries` uses to abandon a poisoned entry at `DELIVERY_ATTEMPT_LIMIT` (3) — **never
increments**, because that bookkeeping only runs for a `Run` that was created and then failed. A
refusal raised before a `Run` exists is invisible to the one safety net designed to stop exactly
this class of problem ("the Hub stopped retrying" — `inbound_queue.py:174`'s own comment). The
entry sits `queued` forever, `controlling` is always it again on the next scheduling pass, and
every entry queued behind it — regardless of what *they* target — starves identically, forever.

Measured directly against the live `beta` database, `critic`'s queue on `proj-18e5d4e0`
(`ledger-stress`):

```
entry-1a37fe42ec46  queued  arrived 2026-08-25T00:10:00Z  review_task_id=task-18e900f3eb96  (job)
entry-078312a2652f  queued  arrived 2026-08-25T18:33:24Z  review_task_id=task-23a0986e7fe9  (job)
entry-1549fa5bbca5  queued  arrived 2026-08-25T23:43:32Z  task_id=task-3292072f63c3          (agent)
entry-c03602972249  queued  arrived 2026-08-25T23:47:14Z  task_id=task-bb86d53a94d5          (agent)
entry-fbeb63c07a21  queued  arrived 2026-08-26T00:32:17Z  task_id=task-23a0986e7fe9           (agent, mine)
entry-9d9904d9252b  queued  arrived 2026-08-26T00:35:20Z  review_task_id=task-0dfc3be5        (job)
entry-37c37a73155d  queued  arrived 2026-08-26T01:03:40Z  task_id=task-23a0986e7fe9           (operator, mine)
entry-942eb1bb30a4  queued  arrived 2026-08-26T01:03:53Z  task_id=task-23a0986e7fe9           (operator, mine)
```

The head entry (`entry-1a37fe42ec46`) arrived within seconds of `task-18e900f3eb96` completing —
plausibly a loop queuing its own next-step review the instant the task finished — and whatever
evidence that review needed was never recorded against it (or was recorded through a path that
doesn't name a commit). From that moment, **every subsequent attempt to talk to `critic` for over
24 hours, eight of them, spanning three different origin types and both real drive attempts this
session made**, silently piled up behind it with zero self-correction and zero signal to the
operator beyond a `200`-with-`run_id: null` response naming a task nobody asked about.

### Fixed live this iteration, `hub/hub/turn_scheduler.py`

A refusal from `trigger_agent_directly` that is not `workspace_unavailable` (an environmental,
not-the-entry's-fault condition already handled separately and correctly, via
`queue_agent_paused`) now counts against the same `delivery_attempts` /
`DELIVERY_ATTEMPT_LIMIT` bookkeeping `return_run_entries` already uses for a `Run` that spawned
and then failed — extended to cover the case that bookkeeping structurally could not see, a
refusal before any `Run` exists. At the limit, the entry is withdrawn with an `abandoned_reason`
naming the refusal, exactly like the existing "the Hub stopped retrying" path.

Regression test added (`hub/tests/test_failed_run_returns_input.py`,
`test_a_terminal_pre_spawn_refusal_abandons_the_entry_after_the_limit`): three triggers against an
agent whose `trigger_agent_directly` call is patched to always raise a terminal `TriggerAgentError`
assert `delivery_attempts` reaches `DELIVERY_ATTEMPT_LIMIT`, the entry's `state` becomes
`"withdrawn"` with a non-null `abandoned_reason` naming the refusal, and a fourth trigger for the
same agent proceeds past it rather than repeating the same wait forever. A second test asserts a
`workspace_unavailable` refusal does **not** count an attempt, preserving the existing
`queue_agent_paused` behaviour for an environmental block. Mutation-checked: reverting the `else`
branch to its pre-fix `pass` reproduces both new tests failing.

### Verified live against the actual wedge, not only against the regression test

Withdrew the specific poisoned entry by hand first (`DELETE
/projects/proj-18e5d4e0/queue/entries/entry-1a37fe42ec46` — the documented operator escape hatch,
confirmed to exist and work: `200`, `state: "withdrawn"`), which is the only way to unblock `critic`
*today* without restarting the Hub on the fixed code. Then re-triggered `critic` on
`task-23a0986e7fe9` with `review_task_id` set correctly this time: the response changed from a
misdirected refusal to `"an older conversation's queued input is being delivered first (run
run-45862ae056ff)"` — the queue moving again — and that run completed for real: `critic` was handed
an isolated checkout at the reviewed commit (`f10d198d5952f7fb7856...`), read the actual diff and
history (working out on its own that the code fix predated the commit under review and only the
tests were new — see F10's note below), ran the suite, and reached a genuine verdict (`APPROVED`,
`update_task` called, transition recorded). The Hub restart to pick up the code fix itself, and the
fixed code's own re-verification once running, are recorded in this iteration's log rather than
repeated here.

### What HELD

**F10 did not recur.** The reviewer's worktree was genuinely checked out at the commit its evidence
named, and it read the real diff rather than guessing — worktree isolation for a *review* turn
(`review_turn.prepare_review_turn`, design D4) works as documented. The escape hatch (`DELETE
/queue/entries/{id}`) also held: it is real, documented, and suffices to unblock an agent by hand
today, which is why this is severity A rather than "unrecoverable."

### What a reviewer should distrust

The withdraw route (`DELETE /queue/entries/{id}`) does not itself call `schedule_agent` afterward
(`release_queue_entry` does; `withdraw_queue_entry` does not) — clearing the head entry did not
wake the rest of the queue on its own; a fresh trigger was what actually nudged it. Not written up
as its own finding — a fresh trigger is an ordinary thing an operator would do next regardless —
but worth knowing if a future session sees a withdrawal that appears to do nothing.

The Hub code fix itself was verified against the real async DB layer through the regression test
(no mock session — `async_session_factory` against a real, if temporary, SQLite database), plus
mutation-checked. It was **not** separately re-poisoned against the running trial Hub after
deploying it: the trial Hub was restarted on the fixed code this iteration (confirmed back on the
`beta` database, all five projects present, all twelve `ai_jobs` rows still `enabled: 0`), but
building a fresh three-refusal reproduction live would have meant deliberately wedging another
agent's queue to prove it un-wedges itself — judged not worth the extra live disruption once the
mechanism was already confirmed live once (the escape hatch) and unit-tested against the real
query path the running process uses. Flagged here rather than silently assumed equivalent.

## F57 (A) — a rejection has no way to say why: `update_task` drops `notes` entirely

**Status:** fixed 31c8639

Found live 2026-08-26, tracing the "does rejection route back legibly" half of Q5. During the
`critic` self-drain that produced a real `revision_needed` verdict on `task-0dfc3be5`
(`run-e842f20908da` — see F10's "lookalike" note above for the rest of that transcript), `critic`
did substantial, real review work: read the diff, traced the empty-postings logic, wrote out a
line-by-line verdict, and called `update_task("task-0dfc3be5", "revision_needed")`. Checked against
the live `tasks` row afterward: `notes` and `deliverables` are both `null`. Every word of the
reasoning above lives only in the run's own transcript — nowhere the task record itself, the board,
or a later reader of the task carries it forward.

### Root cause

`hub/hub/mcp_server.py`'s `update_task` tool, before this fix, took exactly two parameters:

```python
def update_task(task_id: str, status: TaskStatus) -> Dict[str, Any]:
    ...
    return _hub_request("PATCH", f"/tasks/{task_id}", {"status": status})
```

The REST route it calls, `PATCH /tasks/{id}` (`TaskUpdate`, `hub/hub/schemas/tasks.py`), has always
accepted `notes: Optional[Any]`, and `update_task_for_actor` (`hub/hub/api/v1/tasks.py:1172`) has
always applied it (`if body.notes is not None: task.notes = body.notes`). The capability exists
end-to-end on the API; the *tool an agent is actually given* just never offered it. An agent moving
a task to `revision_needed` or `rejected` has no tool parameter to attach a reason to the task
itself — only `send_message` to the author (which does not appear on the task record) or the run's
own transcript (which an operator glancing at the board does not read).

This is not a hypothetical gap: it is the exact mechanism behind the `task.notes`/`deliverables`
being `null` that iteration 8 flagged as "a plausible gap, not yet confirmed" — confirmed here.

### Fixed live, `hub/hub/mcp_server.py`

`update_task` gains `notes: Optional[str] = None`, forwarded unconditionally in the PATCH body
(`{"status": status, "notes": notes}`). Sending `notes: null` on a plain status-only call is safe
and does not clobber existing notes: the route's own gate is `is not None`, not
`model_fields_set`, so an explicit `null` and an absent key are handled identically by the consumer
— read directly at `hub/hub/api/v1/tasks.py:1172` before relying on it, not assumed. The docstring
states plainly that omitting `notes` on a rejection leaves the author with nothing but a status
change, and that a fresh call overwrites rather than appends (there is no separate "append" verb),
so a second-round rejection needs to restate what still matters from the first.

Regression test added, `hub/tests/test_mcp_server.py`,
`test_update_task_forwards_notes_so_a_rejection_is_legible_on_the_task_itself`: asserts the exact
body sent to the Hub carries the reviewer's reasoning verbatim under `notes`. The pre-existing
`test_task_tools_use_agent_ledger_endpoints_without_assigner` was updated for the body's new shape
(`{"status": "completed", "notes": None}`) rather than left to rot. Mutation-checked: stashing just
`hub/hub/mcp_server.py` reproduces `update_task() got an unexpected keyword argument 'notes'` on the
new test; unstashing restores green. `ruff` and `black --target-version py311` clean on both touched
files.

### What a reviewer should distrust

Verified through the regression suite and by reading the exact consuming line in
`update_task_for_actor`, not by driving a fresh live rejection through a real agent turn — the
mechanism this fixes was already caught in the act live (the `task-0dfc3be5` transcript above *is*
the live evidence; the fix closes the exact gap that transcript exposed), so a second deliberately
staged live rejection was judged not worth spending another cheap-model turn on. The trial Hub was
restarted onto this fix and reconfirmed on the `beta` database (five projects, all twelve `ai_jobs`
rows still `enabled: 0`) before this was written up, but no new live rejection was driven through
the restarted process specifically to re-observe `notes` landing non-null. Flag if a future session
wants that extra rep — `task-0dfc3be5` is still sitting `revision_needed` and is a ready-made target
for exactly that, once a reviewer is triggered on it again.

## F58 (A) — approving one task's evidence merges its agent's *entire branch history*, including other unapproved tasks' work and scratch debris, not "the commit the evidence names"

**Status:** fixed 9993c0f (the `work-is-isolated-per-task` merge), CI-green at e78c119

Found live 2026-08-26, driving Q5's undriven F9 half to a full landing commit for the first time
this run. `task_integration.py`'s own module docstring states three rules "each exists because the
naive version damages a repository," and the first is: **"Merge a commit, never a branch... Merging
the branch when one task is approved would ship the others. The accepted evidence already names the
commit the work was demonstrated at; that is what goes in, and anything committed after it stays
out."** `hub/tests/test_task_integration.py::test_later_commits_on_the_branch_are_not_merged`
restates the same guarantee in its own docstring: "D1: what merges is the commit the evidence names,
not the agent's branch. If this test fails, approving one task ships another task's unreviewed
work." That test is green on this branch tip. The guarantee it names is false anyway.

### What actually happened, live

Sequence, on `ledger-stress` (`proj-18e5d4e0`): `task-0dfc3be5` (FR-2) went `revision_needed` ->
(builder revision turn, `run-8c7dda053998`) -> `completed` -> (operator `task-set`) ->
`under_review` -> (critic review turn, `run-d7e30a9c650d`) -> `approved`
(`task_transitions.sequence=95`). Its newest evidence, `ev-57bfd7d6552f`, named commit
`d64b43dffe9666585b383981efb3b91d2125a0e7` on branch `agentweave/builder`. As operator, accepted
that evidence (`POST .../project/spec/evidence/ev-57bfd7d6552f/decision`), confirmed
`integration-preview` then reported `will_merge: true` naming exactly that one commit, and called
`POST .../tasks/task-0dfc3be5/integrations/retry`. Outcome: `merged`, landing commit `9e593f2` in
the subject repo (`C:\Users\huida\Documents\aw-stress`, confirmed by `git log`/`git show --stat`
directly against the repository, not the Hub's own account of it).

**The merge commit's diff carries 13 files, not the evidence commit's own diff.** Alongside the
real fix (`ledger/book.py`, `tests/test_ledger.py`), it also landed: `commit.sh`,
`commit_account_validation.py`, `do_commit.py`, `verify_empty_entry.py`, `verify_fix.py` — scratch
scripts the agent wrote for itself across earlier, unrelated turns — and **`tests/test_account_order.py`**,
which `git log --all -- tests/test_account_order.py` traces to commit `90aa643`, the test for
**`task-e6b05093`** ("Make account ordering stable", FR-3) — a *different task*, still sitting
`assigned`, never reviewed, never approved, no evidence accepted for it at all.
`git log --oneline fbeeb26..d64b43d` (`fbeeb26` was the branch's previous integration point) lists
**16** auto-snapshot commits, and all 16 landed on `master` from the single accepted-evidence commit
at the tip.

### Root cause

`task_integration.integrate()` (`hub/hub/task_integration.py:265`) runs:

```python
_git(root, "-c", ..., "merge", "--no-ff", "-m", f"Integrate approved work {sha[:12]}", target.commit_sha)
```

`git merge --no-ff <sha>` brings in **every ancestor of `<sha>` not already in the target branch** —
the commit's entire history back to the merge-base — not the tree at `<sha>` applied as a patch.
`test_later_commits_on_the_branch_are_not_merged` only ever commits *after* the accepted evidence
and asserts those are excluded; commits *after* a target are never ancestors of it regardless of
merge-vs-cherry-pick, so that test cannot fail no matter which mechanism is used — it is the F43/F52
shape again: a fixture that cannot distinguish the two implementations it exists to tell apart.
Nothing in the suite commits *earlier*, unrelated work on the same branch and asserts it stays out —
the one scenario the docstring's own words promise and the one this live drive actually hit.

### Severity and blast radius

This is not a narrow edge case: `worktrees.branch_name` is per-*agent* (stated in this same module's
docstring), so **every** builder agent's branch accumulates every task it has ever touched, in
commit order. The first evidence acceptance on *any* task on that branch ships the *entire* prior
history of that branch — every other task's work-in-progress, however unreviewed, however far from
`approved`, plus any scratch/debris file the agent happened to leave uncommitted at end-of-turn
(auto-snapshotted unconditionally by `worktrees.snapshot_worktree`, per F52's finding). The review
gate this module exists to enforce is real for the *task being approved* and decorative for
everything else that happens to share its agent's branch. An operator reading `integration-preview`
or the `integrations` history sees one commit sha named and reports it as "what landed" — the UI has
no rendering of the other 15 commits that rode along.

### Not fixed this iteration

This needs a real design decision, not a one-line patch, for the reason `[[F53]]` and `[[F55]]` were
also left open rather than patched in place: the *correct* narrower semantics is not obvious.
Candidates, un-evaluated: (a) `git cherry-pick <last-integrated-on-this-branch>..<target>` — bounds
the merge to "what's new since this branch's last approved landing," which is materially tighter but
still not per-task if two tasks' work is interleaved commit-by-commit on one branch; (b) a true
single-commit cherry-pick of `<target>` applied as a squashed diff against its merge-base, which
is closest to the stated intent but changes conflict semantics and needs its own test matrix; (c)
per-task worktrees instead of per-agent, which is a much larger change. Left for Q6, and flagged
as the highest-severity item in that pass — it directly contradicts this module's own stated design
guarantee and both existing tests that claim to cover it.

### Blast radius made visible, iteration 12 — the merge shape is still unchosen, this is not the fix

Q6, decision-free sub-piece, per the operator's own framing of the option: reduce F58's blast radius
by naming what rode along, without picking a merge-semantics redesign no one has decided on yet.
`task_integration.commits_riding_along()` runs `git rev-list --reverse <main_branch>..<commit_sha>`
*before* the merge (the same query returns nothing once the merge has run, because the target is by
then reachable from main) and records every commit besides the target itself. Persisted on
`TaskIntegration.rode_along_commits` (migration `0089`, plain `ADD COLUMN`, no table recreate needed
unlike `0088`), exposed on `GET .../integrations` as `rode_along_commits: string[]`, and rendered as
an amber warning line under a merged row in `TaskIntegrationNote.tsx` — the UI previously discarded
`reason` entirely for a `merged` outcome (confirmed by reading the component before touching it), so
folding this into `reason` instead would have been invisible on screen, a mistake worth naming since
it is exactly the "passes its test but cannot fire in production" shape this run keeps finding.

Regression test `test_rode_along_commits_names_what_actually_landed` (`hub/tests/test_task_integration.py`)
builds a branch with an earlier, unrelated commit before the evidence-named one, approves, and
asserts the earlier commit **still lands** (the bug is unchanged) **and is named** in
`rode_along_commits`. Mutation-checked twice: reverting `base.rode_along = rode_along` to `[]` in
`task_integration.py` fails the new test with the exact list diff predicted; commenting out the
UI's render guard (`{merged && rodeAlong.length > 0 && (...)}`) fails
`warns when other commits rode along with a merge (F58)` by making the `getByTestId` query find
nothing, in both cases restored and reconfirmed green afterward. `test_later_commits_on_the_branch_are_not_merged`
gained one assertion (`rode_along_commits == []` for a clean single-commit branch) to cover the
negative case in the same run. `ruff`/`black --target-version py311`/`tsc --noEmit`/`eslint` all
clean on every touched file; `hub/tests/test_task_integration.py` (26/26),
`test_migrations.py`+`test_project_persistence.py` (78 passed, 1 skipped, head bumped to `0089` in
both) and the UI's `taskIntegrationRetry.test.tsx` (8/8) all green. Not verified live against the
trial Hub this iteration — see the log for why (a full-suite background run took priority) — so
treat the live-fire claim as unverified until a future iteration restarts the trial Hub onto this
migration and re-drives an approval with a multi-commit branch.

F58 itself is unchanged: the same 13-file, 16-commit merge this finding describes would still happen
today, now with a warning line the operator can actually see. The redesign (candidates a/b/c above)
remains the operator's decision.

### What HELD

The conflict-then-abort path is real and clean: this same live drive hit an actual
`CONFLICT (modify/delete)` (self-inflicted — see below) on a first retry attempt, and
`task_integration.integrate()` ran `git merge --abort` and left the subject repository in a
genuinely clean state (confirmed by `git status` showing no `CHERRY_PICK_HEAD`/`MERGE_HEAD`, no
conflict markers, tree clean) — recorded as a `failed` integration row with the real git conflict
text, not a corrupted checkout. `has_uncommitted_changes`/`CHECKOUT_DIRTY` also fired for real and
correctly refused rather than merging over a dirty tree (see below), and `retry` correctly created a
fresh append-only row each time rather than mutating a past one.

### A second, unrelated but real thing this drive found and cleaned up

`ledger/__pycache__/*.pyc` and `tests/__pycache__/*.pyc` were tracked in git in the `aw-stress`
subject repo since its very first commit (`edc23dc`, 2026-08-23), the product of an earlier
session's project-seeding step using a broad `git add` rather than staging explicit paths — the
exact mistake this run's own standing limits warn against. Any turn that runs the test suite (both
`builder` and `critic` did, live, this iteration) regenerates those `.pyc` files and dirties the
tracked checkout, which silently blocks every future `integrations/retry` with `CHECKOUT_DIRTY` until
an operator manually commits or discards them — with no affordance in the product to tell the
difference between "real uncommitted work" and "regenerated bytecode cache." Untracked
(`git rm -r --cached`, `.gitignore` added, committed as `c421f07`) as real, needed housekeeping of
the test fixture, not an AgentWeave code change. This directly caused the first `merge` attempt's
`CONFLICT (modify/delete)` above (removing the files on `master` while the evidence commit still
modified them) — reverted (`git reset --hard fbeeb26`) before the successful retry so the fix
candidates above are evaluated against the real bug, not a self-inflicted one.

### What a reviewer should distrust

The landing commit `9e593f2` and its 13-file diff were read directly from `git log`/`git show` in
the subject repository — not taken from the Hub's own report, which only ever names the one
`commit_sha` it targeted. The claim that all 16 ancestor commits belong to *this agent's own* prior
work (rather than, say, another agent's) was traced only as far as confirming they are all
`Auto-snapshot: builder's turn` commits by the same agent — not independently verified against
`runs`/`task_transitions` one by one. No fix was attempted this iteration; this is a finding and a
design question, not yet a patch.


## F59 (B) — the same clock-tick tie-break bug as F55, in a second table: an evidence review's "latest" can pick the older decision

**Status:** fixed 31c3825

Found 2026-08-26, Q9's full-suite sweep run early (an iteration reconciling stale `STATE.json`/log
bookkeeping used the time waiting on a background full-suite run to also finish it properly, having
been lost across a process boundary twice in prior iterations). The suite reported exactly one
failure: `test_evidence_latest_review_signal.py::test_a_later_acceptance_replaces_the_reason_shown`.
Re-run bare, six times, on the unmodified branch tip: **3 of 6 failed**, alternating pass/fail with
no code change between runs — the same intermittent shape F55 was chased down as, not a flake to
shrug off.

### Root cause, read from the code, not inferred

`_latest_reviews_for` (`hub/hub/api/v1/spec.py:1093-1116`) and `reviews_for`
(`hub/hub/requirement_evidence.py:515-521`) both answered "which review is latest" (and, for the
second, "in what order did they happen") by
`order_by(EvidenceReview.created_at, EvidenceReview.id)`. This is the *exact* shape F55 fixed for
`Checkpoint` two migrations earlier in this same run — same measured cause: `datetime.now()` on
this machine can return an identical value across consecutive calls (Windows clock resolution
coarser than the microsecond precision the value implies), so two decisions recorded back to back
— an operator rejecting then immediately accepting, or two automated decisions in the same
turn — land in the same tick more often than not. `EvidenceReview.id` cannot break the tie
either: it is `evr-` + a random short id with no relationship to insertion order, so roughly half
the time the tie-break picked the *older* review as "latest" and the operator was shown a stale
decision and its stale reason, silently, with no error anywhere.

### Fix — the same shape F55 already established

`EvidenceReview` gained a `sequence` autoincrement primary key (migration `0091`,
`hub/hub/db/models.py`), exactly mirroring `Checkpoint.sequence`'s reasoning and shape. Both
ordering call sites now read `order_by(EvidenceReview.sequence)` — a real insertion-order key the
database hands out itself, immune to clock resolution. No `get_by_id`-style helper was needed
(unlike `Checkpoint`): no `session.get(EvidenceReview, ...)` call site exists anywhere in the
codebase, checked before writing the migration, so nothing looks an `EvidenceReview` up by its
string id via the ORM identity map.

**A real, second bug caught during verification, not authored by the fix itself.** The
`_columns()` existence guard originally checked only `{evidence_reviews, projects,
requirement_evidence}`. Running the full migration test suite immediately surfaced 14 additional
failures across `test_migrations.py`/`test_project_persistence.py` — `NoSuchTableError: tasks`,
thrown from *inside* `batch_alter_table(..., recreate="always")`'s own reflection, not from this
migration's guard. Traced: `evidence_reviews.evidence_id` FKs to `requirement_evidence`, and
`recreate="always"`'s batch mode reflects that FK target table to preserve the relationship across
the recreate — which in turn reflects `requirement_evidence.task_id`'s own FK to `tasks`. The
several tests that synthesize an upgrade chain starting from a stamped-but-not-materialised early
revision (the same shape `test_migration_00NN_is_guarded_when_tasks_does_not_exist` exists to
cover for *other* migrations) never create `tasks` at all in that chain, so this second-order
reflection raised before this migration's own guard logic ever got a chance to matter. Fixed by
adding `tasks` to the guard's required-table set, with the reasoning written into the migration's
own docstring so the next person editing a table that FKs into `requirement_evidence` does not
rediscover this by a red suite. This is the third distinct instance in this run of a migration's
own reachability guard being insufficient in a way only the *full* migration suite catches — F53's
`downgrade()` missing-table guard and this one are the same species, and the standing rule ("run
the whole migration suite, not just the new test, before calling a migration done") held again
here specifically because it was followed.

**Regression test** (`test_latest_review_breaks_a_tie_by_insertion_order_not_id`,
`hub/tests/test_evidence_latest_review_signal.py`): constructs two `EvidenceReview` rows directly
against the ORM with an identical `created_at` (read from the real evidence row, not synthesized)
and ids chosen adversarially — the *older* row's id (`evr-zzz-older`) sorts alphabetically *after*
the *newer* row's (`evr-aaa-newer`) — the exact shape that picked the wrong row under the old
ordering. Asserts both `_latest_reviews_for` (the "which is latest" query) and `reviews_for` (the
full-history query, which must read chronologically, not just get the endpoint right) pick by
insertion order. **Mutation-checked**: reverted both `order_by` call sites to
`.order_by(EvidenceReview.created_at, EvidenceReview.id)`, reran — the new test failed with the
predicted assertion (`assert 'evr-zzz-older' == 'evr-aaa-newer'`); restored, reconfirmed green.
Bare-reran the originally-flaky test 8 consecutive times post-fix: 8/8 passed, where the unmodified
tip had failed 3/6. `ruff check` and `black --check --target-version py311` clean on all seven
touched files (three source, one migration, three test). Broader slice
(`-k "evidence or spec or agent_actions or requirement"`, 837 tests): 817 passed, 20 skipped, 0
failed.

**Verified LIVE**, not only against the fixture. Restarted the trial Hub on the beta database
(confirmed via a direct query, not `/health` alone: `alembic_version` reads `0091`, and
`evidence_reviews.sequence` is populated `1..3` in original insertion order on the three
pre-existing rows). Posted two real decisions back to back over HTTP against a genuine `awaiting`
evidence row on `ledger-stress` (`ev-9ab3be95`, project `proj-18e5d4e0`) — reject, then
accept — using the operator's own bootstrap API key: the response after the second call correctly
read `review_state: "accepted"` and `latest_review.reason` naming the second call's text, not the
first's. Confirmed from the database directly afterward: `sequence` values `4` then `5` for the two
new rows, `evr-...` ids in no particular alphabetical relationship to which came first — insertion
order, not id, is what the response actually followed. Job sweep immediately after, all five
projects: fourteen `ai_jobs` rows, all `enabled: 0`.

**What a reviewer should distrust:** the live HTTP round-trip above did not land in the identical
clock tick (real network/API latency separated the two calls by ~50ms, `04:36:50.241` vs `.290`),
so it demonstrates the fix works correctly on the real path end-to-end but does not itself
reproduce the original tie live — the tie itself is proven only by the mutation-checked unit test,
which forces it deterministically rather than hoping for a coincidence. This is the same
distinction F55's own live verification drew for `Checkpoint`.

## F60 (A) — An unanswered `ask_user` question that resolves itself mid-turn leaves the task reading `completed`, and the operator can still "answer" it afterward into a state that contradicts the code that shipped

**Status: FIXED 2026-08-30**, `a-task-waits-while-its-run-waits`, part (b), shipped with F14 in the
same change. `033ec4c`'s `_asker_is_gone` guard predates the filing and stands.

**What shipped.** `Question` records the deadline of the wait it starts and when that wait ended
(migration `0099`). The deadline is computed **Hub-side** from the Hub's own inputs — the agent's
`question_timeout_seconds`, the environment the Hub builds, and `_configured_wait`'s own default and
range, restated with an agreeing test. Rounds 1 and 2 had the ask send `wait_seconds`; round 3
overturned it, because that number would have arrived over the run's own credential and the refusal
that keeps an expiry a report of a fact rather than a lever would have compared the report against a
number the reporting party chose.

`ask_user` reports its expiry to `POST /questions/wait-ended` — not an `@mcp.tool()`, so no model can
be prompted into calling it — and the report releases the parked task. The run's **end also sweeps**,
because rounds 1 and 2 had merged "the report was never sent" with "the report was sent and did not
land": task 5.5 requires the second to be swallowed, so the agent proceeded and the task would sit
`blocked` with its own agent unable to record the work. `expire_permission_request` in the same
router already stated that design in one line — *"The run reports and the run's end sweeps"* — and
this now takes both halves.

The task then carries `proceeded_without_answer_reason`, **permanently**. That is the assertion this
finding exists for: it measured the operator answering five minutes after the run ended, choosing the
option the agent had not shipped. If the answer cleared the record, it would disappear at the exact
moment it became most misleading.

**Confirmed live** (`t_f14_f60_wait_parks_the_task.py`, phase B, agent timeout set to the Hub's
minimum): the task parked, the wait ended on its own after ~9s, the task returned to `in_progress`,
the agent's completion was no longer refused, the finished task read *"Proceeded without your answer:
Which colour should the badge be?"*, the conversation rail stopped saying waiting — and answering the
question afterwards did not erase the record.

**One surface family the change had to correct on the way.** `wait_ended_at` introduces a state that
did not exist — unanswered, undeclined, and nobody waiting — and five surfaces derived "somebody is
waiting" from `answered = False`. Two were fixed by the predicate; round 3 found three more. The
conversation rail and a loop's open-question count are excluded, because their audience is the
operator; a checkpoint's `open_questions` **keeps** the entry and marks the wait as ended, because
its audience is the successor agent, which needs to know a decision was taken without anybody.
`scheduler._pending_loop_request` is a sixth reader with a real defect of its own (no `declined`
exclusion at all) and is deliberately out of scope — it is about a loop's stop reason, not about who
is waiting.

Driven live (Q8), following the method's own directive to leave a question deliberately
unanswered. `proj-8605b92d0028`'s `author` agent (Haiku, cheap runner) was told, honestly, to ask
the operator a structured question before touching `task-a9f72e6c80f8` (the `is_low_stock` float
equality bug) and to wait for an answer. It called `ask_user` with three labelled options
(`q-6080bf46c57c`, `blocking: true`). The question was left unanswered on purpose.

**During the wait**, polled every 10s against the live database for the full 290s the turn actually
ran: `runs.status` stayed `running`, and `tasks.status`/`blocked_reason` stayed `in_progress`/`None`
the entire time. This reconfirms **F14** exactly as documented — nothing on the task tells the
operator their agent is sitting on a question.

**What happens after the wait is worse than F14's own write-up anticipated it would be.** F14 says
a task only parks to `blocked` "if the run **ends** with the question unanswered" — implying that
when the run does end, the operator at least sees the task stall visibly. That is not what
happened. `QUESTION_ANSWER_TIMEOUT` (240s) expired inside the tool call; the agent's own transcript
shows it correctly reasoning about the timeout ("The question was not answered within the
timeout... I'll proceed with the most straightforward approach based on the approved
specification"), picked "Direct `<=` comparison" by reading FR-3 itself, made the code edit, ran the
tests, and — in the **same turn** — called `update_task` to set `task-a9f72e6c80f8` to `completed`.
By the time `run_divergence.evaluate_run_end` ran at the true end of the run, the task was no
longer `in_progress` (the agent had already moved it), so `block_task_for_question` had nothing to
park. The run ended `completed`, not `stopped`/`failed`. Confirmed from the rows, not the
transcript's own account: `tasks.status = 'completed'`, `blocked_reason = None`, and
`questions.answered = 0`, `declined = 0`, `blocked_task_id = None` — the question was never parked,
never declined, never linked to anything. It simply stopped being anyone's problem.

**The board now shows a clean, completed task.** Nothing on `task-a9f72e6c80f8` — not its status,
not `blocked_reason`, not any field the task API exposes — indicates that a substantive judgment
call (which comparison semantics to ship) was made unilaterally by the agent after the operator
failed to respond in time. An operator scanning the board for problems would not find this one; they
would have to separately check the questions list and notice a `blocking: true` question with
`answered: false` that no longer has any visible connection to the now-completed task.

**Compounding it: the question can still be "answered" after the fact, into a value that
contradicts the shipped code, with no error and no warning.** Five minutes after the run ended,
`PATCH /api/v1/projects/{id}/questions/q-6080bf46c57c` with `{"answer": "Epsilon-based tolerance"}`
(deliberately the option the agent did *not* pick) returned `200` and recorded `answered: true`,
`answer: "Epsilon-based tolerance"`. Nothing rejects answering a question whose asking run has
already ended, and nothing reconciles the late answer against what actually shipped. The task still
reads `completed` with the `<=` comparison in its worktree; the question record now claims the
operator chose epsilon tolerance. An operator who answers questions from a queue without checking
timestamps would walk away believing they made the decision that shipped, and would be wrong.

**What held:** the timeout itself is real and bounded — `ask_user` did not hang the turn forever,
and the agent's handling of the timeout (falling back to the spec's own explicit language rather
than inventing an answer) was reasonable, arguably the best available behavior for *that* Haiku
agent in *that* turn. The gap is entirely in what the Hub records and surfaces afterward, not in
the model's own judgment call.

Not fixed this session — recorded as a Q8 drive finding per the queue's own discipline (drive items
record, fix passes fix). The shape of a fix is not obvious enough to guess at here: closing the
"question answered after its run ended" hole is a straightforward guard
(`questions.py`'s PATCH handler could refuse or warn when `created_by_run_id`'s run is no longer
`running`), but making the *board* surface "this completed task shipped on an unanswered question"
durably — after the task has already left `in_progress` — is a design decision (a task-level flag?
a distinct completion state? surfaced only via the questions list forever?) that belongs with F14's
own eventual fix, not bolted on separately.

## F61 (B) — every flow conversation has the same title, and no API says which turn is a review

**Status:** open — the operator chose the fix (title a flow conversation by its agent and role) and it is not implemented

Found 2026-08-26 by the **operator**, judging group 11's check 11.2 ("the handover is legible")
against the live trial Hub. This is the first finding in this series produced by a human judgement
call rather than by a drive script, which is the point of group 11 existing.

The routing underneath is correct and was confirmed first, so that the finding is about legibility
and not about mechanism: eight `inbound_queue_entries` on `proj-18e5d4e0` carry a `review_task_id`
(`entry-b3b2decb5bd3`, `entry-bdbff2b6d33b`, `entry-078312a2652f`, `entry-abb2e8c3855e`,
`entry-9d9904d9252b`, `entry-695a53e2517d`, `entry-f54274ebd7f8`, and `entry-1a37fe42ec46`, the
last of which is `withdrawn` — F45's fix visibly working). The scheduler routed every one of them.

**What the operator cannot see.** Two halves, same gap:

1. **Eleven conversations, one title.** `select id, title from conversations where title like
   '%flow%'` returns eleven rows on this project, every one titled `Ledger flow`, spanning three
   agents (`builder`, `critic`, `relay`) and two roles (work, review). Nothing in the title says
   whose turn it is or which kind. The overnight drive took this from six to eleven, so the
   condition worsens with exactly the usage the feature is for.
2. **`review_task_id` is exposed on no API.** `GET /projects/{id}/queue/{agent}` returns
   `abandoned_reason, agent, arrived_at, content, conversation_id, delivered_in_run_id,
   delivery_attempts, hop_depth, id, origin_agent, origin_type, state` — and `grep -n
   "review_task_id" hub/hub/schemas/*.py` matches nothing. The one field that makes an entry a
   review is readable only by opening the database directly, which is what this session had to do.

So the product knows which turn is a review, records it correctly, acts on it correctly, and tells
the operator through neither the UI nor the API.

**Operator's chosen fix:** title a flow conversation by its agent and role, so the activity list
distinguishes a review turn from a work turn on sight. Whether `review_task_id` also belongs on
`QueueEntryResponse` was offered alongside and not selected — the title is the fix.

**What held:** the routing, the `review_task_id` stamping, and F45's withdrawal path are all real
and correct in the rows. Nothing here is a behavioural defect; it is entirely a surfacing one.

**A correction to the runbook, worth carrying:** `group-11-runbook.md` states that the handover
"involved no messaging at all" and that no message carries a `task_id`. That was true when it was
written on 2026-08-25. It is not true now — thirteen messages on this project carry a `task_id`,
`builder` <-> `critic`, from 2026-08-25 23:43 onward, produced by the overnight drive. Both handover
shapes now exist here: silent routing by the scheduler, and agents messaging each other about
tasks. Judge against the live rows, not the runbook's snapshot of them.

## F62 (C) — a mixed-CLI flow reports its tokens in full and its money in part

**Status:** open (no fix commit references it); recorded rather than blocked on

Found 2026-08-26 by the **operator**, judging group 11's check 11.6 ("the spend is visible"), and
recorded rather than blocked on — the check passes, this is the caveat attached to the pass.

`GET /projects/proj-18e5d4e0/accounting` answers in one call with no reconstruction from runs:
34,717,146 tokens over 65 measured turns (1 unavailable), `api_equivalent_usd_micros: 7832067`,
split `builder` 21.85M / `critic` 12.55M / `relay` 322k. That is what the check asks for and it
arrives early enough to act on, which is why 11.6 is a pass.

**The gap:** `relay` reports `total_tokens: 322085` and `api_equivalent_usd_micros: null`. The
dollar figure is not computed by the Hub from tokens and a price table — it is taken from the CLI's
own report, `total_cost_usd` for Claude and `cost` for Codex (`runner_parsing.py:339` and `:641`),
and the Codex CLI does not send one. So the project total of ≈$7.83 is the sum of the turns that
*could* be priced, and silently excludes every Codex turn. On this project that is 10 of 65 turns
and a small amount of money; on a Codex-heavy flow it would be most of the spend, and the total
would still render as though complete.

Severity C rather than B because the tokens — which are complete, per-agent, and the thing an
operator can actually act on before leaving a flow running — are all correct, and because nothing
here is wrong, only partial. Two shapes if it is ever fixed: price Codex turns from tokens against
a model price table (introduces a second, estimated source of truth for money), or mark the total
as partial whenever any contributing turn had no cost report (honest, cheaper, and does not
pretend to a number the CLI never gave).

## F63 (B) — the board says an agent is mid-turn on work nothing is running; two meanings of "in flight" collided

**Status:** fixed 2717687

Found 2026-08-26 by the **operator**, judging group 11's check 11.5 ("is concurrent work
comprehensible?") against a live firing of the `Width bench` flow (`job-f632ee565238`) on
`proj-18e5d4e0`. The third finding in this series produced by a human judgement call.

### What happened, live

One firing, two turns staffed — the concurrency itself worked. Afterwards the loop card read:

```
task-bb86d53a94d5  Reject a posting with an unknown account code   relay    working
task-948637265cb0  Report the trial balance in account-code order  builder  next
```

`task-948637265cb0` is right. `task-bb86d53a94d5` is not: its review run **failed**
(`run-cd011fb845ce`, `error_summary: "task task-bb86d53a94d5 has no recorded evidence, so there is
no commit to review..."`), `firing_active` was `False`, and a direct query for non-terminal runs —
`select id, agent, status, task_id from runs where status not in
('completed','failed','stopped','interrupted')` — returned **zero rows**. Nothing anywhere was
running. The board said `relay` was mid-turn on it anyway.

### Root cause — one word meaning two things

`scheduler.py:1220`, in the `under_review` arm of the queue walk:

```python
if task.assignee:
    in_flight.append((task.id, task.assignee))
continue
```

Unconditional, and **deliberately so**. Its own comment says why: *"Recorded as in-flight rather
than skipped, for finding F23's reason: a bare `continue` removes the row from the board... It is
also what makes a review that ended without a verdict visible -- the task stays here with its
reviewer named, which is a stall the operator can see and act on, where F45 was a spend loop they
could not."* For the scheduler, `in_flight` means **"this firing cannot staff anybody onto this"**.

`api/v1/jobs.py:381` then reads the same collection:

```python
if task.id in working_by_loop.get(task.loop_id, ()):
    entry["agent_role"] = "working"
```

whose own comment defines the word differently: *"`working` — this agent is mid-turn on it."*

Both comments are correct about their own side. Neither is correct about the other. An
`under_review` task whose reviewer is not currently running satisfies the scheduler's meaning and
violates the board's, and there is no third state for it to fall into.

### Why it surfaced now and not before

This is the third finding in the F26 / F49 family, and it exists *because* F49 was fixed. F26 was
"the board names a different agent than the task's assignee"; F49 was "`agent_role` could never say
`working`", because the membership test asked a bare `task.id` against a set of `(task_id, agent)`
tuples and never matched. F49 made the branch reachable for the first time since F26 shipped — and
the first live firing after that fix reached it in a case where it is wrong. A branch unreachable
in production for its whole life is a branch nobody could have found this in.

### The fix the operator chose

A **third role**, rather than narrowing `in_flight` or consulting the runs table from the renderer:

- `working` — a non-terminal run genuinely exists for this task;
- `held` — a reviewer owns it and nothing is running (the verdict-less review, the failed review
  turn, the task waiting on a person);
- `next` — this is who the next firing would give it to.

Rejected alternatives, recorded so they are not re-proposed: having `jobs.py` check the runs table
and downgrade `working` to `next` (loses the distinction between "waiting on a reviewer" and
"queued for the next firing", which is exactly the distinction F23 asked for), and splitting
`FiringDecision.in_flight` into two fields in the scheduler (cleanest at the source, but touches
every consumer for a defect that is entirely in one renderer).

### What HELD

The concurrency itself. One firing, two `JobRun` rows, two conversations, two independent outcomes
— and two rows for one tick is correct rather than a duplicate, because a single row could not say
that one turn finished and one failed. Both **F49** and **F56** were confirmed working in this same
firing: `agent_role` reached `working` at all (F49), and the review turn that could not be given a
commit refused with a stated reason rather than silently wedging `relay`'s inbound queue (F56) —
all three agent queues were checked afterwards and none is wedged.

## F64 (B) — one unstaffable queue, two surfaces, two different causes, opposite remedies

**Status:** fixed 2717687

Found 2026-08-26 by the **operator**, judging group 11's check 11.4 ("does rung 3 read as staffing
or as breakage?") on a live firing of the `Stall bench` flow (`job-453b909ba418`).

**Setup, live:** `critic` and `relay` archived, leaving only `builder` — who authored
`task-18e900f3eb96` (`task_transitions` sequence 68 `assigned -> in_progress` and 69
`in_progress -> completed`, both `actor_agent: builder`) and is therefore excluded from reviewing
it. Two completed tasks in the loop, nobody permitted to take either.

**What rung 3 says**, emitted as a `review_unstaffed` event, severity `info`
(`_emit_review_unstaffed`, fed from `FiringDecision.unstaffed`):

> could not staff this step: no agent is free to take it. Every agent on the roster is either
> running a turn, already holding active work, or is the one that completed this task and so may
> not review it.

This is **correct and was judged a pass.** It names staffing, it is `info` rather than an error, and
it does not invite a restart.

**What the loop card says**, for the same state at the same moment
(`loop.stall_reason`, from `_stall_reason_from_walk`):

> loop queue is stalled: no claimable task among 2 open (2 completed)

This attributes the condition to the **queue** — as though the flow were short of claimable work.
It is short of *people*. Both completed tasks are ready for review this second; what is missing is
an agent permitted to take one. **The two remedies are opposite:** the card's reading sends the
operator to add or unblock tasks, the true cause needs them to add or unarchive an agent.

### Root cause — the good sentence is computed, and then not used by the card

`decide_firing` (`scheduler.py:1300-1320`) returns in a fixed order: `selections` -> `in_flight` ->
`stall_reason`. `unstaffed` rides along on **all three** and is emitted separately as an event at
`scheduler.py:2111`. The card reads `stall_reason` only. So on a firing where every candidate is
unstaffable, `unstaffed` holds the accurate explanation, `stall_reason` holds the generic one, and
the surface an operator actually looks at gets the generic one.

Note this is not the F23 ordering bug returning: that fix put `in_flight` **before** the stall check
so a busy flow stops reporting itself stalled, and it works. This is the neighbouring case — a flow
that is neither busy nor short of work, but short of eligible agents — for which no branch exists.

Two shapes if it is fixed, neither chosen here: have `_stall_reason_from_walk` consult the same
walk's `unstaffed` and prefer its reason when every open candidate is unstaffable (narrow, keeps one
field), or surface `unstaffed` on the loop card as its own line beside `stall_reason` (wider, and
would also give the `review_unstaffed` event a home in the UI it currently lacks).

### What HELD

Rung 3 itself, completely: it fired when it should, said the right thing, at the right severity,
without disabling the job — `_emit_review_unstaffed`'s own comment gives the reason, that
`remove_job` is not undone by resolving whatever caused it. Also `POST /agents/relay/archive`
refused cleanly with `"relay has 1 queued message. Discard them to archive the agent."`, carrying
`blocking_queue_entry_count` and `blocking_queue_entry_ids` — a refusal that names the cause, the
count, and the remedy. The one wrinkle worth a line: the product's own API calls that remedy
**withdraw** (`DELETE /queue/entries/{entry_id}`, `withdraw_queue_entry`), not "discard", so the
operator has to translate the word before they can follow the instruction.

## F65 (C) — a review briefing refused for having no evidence stays queued, and blocks archiving its agent

**Status:** open — `turn_scheduler.py` still ends a no-evidence review briefing on the first refusal rather than after three attempts; queued as Q4-SPEC

Found 2026-08-26 by the **operator**, while setting up check 11.4 — an incidental discovery rather
than a targeted one, which is why it is recorded separately from F64.

`entry-74c9a267afc6` is the loop briefing delivered to `relay` carrying
`review_task_id: task-bb86d53a94d5`. Its run, `run-cd011fb845ce`, failed with the refusal **F56's
fix produces**:

> task task-bb86d53a94d5 has no recorded evidence, so there is no commit to review. Evidence naming
> a commit is what a review turn is given.

That refusal is correct and is a real improvement — before F56 this wedged the agent's entire
inbound queue silently. But the entry itself stayed `state: queued`, `delivery_attempts: 1`. Two
consequences:

1. **It will be re-delivered and re-refused.** Nothing about `task-bb86d53a94d5` will produce
   evidence on its own; the same briefing is queued to fail again on every firing that reaches it.
2. **It blocked archiving its agent.** `POST /agents/relay/archive` returned `409` naming this one
   entry, so an operator trying to reconfigure their roster is stopped by a message queued for a
   turn that has already been refused as impossible. Cleared here with
   `DELETE /queue/entries/entry-74c9a267afc6`, after which the archive succeeded.

Severity C rather than B: nothing is lost, no spend is wasted (the refusal happens before any model
is invoked), and the retry is defensible in the abstract — evidence *could* arrive later, and the
operator's own judgement was that this is worth recording rather than obviously wrong.

**The operator's chosen fix:** treat "no evidence to review" as **terminal for that briefing**
rather than retryable, and withdraw the entry when the refusal fires. The scheduler re-queues a
review when evidence appears anyway, so nothing is lost by not holding this one — and the roster
stops being held hostage by a message that cannot succeed.

### F63 — Resolution, 2026-08-26

Fixed as the operator chose: a **third role**, rather than narrowing `in_flight` or having the
renderer second-guess it.

`_batch_loop_summaries` (`api/v1/jobs.py`) gained a seventh batched query — `Run.agent` and
`Run.task_id` where `Run.status == "running"`, across the projects the loops belong to — and the
role now splits three ways instead of two: `working` when a run is genuinely in flight, **`held`**
when the loop cannot staff the task and nobody is mid-turn on it, `next` when this is who the next
firing would give it to. `scheduler.decide_firing` is untouched; `in_flight` keeps the meaning F23
and F45 gave it.

**Matched on the agent as well as on `task_id`, deliberately.** `run.task_id` is NULL on most real
runs — measured on this database while fixing F43, NULL on 6 of the 10 carrying a `completed`
transition — so a task-id-only test would have reported `held` about genuinely running work, the
same lie in the other direction. The agent fallback can over-report `working` when an agent is
mid-turn on a *different* task; that is the precision the scheduler itself staffs on
(`_agents_running_a_turn`), it is bounded, and it is one-directional.

On screen (`JobCard.tsx`) `held` renders as **"waiting on <agent>"**. The bare unqualified name is
now reserved for genuinely running work, which is the distinction the split exists for.

**A test that pinned the bug in place was corrected, not worked around.**
`test_a_task_being_reviewed_reads_as_working_not_next` asserted `working` over a review with **no
run anywhere** — exactly the state this finding is about — so as written it required the defect.
F49's actual claim is that the `working` branch is *reachable*, and it still is: the fixture now
carries a live `Run` and the assertion is unchanged. This is the F41/F43/F52 shape again, caught in
a test rather than in product code.

Three new tests in `test_board_agent_role.py`: the run-less review reads `held`; a running run with
a NULL `task_id` still reads `working` (the branch production takes); and a **terminal** run does
not keep a review reading `working` — that last one exists because a fix asking "is there a run for
this task" without asking "is it still going" would pass the other two and reproduce the bug, the
review turn that produced F63 having ended `failed`. One vitest case for the renderer.

**Mutation-checked:** collapsing the split back to an unconditional `working` fails
`test_a_review_nobody_is_running_reads_as_held_not_working` and
`test_a_terminal_run_does_not_keep_a_review_reading_as_working` by name; removing the `held`
qualifier from `CurrentTaskAgent` fails the vitest case. Restored and re-confirmed green each time.

**Live-verified** against the trial Hub restarted onto this code, on the exact row that produced the
finding: `task-bb86d53a94d5` now reads `agent_role: held` where it read `working` with zero runs in
the database an hour earlier, and `task-948637265cb0` beside it still reads `next`.

### F64 — Resolution, 2026-08-26

Fixed with the narrow shape: `decide_firing` prefers the staffing sentence over the queue sentence
when it has one. Reaching the stall branch already means no selection and nothing in flight, so if
`unstaffed` is non-empty then unstaffable candidates are *why* nothing was claimable, and the queue
sentence is describing the symptom while naming the wrong cause.

The rung-3 message was already being computed on that same walk and emitted as a `review_unstaffed`
event; it simply never reached the surface an operator reads. The first reason rather than a join of
all of them: several unstaffable reviews in one queue are unstaffable for the same reason, and a
card is a line rather than a report — the event stream still carries one entry per task.

Two tests in `test_flow_width.py`, paired on purpose: a queue whose only agent authored its own
completed work must name staffing and must **not** say "no claimable task among", and a queue that
is genuinely gated on a prerequisite — nothing unstaffed — must keep the queue sentence untouched,
so the fix cannot degenerate into "always say staffing".

**Mutation-checked:** removing the preference fails
`test_a_queue_nobody_can_staff_says_so_instead_of_blaming_the_queue` by name.

**Live-verified** against the restarted trial Hub: the `Stall bench` card, which read *"loop queue
is stalled: no claimable task among 2 open (2 completed)"*, now reads *"could not staff this step:
no agent is free to take it…"*.

**Something the live check turned up that the finding had not claimed.** That card still reports the
staffing reason with the **full roster restored** — `builder`, `critic` and `relay` all `open`, zero
running runs — because `builder` authored the task, `relay` holds other active work, and `critic` is
already the task's own assignee. So the Stall bench was misdescribing itself as a queue shortage
even before any agent was archived; archiving only made the misattribution easier to see. The fix is
reporting truthfully, not over-reporting. **Whether a roster of three should be unable to staff one
review is a separate question about the ladder**, not about this fix, and is left for the operator.

## F66 — A batched turn's workspace and its run binding are decided by two different rules, and they can name different tasks

**Status:** **closed 2026-08-30 — the question was answered in code, and this line was stale for
four days.** The operator question below ("should a turn ever batch a review and ordinary work?")
was answered **no** by `2026-08-27-every-run-knows-its-task` (archived), the day after this was
filed. Enforced in two layers: `turn_scheduler.py:110-131` narrows `selected` to the controlling
entry's kind before a turn starts, and `agent_trigger._review_task_from_entries` refuses a
hand-built mixed batch with a 409 as defence in depth. `run_task_binding.binding_from_entries`
states the outcome from its own side — *"That batch can no longer survive."* It is normative, not
merely implemented: `agent-conversation-workspace` carries **"A turn admits entries of one kind
only"** (`spec.md:1751`) and **"A delivered turn carries a review or ordinary work, never both"**
(`:1779`). The two rules can no longer disagree because the batch they would disagree about cannot
be assembled. Nothing below is retracted — it is the record of why the rule exists.

**Found:** 2026-08-26, driving group 6 of `one-answer-to-what-is-happening` live against the trial
Hub on port 8010. Not by reading — by checking a claim I had already written down and finding it
too generous to itself.

**The claim that was wrong.** Group 1 and its exploration state that *every* review run in the
product's history was unbound. Measured column-wise that is true — `inbound_queue_entries` has zero
rows carrying both `task_id` and `review_task_id`, so no review run was ever bound *through its
review entry*. But two review runs are bound anyway:

```
run-26f0c4702de0   run.task_id = task-23a0986e7fe9
   seq 184  review_task_id = task-0dfc3be5        <- what it was checked out to review
   seq 186  task_id        = task-23a0986e7fe9    <- what it was bound to

run-d7e30a9c650d   run.task_id = task-0dfc3be5    (the mirror image, same day)
   seq 188  review_task_id = task-23a0986e7fe9
   seq 199  task_id        = task-0dfc3be5
```

Both turns were delivered **two** entries: a review of one task and work on another. Their
*workspace* was a detached checkout of the first task's commit; their *run binding*, and therefore
the boundary check that asks "did this run move its task", was against the second. **That is worse
than unbound.** An unbound run is exempt from the check; these were checked against work they were
not looking at.

**The mechanism, and why it is still there.** Two rules pick a task from the same batch and they are
not the same rule:

| | rule | source |
|---|---|---|
| workspace | **any** entry in the batch carrying `review_task_id` wins; two distinct values is a 409 | `agent_trigger._review_task_from_entries` |
| binding | the **earliest queued** entry naming a task wins | `run_task_binding.binding_from_entries` |

Group 1 narrows the gap but does not close it. In both rows above the review entry is the earliest,
so after group 1 they bind to the task they were reviewing and the two rules agree. Reverse the
arrival order — work queued first, review second — and the workspace is still the review checkout
while the binding is the work task. The disagreement is reachable, it is just not what these two
rows happened to be.

**Not fixed here, and deliberately.** `one-answer-to-what-is-happening` is about a review turn
knowing its own task; this is about a turn that is doing two things at once, which is a question
about whether such a turn should exist at all. Test 1.3 pins the binding as deterministic across
both sources, which is what stops it drifting further while the question is open.

**For the operator:** should a turn ever batch a review and ordinary work? The 409 on two distinct
review tasks says the product already thinks one review per turn is the limit. One review plus one
piece of work is the case nothing refuses and nothing reconciles.

## F67 — A divergence response is queued into a conversation that does not exist, so it can never be delivered

**Status:** fixed b7bb8f1

**Found:** 2026-08-26, driving task 6.4 of `one-answer-to-what-is-happening` live. **The repository's
dominant failure mode, caught in my own work**: a fix that passes its tests and cannot fire.

**Measured on the beta database, before any fix:**

```
run_divergences                          25 rows
  ... with a response_run_id              0
divergence-origin queue entries           1  (the one this drive produced)
  ... with conversation_id NULL           1
```

**Zero divergence responses have ever produced a run.** Not "few" — none, across the whole history
of the capability.

**The mechanism.** `run_divergence._queue_response` builds its entry with no `conversation_id`:

```python
entry = new_entry(project_id=..., agent=..., origin_type="divergence", content=prompt,
                  hop_depth=0, task_id=task_id, divergence_source_run_id=source_run_id)
```

and `turn_scheduler.schedule_agent` refuses exactly that shape:

```python
controlling = next((e for e in entries if e.hop_depth <= hop_budget), None)
if controlling is None or controlling.conversation_id is None:
    return ScheduleResult(waiting_reason="queued entry has no conversation")
```

So the entry is written, `schedule_agent` is called, it declines, and the row sits `queued`
forever. Nothing errors. The divergence record even reserves a `response_run_id` column for a run
that cannot exist, and `record_response_run` waits for a caller that never arrives.

**Why it stayed hidden for the whole life of the capability.** `_queue_response` is only reached on
the `retried` and `escalated` outcomes. `escalate` requires `task.escalation_agent`, NULL on every
task ever; no task carried `retry`. All 24 historical divergences are `surfaced`, which queues
nothing. The path had never been walked.

**What walked it.** Group 2 of `one-answer-to-what-is-happening` added `restaffed` — a failed
review answered by resolving the reviewer again — which reaches `_queue_response` on a plain
`surface` task with nothing configured. The first live restaffing (`div-cfae68a70173`,
`loopreviewer` silent on `task-9b0b4a141b21`) produced a correct divergence row, a correct
reassignment, and a queue entry carrying `review_task_id` exactly as design D5 requires — that then
went nowhere.

**Why the group 2 tests did not catch it.** They assert the *entry* is queued with the right agent
and the right columns. None of them asserts it is ever *delivered*. That is the same gap shape as
F49 (renderer tested, derivation not) and as mutation check 4.9 (behaviour covered, boundary not).
An assertion about what was written is not an assertion about what happens.

**Fix.** A response entry gets a conversation. `retry` continues in the diverged run's own thread —
same agent, same work. `escalate` and `restaffed` go to a *different* agent, and a conversation
belongs to one agent (`schedule_agent` checks `conversation.agent != agent`), so those need a fresh
one. Its `origin` is `divergence`, its own value rather than a borrowed one, for the reason
migration `0058` gives for the queue entry's own `origin_type`: *"a signal that reports something
other than what it names is the exact defect this whole capability exists to remove."* Migration
`0093` widens `ck_conversations_origin`.

### F67 — Resolution and live verification, 2026-08-26

Fixed by giving the response entry a conversation, split by agent: `retry` continues in the diverged
run's own thread (same agent, same work, and a fresh one would throw away a resumable provider
session); `escalate` and `restaffed` get a fresh conversation with `origin='divergence'`, because a
conversation belongs to one agent and `schedule_agent` checks exactly that. Migration `0093` widens
`ck_conversations_origin`.

**A second bug inside the fix, caught by its own test rather than by review.** The first draft used
`session.get(Conversation, conversation_id)`. `Conversation`'s primary key is `sequence`, an
autoincrement integer — `session.get` would have compared a `conv-…` string against it and never
matched, silently opening a fresh thread on every retry. `get_conversation_by_id` exists precisely
because that trap has been fallen into before, and its docstring says so. Falling into it again, in
the fix for a defect of the same family, is worth recording rather than quietly correcting.

**Live-verified** against the trial Hub restarted onto this code, driving the whole chain on
`task-9b0b4a141b21` in `drive-2026-08-26`:

```
div-cfae68a70173  loopreviewer  review  restaffed  -> author     (entry stranded; pre-fix)
div-98d3894a9eef  loopauthor    review  restaffed  -> author      response_run_id = run-4f2b920d2b0d
div-3c5011c08e0e  author        review  surfaced   -> nobody left, reason names why
```

The middle row is the point: `run-4f2b920d2b0d` is **the first run in this product's history
started in response to a divergence.** Before the fix the count was 25 divergences and zero response
runs. Its entry carried `review_task_id`, so the responding reviewer got the checkout of the work
under review — design D5, finding F10, verified in production rather than in a fixture.

The third row is the chain bound working: `reviewer` barred as the agent that completed the task,
`loopreviewer` and `loopauthor` barred as agents already silent on it, `author` silent in turn, and
the flow surfaced with *"could not staff this step: no agent is free to take it…"* rather than
looping. Nothing was left queued.

**Also verified in the same drive**, both with the task's policy set to `retry`:

- **The review carve-out (design D3).** `policy_applied` recorded `review`, not `retry`, and **zero**
  response entries were queued. Under the previous behaviour a `retry` task would have re-run the
  same reviewer on the same evidence.
- **A declared reviewer is surfaced, never substituted (design D4).** With `loopreviewer` declared in
  the document and two other agents free, its silent review produced `outcome: surfaced`,
  `response_agent: null`, and a reason naming the declared reviewer and the task.

The trial project was left as found: the declaration removed, the policy back to `surface`, no job
enabled in any project, no run alive, and nothing this drive created left queued.

### F66 — decided 2026-08-26: refuse the mix, at the batcher

The operator's answer to *"should a turn ever batch a review and ordinary work"* is **no**. Proposed
as group 1 of `openspec/changes/every-run-knows-its-task`, which ships it **before** the work-run
binding in the same change — binding work runs is what makes the disagreement reachable, so the
separation lands ahead of the hazard rather than behind it.

The fix is at `turn_scheduler.py`'s batch selection, not only at the trigger's 409: entries stay
queued after a refusal, so refusing alone would reassemble the same batch every attempt and wedge the
agent permanently. Narrowing the batch instead — the controlling entry's kind decides the turn, the
other kind waits for the next one — loses nothing and defers rather than drops. The trigger's refusal
remains as defence in depth for a hand-assembled `queue_entry_ids`.

`turn_scheduler.py` already carries the same defect's earlier twin one comment above, from design D1
and finding F5: *"nothing used to ask which entries may ride on it."* F66 is that sentence with
"over-budget" replaced by "of the other kind".

## F68 (B) — two spellings of one severity, and the louder event is the one that renders as routine

**Status:** open (no fix commit references it)

Found 2026-08-26 while measuring the severity distribution for `every-run-knows-its-task`'s D6.
Nothing was looking for it; it fell out of a count.

```
severity   count
info       2996
warn        108
warning       3     <- turn_produced_nothing, all three
```

`hub/hub/run_divergence.py:613` emits `severity="warning"`. Every other call site emits `"warn"`.
`persist_event` (`hub/hub/utils.py:25`) does not normalise — severity is a free-form string written
to the column verbatim, so nothing catches the divergence at the write.

Three consumers key on `"warn"` and none knows `"warning"`:

- `EventRow.tsx:44` `SEVERITY_BORDER` — no match, `borderClr` is `undefined`, the row renders with
  **no amber border**.
- `EventRow.tsx:37` `SEVERITY_CHIP` — no match, `chip` is `undefined`, the row renders with **no
  severity chip**.
- `ActivityLog.tsx:31` `SEVERITY_FILTERS = ['all','error','warn','info','debug']`, filtered at `:165`
  by strict equality. The event is reachable **only** under `all`. Selecting `warn` hides it;
  selecting `info` hides it too.

The API has the same hole: `GET /events?severity=warn` compares `EventLog.severity == severity`
(`api/v1/events.py:42`), so an operator or script asking for warnings never receives one.

So `turn_produced_nothing` — a turn that ended having written nothing and asked nothing, precisely an
event that wants attention — is the one event in the product that renders as routine and disappears
under the filter meant to find it. Three rows exist today.

**Why it is B and not C:** nothing is lost and no spend is wasted, but the event exists solely to be
seen and it cannot be, which is the "passes its test but cannot fire in production" shape this series
keeps finding. Any test asserting "the event was persisted with a severity" passes.

**Recommended fix:** normalise in `persist_event` against an enumerated accepted set, rather than
only correcting line 613. Fixing the one call site leaves the class open — a fourth spelling can be
introduced the same way tomorrow. The enumeration is what makes it a mechanism instead of a habit.

Adjacent to `every-run-knows-its-task` D6, which derives divergence severity rather than hardcoding
it; that change should not land a new severity string without this normalisation existing.

## F69 — `every-run-knows-its-task` groups 1-5 driven live, all five behaviours held (not a defect — the record the group asked for)

**Status:** not a defect — the record group 6 asked for; all five behaviours held

Driven 2026-08-27, iteration 8, group 6 of `every-run-knows-its-task`, against `proj-18e5d4e0`
(ledger-stress) restarted onto this branch (migration `0093 -> 0094` ran clean on startup;
`GET /api/v1/projects` confirmed all 5 expected projects, `proj-5e960453` untouched).

**What held, measured against the real database, not a fixture:**

- **D1/D2, the binding.** Firing the project's pre-existing "Ledger flow" job produced the first
  job-origin queue entry in this database's history to carry `task_id`. The bound run drove
  `assigned -> in_progress` with `actor_kind='run'` and no operator or agent action —
  `run_task_binding.bind_run_to_task`, previously reachable only from direct operator triggers, now
  reachable from a flow firing.
- **D6, derived severity.** A flow work turn that ended without moving its task produced a
  `run_diverged` event at `severity='info'`, not the old hardcoded `warn` — confirmed by reading the
  `event_logs` row directly, not by trusting the API's default view.
- **D6, resolution.** Completing the same task on the flow's next tick fired
  `run_divergence_resolved` naming `{"task_id": ..., "count": 2}` — and the count included a second,
  unrelated divergence from 2026-08-24 that had never been resolved before this change existed to
  resolve it.
- **D7, the flow régime.** A task set to `divergence_policy='retry'`, worked by a flow that made no
  change, recorded `policy_applied='flow'` in `run_divergences` — not `retry` — and nothing
  auto-spawned afterward. The suppression named in the design fired exactly once, on exactly the
  condition it names.
- **D3/F66, the batching.** Two entries queued for one agent (`critic`) back-to-back, one carrying
  `review_task_id` and one carrying `task_id`: the immediately-spawned turn carried only the review
  entry, the work entry sat `state='queued'`, and it was delivered in the very next turn with no
  further operator action — the exact "rides the next turn" behaviour `tasks.md` 1.1/1.3 pin at unit
  level, reproduced against a real scheduler tick.

**Delta, the actual point of the drive:** job-origin entries carrying `task_id` went from **0/61**
to **8/71** (2 of the 10 new job-origin entries are review-staffing entries, which carry
`review_task_id` instead by design, not a miss). Runtime `→ in_progress` transitions went from
**20** to **28**, +8 — a 1:1 match to the 8 newly-bound job-origin work entries. The boundary
`design.md` measured as structurally unreachable (0 of 61) now applies exactly where the change
intended it to.

**Incidental, not caused by this change:** the drive hit a real, pre-existing staffing stall —
`scheduler.py:1050`'s `unresolved` rung — on a task whose declared reviewer had ended up being the
same agent that did the work. Resolving it the way an operator would (approving the task directly,
since "reviewing it yourself... is the way forward" is the ladder's own stated remedy) is itself
confirmation that the terminal rung's documented escape hatch works under real, un-staged
conditions, not a fixture built to exercise it. Recorded here rather than opened as its own finding
because nothing about it was surprising once read — it is the ladder behaving as designed.

**Left behind in `proj-18e5d4e0`** (job disabled, `ai_jobs WHERE enabled=1` confirmed zero; no
run or queue entry alive at the end): four new tasks — one probe left deliberately `in_progress`
with an unresolved surfaced divergence as durable evidence of the `retry` scenario above
(`task-4928038eba7e`), two real trivial commits used to construct a genuinely reviewable task for
the batching test (`task-c0bd47157c19` uncommitted-evidence and unreviewed, `task-60d1d8183feb`
fully reviewed and approved), and the job's own original task now operator-approved
(`task-e6b05093`). No further cleanup performed, consistent with how this project's other drive
evidence has always been left in place.

## F70 (A) — an operator can move a task to `under_review` without staffing a reviewer, and the flow reads that forever as a healthy review in progress — silently removing the stuck agent from every future review too

**Status:** fixed f58cc75

**Driven 2026-08-27, iteration 10 (Q6), against a genuinely fresh project — `proj-bad259c0c9f2`
(`drive-q6-2026-08-27`), created this iteration, outside the repository, registered via
`e2e.py setup`.** Two Hub-managed agents created via `POST /agents` (`self_registered: false`,
required — `e2e.py agent` always self-registers, and a self-registered agent 409s out of
`POST /jobs/{id}/run`, per this run's own earlier-recorded dead end): `flowauthor`
(claude/claude-haiku-4-5-20251001) and `flowreviewer` (codex/gpt-5.4-mini). A Loop job
(`job-fca8e5d32f63` / `loop-413d32f3e189`) was created with `initial_tasks`, targeting a small
seeded module (`cart.py`, three real deliberately-uncovered defects modelled on the
`drive-2026-08-26` pattern) committed to a real git repo with `main_branch: master`.

**First confirmed, cleanly: D1/D2's binding, live on a brand-new database row set.**
Firing the loop staged `task-2529a21e8c49` (`pending -> assigned`, `actor_kind=operator`) and its
run bound immediately (`assigned -> in_progress`, `actor_kind=run`, `run_id` populated) —
`task_transitions` rows read exactly as `every-run-knows-its-task` designed, reproduced from zero
with no inherited state from `ledger-stress`. The agent did real work: `git log` on the seed repo
shows a real commit (`f523937`) with a correct fix and a new regression test.

**Then a self-inflicted step exposed a real gap.** To test review staffing without waiting on a
cron, the completed task was moved directly from `completed` to `under_review` via
`PATCH /tasks/{id}` — a legitimate operator action (`task_transitions.py`'s transition table marks
`under_review` `_BOTH`, reachable by operator or agent) — **without also reassigning it away from
its own author.** `flowauthor` stayed the assignee.

From that single PATCH, the loop's scheduler permanently misread the task as a staffed review:

```python
# hub/hub/scheduler.py:530-535
#: The statuses meaning a reviewer already holds the task, claimable by nobody (finding F45).
#:
#: A firing that staffs a review moves the task here in the same commit that queues the turn --
#: `_enter_selected_task` -- which is what takes it out of `REVIEWABLE_LOOP_TASK_STATUSES` and
#: stops the next tick offering the same finished work to the same reviewer again.
WITH_REVIEWER_LOOP_TASK_STATUSES: tuple = tuple(sorted(WITH_REVIEWER_STATUSES))
```

and, in the walk itself (`scheduler.py:1214-1232`):

```python
if task.status in WITH_REVIEWER_LOOP_TASK_STATUSES:
    # A reviewer already holds this (finding F45). ...
    if task.assignee:
        in_flight.append((task.id, task.assignee))
    continue
```

The comment's own invariant — "a firing that staffs a review moves the task here **in the same
commit** that queues the turn" — is true of every path the scheduler itself uses, and false of this
one. Nothing checks that `task.assignee` actually differs from whoever completed the task; the
branch fires on status alone. The task (`task-2529a21e8c49`) sat `under_review`/`assignee=flowauthor`
for the rest of the drive — three more loop firings, ~10 minutes — with no error, no
`review_unstaffed` event, no operator-visible signal of any kind. `POST /jobs/{id}/run` reported
`409 "already being worked... nothing is wrong"`, which is the correct sentence for a real review in
flight and a false one for this.

**It compounds: the stuck assignee stops being recruitable as a reviewer for *other* tasks too.**
`_agents_that_are_free` (the pool `resolve_reviewer` draws from) excludes an agent "holding active
work" — and `flowauthor` was still, by construction, holding `task-2529a21e8c49`. When a second real
task (`task-684f8b08e0e0`, authored by `flowreviewer`) reached `completed` and needed a reviewer,
`resolve_reviewer` excluded `flowreviewer` (the author) and should have offered `flowauthor` — idle,
bound, on the roster — but `flowauthor` read as unavailable, and the walk emitted `review_unstaffed`
instead:

```
{"event_type": "review_unstaffed", "agent": "flowauthor", "task_id": "task-684f8b08e0e0",
 "reason": "could not staff this step: no agent is free to take it. Every agent on the roster is
 either running a turn, already holding active work, or is the one that completed this task and so
 may not review it."}
```

On a two-agent roster that message is a full stop: with `flowauthor` wrongly counted as busy and
`flowreviewer` excluded as the task's own author, **zero** agents were ever eligible, permanently,
until an operator manually resolves the original stuck task. The one contaminated PATCH did not just
strand its own task — it silently reduced the loop's reviewer pool by one agent for every task after
it, with the exact same "nothing is wrong" silence as the first-order bug.

**Why A, not B.** Nothing crashes and every individual event is truthful about the narrow question it
answers (`review_unstaffed`'s own reason text is accurate). The failure is structural: an ordinary,
sanctioned, one-line API call — moving a task to `under_review` without also handing it to someone —
degrades the flow's future capacity with no error and no event naming the actual cause, and the
`409`'s own text ("nothing is wrong") actively asserts health. An operator would have no way to
connect a later `review_unstaffed` on an unrelated task back to this one stale row without reading
`task_transitions` by hand, which is exactly what this drive had to do.

**Recommended fix, in the shape of the file's own comment:** the `WITH_REVIEWER_LOOP_TASK_STATUSES`
branch should not trust status alone — it should also confirm `task.assignee` is not the agent that
completed the task (`_agent_that_completed`, already computed a few lines below for the sibling
branch). A task that reaches `under_review` with its own author still assigned is not "a reviewer
already holds this"; it is exactly the case `resolve_reviewer`'s `exclude={author}` exists to refuse,
reached by a different door. Whether that should instead be prevented further upstream — refusing the
plain `completed -> under_review` transition itself unless the assignee changes in the same call —
is a design question for the operator; this finding is about the scheduler's silent misreading, not
a recommendation on which layer should close it.

**Also reproduced, and held correctly, in the same drive:** once a *second* task reached `completed`
authored by a different agent (`task-13c9638e7e30`, authored by `flowauthor`), the *un*-contaminated
path worked exactly as designed — `resolve_reviewer` excluded `flowauthor`, picked the free
`flowreviewer`, staged the review (`assignee` reassigned, status flipped, in the same commit, per the
comment above) and queued a real review turn. This is `every-run-knows-its-task` D3/D4's staffing
ladder working correctly, live, from zero, immediately adjacent to the one row where it couldn't —
recorded because a finding about one path breaking is stronger evidence next to a record that its
sibling held.

**What the drive did not reach, and why — not a defect, a gate working as designed.** The staged
review turn for `task-13c9638e7e30` never delivered: triggering `flowreviewer` directly returned
`"task-13c9638e7e30 has no recorded evidence, so there is no commit to review"` —
this project's tasks were never linked to a spec document/requirement, so `record_evidence` had
nowhere to attach, and this drive's task descriptions never told the agent to call it (only "commit
your change"). This reproduces F65's already-recorded behaviour (a review refused for missing
evidence stays queued) rather than finding something new, and is recorded here as confirmation, not
as a fresh defect. Verdict, approval and integration were consequently not reached this iteration —
left for a future drive that either wires a spec document through first or seeds `record_evidence`
calls into the task briefing.

**Left behind in `proj-bad259c0c9f2`** (job archived, `ai_jobs WHERE enabled=1` confirmed empty
project-wide): three tasks (`task-2529a21e8c49` stuck `under_review` as durable evidence of this
finding — deliberately not resolved, so the row is still there to inspect; `task-13c9638e7e30`
`under_review`/staffed but undelivered, evidence of the F65 reproduction; `task-684f8b08e0e0`
`completed`, evidence of the `review_unstaffed` cascade), two agents, one archived job/loop, three
real commits on the seed repo's `agentweave/flowauthor` branch. No further cleanup performed, so a
future session can inspect the exact rows this finding cites.

## F71 (A) — operator-recorded evidence footprints the operator's own checkout, not the commit the operator named, and a downstream review silently gets the wrong tree

**Status:** fixed b96c222

**Driven 2026-08-27, iteration 11 (Q7), continuing to exercise the verdict/approval/integration
path Q6 explicitly did not reach — using the same live project, `proj-bad259c0c9f2`.** Built the
part of the chain Q6 was missing (a spec document with one requirement, `FR-1`, approved and
adopted onto the board as `task-7f49caae3c6d`) so evidence could be recorded against something real,
then recorded evidence as the operator via `PUT .../documents/.../content` and
`POST /projects/{id}/project/spec/evidence` — the same operator-facing route the Hub UI itself
calls (`hub/hub/api/v1/spec.py:812`, distinct from the agent-facing `POST /spec/evidence` in
`agent_actions.py` that a run authenticates against — the two are separate routers under separate
prefixes, not two callers of the same code path).

**What was recorded.** `flowreviewer`'s real, already-existing fix for the seeded
`apply_percent_discount` float-equality bug sits, uncommitted-to-master, as commit `bd03e4d3` on
`agentweave/flowreviewer` (an auto-snapshot per `worktrees.snapshot_worktree`, confirmed by
`git diff master agentweave/flowreviewer -- cart.py`). The operator recorded evidence for `FR-1`
against `task-7f49caae3c6d` with `locator: bd03e4d3eec894c82159e51ed01ed3dc874287a0` — naming the
fix commit explicitly, in the one field that exists to say which commit is being described.

**The footprint that was actually captured names a different commit — the wrong one.**
`requirement_evidence.record` (`hub/hub/requirement_evidence.py:95`) never reads `locator` to decide
what to footprint. It calls `footprint_root(workspace, actor.kind, actor.name)`
(`requirement_evidence.py:220`), and for `actor.kind == "operator"` that function unconditionally
returns `workspace.root` — the *project's own* checkout, on whatever branch the project happens to
be sitting on, regardless of what the operator's `locator` says. Queried directly against the
`evidence_footprints` table for the row this drive created (`ev-9d22a691db10`):

```
commit_sha: 052632357cb2edaf6fbbb99dd93a1b85fb04724f   (the ORIGINAL SEED commit — bug still present)
branch:     master
reachable_from_main: 1
```

not `bd03e4d3...`, the commit the operator named. `052632357` is `drive-q6-2026-08-27`'s very first
commit — "seed cart module with deliberate uncovered defects" — the state *before* any fix, sitting
on `master` because the operator's own checkout of this throwaway project had never been advanced
past it.

**Confirmed mechanically, not inferred: this is what a review turn would actually be handed.**
Called `requirement_evidence.commit_for_task_review(session, "task-7f49caae3c6d")` directly against
the live database (the same function `agent_trigger`'s review-turn wiring calls to decide what to
check out):

```
resolved: True
commit_sha: 052632357cb2edaf6fbbb99dd93a1b85fb04724f
branch: master
refusal: None
```

A reviewer given this task is hand-checked-out to the buggy pre-fix code, silently, with `resolved:
True` and no refusal — the exact code path that refuses cleanly when there is *no* commit
(`commit_for_task_review`'s two named refusal reasons, both absent here) does not distinguish "no
commit" from "the wrong commit, footprinted with total confidence." `reachable_from_main: 1` compounds
it: `task_integration.integration_targets` (per this same module's own docstring on
`restamp_run_footprints`) merges on exactly this field, so an operator who approved evidence footprinted
this way would have the Hub believe the fix is *already on `master`* — it is not; `master` still
carries the float-equality bug, confirmed directly (`git show master:cart.py`, `discounted == 0.0`
present, no `math.isclose`).

**The direction of the failure is not fixed, and neither is safe.** In this drive the wrong-footprint
commit happened to *predate* the fix — the failure reads as "reviewer sees stale, unfixed code,"
recoverable once the reviewer notices the diff is empty of the described change. The opposite is also
reachable with the identical mechanism: an operator recording evidence while their own checkout
happens to be sitting on *any* commit that is not the one they are describing — including one further
ahead, containing unrelated later work — would footprint *that* instead, with the same unearned
`resolved: True` / possible `reachable_from_main: True`. Nothing about `record`'s code path validates
the named `locator` against the captured footprint, or even warns when the two commits differ.

**Why A, not B.** `footprint_root`'s own docstring states the assumption this breaks: "The operator
keeps the project directory, and that is right rather than merely convenient: it is their own
checkout, and **if they are on a feature branch that is where they observed the thing.**" That
premise is only true when the operator's own checkout *is* the work being described — true for the
scenario the docstring was written against (2026-08-13, operator recording their own observation of
their own tree), false for this one: an operator recording evidence *about a separate agent
worktree's branch*, which is the ordinary shape of reviewing multi-agent work from outside a running
turn (exactly what this drive, and any real operator watching a loop from the dashboard, would do).
The `locator` field exists, is populated correctly, is silently ignored, and the resulting evidence
carries `review_state: accepted` (operator evidence self-accepts, `requirement_evidence.py:151`) —
so this is not a pending claim awaiting scrutiny; it is evidence already treated as decided, footprinted
against a commit nobody named and nobody chose.

**A second, smaller finding surfaced by the same drive: the record-evidence response never reports
the footprint it just captured.** `POST /project/spec/evidence`'s handler
(`hub/hub/api/v1/spec.py:838`) returns `_evidence_view(evidence)` — no `footprint=` argument — while
every *other* caller of `_evidence_view` in the same file (`spec.py:805`, `:867`, `:898`) passes one.
The API response for the call this drive made read `"footprint": null`, which looks exactly like "no
footprint was captured" — the honest, refusal-shaped outcome — when in fact a footprint row was
written to `evidence_footprints` in the same transaction, just naming the wrong commit (above). A
caller who trusted the response over the database would draw the opposite conclusion from either
direction: believing evidence was captured with no footprint at all (false — one exists), or, had the
footprint been correct, having no way to confirm what commit was actually captured without a direct
database read. Not independently severity-rated; recorded as part of F71 because it is what let this
finding's own root cause go unnoticed at the API layer during this drive — the response gave no
signal that anything had gone differently from what was asked for.

**Not fixed this iteration**, consistent with the standing discipline (drive records, a separate pass
fixes) and with how little of `stop_at` remained when this was found. Plausible remedies, none
picked: (1) `record` compares the captured footprint's commit against a `locator` that parses as a
commit-ish and refuses or warns on mismatch; (2) for `actor.kind == "operator"`, resolve the footprint
root from the *named* commit/branch when `locator` identifies one, falling back to `workspace.root`
only when it does not; (3) surface the footprint (and a mismatch, if any) in the record-evidence
response so a human operator has a chance to notice before deciding anything downstream. Left as a
decision for the operator, alongside F70, rather than guessed at here.

**Left behind in `proj-bad259c0c9f2`:** one new spec document (`spec/changes/russet-kirin/spec.html`,
approved, one requirement `FR-1`), one throwaway sibling document from an earlier attempt in the same
session (`spec/changes/lilac-chimera/spec.html`, left at `exploring` — abandoned mid-draft when its
requirement key collided with the one actually used; harmless, not cleaned up, so the git history of
this drive stays honest about the false start), one task (`task-7f49caae3c6d`, `under_review`,
assignee `flowreviewer`, carrying the mis-footprinted evidence `ev-9d22a691db10`) left live and
unresolved as inspectable evidence for this finding, the same discipline F70's rows already follow.

---

### Fixed, 2026-08-27 — F70 and F71, both remedies chosen by the operator

Both findings were left undecided by the overnight run, which correctly refused to pick between
three plausible remedies each. The operator chose on the morning of 2026-08-27, and both fixes
landed the same session with tests that were verified to fail without them.

**F70 — fixed in two halves, because either alone leaves a real gap.**

The operator chose *"refuse at the transition, plus a scheduler guard"* over either half on its own.

* `task_transition_service._guard_reviewer_is_not_the_author` refuses `-> under_review` while the
  task still names the agent recorded as completing it, so no new wedged row can be created. It
  **binds the operator too**, unlike its sibling `_guard_author_is_not_reviewer`, and that is the
  substantive difference between them: the sibling is about *authority* — who may sign off work,
  where a single-operator project must be able to approve its own — while this one is about the
  *state the move produces*, which is a false claim about the world no matter who writes it. Two
  cases permit deliberately: no assignee (nobody is claimed to hold it, so nothing wedges — this is
  the operator taking the task off the board to read it themselves), and no recorded completer (the
  refuse-to-offer/permit-to-act asymmetry `task_is_claimable_by` already documents at length).
* `scheduler`'s `WITH_REVIEWER_LOOP_TASK_STATUSES` branch now detects a task whose named reviewer
  *is* its author and routes it back through the reviewer ladder instead of recording it as
  in flight. Rows wedged before the guard existed therefore recover rather than staying stuck
  forever behind a guard that arrived too late to help them. Deliberately **not** a fall-through to
  the ordinary-work arm: that arm would find the author in `assignee` and re-staff the review as
  implementation, which is F10 arriving by the new route that branch's own comment warns about.

**Two ordering changes came out of building it, and both are load-bearing rather than incidental.**
`_enter_selected_task` transitioned to `under_review` *before* writing the reviewer into `assignee`,
so the new guard read the author and refused the flow's own correct staffing — the fix would have
broken every review the product staffs while passing a guard test suite that only came in through
the operator's door. `update_task_for_actor` had the same shape: it applied `status` before
`assignee`, so a single `PATCH {status: "under_review", assignee: "critic"}` — precisely the remedy
the refusal names — was refused on the strength of an assignee that same request was about to
replace. Both now write the assignee first. `test_review_divergence.py`'s
`_review_run_that_said_nothing` fixture, whose docstring claims it builds a review "the way the
product builds one", tracked the old order and was corrected with it; that claim is true again.

**F71 — fixed as (2) + (3), with (1)'s refusal folded in.**

The operator chose *"resolve from the locator, refuse on failure, and surface it"*.

* `requirement_evidence._take_footprint` reads the footprint at the commit an operator's `locator`
  **names**, not at whatever their checkout is sitting on. The checkout was only ever a fallback for
  when nothing said otherwise — `footprint_root`'s own docstring makes that inference explicit — and
  an explicitly named commit is strictly better information than an inference.
* A locator naming a commit this repository does not have is **refused** (409,
  `locator_commit_unknown`) rather than quietly footprinted at `HEAD`. Falling back there would
  reproduce F71 exactly, in the one case where the operator has said most clearly what they meant.
* `locator_commit` is deliberately narrow — a bare git object name (`^[0-9a-f]{7,40}$`) and nothing
  else. `locator` usually holds a *path* (`evidence_locator_exists` resolves it as one), so anything
  looser would start reading file names as revisions. **A branch name is not accepted** for the same
  reason: `cart.py` and `feature/x` are both plausible paths, and guessing which was meant is the
  kind of judgement this product does not make on the operator's behalf.
* `_branch_at` names the branch only when exactly one local branch's tip *is* that commit. A commit
  mid-history belongs to every branch descending from it, and picking one would put a guess into the
  field `task_integration.integration_targets` groups by. `""` is already this module's word for
  "names no line of work", so the unknown case has an established, honest meaning.
* **Operators only.** An agent's footprint is deliberately its worktree's `HEAD`, uncommitted work
  and all, with `restamp_run_footprints` correcting it once the Hub commits the turn — a
  locator-named commit would fight that mechanism rather than improve it.
* The second, smaller half: `POST .../project/spec/evidence` now passes `footprint=` to
  `_evidence_view`, as every sibling call site in `spec.py` already did. The response said
  `footprint: null` even when a footprint *was* captured, at the exact moment the operator is
  looking and a wrong commit would have cost nothing to notice.

**A separate defect surfaced while verifying this work, and is fixed here too.** CI on `master`
failed on `test_flow_width.py::test_three_startable_tasks_and_one_agent_start_one_and_touch_nothing_else`
after the overnight commits were cherry-picked — the same commit that passes on Windows. Iteration
5's change to that test had asserted `("in_progress", OWNER)` on the strength of D1/D2's new
`task_id` on the staged entry, but that advance happens in the **background task the firing kicked
off**, not in the firing: whichever status such an assertion names, it is a coin toss. It now asserts
what the firing itself decides — this task claimed by this agent, the other two untouched — which is
all 5.2 was ever about. Awaiting the spawn instead was tried and rejected: it settles the race and
costs 40 seconds of real launch attempt per run for a property `test_run_task_binding.py` already
asserts deterministically in its own subject.

**Left live in `proj-bad259c0c9f2`:** the inspectable rows both findings' write-ups describe
(`task-2529a21e8c49`, `task-7f49caae3c6d`, `ev-9d22a691db10`) are untouched. They are a throwaway
project's evidence for what the defects looked like, and the fixes were verified against tests rather
than by mutating them.

---

## F72 — every checkpoint ever produced reported no changed files (severity A, fixed 2026-08-27)

**Status:** fixed 29a5e69 + eaaceb4

**Found while implementing task 6.6 of `2026-08-27-work-is-isolated-per-task`**, which asked only
that `checkpoints.agent_worktree` become task-aware. It was not wired at all.

**The chain, each link verified by grep rather than inferred:**

* `checkpoints.agent_worktree` had **zero callers** anywhere in the repository.
* `compute_envelope(worktree=...)` was reached only from `generate_checkpoint`, whose `worktree`
  parameter defaulted to `None`.
* **All three** `generate_checkpoint` call sites — `api/v1/checkpoints.py`, `checkpoint_handover.py`,
  `checkpoint_trigger.py` — omitted it.
* `_files_from_runs` returns `[]` immediately when its worktree is `None`.

So `files_changed` — a field `conversation-checkpoint` requires the Hub to compute precisely because
a model asked for it would invent one — was **empty in every checkpoint the product has ever
produced**, and a successor reading a checkpoint was told the conversation had touched nothing.

**Why the suite could not see it.** The existing tests pass a path straight into `compute_envelope`,
which is the production path's *last* step. They proved the computation and observed nothing about
the wiring. The same shape as iteration 13's finding one phase earlier: **a renderer test and a
wiring test are different tests.** Under a mutation that reverts the fix, all 24 of those tests stay
green and only the two new ones fail — which is the defect's own signature.

**Fixed by removing the way to forget**, not by adding the argument at three call sites: the
repository is resolved inside `generate_checkpoint`, which always has a conversation. A caller
cannot omit an argument that no longer exists. `agent_worktree` is deleted rather than repaired.

**The repository root, not the workspace each turn ran in — and this is the part measured rather
than argued.** Linked worktrees share one object database, so `git show` from the root reads a
commit made in any of them, *including one whose checkout has since been removed*. Proved in a
throwaway repository: a commit made in a task checkout is still readable from the root after
`git worktree remove`. That inverts the obvious design — per-run resolution would report nothing for
exactly the finished work a checkpoint most wants to describe, because a task checkout is released
when the task is approved (design D5).

**Pre-existing, not caused by per-task isolation** — but isolation would have made it worse in a way
that hid it further: once turns run in `agentweave/task/<id>`, even the wired-up agent-name
resolution would have pointed at the wrong directory.

Covered now by a `conversation-checkpoint` delta in that change, with scenarios for the ordinary
case, the released-checkout case, and the unresolvable-project case (which still yields a
checkpoint, carrying no file list — a checkpoint that does not exist is worse than one that reports
nothing).

---

## Live drive, 2026-08-27: work is isolated per task (task 8.8) — **no defect found**

Driven against the trial Hub on 8010, restarted from source onto this change's code. The Hub was
confirmed by its **project list**, not `/health`, because a Hub on a stale database still answers
`{"status":"ok"}`. Migrations `0095` and `0096` applied to the beta profile on startup; the database
was backed up to `agentweave.db.bak-pre-0096` first.

Script: `scripts/drive/t_task_isolation.py`. Throwaway projects `proj-1b7c4196a041`
(`drive-f58-2026-08-27`) and `proj-1c3a...` (`drive-f58b-2026-08-27`), both created for this.
Neither `proj-5e960453` nor `proj-18e5d4e0` was touched, which was the condition attached to
implementing this change unattended.

**What the drive did.** Two tasks for one project, each provisioned through `ensure_task_worktree`,
a commit made in each task's own checkout, evidence recorded by the operator naming the *first*
task's commit, then the first task approved.

**What held — the whole point, and worth recording as much as a break would be:**

| Observed | |
|---|---|
| Each task got `.agentweave/tasks/<id>` on `agentweave/task/<id>` | per-task provisioning, live |
| `git branch --contains` on each tip named **only that task's own branch** | the two are siblings of `main`, not of each other — this is F58's absence, stated positively |
| Approval merged `a8e7bbc7189c` and nothing else | "Integrate approved work \<sha>" |
| The second task's commit is **not** on `main`, and `second.py` does not exist in the working tree | **F58 does not reproduce** |
| The approved task's checkout was removed, its branch kept | design D5 |
| The **un**approved task's checkout survived the other's approval | design D5, and task 6.10's decision holding |

**F71's fix was exercised in the same run, and worked.** The operator recorded evidence with the
task's commit sha as `locator`; the footprint captured that commit, on the task's branch, with
`reachable_from_main=False` — the exact field whose wrong value was F71's harm. Under the old
behaviour it would have footprinted the operator's own checkout, sitting on `main`.

**One thing the first attempt got wrong, and it was the drive rather than the product.** The first
run approved a task with no accepted evidence and nothing merged. That is correct behaviour, stated
plainly by the integration record — `outcome: skipped`, *"no accepted evidence names a commit, so
there is nothing to merge"* — and the reason `main_branch` looked unset was that the drive PATCHed a
route that does not exist (405) while `POST /projects/open` had already auto-detected `main`
correctly. Recorded because a reader of the first transcript would otherwise read a skipped
integration as a defect.

**Left live:** both throwaway projects and their repositories, with the task branches intact, so the
state described above is inspectable rather than merely reported.

---

## F73 — `ui_stale` is a false positive on any Windows checkout, and no rebuild can clear it

**Status:** fixed (this branch) — `ui_source_fingerprint` now hashes git-normalised content

**Severity: B.** Not a product surface an end user sees, but it disables the one signal that
catches a genuinely stale dashboard bundle, and it disables it *permanently* — which is worse than
not having the signal, because the operator is told the check exists.

**What happens.** `GET /health` reports `ui_stale: true` on a checkout whose `hub/ui/src` is
byte-identical to the commit the build stamp names. Measured on this branch at `2643663`:

```
$ curl -s http://127.0.0.1:8011/health
{"status":"ok","runtime":"native","ui_stale":true,
 "ui_stale_detail":"...asserts it was built from hub/ui/src as of 2026-08-27T17:10:27+00:00,
                    but the source has changed since..."}

$ git diff --stat d1f04e5 HEAD -- hub/ui/src      # d1f04e5 is the stamp's own src_commit
                                                   # (empty -- no change at all)
$ git status --short hub/ui/src
                                                   # (empty -- clean)
```

**Why.** `ui_source_fingerprint` hashed each file's *working-tree bytes*. With
`core.autocrlf=true`, working-tree bytes are a function of checkout policy, not of the source: at
the time of measurement nine tracked, unmodified files under `hub/ui/src` stood CRLF on disk
against LF in the index —

```
$ git ls-files --eol hub/ui/src | grep 'w/crlf'
i/lf w/crlf attr/text=auto eol=lf   components/agents/ComposerModelControls.tsx
i/lf w/crlf attr/text=auto eol=lf   components/agents/ComposerSpecControl.tsx
i/lf w/crlf attr/text=auto eol=lf   components/agents/ConversationControls.tsx
i/lf w/crlf attr/text=auto eol=lf   components/agents/ModelPicker.tsx
i/lf w/crlf attr/text=auto eol=lf   components/layout/Drawer.tsx
i/lf w/crlf attr/text=auto eol=lf   components/layout/LoopFiringGroup.tsx
i/lf w/crlf attr/text=auto eol=lf   components/layout/RowMenu.tsx
i/lf w/crlf attr/text=auto eol=lf   components/layout/SidebarItem.tsx
i/lf w/crlf attr/text=auto eol=lf   components/layout/StatusBar.tsx
```

— so the fingerprint answered a question about the checkout rather than about the source.
Demonstrated directly: rewriting one LF file as CRLF, a change `git diff` reports as nothing at
all, moved the fingerprint `132c4aa…` → `71ae825…`, and restoring it moved it back.

**The bundle was not stale.** Verified rather than assumed: `npm run build` then
`scripts/refresh_ui_bundle.py`, diffed against a snapshot of `hub/hub/static/ui` taken beforehand.
Every byte of the bundle is identical; only `ui-build-stamp.json` changed.

**One defect, or a design gap?** A design gap, and the third instance of one shape. The stamp
mechanism was introduced precisely because the previous comparison (commit dates) could not be
cleared by doing what it asked; `test_a_stamp_recorded_against_a_dirty_tree_survives_the_commit`
records the second instance (a stamp taken against a dirty tree could never match once committed).
This is the third: a stamp taken on one checkout cannot match the same content on another. Each
time, the property that was actually wanted is *content as git defines it*, and each fix
approximated it with something cheaper.

**The fix.** Hash `git hash-object`'s output — the working-tree file's content with its own
`.gitattributes` clean filter applied. That keeps the dirty-tree property the current code was
written for (it reads the working tree, not the index, so staged-vs-committed is still irrelevant)
and adds the missing one, since git's own normalisation is what both sides of the comparison now
agree on. Binary assets are unaffected: `text=auto` means git does not normalise them, so a real
change to one still moves the hash. Batched at 200 paths so a large tree cannot overrun the
Windows command line.

**Test:** `test_the_fingerprint_is_blind_to_working_tree_line_endings`, watched to fail before the
fix with *"a line-ending-only difference git normalises away is not a source change"*. Note the
trap it caught on the way in: a first version of the test used `Path.write_text`, which on Windows
already emits CRLF — so it compared CRLF against CRLF and passed against the defect. It writes
bytes now, and says why.

**Consequence to expect once.** The fingerprint algorithm changed, so every existing stamp is
invalidated and each checkout will report `ui_stale` one final time until it is re-recorded. This
branch re-records this repository's.

**Cross-cutting note for the sweep.** This blocked Step 3 of the e2e method, which says every UI
finding taken from a stale bundle is worthless. It was found *before* driving any screen, which is
the only reason the UI rows of this sweep mean anything.

---

## F74 — evidence from a task-bound run does not carry the task, so its own review turn refuses it

**Status:** fixed (this branch) — `requirement_evidence.record` falls back to the run's binding

**Severity: A.** It breaks the spine the whole product is built around — completed → under_review →
approved → integration — and it breaks it silently, reporting a *different* problem than the one
that exists.

**What happens.** An agent triggered with `task_id`, which does its work and calls
`record_evidence` without repeating the task, produces evidence that the task's own review turn
cannot see. Driven live on `proj-46b602c1f3cb`:

```
POST /projects/{P}/agent/trigger   {"agent":"builder","task_id":"task-a0409448ee8e", ...}
  -> run-62f25237be45, task moves in_progress -> completed, calc.py + test_calc.py committed

POST /projects/{P}/agent/trigger   {"agent":"reviewer","review_task_id":"task-a0409448ee8e"}
  -> 409  "task task-a0409448ee8e has no recorded evidence, so there is no commit to review.
           Evidence naming a commit is what a review turn is given."
```

**The refusal is false.** The evidence exists, and it names a commit:

```
sqlite> SELECT id, task_id, run_id FROM requirement_evidence;
ev-e63d76084f80 | NULL | run-62f25237be45
sqlite> SELECT evidence_id, commit_sha, branch FROM evidence_footprints;
ev-e63d76084f80 | 9b2d781c93499… | agentweave/task/task-a0409448ee8e
sqlite> SELECT id, task_id FROM runs WHERE id='run-62f25237be45';
run-62f25237be45 | task-a0409448ee8e
```

Three separate places in the Hub's own database name the task — the run's binding, the branch the
Hub itself created, and the worktree path — and the column the review turn reads is the one nobody
filled in. `commit_for_task_review` selects `WHERE RequirementEvidence.task_id == task_id`
(`requirement_evidence.py:718`), gets nothing, and reports the "no evidence at all" branch of its
two-branch message. An operator reading that would conclude the agent recorded nothing and go
looking at the agent.

**Why it happens.** `POST /agent-actions/spec/evidence` passes `task_id=body.task_id` and nothing
else. The MCP tool exposes `task_id` as the sixth of six arguments, described as *"The task this
came out of, when there is one"* — optional, and phrased as though the agent might be the one who
knows. The agent is not: it is told what task it is on by the Hub, and the Hub already stored the
answer on the run.

**One defect, or a design gap?** A design gap, and one this codebase has already named. The
`every-run-knows-its-task` work (`1a92642`) established that a run's task is the Hub's fact rather
than something restated per call; `run_task_binding.py:143` records the same shape biting review
runs (*"`run.task_id` was NULL on every review run the product had started"*). Evidence was simply
not swept in. Anything else keyed on `evidence.task_id` inherits the same hole — `duplicate_of`
takes `task_id` too, so duplicate detection was scoped to NULL and could not have fired either.

**The fix.** `record()` derives the task from `runs.task_id` when the caller did not name one, via
`task_bound_to_run` — a near-twin of the `recorded_workspace_dir` helper already beside it. An
agent that *does* name a task still wins, and an operator (no run) is unaffected, so the fallback
stays a fallback.

**Tests:** `test_evidence_inherits_the_task_its_run_is_bound_to`, watched to fail with
`assert None == 'task-bound'`, plus `test_an_agent_may_still_name_a_different_task` guarding
against the fallback overruling an explicit answer.

**Verified live, not only in tests** — this repository's dominant failure mode is a change that
passes its tests and cannot fire in production, so the same drive was re-run against the restarted
Hub:

```
ev-e63d76084f80 | NULL                  | run-62f25237be45   <- recorded before the fix
ev-5a98a7df0fa1 | task-a0409448ee8e     | run-17112845f36f   <- after, agent again named no task
```

and the review turn that returned 409 above returned **200** — `reviewer` started, and took its
detached checkout at `.agentweave/reviews/reviewer`.

**What held, in the same drive.** F71's fix is working: the footprint captured the agent's actual
commit on `agentweave/task/…` with `reachable_from_main: false`, not the operator's checkout.
F10's is working: the reviewer got its own checkout of the work rather than being refused at the
author's worktree.

---

## F75 — a reviewer's independent confirmation is refused as a duplicate of the author's claim

**Status:** fixed (this branch) — `duplicate_of` keys on the actor as well

**Severity: B.** It silences the one actor whose evidence the record exists to collect.

**What happens.** `reviewer`, dispatched onto `builder`'s finished task, checked the work itself
and tried to record what it had verified:

```
mcp__agentweave__record_evidence {"identifier": "FR-1", "kind": "test_result", ...}
  -> 409 "ev-5a98a7df0fa1 already records evidence for FR-1 on this task at this commit,
          and is awaiting. Recording the same demonstration twice makes the reviewer decide
          once per copy and overstates FR-1's evidence count."
```

`ev-5a98a7df0fa1` is **`builder`'s** evidence, not the reviewer's. A review turn runs in a detached
checkout of the very commit under review, so the reviewer's requirement, task and commit are all
necessarily the author's — the key `duplicate_of` uses cannot tell a confirmation from a copy.

**This was created by F74's fix, and that is the honest way to describe it.** Before it, agent
evidence carried no `task_id` at all, and `duplicate_of` returns None the moment any part of its
key is missing — so the duplicate check **had never fired in production for agent evidence since it
was written for F7.** Fixing F74 switched it on for the first time, and the first thing it did was
refuse a reviewer. Two findings, one root: a column nothing filled in.

**The fix.** Add the actor to the key. F7's measured case — one agent recording the same fact
twice — is unchanged, because that is the same actor. A different actor at the same commit is a
second demonstration and is stored.

**Tests:** `test_a_reviewer_confirming_the_authors_work_is_not_a_duplicate`, watched to fail with
the live message above, and `test_the_same_actor_is_still_refused_when_another_has_recorded_too`,
which fails pre-fix too and exists so the new dimension cannot weaken F7's case. Note what the
first version of that test got wrong: without setting the reviewer run's `workspace_dir` to a
checkout of the same commit, the two footprints name different shas, no duplicate is possible, and
the test passes against the defect.

---

## F76 — a review turn dispatched by hand dead-ends: the reviewer cannot record its verdict anywhere

**Status:** **fixed** — operator chose the shape 2026-08-28 ("staff it, and refuse up front when
staffing would be illegal"), specified through three review rounds as
`openspec/changes/2026-08-28-a-review-started-by-hand-can-finish`, implemented and driven live the
same day. See the closing section.

**Severity: A.** The operator starts a review through the product's own mechanism, pays for a full
turn, and the verdict exists only in the chat transcript.

**What happens.** `POST /agent/trigger {"agent":"reviewer","review_task_id":"task-…"}` succeeds,
provisions the reviewer's detached checkout, and the agent does careful work — it re-ran the suite,
wrote a comparison script, and checked negative amounts and rounding boundaries. Then every route
for recording the verdict refused it:

| It tried | It got |
|---|---|
| `update_task` to `approved` | 409 *"Cannot move a task from 'completed' to 'approved'. From 'completed' the available transitions are: under_review."* |
| `update_task` to `under_review` | 403 *"it is still assigned to 'builder', the agent recorded as completing it, so the move would claim its own author is reviewing it. Assign a different reviewer, or clear the assignee to review it yourself."* |
| `record_evidence` | 409 duplicate — F75 above |
| `send_message` to `Operator` | 404 *"Unknown recipient 'Operator': no agent by that name is registered in this project"* — F77 below |
| `decide_evidence` | never attempted; `agents.can_accept_evidence = 0` for every agent in the project, so it would have been refused too |

Four closed doors, and the agent said so in its own words: *"There's a task assignment issue
preventing the formal status update, so let me notify the operator directly."*

**Each refusal is individually excellent.** The `under_review` one is the best refusal in the
product: it names the problem, gives two remedies, and states the cost of doing nothing (*"Left as
is, the task is claimable by nobody and 'builder' counts as busy for every other review in this
project."*). This finding is not about any one of them. It is that the composition has no exit.

**One defect, or a design gap?** A design gap, and the diagnosis is specific: **the loop/flow
dispatch path staffs the task and the manual trigger path does not.** `scheduler.py:767-780` sets
`task.assignee = agent` and applies `completed -> under_review` *before* the reviewer's turn —
written before the transition deliberately, which is F70's fix. `POST /agent/trigger` with
`review_task_id` does none of this: `run_task_binding.task_named_by` treats `review_task_id` as
"check out this commit", explicitly *not* as ownership. So the same operation has two dispatch
paths and only one of them leaves the reviewer able to finish.

**Not fixed here, deliberately.** The repair could be (a) the manual trigger staffs the task the
way the scheduler does, (b) the trigger refuses up front when the task's assignee would block the
review, saying so before the money is spent, or (c) a reviewer gets a verdict channel that does not
require owning the task. (a) matches existing behaviour, (b) is the cheapest, (c) is the largest.
Which one is right is a product decision, and this run's standing instruction is to record rather
than guess — see `decisions_for_user`.

**Cost, since severity is ranked by that:** one full review turn (~3 minutes of Haiku, real
tokens) producing an approved verdict that reached no durable record.

### Fixed 2026-08-28 — and the drive found something three rounds of review did not

**The fix.** `trigger_agent_directly` is the single point both dispatch paths converge on
(`turn_scheduler.py:125` is its only caller), so the repair is one idempotent call to the statement
that already existed: `enter_selected_task`, which the flow path has used since F45. A third
caller, not a second copy. `_enter_selected_task` lost its underscore in the process — two test
modules already imported the private name across a module boundary, and a caller in production code
made it a lie.

**Ordering turned out to be the whole design.** Round 3 caught that placing the staffing beside
`prepare_review_turn` — which both earlier rounds had written — would breach a requirement F58 had
shipped four days earlier: *a request that is going to be refused SHALL NOT leave a workspace
behind*. Every refusal now precedes the checkout. That is free because `apply_transition` neither
commits nor flushes, so the staffing is pending state until the dispatch commits and any later
refusal abandons it.

**Two guards that were not in the original proposal**, both from the round-2 read of the code, both
reachable only from this path because the flow's reviewer ladder cannot produce their states:

* a task that is **neither awaiting review nor already in review** is refused — `enter_selected_task`
  writes the assignee *before* its status branch and that branch has no `else`, so staffing an
  `in_progress` task would take it from the agent working it and travel no transition. The route's
  only other check asks whether evidence names a commit, which is true of tasks still in progress;
* a task **already under review by a different agent** is refused — replacing the holder there also
  travels no transition, leaving a handover the append-only history cannot explain.

**The drive that closed this also opened one.** See **F108** at the end of this file: every one of
these refusals reached the operator as `200 {"success": true, "status": "queued"}` until it was
fixed, which three rounds of review had not noticed and the first live drive did.

### Driven live, 2026-08-28, `aw-e2e1` (`proj-46b602c1f3cb`), Hub on 8011 from source

| | |
|---|---|
| **The finding** | `task-c351c35eb718` dispatched to `reviewer` **by hand**: task read `under_review` held by `reviewer` immediately, and the reviewer recorded its verdict (`revision_needed`) **through the task itself**. Driven twice, either side of F108's fix. |
| **Author as its own reviewer** | `HTTP 403` — *"that is the agent recorded as completing it"*. Was a `200 "success": true` before F108. |
| **Not awaiting review** | `HTTP 409` against `task-a0409448ee8e`, which is `approved` *and* carries evidence naming a commit — the combination that makes the evidence check insufficient. Names `'approved'`. |
| **Held by another reviewer** | `HTTP 409` naming `'reviewer'`, task untouched, driven while a real review was in flight. |

Twelve mutations across the two halves, every one caught by the test that names it — including the
one that mattered, *moving* the staffing below the provisioning, whose first attempt was wrong
(it deleted the staffing instead of relocating it, so it was an earlier mutation wearing a second
label and proved nothing about ordering).

**State left behind:** in `aw-e2e1`, `task-c351c35eb718` sits `revision_needed` held by `reviewer`,
with `review-probe.md` committed in its own checkout; runs `run-a14e93734abc`, `run-151c6dd85bc6`,
`run-f3fac5f1383b` and the reviewer's first turn; the two stranded queue entries F108 created were
deleted. No job or loop was touched, so none was left enabled. 8000 and 8010 were never contacted.



---

## F77 — an agent has no way to address the operator

**Status:** open — filed, not fixed

**Severity: C**, but it is the reason F76's turn ended in prose rather than a record.

**What happens.** The reviewer, having concluded, tried to tell the person who asked:

```
mcp__agentweave__send_message {"to": "Operator", "content": "## Review Verdict: APPROVED ..."}
  -> 404 "Unknown recipient 'Operator': no agent by that name is registered in this project"
```

`send_message` addresses the roster, and the operator is not on it. `ask_user` exists but is for
*questions* — it takes 1-4 structured questions, blocks the run, and waits for answers. A verdict
is not a question, and an agent that used `ask_user` to deliver one would be misusing the one
blocking primitive the product has.

**The refusal is legible about the wrong thing.** It correctly says no agent is named `Operator`;
it does not say whether addressing the operator is possible at all, so the agent's next move is to
guess another name. Per the standing rule that a refusal must say what *would* work, this one
cannot, because nothing would.

**Whether this should be fixed is genuinely open**, and connects to the retired question-detection
backstop: the product deliberately does not guess when trailing prose is addressed to a human. An
explicit `notify_operator` would not be a guess. Recorded, not decided.

---

## F78 — the operator cannot clear a task's assignee, and the API reports that they did

**Status:** fixed — see the commit that adds `test_clearing_the_assignee_lets_the_operator_review_it_themselves`

**Severity: A.** A hard refusal names two remedies and only one of them is reachable; the other
returns `200 OK` and changes nothing.

**How it was found.** Driving row 17 (integration) in `proj-46b602c1f3cb`, taking the completed
`task-a0409448ee8e` through review so its work could reach `master`. F70's guard refused, correctly:

```
PATCH /tasks/task-a0409448ee8e {"status": "under_review"}
  -> 403 "... it is still assigned to 'builder', the agent recorded as completing it ...
          Assign a different reviewer, or clear the assignee to review it yourself."
```

I did what the second half of that sentence says:

```
PATCH /tasks/task-a0409448ee8e {"assignee": null}
  -> 200 {"assignee": "builder", "status": "completed"}      <-- unchanged, and reported as fine
PATCH /tasks/task-a0409448ee8e {"status": "under_review"}
  -> 403 (the same refusal, naming the same remedy I had just been told I performed)
```

**Cause.** `TaskUpdate.assignee` is `Optional[str] = None` and `update_task_for_actor` read it as
`if body.assignee is not None: task.assignee = body.assignee`. `null` and *field omitted* are the
same value, so the only reading available was "leave it alone". There was no way to say "nobody
holds this".

**The pattern was already in the file, one field away.** `escalation_agent`, declared eleven lines
below `assignee` in the same schema, carries a comment saying *"Deliberately not `Optional[str] =
None means leave alone` for this one: clearing an escalation agent is a thing the operator must be
able to do"*, and the service reads it through `"escalation_agent" in body.model_fields_set`. The
same problem had been recognised, solved and documented for the field where a hard guard did **not**
depend on it, and not applied to the field where one does.

**What made it severity A rather than a papercut.** A refusal would have sent the operator to the
other remedy. A success that changes nothing sends them nowhere — the response body is the wrong
answer to the question the request asked, so the natural next step is to disbelieve the guard rather
than the update. The escape hatch that does exist is undiscoverable and was never intended:
`{"assignee": ""}` satisfied `is not None`, so it wrote an **empty string** into the column. That
worked only by accident — every reader of `Task.assignee` in the Hub happens to test Python
truthiness — while the four `Task.assignee.isnot(None)` queries (`scheduler.py:968`,
`agents.py:303`, `agents.py:335`, `status.py:69`) would have counted `""` as a live holder.
`_agents_that_are_free` is one of them, which is the same capacity leak F70 was filed for.

**Why no test caught it.** `test_reviewer_is_not_the_author.py` had a test named *"the remedy the
refusal names has to work in one call, or the guard is a papercut"* — for the reassignment remedy.
The refusal names two. Only one was ever exercised.

**Fix.** `"assignee" in body.model_fields_set` in `update_task_for_actor`, so `null` means *clear
it* and an omitted field still means *leave it alone*; plus a `normalise_assignee` field validator
so `""` and `"   "` arrive as `None` and the column never grows a second spelling of "nobody".
Three tests, two of which were watched to fail against the defect, and both mutation directions
checked: restoring `is not None` fails the two F78 tests, and making the write unconditional fails
`test_an_omitted_assignee_still_leaves_the_holder_alone` and F70's own HTTP refusal test.

**Verified live**, not only in pytest: against a Hub restarted on the fixed code, `{"assignee":
null}` cleared to `None`, a priority-only PATCH left the holder alone, and `{"assignee": "   "}`
normalised to `None`.

---

## F79 — a task the operator has decided about still takes new runs

**Status:** fixed — see the commit that adds `hub/tests/test_a_decided_task_takes_no_new_work.py`

**Severity: A.** An agent is put to work on approved, merged work; the board reports it as running
on that work; and the operator's own release of the card is silently reversed.

**How it was found.** Not by looking for it. Immediately after driving row 17 to a successful merge,
a new trigger came back with `waiting_reason: "an older conversation's queued input is being
delivered first (run run-acbd6c2138b1)"` — a run I had not started, on a task I had just approved.

Reconstructed from the database:

| time (UTC) | what happened |
|---|---|
| 21:38:05 | `entry-5cea5e58d1f0` queued for `builder`, `task_id = task-a0409448ee8e` — legal, the task was `completed` |
| 21:55:12 | operator: `completed -> under_review` |
| 21:55:40 | operator: `under_review -> approved`; integration merges `70474c2` into `master` |
| 22:06 | operator clears the assignee (F78's remedy) |
| 22:07:11 | the Hub restarts and delivers the 29-minute-old entry: `run-acbd6c2138b1`, bound to the **approved, merged** task, and `assignee` is written back to `builder` |

The restart only widened the window. Turns serialise per agent, so an entry waiting behind another
turn while the operator approves the task is an ordinary occurrence, not a crash-recovery edge.

**Reproduced on demand, with no queue and no restart:**

```
PATCH /tasks/task-4ec8342f93ed {"assignee": null}     -> 200  (status: approved)
POST  /agent/trigger {"agent":"author","task_id":"task-4ec8342f93ed"}  -> 200, run started
GET   /tasks/task-4ec8342f93ed
  -> {"status": "approved", "assignee": "author", "assignee_status": "running"}
```

The board now says an agent is actively working a task whose code is already on `master`.

**Cause, and why it is the interesting kind.** The rule is not missing. It is written down, in
`run_task_binding.py`, in the docstring of the constant that names the band:

> Statuses at which a conversation's binding releases itself. Work that has been approved or
> abandoned is finished being worked on, and a thread that kept attributing turns to it would put
> stalled markers on a task the operator has already decided about (design D7).

Three things can name the task a turn works on. `release_conversations_bound_to` enforced the rule
on **one** of them:

| what names the task | covered before? |
|---|---|
| `Conversation.task_id` — the thread is already about it | **yes** |
| `InboundQueueEntry.task_id` — a turn queued earlier | no |
| `TriggerAgentRequest.task_id` — the operator naming it now | no |

`bind_run_to_task` then does the damage it is designed to do — *"Only where the task does not
already name someone else"* — which is exactly the case after the operator clears the assignee.
F78's remedy and F79 compose into undoing each other.

**Fix — two dispositions, because two different things are speaking.** The distinction is not
invented here; `resolve_bound_task` already draws it for a task that has been *deleted* since a
delegation was sent.

* **The operator naming a decided task now** is refused, `409`, at `POST /agent/trigger`, while
  they are reading the response: *"Task X is 'approved', which is a decision the operator has
  already made about it… Move it to 'revision_needed' to reopen it, or start the turn without
  naming a task."*
* **A queued entry whose task has since been decided** is *released*, not refused — beside the
  conversations, at the moment of the decision. Refusing at delivery would be actively wrong:
  `turn_scheduler` treats a non-transient refusal as grounds to abandon the entry after three
  attempts, so the operator's message would be discarded because of a decision taken about
  something else. The turn runs; only the claim that it is work on that task is dropped.

`release_conversations_bound_to` is now reached through `release_bindings_to`, so a fourth surface
acquiring a binding has one function to be added to rather than a call site to be remembered at.

**`review_task_id` is untouched.** Inspecting decided work is what a review is *for*, and clearing
it would restore the hole `every-run-knows-its-task` D3 closed — review runs with a NULL `task_id`,
and `under_review -> approved` transitions that no run records having caused.

**One thing this nearly got wrong, and it is the lesson the carry-forward predicted.** The refusal
was first written into `resolve_bound_task`'s explicit-`task_id` branch, where it read naturally and
passed a unit test. It could never have fired: `POST /agent/trigger` does not run a turn, it queues
an entry, so the task always arrives at that function as a *delegation* — and the only caller of
`trigger_agent_directly` (`turn_scheduler`) never passes `task_id` at all. The live drive caught it:
the trigger still returned `200`. The refusal moved to the route, and its tests were rewritten to go
over HTTP for exactly that reason. **A guard that is present, tested and unreachable is this
codebase's dominant failure mode** — F74, F41 and F38 are prior instances, and this one was authored
and caught inside a single sitting.

**Verification.** Seven tests, four watched to fail against the defect. Every guard mutation-checked
individually: dropping the `state == "queued"` filter fails the history test; also clearing
`review_task_id` fails the review test; widening the band to include `under_review` fails the
boundary test. Live-verified against a Hub restarted on the fixed code — the trigger on the approved
task now returns `409`, the same call on an `under_review` task still returns `200` and starts a
run, and the exact live sequence that produced the defect (queue an entry against a task, then
approve it) leaves the entry with `task_id: None`.

---

## F80 — `asker_waiting` is computed on one question route and hardcoded on the other four

**Status:** fixed — see the commit that adds `hub/tests/test_asker_waiting_is_the_same_on_every_route.py`

**Severity: B.** A wrong surface, on the one field whose whole job is to say whether answering this
question will reach anybody.

**How it was found.** Driving row 13. After declining a question whose asking run had already ended,
the same row read two different ways depending on which route asked:

```
GET  /questions                  -> [(q-a06..., asker_waiting: false), (q-d44..., asker_waiting: false)]
GET  /questions/q-a06ae761e397   ->   asker_waiting: true      (answered, run ended)
GET  /questions/q-d44e523b0d3d   ->   asker_waiting: true      (DECLINED, run ended)
```

**Cause.** `GET /questions` passes its rows through `_with_asker_state`, which resolves the asking
run in one bulk query. The other four routes returning a `QuestionResponse` — create, detail,
answer, decline — returned the ORM row, so Pydantic filled the field from the schema default,
`asker_waiting: bool = True`. The field was not stale on those routes; it was a **constant**, and
the constant is the answer meaning *someone is still waiting*.

**The sharpest instance is `answer_question`.** It computes this exact fact for itself —

```python
asker_still_waiting = question.blocking and not await _asking_run_has_ended(session, question)
```

— to decide whether to queue the answer as a turn, and then returns a body asserting the opposite.
The truth was already in the function, twenty lines above the return.

**Why B and not A.** No shipped surface acts on it: the dashboard reads the list and discards the
mutation bodies, invalidating and refetching instead. It is wrong to every other client, including
an agent reading the API, and it points the operator the wrong way — toward answering a question
that `release_block_for_question`'s F60 guard may then refuse for the very reason this field exists
to report.

**Fix.** `_with_asker_state_one`, built on the existing `_asking_run_has_ended` rather than a second
copy of the rule, applied at the four routes.
`test_the_list_and_the_detail_route_agree` pins the bulk path and the single-row path to each other,
which is what keeps two computations of one fact from drifting.

**One thing the suite caught that the fix got wrong first.** Applied to all four `return question`
statements mechanically, the change also hit `ask_question_for_actor` — a *helper*, not a route,
shared with the agent-facing path, whose caller reads `conversation_id` off the row it returns.
`test_conversation_attention.py::test_a_question_created_through_the_api_records_its_conversation`
failed on `QuestionResponse` not carrying that field. The conversion belongs at the route; the
helper still returns the row.

**Verification.** Five tests, three watched to fail against the defect. Mutation-checked: hardcoding
the field to `False` instead fails the two tests that assert a live asker and an unrecorded asker are
still presumed waiting — so the fix cannot have simply inverted the constant. All 102 question tests
pass.

---

## F81 — the operator's own refusal is written to the timeline twice

**Status:** fixed — see the commit that adds `_operator_already_refused` to
`hub/hub/api/v1/agent_actions.py`

**Severity: C.** The record, not the behaviour. The tool call is refused exactly once and the run
receives one answer; what doubles is what the operator is shown afterwards.

**How it was found.** Driving row 14 (permissions) in `manual` posture. The builder asked to `Write`
a file, the card came up, I pressed Deny once. The activity history then held two rows a second
apart, same `tool_use_id`, same wording:

```
2026-08-27T22:49:47.393783Z  permission_denied  {"tool_name": "Write",
    "tool_use_id": "toolu_01WvbJnCpC9U6Sdh8BKNjNiw", "reason": "the operator refused this action"}
2026-08-27T22:49:48.512857Z  permission_denied  {"tool_name": "Write",
    "tool_use_id": "toolu_01WvbJnCpC9U6Sdh8BKNjNiw", "reason": "the operator refused this action"}
```

**Cause — two writers, each correct in isolation.** `decide_permission_request` persists a
`permission_denied` event when the operator refuses, which is right: the operator's decision is the
event. Then the run reports the decision it received back through `approve_tool_call` ->
`_report_decision` -> `POST /agent-actions/permission-decisions`, and `record_permission_decision`
persists its own, which is also right for the decision it was built for — a refusal the *harness*
made, like the two `'/c/Users/huida/Documents/aw-e2e1' is outside your workspace` rows sitting a few
lines above these in the same history. `approve_tool_call` reports **every** decision, including
the ones it did not make, and neither writer knows about the other.

Two identical warn rows for one refusal is not merely noise: it reads exactly like an agent that
tried the same call twice and was refused twice, which is a different and more alarming fact than
what happened.

**The fix, and why it is on the Hub rather than in the reporter.** `record_permission_decision`
skips the event when a `PermissionRequest` for this run and this `tool_use_id` is already sitting
at `denied` — the card is the join, and its existence at that status is precisely "the operator
refused this, and the route that recorded their decision already wrote the row."

The alternative was for `_ask_operator` to flag its own decisions as already-reported and have
`_report_decision` stay silent about them. Rejected: it puts the invariant in the one process that
must import only stdlib and fastmcp, and it holds only for as long as every client is well-behaved.
The Hub-side join is the same lesson F79 paid for — put the guard where the traffic actually
arrives, not where the intent is legible.

Three neighbouring cases were checked rather than assumed, and each keeps its event:

- a card the operator let **expire** — nobody wrote an event for it, so the run's report
  (`"no operator answered within 20s"`) is the only record there is;
- a refusal reported by a **different run** for the same `tool_use_id` — two agents hitting one
  wall are two facts;
- a **locally decided** refusal carrying no `tool_use_id` at all. `approve_tool_call` defaults it
  to `""` and `open_permission_request` stores what it is given, so an empty id is a value a card
  can genuinely hold — without an explicit guard it would match, and one anonymous denied card
  would silence every anonymous refusal that run ever reports.

**Verification.** Four tests. Every guard mutation-checked individually: removing the skip fails
`test_the_operators_own_refusal_is_not_recorded_twice`; dropping the `run_id` scoping fails
`test_another_runs_refusal_of_the_same_tool_call_does_not_silence_this_one`; dropping the
`status == "denied"` filter fails `test_a_request_the_operator_let_expire_is_still_recorded`;
dropping the empty-`tool_use_id` early return fails
`test_a_locally_decided_refusal_without_a_tool_use_id_is_still_recorded`. The last of those needed
the test strengthened — the guard was invisible until the test built the card with `tool_use_id=""`
that it defends against. All 33 tests in `test_agent_actions_coordination.py` pass.

**Proven live** against a Hub restarted on the fixed code: a fresh manual-posture run, denied once,
left exactly one `permission_denied` row (`run-609b3c476147`, 22:58:05) where the pre-fix run left
two.

---

## F82 — creating a loop with initial tasks replies that its queue is empty

**Status:** fixed — see the commit that adds
`test_creating_a_loop_with_initial_tasks_reports_the_queue_it_just_seeded`

**Severity: B.** No state is wrong; the answer is. The one call whose job is to seed a loop's queue
tells the caller it did not.

**How it was found.** Driving row 11 (jobs and loops). `POST /projects/{id}/jobs` with
`stop_when_queue_empties`, a purpose, and one `initial_tasks` entry returned `201` with:

```
"loop": { "id": "loop-3f0427315dd9", ..., "queue": {}, "current_tasks": [] }
```

Reading the same loop back one call later:

```
"queue": { "pending": 1 },
"current_tasks": [ { "id": "task-1b7af6b595e6", "title": "Add a MULTIPLY note to README",
                     "status": "pending", "agent": "builder", "agent_capacity": "next" } ]
```

**Cause — the second implementation, built in the wrong order.** `_batch_loop_summaries` computes
this block in six fixed queries and is what `list_jobs`, `get_job`, the update route and the loop
routes all answer with. `create_job` does not call it. It assembles a `LoopSummary` by hand with
literal `queue={}, current_tasks=[], open_questions=0` — and assembles it *above* the loop that
creates `initial_tasks`, so even a computed block would have been computed before there was
anything to count. Two independent reasons for the same wrong answer.

The comment at the top of `loops.py` says of `firing_active` that every route "gets the same fact
from the same query, so no second implementation can drift from this one." The intent was already
written down; `create_job` is the surface it was not applied to. That is the shape iteration 3's
carry-forward names — **a rule enforced on one surface of several** — and this is the same
codebase's other habit, **a field hardcoded on one route and computed on another**, which is F80
exactly.

Why it matters beyond tidiness: an operator who has just defined a loop and its opening work is
shown an empty queue, and the obvious next move on an empty queue is to add the tasks again.

**The fix.** Delete the hand-assembled summary and call `_batch_loop_summaries` *after* the seeding
loop, which is the only ordering that can be right. `create_task_for_actor` commits, so the count
is of committed rows.

**Verification.** Two tests. The seeded case asserts the response reports `{"pending": 2}` and a
named current task, and that `GET /loops/{id}` agrees with it — the point of computing the block is
that the two cannot disagree. The bare case asserts a loop created with no `initial_tasks` still
reports an empty queue, so the fix cannot have simply invented content. Both mutations fail the
seeded test: restoring the hardcoded literal, and keeping the computed call but moving it back
above the seeding loop. 254 loop/job tests pass.

**Proven live** against a Hub restarted on the fixed code — see the drive record for iteration 4.

---

## F83 — a loop created enabled with `initial_tasks` never reaches the scheduler

**Status:** fixed — see the commit that adds `hub/tests/test_job_reaches_the_scheduler.py`

**Severity: A.** The operator arms a loop and the loop does not exist. `enabled: true` in the
response, a `next_run` in the response, a row reading `enabled = 1` — and no firing, ever, until
the Hub restarts.

**How it was found.** Driving row 11. I created a loop enabled, with one `initial_tasks` entry and
a once-a-minute cron, then waited. `next_run` passed. Nothing. `run_count` stayed 0 for ten minutes
while a *different* loop, created disabled and enabled afterwards through `PATCH`, fired on time
every minute in the same Hub.

Reading APScheduler own store against `ai_jobs` said it plainly:

```
job-46c034fb49f0  e2e-loop-drive       enabled=1  in_store=True     <- created disabled, PATCHed on
job-62babfc5bf69  e2e-operator-stop    enabled=1  in_store=False    <- created enabled, seeded
```

Bisected to one variable. `loop-enabled-noseed` (enabled, loop, **no** `initial_tasks`) registered;
`loop-enabled-seeded` (identical plus one initial task) did not. Reproduced on demand.

**Cause.** APScheduler `SQLAlchemyJobStore` runs on a **separate synchronous engine** pointed at
the same SQLite file (`JobScheduler._get_sync_engine`). `create_job` handed the job over while its
own async session still had a transaction open, so the store INSERT could not take the write lock:

```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked
[SQL: INSERT INTO apscheduler_jobs (id, next_run_time, job_state) VALUES (?, ?, ?)]
```

Seeding is what leaves the transaction open: `create_task_for_actor` ends with a `refresh` and four
read helpers after its last commit, and a read transaction is enough. The bare path has nothing
after its commit, which is why it always worked.

Then **three layers of silence**, which is the part worth keeping. `add_job` catches the error,
logs at `error`, and returns `False`. `create_job` did not read the return value. The whole block
sat inside a bare `except Exception: pass` commented "Scheduler might not be initialized yet". So
the one signal that survived was a log line under a logger whose output does not reach the Hub
console — and the only way to notice from outside was that the loop you armed never ran.

**The fix.** One `_hand_job_to_scheduler(session, job_id, job)` used by create, update and archive,
which **commits before handing over** — the request must not hold the database it is about to ask
a second engine to write. Registration failure is now logged loudly instead of swallowed; it is
deliberately not raised, because the row is the source of truth and `JobScheduler.start` reads it,
so an unregisterable job is picked up at the next restart. Late is a better answer than a 500 over
a job that already exists — but silent is not an answer at all.

**Verification.** Six tests. The stub scheduler records `session.in_transaction()` at the moment of
handoff, because that — not "was the scheduler called", which it always was — is the fact that
decides whether the store can write. Removing the commit fails all of them. Covers the seeded loop
(the reproduction), the bare job (the case that worked, so the fix cannot invert it), a job created
disabled, enable/disable through `PATCH`, and archive.

**Proven live** against a Hub restarted on the fixed code: `live-fix-seeded`, created enabled with
`initial_tasks`, appears in `apscheduler_jobs` immediately.

---

## F84 — an operator who stops a loop stops nothing; it fires for another seventeen minutes

**Status:** fixed — see the commit that adds `hub/hub/loop_ending.py`

**Severity: A.** The headline find of iteration 4, and the worst kind: every reader agreed the loop
had stopped while it went on spending tokens unattended. This is precisely the governance failure
the `archive_loop` docstring names — *"archiving one would hide unattended work that is still
firing"* — arrived at through a different door.

**How it was found.** Driving row 11. I created a loop, enabled, once-a-minute cron, then stopped
it the way the API offers: `PATCH /jobs/{id}` with a `stop_reason`. The response was `200` with
`ending_state: "stopped"`. Adding a task afterwards was refused, correctly, with *"This loop
stopped (operator stops this loop now) at an unknown time and its queue is closed."*

Seventeen minutes later:

```
STOPPED-LOOP enabled True runs 12 ending stopped queue {in_progress: 1}
  history [(completed, 23:26:00), (completed, 23:25:00), (completed, 23:24:00), ...]
```

Twelve firings after the stop. Every one a real agent turn. Every one recorded `completed`, so
nothing even looked wrong.

**Cause — a partial copy of an ending.** A loop ends two ways, and both must leave four facts:
`stop_reason`, `stopped_at`, `ending_state`, and `job.enabled = False`. The scheduler firing path
set all four. The operator route set **two**, and the two it omitted were *when* it stopped and
*the stopping itself*. `_loop_stop_reason` never consults `ending_state`, so nothing downstream
compensated: the job stayed enabled, stayed registered, and kept its cron.

`stopped_at` being NULL is the same omission quieter half. Two separate refusals quote it and both
fall back to the literal "an unknown time" — the Hub saying it does not know when something
happened that it did itself, a minute earlier.

This is the shape iteration 3 carry-forward named again: **a rule enforced on one surface of two.**
The docstring on `_authorize_loop_task_creation` even asserts the invariant that was false —
`ending_state` is *"set once, at the same site as stop_reason/stopped_at, only by the loop own
termination path"*. The operator route is a second site, and it set neither of the other two.

**The fix.** `hub/hub/loop_ending.py` states an ending once — `end_loop(job, loop, reason, when)` —
and both paths call it. The route additionally hands the now-disabled job back to the scheduler, or
the row would say stopped while APScheduler kept firing it: the same defect one layer out, and it
needed its own test because the row-level tests cannot see it. `QUEUE_DRAINED_REASON` replaces the
literal compared against in two places and returned from a third.

**Verification.** Eight tests across two files, each mutation-checked. Not clearing `job.enabled`
fails `test_an_operator_stop_disables_the_job`; dropping `stopped_at` fails two, including the one
that asserts the refusal text no longer says "an unknown time"; overwriting `ending_state`
unconditionally fails the test that an operator re-editing the prose does not rewrite a recorded
governance fact; not handing the job back to the scheduler fails
`test_stopping_a_loop_unregisters_its_job`. That last mutation passed everything at first — the
row-reading tests cannot see a stale scheduler registration, which is exactly how the original bug
survived. Two tests assert the other direction, that editing a running loop neither ends it nor
unregisters it. 260 loop/job tests pass.

**Proven live** against a Hub restarted on the fixed code: the stop returns `enabled: false` and
`stopped_at: 2026-08-27T23:32:09Z`, `apscheduler_jobs` is empty afterwards, and the queue refusal
now names the real time instead of "an unknown time".

---

## F85 — a loop stages a review it cannot start, wedges the task, and fails on it forever

**Status:** fixed — see the commit that adds `hub/tests/test_a_review_needs_something_to_review.py`

**Severity: A.** A single missing evidence call turns a working loop into a permanently stuck one,
with a task no agent can move and a firing that fails every minute for as long as the loop is
enabled.

**How it was found.** Driving row 11, watching a real loop work a real task. Firing one, 23:07,
claimed the task and the agent finished it. Firing two, 23:14:

```
history [('failed', '23:14:00'), ('completed', '23:07:00')]
error_summary: task task-1b7af6b595e6 has no recorded evidence, so there is no commit to
               review. Evidence naming a commit is what a review turn is given.
```

The task afterwards: `under_review`, `assignee: author`. It was `completed` a minute earlier.

**Cause — the selection mutates before the dispatch can refuse.** `decide_firing` picks a
`completed` task for review through the reviewer ladder, `_enter_selected_task` moves it
`completed -> under_review` and writes the reviewer into `assignee`, the caller commits, and only
*then* is the turn dispatched — where `prepare_review_turn` refuses, because a review turn is a
detached checkout of the commit the task's evidence names and there was no evidence at all.

Nothing in the walk had ever asked whether the review could be provisioned. The word **evidence did
not appear anywhere in `scheduler.py`**. The ladder answered *who* should review; nothing answered
*whether there is anything to review*.

And it does not recover. The task now sits in `under_review` naming an agent that never ran, which
is the F70 wedge reached by a new route: `_agents_that_are_free` counts that agent busy on it
forever, so the project loses a reviewer for every other task too. The next firing re-stages the
same review and fails identically.

**The fix.** The walk asks `requirement_evidence.commit_for_task_review` — *the same function the
trigger refuses with*, not a restatement of the rule, so the gate and the refusal cannot disagree —
before resolving a reviewer, and reports an unreviewable task as `unstaffed` with the reason. The
task is never moved, and the walk continues so ordinary work behind it still starts (D4: surface
the step, do not stop the flow).

`unstaffed` rather than a bare skip, deliberately: F64 already raised `unstaffed` into the loop's
stall sentence, so the operator reads *why* on the card. A queued entry and a failed `JobRun` — what
the old behaviour produced — appear on neither.

**One existing test's premise changed, and that is worth stating plainly.**
`test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn` required the firing to
dispatch the doomed review anyway, so the operator could see what was attempted. The live drive
priced that: it costs a status mutation the refusal cannot undo, a wedged task, and a failure
every minute. The test now asserts the stronger position — nothing dispatched, nothing mutated —
and its docstring records why it changed. Four other tests were fixture gaps: they built completed
tasks with no evidence and expected a review, so they now record evidence through a shared
`hub/tests/review_evidence.py` helper.

**Verification.** Five new tests, three mutation-checked dispositions: removing the gate fails
three; keeping the check but not skipping the selection fails three; turning the `continue` into a
`break` fails the test that ordinary work behind an unreviewable task still starts. Two tests assert
the other direction — a task whose evidence names a commit is still selected, and evidence that
names *no* commit gets its own distinct reason rather than being flattened into the first. 587 tests
across the loop, job, firing, review, flow, board and claimability suites pass.

**Proven live** against a Hub restarted on the fixed code. A fresh loop, a real agent turn that
completed the task without recording evidence, and then:

```
queue {'completed': 1}   current_tasks []
stall: task task-6fa800255c8f has no recorded evidence, so there is no commit to review...
history [('skipped', '23:52:00', tick_count 2), ('completed', '23:45:00', tick_count 1)]
```

The task stays `completed` instead of being wedged, the firing is `skipped` rather than `failed`,
and repeated skips **coalesce into `tick_count`** instead of appending a row a minute — so this no
longer feeds F12's history eviction either.

---

## F86 — an unattended loop inherits "ask me first" from a conversation the operator had hours ago

**Status:** fixed — see the commit that adds `UNINHERITED_BY_A_SCHEDULE_PERMISSION_MODE`

**Severity: B.** An overnight loop that stops to ask permission is an overnight loop that does
nothing, slowly, while reporting that it ran.

**How it was found.** Not looked for. While waiting on F85's live proof, the probe loop fired and
then sat for eight minutes producing nothing:

```
23:47:22 permission_denied  Edit        "no operator answered within 120s, so this was not approved"
23:49:24 permission_denied  Bash        "no operator answered within 120s, so this was not approved"
23:51:2x permission_denied  PowerShell  "no operator answered within 120s, so this was not approved"
```

The agent's `default_permission_mode` was `None` and the job named no posture. The conversation the
firing opened carried `{"permission_mode": "manual"}`.

**Cause.** `inherit_runtime_overrides` copies the agent's most recent conversation overrides into
any conversation opened without them, which is right and has a good reason: an operator sets a
posture, an agent hands work to a peer, and without inheritance the reply runs under a posture
nobody chose. It withholds exactly one value, `bypassPermissions`, whose comment says: *"reaching
runs started by a peer or a job, by a route the operator cannot see, is not what choosing it
meant."*

That sentence is true of `manual` too, and more sharply. My interactive row-14 drive two hours
earlier had set `manual` on a builder conversation; the loop inherited it at 23:45 and put every
tool call to a person who, by the definition of a scheduled job, was not there. The turn then
"completed" having been refused everything it attempted — the worst shape a failure can take,
because the JobRun says `completed`.

The asymmetry is that only the *permissive* extreme was considered. The blocking extreme fails the
same test and was not.

**This failure had already been seen once, at the neighbouring boundary, and written down.**
`checkpoint_cutover.py` carries the comment *"An inherited `{"permission_mode": "manual"}` is what
failed run-9058966b"* — the same symptom, diagnosed correctly, and answered there by deciding that
a handoff must not silently change posture mid-lineage, which is right for a handoff. Nobody
followed the `manual` back to where it entered. It entered at `inherit_runtime_overrides`, from an
interactive conversation, into a turn started by a schedule.

A loop lineage cannot now acquire `manual` by inheritance at all, so the cutover boundary needs no
change: with the source closed, there is nothing for it to carry.

**The fix.** `manual` is withheld from a conversation whose `origin` is `job` — dropped, not
replaced, exactly as `bypassPermissions` is, so the agent's own `default_permission_mode` and then
the catalog default decide an unwatched turn's posture, which is what they are for. Peer
conversations still inherit it: there the operator is usually present, and an extra card is cheap.

**Verification.** Five tests, both dispositions mutation-checked. Removing the scoped withhold fails
the firing test; widening it to every origin fails the peer test. Three more assert the fix did not
overreach — a firing still inherits a posture it can act on, the model travels beside a withheld
posture, and `bypassPermissions` stays unconditional.

**Proven live** against a Hub restarted on the fixed code, with the same `manual` conversation still
sitting at the top of the builder's history. Two firings, both `completed` in about twenty seconds,
their conversations carrying `runtime_overrides: null` instead of `manual`, and **no new permission
card created at all**.

---

## F87 (A) — a message the Hub gives up on disappears, and the record of it says nothing

**Status:** fixed `46458ae` — adds `delivery_state: "abandoned"` to `TimelineEntry`

**Severity: A.** Input the operator typed is discarded and no surface names it. The queue card
returns to `0 waiting`, the message vanishes from the conversation it was addressed to, and the
one durable record renders as the bare string `queue_entry_abandoned`. A dropped message and a
delivered one leave the product looking identical.

**How it was found.** Driving row 6 of the matrix, the inbound queue. The trial project had one
entry left `queued` at one delivery attempt from an earlier iteration. Two settings saves later
(a `PATCH /queue/settings` calls `schedule_agent` for every queued agent) it reached
`DELIVERY_ATTEMPT_LIMIT` and the Hub gave up, correctly and by design:

```
entry-241e4cf5e6d8  state: withdrawn  delivery_attempts: 3
abandoned_reason: "delivery failed 3 times (task task-1b7af6b595e6 has no recorded evidence, so
                   there is no commit to review...); the Hub stopped retrying"
event: queue_entry_abandoned  severity: warn
```

The abandonment machinery is right. What follows it is not. Immediately afterwards:

```
GET /queue/author/status  ->  {"waiting_count": 0, "waiting_reason": null, "delivery_attempts": 0}
```

Which is exactly what a *successful* delivery leaves behind.

**Three surfaces, and all three were silent.**

1. **The conversation.** `_queued_entries_for` selected `state == "queued"`, and an abandoned
   entry is `withdrawn`. So the message the operator was watching wait simply left the thread. It
   is the place they will look, and it was the one place guaranteed not to have it.

2. **The queue card.** `useSSE`'s handler for `queue_entry_abandoned` invalidates
   `['project', pid, 'queue', agent]`, and its comment states the intent exactly — *"The Hub
   stopped trying to deliver something. The queue card is where that shows."* The card cannot show
   it. `useQueuedEntries` fetches `?state=queued`, so the refetch the event triggers is the
   refetch that removes the row; and `useQueueStatus` returns `0 waiting`, which hides the
   indicator entirely (`AgentTimeline` renders it only `when waiting_count > 0`). The invalidation
   works perfectly and produces a *cleaner* screen.

3. **The activity log.** The only durable record, and `summaryForEvent` had no case for it. Its
   default branch reads `data.error ?? data.message ?? data.summary ?? data.title`; the payload's
   field is `reason`. So the summary equalled the type, `EventRow` suppresses a summary that
   equals the type, and the row read `queue_entry_abandoned` with a warn chip and nothing else —
   no reason, no agent, no content, no conversation. `queue_agent_paused` (`reason`) and
   `queue_entry_released` (`released_from_depth`) are in the same state for the same reason. This
   is the failure that file's own comment describes two cases above, about `permission_denied`:
   *"these carry the only detail worth reading in a field the default branch does not look at, so
   without a case they render as their own event name twice over."*

**One defect or a design gap?** One defect, arrived at from three directions — and the third time
this corpus has found *a comment asserting an invariant that a second site does not keep*
(cf. F82, F84). Every part of giving up on an entry is implemented and correct; nothing that
reports it was.

**The fix.** The thread keeps it. `_queued_entries_for` now also selects entries the Hub abandoned,
`TimelineEntry` gains a third `delivery_state` — `abandoned` — and an `abandoned_reason`, and the
timeline renders it in place, at the timestamp it arrived, tagged `not delivered` in red with the
reason beside it and no controls (both the withdraw and the release endpoints refuse a row that is
no longer `queued`, so either would be an offer to be told no). `summaryForEvent` gains the three
queue cases.

Keyed on `abandoned_reason` rather than on `state == "withdrawn"`, because an operator withdrawal
reaches the same state: putting one of *those* back would re-show a message they chose to take
away. Tested both ways.

**Live proof**, against a Hub restarted on the fixed code — the same entry, in the same
conversation, at its original position in the thread:

```
GET /agent/author/chat/conv-d3d63affa16c
{"id": "entry-241e4cf5e6d8", "kind": "operator_input", "delivery_state": "abandoned",
 "hop_budget_exceeded": null, "timestamp": "2026-08-27T23:14:00Z",
 "abandoned_reason": "delivery failed 3 times (...); the Hub stopped retrying"}
```

and the operator's own withdrawal from earlier the same iteration (`entry-9cf685b52ae8`, withdrawn
while queued) is still correctly absent from `conv-b9fc97d600f1`.

**Verification.** 3 Hub tests + 3 UI tests + 3 event-summary tests, each watched to fail first.
Four mutations, each failing a named test: dropping the `abandoned_reason` condition brings the
operator's withdrawal back; dropping `or abandoned` from `hop_budget_exceeded` re-offers Continue;
collapsing `delivery_state` to two values loses the state; and dropping `!abandoned` from `actions`
re-draws the controls. That last one initially passed under mutation — the test asserted the
absence of the *glyph* and the withdraw control is a bare `close` icon — which is F81's lesson
again: a guard no test can see is a guard the next reader deletes. The assertion now keys on the
button's `title`.

**What this does not fix, and is not claiming to.** The queue card's own two hooks still ask only
about `queued`, so `0 waiting` remains what the card says after an abandonment. The conversation
and the activity log now both carry the fact, which is where an operator looks for a *message*;
making the card carry a count of dropped input is a separate question about what that number
means.

---

## F88 (A) — two grants the operator can confer, and neither has ever done anything

**Status:** fixed `a42f978` — defaults `checkpoints.visibility` to `project`, backfills the stored
rows in migration `0097`, and adds `list_checkpoints` / `read_checkpoint`

**Severity: A.** `can_read_checkpoints` and `can_recall` are a documented capability with a
settings control, a canonical-context paragraph that tells the agent it has them, and a spec
requirement. Turning both on changed nothing whatsoever. An operator who grants a reviewer access
to its author's history gets a reviewer that is refused everything, with a not-found the product
deliberately makes indistinguishable from "there is no such record" — so the operator has no way
to tell the grant failed, and the agent is told to read the refusal as an absence.

**How it was found.** Driving row 15 of the matrix, checkpoints. A real turn on `author`,
`POST /conversations/{id}/checkpoint`, a real generated checkpoint (`ckpt-d4ba5292443a`, probes
passed) citing one observation, `out-e3b591766336`. Then `builder`, granted both:

```
PATCH /agents/builder  ->  {"can_read_checkpoints": true, "can_recall": true}

builder, live turn:  recall("out-e3b591766336")
  ->  Hub rejected GET /recall/out-e3b591766336 (404):
      No recorded observation by that id is available to you.
```

**The cause is one absent default, and the whole shape is in `checkpoint_access.py`'s own
docstring.** Effective access is `capability ∩ visibility`. `may_read_checkpoint` returns True for
a peer only when `checkpoint.visibility in ("project", "granted")` — and `visibility` shipped
defaulting to `"private"` with **no caller anywhere passing anything else**: not the operator's
"take a checkpoint now" route, not the threshold trigger, not the handover path. There is no route,
no MCP tool and no UI control that can change one. So the visibility side of that intersection has
been closed for every checkpoint that has ever existed, in every project, and `may_recall` — which
requires `may_read_checkpoint` — was unreachable for a peer by construction.

**Why the suite did not see it.** `hub/tests/test_checkpoint_access.py` is thorough and every one
of its peer-access tests passes `visibility="project"` **explicitly** to its `_checkpoint` helper.
The access rules are correct and well tested; what was never tested is the value the product
actually stores. This is the same failure the repository had already diagnosed once and written
down, in `api/v1/agents.py` above `GRANT_FIELDS`, about `can_accept_evidence`: *"The column and its
migration have existed since 0068. Nothing could set it — no schema, no route, no control — so
`requirement_evidence.may_accept` refused every agent in every project, and a capability enforced
everywhere and grantable nowhere is a refusal of everyone."* Same sentence, one column over.

**The fix follows the spec rather than inventing a policy.** `conversation-checkpoint` says *"A
checkpoint MAY additionally restrict itself, in which case access requires both the reader's grant
and the checkpoint's own visibility"* — restriction is an exception a checkpoint opts into, not the
state every checkpoint is born in. So the default becomes `project`, and migration `0097` moves the
stored rows: every stored `private` is the absent default rather than anybody's decision, and
leaving them would split a project's history at the migration with the older half permanently
unreadable. **The system stays closed by default** — both reader grants still default to False, and
this changes nothing about them.

**A second half, found while fixing the first.** With visibility corrected, `can_read_checkpoints`
still granted nothing on its own: the agent surface had no tool that returns a checkpoint, only
`recall`, which reaches *observations* a checkpoint cites. The spec's own scenario requires the
other state to exist — *"the observation request is refused **and the checkpoint remains
readable**"* — and the canonical context promised it in as many words: *"You may read your peers'
checkpoints."* `submit_checkpoint_notes`' docstring assumes it too, telling an agent its notes are
read by *"a reviewer of what you just finished"*. Nothing gave that reviewer a way to find or open
one. So `list_checkpoints(agent=None)` and `read_checkpoint(checkpoint_id)` now exist, over
`GET /agent-actions/checkpoints` and `/checkpoints/{id}`, identity taken from the run's minted
credential like everything else in that namespace — `agent` narrows the list and can never widen
it, and an id out of reach answers 404 for the same disclosure reason `recall` does.

**Proved live against a Hub restarted on the fixed code**, same project, same checkpoint:

```
builder   (granted)   list_checkpoints  -> 1 row, agent "author", yours: false
                      read_checkpoint   -> "Create a CSV schema documentation file with ..."
                      recall            -> "Done. The `id` column should be indexed because ..."

reviewer  (ungranted) list_checkpoints  -> 0 rows
                      read_checkpoint   -> 404 No checkpoint by that id is available to you.
```

**Left for the operator.** `private` is now a value nothing produces, in the other direction: there
is still no way to restrict one checkpoint. That is a `MAY` in the spec and a real capability
question — a per-checkpoint control, an agent-level default, or neither — and it is not guessed at
here. `granted` remains unreachable and always was; it implies a grantee list that no table holds.

---

## F89 (A) — turning on automatic checkpointing kills the turn that triggers it

**Status:** fixed `7cecd71` — commits the session before `run_worker` in `checkpoint_generation`

**Severity: A.** The agent's run never finishes. No `run_completed`, no `ended_at`, no exit code;
the `Run` row sits `running` forever and the agent sits `running` with it, so nothing can be
scheduled onto it again. The transcript shows the turn finished normally — the agent said its piece
and stopped — and every product surface says it is still going. Reproduced twice, on two different
agents, first time each.

**How it was found.** Driving row 15 of the matrix. Automatic mode needs a threshold a cheap turn
will cross, so `reviewer` was put on `automatic` with `tokens/5000` and asked to say one word:

```
PATCH /agents/reviewer  {"checkpoint_mode":"automatic","checkpoint_threshold_mode":"tokens",
                         "checkpoint_threshold_value":5000}
trigger reviewer: "Say the single word ACKNOWLEDGED and stop."
```

The agent said ACKNOWLEDGED and the transcript recorded `Completed`. Four minutes later:

```
running runs: [('run-cabd138d5be1', 'reviewer', 'conv-738f939e6999', '01:42:57')]
agents:       author idle | builder idle | reviewer running
events:       run_started ... context_warning ... context_warning(null)   <- and nothing after
```

No `run_completed` event was ever written. `builder`, configured the same way and given the same
one-word turn, wedged identically — and its checkpoint came out `unwritten` with
`worker_invocation_id = None`, which is the thread that leads to the cause.

**The cause is a lock held across a CLI spawn.** `checkpoint_trigger.consider` opens a session,
and `generate_checkpoint(db, …)` uses it for every read — the anchor, the loop, the envelope, the
transcript, the pending notes — and then calls `run_worker` **with that transaction still open**.
`run_worker` is a real `claude` spawn, measured at ~20s. SQLite gives no concurrency to a
connection waiting behind another one's transaction: for those twenty seconds every other
connection's write waits out the 5s busy timeout and then raises `database is locked`.

`_record`, which writes the `WorkerInvocation`, opens its own session and is wrapped in
*"accounting must not take the work down with it"* — so it swallowed the lock error and returned
`None`. That is the `worker_invocation_id = None` above, and it is the visible corner of what was
happening to every other writer at the same moment, including the live turn's own output recording
and its finalisation.

`run_worker`'s docstring already states the rule that was broken: *"Callers pass primitives rather
than a `Runner` row so the spawn does not hold a session open across a call that can take
minutes."* Passing primitives is not enough if the caller's own transaction is open around the
call.

**The fix is one commit, in the literal sense.** Everything before the spawn is reads, so
`generate_checkpoint` commits before calling `run_worker`, ending the transaction and releasing the
lock for the spawn's duration. `expire_on_commit=False` on the session factory, so the objects
loaded above stay usable. `probe_checkpoint` renders its prompt first and commits second, for the
same reason — rendering inside the call argument would reopen a transaction across the second
spawn.

**The test asserts the property at the spawn**, not by racing a writer: `run_worker` is wrapped and
`db.in_transaction()` recorded at each of the two calls. Watched to fail with the commit removed —
`[True, False]` against `[False, False]`, the generation spawn holding the lock and the probe not,
which is exactly the asymmetry the live evidence showed.

**Why the suite could not see it.** The same reason as [F88] one file over: the tests drive
`generate_checkpoint` on a session with nothing else contending for the database, so a transaction
held across a stubbed, instantaneous spawn costs nothing and is invisible. The defect only exists
when a second connection is trying to write — which, in production, is every single time, because
the only thing that triggers this path is a live turn streaming output.

**Proved live against a Hub restarted on the fixed code**, same project, same configuration.
`builder` under `automatic` with `tokens/5000`, twice:

```
run_started -> context_warning -> run_completed        (both runs, both times)
conv-f8277f71ddb7  archived  ->  conv-83decbbd4a7c  origin "handoff"
conv-a01a34fb6975  archived  ->  conv-5a90f69aee1d  origin "handoff"
```

Which corrected a wrong conclusion on the way. Before the fix, the checkpoint was generated and
the conversation stayed open, and the obvious reading was that `automatic` can never cut over —
`cut_over` refuses a conversation whose run is in progress, and the trigger fires from a mid-run
reading. That reading was wrong: generation takes ~20s, an ordinary turn ends inside that window,
and once the run is no longer wedged the cutover happens. **The refusal was the wedge, not the
design.** What is *not* measured, and is therefore not claimed here, is the turn that outlasts its
own checkpoint generation — that one should meet the refusal, and nothing retries it afterwards
because the next reading is short-circuited by `_nothing_new_since_last_checkpoint`. Left for the
next sweep to measure rather than asserted from the code.

**Left for the operator, and not guessed at.** The engine opens SQLite with neither WAL nor an
explicit `busy_timeout` (`db/engine.py`: `connect_args` carries only `check_same_thread`). WAL
would make readers stop blocking writers at all and would have made this defect a slowdown instead
of a wedge. It is also a deployment-visible change — extra `-wal`/`-shm` files, and it does not
work over a network filesystem — so it is a decision rather than a repair, and the repair above
stands on its own either way.

---

## F90 (A) — a turn held back by another agent's turn is never let go again

**Status:** fixed `a053553` — re-drains the project's queued agents when a run ends

**Severity: A.** The operator's message is accepted, sits in the queue, and never runs. Not
abandoned, not refused, not reported: `waiting_count: 1`, `waiting_reason: null`,
`delivery_attempts: 0`, every agent idle, and nothing in the product will ever pick it up. It ends
when the operator happens to do something unrelated — open the project, save settings, relocate the
workspace — which is the only place `redrain_queued_agents` is reachable from.

**How it was found.** Driving row 16 of the matrix, per-task worktrees, and specifically design
D8's *"a task's checkout takes one writing turn at a time"*. Two agents, one task:

```
trigger builder,  task_id=task-294f3af9448b, "sleep 90 then append a line"   -> running
trigger reviewer, task_id=task-294f3af9448b, "do nothing"                    -> queued
```

The refusal is exactly right, and classified exactly right: **transient**, so the entry keeps its
delivery attempts rather than counting one towards abandonment. Then builder finished, and:

```
t+100s   author idle | builder idle | reviewer idle
         GET /queue/reviewer/status -> {"waiting_count": 1, "waiting_reason": null,
                                        "delivery_attempts": 0}
```

Four minutes of that. Then an unrelated `PATCH /queue/settings` — changing nothing, saving the same
four values back — delivered it instantly, because that route calls `redrain_queued_agents`.

**The cause is a wake-up that was never wired.** `turn_scheduler`'s own comment on the transient
branch says the entry *"stays `queued`, and the next tick tries again."* **There is no tick.**
Scheduling is entirely event-driven, and the event that should free this entry — the holder's run
ending — calls `schedule_agent(project_id, agent)` for the agent whose run it was. The agent that
was parked is a different one, by construction: D8 refuses a *second* agent on a task the first is
holding.

The product has already met this shape once and written it down, six hundred lines above the fix,
on the spawn-failure branch: *"without this an entry handed back here waits for something else to
drain it. Nothing does on a timer… Measured — an entry sat `queued` at one attempt until an
unrelated settings save drove the second."* Same sentence, same route, one agent over.

**The fix.** Every terminal exit of a run — completed, failed, and the spawn that never started, on
both the exec and the app-server paths — now calls `redrain_queued_agents(project_id)` **instead
of** `schedule_agent(project_id, agent)`, and unconditionally where two of the five were gated on
the run having handed entries back. A re-drain is a strict superset: `schedule_agent` answers
"queue is empty" for an agent with nothing waiting, so the ending run's own entries are still
picked up. Replacing rather than adding matters — the first version did both and scheduled the
ending agent twice, which `test_a_pre_spawn_failure_schedules_the_agent` caught by counting the
calls.

Project-scoped rather than "the agents waiting on the task this run held", deliberately: the
invariant is that a run ending frees whatever it was holding, and the task checkout is only today's
instance of that. Scoping to the task would be correct now and silently incomplete for the next
hold anyone adds. It costs nothing when nothing is waiting — the query returns only agents that
actually have a queued entry, and `schedule_agent` refuses a busy one.

**The test the suite already had, and what it could not say.**
`test_a_collision_leaves_the_entry_queued_and_delivers_it_when_the_task_is_free` sets the collision
up correctly, ends the holder's run **with a database write**, and then **calls `schedule_agent`
for the challenger by hand**. So it proves the entry *can* be delivered once the task is free —
which was never in doubt — and not that anything delivers it. The step it performs on the product's
behalf is the exact step the product omits. Third instance tonight of the same class: [F88]'s
access tests pass a `visibility` nothing produces, [F89]'s generation tests spawn with no second
writer contending, and this one schedules the turn itself.

The new test takes a **real** holder turn and lets it end through `_execute_run`, then asserts a
`Run` row exists for the challenger — nothing in it schedules that agent. Watched to fail with the
five new calls removed. Two harness notes that cost a round each: this file's other tests raise
`RuntimeError` from the patched spawn, which escapes `_execute_run` entirely (the spawn sits above
its `try`) so the run is never finalised and the moment under test never arrives — `FileNotFoundError`
is the branch that ends a run properly. And `_agent` posts the whole roster through session sync, so
registering two agents takes one call, not two.

**Proved live against a Hub restarted on the fixed code**, same two agents, same task: the trigger
answered `queued` with the holder named as the reason, and the instant builder went idle reviewer
went `running` and answered.

**What this does not fix.** While the entry is parked, `GET /queue/{agent}/status` still reports
`waiting_reason: null`. The reason exists — the trigger response carried it verbatim — but nothing
persists it onto the entry, so the durable surface an operator would consult a minute later says
only that something is waiting. That is [F87]'s shape again, and it is a separate change.

---

## F91 (A) — restarting the Hub spends the operator's message, for a condition that had already passed

**Status:** fixed (this iteration)

Row 19, resilience. Trigger a turn, kill the Hub while it runs, restart it. Measured live in
`aw-e2e1`, twice, before the fix:

```
02:54:45  trigger builder      -> run-41977e93fb94, entry-24d8b3025c2d delivered, attempts 0
02:54:5x  kill -9 the Hub
02:55:06  restart              -> run_interrupted, returned_entry_ids: [entry-24d8b3025c2d]
02:55:0x  GET /queue/builder/status
          {"waiting_count": 1, "waiting_reason": "delivery failed 2 times; 1 attempt left",
           "delivery_attempts": 2}
```

**Two** attempts for one restart, and then the entry sat `queued` with every agent idle until an
unrelated `PATCH /queue/settings` delivered it. `DELIVERY_ATTEMPT_LIMIT` is 3. Three restarts with
a run in flight and the operator's message is withdrawn with *"delivery failed 3 times; the Hub
stopped retrying"* — a message they typed, gone, because they updated the Hub.

Only one of those two attempts is legitimate. `return_run_entries` charges one because the run
really did die. The second comes from `reconcile_interrupted_runs`, which finishes by re-draining
the agents it repaired — and it runs inside `lifespan()`, **before the Hub has served a single
request**. In native mode the callback address is observed from a real connection
(`bound_address.py` exists precisely so it is fact rather than configuration), so at that moment
there is none, and `trigger_agent_directly` refuses with:

> Cannot determine the Hub's own address for this run … **retry once the Hub has served at least
> one request.**

That refusal was classified terminal. `turn_scheduler`'s own comment explains what terminal means —
a refusal that *"repeats identically forever"* — and `TriggerAgentError.transient` is documented as
asking *"does this refusal describe a condition that clears on its own?"* The refusal's own last
sentence is the answer. The repository had already written the sentence that names the defect, in
two places, about this exact field.

**Fixed in two halves, because either alone is insufficient.**

1. The refusal is now `transient=True`, so nothing is charged for it. But a transient refusal
   records nothing and waits for a later tick — and on this path there is no later tick, which is
   [F90] exactly.
2. So the startup re-drain is **deferred** rather than attempted: `reconcile_interrupted_runs` asks
   the new `bound_address.known()` and, when the answer is no, parks the agents it repaired.
   `main.py`'s address-observing middleware drains them on the first request the Hub serves — the
   precise moment the postponed condition clears. Fire-and-forget, so a queue drain can never
   delay or fail an operator's request.

`bound_address.known()` also replaces the hand-spelled `bool(os.environ.get("HUB_URL")) or
bound_address.get() is not None` in `agents.py`. Two call sites spelled it out and a third did not
ask at all; one function now holds it.

**Verified.** Two Hub tests watched to fail (the deferral, and the `transient` classification),
plus 125 passing across the eight touched files. Live, on the fixed code, the identical experiment:

```
03:02:52  trigger reviewer     -> run-f45cd63e3b11, entry-478bafdc055f, attempts 0
03:03:0x  kill -9 the Hub
03:03:11  restart              -> run_interrupted, attempts 1
03:03:25  entry-478bafdc055f delivered in run-64f340ce6161, unprompted
03:03:32  run-64f340ce6161 completed
```

One attempt instead of two, and the message ran fourteen seconds later with no operator action
where before it needed one.

---

## F92 (B) — a run the Hub reconciles is billed to nobody, beside a total that says it is complete

**Status:** fixed (this iteration)

Row 18, accounting. `usage-accounting`'s first requirement is *"exactly one accounting outcome for
every Hub-owned run after that run ends"*, and an unavailable one *"MUST NOT represent missing
values as zero"*. Measured in `aw-e2e1` before the fix:

```
runs by status, joined against turn_usage
  completed    73   missing 0
  interrupted   3   missing 3      <- all of them
```

Three runs ended with no accounting outcome of either kind. One had been streaming for **thirteen
minutes** before a Hub bounce killed it. And the aggregate the operator reads said:

```
{"measured_turns": 72, "unavailable_turns": 0, ...}
```

`unavailable_turns: 0` is not silence — it is a positive claim that nothing in this project is
unmeasured, made over three turns that are. That is worse than a wrong number, because a wrong
number invites a second look.

Two paths ended a run without recording one. `reconcile_interrupted_runs` never did, and
`_execute_run`'s catch-all handler — the last of its five terminal sites — never did either; the
other four all call `record_turn_usage(sample=None)`, and the `FileNotFoundError` branch even
carries the rule in a comment about a sibling concern: *"the rule is 'a terminal run leaves nothing
pending', not 'the paths where we expect some'."*

Both now record an explicitly **unavailable** outcome. `Run` carries no runner, so reconciliation
recovers it from the agent's binding (`_runner_cli_for_agent`) and records `None` rather than a
guess when the agent has since been unbound. `record_turn_usage` was already idempotent — it
returns the existing row — so a crash between "measured outcome written" and "run row committed"
cannot have a measured turn overwritten by an unavailable one; that is pinned by its own test.

**Live, after the fix**, the same project reports `{"measured_turns": 74, "unavailable_turns": 9}`.
Nine turns the operator can now see are unaccounted for, where the surface previously said none
were.

**The rest of row 18 is clean, and was driven rather than read.** With `token_budget` set to 1000
against 12.68M of measured usage: an operator trigger started a run immediately
(`"status": "running"`, no waiting reason); an agent-origin entry created by `builder` calling
`send_message` stayed `queued` with `waiting_reason: "token budget exhausted"` and
`delivery_attempts: 0` — the refusal is correctly transient, so pausing an agent does not spend its
message; and clearing the budget to `null` delivered it unprompted. All three of the spec's
scenarios for *"a project token budget pauses autonomy but not the operator"* hold as written.

**Not fixed, and recorded as a question for the operator:** `worker_invocations` — the checkpoint
and probe spawns — are real model calls made on the operator's behalf and appear on **no aggregate
surface and in no budget**. `aw-e2e1` has 14 of them costing 297,475 `usd_micros`, about 9% on top
of the 3,175,674 the accounting API reports, and the only read path anywhere is one checkpoint's
own detail. `WorkerInvocation`'s docstring calls the table *"the whole accounting surface for such
calls"*, which is true of where it is written and not of where it is read. Whether that cost joins
the project total, sits beside it, or counts against `token_budget` is a decision about what a
budget means, not a repair — see `decisions_for_user`.

---

## F93 (A) — a runner binary that is present but broken wedges its agent until the Hub is restarted

**Status:** fixed (this iteration)

Row 19, resilience: *corrupt or withhold a runner binary*. `_execute_run` wraps its spawn in
`except FileNotFoundError` and nothing else. A missing binary is one way a spawn fails; it is not
the common one on Windows. A corrupt or non-executable file raises `OSError` (`[WinError 193] %1 is
not a valid Win32 application`), a denied one `PermissionError`, and `pywinpty`'s own failures
neither. **Every one of those escaped the coroutine entirely.**

Driven live in `aw-e2e1` — a 31-byte text file named `claude.exe`, first on the Hub's `PATH`, so
`shutil.which` finds it and launchability passes:

```
03:08:58  POST /agent/trigger author  -> 200, run-91015150a198, "status": "running"
03:09:08  POST /agent/trigger author  -> 200, "waiting_reason": "agent is already running"
03:09:33  RUN   status running · pid None · ended_at None · error None
          agents  [author running, builder idle, reviewer idle]
          turn_usage rows for the run: 0
          events: nothing. No run_failed, no queue_entry_abandoned, nothing.
```

The row stayed `running` **with no pid**, forever. The agent card read `running`. `POST
/agent/trigger`'s "already has a run in progress" guard then refused that agent every subsequent
turn, so the operator's next message queued behind a run that had never started. The exception went
to asyncio's unretrieved-task handler, where nothing reads it. The only recovery was restarting the
Hub — which is to say the operator's remedy for a broken runner was to bounce the whole product.

The fix is `except Exception`, which the branch body was already correct for: it marks the run
failed with the OS's own message, records the accounting outcome, returns the input to the queue,
broadcasts `run_failed`, and re-drains. `CancelledError` is a `BaseException` in 3.8+, so real
cancellation still propagates.

**Live, on the fixed code, identical setup:**

```
run-1cb2dff1bbc5  status failed · ended_at set
  error: "This version of %1 is not compatible with the version of Windows you're running..."
  turn_usage: unavailable, runner claude
events: run_failed (carrying that error), queue_entry_abandoned (attempts 3, reason stated)
agents: [author idle, builder idle, reviewer idle]
```

The retry-to-abandonment is the designed behaviour for a spawn that fails identically every time
([F56]'s shape) and the operator is told about it three ways. Before the fix they were told nothing
and lost the agent.

---

## F94 (B) — kill an agent and the product tells you `exit 4294967295`, again

**Status:** fixed (this iteration)

Row 19, resilience: *kill an agent process*. Everything about the recovery is right — the run went
`failed`, a **measured** accounting outcome was recorded (35,742 tokens; the result event had
already been parsed), the entry went back to the queue, and a retry run completed. What the
operator was told about it was not:

```
GET /agents/reviewer/timeline
  "Run failed (exit 4294967295)"
```

That number is `0xFFFFFFFF`, Windows' `-1` read unsigned. It is verbatim the loop-8 finding that
`readable_exit_code` exists for, whose own docstring says *"an operator seeing it has no reason to
connect it to the process they just killed — measured on 2026-08-14"*. The fix shipped, with a test
named `test_the_payload_renders_the_exit_code_rather_than_shipping_it_raw` asserting finding L9-1's
rule that **a broadcast payload is a display surface**.

It shipped into `_transport_failure_fields` and `_runtime_failure_fields` — both of which are
**Codex** paths. The pty path, which is to say the Claude path, which is to say the default runner,
calls `_broadcast_run_lifecycle(..., exit_code=exit_code)` with the process's own number. The
summary an operator reads is derived from that payload (`agents.py::_run_lifecycle_summary`), so
one raw value reached every surface. The `run.error` beside it is `NULL` for a killed process, so
the ten-digit number was the entire explanation on offer.

Rendering now happens **inside `_broadcast_run_lifecycle`**, over `exit_code` and
`runtime_exit_code`, rather than at each caller — which is precisely how this path came to miss it.
`readable_exit_code` is idempotent, so the two callers that already rendered are unaffected, and
`Run.exit_code` in the database stays raw, as design D3 requires.

**Live, on the fixed code:** killed a running `builder` at pid 23260 →
`"Run failed (exit -1)"`, with `runs.exit_code` still `4294967295` in the database.

The general lesson is the one this file keeps re-learning: a rule applied at N call sites is a rule
that holds at N-1 of them. This one now lives at the join.

---

## F95 (A) — a project can be moved exactly until its first turn, and never again

**Status:** fixed (this iteration)

Row 19, resilience: *drive a project whose working directory has moved*. Everything up to the
repair is right. Moving `aw-f52` on disk flipped `directory_state` to `missing` within seconds, the
project stayed visible with its history, and a trigger was refused with a typed error naming the
path:

```json
{"code": "project_workspace_missing",
 "message": "project directory does not exist: C:\\Users\\huida\\Documents\\aw-f52",
 "directory_state": "missing"}
```

Then the repair itself:

```
POST /projects/proj-a1736a6a596b/relocate  {"path": ".../aw-f52-moved"}
  422 {"code": "project_relocation_active",
       "message": "project cannot be relocated while a run or worktree mutation is active"}
```

**Nothing was active.** One run has ever existed in that project and it is `completed`; the single
agent is `idle`. What blocked the move was `.agentweave/worktrees/builder`, left behind by that one
completed turn on 2026-08-27.

`_guard_relocation` refused whenever `.agentweave/worktrees` or `.agentweave/tasks` held anything
at all. The observation behind it (task 6.9) is correct — a linked git worktree is held together by
two **absolute** paths, the main repo's `.git/worktrees/<name>/gitdir` and the checkout's own
`.git` file, and moving the project invalidates both. But an agent worktree is **permanent**: one
ordinary turn creates it and nothing ever removes it. So "a checkout exists" is a fact about the
project's history, not about activity, and the guard's real meaning was *a project may be moved
until it has been used, and not afterwards*.

The spec's own condition is narrower than the code's:

> **WHEN** an unavailable project's marked directory is opened at a new path **and it has no active
> run or worktree mutation** — `local-project-workspace`, "A project directory is relocated"

Existence is not activity. And the refusal never un-broke anything: by the time the operator asks,
they have already moved the directory. All the refusal preserved was a Hub pointing at a path that
is gone — and no remedy was stated, because there is no control anywhere that removes an agent
worktree.

**Fixed by repairing instead of refusing.** The gate is now active runs only. Relocation — through
both routes, `POST /relocate` and the open-at-a-new-path flow the spec actually describes — calls
`_repair_checkout_registrations`, which runs `git worktree repair` over every checkout under
`.agentweave/worktrees`, `/tasks` and `/reviews`, then prunes. Best-effort by design: a project
that is not a git repository has nothing to repair, a checkout git cannot place is logged and left,
and neither fails the relocation. Guarded on the path actually changing, so an ordinary re-open
costs no subprocesses.

**Live, on the fixed code**, against the real moved project:

```
before   git worktree list -> .../aw-f52-moved/.agentweave/worktrees/builder  [prunable]
         git -C <checkout> status -> fatal: not a git repository:
                                     C:/Users/huida/Documents/aw-f52/.git/worktrees/builder
POST /relocate .../aw-f52-moved2 -> 200, directory_state "available"
after    git worktree list -> .../aw-f52-moved2/.agentweave/worktrees/builder   (no "prunable")
         git -C <checkout> log -1 -> c8d0fb1 f52: fix is_low_stock
POST /agent/trigger builder      -> run-4e266e6f1c74, completed, exit 0
```

**Two existing tests pinned the defect and were replaced, not deleted.**
`test_copied_active_worktree_metadata_blocks_relocation` and
`test_copied_task_checkout_blocks_relocation` both asserted the refusal, and both are the
carry-forward pattern in its sharpest form: each `mkdir`s the checkout directory by hand, because
that is the state the guard reacts to — and in production the thing that creates it is *any
completed turn*. A test that has to build the blocking state itself never asks how often the
product builds it. The answer was "always, permanently, after the first turn".

---

## F96 (A) — the product names the remedy, the operator performs it, and nothing happens

**Status:** fixed (this iteration)

Sweep #2, second-order resilience. An agent whose runner binding is absent — the state a roster
entry is in before the operator picks a runner for it, and the state one PATCH away at any later
moment — is sent a message. The Hub handles that part well: it queues the input rather than
refusing it, and answers with the remedy in words.

```
PATCH /agents/swapper  {"runner_id": null}          200
POST  /agent/trigger   {"agent": "swapper", ...}    200
  {"status": "queued",
   "waiting_reason": "No runner is bound to this agent. Bind one in the Hub UI before it can run."}
```

The operator then does exactly that. Thirty seconds of polling later:

```
PATCH /agents/swapper  {"runner_id": "runner-867c59fc4a9e"}   200
  +5s   {"waiting_count": 1, "waiting_reason": "delivery failed 1 time; 2 attempts left"}
  +10s  {"waiting_count": 1, "waiting_reason": "delivery failed 1 time; 2 attempts left"}
  ...   unchanged through +30s
```

Two things are wrong there and the second is worse than the first. The message did not move. And
the status no longer mentions the runner at all — the retry countdown has taken the place of the
reason, so the surface the operator is watching now describes a *delivery problem* on an agent
whose delivery problem they have just fixed.

It was deliverable the whole time. An unrelated `PUT /projects/{id}/settings`, sent for no reason
connected to this agent, delivered it within six seconds and the turn ran:

```
PUT /settings -> 200
  +6s  {"waiting_count": 0, "running": true, "delivery_attempts": 0}
```

**Cause.** Queue delivery has no tick — `turn_scheduler`'s own comment says so. An entry is
re-attempted only when something calls `schedule_agent` or `redrain_queued_agents`, and the
redrain sites are: a run ending, `POST /projects/open`, `PUT /projects/{id}/settings`, and
`POST /projects/{id}/relocate`. Relocation is there precisely because it is the repair for
*"project workspace is unavailable"*. Binding a runner is the repair for *"no runner is bound"* —
and it was the one repair route in the product with no redrain behind it.

This is iteration 7's pattern again, one column over: **a rule applied at N call sites holds at
N-1 of them.** "The repair is a redrain site" was applied to the workspace refusal and never asked
of the binding refusal.

**Fix.** `patch_agent` calls `schedule_agent(project_id, name)` after commit, when the PATCH
actually changed the binding to a non-null runner. `schedule_agent` rather than
`redrain_queued_agents` because this repair is agent-scoped, and gated on the binding *changing*
because the Hub UI submits the whole agent form — a PATCH carrying the runner the agent already
has is the ordinary case, and must not start a turn as a side effect of a rename.

**Not** reclassified as transient. "No runner is bound" repeats identically forever until the
operator acts, which is the terminal bucket's stated criterion and the same treatment an archived
agent gets. With the repair now delivering, the countdown is what it should be: the record of an
operator who never came back.

**Tests.** `hub/tests/test_runner_binding_redrain.py`, two of them, both mutation-checked
separately — one that the rebind delivers, one that a PATCH re-stating the same runner schedules
nothing. Watched to fail as *"the rebound agent's run never settled within 10.0s: []"*.

Proved live on the fix, same experiment: the rebind delivered the message in the same instant
(`running: true` on the first poll), where before it sat queued indefinitely.

---

## F97 (B) — the reason a turn is waiting exists, is correct, and never reaches the operator

**Status:** fixed (this iteration)

Two writing agents, one task — an ordinary sequence of clicks, and the exact case design D8 exists
for. `writer` is running a turn on `task-d64523ce8ada`; the operator starts `writer2` on the same
task. The refusal is right, the classification is right, and the entry is correctly unbilled:

```
POST /agent/trigger {"agent": "writer2", "task_id": "task-d64523ce8ada"}
  200 {"status": "queued",
       "waiting_reason": "writer is already running a turn on task task-d64523ce8ada;
                          a task's checkout takes one writing turn at a time."}
```

One second later, on the surface the UI actually polls:

```
GET /queue/writer2/status
  {"waiting_count": 1, "running": false, "waiting_reason": null, "delivery_attempts": 0}
```

`1 waiting`, no explanation. Which is, verbatim, the state `get_queue_status`'s own comment says
it exists to prevent:

> a turn can be refused inside the trigger, where the reason was raised and then discarded,
> leaving the operator with "1 waiting" and no explanation to reason from

That comment is true of the two cases it was written for — a missing CLI, an unavailable workspace
— because the route re-derives those itself, read-only. Every refusal raised deeper inside
`trigger_agent_directly` is invisible to it, and a transient one has no delivery-attempt count to
fall back on either, so it reports nothing at all. The operator cannot tell a turn that is
correctly waiting its turn from one that is stuck.

**Fix — record it rather than re-derive it.** `inbound_queue_entries.waiting_reason` (migration
`0098`), written by `schedule_agent` from the refusal's own `detail` at the moment it parks the
entry, cleared in `mark_delivered` when the wait ends. `get_queue_status` reads it after its live
checks — which describe the agent *now*, and a repair since the last attempt may already have
cleared the recorded reason — and before the delivery-attempt counter, for the reason that
counter's own comment gives.

Restating each refusal's condition in the status route was the alternative and is the worse one:
two copies of every refusal, and the *next* one invisible in the same way. This is the shape
`TriggerAgentError.transient` already chose for itself — ask directly rather than derive from each
cause.

No backfill, for `0043`'s and `0096`'s reason: the column records what a delivery attempt was
refused with, and for an entry queued before the migration no such record was kept.

**Tests.** `test_the_status_route_reports_the_collision_the_trigger_refused_on` in
`hub/tests/test_task_turn_collision.py`, plus two migration tests. Both halves mutation-checked:
stop recording and the assertion fails with `assert 'collision-holder' in ((None or ''))`, which is
the live symptom exactly; stop clearing and a delivered entry still explains itself with a wait
that is over.

Proved live on the fix: the same two-agent collision, and the status route now answers with the
refusal's own sentence and `delivery_attempts: 0`.

**What drove clean in the same sweep, and is worth saying so.** Deleting an agent's worktree
directory by hand and leaving the git admin entry behind — `git worktree list` reporting it
`prunable` — is fully recovered from: the next trigger rebuilt the checkout and the turn completed
and committed. Runner and charter deletion are both correctly refused while bound, and an archived
agent cannot accumulate queue entries because `POST /agent/trigger` refuses before queueing.

---

## F98 (A) — "Full access" is the *least* permissive posture a Codex agent can be given

**Status:** fixed (this iteration)

Sweep #2, the Codex angle. Every finding in this corpus before it was found on the Claude path.

The Permissions control offers four postures, and both providers declare the same four with the
same labels on purpose — the catalog says so in as many words: *"an operator should not have to
learn two vocabularies for the same choice."* They read as an ordering, narrowest to widest:

| Label | id |
|---|---|
| Ask me | `manual` |
| Workspace only | `workspace` |
| Edit files | `acceptEdits` *(the default)* |
| Full access | `bypassPermissions` |

On the Codex path the last one was not wider than the third. It was not even equal to it. It was
`None` — and `None` is the value that means *the operator chose nothing*.

### Measured live, on one agent, on the same command, twice

`coder` (`gpt-5.4-mini`, app-server transport) in `aw-e2e2`, asked to run one shell command
writing to a path outside its worktree. Posture set to **Full access** both times, through the
two surfaces that can set it.

```
agent default = bypassPermissions            per-run override = bypassPermissions
                                             (agent default acceptEdits)
"Succeeded."                                 "Refused: writing to
C:\...\aw-e2e2\OUTSIDE_WS.txt written        C:\...\aw-e2e2\OUTSIDE_WS.txt was
                                             denied by the sandbox."
```

Same posture. Same agent. Same command. Opposite outcomes. And the surface that *failed* is the
composer's Permissions pill — the one an operator actually uses to say "just this turn, let it
off the leash".

The second run is not merely narrower than Full access should be. It is narrower than **Workspace
only**, which was measured in the same session accepting an escalated command purely because it
ran from inside the workspace. An operator moving the control one notch *wider* got a strictly
smaller grant.

### Why one worked

`_codex_posture` (`agent_trigger.py:1958`) translated the operator's posture into what the Codex
runtime understands, and it knew three of the four:

```python
if permission_mode == "manual":                  return OPERATOR_POSTURE
if permission_mode == WORKSPACE_PERMISSION_MODE: return WORKSPACE_PERMISSION_MODE
return None                                      # <- "bypassPermissions" landed here
```

Downstream, `None` is indistinguishable from "no posture chosen":

- `_thread_policy` returned `workspace-write` / `on-request` — the default pair — so Codex's own
  sandbox refused the write before any approval was raised. (Codex's sandbox *is* enforced on
  Windows; measured separately with `codex exec --sandbox read-only`, which denied the same write
  with `UnauthorizedAccessException`. The earlier probes that appeared to escape were writing into
  the system temp directory, which `workspace-write` grants by default.)
- `decide_approval` fell through to `{"decision": "accept"} if yolo else {"decision": "decline"}`,
  so any approval Codex *did* raise was declined.

`_thread_policy` had a branch for exactly this posture — `if posture == "bypassPermissions":
return "danger-full-access", "never"` — written when the postures were designed, and unreachable
from the day it was written, because the only function that could produce that string threw it
away.

What hid it for so long is the legacy `config["yolo"]` flag. `_apply_default_permission_mode`
(`agents.py`) reconciles it whenever an agent's **default** posture is set — `"yolo": posture ==
FULL_ACCESS_PERMISSION_MODE` — and `yolo` reaches `_thread_policy` by a route of its own
(`if yolo and posture is None`). So the agent-default surface worked, by accident, through the
older spelling. Nothing writes `yolo` for a per-run override, and there is no reason it should:
`yolo` is a two-valued flag and the posture has four values.

### The same hole in the transport beside it

Found by asking the carry-forward's own question — *a rule applied at N call sites holds at N-1 of
them; go count them* — rather than by driving it a second time.

`_build_codex_command` (the `codex exec` transport, selected by a runner carrying
`--no-app-server`) chooses between `--dangerously-bypass-approvals-and-sandbox` and
`--sandbox workspace-write` from `yolo` alone. The catalog's Codex `permission_mode` control
renders nothing to argv on purpose — `ApplySpec(style="none")`, because app-server carries the
posture in its thread policy instead — so on that transport too, the only thing that could ever
reach the sandbox flag was the flag one surface writes. Identical defect, identical cause, and it
would have survived a fix aimed only at where the defect was seen.

### The fix

`FULL_ACCESS_PERMISSION_MODE` moves from `api/v1/agents.py` — whose only interest in it is
reconciling `yolo` — to `model_catalog.py`, beside `WORKSPACE_PERMISSION_MODE` and the postures it
has to stay ordered against. `_codex_posture` passes it through; `_thread_policy`'s existing
branch becomes reachable; `decide_approval` accepts on the posture's own terms rather than on
`yolo`'s, for both sandbox approvals and the permissions request; and `_build_codex_command` takes
`full_access` and stops asking `yolo` alone.

`acceptEdits` deliberately still maps to `None`. It *is* the default posture, and the default pair
already produces its Codex meaning: edit freely inside the workspace, refuse an escalation out of
it. Widening it was not the defect and is not the fix.

### Verification

- `hub/tests/test_codex_posture_ordering.py`, 24 tests, written as an **ordering** rather than as
  four independent rows, because the defect was not one wrong row — it was that the widest posture
  had become narrower than the middle one while keeping the label "Full access". The thread-policy
  tests reach `_thread_policy` **through `_codex_posture`**, never by passing the constant in by
  hand: a test that called it directly with the string would have passed against the defect for
  the whole time the branch was unreachable.
- Three separate mutation checks, each watched to fail: restoring the `_codex_posture` drop (12
  failures), removing `decide_approval`'s full-access branch with the mapping left intact (6), and
  returning the exec transport to `yolo`-only (1). Three guards, three independent failures.
- Proved live end to end against a Hub restarted onto the fixed code: the per-run-override run
  that was refused now writes the file, with the agent's default still `acceptEdits` and
  `config` still `{"yolo": false}` — and a "Workspace only" override on the same command is still
  refused, so the ordering holds in both directions rather than everything having been widened.

---

## F99 (B) — the Effort control does nothing on the transport Codex agents actually use

**Status:** **fixed** — iteration 10, 2026-08-28. The open question below (does `thread/start`
*honour* `model_reasoning_effort`, or accept and ignore it?) was settled by live measurement
first; the answer is **honoured**, and the fix is the one this section already sketched.

Found by following F98's seam rather than by driving a second time. F98 was one control that failed
to cross from the operator's choice into the Codex runtime; this asks what else crosses by the same
route, and the answer is: nothing else does, because there is no route.

The catalog declares two controls for Codex. `permission_mode` (F98's) renders nothing to argv on
purpose. The other is **Effort**:

```python
ControlDescriptor(
    id="effort", label="Effort", kind="enum",
    values=_enum("low", "medium", "high", "xhigh"), default="medium",
    apply=ApplySpec(style="config", template="model_reasoning_effort={value}"),
)
```

`style="config"` means `render_control_args` turns it into `-c model_reasoning_effort=high` in the
argv `build_command` produces. That works on `codex exec`. It cannot work on `app-server`, and
`_execute_run` says so itself, in its own docstring:

> *`cmd` was still built for it by the caller, but is unused here — app-server has no argv, it
> speaks JSON-RPC.*

app-server is the **default** transport for every Codex agent (`uses_app_server` returns true
unless the runner carries `--no-app-server`), and every Codex agent an operator can create through
the Add-agent dialog sets no flags. So for the ordinary case, an operator raising Effort to `xhigh`
changes nothing at all — and unlike F98, there is not even an accidental second route: nothing
resembling `yolo` exists for this control.

`permission_mode` is the only control passed to `_execute_codex_appserver_run` explicitly, and it
was passed there *because* somebody noticed the argv did not carry it. The same noticing never
happened for `effort`.

### What is measured, and what is not

Measured:

- `model_reasoning_effort` is the correct key, it reaches the provider, and it is validated —
  `codex exec -c model_reasoning_effort=definitely-not-a-level` prints
  `reasoning effort: definitely-not-a-level` in its header and the API rejects the turn with
  *"Supported values are: 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', and 'max'."*
  (CLI 0.146.0.)
- `ThreadStartParams.config` is `{"type": ["object","null"], "additionalProperties": true}` —
  a free-form config-override map, per `codex app-server generate-json-schema --out`. It is the
  same map the Hub already uses successfully for `mcp_servers`, which is itself a `config.toml`
  key, so the config-map-equals-config.toml-overrides mapping is established by working code in
  this repository rather than assumed.
- The catalog offers Codex four effort values where the provider accepts seven. `none`, `minimal`
  and `max` are simply not offerable today. That is a smaller, separate observation and not the
  defect.

Not measured, and the reason this is filed open rather than fixed: whether `thread/start` actually
*honours* `model_reasoning_effort` inside `config`, as opposed to accepting and ignoring it. A
free-form map with `additionalProperties: true` will not reject an unknown key, so schema
acceptance proves nothing on its own. The check that would settle it is a live turn under
`app-server` with the key set, reading the effort back off the thread — and a fix built on the
untested assumption would be exactly the kind of plausible-looking repair this corpus keeps
finding.

### The fix, when it is taken

Thread the value from `control_overrides` through `_execute_run` → `_execute_codex_appserver_run`
→ `run_turn`, and merge it into the `config` dict `thread_params` already builds — which today is
constructed only `if mcp_command`, so it needs to exist whenever either input is present. Prove
the honouring first, then write the guard.

The wider lesson is the one to keep: **`_execute_run`'s docstring names the hazard exactly — "cmd
is unused here" — and the hazard it names is that every control rendered into argv silently
disappears.** One control was rescued by hand and the class was never swept. Whenever a comment
says a value is unused on a path, ask what else arrives by that value.


### The measurement, 2026-08-28 — honoured, twice over

Two probes against CLI 0.146.0, both driving the Hub's own `run_turn` (raw pipes to
`codex app-server` hung on this machine at iteration 9; the Hub's client does not, so the probe
that works is the one that goes through the code being fixed):

| Probe | `config` passed to `thread/start` | Result |
|---|---|---|
| **A** — bogus value | `{"model_reasoning_effort": "definitely-not-a-level"}` | The turn is rejected by the provider: *"Supported values are: 'none', 'minimal', 'low', 'medium', 'high', 'xhigh', and 'max'."*, `status: 400` — **byte-identical to what `codex exec -c model_reasoning_effort=…` gets for the same model** |
| **B** — control | *(no key)* | Turn completes, one `OK` |
| **C** — valid value | `{"model_reasoning_effort": "xhigh"}` | Turn completes, and the rollout's `turn_context` records `"effort": "xhigh"` |

C is the positive half and A is the negative one: a value that is refused when wrong and recorded
when right is not being ignored. `~/.codex/sessions/…/rollout-*.jsonl` — whose path `thread/started`
reports — is the read-back surface the earlier write-up said it lacked.

### What shipped

`model_catalog.render_control_config(provider, overrides)` — the sibling of `render_control_args`,
rendering the same `style="config"` declarations as a key → value map instead of `-c KEY=VALUE`
argv. It is generic: a control is still declared once, in the catalog, and neither renderer knows
what any control means. `agent_trigger` renders it next to `build_command` and passes it through
`_execute_run` → `_execute_codex_appserver_run` → `run_turn`, which merges it into `thread/start`'s
`config` alongside `mcp_servers` — that map is now built whenever *either* input exists, where
before it existed only `if mcp_command`.

Tests, each watched failing with the fix reverted:
`test_config_overrides_reach_thread_start`, `test_config_overrides_and_mcp_server_share_one_config`
(the two inputs must not evict each other), `test_a_config_style_override_reaches_the_app_server_transport`
(the wiring, through a real `POST /agent/trigger`), and five in `TestRenderControlConfig`.

The catalog still offers four of the provider's seven effort values (`none`, `minimal` and `max`
are unofferable). That remains a separate, smaller observation — and now that the control works,
it is worth something rather than moot.

---

## F100 (A) — a Codex turn that fails at the provider is recorded as a completed run with no output

**Status:** **fixed** — iteration 10, 2026-08-28. Found by the F99 probe, not by looking for it.

Probe A above was supposed to produce a loud failure. It produced this instead:

```
--- A bogus: status=completed error=None stderr='' n_events=0
```

A turn the provider rejected with a 400 came back as **completed, with no error and zero events**.
The operator's surface for that run is a run that succeeded and said nothing.

### Why

`run_turn`'s notification loop had two branches:

```python
elif method == "turn/completed":
    status = "interrupted" if interrupted else "completed"
    break
elif method == "turn/failed":
    ...
```

`turn/failed` **does not exist**. `codex app-server generate-json-schema` for CLI 0.146.0 lists
exactly three turn notifications in `ServerNotification` — `turn/started`, `turn/completed`,
`turn/moderationMetadata`. The failure branch has never been reachable on this CLI; every test that
exercised it fed the loop a notification the product cannot receive, so the suite proved a dead
path worked while the live path could not fail.

The information was there and was read past. `turn/completed` carries a `Turn`, and `Turn.status`
is a `TurnStatus`: `completed | interrupted | failed | inProgress`. Its `error` field is documented
in the schema as *"Only populated when the Turn's status is failed."* The live payload had both:

```json
{"method": "turn/completed", "params": {"turn": {"status": "failed",
  "error": {"message": "{...[invalid_enum_value]..."status": 400}", "codexErrorInfo": "other"}}}}
```

— preceded by a `thread/status/changed` to `systemError` and a separate `error` notification with
`willRetry: false`, both also ignored. **`turn/completed` means the turn ended, not that it
succeeded.**

Where the dead name came from is measurable too: `codex exec --json`, given the same bogus value,
emits `thread.started · turn.started · error · turn.failed`. `turn.failed` is **exec's** vocabulary,
and `runner_parsing.parse_codex_line` handles it correctly. The app-server branch is that name
transplanted across a transport that does not use it — the same transplant as F102's `todoList`,
which is `exec`'s `todo_list` in camelCase.

### Blast radius

Every provider-side failure on the app-server transport — the default for every Codex agent an
operator can create — reaches the operator as a silent successful run: a 400 of any kind, an
expired credential, a rate limit, a context overflow, a moderation refusal. The run finalises
`completed`, `Run.error` stays NULL, no `error` event is broadcast, the timeline shows nothing, and
any queue entry it consumed is spent. That is severity A on the plainest reading: the operator acts
on "it ran and produced nothing" — reruns it, rewrites the prompt, doubts the agent — when the
truth was a stated, actionable error the Hub already had in hand.

It also explains a shape that has been seen before and blamed elsewhere: a Codex turn that
"completed instantly with no output".

### The fix

Read `turn.status`. `failed` fails the turn, mapping `Turn.error` through the same
`map_turn_failure` the dead branch used, so the provider's own message reaches `TurnOutcome.error`
and an `error` event; `interrupted` — whether this Hub asked for it or not — reports interrupted;
anything else completes. `_turn_error_message` is shared by both carriers. The `turn/failed` branch
is kept for version drift with a comment saying it is absent from 0.146.0's schema, so it can never
again be mistaken for the live failure path.

Tests, both watched failing with the fix reverted:
`test_turn_completed_with_failed_status_is_a_failure` (payload copied from the live capture) and
`test_turn_completed_with_interrupted_status_is_not_a_completion`.

### The lesson

**A test can pin a branch the product cannot reach.** `test_turn_failed_notification_is_reported`
passed for as long as it existed, asserting the Hub reports a failed turn, and the Hub could not
report a failed turn. Nothing in the suite could have caught it: the fixture supplied the
impossible input.

What caught it was a probe with a *known* expected outcome — I set a value the provider must
reject, and the absence of the rejection was the finding. The general form: **when you already know
what a probe must produce, its silence is evidence.** That is the second time in two iterations
that a measurement chosen to be able to contradict me did the work, and neither came from reading
harder. This one came free, riding on a probe aimed at something else entirely.


---

## F101 (A) — the Hub's own MCP server can fail to start and the turn says nothing

**Status:** **fixed** — iteration 10, 2026-08-28. Third finding of the iteration, and the second
found by a probe aimed at something else: F100 taught that `run_turn`'s notification loop drops
statuses it does not read, so the next question was *what else does it drop*.

The loop ended with this comment:

> *Anything else (`mcpServer/startupStatus/updated`, `thread/status/changed`,
> `account/rateLimits/updated`, `item/agentMessage/delta`, `remoteControl/status/changed`,
> `serverRequest/resolved`) carries no timeline-relevant content for this pass.*

`mcpServer/startupStatus/updated` carries `McpServerStartupState` — `starting | ready | failed |
cancelled` — plus `error` and `failureReason`. One of those four states is the most
timeline-relevant thing that can happen to a turn.

### Measured live, 2026-08-28

A turn driven through the Hub's own `run_turn` with `mcp_command` pointed at a script that does
not exist, asking the agent to use an AgentWeave tool:

```
{"name": "agentweave", "status": "starting", ...}
{"name": "agentweave", "status": "cancelled", ...}
{"name": "agentweave", "status": "failed",
 "error": "MCP client for `agentweave` failed to start: MCP startup failed: handshaking with
           MCP server failed: connection closed: initialize response"}
```

```
status: completed   error: None
agent's final word: "Unavailable"
```

The Hub's own collaboration server failed to start, said exactly why, and **the run finalised
`completed` with `Run.error` NULL and no error event anywhere.** The agent held no AgentWeave tools
at all for that turn: it could not send a message, record evidence, update a task, or call
`ask_user`. To the operator it is a turn that ran fine and simply did not record anything —
indistinguishable from an agent that chose not to.

### Why it matters more than the probe's artificial cause

The path is `[sys.executable, <hub>/mcp_server.py]`, so a missing file is not the realistic
trigger. These are: `mcp_server.py` raising on import (it may import **only** stdlib + fastmcp —
a rule that exists precisely because that import is fragile), fastmcp absent from the interpreter
the Hub happens to be running under, a handshake that times out under load, or the
`reauthenticationRequired` failure reason the schema declares. Every one of them produces a
turn that looks successful and quietly cannot touch any collaboration state.

It is also a ready explanation for a whole class of past confusion — *"the agent completed the turn
but nothing was recorded"* — which has been blamed on prompts, on charters, and on the model.

### The fix

`status == "failed"` maps to an error event on the timeline, naming the server and the provider's
own message. The Hub's own server says what it costs — *"no messages, evidence, task updates or
questions"* — because that is the operator's actual consequence; any other server (`codex_apps`,
or anything in the operator's Codex config) is reported plainly, since it costs this Hub nothing.

Two deliberate limits, both tested:

- **The turn is not failed.** A model with no tools may still be useful, and that judgement is the
  operator's — but they can only make it if they are told.
- **Reported once per server per turn.** Measured live: the app-server repeats every startup
  transition, so an undeduplicated report tells the operator the same thing twice. `cancelled` is
  not reported at all — a failing server passes through it on the way to `failed`.

Tests: four in `TestRunTurnMcpStartupFailure`, each watched failing with its guard broken; and the
live probe re-driven after the fix, which now emits exactly one error event carrying the provider's
own sentence.

### The lesson, which is the same one twice

**A comment enumerating what a loop ignores is a list of unread evidence, not a proof of
irrelevance.** F100 was a status field read past inside a notification the loop handled; F101 is a
whole notification the loop declined to handle, dismissed in prose. In both cases the product had
the operator's answer in hand and threw it away, and in both cases the finding took one probe with
a known expected outcome.

Iteration 9 said *"the code keeps naming its own hazard in a comment and then not sweeping the
class."* That is now three consecutive iterations where the comment was right there. Sweep the
class, always: **when a comment says a thing is ignored, enumerate what arrives that way.**


---

## F102 (B) — the agent's plan is invisible on the transport every Codex agent uses

**Status:** **fixed** — iteration 10, 2026-08-28. Fourth of the iteration, and found by sweeping
F100's class deliberately rather than by another accident: *what else does this loop pin a name
for that the CLI does not send?*

`map_item_to_events` ended with:

```python
if item_type in ("todoList", "planUpdate"):
    ...
    return [status_event("plan", summary=summary)]
```

`ThreadItem`'s type union in CLI 0.146.0 is `agentMessage · collabAgentToolCall ·
commandExecution · contextCompaction · dynamicToolCall · enteredReviewMode · exitedReviewMode ·
fileChange · hookPrompt · imageGeneration · imageView · mcpToolCall · plan · reasoning · sleep ·
subAgentActivity · userMessage · webSearch`. Neither `todoList` nor `planUpdate` is in it, and
never has been — they are camelCase guesses at `exec`'s `todo_list` / `plan_update`, which are
that transport's item names.

### Measured live, 2026-08-28

A codex turn asked to record a plan:

```
turn/plan/updated {"plan": [{"step": "Lint the Python project…", "status": "pending"},
                            {"step": "Run the test suite…", "status": "pending"},
                            {"step": "Update documentation…", "status": "pending"}]}
event kinds emitted by the Hub: ['text', 'text']
```

The plan arrives as **its own notification**, not as an item — so the item branch could not have
matched even had it been spelled right. Every plan a Codex agent makes was dropped, on the default
transport, while the code meant to render it sat there looking present. `exec` shows plans; the
transport an operator actually gets does not. After the fix, the same probe: `['status', 'text']`.

### The fix

`turn/plan/updated` → `map_plan_update` → the same `status_event("plan", summary="step; step")`
`exec` produces, because one timeline shape across both transports is task 2.5's stated goal. Step
statuses (`pending | inProgress | completed`) are deliberately not rendered, for that parity —
which makes a re-send that only moves a status carry nothing new, so an unchanged summary is not
repeated at the operator. The dead item branch is deleted, and a comment where it stood says where
plans actually come from, so it cannot be re-added as a guess.

Three tests, each watched failing with its guard broken.

### The lesson

Third dead branch in one iteration (`turn/failed`, `todoList`, and the `mcpServer` notification
dismissed in prose), all in the same 200 lines. **Code written against a protocol needs the
protocol checked back, not remembered** — `codex app-server generate-json-schema` takes seconds and
would have caught all three, at any point, for free. It is now the first thing to reach for when
touching this file.

## F103 (B) — every context reading in the timeline rendered as the words `context_warning`

**Status:** fixed f1d7a85

Observed twice, live, in two separate drive sessions before it was filed — and skipped past both
times as cosmetic, which it is not: `context_warning` is the row an operator reads to decide
whether an agent is about to run out of room.

`summaryForEvent`'s default branch picks the first of `error`/`message`/`summary`/`title` a payload
carries, and returns the event *type* when it has none. A context reading carries `agent`,
`percent`, `context_tokens`, `limit_tokens`, `model`, `session_id`, `conversation_id` and
`observed_at` — none of the four. So the Activity log and the Logs view both printed the literal
string `context_warning`, next to a label already reading "context_warning", with the measurement
nowhere on screen. The value it exists to show was the one thing it did not show.

This is the fourth event family to land here (`permission_denied` and the three `queue_*` kinds got
their cases the same way), and the default branch's four-field guess is why: it is a heuristic over
payload shapes nobody enumerated, so a new event kind is invisible by default and visible only if
someone notices. Every kind that has ever needed a case needed it because its payload names its
detail something else.

### The fix

A `context_warning` case that reads what the reading actually holds:

- `coder is at 62.5% of its context window, 125000 of 200000 tokens (gpt-5.4-mini)`
- `builder has used 48123 context tokens (claude-x)` — no percentage, because `resolve_usage_limit`
  invents none for a model the catalog does not declare, and the raw count is still worth reading
- `builder: a context reading with no measurement` — names the agent rather than the event

Three tests, all three watched failing first, each returning the bare string `context_warning`.

## F104 (—) — ThreadItem's eleven unhandled variants: swept live, none of them occur

**Status:** not a defect (measured 2026-08-28, CLI 0.146.0)

Filed as a **negative** result so nobody spends another iteration on it. `map_item_to_events`
handles seven of `ThreadItem`'s eighteen variants and explicitly suppresses an eighth
(`userMessage`), leaving ten that render nothing: `hookPrompt`, `plan`, `dynamicToolCall`,
`collabAgentToolCall`, `subAgentActivity`, `imageView`, `sleep`, `imageGeneration`,
`enteredReviewMode`, `exitedReviewMode`, `contextCompaction`. On paper that is ten ways for an
agent to do work the operator cannot see — the same shape as F100/F101/F102, in the same file, and
the obvious next place to look after them.

It is empty on evidence. One live turn through the Hub's own `run_turn`
(`.claude/autonomous/scratch/probe_items.py`, tracing every notification rather than a chosen few)
was asked to record a plan, write a file and run a command — three of the likeliest triggers — and
delivered exactly `userMessage`, `reasoning`, `agentMessage`, `fileChange`, `commandExecution`.
**Zero unhandled item types.** `plan` exists in the union with a `text` field, and still did not
arrive as an item: the plan came as `turn/plan/updated`, confirming F102's finding rather than
qualifying it.

That does not prove the ten are unreachable — a review turn should produce
`enteredReviewMode`/`exitedReviewMode`, and a long enough session `contextCompaction`. It proves
the ranking was wrong: the schema diff said "ten silent branches" and the product said "none of
these happen here". A gap between a protocol's surface and a product's usage is not a defect, and
counting union members is not measuring.

**The review-turn caveat above is now closed, and the answer is no (measured 2026-08-28,
iteration 13).** A real codex review turn was driven end to end — `swapper` on `codex`/`gpt-5.4-mini`
in `aw-e2e1`, `POST /agent/trigger` with `review_task_id=task-a0409448ee8e` (the only task carrying
evidence that names a commit), `run-eb29661d2cc7`, ~90s, `exit_code: 0`. Its complete event trace is
`run_triggered`, `run_started`, `queue_entry_delivered`, eleven `context_warning`, two
`permission_denied`, `run_completed`. **`enteredReviewMode` and `exitedReviewMode` did not arrive,
and `map_item_to_events` needs no branch for them.**

The reason is worth stating because it retires the expectation rather than merely one test of it:
**AgentWeave's review turn is an ordinary turn given a review checkout and a reviewing prompt — it is
not codex's built-in `/review` mode**, which is what emits those two. Nothing in the product's review
path can produce them, so this is not "not observed yet"; it is not reachable from here.

That leaves `contextCompaction` as the sole item in the ten with an untested route to arriving, and
it needs a session long enough to compact.

### What the sweep did find

The comment at the end of `run_turn`'s loop listing the notifications it ignores was written from
memory and was missing `turn/diff/updated` entirely. It is now the measured list, with the
measurement dated. Two of its entries were checked rather than assumed: neither
`item/agentMessage/delta` nor `item/commandExecution/outputDelta` is a transport-parity gap,
because `runner_parsing` does not stream partial text on `exec` either — both transports show a
message when it completes.

### The lesson

Iteration 10's rule was *check the protocol back, do not remember it*. This is its other half: a
protocol you have checked back tells you what **can** arrive, never what **does**. The generated
schema is the cheap way to build a candidate list; only driving the product ranks it. The one probe
that cost two minutes here would have saved eleven speculative findings.

## F105 (B) — the failure family: ten persisted event kinds render as their own bare name

**Status:** fixed 5d9638c

The sixth family to need a hand-written case in `summaryForEvent`, and the first found by sweeping
the emitters instead of by someone happening to see a row. `permission_denied`, the three `queue_*`
kinds and `context_warning` (F103) were each discovered live, one at a time, over four sessions.
That method was the defect underneath the defect, so this pass enumerated the Hub's own
`persist_event` call sites and asked which of them the default branch can render at all.

### How the list was narrowed, because 53 unhandled kinds is not 53 defects

Two cuts, both taken before anything was filed:

1. **Does it reach a timeline?** `summaryForEvent` is called from `EventRow.tsx` and `LogLine.tsx`,
   both of which read `event_logs`. A kind only ever broadcast over SSE reaches neither. So the
   candidate set is the `persist_event`/`record_event` call sites — 54 distinct `event_type`
   literals — not the wider set of things the Hub emits.
2. **Does the default branch already render it?** It picks the first of
   `error`/`message`/`summary`/`title` the payload carries. `conversation_binding_conflict` names
   its detail `error` and renders correctly today; it is deliberately **not** fixed here, and a
   test asserts it still falls through, so a later sweep does not "fix" it and count that.

What survives both cuts is a persisted kind whose payload names its detail something else — which
is precisely how each of the five earlier families earned its case. Ten of them, and they are not a
random ten: they are almost exactly the `severity="warn"`/`"error"` rows.

| Kind | Emitter | Detail it carries | Rendered as |
|---|---|---|---|
| `job_run_failed` | `scheduler.py:2487`, `api/v1/jobs.py:84` | `error_summary`, `job_name` | `job_run_failed` |
| `job_run_skipped` | `scheduler.py:2106/2141/2290` | `reason` | `job_run_skipped` |
| `agent_action_rejected` | `api/v1/messages.py` ×4 | `endpoint`, `reason`, `recipient` | `agent_action_rejected` |
| `turn_produced_nothing` | `run_divergence.py:652` | `spec_document`, `run_exit_status` | `turn_produced_nothing` |
| `review_unstaffed` | `scheduler.py:1679` | `task_id`, `reason` | `review_unstaffed` |
| `loop_stopped` | `scheduler.py:2160` | `reason` | `loop_stopped` |
| `loop_queue_exhausted` | `scheduler.py:2181` | `loop_id` | `loop_queue_exhausted` |
| `run_interrupted` | `run_reconciliation.py:109` | `returned_entry_ids`, `abandoned_entry_ids` | `run_interrupted` |
| `queue_chain_suspended` | `api/v1/messages.py:295` | `hop_depth`, `hop_budget` | `queue_chain_suspended` |
| `task_worktree_release_failed` | `task_transition_service.py:494` | `reason` | `task_worktree_release_failed` |

`job_run_failed` is the one that costs most. It is written at `severity="error"`, so it is the red
row an operator scans for, and it carries `error_summary` — a field whose entire purpose is to say
why — one name away from being read. The operator saw a red row saying `job_run_failed` and had to
go to the job's run history to learn anything at all. `run_interrupted` is the same shape for a
crash: `abandoned_entry_ids` is the list of messages nothing will ever pick up again, and its
length was not on screen.

`review_unstaffed`'s own docstring says it exists so "an operator watching the app should learn this
without going to look for it". It rendered as the word `review_unstaffed`.

### The fix

Ten cases, each reading the field its emitter actually sets — verified in the emitter, not inferred:

- `"nightly review" failed for reviewer: runner claude exited 1`
- `POST /messages refused: unknown_recipient (nobody)`
- `coder ended (completed) without changing spec/changes/x.md` — deliberately not worded like
  `run_diverged`, which is about a task nobody moved rather than a document nobody changed
- `no agent could review task-7: no eligible reviewer`
- `coder's run was interrupted — 1 message requeued, 2 dropped`
- `reviewer: chain suspended at hop 6 of a 5-hop budget`

Thirteen tests. Twelve were watched failing first, each returning the bare event name; the
thirteenth is the `conversation_binding_conflict` control, which passed before and after.

### The design question this raises, for the operator

Six families have now needed the same fix for the same reason, and the sixth was found only because
someone went looking on purpose. The default branch is a heuristic over payload shapes nobody
enumerated: a new event kind is invisible by default and visible only if a human notices. The
alternative is an enumeration — a declared summary per persisted `event_type`, with a test that
fails when an emitter introduces a kind the map does not know. That is a real cost (every new event
kind acquires a required second edit) and it is the operator's call, so it is recorded in
`decisions_for_user` rather than built. What is not in doubt is that finding these by eye has now
failed six times.

### What was NOT filed

Kinds that survive cut 1 but carry no operator-facing detail at all — `agent_created`,
`job_created`, `project_adopted`, `queue_entry_queued` (12 sites) and friends — render as their own
name too, and for those that is nearly the whole content. They are noise, not a defect, and adding
ten more cases to say `agent_created` in different words would be worse than the default. The cut
is between *a payload whose detail is unread* and *a payload with no detail*.

## F106 (—) — `ask_user` on Codex: drives clean end to end, blocking and resumption both real

**Status:** not a defect (driven live 2026-08-28 07:42–07:43, CLI 0.146.0, `gpt-5.4-mini`)

Filed as a **negative**, because `ask_user` on the Codex transport had been carried as "highest
value untouched" for four consecutive iterations and would otherwise be re-driven a fifth time.
Every previous `ask_user` observation in this corpus was on Claude, whose `--permission-prompt-tool`
and pty transport share nothing with the path Codex takes: Codex runs through
`codex_appserver.run_turn` over a hidden pipe, so the tool call, the block, and the resumption are
all a different mechanism reaching the same table. That the Claude path works implied nothing about
this one.

It works, and the evidence is a per-second trace rather than an inference. Agent `swapper` in
`aw-e2e1` (`proj-46b602c1f3cb`), bound to `runner-ea0b631f27d6` (`codex` / `gpt-5.4-mini`), was
triggered with a prompt naming the tool. `agent_outputs` for `run-321da508636a`, in sequence:

| seq | at (local) | kind | content |
|---|---|---|---|
| 2 | 07:43:06 | `tool_use` | `Called agentweave.ask_user`, `category: mcp`, one question with both options |
| — | 07:43:06 | — | `q-984ce6607b78` appears unanswered, `blocking: true`, `batch_size: 1` |
| — | 07:43:17 | — | operator answers `blue` via `PATCH /questions/{id}` |
| 3 | 07:43:18 | `tool_result` | `agentweave.ask_user completed`, payload carries `success: true` and the question id |
| 4 | 07:43:19 | `text` | `blue` |

`runs.status = completed`, `exit_code = 0`, `ended_at` 07:43:19 — **two seconds after the answer**,
and twelve seconds after the question was raised. So all four properties that matter hold: the tool
call reaches the Hub from the pipe transport, the run genuinely blocks rather than proceeding on a
guess, the answer unblocks it within a second, and the answer's *content* reaches the model, which
is the part a mere status transition would not prove — the agent replied with the word the operator
chose and not the other option.

**The mechanism that makes this stay closed:** `ask_user` is an MCP tool, and `mcp_server.py` is the
same standalone process for both runners — the Codex-specific surface ends at how the tool call is
*transported*, and `codex_appserver` already carries `tool_use`/`tool_result` pairs for every MCP
call (F102's sweep established that). There is no Codex-side branch in the question path to be
wrong. Re-drive this only if the transport itself changes.

### One trap, recorded but not filed

`GET /projects/{id}/questions?status=pending` returns **every** question, answered ones included —
the filter parameter is `answered` (`questions.py:233`), and FastAPI silently discards an
unrecognised query parameter rather than refusing it. This cost one wrong reading here (an answered
question from a different agent looked like the pending one). It is stock FastAPI behaviour and the
UI passes the right name, so it is not filed as a defect; it belongs with the API-shape traps in
`method_reminders`. Note also that the answer route is `PATCH /questions/{id}` — `POST
/questions/{id}/answer` is a 405, and only `/decline` is a POST sub-route.

## F107 (B) — the Codex file-change approval card names a *category*, never the action: the operator approves "a file change" without seeing which file

**Status:** fixed `ddb965a` (found live 2026-08-28 07:52–07:54, fixed and re-driven 08:12–08:14,
CLI 0.146.0, `gpt-5.4-mini`, agent `swapper` in `proj-46b602c1f3cb`). The section below is kept as
written; two of its claims are wrong and are corrected at the end rather than edited away.

The "Ask me" posture **works on Codex** — that half is a negative, and it is traced below. The
defect is what the card the operator answers actually contains.

### The posture itself: driven end to end, and it holds

`POST /projects/{id}/agent/trigger` with `overrides: {"permission_mode": "manual"}`, prompt asking
for a file to be created:

| at (UTC) | what |
|---|---|
| 06:52:59 | run `run-5a502a77d545` starts |
| 06:53:14 | `perm-d053068ab1de` appears, `status: pending` — the run is blocked, 15s in |
| 06:54:09 | operator answers `POST /permission-requests/perm-d053068ab1de/decide {"allow": true}` → `status: allowed`, `decided_by: operator` |
| 06:54:14 | run `completed`, `exit_code 0`, five seconds after the decision |

And the content proof, which a status transition alone would not give:
`.agentweave/worktrees/swapper/ask-me-probe.txt` exists and contains `PROBE`. The approval did not
merely unblock the run — the **approved action executed**. `manual` maps through `_codex_posture`
to `OPERATOR_POSTURE`, `decide_approval` raises the request, and the operator's answer reaches the
thread. Claude's result implied nothing here (`--permission-prompt-tool` vs
`codex_appserver.decide_approval` are genuinely different mechanisms), so this needed the drive it
got.

### The defect

The card carries **no description of the action**:

```
{"id": "perm-d053068ab1de", "agent": "swapper", "run_id": "run-5a502a77d545",
 "tool_name": "a file change", "tool_use_id": "",
 "tool_input": {"grantRoot": null, "reason": null}, "status": "pending"}
```

`tool_name` is not a tool name. It is one of exactly two fixed strings from
`_CODEX_APPROVAL_LABELS` (`agent_trigger.py:1969`), keyed on the **JSON-RPC method name alone**:

```python
_CODEX_APPROVAL_LABELS = {
    "item/commandExecution/requestApproval": "a command",
    "item/fileChange/requestApproval": "a file change",
}
```

The request's `params` — which is where Codex puts the argv for a command and the path/diff for a
file change — are never carried onto the `PermissionRequest`. `tool_input` holds only
`grantRoot` and `reason`, both `null` here. So the operator's entire view of a command approval is
the string **"a command"**: `ls` and `rm -rf ~` are the same card, and no amount of care on the
operator's part can tell them apart.

That is worse than the equivalent on Claude, where `tool_name` is the real tool and `tool_input`
the real arguments — so this is a Codex-side loss, not a product-wide limitation. And it defeats the
posture's own purpose: `manual` exists so a human decides, and a decision made without the action
in front of you is not a decision. The comment above the map ("the raw method names are protocol,
not something to put in front of a person deciding in seconds") is right about the *label* and
silently drops the payload the label was supposed to summarise.

**Severity B rather than A** only because the sandbox still bounds what an approved Codex action
can reach (F98's mapping work) — the blast radius of a wrongly-approved card is the workspace, not
the machine. Raise it to A if `grantRoot` escalations ever route through the same card, since that
is precisely the request whose *scope* the operator cannot currently see.

**The fix is narrow:** carry the approval request's `params` onto `PermissionRequest.tool_input`
where `decide_approval` builds the row, and keep `_CODEX_APPROVAL_LABELS` as the human summary line
above it. Not attempted here — the run's `stop_at` is 08:00 and this was found at 07:55.

### Fixed 2026-08-28, `ddb965a` — and two of the claims above are wrong

Fixed, but not by the fix the section proposed, and the section overstates the defect in two
places. Both corrections were forced by reading the protocol rather than the transcript, so they
are recorded here rather than quietly not-done.

**Correction 1 — command approvals were never affected.** The headline sentence ("`ls` and
`rm -rf ~` are the same card") is false. `CommandExecutionRequestApprovalParams` carries `command`
and `cwd`; `approval_subject` already captured both; and `PermissionRequestCard.describe()` already
rendered them. The drive that produced this finding raised a **file change**, and the section
generalised from it to a method it never exercised. Re-driven live today at 08:12 with the same
agent and posture: `perm-185f063ad551` arrived as `"tool_name": "a command"` with the entire
PowerShell invocation and its cwd in `tool_input`. The Codex-side loss was real but narrower than
written.

**Correction 2 — the proposed fix would not have worked.** "Carry the approval request's `params`
onto `tool_input`" is exactly what `approval_subject` already does, and it is not enough, because
the paths are **not in the params**. Verified against `codex app-server generate-json-schema` at
CLI 0.146.0: `FileChangeRequestApprovalParams` has exactly `itemId`, `startedAtMs`, `threadId`,
`turnId`, `grantRoot` and `reason`. Copying the whole params map would have added three protocol
identifiers to the card and still left the operator without a filename — a fix that passes its
test and cannot do the thing, which is this repository's dominant failure mode and would have been
another instance of it.

**What the paths are actually in, and why this is fixable at all.** The `fileChange`
*item* — `FileChangeThreadItem.changes[].path` — and the approval names that item by `itemId`.
The item arrives **first**: on the 07:52 drive the `tool_use` mapped from `item/started` was
persisted at `06:53:14.339` and the permission request created at `06:53:14.352`, thirteen
milliseconds later. Measured from the drive Hub's own database, not assumed from the protocol
being sequential. So `run_turn` now keeps this turn's items by id and `approval_subject` resolves
`itemId` back to the item it names.

Paths only, not the diffs the item also carries — the card is one line read under a run's timeout,
and a patch body pasted into it buries the filenames it exists to show; the diff is already in the
timeline's `tool_use` for the same item. Where nothing resolves, `paths` is **absent** rather than
empty, so the card falls through to `grantRoot`/`reason` exactly as before instead of claiming the
patch touches no files. The refusal record (`_on_refusal`) had the same blind spot and now prefers
`paths` over the coarser `grantRoot`.

**Considered and deliberately not done: deciding the "Workspace only" posture per-path.**
`decide_approval` refuses a file change by `_within(grantRoot, workspace)`, and `grantRoot` is
usually null, so that posture declines every file-change approval it sees. The newly-available
paths would let it decide on the real target instead — and that is a *loosening* of a boundary,
not a display repair. It is also probably not a defect: that posture starts
`workspace-write`/`on-request`, so an in-workspace write raises no approval at all, and one that
does raise is an escalation whose scope is genuinely unstated — "an unknown boundary is not an
open one" is the right answer there. Recorded so the next session does not redo this analysis;
if the operator wants it changed it is a decision, not a fix.

**Live proof, 2026-08-28 08:12–08:14**, trial Hub on 8011 restarted from source on the fixed code
and confirmed by its **project list**, not `/health`. The first trigger produced a *command*
approval (correction 1's evidence); denying it made the agent give up rather than fall back, so a
second trigger forbade the shell explicitly. That raised `perm-c2dbaab3b89e`:

```
{"grantRoot": null, "reason": null,
 "paths": ["C:\\Users\\huida\\Documents\\aw-e2e1\\.agentweave\\worktrees\\swapper\\f107-probe.txt"]}
```

— where last night's `perm-d053068ab1de` had the first two keys and nothing else. Allowed at
08:14; the run completed `exit_code 0`; and **`f107-probe.txt` exists containing
`CARDNAMESTHEFILE`**. That last clause is the load-bearing one, per iteration 14's rule: the card
named a file, and the file the card named is the one that appeared.

**Mutation-checked, six, each caught by the test that names it:** dropping the item recording
(4 of 5 wiring tests fail); resolving by recency instead of by id (only the multi-item test fails,
which is what that test is for); emitting `paths` when empty; carrying the diffs into the card;
removing the UI branch (4 card tests); and letting an empty list bury the `grantRoot` fallback.

**State left behind:** in `aw-e2e1`, runs `run-08961a9a5b8f` (denied, gave up) and
`run-91ce8b8961e7` (allowed, completed), conversations `conv-077915d9ea0e` and `conv-4b9c19ba8322`,
permission requests `perm-185f063ad551` (denied) and `perm-c2dbaab3b89e` (allowed), and
`f107-probe.txt` in swapper's worktree. No job or loop was touched, so none was left enabled. The
Hub on 8011 is left running on this branch's code; 8000 and 8010 were never contacted.

---

## F108 (B) — a permanently refused request answers `200 {"success": true}`

**Status:** **closed as a class** (2026-08-28), and **the class was not the one described below.**
See *What the class actually turned out to be* at the end of this section before trusting the
paragraph that opens it.

Found by driving F76's own fix, and it is the reason phase 4 exists. Every dispatch-time guard
behaved exactly as designed, the task was left untouched every time — and the operator could not
tell a refusal from a success:

```
POST /agent/trigger {"agent": "builder", "review_task_id": "task-c351c35eb718"}
  -> 200 {"success": true, "status": "queued",
          "waiting_reason": "Cannot move task ... to 'under_review': it is still assigned to
                             'builder', the agent recorded as completing it, ..."}
```

The refusal's own sentence, correct and complete, delivered in a field named for *waiting*, under a
flag saying the opposite. `turn_scheduler` catches `TriggerAgentError` and records it as the queue
entry's `waiting_reason` (deliberately — it is what keeps `GET /queue/{agent}/status` able to
explain itself), so a request that can never succeed presents as one that is merely queued. It then
retries until the abandonment counter gives up. **Two entries were left stranded in `aw-e2e1` by the
drive that found this**, which is what made it visible at all.

Fixed for this route by asking the same three questions before anything is queued, via
`review_dispatch_refusal`, shared with the dispatch so the two cannot drift. Duplicated rather than
moved, because the flow path never passes through the route — and this is the shape the route
already used for `commit_for_task_review`, which is likewise checked in both places.

**Open as a class**, and deliberately not fixed here: every *other* refusal on that path still
answers the same way — an archived agent, a task that does not exist, an unimplemented runner, a
`work_dir` the project does not contain. Making `turn_scheduler` propagate non-transient refusals
would fix all of them in one edit, and would change the behaviour of every one of those paths, none
of which this change has driven. That is its own change.

**Three rounds of review did not find this, and the first drive did.** The rounds were reading code;
the drive was the first time the change was asked a question by an operator. Nothing in three passes
thought to ask what the HTTP route *returns* when the function it calls raises.

### What the class actually turned out to be

Closed by `2026-08-28-a-refused-request-says-so`, and the change's round 2 found that **the four
examples above are not the class.** Each was checked against the route rather than taken on trust:

| This section's example | Where it actually lands |
|---|---|
| an archived agent | already **409 pre-queue**, `agent_trigger.py:1108` |
| a task that does not exist | already **409 pre-queue**, `:1173` and `:1199` |
| a `work_dir` the project does not contain | already **400 pre-queue**, `:1134` |
| an unimplemented runner | **unreachable** — `Runner.cli` is constrained to `claude`/`codex`, and the test that used to reach the 501 was deleted with a note saying so |

The observation in this finding is correct and was reproduced. The *class* it inferred was written
without checking the route's own guard list, and the change that fixed it would have shipped with
none of its named cases able to fire. Recorded here because the next reader of this finding meets
this paragraph, not the change's design document.

**What is really reachable**, and it is a better reason than the one given here:

1. Conditions with no pre-queue mirror at all — a name that is on no roster (`:452`), `work_dir`
   combined with a review (`:591`), a turn batching two review targets or mixing kinds
   (`:337`/`:351`).
2. **Every hoisted guard is time-of-check/time-of-use.** The pre-queue guards run when the request
   arrives; the entry is delivered when the agent is next idle, which the queue makes arbitrarily
   later. Hoisting more guards can never close that, because the gap is time, not coverage. That is
   the durable justification for the fix.

The fix also had to be narrower than "propagate non-transient refusals", the mechanism this
section proposes. Non-transient covers refusals about the **environment** — no runner bound, a CLI
missing from PATH — which the product deliberately queues so that performing the repair delivers
them (**F96**). Refusing those, and withdrawing their entries, would have deleted F96's fix. The
gate is a new explicit *request-level* classification instead.

**Driven live after the fix:** `POST /agent/trigger` for a mistyped agent answers `409` with the
refusal's own sentence and `GET /queue/<agent>/status` reports `waiting_count: 0`; an agent with no
runner bound still answers `200 … queued` with its entry intact.

**Filed out of this change, not fixed by it:** `terminal_failure`'s dishonest defaults (six early
returns claim `True` without meaning it, and `scheduler.py`'s two flow consumers gate on that flag),
and the delivery-attempt accounting that is now **F114**.

---

## F109 (B) — the hub suite runs every session on one database connection, and the retry chain stalls because of it

**Status:** **the mechanism was already known — this finding rediscovered it.** Filed 2026-08-28
while implementing F108, upgraded the same night, and then **corrected**: see *This was not news*
immediately below before reading the rest. What is genuinely new is the link to the flaky test, a
cheap reproduction, three measured fixes, and a second affected test.

**The fix is declined, 2026-08-29 — the operator will not pay 4× suite runtime.** The file-backed
fixture works (12/12 clean against ~1-in-6) and costs roughly four times the suite's runtime on
every local run and every CI job. The suite is *already* too long at ~23 minutes, so quadrupling it
is the wrong trade for a 1-in-6 flake in three named tests whose cause is documented at the line and
whose production path is proven unaffected. CI was green on all nine jobs at `c994af5` the same day.

**Do not re-propose the file-backed fixture.** What is open instead is the broader question the
decision surfaced — *the hub suite takes too long* — which is its own investigation and not this
finding. Revisit F109 only in that context, or if the flake rate rises.

### This was not news, and the finding should have checked

`test_agent_trigger_overrides.py:259` carries an `xfail` whose reason describes this mechanism in
more detail than the sections below, and with better numbers:

> `sqlite+aiosqlite:///:memory:` resolves to a StaticPool: one DBAPI connection shared by every
> session in the process. SQLAlchemy tracks transaction state per Session, SQLite per connection, so
> any session closing concurrently rolls back the shared transaction and discards another session's
> pending UPDATE while its `commit()` still returns cleanly. **Measured in isolation at 105/200
> commits lost with a concurrent poller against 0/200 without**, and observed on CI (`3c1f33a`,
> 2026-08-17): a ROLLBACK from another task landed 2.5 ms before `_execute_run`'s finalize COMMIT,
> which then committed nothing. Production is unaffected — a file-backed `DATABASE_URL` gets
> `AsyncAdaptedQueuePool`, one connection per session. **Un-xfail once the fixture gives each
> session its own connection**; the assertions below are correct as written and this test has never
> failed for a product reason.

That is the whole of this finding's mechanism, written down eleven days earlier by whoever hit it
first, and it even answers the question this finding recorded as unproven — whether production is
safe. The e2e skill's own rule covers this exactly: *"you may be finding confirmation rather than
news"*, and it names checking the specs, the archived changes and the roadmap. **A grep for
`StaticPool` would have found it in one command, and was not run.**

Kept rather than deleted, because the parts below are still additions:

- the **link to the flake** — nobody had connected that known fixture defect to
  `test_spawn_failure_marks_run_failed`, which had been carried as "unexplained" across two handoffs;
- a **five-second reproduction**, against a full-suite run that surfaced it once in two hours;
- **three measured fix candidates**, which turn "un-xfail once the fixture gives each session its
  own connection" from an instruction into a costed decision;
- a **second affected test**, found by sweeping (below).

Corrected here rather than quietly, because a finding that claims to have discovered what the
codebase already knew misleads the next reader about where the knowledge lives.

### What happens

`test_agent_trigger.py::test_spawn_failure_marks_run_failed` fails intermittently on
`assert entries[0].delivery_attempts == DELIVERY_ATTEMPT_LIMIT` with `2 == 3`. Handoff 0096 recorded
it as needing full-suite state and not reproducing in isolation. It does reproduce in isolation —
about **one attempt in seven** — when the same scenario is run 40 times in one parametrized test.

The state it stalls in is the alarming part, and it is the same shape as an outage
`_execute_run`'s own comment says was worth a `CancelledError` handler to prevent:

| | |
|---|---|
| the `Run` row | `status='running'`, `ended_at=NULL`, `error=NULL` — **forever** |
| the queue entry | `state='queued'`, `delivery_attempts=2` — never retried, never abandoned |
| every later `schedule_agent` for that agent | `"agent is already running"` |

An agent in that state accepts input and never runs again, with nothing anywhere a human would see.

### The mechanism, as far as it was measured

Traced with a `before_update` mapper listener on `Run`, a spy on `schedule_agent` recording the
running-run set and its caller, and two probes inside `_execute_run`'s spawn-failure branch:

```
execute-begin   R2
failbranch      R2 run_found=True status=running      <- R2 writes failed, commits
schedule->STARTED R2   running=[]                     <- the failed write is visible here
execute-end     R1
failbranch-postcommit R2 about to redrain
schedule->agent is already running  running=[R2]      <- R2 is running again
```

**No ORM update and no Core `update(Run)` sets the row back to `running`** — the listener saw the
`-> failed` writes and nothing after them, and `grep "update(Run)"` over `hub/hub` is empty. The
state is produced by transaction interleaving, not by application logic.

And the interleaving is available because **the suite gives every session the same database
connection.** `TEST_DATABASE_URL` is `sqlite+aiosqlite:///:memory:`, and SQLAlchemy forces
`StaticPool` for that URL — measured, not assumed:

```
$ DATABASE_URL=sqlite+aiosqlite:///:memory: python -c "...; print(type(engine.pool).__name__)"
StaticPool
```

Production resolves to `AsyncAdaptedQueuePool`, one connection per session. So in the suite a
background run task's `commit()` and a request session's transaction are the *same* SQLite
transaction, and `async with async_session_factory()` exiting can revert work another session
believes it committed. In production it cannot.

### Proven, 2026-08-29

The first pass of this finding said the mechanism was *probably* transaction interleaving on a
shared connection. It is, and here it is. A listener on `before_cursor_execute` / `begin` / `commit`
/ `rollback`, logging the **raw DBAPI connection** behind each event:

```
conn#3840 >>> BEGIN                                        (session A)
conn#3840 SELECT runs.id AS runs_id, …                     (session A)
conn#3840 >>> BEGIN                                        (session B, same connection)
conn#3840 UPDATE runs SET status=?, error=?, ended_at=?     (session B marks the run failed)
conn#3840 <<< COMMIT                                       (session B)
conn#3840 <<< ROLLBACK   <--                               (session A closes)
conn#3840 SELECT job_runs.…
conn#3840 UPDATE inbound_queue_entries SET delivery_attempts=?
conn#3840 <<< COMMIT
```

**Every statement in the whole trace is on one connection.** Two `AsyncSession`s each believe they
own a transaction; SQLite has exactly one per connection. One session's `COMMIT` ends the other's
transaction, and one session's closing `ROLLBACK` discards work the other believes it committed —
which is how the run ends up `running` with no `error` and no `ended_at`, forever.

**The trap that nearly hid it:** logging `id(conn.connection)` shows *different* ids per session,
because that names a per-checkout `_ConnectionFairy` wrapper rather than the connection. Read
naively it looks like proof of isolation. `driver_connection` is the one to log.

### What was measured, and why none of it was applied

Three configurations, each run against the reproduction:

| Configuration | Result |
|---|---|
| `NullPool` + `file:…?mode=memory&cache=shared` | **Dies.** `no such table: projects` — a shared-cache in-memory database exists only while a connection to it is open, and `NullPool` closes each one when it is done. |
| the same, plus a keep-alive connection held for the process lifetime | **Three of four tests in the reproduction fail**, and not the flaky one — different failures, in the mocked-spawn tests, with the mocked `FileNotFoundError` escaping instead of being handled. |
| `NullPool` + a **file-backed** SQLite database | **The flake disappears.** 12/12 probe runs clean and 6/6 of the flaky selection, against ~1 in 6 today. But the suite runs roughly **four times slower** — 2% of the suite in the time the current configuration takes for 8% — and a full run was stopped rather than completed. |

So a fix exists and is reachable, and it is **not** a one-line switch: the fastest isolated variant
breaks tests for a second reason, and the variant that works costs a multiple of the suite's runtime
on every run and every CI job. That is a change with its own design question, its own verification,
and a cost the operator should weigh — not something to flip unattended at 01:00.

### Swept for, 2026-08-29 — and there is a second one

The same interleaving is available to every test that lets a background run task commit while a
request session is open. That population is the **21 test files** that await a background run;
running all of them eight times over (257 tests, ~2.5 minutes a round) turned up:

| | |
|---|---|
| `test_agent_trigger.py::test_spawn_failure_broadcasts_run_failed_event` | **failed 1 round in 8** — a *different* test from the known flake, in the same file and the same family |
| the `xfail` at `test_agent_trigger_overrides.py:259` | alternated `xpassed` / `xfailed` across the eight rounds — it is `strict=False`, so it is harmless, but it is the same non-determinism showing as an expectedly-failing test that passes about half the time |
| everything else | deterministic across all eight rounds |

So the answer to "has anyone looked for others" is now yes, and the answer is **at least one more**,
plus the xfail that was already flagged. Both are in the population the mechanism predicts, which is
the useful part: the prediction held.

Two cells in `25469ac` were already found green for reasons unrelated to what they claimed. This is
a third mechanism for that, and the sweep above is the first time it has been quantified.

### What it costs today

`test_spawn_failure_marks_run_failed` failed **two of the three** full-suite runs on the night of
2026-08-28 and roughly **one in six** for the five-second selection;
`test_spawn_failure_broadcasts_run_failed_event` failed **one round in eight** of the targeted sweep.
The third full-suite run was completely green. So merging has a material chance of a red CI run for a
reason that has nothing to do with the branch — and an equally material chance of looking fine,
which is the harder half to act on.

### What to do about it

Not fixed here deliberately: the candidate fix is giving the suite genuinely independent
connections, which changes the transaction semantics under ~3,500 tests at once, cannot be verified
in less than a full 25-minute suite run per attempt, and can plausibly trade this flake for
`database is locked`. That is an operator's call, not something to change unattended.

The cheap reproduction is the contribution, and there is now a cheaper one still. This selection
takes about five seconds and fails roughly one run in six:

```
pytest hub/tests/test_agent_trigger.py -q -k "spawn_failure or unbound_agent or runtime"
```

Six consecutive runs of it **at commit `84c990e`, before any of 2026-08-28's changes existed**:

```
1 failed, 3 passed        <- assert 2 == 3   (delivery_attempts)
4 passed
4 passed
4 passed
4 passed
4 passed
```

That is also the attribution: the flake predates the F108 work, so a full-suite run of that branch
reporting this single failure is reporting this, not a regression. Worth having written down,
because it is the failure most likely to be misread as a casualty of the next change to touch the
queue — `2026-08-28-a-delivery-attempt-means-a-delivery` names it in its D7 for exactly that reason.

The earlier reproduction still has a use: a parametrized test running the scenario 40 times, which
stalls in ~6 of 40 and lets the *state* be inspected rather than only the assertion.

---

## F110 (B) — `AW_CHECK_UI_BUNDLE=1` passes on a stale bundle if you skip the build

**Status:** **fixed** (2026-08-29). Found 2026-08-28 by walking into it while shipping F108's UI
half — the script certified a bundle whose hash had not moved, and twelve tests agreed.

`CLAUDE.md` describes the guard as: after `npm run build`, run `scripts/refresh_ui_bundle.py`,
which "copies `dist/` over it, confirms the copy, and records `ui-build-stamp.json`, the
fingerprint of the source it was built from", and `test_ui_build_stamp.py` "gates the stricter
bundle-matches-source assertion behind `AW_CHECK_UI_BUNDLE=1`".

Run the refresh script **without** building first and the guard is satisfied anyway:

```
# three .tsx/.ts files edited, no `npm run build`
$ py -3.11 scripts/refresh_ui_bundle.py
Refreshed hub/hub/static/ui and recorded the build stamp.
$ git status --short hub/hub/static/ui
 M hub/hub/static/ui/ui-build-stamp.json          <- the JS hash never moved
$ AW_CHECK_UI_BUNDLE=1 pytest hub/tests/test_ui_build_stamp.py -q
12 passed
```

The stamp is written **from the current source**, and the assertion compares the stamp to the
current source — so the script stamps whatever `dist/` happens to hold as though it were built
from what is on disk now. The one input neither of them consults is whether `dist/` is older than
the source it is being certified against.

**Why it matters more than it looks.** This is the guard that exists so `/health` can stop
reporting `ui_stale`, and the failure it is aimed at — committing a bundle that does not match its
source — is exactly the failure it will now certify as fine. It also fails in the safe-looking
direction: everything is green, and the operator is served a UI missing the change whose tests all
passed. Running the build afterwards produced a different JS hash
(`index-CCnq-93I.js` → `index-C3KKeU0v.js`), which is how it was caught at all.

**Fixed by the second of the two candidates**, which keeps the build an explicit step:
`refresh_ui_bundle.stale_build()` refuses when the newest file under `hub/ui/src` is newer than
everything in `hub/ui/dist`. A build reads all of the source and writes all of the output, so a
source file newer than the whole bundle means the build never saw it. The refusal names the file
that moved and the command to run.

The stamp itself is excluded from the comparison. It is written into the copy *after* the build, so
counting it as build output would make every run look fresh — which is the failure this guard exists
to prevent, reintroduced by the guard.

Driven both ways before committing: with `dist/` current the script runs normally; after
`touch hub/ui/src/api/client.ts` it exits 1 with *"hub/ui/dist is older than
hub/ui/src/api/client.ts, so it cannot have been built from the source that is here now."* Test
`test_ui_build_stamp.py::test_the_refresh_script_refuses_a_dist_older_than_the_source`,
mutation-checked by disabling the guard.

**The other candidate is still open**: having the script run the build itself would make the
documented sequence impossible to get wrong, where this only makes getting it wrong loud. It was
not taken because it turns a copy step into a build step, which changes what `make ui` means — a
decision rather than a repair.

---

## F111 (B) — a self-registered agent with no runner is told to install a binary named after itself

**Status:** **superseded by an operator decision, 2026-08-29 — self-registration leaves the product.**
Found 2026-08-28 by driving F108's own fix against the trial Hub, and originally filed as a question
about what a third sentence should say. It is not. See *The decision* at the end.

Registered `unbound-driver` through `POST /agents/register`, bound it nothing, sent it a message:

```
POST /agent/trigger {"agent": "unbound-driver", "message": "hello"}
  -> 200 {"status": "queued",
          "waiting_reason": "Runner CLI 'unbound-driver' was not found in PATH."}
GET /queue/unbound-driver/status
  -> {"waiting_count": 1, "waiting_reason": "Runner CLI 'unbound-driver' was not found in PATH."}
```

There is no runner bound at all. The operator is told to go and install a program named after their
own agent, and there is no such program and never was.

### It is the case `get_agent_config`'s own comment says it fixed

`launchability.get_agent_config` (`hub/hub/launchability.py:361`) carries this, from 2026-08-25:

> Both patched the *bound* case only, so the **unbound** case — `runner_id IS NULL` — still fell
> through `RUNNER_CLI["native"] is None` to the agent-name fallback, and reported a missing CLI
> named after the agent. … all three such agents were reported unlaunchable with
> `Runner CLI 'architect' was not found in PATH` — a binary named after the agent.

The repair it made is guarded:

```python
elif not agent_row.self_registered and "runner" not in meta:
    meta["runner"] = RUNNER_UNBOUND
```

So a **self-registered** agent with no runner anywhere still takes the fallback — and the very
sentence the comment quotes as the symptom is what the drive read back, three days later.

### Why it is narrower than it looks, and why it still matters

An operator creating an agent in the Hub UI is unaffected: the UI posts
`POST /api/v1/projects/{id}/agents`, which sets `self_registered=False` (`api/v1/agents.py:669`).
`self_registered=True` comes only from `POST /agents/register` — an agent joining itself, and the
repo's own harnesses. That is exactly the population the 2026-08-25 measurement was taken on, so it
is reachable, it has been seen live twice now, and the surface it is wrong on is the one an operator
consults when nothing is happening.

### It is on the operator's main screen, three times in one view

Filed above from the API. Driven through the dashboard the same night, the same wrong sentence
appears three times in a single screenshot of the conversation view — in the message's
not-delivered badge, in the queue line beneath the transcript (*"1 waiting — Runner CLI 'ui-probe'
was not found in PATH."*), and under the composer (*"Queued — Runner CLI 'ui-probe' was not found
in PATH."*).

That is not a corner of an API response. It is the surface an operator reads when they are working
out why nothing is happening, and every line of it points at a program that does not exist.

### Not fixed here, because the obvious fix is also wrong

Dropping `self_registered` from the condition would make `probe_agent` answer *"No runner is bound
to this agent. Bind one in the Hub UI before it can run."* — and for a polling self-registered agent
that is **also** false. It runs itself; it is not waiting to be bound, and binding a runner is not
the remedy. Neither existing sentence is true of this agent, which makes this a question about what
the third sentence should say and which verdict owns it (`collaboration_ready` already draws a
related line) — a design decision, not a one-line change. Left for a spec loop.

### The decision, 2026-08-29 — there is no third sentence, because the population goes away

The operator's answer to "does self-registration still belong in the product" was **no**, and the
code agrees. Measured before asking:

- **No shipped client calls `POST /agents/register`.** Not the CLI — `src/agentweave/` only ever
  *reads* `self_registered` (`transport/http.py:570,579`). Not the UI — `hub/ui/src/api/agents.ts`
  types the flag and `AgentCard.tsx:65` renders a badge from it, but nothing posts to the route. Not
  `mcp_server.py`, which has no reference to either.
- Its only callers are **~30 Hub test files** using it as a fast agent fixture, `.claude/skills/
  e2e-loop/e2e.py`, and a row in `docs/reference/hub-api.md`.
- It comes from the archived `2026-04-26-agent-self-registration` change — the watchdog era. The rot
  is visible in the same file: `_CONTACT_MODES` still offers `"watchdog-spawn"` and `agents.py:668`
  still *defaults* to it, for a subsystem that was deleted. That is **F3**, and it has the same root.

So F111 and F3 both close by **deletion**, not by wording — the agent that reads the wrong sentence
can no longer be created. The real cost is re-fixturing the ~30 test files that use the route for
convenience. Queued as a spec loop.

---

## F112 (B) — creating a document with an unrecognised `kind` answers `500 Internal Server Error`

**Status:** **fixed** the same night (2026-08-28). Found by the full-surface sweep.

```
POST /projects/{id}/project/documents {"title":"Sweep C","kind":"change"}
  -> 500  Internal Server Error
POST /projects/{id}/project/documents {"title":"Sweep D","kind":"banana"}
  -> 500  Internal Server Error
```

`"change"` is not a contrived input. The Hub mints document paths under `spec/changes/…` and
reports the default kind as `"change-spec"`, so `"change"` is exactly what a caller guesses — and
the guess produces the least useful response the surface can give: no status worth branching on, no
sentence, nothing naming the four values that would have worked.

The valid set is `SPEC_KINDS = ("baseline", "system-map", "roadmap", "change-spec", "capability")`,
enforced by a CHECK constraint (`ck_spec_documents_kind`). `spec_lifecycle.create_document` wrote
`kind` straight through, so an unrecognised value reached the flush and surfaced as an unhandled
`IntegrityError`.

**The same function already guards the column beside it, and says why.** Its `phase` check carries
this comment:

> Stated here too so the refusal names the problem rather than surfacing as an IntegrityError from
> the flush below.

That reasoning was never applied to `kind`. This is the argument-versus-code gap the round
discipline exists for, sitting inside one function: the principle is written down, correct, and
applied to one of two adjacent columns.

**Reachable by agents, not only operators.** `create_spec_document` is an MCP tool, and it reaches
the same function. An agent that guesses the kind gets a 500 and has no way to learn the valid set —
the refusal is its only feedback and it carries nothing.

**Fixed** by mirroring the `phase` guard: `PhaseError(code="unknown_kind")` whose message names
every valid kind, which the route already maps to `409 {"message", "code"}`. Test
`test_an_unrecognised_document_kind_is_refused_and_names_the_kinds`; mutation-checked by removing
the guard.

---

## F113 (B) — `propose` promises "every check that refuses it" and omits one of them

**Status:** **open.** Found 2026-08-28 by the full-surface sweep. The fix changes a status code, so
it is a decision rather than a repair.

`POST /project/documents/propose` has two blockers and reports them through two different channels:

| Blocker | How it comes back |
|---|---|
| the payload is incomplete (`spec_completeness.check`) | **`200`** with a `blocking` array — one entry per check, each naming what to do |
| the exploration has not been closed (`spec_lifecycle.transition`, `:332`) | **`409 {"code": "explore_not_closed"}`** |

The second is **never in the first's list.** Driven live:

```
POST …/documents/propose            -> 200  blocking: [no_requirements, non_goals_empty]
   phase afterwards: exploring, explore_closed=false      <- the closure blocked it too, unlisted
POST …/documents/close-exploration  -> 200  explore_closed=true
POST …/documents/propose            -> 200  blocking: [no_requirements, non_goals_empty]
```

So an operator holding an incomplete document with an open exploration is told two things block the
proposal. Three do. They fix the two, propose again, and meet the third — a round trip caused only
by the list omitting one of its own members.

**The route states the contract it breaks**, which is what makes this a B rather than friction:

> *Move a document to `proposed`, or report every check that refuses it.* — the route docstring

It is also asymmetric in the other direction. The *same* situation — "this cannot be proposed yet,
and here is why" — arrives as `200` with a list when the payload is incomplete and as `409` when it
is complete but the exploration is open. A client cannot write one branch for "not yet".

### Why it is not fixed here

The clean fix is for `spec_service.propose` to compute the closure blocker as a finding and put it
in `blocking` with the others, leaving `transition()` as the authority behind it. That makes the
list honest and gives clients one shape — and it turns today's `409 explore_not_closed` from this
route into a `200` with a blocker, which is a behaviour change with tests naming it.

The additive alternative — add the closure finding only when the list is already non-empty — keeps
every status code and makes the list complete exactly when it exists, which is a worse contract
than either of the other two.

Choosing between those is the operator's call, and by this repository's own rule a change that
needs a spec goes through three rounds before a line of it is written.

---

## F114 (A) — sending three messages to an agent that cannot launch destroys the first one

**Status:** **fixed** (2026-08-29) by `2026-08-28-a-delivery-attempt-means-a-delivery`, through
three rounds and re-measured live. Measured 2026-08-28 against the trial Hub. F108's round 1 filed
this abstractly ("a non-transient refusal consuming three delivery attempts on every path"); this
is the measurement, and it was worse than the abstraction suggested.

Five messages to an agent with no runner bound, sent back to back, nothing else happening:

```
entry                  content      state       att  abandoned_reason
entry-aeef00996fce     message 1    withdrawn     3  delivery failed 3 times (Runner CLI '…' was not found…)
entry-2e1f5501377e     message 2    queued        2
entry-f6cb62ebf395     message 3    queued        0
entry-20c7fe2918f9     message 4    queued        0
entry-f202b1e9d3ec     message 5    queued        0
```

**Message 1 is gone, and no run was ever attempted for it.** Its recorded reason —
*"delivery failed 3 times"* — describes three deliveries that never happened. What actually
happened is that the operator sent two more messages: every `POST /agent/trigger` calls
`schedule_agent`, which selects the oldest conversation's entries and, on a non-transient refusal,
increments `delivery_attempts` on each of them (`turn_scheduler.py:191`). Three *messages* consume
the three *delivery attempts* — and so does anything else that schedules the agent, including the
Continue button below and `redrain_queued_agents`, which runs at the end of every turn in the
project.

Elapsed time is not involved. This took under two seconds.

### Why it is severity A

- **The operator's input is destroyed**, silently as far as the composer is concerned — every
  trigger answered `200 … "queued"`.
- **The stated reason is false.** An operator reading "delivery failed 3 times" will go looking for
  three failures, and there are none.
- **It undercuts F96 exactly.** F96 exists so that binding a runner delivers the message queued
  while none was bound. An operator who sends a few messages before getting round to the binding
  has already lost the first ones. F96's own live log shows the same mechanism from the other side:
  `waiting_reason` had become `"delivery failed 1 time; 2 attempts left"`, the retry counter having
  taken the reason's place.
- **The trigger is ordinary use.** Not a retry storm, not a loop — a person typing twice more.

### The product's own suggested remedy is what destroys it

The conversation view offers a button for exactly this situation:

> **Continue** — *`<agent>` has work waiting — start it without sending a message.*

It calls `POST /conversations/{id}/continue`, which reaches `schedule_agent` like everything else.
Measured (`scripts/drive/t_continue_burns_attempts.py`), one queued message, no other activity:

```
after queueing:      state='queued'     attempts=1
Continue click 1:    started=False  ->  state='queued'     attempts=2
Continue click 2:    started=False  ->  state='withdrawn'  attempts=3
      abandoned_reason: delivery failed 3 times (…); the Hub stopped retrying
Continue click 3:    started=False  ->  state='withdrawn'  attempts=3
```

**Two clicks.** Every one answered `200`. Every one reported `started: false` and nothing else — no
indication that clicking again is destructive, and no sign afterwards that the click is what did
it. An operator who cannot see why their message is not moving, and presses the button the product
put there to move it, deletes it.

That is what settles the severity. It is not an edge case reachable by unusual API use; it is the
single most likely thing a person does next.

### And the operator is told the false thing, not just the database

Driven through the dashboard the same night (`scripts/drive/t_ui_refusal.py`, Playwright against
the trial Hub), the conversation view renders the message with a red badge:

```
NOT DELIVERED   delivery failed 3 times (Runner CLI 'ui-probe' was not found in PATH.);
                the Hub stopped retrying
```

So this is not a database detail an operator would have to go looking for. The claim that delivery
was attempted three times and abandoned is stated on the main conversation surface, above the
message it destroyed, and it is false.

### The fix shape, and why it was not available until tonight

`F56` added the counting for a stated reason: a refusal raised before any run exists "repeats
identically forever, and every entry queued behind it starves along with it". That reasoning is
sound — **for a refusal about what was asked.** It is exactly wrong for a refusal about the
environment, where the entry is *supposed* to wait for a repair and the product has promised to
keep it.

Until tonight there was no way to tell those apart at that line. F108 introduced
`TriggerAgentError.request_level` for the operator's route, and the same flag answers this:

> count a delivery attempt only when the refusal is **request-level**; leave the counter alone for
> an environment-level refusal, exactly as it is already left alone for a transient one.

A permanently-wrong entry still stops wedging the queue, which is what F56 was protecting. An entry
waiting for a runner to be bound stops being consumed by the operator's own typing, which is what
F96 was protecting. The two findings stop pulling against each other.

**Not implemented when this was filed.** It changes when the Hub gives up on operator input, which
is the most consequential thing the queue does, and this repository's rule is that a change needing
a spec goes through three rounds before a line of it is written.

### What the three rounds changed, and why the first shape was wrong

The fix shape above — *reuse `request_level`* — **is not what shipped**, and round 2 is why.

`request_level` answers *will this caller ever be satisfied*. The counter is asking something else:
*does this refusal block only this entry, or the whole agent?* Those axes cross. `:756` — "could not
prepare isolated worktree" — is environment-level **and** entry-specific, because the workspace it
failed to prepare is the **task's**, not the agent's. And `schedule_agent` always builds its turn
from the oldest eligible entry, so an entry whose checkout can never be prepared sits at the head
and starves every other conversation. Gating on `request_level` would have stopped counting there
and reintroduced F56's scenario exactly.

What shipped is a third classification, `TriggerAgentError.agent_wide`, defaulting to `False`, on
three sites and nothing else: **no runner is bound**, **the bound runner's row is gone**, **the
bound runner's CLI is not on PATH**. All three are properties of the agent's own binding, so nothing
is starving behind the entry they protect — which is the same reason the transient branch beside
them already declines to count.

Round 3 added one more correction, and it made the change smaller: the requirement everyone assumed
this contradicted — *Repeated delivery failure does not wedge an agent* — is scoped in its own first
sentence to *"a failed run's input"* and *"how many times a queued input has **failed to be
delivered**"*. This path has no run and no delivery. **The behaviour F114 complains about was never
specified at all**; `F56` added the second counting site without a requirement behind it.

### Re-measured live, 2026-08-29

Same two scripts that produced the finding, same trial Hub, after the fix:

```
$ py -3.11 scripts/drive/t_queue_attrition.py
  message 1..5 queued
  entry-abafb836663f  message 1  queued  0
  entry-63648d89193b  message 2  queued  0
  entry-92bb8988880d  message 3  queued  0
  entry-c0594881f6a4  message 4  queued  0
  entry-42b7143c8cea  message 5  queued  0
  sent 5, still queued 5, withdrawn 0

$ py -3.11 scripts/drive/t_continue_burns_attempts.py
  Continue click 1: started=False -> state='queued' attempts=0
  Continue click 2: started=False -> state='queued' attempts=0
  Continue click 3: started=False -> state='queued' attempts=0
  the entry survived three clicks
```

Before: message 1 withdrawn at three attempts, and two clicks of Continue enough to do it.

**Not re-measured live: the delivery after the repair.** Binding a runner on this machine spawns a
real provider run, and no token budget was agreed for the overnight session, so the outcome —
*perform the repair, get every message* — is covered by
`test_the_input_survives_until_the_agent_can_run` rather than by a live drive. That is the one
assertion in this finding's closure that rests on a test rather than on the product.

---

## F115 (B?) — the agent worktree is a working directory, not a boundary: an absolute path writes straight into the operator's checkout, and the Hub still records the worktree

**Status:** **open, severity is the operator's call.** Found 2026-08-29 driving rows 13 and 14 — the
first live agent turns ever spent on this product. Reproduced across four runs.

Project `drive-2026-08-29` (`proj-8e29ef6813e4`), one agent `asker` on a Haiku runner, no task
binding. Every run was told the same thing in different words: *write a line to a new file in the
project root.*

| Run | Posture | Where the file landed |
|---|---|---|
| `run-cd72f733910f` | default | — (`ask_user` row, no write) |
| `run-c10e35f30d81` | default | `.agentweave/worktrees/asker/drive-note.txt` — **isolated** |
| `run-72de0f5c6898` | `manual` | `C:\…\drive-2026-08-29\drive-note-121250.txt` — **the operator's checkout** |

**All four runs recorded the same `workspace_dir`:**

```
sqlite> select id, workspace_dir from runs where project_id='proj-8e29ef6813e4';
run-cd72f733910f | C:\…\drive-2026-08-29\.agentweave\worktrees\asker
run-c10e35f30d81 | C:\…\drive-2026-08-29\.agentweave\worktrees\asker
run-e3f1a39c2a14 | C:\…\drive-2026-08-29\.agentweave\worktrees\asker
run-72de0f5c6898 | C:\…\drive-2026-08-29\.agentweave\worktrees\asker   <- wrote outside it
```

So the Hub believes all four ran in the worktree. Three did. One wrote into the checkout the
worktree exists to protect, and nothing recorded that it had.

### What actually decides it

Nothing in the product — **the model's choice of path form.** The worktree is the spawned process's
*cwd*. An agent that writes `drive-note.txt` stays inside it; an agent that resolves "the project
root" to `C:\Users\huida\Documents\drive-2026-08-29\drive-note.txt` and passes that absolute path
to `Write` lands outside it and succeeds. Same agent, same project, same instruction, two different
outcomes across two runs — because the model spelled the path differently the second time.

### Why it matters beyond the stray file

- **Evidence is footprinted at `Run.workspace_dir`** (F71, 2026-08-27). A change written outside the
  worktree is invisible to footprinting: the evidence looks at the worktree and finds nothing, so
  work that *did* happen cannot be attributed, and work that escaped review is not flagged.
- **Per-task isolation** (`2026-08-27-work-is-isolated-per-task`, 69 tasks) rests on the same
  assumption. Its guarantee — approving one task cannot ship another task's unreviewed work — holds
  only for agents that use relative paths.
- The auto-snapshot commit on `agentweave/<agent>` captures the worktree, so the escaped write is
  **not** in the snapshot either.

### The counter-argument, which is why the severity is a question and not a claim

In `manual` posture the operator *was* shown the truth. The card named the tool and the full input:

```
tool_name: "Write"
tool_input: {"file_path": "C:\…\drive-2026-08-29\drive-note-121250.txt",
             "content": "drive touched this"}
```

A reading operator sees the absolute path and can deny it. That is the permissions feature doing
exactly its job, and it is a real argument that the boundary is *meant* to be the operator rather
than the filesystem — consistent with CLAUDE.md's native mode, which "can open valid local
directories" and reserves path confinement for Docker mode.

But the two default-posture runs raised **no card at all**, and one of those wrote a file. So in the
posture an operator is most likely to be running, nothing shows the path and nothing constrains it.

**Decided by the operator, 2026-08-29: the worktree is only ever a cwd, and the operator is the
boundary.** Native mode is not to confine writes; path confinement stays a Docker-mode property. So
this is a **`workspace_dir` honesty** problem, not a worktree-setup defect, and the change is:

1. `Run.workspace_dir` must stop implying containment — it records where the run was *started*, not
   where its writes landed.
2. A write outside the worktree should be **detected and recorded** rather than passing silently.
3. Evidence footprinting (F71) must learn about escapes, so work that left the worktree is not
   invisible to attribution.
4. The docs must say plainly that native mode does not confine and Docker mode does.

The accepted risk, in the operator's words: work still lands in the real checkout — the operator
just finds out about it. Queued as a spec loop; by this repository's rule it gets three rounds
before a line of it is written.

### Part (2) decided, 2026-08-30 — and the premise it was parked on was wrong

Part (2) was the one thing left unauthorised, on the stated grounds that *default posture raises no
permission card, so there is nowhere honest to detect an escape*. **That premise is false.** The
card is the **approval** path; there is a separate **observation** path that runs in every posture,
because it is how the transcript is built. `runner_parsing.py:264-272` parses every `tool_use` block
from Claude's stream with its full input:

```python
elif block_type == "tool_use":
    events.append(tool_use_event(
        tool=block.get("name", "unknown"),
        input_data=block.get("input", {}),      # the whole input, file_path included
        call_id=block.get("id"),
    ))
```

That fires regardless of `permission_mode`, and `codex_appserver.py` emits the same events for
Codex. F115's own escaping run was a `Write` call carrying an absolute `file_path` — exactly the
shape this parse already sees, in exactly the posture the finding is about.

**Decided: detect at the tool-event parse point, and name it for precisely what it catches.** The
recorded fact is *a file tool wrote outside the workspace*, never "escapes". Two vectors are
explicitly out of scope and get their own finding rather than being silently implied by the label:

- **Shell writes.** A `Bash` call arrives as a command string, not a path; `echo x > /abs/path`
  is invisible to a path check.
- **Symlink traversal.** A symlink inside the worktree pointing out defeats any path check, because
  the path the tool reports is legitimately inside.

The finding's own warning — a detector that misses the case it is about is worse than none, because
it reads as coverage — applies to the **label**, not to the mechanism. Named exactly, this is real
coverage of the reproduction that produced the finding.

**Containment is not to be built.** If native mode ever confines, it adopts an existing OS-level
sandbox rather than inventing a boundary — see the research below.

### What the rest of the field does (researched 2026-08-30)

**"A worktree is not a sandbox" is the explicit industry consensus**, and it is this finding's
reframe arrived at independently:

> A separate checkout constrains where an agent's *Git* writes land. It does not constrain what
> commands the agent runs, what it reads outside the repository, or where a symlink points.
> — *Isolation boundary, not a security boundary.*
> ([digitalapplied.com](https://www.digitalapplied.com/blog/agent-cli-worktree-isolation-parallel-coding-agents))

Worktrees solve a **concurrency** problem, not a **containment** one. That survey is also where the
symlink vector above came from.

**The architecture is mainstream.** The GitHub Copilot desktop app (Build 2026) runs each parallel
agent session in its own isolated worktree; Copilot CLI shipped an experimental `/worktree` command
on 2026-08-03; Claude Code documents a `--worktree` flag and `isolation: "worktree"` for subagents.
One worktree per agent on its own branch is table stakes, not a differentiator.

**Containment exists as a buyable layer.**
[`@anthropic-ai/sandbox-runtime`](https://github.com/anthropic-experimental/sandbox-runtime)
enforces filesystem and network restriction at the OS level without a container: Seatbelt
(`sandbox-exec`) on macOS and bubblewrap on Linux, both deny-by-default with an allow-list; on
**Windows**, a dedicated `srt-sandbox` local user account with additive inheriting ACEs granted on
the working tree for that SID alone — a model that composes with worktrees unusually well. Claude
Code ships its own `/sandbox` on the same primitives.

**Why that is a later option and not this change.** Windows support is **alpha**, needs a one-time
elevated `npx @anthropic-ai/sandbox-runtime windows-install`, cannot do per-execution filesystem
overrides, and does not reach per-user tool installations. Claude Code's `/sandbox` is documented
for Linux and macOS, with its sandboxed bash tool a beta research preview. And on Linux the
deny-path mechanism *"only blocks files that already exist"* — which is precisely the create-a-new-
file case F115 reproduced. Recorded as the eventual containment path, to revisit when Windows
support leaves alpha.

### The cross-worktree variant — worse than the case above

Raised by the operator 2026-08-30 and confirmed in code. Everything above concerns an agent writing
into the **operator's** checkout. The same mechanism lets alice write an absolute path into
**bob's** worktree, and the consequence there is worse.

`snapshot_worktree` (`hub/hub/worktrees.py:737-776`) commits whatever is dirty in a worktree onto
that agent's own branch:

```python
_run_git(worktree, "add", "-A")
...
message = f"Auto-snapshot: {agent}'s turn"
```

`git add -A` — everything in the folder, whoever put it there — committed to `agentweave/bob`,
under a subject saying it was bob's turn.

| Escape | What happens | Would the operator notice? |
|---|---|---|
| → operator's checkout | file sits uncommitted, visible in `git status` | probably, eventually |
| → another agent's worktree | **auto-committed to that agent's branch**, labelled as that agent's turn, flows through review and merge looking legitimate | no |

The second does not merely escape isolation — it **launders the work through the wrong identity**.
Review approves it as bob's, evidence attributes it to bob, and the trail back to alice is gone.
Part (2)'s tool-level detection catches this too, since the path is equally outside the writing
agent's own workspace; what it adds is that the recorded fact must name *which* workspace was
written into, not merely that one was left.

### One thing this is not

Not a prompting problem. Non-determinism makes the escape *unpredictable*; it is not what makes it
*possible*. A perfectly deterministic agent instructed to use absolute paths would do the same and
succeed. "Always use relative paths" is a request competing with a model that often has good
reasons to resolve paths absolutely. The only real levers are an OS-enforced boundary or noticing
after the fact.

### Round 1 correction, 2026-08-30 — the default posture does constrain this, and the escape was an approval

Written while proposing `openspec/changes/a-write-outside-the-workspace-is-recorded`. **The
operator's decision above is unchanged and none of the four parts moves.** What is wrong is a
premise this finding argued from, and the round discipline exists precisely for the case where the
argument is wrong while everything it argues about is right.

This finding says *"in the posture an operator is most likely to be running, nothing shows the path
and nothing constrains it."* That is false. `DEFAULT_CLAUDE_PERMISSION_MODE = WORKSPACE_PERMISSION_MODE`
(`hub/hub/runner_commands.py:66`) — the default posture for a non-yolo Claude run is `workspace`, which
routes every call to `mcp_server.approve_tool_call`, and `_decide` (`hub/hub/mcp_server.py:864-916`)
refuses a path outside `AW_WORKSPACE_DIR` on a `realpath` + `commonpath` comparison. There is a
shipped requirement of record for it: `agent-run-sandboxing`, *"A posture exists in which the
workspace boundary is enforced per tool call"*.

Measured rather than read, against this checkout:

```
outside abs : {'allow': False, 'reason': "'...\aw-outside\drive-note.txt' is outside your workspace"}
inside rel  : {'allow': True,  'reason': 'inside your workspace'}
traverse .. : {'allow': False, 'reason': "'../drive-note.txt' is outside your workspace"}
read outside: {'allow': False, 'reason': "'...\aw-outside\drive-note.txt' is outside your workspace"}
default posture: workspace | without approver: acceptEdits
```

So the default posture refuses the exact call this finding reproduced — including the `..` traversal
variant — and it checks reads as well as writes. And `run-72de0f5c6898`, the run that escaped, was
**`manual`**: the posture in which the *operator* answers. The card named the tool and the full
absolute path, and it was allowed. **The escape was an approval, not a hole in the default.**

The gap therefore relocates rather than shrinking. It is not that the default posture is blind; it
is that an outside-the-workspace write leaves **no trace in any posture where it is possible** —
`manual` where the operator approved it, full access which checks nothing, and the `acceptEdits`
fallback used where no Hub MCP server is configured to answer (`runner_commands.py:73`). Plus one
that survives even under `workspace`: a shell command that builds its path at runtime, which
`_decide` says of itself is *"a boundary, not a sandbox"*.

**Consequence for part (4).** "The docs must say plainly that native mode does not confine and Docker
mode does" cannot be written as stated, because it is false in both directions: native mode's default
posture *does* check, and native mode's unchecked postures exist too. The proposal states it **per
posture** instead, which serves part (4)'s intent — say plainly what is checked — with a sentence
that is true.

---

## F116 (B) — the same API forbids an unknown field on one route and silently drops a safety-relevant one on another

**Status:** **FIXED 2026-08-29** on `autonomous/2026-08-29-decided-fixes-and-drive`, through the
full three-round spec loop (`openspec/changes/2026-08-29-an-unknown-field-is-named/`). Found
2026-08-29 while driving row 14, by getting it wrong first.

Driven live on a Hub on 8011 running the fix: F116's exact body now answers
`422 {"loc":["body","permission_mode"],"type":"extra_forbidden"}`, and the posture sent the way it
actually travels — in `overrides` — still raises the card, which the operator allowed and the run
then wrote its file. A refusal that broke the working path would not have been a fix.

The rule went on a shared `RequestModel` base rather than on the one model, so all 57 request body
models reachable from `app.routes` now forbid unknown fields, with one named exemption
(`SpecDocumentCreate`, kept lax by two shipped requirements) and one named untyped body
(`patch_agent` — see F117 below). A test walks the routing table and asserts both, so the next lax
model is a red build rather than a discovery three months from now.

Three things the fix would have broken, all repaired rather than exempted: `normalize_legacy`
rebuilt its payload from keys it knew and so kept absorbing unknown fields on the legacy path;
`normalize_assignee_aliases` stripped its aliases only when `assignee` was absent, so a
rolling-upgrade body was refused for a name the contract accepts; and `PUT …/project/instructions`
read `body.get("content", "")` off an untyped dict, so a misspelled field answered `200` and
**blanked the project's instructions**.

`POST /projects/{id}/agent/trigger` accepts an unknown top-level `permission_mode` and returns
`200`, having ignored it:

```
POST …/agent/trigger {"agent":"asker","message":"…","permission_mode":"manual"}
  -> 200 {"success": true, "status": "running", "run_id": "run-c10e35f30d81"}
```

No card was ever raised; the run wrote its file unsupervised. Posture is not a top-level field at
all — it travels in `overrides`, keyed `permission_mode`, which is the map the composer's
Permissions pill fills (`hub/ui/src/api/modelCatalog.ts:56`,
`hub/ui/src/components/agents/AgentOutputPanel.tsx:327-328`). Sent that way it works, and the card
appears in about twelve seconds.

The sibling route is strict about exactly this:

```
POST …/permission-requests/{id}/decide {"decision":"allow"}
  -> 422 {"detail":[{"type":"missing","loc":["body","allow"],"msg":"Field required"},
                    {"type":"extra_forbidden","loc":["body","decision"],
                     "msg":"Extra inputs are not permitted"}]}
```

Two opposite policies inside one API, and **the lax one is the safety-relevant one.** An operator
scripting a supervised run gets a normal-looking `200`, a run that starts, and no supervision —
with no way to tell from the response that the posture they asked for was discarded. The strict
route, by contrast, told me precisely what was wrong and what the field was called; that refusal is
the product at its best, and is what the trigger route should do with an unknown `permission_mode`.

Smallest honest fix: forbid extras on `TriggerAgentRequest` too, so the misuse is named rather than
absorbed. Worth checking whether other write routes share the lax setting before choosing where the
rule belongs.

### Two smaller things noticed in the same drive, filed here rather than as findings

- **The agent roster listing carries no `id`.** `GET /projects/{id}/agents` returns rows keyed by
  `name` with no identifier, while `POST /projects/{id}/agents` returns `{"id": "agent-…"}`. Nothing
  is broken — `/agent/trigger` wants the name — but a script that creates an agent and then reads
  the roster cannot correlate the two without matching on name.
- **F3 confirmed live on the default path.** A freshly created Hub-owned operator agent comes back
  `"contact_mode": "watchdog-spawn"` — the deleted subsystem — from `POST /projects/{id}/agents`,
  not from any legacy route. Same root as F111's removal, and it should go with it.

---

## F117 (B) — `PATCH /agents/{name}` takes an untyped body: a misspelled setting answers 200 and changes nothing

**Status:** open. Found 2026-08-29 by F116's own surface walk, confirmed live on 8011.

F116 made every request body model refuse what it cannot honour. Three routes had no model to put
the rule on — `body: dict`. One was `PUT …/project/instructions`, fixed in the same change because
its defect was destructive. One is `POST …/agents/register`, which F111 deletes. This is the third,
and it is the same shape as F116 on the route that carries an agent's *safety* settings —
`default_permission_mode`, `permission_timeout_seconds`, `question_timeout_seconds`:

```
PATCH …/agents/asker {"permission_timeout_secondz": 5}
  -> 200, agent unchanged, nothing said
```

The handler does have a vocabulary check, but it is narrower than it looks and it was described too
generously in the change's own design (D7, which said "400 for an unknown key"). Measured: the
`set(body.keys()) <= _unrestricted_fields` guard fires **only** when the name belongs to a
session-synced configured agent, and then answers `409 "reserved for a configured agent"` — a
message about the name, not about the field. For a Hub-owned agent, which is every agent an
operator creates in the UI, there is no check at all.

Not fixed inside F116 deliberately: modelling this body turns the existing `400`s that the handler
raises by hand (`contact_mode`, and the per-field validators below it) into FastAPI `422`s, which
is a visible change across the agent settings UI and wants its own review. It is named in
`NO_CONTRACT_BY_DESIGN` in `hub/tests/test_request_strictness.py` with that reason, so the exemption
is a decision on the record rather than a silence — but a named exemption over a live defect is not
a fix.

---

## F118 (B) — every task id in every recorded transcript reads `ta<redacted>`, because `task-` ends in `sk-`

**Status:** fixed this session (`hub/hub/runner_events.py`, `src/agentweave/diagnostics.py`), with
nine tests watched red first and the repair driven live on 8011.

Found driving row 16 of the coverage matrix. Reading the stored transcript of two agents editing one
file, every identifier that should have said *which task* was gone:

```
tool_use   mcp__agentweave__update_task {"task_id": "ta<redacted>", "status": "completed"}
tool_use   Read {"file_path": "C:\\...\\.agentweave\\tasks\\ta<redacted>\\calc.py"}
tool_result "16ddfc6 Auto-snapshot: beta's turn on ta<redacted>"
tool_result "On branch agentweave/task/ta<redacted>\nnothing to commit, working tree clean"
```

**The cause is two characters.** `_SECRET_VALUE_RE`'s second alternative is `sk-[A-Za-z0-9_=-]+`,
the OpenAI key prefix, and it was **unanchored** — so it matched the `sk-` inside the word
`ta·sk-479933b7ec7f`. Reproduced at the function, no server required:

```
redact_secrets("task-479933b7ec7f")                  -> 'ta<redacted>'
redact_secrets("subtask-1")                          -> 'subta<redacted>'
redact_secrets("agentweave/task/task-670a6d4a5b72")  -> 'agentweave/task/ta<redacted>'
```

`task-<12 hex>` is the shape the Hub mints for the primary key of **every** task, so this fired on
every task id in every stored transcript, in every project, since the redactor shipped. `subtask-1`
shows one trailing character is enough.

**Why it matters more than a cosmetic loss.** The task id is the join between a transcript and the
board. An operator reading an agent's output to answer *"what did this run actually touch"* had the
one identifier that answers it replaced by a redaction marker — and, because the marker looks
deliberate, it reads as the product protecting a secret rather than as damage. The file paths under
`.agentweave/tasks/<task-id>/` and the auto-snapshot commit messages went with it, so the transcript
could not even be reconciled against git by hand.

**The fix** anchors both credential prefixes with `(?<![A-Za-z0-9_])`: a prefix is only a prefix at
the start of a word. The lookbehind deliberately does *not* reject `-`, because a hyphen does not
start a word — `x-sk-abcdef0123456789` is still a key wearing its prefix and is still redacted,
while `task-...` is not. The third alternative is untouched.

Driven live after the fix, a real Haiku turn on a Hub restarted onto the repaired code:

```
tool_use    mcp__agentweave__get_task {"task_id": "task-020be941e2e8"}
tool_result {"id":"task-020be941e2e8", ...}
text        task-020be941e2e8
```

**This is F31 one alternative over, and the same lesson.** F31 narrowed the *third* alternative
after measuring that it ate the Hub's own vocabulary. Nobody then asked the same question of the
first two — and the answer was worse, because a document slug only sometimes runs to 32 characters
whereas *every* task id contains `sk-` by construction. The F31 test file existed, was thorough,
and contained no task id.

---

## F119 (B) — F31's repair landed in one of three copies of the same regex

**Status:** Hub half fixed this session (`hub/hub/scheduler.py` now calls `redact_secrets`); the
CLI's copy keeps its own third alternative deliberately, and that divergence is left for the
operator.

The same credential-redaction rule is written out three times:

| Where | What it redacts | Third alternative |
|---|---|---|
| `hub/hub/runner_events.py:46` | agent transcripts | `[A-Za-z0-9+/=]{32,}` — narrowed by F31 |
| `hub/hub/scheduler.py:42` | a loop's `error_summary` | `[A-Za-z0-9_=-]{32,}` — **pre-F31** |
| `src/agentweave/diagnostics.py:35` | `doctor` output | `[A-Za-z0-9_=-]{32,}` — **pre-F31** |

F31 measured its list against the transcript path and fixed that path. The other two kept the broad
rule, so the exact strings F31 recorded as damage still vanish from the surface an operator reads
when a **firing fails**, which is the one place a long identifier is most likely to appear:

```
_safe_error_summary(RuntimeError("could not start mcp__agentweave__record_evidence"))
  -> "could not start <redacted>"
_safe_error_summary(RuntimeError("could not start spread-fairness-metric-fix-for-idle-staff"))
  -> "could not start <redacted>"
```

All three also carried F118's unanchored `sk-`.

**Fixed for the Hub by deleting the copy, not by syncing it.** `_safe_error_summary` now calls
`redact_secrets` from `runner_events`, so there is one definition inside the Hub and the next repair
cannot land in only one of them. The CLI's copy stays separate on purpose — the CLI imports nothing
from the Hub, which `runner_events.py`'s own docstring states as the reason it is a reimplementation
in the first place. Its `sk-` anchor is fixed (F118 applies verbatim), its third alternative is not:
what `doctor` prints is env and config values rather than the Hub's composed vocabulary, so F31's
measurement does not transfer, and narrowing a *secret* filter on an unmeasured surface is the
operator's call. **Open question for the operator: should the CLI's catch-all be narrowed too?**

---

## F120 (C) — a flow's claim of a task is recorded as an operator's transition, by nobody

**Status:** open, filed not fixed. Confirms `SURVEY.md`'s code-read suspicion **S6**, unverified
since 2026-08-23.

Driving row 12, the flow's first firing claimed both of its tasks. The transition rows:

```
seq  task              from     to           actor_kind  actor_agent  origin
5    task-524904110504 pending  assigned     operator    None         actor
6    task-08afabab0ba6 pending  assigned     operator    None         actor
7    task-524904110504 assigned in_progress  run         alpha        runtime
```

Rows 7 onward are exemplary — the run, the agent, the origin. Rows 5 and 6 say a *person* moved
those tasks, and name nobody. No person was awake: this was `POST /jobs/{id}/run` fanning out to two
agents. The scheduler passes `operator()` to `apply_transition` because the loop is acting with
operator authority, and authority is genuinely what the *gate* needs — but it is not what the
*history* records. The argued point of the transition machine is that "every recorded history
describes a legal sequence" worth reading, and an operator auditing how a task came to be assigned
is told the answer is themselves.

Not fixed here: it wants an actor kind meaning "a loop, with operator authority", which touches the
transition machine's declared vocabulary and every reader of `actor_kind`. That is a spec loop, not
a drive fix.

---

## F121 (C) — one firing of a flow, two `JobRun` rows, and the badge says "2 runs"

**Status:** open, filed not fixed. Possibly working as designed; recorded because the *word* is
overloaded, not because the rows are wrong.

A flow that dispatches two turns in one firing writes two `JobRun` rows with an identical
`fired_at`, and increments `job.run_count` once per row:

```
run-9f783fb558f2  2026-08-29 15:49:46.910091  completed  manual  tick_count=1
run-45a5e9048a54  2026-08-29 15:49:46.910091  completed  manual  tick_count=1   <- same firing
run-16becaa17f09  2026-08-29 15:50:24.844657  completed  manual  tick_count=1
run-03cfcff87109  2026-08-29 15:50:24.844657  completed  manual  tick_count=1   <- same firing
```

`POST /jobs/{id}/run` returned **one** `run_id` per call, and the API was called twice.
`run_count` read 4.

The per-row design is deliberate and well argued (`_stage_selection`: "Returns the `JobRun` id so
the starter can record a refusal against it") — a dispatched turn needs somewhere to record its own
outcome. But `JobCard.tsx:434` renders `{job.run_count} runs`, and the F25 comment four lines below
it defines the same word as *"firings that actually ran"*. Both definitions are now live on one
card, and a flow is exactly the case where they diverge. A third firing that dispatched one turn
took the count to 5 for three firings.

Nothing is *wrong* in the database. What an operator cannot do is read "how many times did this
flow fire" off the card.

---

## Row 12 FLOWS and row 16 WORKTREES — driven end to end, and what held

Both rows were `not reached` in every previous sweep. Driven 2026-08-29 on 8011 against this
branch's code, in a fresh git project (`drive-wt-0829`, `proj-dc4d43543bea`) with three Haiku agents.

**Row 16 — worktree isolation held completely.** Two agents, two tasks, both told to edit `calc.py`:

- each got its own checkout at `.agentweave/tasks/<task-id>/` on its own branch;
- both edits landed, on their own branches, as `Auto-snapshot: <agent>'s turn on <task>` commits;
- **`main` was untouched** — `git show main:calc.py` still had only `add` and `sub`;
- `GET /worktrees/conflicts` named both *task* workspaces (not the agents) and the one conflicting
  path, `calc.py`, which is exactly what `ConflictInfo`'s docstring promises;
- `GET /worktrees/<agent>` listed each agent's task checkouts with `provisioned: true` and
  `grandfathered: false`, and provisioned nothing by being read.

**Row 12 — a flow decomposed an approved document and reviewed its own work.**

- Two independent tasks materialised onto the board from the approved document, into the flow's
  queue, with their requirement links intact (`FR-1`, `FR-2`).
- The first firing started **both** in parallel, one per agent — the property that distinguishes a
  flow from a loop, and it works.
- With a third agent present, a later firing resolved `gamma` — idle, holding no work, **not the
  author** — as reviewer for `alpha`'s completed task, moved it to `under_review`, ran a real review
  turn, and `gamma` approved it. The whole ladder, live.

**Refusals that held, each naming what would work instead.** Every one of these was provoked
deliberately:

```
completed -> under_review, author still assigned
  403 "...it is still assigned to 'alpha', the agent recorded as completing it, so the move would
       claim its own author is reviewing it. Assign a different reviewer, or clear the assignee to
       review it yourself. Left as is, the task is claimable by nobody and 'alpha' counts as busy
       for every other review in this project."

completed -> approved
  409 "Cannot move a task from 'completed' to 'approved'. From 'completed' the available
       transitions are: rejected, under_review."

record_evidence, same requirement, same task, same commit, twice
  409 duplicate_evidence "...Recording the same demonstration twice makes the reviewer decide once
       per copy and overstates FR-1's evidence count. If the wording is wrong, say so on that piece;
       if the work has moved on, commit it first so the new evidence names the commit it
       demonstrates."

integration retry on a task in 'completed'
  409 "Cannot retry integration for a task in 'completed': only an approved task has work to
       integrate."
```

The agents *read* the duplicate-evidence refusal correctly — alpha's transcript reasons "evidence
for FR-1 has already been recorded" and moves on rather than retrying.

---

## F122 (B) — a flow drives a task to `approved` by itself, and the work never reaches the branch

**Status:** open, filed not fixed. **Needs an operator decision**, so it is deliberately not
repaired here.

The end of row 12's drive. A flow started `task-524904110504`, `alpha` implemented it and recorded
evidence, a later firing resolved `gamma` as an independent reviewer, and `gamma` approved it. The
board reads `approved`. `main` still has only `add` and `sub`:

```
GET /tasks/task-524904110504/integrations
  { "outcome": "skipped",
    "reason": "no accepted evidence names a commit, so there is nothing to merge",
    "actor": "gamma", "target_branch": "main", "commit_sha": null }

git show main:calc.py   ->  add, sub.  No power().
```

The gate itself is right and says exactly why. The problem is that **the flow cannot clear it.**
Integration needs *accepted* evidence; `alpha`'s `ev-e735dfc4db23` was `review_state: awaiting` and
stayed there, because accepting evidence needs `can_accept_evidence`, which is `false` on every
agent a project creates. So the reviewer the flow itself resolved could approve the *task* and could
never accept the *evidence* — the one step between an approved task and merged work is the one step
no participant in a default flow is able to take.

The operator is not exactly uninformed — `latest_integration.outcome` is on the task — but the
headline says `approved`, and a flow with `stop_when_queue_empties` will happily drain and stop
having merged nothing.

**Three shapes, none of them obviously right, which is why this is a decision and not a fix:**

1. a flow-resolved reviewer is granted `can_accept_evidence` for the task it was resolved for —
   narrow, but it makes implicit a grant the product deliberately made explicit;
2. approving a task with unaccepted evidence is *refused*, the way the author/reviewer gate refuses
   — loud, but it wedges every project that has not turned the grant on;
3. nothing changes in the machinery and the flow *says* it: an approved-but-unmerged task is
   surfaced as a stall, the way an unstaffable review already is.

Related but not the same: **F88** fixed the sibling capability `can_read_checkpoints` and quotes
`api/v1/agents.py` on `can_accept_evidence` having once been "enforced everywhere and grantable
nowhere". It is grantable now. What is new here is that the flow's own reviewer ladder never grants
it, so the automation cannot finish what it started.

### F122, proved from the other side: the missing step is exactly one operator action

Driven immediately after, on the same task, with no agent turn:

```
POST /project/spec/evidence/ev-e735dfc4db23/decision  {"decision":"accepted", ...}
  -> review_state: "accepted", latest_review.actor_kind: "operator"

GET  /tasks/task-524904110504/integration-preview
  -> will_merge: true, targets: [2da8dc9ad076 on agentweave/task/task-524904110504, ...]

POST /tasks/task-524904110504/integrations/retry
  -> outcome "merged", commit 2da8dc9ad076 -> main

git log --oneline main
  bf6f1d7 Integrate approved work 2da8dc9ad076
  2da8dc9 Auto-snapshot: alpha's turn on task-524904110504
  2bdfb0e seed
git show main:calc.py   ->  add, sub, power.
```

Nothing else changed. The task had been `approved` for eight minutes with `will_merge: false`;
accepting one piece of evidence flipped the preview and the retry merged. So F122 is not a broken
integration path — **the integration path is correct and complete**, and the gap is precisely that
no participant in a default flow can perform the one operator action that opens it.

## Row 17 INTEGRATION — driven end to end, and it held

The same sequence covers row 17, which had not been driven on this branch. Beyond the merge itself:

- the *second* target, `HEAD` — gamma's detached review checkout, pointing at the same commit — was
  attempted and **skipped** with `"2da8dc9ad076 is already in main; there was nothing to merge"`
  rather than merged twice;
- `integration-preview` before the accept said `will_merge: false` with the same sentence the
  skipped integration later recorded, so the operator could have predicted the outcome without
  attempting it;
- the refusal on a `completed` task (*"only an approved task has work to integrate"*) and the
  refusal with no accepted evidence are two different sentences for two different causes.

**One blemish, noted not filed:** the merged integration row reads `actor_kind: "operator"` with
`actor: ""`. Same shape as F120 one table over — the record knows what kind of actor it was and does
not name it. Not raised as its own finding because there is exactly one operator per instance today,
so the empty string is unambiguous rather than wrong.

**F75's fix confirmed live.** `gamma`, reviewing `alpha`'s work, recorded its own
`manual_observation` (`ev-1cb189450dc8`) against `FR-1` with the *same digest* as the author's
`implementation` evidence, and it was **accepted, not refused as a duplicate** — while `alpha`
re-recording its own claim in a later turn *was* refused. The rule distinguishes a second author
claim from an independent confirmation, which is exactly what F75 asked for.

## Row 19 RESILIENCE, two of three parts — driven, and both held

**Two concurrent triggers for one agent.** Two `POST .../agent/trigger` calls for `alpha` fired from
two threads, 19 ms apart, into two different conversations. Neither raced, neither was lost, and
each was told something *different and correct*:

```
trigger A  status "queued"  waiting_reason: "an older conversation's queued input is being
                                             delivered first (run run-6a2a3219b785)"
trigger B  status "queued"  waiting_reason: "agent is already running"
```

Both entries then ran, in arrival order, in their own runs:

```
entry-30b613696046  arrived 16:07:32.951  delivered 16:07:33.379  run-6a2a3219b785  ended :43.055
entry-3fbc4defcd68  arrived 16:07:32.970  delivered 16:07:43.305  run-e18f0ca41828  started :43.306
```

`delivery_attempts: 0`, `abandoned_reason: null` on both. `turn_scheduler`'s per-`(project, agent)`
lock is doing exactly what `SURVEY.md` credits it with, and the *reason* the loser was given names
the run that beat it rather than a generic "busy".

**Stopping a run mid-flight.** `POST .../agent/{name}/stop` eight seconds into a real turn:

```
200 {"success": true, "message": "Stop signal sent to beta (run run-c5fb49f86c77).",
     "status": "stopping"}

runs:        status "stopped", exit_code 2, ended 8.2s after it started
event_logs:  run_stopped  severity "info"  exit_code 2
agents:      beta idle within 4 seconds
queue entry: state "delivered", abandoned_reason null
```

`stopped` is its own status, not `failed`, and the event is `info` rather than an error — which is
the right reading of an operator doing something deliberate. This is the same family as **F94**
(*"kill an agent and the product tells you `exit 4294967295`"*): a deliberate stop is now legible.

**Not driven:** killing the Hub with a run in flight (`run_reconciliation`). Left for a later
iteration — it needs the trial Hub restarted mid-turn, and this iteration's Hub was carrying an
unrelated fix under test.

**A stopped run keeps everything it produced** — settled by repeating the stop at twenty-five
seconds rather than eight, because one run could not distinguish "the stop discarded buffered
output" from "there was nothing yet":

```
run-5bc7ea3b2dcb  started 16:09:59.507  stopped 16:10:24.781  exit_code 2
agent_outputs:    20 rows, first at 16:10:08.046, last at 16:10:23.309
```

The last row landed 1.5 s before the stop took effect, and the transcript is complete up to it. The
earlier eight-second stop's empty transcript was therefore honest: this model's first output row
arrives 8.0-8.5 s after start on this machine, every time it was measured today, so that run had
genuinely produced nothing. **No finding** — recorded because an empty transcript after a stop looks
exactly like discarded output, and the next reader deserves the measurement rather than the worry.

## Row 19 RESILIENCE, the third part — the Hub killed with a run in flight. It held.

Driven 2026-08-29 17:45-17:50 on 8011 against this branch, `scripts/drive/t_row19_crash.py`. This
is the half the paragraph above left open. Two specimens, one per agent, both hard kills
(`Stop-Process -Force`, so `lifespan`'s `terminate_all_active_runs()` never ran — a crash, not a
bounce).

**Nothing is orphaned, and that is measured rather than assumed.** The `Run` row's `pid` is the
CLI itself, and it dies with its Hub:

```
hub pids 28980 (py.exe launcher) -> 22604 (python.exe, uvicorn)
  22604 -> 25712 OpenConsole.exe      after Stop-Process -Force: gone
  22604 -> 19688 claude.exe           after Stop-Process -Force: gone   <- runs.pid = 19688
```

This matters because `reconcile_interrupted_runs` **skips** any run whose `pid_alive(run.pid)` is
still true. Had the ConPTY child survived its parent — which is the ordinary Windows expectation,
nothing reaps a grandchild — every crashed run would have stayed `running` forever and wedged its
agent, since `POST /agent/trigger` refuses while a run is in progress. The pseudoconsole closing is
what makes the reconciler's precondition true here, so the good outcome rests on a property of
ConPTY, not on anything the reconciler does.

**The restart tells the truth and then does something about it.** Specimen one, `alpha`, killed 20 s
into a turn:

```
16:46:40.653  run_triggered     run-7b910e688f68
16:46:40.757  run_started
   ~16:47:00   Stop-Process -Force on the Hub
16:47:00.720  run_interrupted   pid 20504, returned_entry_ids ["entry-68dd93ce09b2"],
                                abandoned_entry_ids []          severity warn
16:47:04.115  run_triggered     run-179b80185f46   session_mode "resume"
16:47:04.135  queue_entry_delivered  entry-68dd93ce09b2  <- the SAME entry, redelivered
16:47:30.420  run_completed     exit_code 0
```

Four seconds from the Hub answering again to the operator's message being back in a live turn, with
no operator action at all. That is `_schedule_or_defer`'s deferred re-drain firing off the first
request the restarted Hub served — the path whose docstring says it exists because
`reconcile_interrupted_runs` runs before the Hub knows its own address. It works.

Specimen two, `beta`, reproduced it: `run-63d92186c7b6` -> `interrupted` at restart, `run-5aed9335cb5a`
started within seconds on the same input.

**The redelivered agent is told it is a redelivery.** From the resumed run's own transcript:

> *"The note says 'delivery attempt 2; an earlier attempt was cut off before it finished' — so this
> appears to be something that was interrupted and needs to be completed."*

`inbound_queue.py:116-119` composes that line, and the agent read it and acted on it. A redelivery
that looked like a first delivery would make the agent redo completed side effects silently.

**Accounting records the crash rather than dropping it.** `unavailable_turns` went 2 -> 3 (alpha's
0 -> 1) across the crash, so the interrupted run has exactly one outcome and it is `unavailable`,
not a zero and not an absence — which is `usage-accounting`'s stated rule, reached by the crash
path.

**A trigger arriving during the recovery is queued, not lost or refused:**

```
POST /agent/trigger  200  {"status": "queued", "run_id": null,
                           "waiting_reason": "agent is already running"}
```

It ran as `run-ec7005e6f593` the moment the resumed run ended.

**No finding. Two things worth knowing anyway.**

- **Three crashes withdraw an operator's message.** `return_run_entries` counts a delivery attempt
  per interruption; at `RESUME_RETRY_LIMIT = 2` the conversation's `provider_session_id` is cleared
  (the agent loses its provider-side context) and at `DELIVERY_ATTEMPT_LIMIT = 3` the entry is
  `withdrawn` with `abandoned_reason` set. Both constants carry a written rationale that names this
  case explicitly ("Fewer, and a Hub restart could discard an operator's message"), so this is a
  decided trade-off, not a defect — but an operator whose Hub crash-loops three times loses the
  message, and the only breadcrumb is `delivered_in_run_id` on a withdrawn entry.
- **`pid_alive` is a pid-existence check, not pid+identity**, as its own docstring says. A Hub down
  long enough for the OS to recycle the pid reads the run as still alive and never reconciles it.
  Not reproducible on demand and already written down at `pty_runner.py:142-147`; recorded here
  because this row is the one place the consequence is visible — the run stays `running` and its
  agent is wedged with no way back except another restart.

**What is not covered by this row even now:** a Hub killed while a *permission card* or a *question*
is open (the reconciler calls `expire_pending_for_run`, which this drive never exercised because
both specimens ran in default posture), and a crash while a run holds a task (`divergences_to_evaluate`
is only populated for `run.task_id`, and neither specimen was task-bound).

## Row 19 x row 14 — the Hub killed while an operator's decision is on screen. It held.

The crash drive above ran both specimens in default posture, so `reconcile_interrupted_runs`'
call to `expire_pending_for_run` was never reached. Its comment is the reason it exists — *"a Hub
bounced while an operator decision was on screen leaves a row nobody will ever poll again"* — so
this drives that, `scripts/drive/t_row19_crash_card.py`, 2026-08-29 17:54.

```
17:54:50  card perm-acc79b61af1d  status "pending"   run-2f56b98d86f3  tool Write
   ~:58   Stop-Process -Force on the Hub
17:55:0x  restart
          card perm-acc79b61af1d  status "expired"   decided_at null   decided_by null
          run-2f56b98d86f3        status "interrupted"
          GET /permission-requests  -> the card is gone from the operator's list
POST .../perm-acc79b61af1d/decide {"allow": true}
   409 {"detail": "this request was already expired; the run has moved on"}
17:55:10  perm-3d4bae2c9135  a FRESH card, run-67f5dee85c34, same Write
          {"allow": true} -> 200, and card_crash_note2.txt exists in gamma's worktree 2s later
17:55:15  gamma idle
```

Twenty seconds from crash to the operator being asked the same question again by a live run, and
the stale card cannot be answered into a void — the `409` names *expired* rather than the generic
"already decided", so the operator can tell "I was too slow" from "the Hub died under me".

**`decided_at` is null on an expired card, and that is right.** Nobody decided it. It matters
because a client that asks "is this card still open?" with `!decided_at` reads an expired card as
answerable — **this harness did exactly that on its first run**, and the mistake was invisible
because the list route hides expired rows by default (`pending_only`). Checked against the UI
rather than left as a worry: `permissions.ts` types `status` as the four-value union,
`PermissionRequestCard.tsx:66` selects on `status === 'pending' || status === 'expired'` and
renders the expired one `is-stale` with a dismiss button and no answer buttons. The UI reads the
field that carries the answer. **No finding.**

**A harness bug that would have shipped a false verdict, recorded because it is the more useful
half of this row.** The first run of `t_row19_crash_card.py` posted `{"decision": "allow"}` — the
field is `allow`, a bool — got a `422`, and scored it as *"deciding a dead card is refused"*. It
proved only that the harness could not spell the request. Worse, the same typo then failed to
answer the **fresh** card, which expired 120 s later (`permission_denied`: *"no operator answered
within 120s, so this was not approved"*), and the run completed without writing the file — which
the harness scored as *"the work completed after the crash"* because it was watching the agent go
idle rather than watching the file appear. Two green verdicts, both false, from one typo in a
request body. The re-run asserts the artefact (`os.path.exists`) and the exact status code
(`== 409`, not `>= 300`), which is what a verdict has to do to be worth reading.

That is F116's own lesson arriving from the other side: **F116 forbade extras so a misspelled
field is named rather than absorbed, and here the named refusal was still misread by the client
that caused it.** The `422` did everything right. A drive that only checks "did it refuse?" learns
nothing from a good refusal.

## Row 19 x row 8 — three crashes on one task-bound run: the input is abandoned, and the operator is told

`reconcile_interrupted_runs` has a branch nothing had ever reached:

```python
if run.task_id and not returned_entry_ids:
    divergences_to_evaluate.append(run.id)
```

`returned_entry_ids` is empty only when `return_run_entries` gave up, which is
`DELIVERY_ATTEMPT_LIMIT = 3` — so the branch needs the Hub killed **three times on the same
input**. That is also exactly the case the crash drive above filed as *"an operator whose Hub
crash-loops three times loses the message"*, so `scripts/drive/t_row19_crash_task.py` drives both
at once: a task assigned to `beta`, a run bound to it, and three hard kills in four minutes.

```
entry-06b6c75505dc  task-d1ae1dfe5124  delivered, attempts 0
crash 1 -> state "queued",     attempts 1, provider_session_id 7824ae64-… kept
crash 2 -> state "queued",     attempts 2, provider_session_id NULL      <- RESUME_RETRY_LIMIT
crash 3 -> state "withdrawn",  attempts 3, "delivery failed 3 times; the Hub stopped retrying"
```

Every constant behaved as its comment says, including the middle one nobody would notice: at the
second failure the conversation's provider session is dropped, so the third delivery starts fresh
rather than re-killing the runtime on a session that cannot be resumed.

**The message is gone, and nothing about that is silent.** After the third crash:

| Surface | What it says |
|---|---|
| `GET /tasks/{id}` | `status: "in_progress"`, `has_open_divergence: true` |
| `GET /tasks/divergences/recent` | `div-6c07fa8009fb`, `run_exit_status: "interrupted"`, `task_status_at_end: "in_progress"`, `outcome: "surfaced"` |
| `GET /queue/beta` | the entry, `state: "withdrawn"`, with its `abandoned_reason` |
| `GET /agent/beta/chat/{conv}` | the operator's own message, `delivery_state: "abandoned"`, reason attached |
| `AgentTimeline.tsx:787-808` | renders that as a red **"not delivered"** chip *with the reason beside it* |

The task does not silently sit in `in_progress` looking like work in flight: the divergence is
raised on the crash path, by the same `evaluate_run_end` the ordinary end-of-turn path uses. This
is the S6-adjacent worry answered in the product's favour.

**Two measurements taken because the first reading of them was wrong.**

*Output produced before a crash is not discarded.* The three abandoned runs had **zero** stored
output rows each, next to a completed run of the same work with sixteen — which reads exactly like
a crash eating the transcript. It is not. Killed deliberately *after* rows existed:

```
run-1036804a218c  4 rows at t+9.1s (thinking, text, tool_use, tool_result)
  Stop-Process -Force
  rows immediately after the kill: 4
  rows after the restart:          4
```

`record_agent_output` commits per event, and a committed row survives its Hub. The zero-row runs
were killed **before this model's first output row**, which lands 8.0-8.5 s after start on this
machine — measured twice today, once for the stop half of row 19 and once here.

*An interrupted run's `ended_at` is the restart time, not the crash time.* `reconcile_interrupted_runs`
sets `run.ended_at = now()`, and "now" is whenever the Hub came back:

```
started_at 17:00:28.66   killed ~17:00:37.6   ended_at 17:00:42.29
lived ~9 s; the row claims 13.6 s
```

That is what made the zero-row runs look impossible — their durations are inflated by however long
the Hub was down. **Not a finding today, because `ended_at` is on no response schema and no UI
component reads it** (checked, not assumed). It becomes one the moment a run duration is surfaced:
a Hub that crashes at midnight and restarts at nine reports a nine-hour run. Whoever exposes it
should bound it by the last `agent_outputs` row for the run, which is the only honest upper bound
the Hub still holds.

## Row 19 x row 13 — the Hub killed while `ask_user` is blocking. Nothing expires the question, and nothing needs to.

The card half of this is handled by an explicit pass (`expire_pending_for_run`). Questions get
none: `run_reconciliation.py` does not mention them. That asymmetry is what this drove
(`scripts/drive/t_row19_crash_question.py`), expecting to find a question left claiming an agent
was waiting on it forever. It is not there, and the reason is worth writing down.

```
17:03:16  run-641a10f7c182 starts, calls ask_user, blocks
17:03:27  q-3b7e6cc781f2  "Which colour should the badge be?"  asker_waiting true
   ~:33   Stop-Process -Force on the Hub
17:03:36  restart -> run-641a10f7c182 status "interrupted"
          q-3b7e6cc781f2  still there, still unanswered, asker_waiting FALSE
17:03:40  run-93067b1a17d5, the redelivered turn, asks again
17:03:48  q-7bf5289f85aa  asker_waiting true
          answered "blue" -> the run finished four seconds later
```

`asker_waiting` is derived per read — `created_by_run_id not in (runs whose status != "running")`
(`questions.py:249-270`) — so the reconciler flipping the run to `interrupted` is *itself* the
thing that makes every question that run asked go inert. A derived field cannot be forgotten by a
new code path the way an explicit expiry pass can, which is why the asymmetry is a design rather
than an omission. Two open questions, one dead and one live, are distinguishable by the field
alone.

**And the surfaces read it.** Not assumed — read:

- `QuestionsPanel.tsx:150-151` partitions the unanswered list on `blocking && stillWaiting`, with
  the comment *"asserting it collectively while ignoring it individually is the dishonest half"*:
  the dead question drops out from under the "agents are waiting" banner instead of inflating it.
- `AgentQuestionCard.tsx:70,86-95` renders a **"no longer waiting"** chip with the hover text
  *"The run that asked this has ended. Answering now would reach it as a new message, not as the
  answer it was waiting for."*

Answering the dead one is still allowed (`200`), and that is the right call — the row keeps the
operator's answer, and the reply reaches the agent as an ordinary message rather than vanishing.
The product's honesty here is in labelling it, not in forbidding it.

**No finding.** Recorded because the asymmetry looks like a bug from the code alone: one kind of
operator-facing block is expired explicitly on the crash path and the other is not mentioned. The
answer is that one is stored state and the other is computed from the run, and only driving it
shows which.

## Row 19 x row 11 — a crash mid-firing, and F123

`reconcile_stale_job_runs` is the second half of the startup pass and nothing had driven it either.
Driven 2026-08-29 18:06, `scripts/drive/t_row19_crash_job.py`: a job fired by hand, the Hub killed
eight seconds in, restarted.

**The reconciliation itself is exactly right.** No `JobRun` is left `in_progress`, the firing is
`failed`, and the summary is one an operator can act on rather than a stack trace:

```
run-5d31c6858841  status "failed"  trigger "manual"  tick_count 1
error_summary: "Reconciled on Hub start: no live run behind this firing"
```

It reaches that by the `conversation_id` correlation the two tables share by convention rather
than by constraint — `JobRun` and `Run` have no foreign key — and the correlation held.

## F123 (C, open) — a crashed firing reads `failed` forever, including after the Hub itself retried it and the work succeeded

Same specimen, sixteen seconds later:

```
job_runs   run-5d31c6858841  conv-eb547b1f68eb  status "failed"
runs       run-5fe90fc12c65  conv-eb547b1f68eb  status "interrupted"   (the crash)
           run-bf3961c3ee7d  conv-eb547b1f68eb  status "completed"     (the retry, 17:07:10)
queue      entry-7f110f6fcc1c  origin_type "job"  state "delivered"  attempts 1
```

The Hub's own crash recovery put the job's message back, delivered it to a new run **on the same
conversation**, and that run did the work and completed. The job's history does not say so. It
says `failed`, and there is no second row for the retry — so the operator's only view of whether
this job's work happened reports the opposite of what happened.

**Mechanism, and it is one line.** `scheduler.finalize_job_run_for_conversation` selects
`JobRun.conversation_id == … AND JobRun.status == "in_progress"` (`scheduler.py:1569-1574`).
Reconciliation has already moved this row to `failed`, so the completing retry matches nothing and
finalisation is a no-op. Every part is individually defensible: the firing *did* fail, and a
terminal row should not be silently rewritten by a later run.

**Not fixed, because the fix is a decision about what a `JobRun` is**, and the same table already
has **F121** open against it (one firing, two `JobRun` rows; the badge counts turns not firings).
The three shapes, costed:

1. *Let the retry finalise the failed row* — smallest diff (drop the `in_progress` filter, or
   widen it to `("in_progress", "failed")`), but it makes a terminal status mutable and erases the
   fact that a crash happened at all.
2. *Append a `JobRun` for the retry* — the history reads firing → failed → retried → completed,
   which is what happened. But the retry is not a firing: `run_count`, `last_run` and the badge all
   count these rows, so this inflates every one of them, which is precisely F121's complaint.
3. *Leave the row and mark the job* — a `continuity_warning`-style field saying "the last firing
   was interrupted; its work was retried and completed". `JobResponse` already carries
   `continuity_warning`, so the surface exists.

My reading is (3), because it is the only one that keeps the firing's record honest *and* tells the
operator the work happened — but F121 and this should be decided together rather than one at a
time, since both are about the same confusion between a firing, a turn, and the work.

Severity **C**: no work is lost, and the operator can find the truth in the agent's conversation.
It is the *job* view that is wrong, and that is the view a job exists to be read from.

---

## Row 11 LOOPS, second half — a loop fires, works, stalls, drains and stops, and stays stopped

Driven 2026-08-29 on 8011 against this branch, in `drive-wt-0829` (`proj-dc4d43543bea`), one Haiku
agent. Two harnesses: `t_row11_loop.py` (the queue-drained ending) and `t_row11_loop_quiet.py` (the
stop-time ending, plus the quiet window). **19/21 and 12/12** — and both of the first harness's two
BADs are a mis-specified assertion of mine, not a defect; the measurement behind them is real and
is recorded under F121 below.

**The whole ladder, live.** `POST /jobs` with `stop_when_queue_empties` and two `initial_tasks`
created the job, the `Loop` row and both queue entries in one call, and the response reported
`queue: {"pending": 2}` — the seeded queue, not the empty one an earlier version of that route
computed before seeding. One manual fire, then the cron:

```
17:18:15  manual     completed   task A pending -> in_progress -> completed
17:19:00  scheduled  completed   task B pending -> in_progress -> completed
17:20:00  scheduled  skipped     tick_count 2   "task task-c7a2f0dbb4c5 has no recorded evidence…"
17:22:00  scheduled  skipped                    "loop queue is empty"   -> ending
```

Both artefacts exist with exactly the content asked for, each in its own task checkout
(`.agentweave/tasks/<task-id>/loop_r11_{a,b}.txt`, `ALPHAONE` / `ALPHATWO`), on its own
`agentweave/task/<task-id>` branch, and `main` was untouched throughout. **One task at a time**
held: the second was never claimed while the first ran.

**Stalled is not finished, and it says why.** With both tasks `completed` and nothing approved, the
loop ticked twice more and stopped nothing. The skipped row carries a reason an operator can act
on rather than a status word:

> *task task-c7a2f0dbb4c5 has no recorded evidence, so there is no commit to review. Evidence
> naming a commit is what a review turn is given. Until the work that finished this task is
> recorded as evidence naming a commit, no reviewer can be given anything to look at.*

and the second identical tick **incremented `tick_count` to 2 on the same row** instead of writing
a duplicate, which is `loop-notices-and-reacts` design D6 working exactly as its docstring argues.

**The four ending facts, both ways.** Approving both tasks drained the queue and the next tick
ended the loop: `ending_state: "completed"`, `stop_reason: "loop queue is empty"`, `stopped_at`
populated, `job.enabled` false. A second loop created with a `stop_at` **two minutes in the past**
ended on its first firing with `ending_state: "stopped"` — not `completed`, because its queue still
held open work — `stop_reason` naming the time, and **no agent was spawned at all**: the one queued
task was still `pending` afterwards. The stop condition is checked before the spawn, and
`POST /jobs/{id}/run` on it answered `409 loop stop time reached (…)` rather than firing.

**Stopped is true, not merely reported** — which is the property `loop_ending.py`'s own docstring
records going wrong once (a loop that read `stopped` at 23:09 and ran twelve more real turns).
Watched for 160 seconds — three cron ticks — after the time-stop: `run_count` stayed 0, the history
stayed at one row, the agent stayed idle, and the outstanding task was never picked up.

**Three ways to restart an ended loop, all refused, each naming the remedy.**

```
PATCH /jobs/{id} {"enabled": true}
  409 {"code": "loop_ended", "message": "This loop has ended (loop queue is empty) at
       2026-08-29T17:22:00.049752+00:00 and cannot be restarted: its queue is closed, so the next
       firing would stop it again within the minute. Create a new loop with the work instead."}
  ...and it did not half-apply: the job was still disabled afterwards.

POST /jobs/{id}/run
  400 "Job is disabled"

POST /tasks {"loop_id": "<the ended loop>"}
  403 {"code": "loop_stopped", … "offered_task": {…}}   — the operator is refused too, and the
      submitted task is echoed back so it can be resubmitted as a new loop's initial_tasks.
```

Every one of those quotes a real `stopped_at`; the `"an unknown time"` fallback that F13's write-up
found live did not appear once. Two of the three were re-run against the **time-stopped** loop and
answered identically, quoting its own reason and time — so "ended" is one state with one set of
consequences, not two that happen to look alike. (The third differs only in *where* it is caught:
`POST /run` on the time-stopped loop is what ended it, so it answered `409 loop stop time reached`
rather than the `400 Job is disabled` a second press would get.)

## F124 (B) — a loop's work can never reach the main branch, and the card offers a retry that cannot succeed

**Status:** open, filed not fixed. Found by driving row 11's second half, 2026-08-29.

Both loop tasks above were approved by the operator. `main` never moved:

```
git ls-tree main --name-only   ->  README.md, calc.py      (no loop_r11_a.txt, no loop_r11_b.txt)

GET /tasks/task-d3c48be292dc
  "latest_integration": {"outcome": "skipped", "commit_sha": null,
                         "reason": "no accepted evidence names a commit, so there is nothing to merge"}
```

So far this is `task_integration.py` behaving exactly as designed and saying so on the task
response, which `TaskIntegrationNote.tsx` renders. **The defect is that for a loop this reason is
permanent, and the module's own comment says it should not be:**

> *Why nothing was merged, in words that name the thing the operator would change. Each is a state
> of the world rather than an error: none of them means anything went wrong…*

`_commits_for_task` resolves what to merge through `TaskRequirementLink → RequirementEvidence
(accepted) → EvidenceFootprint` (`task_integration.py:143-167`). A loop's tasks come from
`create_loop`'s `initial_tasks`, and nothing requires — or, in the ordinary case, supplies — a
`requirement_ids`. With no requirement link there is no requirement for `record_evidence` to name,
so the agent cannot record evidence even if it tries; with no evidence there is nothing to accept;
with nothing accepted there is no commit; so `NOTHING_TO_MERGE` is not a state of the world that
could change, it is the only state this task can ever be in.

The loop's own stall reason had already said the same thing from the other side — *"no reviewer can
be given anything to look at"* — and it is right, for the same reason.

**The visible half, measured twice.** `TaskIntegrationNote` offers **"Try again"** for every
non-merged outcome except `no main branch set`. Pressed here, it answers `200` and appends a second
identical row:

```
POST /tasks/task-d3c48be292dc/integrations/retry   -> 200
  tint-ee8b204b8a30  skipped  "no accepted evidence names a commit…"   17:21:03
  tint-7e8f8c3a45a4  skipped  "no accepted evidence names a commit…"   17:23:46   <- the retry
GET  /tasks/task-d3c48be292dc/integration-preview  -> {"will_merge": false, "targets": []}
```

`integration-preview` **already knows** the retry cannot work (`will_merge: false`, `targets: []`)
and the card does not ask it. This is the same shape as the bug the file's own comment records
fixing once before — a remediation stated, followed, and provably a no-op — arriving on the button
that replaced it.

**Not F122.** F122's task had evidence sitting at `review_state: awaiting`, so a real remedy
existed (accept it) and the complaint was that a *flow* cannot reach it. Here no evidence can exist
at all, the approver is the operator, and no flow is involved. A fix for F122's accept step would
not touch this.

**What it costs.** A loop is the product's answer to "shorter dev loops that keep developing". Every
one of them accumulates approved work on per-task branches that no operator action will ever merge,
while the board says `approved` — and the one control offered for it appends a row each time it is
pressed.

**Three shapes, none of them chosen here.**

1. *Let a task's own branch tip be a merge source when it has no requirement links.* Cheapest to
   state, and it breaks the module's first rule ("merge a commit, never a branch") in the one place
   that rule was written for — a task branch carries only that task's work, so it is arguably safe,
   but it makes approval merge unreviewed work.
2. *Make the loop path able to produce evidence* — a synthetic requirement per loop, or evidence
   that names a task rather than a requirement. Honest, and the largest change: `RequirementEvidence`
   is keyed on a requirement everywhere.
3. *Say so instead of offering a retry.* Smallest true fix: `TaskIntegrationNote` asks
   `integration-preview`, and when `will_merge` is false for a reason retrying cannot change, states
   what would have to happen rather than offering a button. Fixes what the operator sees; leaves the
   work unmergeable.

Recommendation: **(3) now, (2) as its own change.** (1) trades a governance property for
convenience and should not be taken quietly.

## F121, strengthened — the same word under-counts on a loop and over-counts on a flow

F121 recorded that a flow writes one `JobRun` per dispatched turn, so `JobCard.tsx`'s
`{job.run_count} runs` reads 4 for two firings. The loop drive measured the divergence running the
other way:

```
job history:  4 rows   (2 completed, 2 skipped — one of them tick_count 2, so 5 ticks)
job.run_count: 2
```

A skipped firing does not increment `run_count`, which is consistent with the F25 comment's
definition (*"firings that actually ran"*) and inconsistent with the card's own word. So the badge
under-reports a stalled loop and over-reports a wide flow, and neither is a database defect. This
does not change F121's status; it removes the reading that it is a flow-only quirk.

*(The two `[BAD]` verdicts in `t_row11_loop.py` are this measurement. The assertion as written —
`run_count == len(history)` — asserts a thing the design never promised; it is kept, failing, with
this note, because deleting it would delete the measurement.)*

## F125 (C) — a task's title cannot be changed by anybody, and F116's fix is what made that visible

**Status:** open, filed not fixed. Small.

Found by accident: the quiet harness tried to rename an orphaned task and got

```
PATCH /projects/{p}/tasks/{id}  {"title": "Write loop_r11_c.txt (orphaned)"}
  422 [{"type": "extra_forbidden", "loc": ["body", "title"],
        "msg": "Extra inputs are not permitted"}]
```

`TaskUpdate` (`hub/hub/schemas/tasks.py:120`) has no `title` field, and `TaskDetailDrawer.tsx`
renders `task.title` into an `<h2>` with no editor anywhere. So a task is named once, at creation,
forever — including a task an agent named, and including one whose title has gone stale because the
work moved. `description` is editable; the line the board actually shows is not.

Whether that is a gap or a deliberate contract is an operator call, which is why this is filed
rather than fixed.

**What is not in doubt is the 422.** This is F116's own change firing on a field nobody wrote a test
for: before the `RequestModel` base landed, this PATCH answered `200` with the title unchanged —
F117's exact shape, on the field most likely to be edited by hand. The first thing the strictness
caught in the wild, it caught within a day, in a harness that was not looking for it.

## F126 (B) — a spent checkpoint can be cut over again, and the second press mints a second successor that does the work a second time

**Status:** open, filed not fixed (iteration 8, `t_row15_cutover.py`, the one `[BAD]` of 36).

`POST /projects/{p}/checkpoints/{id}/cutover` has no guard against being called twice on the same
checkpoint. Driven live against `ckpt-5acb5c671217`:

```
POST .../checkpoints/ckpt-5acb5c671217/cutover   200  successor conv-b21d999ecaf0  entry-ed1d74dcddd7
POST .../checkpoints/ckpt-5acb5c671217/cutover   200  successor conv-c1799d084153  entry-2b8b17f41030
```

Both successors are `lifecycle: open`, `origin: handoff`, and carry the **same** derived title
(`"Continued: Create a file called CHECKPOINT_A.txt …"`). Two conversations, indistinguishable in
the navigation tree, both claiming to continue the one archived predecessor.

**It is not merely a duplicate row — the duplicate did real, billed work.** I called `continue`
exactly once, on the first successor. The queue afterwards:

```
entry-ed1d74dcddd7  checkpoint  delivered  conv-b21d999ecaf0  run-cdad300b6180
entry-2b8b17f41030  checkpoint  delivered  conv-c1799d084153  run-99ba2ab65297
```

Two runs. Two Haiku turns. The second successor's transcript reads *"Good! The files already
exist"* and then goes on to re-verify and re-close the same task — so the second turn was not a
no-op, it was a whole turn spent rediscovering that there was nothing to do.

### Mechanism

`cut_over` (`hub/hub/checkpoint_cutover.py:63`) has exactly two refusals:

1. `checkpoint.status != "ready"` — unchanged by a cutover, so a spent checkpoint still passes.
2. `archivable(db, predecessor)` — whose **first line** is
   `if conversation.lifecycle == "archived": return None` (`hub/hub/conversations.py:374`).

That early return is right for what `archivable` is for: archiving an archived conversation is a
no-op, not an error. It is the wrong question to ask here. Nothing anywhere records that this
checkpoint has already been handed to a successor — `Checkpoint` has no consumed/spent column, and
the route does not look for an existing `origin: handoff` conversation.

### Why the UI has not shown this

The Hub UI cannot reach it *from one tab*. `checkpointOperationStore.writeCheckpoint`
(`hub/ui/src/store/checkpointOperationStore.ts:34`) holds an `inFlight` map keyed by
`projectId:conversationId` and does take-then-cutover as one act, so a double-click within a tab
coalesces. That guard is **client-side and per-tab**: a second browser tab, a reload between the
201 and the cutover, a retried request after a network timeout, or any non-UI client gets two
successors. The Hub's own standard elsewhere is a server-side claim — `take_checkpoint` holds
`_checkpoint_claims` (`hub/hub/api/v1/checkpoints.py:27`) for exactly this reason on the *cheaper*
half of the pair. Generation is guarded and idempotent-ish; cutover is unguarded and durable.

Related, and worth deciding at the same time: the banner that offers a cutover in the UI filters on
`checkpoint.trigger === 'context_pressure'` (`AgentOutputPanel.tsx:485`), so a checkpoint the
operator generated on purpose is never offered one. The operator-triggered path reaches cutover only
through `writeCheckpoint`, which generates its own.

### Shapes

1. **Smallest.** Refuse a second cutover: 409 when a conversation already exists whose
   `origin == "handoff"` and whose queue entry names this checkpoint. Costs one query, names the
   state, and is the same shape as `_checkpoint_claims`.
2. **Honest.** Give `Checkpoint` a `cut_over_to_conversation_id`, set inside the same commit as the
   successor, and refuse when it is set. The row then answers *"where did this checkpoint go"*,
   which nothing can answer today, and the refusal can name the successor rather than a generic
   conflict. One migration.
3. **Do nothing, deliberately** — argue that a second cutover is a legitimate fork. It is not:
   nothing forks the *predecessor*, both successors carry the same `lineage_id`, and the second one
   is billed for rediscovering that its work is done.

Recommendation: (2). It costs a migration and answers a question the operator can otherwise only
answer by reading queue entries, and (1) is a subset of it.

### What held around it — row 15's cutover leg, driven end to end

35 of 36 verdicts. Worth recording because none of this had been driven live before:

| | |
|---|---|
| Refusal with no checkpoint runner | exactly **409**, naming project settings — no silent fallback onto another agent's runner |
| A partial `PUT /settings` | left `hop_budget` and `checkpoint_mode` untouched (the `exclude_unset` merge doing its job) |
| Generation | **201** in 17s on Haiku, `status: ready`, `probe_status: passed`, no generation error |
| `files_changed` | `["CHECKPOINT_A.txt"]` — the file the turn actually wrote |
| The body | carried the deferred next action (`RELAYTWO`) and a citation quoting the line it came from |
| `GET /checkpoints/{id}/rendered` | 2,035 chars, envelope + body, honest about the task list not being conversation-scoped |
| Cutover | predecessor `archived`, successor `open`/`handoff`, title derived not regenerated, queue entry `origin_type: checkpoint` addressed to the successor and framed with the preamble |
| **The relay** | the predecessor was told **not** to write `CHECKPOINT_B.txt`; after `continue`, the successor wrote it, containing `RELAYTWO`. The handover carried the work across, end to end, and the file on disk is the proof. |


## Row 11 LOOPS, third pass — the three stall shapes that had never been driven, and D6's coalescing

`t_row11_stalls.py`, **28 of 28 verdicts held.** Nothing under `hub/` changed; the Hub on 8011
(started 18:06:50, newest `hub/` commit 17:04) served this branch's code throughout.

`_loop_stall_reason` has four branches and iteration 7 drove exactly one of them — the queue whose
tasks are all `completed` and unapproved. The other three are now driven, against a live Hub, with
the **exact** sentence asserted each time rather than a substring:

| shape | set up as | the Hub said |
|---|---|---|
| gate, still workable | A `blocked`, B `pending` depending on A | `loop queue is stalled: 1 still awaiting a prerequisite's approval` |
| gate, permanent | A `rejected`, B still depending on A | `loop queue is stalled: 1 gated on a rejected prerequisite that will not clear on its own` |
| no gate, waiting on a person | dependency removed, B `blocked` | `loop queue is stalled: no claimable task among 1 open (1 blocked)` |

Each arrived as a **409** from `POST /jobs/{id}/run`, and each left the loop alive: `ending_state`
null, `job.enabled` true, `next_run` still set. Skipped is not stopped, and the product means it.
Three further facts came out of the same drive, none of them previously driven:

* **The dependency edge is operator-reachable and symmetric.** `POST /tasks/{B}/dependencies`
  answered 201, and afterwards B's response carried `prerequisites: [A]` while A's carried
  `dependents: [B]` — the graph reads from both ends without a second request.
* **Design D6's coalescing works.** Firing the same stall twice appended **no** second row: the
  existing `JobRun` went `tick_count` 1 → 2 with `fired_at` frozen at the first refusal, and no
  second `job_run_skipped` event was persisted. Change the shape (reject the prerequisite) and a
  **new** row appears while the old one's count stays at 2 rather than being resurrected. A stall
  that lasts an hour therefore leaves one readable row, not twelve identical ones.
* **Zero spend.** Every `JobRun` this loop ever wrote is a `skipped` stall with a null
  `session_id`, and the loop's agent never left `idle`. Four firings, no runner ever touched.

The `blocked` shape needed `blocked_reason` on the PATCH — a 422 that names the field, which is
right. Worth recording only because the first run of the harness omitted it, the task stayed
`in_progress`, and the firing then **claimed it and spent a real turn**. The harness now aborts if
the setup status is not what the shape requires, rather than driving a different scenario than the
one it prints. That accident is what found F127 and F128 below.

One teardown note, not a finding: a loop whose job is merely disabled cannot be archived
(`400 this loop is still running`), because `ending_state` is written only by a firing that meets a
stop condition. The operator's own ending path is `PATCH /jobs/{id}` with `stop_reason`, which
routes through the same `end_loop` a firing uses. Both drive harnesses now tear down that way.

## F127 (B) — pressing Run on a healthy loop whose agent is busy answers 500 "Failed to fire job"

Reproduced deterministically: `t_run_while_busy2.py`, **7 of 7 verdicts held**, against
`proj-dc4d43543bea` on 8011.

`_do_fire_job` has **two** branches that decline a firing and deliberately record nothing:

1. `DECISION_IN_FLIGHT` — every candidate is already being worked. **This is the one F48 fixed.**
   `run_job` re-derives the decision through `_loop_work_is_all_in_flight`
   (`hub/hub/api/v1/jobs.py:1139`) and answers 409: *"Every task on this loop's queue is already
   being worked. Nothing was started, and nothing is wrong."*
2. the **busy guard** — `_loop_flow_busy_reason` (`hub/hub/scheduler.py:2083`), the loop's agent is
   mid-turn and nobody else is free. It returns `False` before a `JobRun` is even constructed.

F48's re-derivation cannot see the second, because it asks a different question:
`_loop_work_is_all_in_flight` calls `decide_firing`, and `decide_firing` never reaches the busy
guard. For a loop with ordinary claimable work the answer is `DECISION_CLAIM`, not
`DECISION_IN_FLIGHT` — so `run_job` falls through to the branch below it and raises **500** with the
bare fallback string `"Failed to fire job"`, because there is no `JobRun.error_summary` to quote.

Measured, with the loop in perfect health at that moment: `ending_state` null, `enabled` true,
`next_run` set, its one task still `pending`, and **no history row written at all** — so the
operator gets a 500, no reason, and nothing in the loop's history that explains it. F48's own
write-up names this exact harm: *"the operator was being told their flow had broken."*

Reproducing it needs the free list genuinely empty, which is why the first attempt missed (see
F128): park one active task on every sibling agent, put the job's own agent mid-turn, press Run.

**Shape of the fix (not implemented — it wants a round).** The honest one is to make the
re-derivation ask the same question the firing asked: `_loop_work_is_all_in_flight` should also
consult `_loop_flow_busy_reason`, and `run_job` should answer 409 naming the busy agent. The
narrow one — treating "no `JobRun` was written" as "nothing is wrong" — is wrong for the reason F48
gives itself: inferring health from the *absence* of a row is how "the flow is fine" and "the flow
broke" became indistinguishable in the first place. The cron path is unaffected; this is purely
what the **manual Run button** reports.

## F128 (B) — a loop runs on an agent its job does not name, whenever its own agent is busy

Driven live in `t_run_while_busy.py` (that file's own BAD lines are this discovery). Job
`busy-run` was created with `agent: gamma`. gamma was put mid-turn on an unrelated errand. Pressing
Run answered **200**, and the work went to **alpha**: `conv-a51b18211d43`, agent `alpha`, origin
`job`, loop `loop-c888f4edb675`, and the queued task's `assignee` read `alpha`.

The mechanism is `_loop_flow_busy_reason` (`hub/hub/scheduler.py:270`), whose refusal needs both
halves: the job's agent is busy **and** `_agents_that_are_free(session, project_id)` is empty. That
list is **project-scoped**. Its docstring states the invariant that is supposed to make this safe:

> A single-agent loop reaches that by the general rule with no branch of its own — its one agent is
> the busy one and the free list is empty — which is what keeps this exactly as strict as before
> for every loop that exists today.

**That invariant only holds in a project with exactly one agent.** In a three-agent project a loop
that names one agent is not single-agent as far as this check is concerned, and the comment at
`scheduler.py:2081` — *"identical for every single-agent loop, so this branch behaves exactly as it
did for all of them"* — is false there. Two consequences, both measured:

* the substitution above: `job.agent` is silently only a default, so a loop bound to an agent for
  its charter or its runner is run by a different agent with a different charter and runner;
* F127's busy-guard refusal is effectively unreachable in a multi-agent project until every sibling
  is also occupied — which is exactly the corner where it does fire, and answers 500.

**Not a defect on its own reading** — design D12 chose width for flows deliberately, and
`job.agent` really is D2's default. What is wrong is that nothing tells the operator: the job form
takes an agent, the loop lists a label and an agent, and neither says "or whoever is free". This is
**the operator's call**, and it is one decision with two shapes: either the free list becomes
loop-scoped (a loop staffs only the agents it names, a flow staffs its roster), or the UI and the
API stop presenting `job.agent` as who runs this loop. Filed, not fixed.

## F129 (B) — requirement drift works, and the app cannot reach any of it

**Driven 2026-08-29, iteration 10, on the 8011 Hub running this branch. Row 10 of TESTPLAN.md,
never driven before today. `scripts/drive/t_row10_drift.py`, 31/31 assertions good.**

The loop itself is correct, and worth saying so plainly before the finding, because every sentence
below was measured rather than read:

| what was driven | result |
|---|---|
| operator records evidence naming `cart.py` | 201, footprint `kind=git`, `branch=main`, `commit_sha` equal to the repo's HEAD, and `review_state` already `accepted` on arrival |
| scan with an unchanged tree | 200, nothing raised for that evidence |
| commit a change to the footprinted file, scan | 200, exactly one candidate, `observed` naming `cart.py` alone with distinct `was`/`now` blob ids, hung off the right evidence row |
| coverage while the candidate is open | `drifting` — the documented top precedence |
| scan again while it is open | raises nothing; the same question is not asked twice |
| resolve with a bogus resolution | **422** naming `unknown_resolution` |
| resolve an unknown drift id | **404** |
| resolve `implementation_corrected` | 200, `state: resolved`, coverage back to `verified` |
| scan after resolving | raises nothing — the resolution holds |
| move the ground *again* | a **fresh** candidate, a different row |
| add an unrelated file | raises nothing |
| put the footprinted file back to its recorded blob | raises nothing |

That last row was found by accident: a second run of the harness rewrote `cart.py` to content an
earlier run had already produced, the scan correctly said nothing, and the harness called it a
defect. It is not one — a file that is byte-identical to its footprint has not drifted. The harness
now stamps every write with the repo's commit count so no run can silently reproduce an earlier
blob, and asserts the revert case deliberately.

**The finding is that none of it is reachable from the product.** `POST /spec/drift/detect` is the
**only** writer of a `RequirementDrift` row — no scheduler sweep, no MCP tool, no other route calls
`requirement_evidence.detect_drift`. And `hub/ui/src` never calls it: the whole string `drift`
appears in the UI in exactly two load-bearing places, both of them the *word* `drifting` as a
coverage state — `api/spec.ts:98` in the union type, and `SpecCoverageBar.tsx:10` as a bucket.
There is no hook for `/spec/drift`, none for `/spec/drift/detect`, none for
`/spec/drift/{id}/resolve`.

So the coverage bar carries a `drifting` bucket that **cannot light up through the app**, and if
something outside the app lights it up, the operator is shown a requirement that has changed
underneath its evidence with:

* no way to see *what* moved (`observed` is only on `GET /spec/drift`),
* no way to answer the question the whole feature exists to ask, and
* no way to clear it — `drifting` is the top of the precedence chain, so that requirement now
  reads `drifting` on every screen, permanently, until somebody makes an HTTP call by hand.

The backend's own docstring says the outcome is *"a question for a person rather than a state the
requirement acquires by itself"*. Today there is no person it can ask.

**Shape of the fix** — this is a UI gap, not a backend one; the backend is complete and correct.
The smallest honest version is three controls on the spec surface: a **Scan for drift** action, a
list of open candidates showing `observed`, and the three-way resolution on each. The one design
question worth the operator's judgement is whether the scan stays manual. It is not free (it runs
`git ls-tree` per distinct branch plus a reachability refresh), and the route's own comment says
the operator's explicit scan is also the moment reachability is re-answered — so making it
automatic on some cadence changes two things at once, and the manual button should ship first.

Filed as **B**, not **A**: nothing is lost or corrupted, and no run misbehaves. But a shipped
feature that has a database table, a lifecycle, three routes, a precedence rule at the top of
coverage, and a UI bucket — and that no operator can reach — is the shape this drive exists to
find.

### F128 — confirmed in isolation, 2026-08-29 iteration 10

Iteration 9's caveat was that F128 was found by a harness asserting something else, and observed
once. `scripts/drive/t_f128_substitution.py` is written for it, and holds **12 of 13** assertions:

* three idle agents, a job configured `agent: gamma`, nobody parked, so the free list is genuinely
  non-empty;
* gamma put mid-turn on an unrelated errand, then Run pressed → **200**, not a refusal;
* the conversation the firing created is `origin: job` and **ran on `alpha`** — one of the free
  siblings, not gamma;
* the loop's first task is `in_progress` with `assignee: alpha`;
* and `GET /jobs/{id}` still answers `agent: gamma`. Nothing anywhere records that somebody else
  did the work.

Reproduced identically on three separate firings across three runs of the harness (`alpha` every
time, with `beta` also free — so the choice is not random, though this harness does not establish
what orders it).

Two facts about *driving* a loop came out of it, neither of them defects, both worth knowing before
writing the next harness:

* **A loop delivers one task at a time.** Pressing Run again while the first errand is in flight is
  refused **409** — *"Every task on this loop's queue is already being worked. Nothing was started,
  and nothing is wrong"* — which is F48's re-derivation answering correctly.
* **A Haiku errand does not close the task it was handed.** The turn answers the message and the
  task sits `in_progress` indefinitely; four minutes of waiting proved it. The harness now has the
  operator complete the task, which is a real operator action rather than a way around one.

### F127 — reproduced a second time, in a shape nobody set up for it

The second firing in that harness — healthy loop, one `pending` task, nothing in flight — answered
**500 "Failed to fire job"**. The cause is F127 exactly: at that moment gamma was mid-turn, alpha
was still finishing the turn the first firing started, and **beta was holding two `in_progress`
tasks left over from an earlier drive**, so `_agents_that_are_free` was empty and the busy guard
refused with nothing recorded.

That matters for how F127 is read. `t_run_while_busy2.py` empties the free list deliberately, by
parking a task on every sibling, and a reader could fairly ask how contrived that is. This one was
not set up at all: **ordinary leftover work on one agent was enough**, in a three-agent project, to
turn an operator's Run press into an unexplained 500. The narrower the roster and the longer the
project has been used, the likelier it is.

---

## F130 — a checkpoint over an empty span makes the NEXT checkpoint re-summarise the whole conversation

**Found by driving the second link of a checkpoint chain** (`scripts/drive/t_row15_chain.py`), which
row 15's cutover leg never reached: every checkpoint that harness made was a conversation's *first*,
so `previous_checkpoint_id` was NULL on all of them and nothing had ever exercised the lineage
columns live.

The chain machinery itself is **right**, and this is worth saying before the defect: three
checkpoints on one conversation came back `ckpt-5270b01ef65a → ckpt-a6462ba1cbd4 →
ckpt-e302e3e494f9`, each naming its predecessor, all three carrying the founder's `lineage_id`,
exactly one of them with no predecessor, and each render printing `Previous checkpoint: <id>` at the
top. The list route reports the same links. That half needed driving and it held.

### The defect

Press **Checkpoint** twice with no turn in between — an ordinary operator slip, and the product
allows it: the second call answers **201**, `status: ready`, `probe_status: passed`, with a written
body about a span in which nothing happened and `_No files recorded_` in its render.

That checkpoint stored `covers_through_run_id = NULL`, because the span was empty:

```python
covers_from_run_id=runs[0].id if runs else None,
covers_through_run_id=runs[-1].id if runs else None,   # hub/hub/checkpoints.py:367
```

and `runs_to_cover` reads NULL as *unknown, so cover everything*:

```python
if anchor is None or anchor.covers_through_run_id is None:
    return runs                                        # hub/hub/checkpoints.py:179
```

So the **third** checkpoint, anchored on the empty one, silently re-covered the conversation from
the beginning. Measured: after a first turn that wrote `CHAIN_ONE.txt` and a second that wrote
`CHAIN_TWO.txt`, checkpoint #3's `files_changed` names **both** — `CHAIN_ONE.txt` had already been
covered by #1 and is not new work by any reading.

The fallback's own docstring justifies itself against a *different* case: "falls back to all runs
when the anchor names a run this conversation no longer has — covering a turn twice is a redundancy,
whereas silently covering none is a hole." That reasoning is sound for a **missing** run. Here
nothing is missing: the anchor is intact and its emptiness is a **fact**, not an absence of
information. NULL is being asked to mean two different things — "I do not know where you got to" and
"I got to exactly where the last one did" — and only the first is handled.

### Why it is worse than a redundancy

In the first run of the harness the third checkpoint's written half opened:

> "## Current state — No progress. The file creation task remains incomplete—the file has not been
> created."

while its own computed half listed `CHAIN_ONE.txt`. The file **had** been created. Re-covering an
old span does not merely cost the worker tokens; it hands the worker a span whose outcome it has to
reconstruct from a transcript it half-summarised already, and the result was a checkpoint that
contradicts its own file list. `probe_status` was **passed** throughout — correctly, because the
probe grades whether a blind reader can recover files/tasks/questions from the render, not whether
the prose is true. The probe cannot catch this and is not meant to.

The blast radius grows with the conversation: on a long one, one stray Checkpoint press means every
later checkpoint in that conversation re-summarises everything back to turn one, at full worker
price, forever — nothing ever re-establishes a non-NULL `covers_through`.

### The fix shape (not decided here)

Three options, cheapest first:

1. **Carry the anchor forward.** When the span is empty, store the anchor's `covers_through_run_id`
   rather than NULL. One line, keeps the chain continuous, and the empty checkpoint stays a legal
   record of "the operator asked at this moment".
2. **Refuse the empty span**, 409, naming the checkpoint that already covers it. Cleaner in that it
   stops writing a body about nothing, but it removes an operator's ability to re-checkpoint after
   editing notes, so it needs the notes path checked first.
3. **Distinguish the two NULLs** — an explicit `covers_nothing` flag, or making `covers_through`
   non-nullable with a sentinel. Most honest, most schema churn.

(1) and (2) are not exclusive. What must not happen is the fourth option nobody proposed: leaving it
and treating "covering a turn twice is a redundancy" as covering this case, because the observed
cost here was a checkpoint that says the work was not done.

### Reproduction

`py -3.11 scripts/drive/t_row15_chain.py` against a Hub with a checkpoint runner available
(`AW_PROJECT`, `AW_AGENT`, `AW_RUNNER` override the defaults). The F130 assertion is written in the
direction the product **actually behaves** — "#3 ALSO re-covers the first turn" — so the day it is
fixed that line goes red and says why.

---

## F131 — Continue on one conversation starts a different conversation's work, and reports success against the one you pressed

**FIXED 2026-08-30** — `openspec/changes/continue-starts-what-it-names`, three spec-loop rounds
then implementation. Driven live afterwards: **17/17**,
`scripts/drive/t_f131_start_reported_to_its_own_input.py`. Two corrections this change established
are recorded under "What the fix corrected in this finding" at the end; the account below is left
as it was written so the two can be compared.

**Found by driving the `continue` endpoint's unreached branches**
(`scripts/drive/t_continue_branches.py`). Two of them are fine and are now covered: pressing Continue
with nothing queued answers **200** with `started: false, waiting_reason: "queue is empty"`, and
pressing it while the agent is mid-turn answers **200** with
`waiting_reason: "agent is already running"`. Both name the reason rather than failing silently, and
neither started anything.

The third thing the drive asked is not a branch. `POST /conversations/{id}/continue` resolves the
conversation **only to 404 on it**, and then schedules the *agent*:

```python
conversation = await _conversation_or_404(session, project_id, conversation_id)
result = await schedule_agent(project_id, conversation.agent)      # hub/hub/api/v1/checkpoints.py:271
return {"conversation_id": conversation_id, "started": result.waiting_reason is None, ...}
```

`schedule_agent` takes the agent's **next queued entry, whatever conversation it belongs to**. The
conversation in the path contributes nothing except the agent's name and a 404.

### Measured

With gamma idle and exactly one thing queued — a checkpoint entry addressed to successor
`conv-7e15b83ad8b5`, produced by a cutover — Continue was pressed on `conv-766a9eee3bfc`, an
unrelated open conversation of the same agent with nothing queued for it.

* the call answered **200**, `started: true`, `waiting_reason: null`, `conversation_id:
  conv-766a9eee3bfc` — the one pressed;
* the successor's queue entry was **consumed** (`GET /queue/gamma` empty afterwards);
* and the runs table for that window holds exactly one new run, `run-f36b8f55fae9`, on
  **`conv-7e15b83ad8b5`**. The pressed conversation's newest run is minutes older, from a previous
  harness.

So the operator pressed Continue on A, was told A started, and B ran.

### Why it matters, and why it is not simply "the queue is per agent"

It is true and correct that a turn is a per-agent resource: one agent runs one turn at a time, and
the queue is the agent's. The defect is not the scheduling — the right work ran. It is that the
**endpoint is addressed per conversation and answers as if it were**. `started: true` alongside the
conversation id the caller supplied is a claim about that conversation, and it is false. An operator
watching A sees a success and then nothing: no turn appears, no output, no error. The very next
thing they will do is press it again.

The shape is the same one F116 was about: a route that accepts an input, does something else with
it, and returns a success that names the input back. There the input was silently discarded; here it
is silently substituted. And it is the same family as F128, where a loop's configured agent is not
the agent that runs it — a product that reports the identifier you supplied rather than the one it
acted on.

### The fix shape (not decided here)

1. **Report what actually started.** `schedule_agent` knows the entry it picked; return *its*
   conversation id and let the UI show that a different conversation began. Smallest honest change,
   and it makes the surprising case visible instead of invisible.
2. **Refuse the mismatch.** If the agent's next entry is not for the conversation in the path,
   answer 409 naming the conversation that is actually next. Safer for an operator who meant "this
   one", worse for the case where they just want the agent moving.
3. **Both** — refuse by default, report on force. Probably over-built for one button.

What must not happen is keeping the current answer, because it is the one shape that is
indistinguishable from success.

### Reproduction

`py -3.11 scripts/drive/t_continue_branches.py` against a Hub with a checkpoint runner available
(`AW_PROJECT`, `AW_AGENT`, `AW_RUNNER` override the defaults). Needs an existing conversation for
that agent to act as the wrongly-pressed one — the harness takes the first it finds. The F131
assertions are written in the direction the product **actually behaves**, so the day it is fixed
they go red and say why.

**That day was 2026-08-30, and those assertions have been flipped** — see the comment at step 4 of
`t_continue_branches.py`, which records that the flip is the fix rather than a regression.

### What the fix corrected in this finding

**1. The reproduction above is not the one that matters.** It presses Continue on a conversation
with *nothing* queued for it, and that path is unreachable from the shipped UI: the button renders
only when `queuedEntries.some(entry => entry.conversation_id === currentConversationId)`
(`AgentOutputPanel.tsx:337-340,1064`). The severity is exactly what this finding says; the
*reachable* path is different — the pressed conversation **has** a queued entry and another
conversation of the same agent has an **older** one, so every client-side gate is satisfied and the
substitution happens anyway. That is what
`scripts/drive/t_f131_start_reported_to_its_own_input.py` builds, with two cutovers on
auto-continue-off, which is the only operator act that queues without scheduling.

It also means the two cases need **different answers**. Telling a conversation that queued nothing
that its input is "waiting behind other input" reports a queue position that does not exist. Round
3 of the spec loop found rounds 1 and 2 had collapsed them into one.

**2. The rule was already shipped — for refusals — and merely unwritten for starts.**
`agent-conversation-workspace` has carried *"A refusal is reported only to the input it is about"*
since before this finding, and `POST /agent/trigger` implements it in both directions, comparing
`scheduled.response.conversation_id` to the conversation it appended to (`agent_trigger.py:1353`).
`continue` is the second conversation-addressed caller of `schedule_agent` and implemented neither
half — it could be written without them because the requirement's *text* is about refusals. So this
was not a missing decision. It was a decision stated in one direction, with the other half left to
be re-derived by whoever wrote the next route. The change writes the start half down, and the
implementation adds the test that pins `/agent/trigger` too, so the two routes cannot drift apart
again. **That test is the one that would have caught this defect.**

Fix shape 1 above ("report what actually started", keeping `started: true`) was **rejected** in
design: truthful about what ran and still wrong about what the caller asked. Shape 2 (409) was
rejected as an error answer to a case the shipped requirement already answers with *accepted,
waiting*. What shipped is the comparison plus two distinct waiting reasons plus
`started_conversation_id`, with turn selection deliberately untouched — the right work was always
running.

A third caller was corrected alongside: `checkpoint_cutover.py`'s `auto_continue` logged only
`if result.waiting_reason:`, so the case where a turn started for a *different* conversation was
**silent** while the successor did not start.

---

## F132 — drift has no agent-side half either, and the gate's remedy names an action no surface offers

**Read 2026-08-29, iteration 12. Static, not driven: this closes `next_action` item (e), "the drift
feature's agent-side half (F129), if it has one." It has none, and looking for it turned up a
sharper version of F129 than F129 states.**

F129 measured that `POST /spec/drift/detect` is the only writer of a `RequirementDrift` row and that
`hub/ui/src` never calls it — so the operator surface cannot raise drift. The open question it left
was whether the agent surface could. It cannot, and the two halves compose into something worse than
either alone.

### The agent surface has no entrance

| where an agent could reach drift | what is there |
|---|---|
| `hub/hub/mcp_server.py` | 26 `@mcp.tool()` functions; **none** mentions drift. Both string matches for "drift" in that file are comments about *spec-payload* drift failing in CI (lines 34, 1016) — a different concept. |
| `hub/hub/api/v1/agent_actions.py` — the agent's whole route surface | 31 routes; the spec block is `/spec/evidence` (record, list, decide) and `/spec/documents` (list, create, rename, submit). **No `/spec/drift` route of any kind.** Its only "drift" match is `spec_lifecycle.divergence` at line 1118, which is a document-digest divergence check, unrelated to `RequirementDrift`. |
| the canonical turn context (`hub/hub/api/v1/agents.py`) | no `coverage` and no `drift`; the only matches are three comments using "drift" in its ordinary English sense. `requirement_coverage` is imported by `api/v1/spec.py`, `api/v1/tasks.py`, `requirement_gate.py`, `schemas/tasks.py` and `task_transition_service.py` — never by the agent's context or its routes. |

So an agent cannot raise a candidate, cannot list one, cannot resolve one, and is never told that a
requirement it is working on is `drifting`. Drift is an operator-API-only feature on both sides.

### The part that is worse than unreachable

`drifting` is not inert while it is unreachable — `requirement_gate` consumes it. The gate refuses
the `approved` transition for any `gate`-rigor requirement whose coverage is not `verified`
(`requirement_gate.py:39`, `:235`), and every non-verified state carries a remedy naming what would
change it. Drift's is:

```
requirement_coverage.DRIFTING: (
    "the implementation changed after it was verified — resolve the drift candidate"
),
```
`hub/hub/requirement_gate.py:60-62`

**"Resolve the drift candidate" is an action no surface in the product offers.** The only writer of
a state other than `candidate` is `requirement_evidence.resolve_drift`, reachable only through
`POST /spec/drift/{drift_id}/resolve` (`api/v1/spec.py:974`), which — measured again this iteration,
independently of F129 — appears nowhere in `hub/ui/src`: grepping the whole UI for "drift" returns
the union member `'drifting'` in `api/spec.ts:98`, the coverage bucket in `SpecCoverageBar.tsx:10`,
the unrelated *spec-manifest* drift summary in `SpecDocumentPanel.tsx`, and 45 further matches that are all code comments using "drift" in its ordinary
English sense (49 lines in total). No URL.

**And it cannot self-heal.** `detect_drift` skips any evidence that already has an open candidate
(`requirement_evidence.py:1041-1058`, the `open_candidates` set and the `continue` on it) and never
closes one. Putting the file back to its footprinted blob makes a *later* scan raise nothing — F129
measured that — but does nothing to the row already open. Re-scanning is explicitly designed not to
ask the same question twice, which is right, and which also means re-scanning is not an escape.

The gate's docstring says the refusal has to be actionable because "an unactionable gate gets
switched off, which is worse than never having built one" (`requirement_gate.py:17-22`). This is one
refusal whose remedy is unactionable through the app by construction. The reason nobody has hit it
is only that the same missing UI that cannot clear a candidate also cannot raise one — the feature
is symmetrically unreachable, and that symmetry is the whole thing keeping the gate usable. Anything
that adds a *detect* button without a *resolve* one — an obvious first slice, and the cheaper half —
would strand a task in `approved`-refused with no way out but a hand-written API call.

### What this changes about F129's fix

F129 asks for a way to reach detection. This says the two routes must ship **together, or resolve
first**, and that the gate's remedy string is the acceptance test: a state whose remedy cannot be
performed on the surface that shows it is a bug even when the state is correct.

Not proposed here — this wants a spec loop, and the clock ended this session before one could start.

**Evidence:** all static, all cheap to re-check. `grep -c "@mcp.tool()" hub/hub/mcp_server.py` → 26;
`grep -n "^@router\." hub/hub/api/v1/agent_actions.py`; `grep -rn "drift" hub/ui/src`;
`hub/hub/requirement_gate.py:39,60-62,235`; `hub/hub/requirement_evidence.py:998-1058`;
`hub/hub/api/v1/spec.py:921,942,974`.

## F133 (B) — the operator's own message erases the reason their agent is stalled

**Driven 2026-08-30, iteration 11, full-surface sweep. Reproduced live on the 8011 Hub against
`proj-1964cdedffe2` (`drive-0830-sweep`), two Haiku agents, real turns.
Harness: `scripts/drive/t_row18_budget_reason.py` — 10/11, and the one failure is this.**

A project token budget pauses autonomous turns and lets the operator's own through. Two places
decide whether a stalled turn counts as autonomous, and they decide it differently:

| | predicate | scope |
|---|---|---|
| `turn_scheduler.schedule_agent` (`turn_scheduler.py:133-138`) | `initiator = "operator"` if any entry in **the selected turn** is operator-origin | the controlling entry's conversation, within hop budget, matching its kind, capped |
| `GET /queue/{agent}/status` (`inbound_queue.py:145-149`) | `all(entry.origin_type != "operator")` | **every** queued entry for the agent, across every conversation |

An operator message queued *beside* a blocked autonomous one satisfies the scheduler's predicate
(the operator's entry is not in the turn the scheduler built) and fails the endpoint's (it is in the
set the endpoint looks at). The scheduler still refuses; the endpoint stops saying why.

### The reproduction, as it ran

Budget set to 1 with 35,027 tokens already used, so `exhausted: true`. `peer` is triggered once and
calls `send_message` to `driver`; the resulting agent-origin entry cannot start.

```
3. THE CONTROL -- only the autonomous entry queued
--- GET /queue/driver/status  [200]
{"agent":"driver","waiting_count":1,"running":false,
 "waiting_reason":"token budget exhausted","delivery_attempts":0}

4. the operator now sends their own message to the same agent
--- POST /agent/trigger (operator)  [200]
{"success":true,"status":"queued","conversation_id":"conv-329cb276f816",
 "queue_entry_id":"entry-8157f49800d5","waiting_reason":"token budget exhausted"}
   nothing started -- idle;  two entries now queued -- ["agent","operator"]

5. read the reason again -- same stall, operator input added
--- GET /queue/driver/status  [200]
{"agent":"driver","waiting_count":2,"running":false,
 "waiting_reason":null,"delivery_attempts":0}
```

### What the operator actually sees

`AgentTimeline.tsx:341` is the only render of this field:

```tsx
{queueStatus.waiting_count} waiting{queueStatus.waiting_reason ? ` — ${queueStatus.waiting_reason}` : ''}
```

So the panel reads **"2 waiting"**, full stop. The transient half is `AgentOutputPanel.tsx:693` and
`:763`, which show the *trigger response's* reason as a session notice — the operator is told
"Not started — token budget exhausted" once, at the moment they press send, and the standing
display beside the agent from then on says only how many.

`waiting_count: 2, waiting_reason: null` is exactly the state `db/models.py:586` records as the
defect the `waiting_reason` column was added to remove — *"reported to the operator as
`waiting_count: 1, waiting_reason: null`"* — reproduced by the operator doing the one thing the
panel invites them to do when an agent looks stuck: send it a message.

### Why the reason is not merely stale, but gone

Nothing persists it. `turn_scheduler.py:174` writes `entry.waiting_reason` only inside the
`TriggerAgentError` handler; the four early returns — hop budget, token budget, no conversation,
conversation unavailable — return a `ScheduleResult` and write nothing. So the endpoint's fallback
at `inbound_queue.py:183` (*"what the last attempt was actually refused with"*) has no row to read,
and the recomputation is the only answer there is.

The Hub knew the reason one call earlier: `POST /agent/trigger` answered
`waiting_reason: "token budget exhausted"` (step 4 above) because it reports
`scheduled.waiting_reason` straight from the refusal. The operator is told once, in a response body,
and the panel they will actually look at afterwards says nothing.

### Precisely one branch diverges — the other three agree

Worth stating, because the obvious next thought is that every branch has this shape and it does not.

- **hop budget** — endpoint `all(entry.hop_depth > hop_budget)`; scheduler
  `can_start = any(entry.hop_depth <= hop_budget)` over the *same* unfiltered set
  (`turn_scheduler.py:93-95`). Exact complements. Agree.
- **already running** and the launchability/workspace probes are read-only statements about the
  agent, not about a turn's composition. No predicate to diverge from.
- **token budget** — the only one whose scheduler side is computed over the *selected* turn rather
  than the whole queue.

### One defect, or a symptom

A symptom. The endpoint re-derives, from a different set, a decision `schedule_agent` has already
made — so the two can disagree about anything the selection step touches, and today they disagree
about one thing. The narrow repair (mirror the selection in the endpoint) leaves the duplication
that produced it; the clean one (factor the read-only selection out of `schedule_agent` so both
callers ask the same function) is a refactor of the scheduler's hot path. **Filed, not fixed** —
two defensible answers is decision D5's stated line for filing.

Related but not the same as **F131**: F131 is about `Continue` reporting another conversation's
start as its own. This needs no `Continue` and no checkpoint, and F131's fix
(`openspec/changes/continue-starts-what-it-names`) does not touch `inbound_queue.py`'s predicate.
Not covered by anything in `openspec/changes/`.

**Reproduce:**

```
AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=proj-1964cdedffe2 \
    PYTHONIOENCODING=utf-8 py -3.11 scripts/drive/t_row18_budget_reason.py
```

Clears the budget and drains the queue in a `finally`. Costs two Haiku turns.

## F134 (B) — a charter with no content is injected as a bare heading, and the agent is reported fully configured

**Driven 2026-08-30, iteration 11, full-surface sweep. Row 4 into row 3, on the 8011 Hub,
`proj-1964cdedffe2`.**

`POST /projects/{p}/charters` with `{"name": "sweep-empty", "content": ""}` answers **201**. Binding
it to an agent answers **200**. The canonical context that every real turn is built from then ends
like this — this is the literal last line of
`GET /projects/{p}/agents/agent-context?agent=unbound-driver`:

```
## Charter: sweep-empty
```

Nothing under it. The document stops there.

The code has a strictly better sentence for this situation and cannot reach it:

```python
if charter:
    lines.append(f"## Charter: {charter.name}")
    lines.append("")
    lines.append(charter.content)      # ""
    ...
else:
    lines.append("## Charter")
    lines.append("")
    lines.append("No charter is assigned to this agent.")
    ...
    missing.append("charter")
```

`hub/hub/api/v1/agents.py:1502-1513`

`if charter:` tests the *row*, which is always truthy when one is bound, so an empty contract takes
the first branch. Two consequences:

1. **The agent reads a heading that promises a behaviour contract and finds nothing.** An agent
   reasonably reads that as truncation. `_render_hub_agent_context` is not a reporting route — it is
   materialised into the workspace immediately before command construction for *every* turn
   (`agent_trigger.py:897-911`, *"an edited charter is therefore visible on the next run"*), so this
   is what a real run receives.
2. **`missing` stays `[]`.** The response reports the agent as wanting nothing, while its behaviour
   contract is empty. The `else` branch appends `"charter"`; this branch cannot.

### The corpus does not cover it

`openspec/specs/agent-charter/spec.md:56-72` governs the neighbouring case and stops short:

> An agent with no bound charter SHALL remain usable — its context response SHALL state plainly that
> no charter is assigned rather than erroring **or fabricating behavior content**.

A bound-but-empty charter is neither "resolves its bound charter" nor "has no bound charter". The
requirement's own phrase is the right test and no scenario applies it here.

### The asymmetry that produced it

`hub/hub/schemas/charters.py:12-13` — `name: str = Field(min_length=1, max_length=256)` beside
`content: str` with no constraint. The name of a behaviour contract is guarded; its text is not.

### One defect, or a design gap

A gap, with more than one defensible answer, so **filed, not fixed**: refuse empty content at the
API (an operator mid-edit cannot save a blank draft), or render the no-charter notice and count it
in `missing` (an empty charter and no charter become indistinguishable, which may be exactly right),
or emit a third explicit statement. `PATCH` has the same hole — `content: Optional[str] = None`
means an existing charter can be blanked the same way. Severity B rather than A: it degrades what an
agent is told rather than stopping anything, and no seeded charter is empty (all 9 have content).

**Reproduce:**

```
POST  /api/v1/projects/<p>/charters    {"name":"blank","content":""}      -> 201
PATCH /api/v1/projects/<p>/agents/<a>  {"charter_id":"<id>"}              -> 200
GET   /api/v1/projects/<p>/agents/agent-context?agent=<a>
      -> .context ends "## Charter: blank" ; .missing == []
```

### Also driven this row, and held

- `GET /fs/list` on a missing path, and on a *file*, answers 200 with `entries: []` **and a
  `reason`** naming the OS error — it does not turn "I could not look" into "there was nothing
  there". `DirectoryPicker.tsx:158-161` renders it: *"Can't read this directory: {reason}"*. The
  seam this sweep expected to be broken is not.
- Duplicate charter names are accepted (six rows named `sweep-charter` in this project). Not filed
  as a defect: binding is by `charter_id` throughout, and no requirement claims names are unique.
  Recorded so the next sweep does not re-derive it.
- `GET /agents/agent-context` for an agent that does not exist answers 200 with onboarding context,
  by design; an illegal agent name answers 400 `Invalid agent name`.

## F135 (C) — the sweep harness reported its own wrong turn as a product defect, for the second time

**Corrected 2026-08-30, iteration 11.** Recorded because `t_sweep_surface.py`'s own docstring
already warns about exactly this — *"the first pass of this script guessed six of them and reported
five false 404s"* — and it happened again in a different way.

`probe(3, "canonical context", "GET", f"/projects/{P}/agents/context", expect=200)` called the
**charter**-content route, which takes a required `charter` query parameter
(`agents.py:2053-2056`), with no parameters. Its `422` was reported as an unexpected status for two
runs. The canonical per-agent context the matrix row means is
`GET /agents/agent-context?agent=<name>` (`agents.py:2077`), which answers 200.

Fixed in place, with the two refusal probes the corrected route makes available (a name that does
not exist, and a name that is not legal). Row 3 also hard-codes the agents `driver` and
`unbound-driver` from an older fixture; on a fresh project its three archive/unarchive probes answer
`404 Agent not found`, which is the harness's state and not the product's. Left as-is and stated
here rather than made self-provisioning: creating agents inside a probe script is how a sweep starts
testing its own setup code.

## F115, reproduced independently — two identical triggers, one inside the boundary and one outside

**Driven 2026-08-30, iteration 11, on the 8011 Hub, `proj-1964cdedffe2` (`drive-0830-sweep`), a
fresh project created this morning. Not a new finding — the same defect F115 states, reached by a
different route, and worth recording because the two runs differed with nothing else changed.**

Row 14's harness triggers `asker` under `manual` posture with one instruction: *"Write the single
line 'drive touched this' to a new file named `<tag>.txt` in the project root."* It was run twice,
nine minutes apart, same agent, same runner, same posture, same sentence with only the filename tag
different. The permission card's `tool_input.file_path` was:

| run | tag | path the card offered |
|---|---|---|
| `run-dddadb7f817e` | `i11b` | `…\drive-0830-sweep\.agentweave\worktrees\asker\drive-note-i11b.txt` |
| `run-0d750fe5d14d` | `i11c` | `…\drive-0830-sweep\drive-note-i11c.txt` |

Both were approved. Both writes landed where the card said. So the operator's checkout now holds
`drive-note-i11c.txt` as an untracked file on `main`, while `drive-note-i11b.txt` sits on
`agentweave/asker` where it belongs:

```
$ git -C drive-0830-sweep status --porcelain
?? .agentweave/
?? drive-note-i11c.txt          <- outside the boundary
$ ls drive-0830-sweep/.agentweave/worktrees/asker/
calc.py  drive-note-i11b.txt    <- inside it
```

Nothing in the product distinguished the two. This is the phrase "project root" being genuinely
ambiguous to an agent standing in a worktree — and the point is that the ambiguity is *load-bearing*,
because whichever way it resolves the Hub proceeds identically.

**What this adds to F115.** F115's proposal already covers the posture analysis and states that
`manual`'s card "named the tool and the full absolute path". What it does not say is that the card
names the path *and nothing else* — no marker that this one leaves the agent's workspace, no
comparison against the boundary the Hub itself computed a moment earlier to launch the run. The
operator approving that card is the last human who could have stopped it, and the card gives them
nothing to notice with. Recorded here rather than proposed: the change's scope is settled (decision
D3 — record it against the Run) and widening it to the approval surface is the operator's call, not
an unattended run's. The relevant sentence for them is that `manual` is not a safer posture than the
default here; it is the posture in which a human is asked to make a judgement they have not been
given the inputs for.

**Also driven, and held:** rows 13 and 14 both pass on Claude/Haiku. `ask_user` raised a real
blocking question in ~20s, `PATCH /questions/{id}` answered it and it left the open list
immediately; the `manual` posture raised a permission card in ~12s on both runs and
`POST …/decide {"allow": true}` cleared it in under a poll. Neither row was passing when this
iteration started — see F135 continued below for why the harness said otherwise.

## F135, continued — three more of the sweep's own wrong turns, all in the live-turn harnesses

Same class as F135 above; grouped with it rather than given new numbers, because none is a product
defect and the pattern is the finding.

1. **Row 13 answered somebody else's question and called itself passing.** `wait_for` matched *the
   first open question in the project*, and an earlier drive in the same project had left one open
   from a different agent (`from_agent: "peer"`, about a task called `Sweep B`). It appeared "after
   ~0s", was answered, and row 13 reported PASS without `asker` having asked anything. Fixed: the
   row now snapshots the open set before triggering and requires a question that is both new and
   `from_agent == agent`. With the fix, the real question — *"Which colour should the badge be?"*,
   from `asker` — appeared after ~20s and the row passes honestly.

2. **Row 14 blamed the product for row 13's run still being alive.** Both rows trigger the same
   agent and nothing waited between them, so row 14's trigger answered
   `status: "queued", waiting_reason: "agent is already running"` — the Hub saying exactly what was
   wrong — and the row spent 160 seconds waiting for a permission card that could not exist,
   then reported *"no permission request was ever raised"*. Fixed: both rows wait for the agent to
   go idle first, and row 14 returns `SKIPPED` rather than `FAIL` if it never does.

3. **Row 14's decision body had the wrong shape.** It sent `{"decision": "allow"}`; the route takes
   `{"allow": true}` (`PermissionDecision`, `hub/hub/api/v1/permissions.py:25-26`). The refusal is a
   good one and is worth quoting as the counter-example to this file's usual complaint about
   illegible 4xx — it names both halves of the mistake:

   ```
   422 {"detail":[{"type":"missing","loc":["body","allow"],"msg":"Field required"},
                  {"type":"extra_forbidden","loc":["body","decision"],
                   "msg":"Extra inputs are not permitted","input":"allow"}]}
   ```

4. **`t_row13_questions.py` hard-coded the 2026-08-29 drive's repository**, which is also F115's
   live reproduction, with no way to point it elsewhere — so running row 13 would have written an
   agent's note file into somebody else's evidence. It opened that project on the 8011 Hub before
   this was noticed; nothing was written and the directory is intact (`README.md`, `calc.py`, and
   yesterday's `drive-note-121250.txt`, all unchanged). `WORKDIR` now reads `AW_DRIVE_DIR` and
   `PROJECT_NAME` follows the directory's own name.

The through-line: **every one of these made the product look worse than it is**, and three of the
four would have been filed as findings by a less suspicious reading. A harness that carries state
between rows, or between runs in one project, is not a cheaper fixture — it is a source of false
positives whose cost is paid by whoever reads the report.

## F136 (B) — the fix that stopped the Hub naming a binary after your agent does not cover the agents that most need it

**Driven 2026-08-30, iteration 12, on the 8011 Hub, `proj-1964cdedffe2` (`drive-0830-sweep`).
Reproduced on two independent surfaces in the same request cycle.**

An agent with **no runner bound at all** is reported as needing a command-line program named after
itself:

```
GET /api/v1/projects/proj-1964cdedffe2/agents/launchability
  "unbound-driver": {
    "runner": "native",  "cli": "unbound-driver",  "present": false,
    "runnable": false,
    "reason": "Runner CLI 'unbound-driver' was not found in PATH.",
    "collaboration_ready": null, "collaboration_reason": null
  }

GET /api/v1/projects/proj-1964cdedffe2/queue/unbound-driver/status
  {"waiting_count": 3, "waiting_reason": "Runner CLI 'unbound-driver' was not found in PATH."}
```

The agent's row is `runner_id = NULL`, `config = {}`, and there is no `agents.unbound-driver` entry
in session.json. Nothing anywhere says how to launch it. The operator is told to go install
`unbound-driver`.

### Why this is not simply F30 again

`hub/hub/launchability.py:36-43` introduces `RUNNER_UNBOUND` **specifically to end this sentence**,
and says so, citing the same measurement in the same words:

> Measured on the trial Hub 2026-08-21: an agent with `runner_id IS NULL` was reported as
> `Runner CLI 'probe-norunner' was not found in PATH`, sending the operator to look for a binary
> named after their own agent.

`get_agent_config`'s docstring (`launchability.py:369-375`) then states the repair as complete —
*"Doing it here fixes both surfaces at once and gives the unbound case a name of its own"*. Both
surfaces in that sentence are the two this finding reproduces on. They are not fixed.

The reason is one clause at `hub/hub/launchability.py:418`:

```python
elif not agent_row.self_registered and "runner" not in meta:
    meta["runner"] = RUNNER_UNBOUND
```

`self_registered` is set by `POST /projects/{p}/agents/register` (`agents.py:1696`, `agents.py:1709`)
— the documented path by which an agent joins a roster on its own. So the branch that gives the
unbound case an honest name is switched **off** for exactly the population that reaches the unbound
state most easily, and stays on for the population that cannot: `POST /projects/{p}/agents`, the
route the Hub UI's `useCreateAgent` calls (`hub/ui/src/api/agents.ts:330-335`), writes
`self_registered=False` **and** requires a launchable runner up front (`agents.py:658-673`), so a
UI-created agent is never unbound at birth.

With the branch off, `meta` carries no `runner`, `probe_agent` defaults it to `"native"`
(`launchability.py:57`), `RUNNER_CLI["native"]` is `None`, and `cli = RUNNER_CLI.get(runner) or name`
(`launchability.py:82`) resolves to **the agent's own name**. That is the fallback the whole
`RUNNER_UNBOUND` constant exists to stop being reachable.

### The exemption's own justification is measurably false

The guard is deliberate, and defended in prose at `launchability.py:377-378`:

> A **self-registered** agent is exempt: it manages its own execution and legitimately has no
> `Runner`, so calling it unbound would refuse something that works.

It refuses nothing. `runnable` is already `false` on both sides of the change — `present` is false
either way, because `shutil.which("unbound-driver")` finds nothing. Only the **sentence** changes.
Worse, the fallback means an agent whose name collides with a real binary (`node`, `git`, `make`) is
reported *runnable* on a program that has no idea what AgentWeave is.

The comment at `launchability.py:424-425` then defends the exemption a second way — the Hub cannot
trigger these agents, *"which is a separate verdict (`collaboration_ready`) that already says so"*.
Measured above: `collaboration_ready` is **`null`**. It says nothing. And the test named as pinning
it, `test_agent_with_no_bound_runner_has_no_collaboration_verdict`
(`hub/tests/test_launchability.py:306-319`), configures its agent through `session/sync` with
`{"runner": "claude"}` — so `"runner" in meta` is true and the second half of the `elif` already
excludes it. That test does not exercise the `self_registered` guard at all.

**Measured, not argued.** With line 418 reduced to `elif "runner" not in meta:` and nothing else
changed:

```
py -3.11 -m pytest hub/tests/test_launchability.py -q                       -> 39 passed
py -3.11 -m pytest hub/tests/test_agents_self_registered.py \
    hub/tests/test_inbound_queue.py hub/tests/test_agents.py \
    hub/tests/test_agent_trigger.py -q                                      -> 90 passed
```

129 tests, nothing pins the exemption. The file was restored afterwards; **this is filed, not
fixed.**

### Why it is filed rather than fixed

Because deleting the guard answers the wrong half of the question. Dropping it makes every
self-registered unbound agent say *"No runner is bound to this agent. Bind one in the Hub UI before
it can run."* — right for a `contact_mode: "poll"` agent that nothing will ever launch, and wrong
for a `contact_mode: "mcp"` agent with an `mcp_endpoint`, which drives itself and should not be sent
to the roster to bind a runner it does not want. The honest repair probably needs a third reason,
keyed on contact mode rather than on `self_registered`, and that is a design decision.

What is not in question is that the current sentence is wrong for **both** of those agents. Whatever
the third reason turns out to say, `cli = ... or name` at `launchability.py:82` should stop being
reachable; the agent's name is not a program.

### Reproduction

Against the 8011 Hub with `AW_HUB` / `AW_KEY` / `AW_PROJECT` exported:

1. `POST /projects/{p}/agents/register` with `{"name": "norunner-probe", "contact_mode": "poll"}`
2. `PATCH /projects/{p}/agents/norunner-probe` with `{"runner_id": null}`
3. `POST /projects/{p}/agent/trigger` with `{"agent": "norunner-probe", "message": "hi", "session_mode": "new"}`
4. `GET /projects/{p}/queue/norunner-probe/status` — `waiting_reason` names the agent as a CLI
5. `GET /projects/{p}/agents/launchability` — `agents["norunner-probe"].cli` is the agent's name

`scripts/drive/t_sweep_queue.py` now reaches this on every run — see F137 for why it did not before.

## F137 (C) — the harness that promised to spend no provider tokens had been spending them, and was measuring a different queue

**Corrected 2026-08-30, iteration 12.** Three defects in `scripts/drive/t_sweep_queue.py`, all of
the F135 class — the harness's own state, reported as the product's.

**1. The agent was archived, so every probe answered 409.** The file names a fixed agent,
`unbound-driver`, and never ensures it exists or is open. An earlier drive left that name archived,
so the first run of this iteration produced three `UNEXPECTED` lines all reading
*"unbound-driver is archived and cannot be triggered"* — which is the product behaving correctly at
a boundary the harness had walked into. `POST /agents/register` is idempotent but does **not** reopen
an archived row; the fix registers *and* unarchives.

**2. The agent had a runner bound, so the file's entire premise was false.** The docstring's claim is
that this row is free:

> The trick that makes them free is the agent with no runner bound: every trigger for it queues
> durably and nothing ever spawns, so the queue, the scheduler's attribution, withdrawal, release and
> concurrent triggers are all reachable **without a single provider token**.

Nothing enforced it. A later drive had bound `Haiku (cheap)` to that same name, so on the corrected
run the first trigger came back `status: "running"` and the release probe answered *"already
delivered"* — **five real Haiku turns were started by a file that says it starts none**, and the
queued entries had to be withdrawn by hand to stop the cascade.

The measurement damage is worse than the tokens. The `waiting_reason` the file exists to observe
changed underneath it:

| precondition | what row 6 reported as the reason a turn had not started |
|---|---|
| runner bound (silently) | `"agent is already running"` |
| no runner (the stated premise) | `"Runner CLI 'unbound-driver' was not found in PATH."` |

The first is a true statement about a situation the file was not written to examine. The second is
**F136**, which had been sitting behind this all along and had never once been looked at.

The fix asserts all three preconditions before any probe runs — exists, open, no runner — and
`sys.exit(1)` with a stated reason if the unbind does not take, rather than reporting on a situation
that is not the one described.

**3. An absence reported as a collision.** The row-19 concurrency check counted `None` entry ids as
duplicates, so four identical 409 refusals printed
`<-- TWO REQUESTS WERE GIVEN THE SAME QUEUE ENTRY` — an alarm about collision raised by there being
nothing to collide. It now filters the Nones and says plainly how many of the four triggers were
accepted.

**The general lesson, third time of asking.** A drive harness pinned to a named fixture is only as
true as the fixture, and the fixture is shared, mutable, and edited by every other harness in this
directory. A file whose docstring makes a claim about cost, or about what it is measuring, must
*check* that claim at the top and refuse to run when it is false. Stating it in prose is what
produced two iterations of confident, wrong output.

### What held

With the preconditions enforced, row 6 is clean and the whole of it passes: entries queue durably;
`session_mode: "new"` mints a distinct conversation per request, including under four concurrent
triggers (4 distinct entries, 4 distinct conversations, no collision); the third trigger's
`conversation_id` is **its own**, not the first conversation's; withdrawal is idempotent-by-refusal
(`409 "absent or has already been delivered/withdrawn"`); and `POST /queue/entries/{id}/release`
declines an entry that is not hop-blocked with the best refusal in this file's collection —
*"Queue entry is at hop 0, within the project's hop budget of 6, so the hop budget is not what is
holding it. Check the agent's queue status for the reason it is waiting."* That sentence names the
number, the budget, the conclusion and where to look next.

Rows 5 and 15's API halves are also clean — `t_sweep_conversations.py`, 0 unexpected statuses.
Archiving a conversation with input still queued is refused with the reason
(*"Archiving it would strand them, because nothing delivers into an archived conversation"*),
archive is idempotent, an empty title is refused, and a trigger into an archived conversation is a
409 rather than a silent new one.

### One thing worth an operator's eye, not filed

`GET /projects/{p}/queue/{agent}/status` answers **200 with `waiting_count: 0`** for an agent that
does not exist (`inbound_queue.py:108-125` never loads the `Agent` row). It is the "I could not
look" / "there was nothing there" confusion this file complains about elsewhere, but nothing
currently reaches it: there is no agent-rename route, so a name in the UI cannot go stale, and
archiving is refused outright while entries are still queued (`agents.py:2124-2143`). Recorded so
the next person who adds a rename knows the queue is keyed on the name string.

## Row 5 driven live — the conversation thread holds together, 14 checks, 0 failures

**Driven 2026-08-30, iteration 12, on the 8011 Hub, `proj-1964cdedffe2`, agent `driver` bound to
Haiku. New harness `scripts/drive/t_row5_conversations.py`, two real turns.** Recorded because row 5
had never been driven past its API half, and because everything below is only observable once a
provider has actually replied.

Turn 1 plants a codeword and is told to reply `OK`. The operator then renames the conversation and
sends a second message asking for the codeword back. Every check passed:

| what | result |
|---|---|
| trigger names a conversation, run starts | `conv-c0f582c3d4ae`, `status: "running"` |
| the operator's own message is in the transcript | yes, as `kind: "operator_input"` |
| the agent replied | `agent_output` / `output_kind: "text"` → `"OK"`, ~8s |
| the conversation was given a title, not marked operator-set | yes, `title_set_by_operator: false` |
| a provider session was recorded | `374666cc-…` |
| rename accepted, title is exactly what was typed | yes |
| rename flips `title_set_by_operator` | `true` |
| second message stayed in the **same** conversation | yes, same id back |
| **the agent still knew the codeword** | replied `TANGERINE-I12B` |
| the operator's title survived the next turn | yes — the documented `name_conversation` no-op holds |
| one provider session across both turns | `374666cc…` → `374666cc…`, unchanged |
| conversation idle again, context usage measured | `attention: "idle"`, 17.69% of Haiku's window |

The middle one is the row's whole point. Two triggers, separated by an operator rename, resumed the
same provider session — so a conversation in this product is a real thread and not two runs sharing
an id. Nothing in the API half could have shown that.

**One cosmetic note, not filed.** With no `name_conversation` call the title is the first 115
characters of the opening message, cut mid-word: `'…Reply with only the two characters OK. Do not'`.
It is a placeholder doing its job, and the sidebar ellipsises it anyway; recorded only so the next
person to look at titles knows nothing generates one.

## F138 (B) — three drive harnesses are hard-wired to a forbidden project, and one of them writes

**Found 2026-08-30, iteration 12, while reading `t_hop.py` before trusting it. Fixed in the same
commit.** No damage occurred: the files were read, not run.

`scripts/drive/` carries a standing rule, repeated in `STATE.json`'s limits and in three of the
files' own docstrings — *"never `proj-5e960453` (this repo on the trial Hub) or `proj-18e5d4e0`"*.
Five files enforce it with an explicit `FORBIDDEN` set. Three do the opposite:

```
scripts/drive/t_hop.py:8    P = "proj-18e5d4e0"
scripts/drive/t_loop.py:8   P = "proj-18e5d4e0"
scripts/drive/t_spec.py:5   P = "proj-18e5d4e0"
```

Hard-coded, with no `AW_PROJECT` override and no guard. And `aw.py:16-18` defaults `AW_HUB` to
**`http://127.0.0.1:8010`** — the operator's own trial Hub — with a real key baked in as the
default. So `py -3.11 scripts/drive/t_spec.py`, run with no environment at all, is a request
against the operator's live Hub and their protected project. That is the *default* invocation; the
protection has to be added by the caller, which is backwards.

`t_hop.py` and `t_loop.py` only poll. **`t_spec.py` writes**:

```python
c, b = api("PUT", f"/projects/{P}/project/documents/{DOC}/content", {"document": payload})
```

`DOC` is `spec/changes/indigo-wyvern/spec.html` and `payload` is a fully-formed change-spec about a
ledger library. Running that file replaces the content of that document in `proj-18e5d4e0` — a
project this run is explicitly forbidden to touch — and the operator's only warning is a line five
files down that they would have had to open the file to read.

This is the same class as F137 but a step worse. F137 was a harness measuring the wrong thing.
This is a harness whose *safe* invocation is the one nobody types.

**Fixed**, using the shape the five compliant files already established, so there is one pattern
rather than two:

```python
P = os.environ.get("AW_PROJECT", "")
if P in ("proj-5e960453", "proj-18e5d4e0") or not P:
    print("REFUSING TO RUN: set AW_PROJECT to a drive project. "
          "proj-5e960453 (this repository) and proj-18e5d4e0 are off limits.")
    sys.exit(1)
```

Verified by running each with `AW_PROJECT=proj-18e5d4e0` and with it unset: both exit 1 with the
refusal and issue no request. Refusing the *empty* case as well is deliberate — an unset
`AW_PROJECT` used to mean "use the hard-coded one", and silently falling back to a working default
is how the hazard survived this long.

**Left for the operator.** `aw.py`'s defaults are the other half of this and were not changed:
`HUB` defaults to 8010 and `KEY` to a literal `aw_live_…` for that Hub. Every drive in this
directory is run with all three variables exported, so the defaults serve nobody and point at the
one instance the drive must not disturb. Removing them — or defaulting `HUB` to nothing and
refusing — is a one-line change with no caller to break, but it changes how every file in the
directory is invoked, so it is stated here rather than done unattended.
