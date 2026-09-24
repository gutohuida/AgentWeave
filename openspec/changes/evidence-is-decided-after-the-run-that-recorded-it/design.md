# Design — evidence is decided after the run that recorded it

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B5-2026-09-24.md`, section 2: APPROVE WITH
FIXES) and the operator's **decision 2** of that review changed this design. Checked against HEAD
`d0da83d` (product code unchanged since `404c7d5`).

| Review item | What changed | Where |
|---|---|---|
| **HIGH** — in F358's own scenario the refused agent is never told the row is ready: the reviewer was woken while the author's run was live (`scripts/drive/FINDINGS.md:29419-29424`), nothing stops that delivery, and after D1 its turn ends on `recording_run_live` with nothing to wake it again | **Operator decision 2: re-queue.** New **D7**: `decide` remembers each agent it refuses `recording_run_live`, keyed by the recording run; when that run's registry entry is popped, the Hub queues each such agent one short entry saying the row is ready, in the conversation it was refused in. New origin `evidence` (a migration). New ADDED requirement "An agent held from a decision is told when it can decide" with three scenarios; tests 1.15-1.19 | D7, spec, tasks 1.15-1.19 / 2.8-2.11 |
| **LOW** — a hung run (no maximum turn duration; an `ask_user` wait stays in the registry) holds decisions until stopped | D1's refusal sentence now names stopping the run as a remedy | D1, test 1.1 |
| **LOW** — a revised row keeps its old `produced_at`, while `commit_for_task_review` ("most recent evidence wins", `requirement_evidence.py:785-800`) and change 3's *latest* label order by it | **Decided: a revision bumps `produced_at`** — the revision *is* the most recent recording of that demonstration | D2, spec, test 1.7 |
| (ledger) R3's decision-route 500 | Filed as **F426**; D6 is its fix | D6 |

Nothing else in the review's section 2 asks for a change: it verified that a crashed run left
`running` cannot block decisions (the registry fails open), that D6's wrapper catches
`TimeoutExpired`, that D5's `_git` catches `OSError`/`SubprocessError` (`:475-490`), and that the MCP
client treats 200 and 201 alike.

---

It is S12's F358 half; S12's F165/F166 half is `a-footprint-names-the-line-of-work-its-commit-is-on`,
which D12 governs. Operator decision 2 of the review above governs D7.

## What the code does today (HEAD `404c7d5`)

| Step | Where | What it does |
|---|---|---|
| record | `requirement_evidence.record`, `:97-191` | footprint read **before** the row (`_take_footprint`, `:248-296`), duplicate check (`duplicate_of`, `:194-245`), row written `awaiting` for an agent |
| decide | `requirement_evidence.decide`, `:677-737` | refuses a bad value (422), no grant (403), self-acceptance (403); otherwise appends `EvidenceReview` and sets `review_state` |
| re-point | `restamp_run_footprints`, `:905-997`, called from `_restamp_evidence_footprints` (`agent_trigger.py:1769-1801`) inside the finalize block that sets `run.status`/`ended_at` | every row the run recorded is re-pointed at the snapshot commit, **decided or not** (its docstring: "Every row of the run is re-pointed, whatever has since been decided about it") |
| liveness | `run_liveness.run_is_live`, `:69-71` | membership of `active_ptys`/`active_app_server_runs`; `_execute_run` pops its entry in a `finally` that runs **after** the finalize block (module docstring, `:22-28`) |

So the registry entry covers exactly the window in which a footprint can still change, and its
absence means the footprint is final. That is the same predicate the approval gate already uses for
the same reason (`requirement_gate._check_live_turn`, `:544-579`, F162).

## D1 — `decide` refuses while the recording run is live

```python
if evidence.run_id and run_liveness.run_is_live(evidence.run_id):
    if actor.kind == "agent" and actor.name and actor.run_id:   # D7, same synchronous step
        run_liveness.note_decision_waiter(
            evidence.run_id, agent=actor.name, refusing_run_id=actor.run_id,
            evidence_id=evidence.id,
        )
    raise EvidenceRefusedError(
        f"{evidence.id} was recorded by run {evidence.run_id}, which is still running. Its commit "
        "is re-pointed at the work when that run ends, so a decision now would judge a commit "
        "the Hub is about to replace. Decide once the run has ended"
        + ("; you will be sent a note when it does." if actor.kind == "agent" else ".")
        + " If that run is stuck — hung, or waiting on an answer nobody is giving — stopping it "
        "ends it, and the decision is then open.",
        code="recording_run_live",
        http_status=409,
    )
