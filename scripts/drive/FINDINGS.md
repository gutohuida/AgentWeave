# Findings — driving AgentWeave

Project under test: `ledger-stress` = `proj-18e5d4e0` at `C:\Users\huida\Documents\aw-stress`
Trial Hub `127.0.0.1:8010`. Agents: `builder`/`critic` (Haiku 4.5), `relay` (gpt-5.4-mini).
Settings for the test: `hop_budget=2`, `allow_agent_jobs=true`, `main_branch=master`.

Severity: **A** = wrong behaviour an operator will act on · **B** = wrong/misleading surface ·
**C** = friction or vestige.

---

## F1 (A) — One cron string, three different answers; the one on screen is wrong

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

Every agent created through `POST /projects/{id}/agents` comes back with
`"contact_mode": "watchdog-spawn"` (measured: `agent-61634fab`, `agent-ee3a289d`, `agent-b38ef2b7`).
The watchdog was deleted and CLAUDE.md lists `watchdog.py` among the modules that must never be
recreated. The name survives on the public API surface as the default value of a field, which
means the first thing a new integrator reads about how agents are contacted names a subsystem that
does not exist.

## F4 (C) — A fresh project does not adopt the main branch it can already see

`POST /projects/open` on a git repository returns `main_branch: null`, while
`GET /projects/{id}/main-branch-suggestion` immediately answers
`{"suggestion": "master", "chosen": null, "is_repository": true}`. The Hub knows the answer at open
time and still requires the operator to go and confirm it in settings. Everything downstream that
needs a base branch (worktree isolation, conflict detection, evidence footprint re-stamping via
`project.main_branch`) is degraded until they do, with no prompt saying so.

## F5 (A) — The hop budget is defeated by any operator message, and the counter resets

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

While `run-f8f7a33c` was live on `task-cdd990b1`, the task read:

```
status: in_progress    assignee: null    assignee_status: "idle"
```

The run *was* bound to the task — `bind_run_to_task` moved it to `in_progress`, which is the only
reason its status changed. But nothing wrote the agent's name to `assignee`, and
`assignee_status` is derived from that null, so it reports `idle` about an agent that is at that
moment running. A board watcher sees an in-progress, unassigned card whose assignee is idle.

## F7 (C) — Duplicate evidence for one requirement is accepted without comment

`builder` recorded evidence for FR-1 unprompted on its first turn (`ev-42cad5d2`), then recorded
the same fact again when asked (`ev-5d0273ad`) — same requirement, same task, same commit, near
identical prose. Both were stored, both entered `review_state: awaiting`, and coverage read
`evidence_count: 2, accepted_count: 0`. The reviewer has to decide twice about one fact, and
`evidence_count` overstates what was demonstrated.

Note the `digest` field is *not* a duplicate detector — it pins the requirement's wording at
production time (`requirement_evidence.py:113`), which is a different and well-designed mechanism.
There is simply no duplicate check.

## F8 (C) — Two refusals, two standards of helpfulness

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

## F11 (B) — `run_count` counts firings that did nothing

**Confirmed.** After the loop's life: `run_count = 9`, of which only **4** spawned an agent. The
rest were skips (`loop queue is stalled`, `loop queue is empty`). `scheduler.py:796-797`
increments `run_count` and stamps `last_run` *before* any skip branch runs, so both fields describe
"the scheduler considered this job", not "this job ran". A card reading "9 runs · last run 18:01"
overstates by more than 2x, and `last_run` points at a firing that did nothing.

The `JobRun` rows themselves are honest — they carry `status` — so the `Last 5` health dots are
right while the count beside them is wrong.

## F12 (A) — `stop_when_queue_empties` waits for a human, and burns a firing a minute meanwhile

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

## F13 (B) — Re-enabling a finished loop is accepted, useless, and leaves a contradictory state