```

**Stopping the run is a named remedy (review, LOW).** Nothing bounds a turn's duration, and a run
waiting in `ask_user` stays in the registry, so a hung or parked recording run holds every decision
on its rows until it ends. The operator's Stop (`POST …/agent/{agent}/stop`, `agent_trigger.py:1681`)
ends it; `_execute_run`'s finalize block then restamps and pops, as for any other end. The sentence
says so rather than leaving the operator to infer it.

Placed **after all three existing refusals** — value (422), grant (403), self-acceptance (403) —
immediately before the `EvidenceReview` is built (R2: R1 wrote "before the grant check", which would
answer an ungranted agent 409 and contradict R1's own reason and test 1.5). A malformed value is
still 422, and an ungranted or self-deciding agent is told the refusal that does not clear with time
first; only an otherwise-valid decision meets the wait.

**Why refuse rather than accept and re-open.** The alternative is to let the decision stand and
reset it to `awaiting` if the re-point moves the commit. That rewrites a decision the append-only
rule (`requirement-traceability`: "Acceptance and rejection SHALL be recorded append-only") says is
never overwritten, and a reviewer who was told "accepted" would find it undone. Refusing costs a
wait that ends on its own.

**Registry, not `Run.status`.** A crashed Hub leaves `Run.status == "running"` until startup
reconciliation; reading the column would wedge decisions on every row that run recorded. The
registry fails open, as `run_liveness`'s docstring argues (`:8-13`).

**The operator is covered too.** The operator's decision is equally a judgement of a moving commit.
Both routes map `exc.http_status` already (`spec.py:916`, `agent_actions.py:1341`).

**What the routes return when a called function raises.** `decide` raising → 409 (this code), 403 or
422, nothing committed. After a successful decide, `integrate_what_was_waiting_for_this_evidence`
catches everything and rolls back (`task_integration.py:672-707`). **R3 re-ran this and it does not
answer 200** when a task is actually waiting (R1's measurement did not reach the raise — see D6): the
decision is committed and stands, but the route then answers **500**. D6 fixes it.

## D2 — a re-record in the same run revises its own undecided row

In `record`, **for an agent with a run, first look for this run's own matching row** — `duplicate_of`'s
key plus `RequirementEvidence.run_id == actor.run_id` (a keyword on `duplicate_of`, or a second query
beside it). R3: `duplicate_of` returns the **oldest** match (`order_by(produced_at, id).limit(1)`,
`requirement_evidence.py:236-244`), and in D5's own case — a new turn whose checkout starts at the
previous turn's snapshot, where the previous run's row already sits — that oldest row belongs to the
*previous* run, so a same-run check made on it never fires and a second record in the same turn would
mint a third row through D5. When this run's row `already` exists and
`already.review_state == AWAITING`, update `already.kind`, `already.locator`, `already.summary`,
re-apply the footprint just taken — `_apply_footprint(session, already, taken, existing_footprint,
outside_writes=await outside_writes_for_run(session, already.run_id))`. The `outside_writes`
argument is not optional here (R2): `_apply_footprint` writes the column on every mapping and `None`
means *not observed* (`requirement_evidence.py:392-429`), so omitting it would erase what
`capture_footprint` recorded at the first record (`:433-472`),
and return `already` with a `revised` marker for the route. Otherwise the refusal stands.

- Same run means same checkout, same task, same actor — and under D1 nobody can have decided it
  while the run is live. The `review_state == AWAITING` guard covers the one gap: a Hub restarted
  mid-run empties the registry, so a decision could have landed; such a row is refused as today.
- **`produced_at` is bumped to now (operator review, LOW).** The revision is the most recent
  recording of that demonstration, and two readers order by the column: `commit_for_task_review`
  ("the most recent evidence wins", `requirement_evidence.py:785-800`, `order_by(produced_at, id)` at
  `:800`) and `the-coverage-bar-takes-the-evidence-decision-it-asks-for`'s *latest* label (the list
  route's `order_by(produced_at)`, `spec.py:879`). Left at the first record's time, a same-run
  revision would lose to any row recorded between the two, and the coverage bar would name the wrong
  piece as latest. `duplicate_of` also orders by it (`:242`), but D2 no longer reads `duplicate_of`'s
  oldest match for the same-run case, so the bump cannot misdirect it.
- `digest` is **not** revised. If the requirement was reworded mid-turn, `duplicate_of` does not key
  on digest, so the row would move to a wording it was not recorded against. Instead: if
  `already.digest != requirement.digest`, do not revise — record a new row (the old one goes stale
  through the existing mechanism). R2 checked this against `requirement_coverage`: staleness is
exactly `item.digest == requirement.digest` (`requirement_coverage.py:192`, `:310`), so a revised row
keeping its old digest would still read stale, and one moved to the new digest would claim a wording
it was not recorded against — the guard is right.
- Routes: `POST /agent-actions/spec/evidence` (declared `status_code=201`, `agent_actions.py:1184`,
  so the revise branch returns a `JSONResponse(status_code=200)` explicitly) answers **200** (not 201) with the same body plus
  `"revised": true`. `POST /spec/evidence` (operator) never has a run, so never revises.

## D3 — the cross-run refusal names what clears it for an agent

For `actor.kind == "agent"` the last sentence becomes: *"If the work has changed since, record again
once it has: the Hub commits your changed checkout when this turn ends, and evidence recorded after a
change names the new commit."* R1 found this incomplete on its own: a changed checkout still footprints the turn-start commit
**mid-turn**, so a record in a *new* turn with uncommitted changes would still be a duplicate at
record time. **D5 closes that sub-case (R2)**, which makes the sentence true as written. The
operator's sentence keeps *"commit it first"* — for them it is true.

## D5 — an agent's changed checkout is not a duplicate of its committed state (R2, Open Question 2)

When `duplicate_of` finds a row and D2 does not revise it, and the actor is an agent, `record` asks
the footprint root once whether the checkout has uncommitted changes (`_git(root, "status",
"--porcelain")`, this module's own `_git`, 15 s timeout, `None` on failure). Changes present → no
refusal: the new row is recorded, and `restamp_run_footprints` re-points it at the snapshot the Hub
commits when the turn ends, which is a different commit from the earlier row's. Clean, or the
question fails → the refusal stands, as today.

- The git call runs **only on the duplicate path**, so an ordinary record costs nothing new.
- `requirement_evidence`'s own `_git` rather than a `task_integration` helper: `task_integration`
  imports this module, and the check is one command.
- **Only where the turn will be snapshotted.** `_execute_run` commits a dirty tree only for a run
  given an isolated workspace that is not a review checkout (`agent_trigger.py:1033`, `:1341`: a
  review turn and a turn in the project's own checkout pass `worktree=None`). Anywhere else the new
  row is never re-pointed and would be a real duplicate at the same commit — a reviewer's checkout
  dirtied by `.pyc` files is the observed case. So D5 applies only when **the run's recorded
  directory** (`Run.workspace_dir`, written from `effective_work_dir`, `agent_trigger.py:1264` — the
  same directory `_execute_run` snapshots) still exists and lies under `worktrees.task_root` or
  `worktrees.worktree_root` (`worktrees.py:153-188`), never `review_root` (`:207`) or the project
  root; `git status` runs there. R3: keyed on the recorded directory, not on `footprint_root`'s
  answer, because when that directory is gone `footprint_root` falls back to the agent's *own*
  checkout (`requirement_evidence.py:343-348`), which is not the directory the turn's snapshot will
  commit.
- Agents only. An operator's footprint may be a named commit (`_take_footprint`, F71), and their
  sentence still says to commit.
- Test 1.8 (the cross-run control) must stage a **clean** checkout; test 1.12 stages a dirty one.

## D4 — `recording_run_live` on the evidence view

`_evidence_view` (`spec.py:1108-1144`) gains `"recording_run_live": bool(evidence.run_id and
run_liveness.run_is_live(evidence.run_id))`. Registry lookup, no query. The operator routes that
return `_evidence_view` (requirement detail, list, record, decide) carry it. The agent-plane record
response (`agent_actions.py:1238-1245`) is its own dict and gains the same key; the agent-plane
list (`agent_actions.py:1248-1305`) spreads `_evidence_view` and inherits it.

## D6 — a decision route answers the decision it committed, whatever the merge after it does (R3)

**Measured by R3**, not read: a scratch test (deleted) recorded agent evidence, patched
`tasks_awaiting_this_commit` to load a real approved-shaped `Task` (so a transaction is open, as in
production) and `retry_integration` to raise, then called `POST /spec/evidence/{id}/decision
{"decision":"accepted"}`. The decision committed (stored row `accepted`), the wrapper logged and
rolled back (`task_integration.py:702-707`), and the route then raised
`sqlalchemy.exc.MissingGreenlet` at `_evidence_view` (`spec.py:926` → `:1110`): **a bare 500**. The
rollback expires every loaded instance (`expire_on_commit=False` does not cover a rollback —
`turn_scheduler.py:402-404` says the same), and the route reads the expired `evidence` and `review`
to build its answer. The agent-plane route reads `evidence.id` after the same call
(`agent_actions.py:1354-1357`) and fails the same way. R1's "200" was measured with no task waiting,
so the raise it staged was never reached.

The fix: both decision routes build their response **before** calling
`integrate_what_was_waiting_for_this_evidence` (operator: `view = _evidence_view(evidence,
latest_review=review)`; agent plane: the two plain values) and return it afterwards. Integration
changes no field either response carries. Any later reader in those routes (the `spec_updated`
broadcast `the-coverage-bar-takes-the-evidence-decision-it-asks-for` adds) uses the captured id.
Carried here because D1 adds a refusal to the same two routes and the coverage bar's Accept (the
same bundle) consumes the response: a 500 on a decision that stood is what it would render. **Filed
as F426** (`scripts/drive/FINDINGS.md:32808`, "an evidence decision whose merge then fails answers a
bare 500 after the decision is saved"); this change closes it.

## D7 — an agent refused `recording_run_live` is re-queued when the run ends (operator decision 2)

**The gap (review, HIGH).** F358's reviewer was woken by the author's message while the author's run
was still live (`scripts/drive/FINDINGS.md:29419-29424`). Nothing prevents that: turn delivery never
asks `run_is_live` (no caller in `scheduler.py` or `turn_scheduler.py`). Under D1 such a reviewer's
decision is refused, its turn ends, and nothing ever tells it the row became decidable — D1 would turn
F358's wrong decisions into missing ones.

**Where the refused agents are remembered: beside the registry, in memory.** `run_liveness` gains

```python
#: recording run id -> {refused agent -> DecisionWaiter(refusing_run_id, evidence_ids)}
decision_waiters: Dict[str, Dict[str, DecisionWaiter]] = {}

def note_decision_waiter(recording_run_id, *, agent, refusing_run_id, evidence_id) -> None: ...
def take_decision_waiters(recording_run_id) -> Dict[str, DecisionWaiter]:   # pop, synchronous
```

- **Why in memory and not a column or table.** The fact is *about the registry entry*: "this agent is
  waiting for that entry to go". It is only meaningful while the entry exists, and it dies with it on
  a Hub restart, which is the correct pairing — after a restart the recording run is not live
  (`run_liveness`'s docstring, `:8-13`), so the decision is already open and there is no event left to
  wait for. A persisted marker would outlive the only event that could clear it and need a sweeper.
  **The residual, stated:** a Hub restart while an agent waits loses the note; the agent's refusal
  told it the rule (decide once the run has ended), and the operator's coverage bar shows the row
  decidable (`the-coverage-bar-takes-the-evidence-decision-it-asks-for`).
- **No race with the pop.** `decide` checks `run_is_live` and calls `note_decision_waiter` in one
  synchronous stretch (no `await` between them); the transports' `finally` pops the registry entry and
  takes the waiters in one synchronous stretch too. On one event loop the two cannot interleave: either
  the refusal saw the run live and its note is taken by the pop, or the pop came first and the decision
  was not refused.
- **Agents only.** An operator refusal notes nothing: the operator has no queue, and change 3's
  `spec_updated` broadcast after the pop refreshes their screen. An agent actor without a `run_id`
  (none exists on the agent plane today) notes nothing.
- Keyed per agent: a second refusal of the same agent on the same run adds the evidence id and keeps
  the **latest** refusing run (its thread is the one to continue).

**Where the wake fires: right after the pop, on both transports.** `_execute_run`'s `finally`
(`agent_trigger.py:2706-2714`: `run_liveness.active_ptys.pop(run_id, None)` at `:2707`) and
`_execute_codex_appserver_run`'s (`:3250-3254`: `active_app_server_runs.discard(run_id)` at `:3251`)
each call a **synchronous** `_wake_decision_waiters(project_id, run_id)` immediately after the pop and
before the block's only `await` (`outside_writes.flush()`; the comment at `:2709-2713` says nothing
that must happen may go below it, because a cancelled task stops at that await). After the pop, not at
`evaluate_run_end` (`:2558`) or the run-end `redrain_queued_agents` (`:2661`), which run *before* it:
a note sent then could reach a turn that decides while the entry is still registered. The launcher
takes the waiters synchronously and hands the async part to a background task, the pattern
`checkpoint_handover.consider_handover_from_run_end` uses for the same boundary
(`checkpoint_handover.py:301-331`: `create_task`, held in a module set, `RuntimeError` without a loop
dropped). A failure in the background task is logged and never reaches the finished run.

**What is queued — through the queue, as a divergence response is.** The background task opens its
own session and, per waiter, builds an entry with `inbound_queue.new_entry` (`inbound_queue.py:23-69`)
and then calls `turn_scheduler.schedule_agent` (`turn_scheduler.py:271`) — the same two steps
`run_divergence` takes (`_queue_response`, `run_divergence.py:224-271`; `schedule_agent` at `:872-874`).
Through the queue so hop budget, delivery caps and ordering apply, and so an agent that is busy by then
receives it when its own turn ends (the run-end `redrain_queued_agents`, `agent_trigger.py:2661`;
`turn_scheduler.py:695-712`).

- **Conversation: the one the agent was refused in** — the refusing run's `Run.conversation_id`, when
  that conversation is still open and belongs to the agent (read with
  `conversations.get_conversation_by_id`, never `session.get`, for the reason
  `run_divergence._conversation_for_response` gives, `run_divergence.py:311-316`). `schedule_agent`
  refuses an entry with no conversation (F67, `run_divergence.py:284-286`), so where that thread is
  gone the waiter is **dropped and logged**, not given a new thread: a new conversation would need a new
  `ck_conversations_origin` value (`db/models.py:513`) and a MODIFIED to `conversation-lifecycle`'s
  closed origin set, for a note whose whole point is to continue the thread the refusal happened in.
  **Checked against `agent-conversation-workspace`'s "Traffic with no sending conversation binds to
  its sender identity"** (`openspec/specs/agent-conversation-workspace/spec.md:1031-1045`): not
  contradicted. That requirement covers a message with *no* conversation to key on; this note answers
  a call the agent made from a known conversation, and is keyed to it — as `run_divergence`'s
  same-agent response already continues the diverged thread (`run_divergence.py:310-316`).
- **Workspace: the refusing turn's.** `task_id` and `review_task_id` are copied from an entry that
  was delivered into the refusing run (`InboundQueueEntry.delivered_in_run_id == refusing_run_id`,
  `db/models.py:575`; the two columns at `:626` and `:637`), so a reviewer resumes in its review
  checkout (`turn_scheduler._entry_kind`, `:69-81`). A directly-triggered refusing run has no delivered
  entry; both stay `None` and the conversation's own binding decides, as for any message into it.
- **Origin: a new value, `evidence`.** `hop_depth=0`, `origin_agent=None` — it is the Hub's own act.
  Its own value for the reason `models.py:641-649` and migration `0058`'s docstring give for
  `checkpoint` and `divergence`: no operator asked for it and no agent sent it, and borrowing either
  would misstate where it came from in the queue the operator reads. That moves both CHECK constraints
  (`ck_inbound_queue_origin_type` and `ck_inbound_queue_origin_agent`, `db/models.py:651-666`) — a
  migration at **the next free revision at build time** (head is `0105`; change 4 of this bundle and
  four other parked changes also want one), by table recreation as `0058` does. `new_entry`'s allowed
  set (`inbound_queue.py:42-45`) gains it, and `format_turn_prompt` (`inbound_queue.py:105-110`) gains
  a branch rendering the origin as `AgentWeave` — without it the entry would render `Agent "None"`,
  because every origin other than `operator` and `job` falls to the agent branch.
- **Content** (short, facts only): *"You tried to decide ev-a, ev-b while run R was still recording
  them, and the Hub held the decision. That run has ended; ev-a now names commit abc1234, ev-b names
  def5678. They are open for a decision now — read them again first if the commit changed what you
  were judging."* The commits are read from the rows' footprints, which the finalize block has
  committed by the time the entry is popped. A row decided in between (the operator got there first)
  is left out; if none is left, nothing is queued.
- **Once per refusal set.** `take_decision_waiters` pops, so a run's waiters are woken once.

**What the woken turn meets.** The row is decidable (the entry is gone); the recorder's footprints
name the snapshot commit. Nothing about the woken turn is special: if the reviewer is refused again for
another reason (grant revoked), that refusal is ordinary.

## Risks

- **A reviewer that records its own evidence and then asks the operator to decide it** waits on
  `ask_user` while its own run is live, and the operator meets `recording_run_live` until the turn
  ends. The review briefing names only rows that exist when the turn starts
  (`review_turn.verdict_evidence_sentence`, `:178-235`), which were recorded by ended runs, so the
  product does not route anyone into this; D4's field lets a screen say why the decision is held.
- **A hung recording run** holds its rows' decisions until it is stopped (review, LOW). D1's refusal
  names stopping it; D7 then wakes whoever was refused.
- **A Hub restart drops D7's notes** (D7, stated residual). The decision is open after a restart, so
  nothing is blocked; only the reminder is lost.
- **Noticed, not carried:** `format_turn_prompt` renders every `checkpoint` and `divergence` entry as
  `Agent "None"` today (`inbound_queue.py:105-110` has branches only for `operator` and `job`, and
  both origins carry `origin_agent IS NULL`). D7 adds a branch for its own origin only; the existing
  two are for the orchestrator to file.

## Open questions

1. **Retiring a superseded row across runs** (F358 cost 3). Options: (a) an author-only `withdraw`
   that appends a review with decision `withdrawn`, which coverage treats like `rejected` minus the
   "Rejected" wording; (b) leave it — the reviewer's rejection is the retire path. Recommended: (b)
   for this change; (a) as its own change if the operator sees it recur.
2. **The new-turn duplicate** — **decided by R2: (a), written as D5.** One `git status --porcelain`
   on the duplicate path only; a failed call keeps today's refusal, so the fallback is the safe one.

## Round log

- **R1, 2026-09-24.** Re-verified F358 against `404c7d5`; measured the decide route's answer when
  integration raises (200, decision stands). Wrote D1-D4.
- **R2, 2026-09-24.** Re-derived: the registry entry is popped after the restamp on both transports
  (`agent_trigger.py:2461` then `finally` `:2706`; `:3134` then `finally` `:3250`) — holds. Fixed D1's
  placement (after all three existing refusals), D2's footprint re-apply (must pass
  `outside_writes`), and answered Open Question 2 as D5. The agent-plane list already spreads
  `_evidence_view` (`agent_actions.py:1296`), so D4 reaches it with no extra edit.
- **R3, 2026-09-24.** Re-derived without R2's notes. **Ran** the decision route under a raising
  integration with a task actually waiting: it answers **500** (MissingGreenlet after the wrapper's
  rollback), decision committed — R1's 200 never reached the raise. Added **D6** (build the response
  before integrating). D2 now looks for **this run's** matching row first (`duplicate_of` returns the
  oldest match, which in D5's own new-turn case is the previous run's). D5 keys on the run's recorded
  directory, not `footprint_root`'s fallback. D1's placement, D2's `outside_writes` and digest guard,
  D3, D4 and the registry-popped-after-restamp ordering all re-derived and hold.
- **Operator review, 2026-09-24** (`spec-queue/tracks/reviews/B5-2026-09-24.md` §2, operator
  decision 2). Added **D7** (re-queue refused agents when the recording run's registry entry is
  popped; new queue origin `evidence`, a migration). D1's refusal names stopping the run. D2 bumps
  `produced_at` on revision. D6 named as F426's fix. Citations re-verified at `d0da83d`.