`PATCH /jobs/{id} {"enabled": true}` on a loop that stopped with `ending_state: completed` returns
`200` and `enabled: true`, while the same response still carries `stop_reason: "loop queue is
empty"`, `stopped_at: 2026-08-23T18:00:00Z`, `ending_state: "completed"`. So the loop is
simultaneously enabled and finished.

One minute later it fired (`run_count` 8 → 9), immediately re-stopped, and set `enabled: false`
again. The operator's action was silently undone; the only account of why is a history row.

Nothing refuses the toggle or says "this loop has finished — give it work or create a new one",
which is what the operator actually needs to hear.

## F14 (B) — A task waiting on the operator still reads `in_progress`

`ask_user` worked well: `builder` asked a structured question with two labelled options,
`blocking: true`, `asker_waiting: true`, and the answer reached the agent, which then completed the
task. The whole operator-in-the-loop path is sound.

But while the run sat blocked on the question, its bound task read `status: in_progress`,
`blocked_reason: null`. `block_task_for_question` is called from exactly one place —
`run_divergence.evaluate_run_end` (`run_divergence.py:325-326`) — so a task only parks to `blocked`
if the run **ends** with the question unanswered. During the wait, which is the whole point, the
board says the work is progressing.

## F15 (C) — Stopping an agent does not stop the work

`POST /agent/builder/stop` behaved correctly: the run went to `stopped` (not `failed`), `ended_at`
was set, and the already-delivered queue entry was not spuriously returned.

But `critic` had meanwhile messaged `builder`, so a *new* builder run (`run-448817a1`) started
moments after the stop. The stop endpoint stops **one run**, and the queue immediately starts
another. There is no "pause this agent" — the only lever is per-run, and a peer conversation
outlives it.

## F16 (C) — `loop_id` is accepted on task creation but never echoed back

`POST /tasks {"loop_id": "loop-8e8379bb"}` returns `201` with `"loop_id": null` in the body, while
the loop's own summary immediately shows `queue: {pending: 2}` and names the task as
`current_task`. The write worked; the response denies it. There is no way to confirm from the
create call that a task joined the loop.

## F17 (B) — Every Hub-run agent says "No activity yet", forever

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

The board screenshot shows `@builder · Idle` chips on the tasks the **loop** claimed
(`scheduler.py:979` sets `claimed_task.assignee = job.agent`) and no assignee at all on the task a
**direct `task_id` trigger** bound. Two paths reach `in_progress`; only one names who is doing it.

## F19 (C) — A gated task is indistinguishable from an ordinary pending one

`task-b74d1511` ("Add a trial-balance report") depends on two unapproved tasks and cannot start.
On the board it renders exactly like any other pending card — `Pending`, `Medium`, its requirement
chips. Nothing marks it gated.

The data is available: `GET /tasks` returns a populated `prerequisites` array with each
prerequisite's status. `TaskCard.tsx` and `TasksBoard.tsx` reference neither `prerequisites` nor
`dependents` (grep: no matches). The dependency information is one tab away, on the Dependencies
board, but the operator has to already suspect there is something to look for.

## F20 (C) — Deep links use query parameters, and nothing says so

`/projects/{id}/tasks` silently renders Overview. The app has no router dependency; destinations
are query parameters read from `window.location.search` (`navigation.ts:327-375`), so the working
URL is `/?project={id}&tab=tasks`. This is a deliberate design (`useWorkspaceNavigation.ts` cites
"design.md decision 9 — no routing"), and it works — but an unknown path shape falls back to
Overview without comment rather than 404ing or correcting itself.

## F21 (B) — A Haiku agent cannot reach `record_evidence`, and burns a whole turn trying

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

## F22 (B) — Shared dependencies are not symlinked on this machine, and nothing says so

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

Same session. Before any real firing, the card showed the `0 runs` chip while Recent Runs displayed
one entry. `run_count` counts firings that actually ran, so a queue that has only ever refused is
honestly zero — and it went to `2 runs` once real firings happened, confirming the intent. But the
chip and the list are two counts of the same word on one card, and they disagree on first read.

---

## F26 (C) — the board names a different agent than the task's assignee

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
