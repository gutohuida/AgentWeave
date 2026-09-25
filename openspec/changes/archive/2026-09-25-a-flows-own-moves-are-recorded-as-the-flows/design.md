# Design — a flow's own moves are recorded as the flow's

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B3-2026-09-24.md` §4) verdict was
**APPROVE WITH FIXES**. **The operator accepted D8 as designed**: a recorded cause, not a third actor
kind; a review staged late by a divergence restaff stays "You moved"; a manual Run press reads
"Loop X moved"; the 38 existing rows keep "You moved". Fixes applied (re-verified on HEAD `a50a49b`):

- **Signature, aligned with S13.** S13 (`a-flow-stages-its-review-in-the-dispatch`, REVISING, not
  edited here) rebases onto `enter_selected_task(..., origin, job_id)` (its design, *Collisions*).
  This change's task 2.3 now **defines that signature**:
  `enter_selected_task(session, task, *, agent, is_review, origin=ORIGIN_ACTOR, job_id=None)`,
  passed through unchanged to both `apply_transition` calls, which validates the pair (D2). Chosen
  over R3's `job_id`-only form because it is the cleaner one, not only because S13 expects it: the
  dispatch at `agent_trigger.py:898` reads a *cause* off the delivered entries, and a cause is the
  `(origin, job_id)` pair `apply_transition` already takes. One vocabulary from the entry to the row,
  one validation point, and a later cause (the divergence question in *Interaction*) needs no new
  parameter. S13 needs no rebase beyond what its text already says.
- **Task 1.5's source scan would trip** on the MCP `task_history` docstring, which will name
  `origin: "job"`. The scan is now AST-based: it finds the `ORIGIN_JOB` symbol and `origin=`
  keyword arguments with a literal value, never text in a docstring.
- **Line number:** `new_entry` is at `inbound_queue.py:24`, not `:50` (D5 corrected).
- **Cross-reference.** `task-lifecycle-governance`'s *"The system may cause a transition without
  becoming an actor"* (`openspec/specs/task-lifecycle-governance/spec.md:580-607`) now carries a
  MODIFIED delta saying a scheduled job's move acts **as the operator**, as the runtime's acts as the
  run.
- **Stale text.** `spec-queue/tracks/B3.md:328` (outside this change; not edited) and this design's
  *Interaction* said S13 never mentions this change. S13's R2 added a *Collisions* paragraph, a
  governance sentence and task 1.14c, consistent with this change; *Interaction* is corrected.
- The operator's three D8 answers are pinned: control 1.3d (divergence restaff stays the operator's
  request), 1.3c (manual Run press is the loop's), and D2's no-backfill rule (old rows).

**Built on the recommended answer to D8**: *no new actor kind; a new recorded cause (`origin="job"`)
naming the job, with the operator's authority unchanged.* **If the operator answers otherwise** (a
third actor kind), this change is withdrawn: that answer must first modify
`task-lifecycle-governance`'s *"The system may cause a transition without becoming an actor"*
(which forbids it) and give every edge of `TRANSITIONS` a declaration for the new kind; the tests in
group 1 that assert what the history *says* would carry over, the ones about origin would not.

## Context — re-verified on HEAD `404c7d5`

| Finding | Still open? | Evidence |
|---|---|---|
| F47 | open, moved | `scheduler.py:906` and `:908` pass `operator()` (F47 cited `:828`/`:830`; the code moved, not the defect). `ACTOR_KINDS` still two (`task_transitions.py:36`) |
| F120 | open, same defect | rows written by those two lines are the `pending→assigned` rows F120 captured |

The staging function has **three** callers, not two (`grep -n "enter_selected_task(" hub/hub`):
`scheduler.py:3336` (`_do_fire_job`), `scheduler.py:3709` (`_stage_selection`) and
`api/v1/agent_trigger.py:898` (a review dispatched by the operator by hand — F76's repair). Only the
first two are a scheduled firing.

**Can the third caller travel an edge on a flow's behalf? Yes — R1's "operator only" was wrong (R2).**
`trigger_agent_directly` does not take `review_task_id` only from the operator's request: when none is
passed it reads it off the entries being delivered (`agent_trigger.py:823-824`,
`_review_task_from_entries` `:431-461`). Three producers write `InboundQueueEntry.review_task_id`: the
operator's trigger (`:1582`), a flow's review selection (`scheduler.py:3417-3419` and `:3747`,
`origin_type="job"`) and a divergence restaff of a failed review (`run_divergence.py:483`,
`origin_type="divergence"`). On `:8000`, read `mode=ro`: 17 job-origin and 3 divergence-origin entries
carry one. All of them reach `:898`. Whether an edge is travelled there depends only on the task's
status at delivery: the flow staged `under_review` when it queued the entry, so normally the `pass`
branch runs — but nothing withdraws a queued review entry when its task leaves review, and
`under_review → revision_needed → in_progress → completed` is legal for either actor
(`task_transitions.py:134-146`). A flow-queued review that waited (agent busy, provider hold) while
that happened travels `completed → under_review` at `:898` with `operator()` and `origin="actor"` —
the defect this change fixes, through the one caller it left alone. And after S13 (below) this is the
flow's **only** staging path, so fixing it here is not a corner case but the change's durable half.

**So the cause travels with the entry.** `InboundQueueEntry` gains `job_id` (nullable `String(64)`, no
FK, same migration); `new_entry` takes it; the two scheduler `new_entry` calls (`:3404`, `:3736`) pass
`job.id`. At `:898` the cause is read from the delivered entries that name the review task: if any has
`origin_type == "operator"`, the operator asked (`origin="actor"`, as today); otherwise, if one has a
`job_id`, the move is that job's (`origin="job"`). A divergence-origin entry keeps today's recording —
the restaff is the Hub acting on the operator's divergence policy, a cause this change does not name
(see Interaction).

## D1 — Options for D8

1. **A recorded cause, not an actor** (recommended). `origin` already exists to answer *"what caused
   this transition to be requested"* (`db/models.py:829-842`); `runtime` is its only non-actor value
   today. Adding `job` records the fact F47/F120 ask for, meets the existing requirement's cause
   clause, and moves no guard: `is_allowed` reads `actor.kind`, which stays `operator`; the
   author/reviewer guards read `actor.agent`, which stays `None`, exactly as today.
2. **A third actor kind** (`flow`/`system`). Forbidden by the shipped requirement and costs an edge
   declaration per status pair, plus every `is_operator` branch (`tasks.py:676, 1319, 1335, 1418`).
   It would also make a flow's authority a separate thing the operator must reason about, when the
   operator granted it by creating the flow.
3. **Leave it, relabel in the UI.** Not possible: the row carries nothing that distinguishes a
   flow's move from the operator's.

## D2 — The column and the value

- `ORIGIN_JOB = "job"` in `task_transition_service.py:563-565`; `ORIGINS` gains it.
- `TaskTransition.job_id: Optional[str]`, `String(64)`, nullable, indexed not required, **not a
  ForeignKey** (the same SQLite drop trap `models.py:708-712` records). Jobs are never deleted
  (`jobs.py:1174-1187` refuses), so the id stays resolvable.
- `InboundQueueEntry.job_id`, same shape (R2; see Context) — the only way the cause survives from the
  firing that queued a review to the dispatch that stages it.
- `apply_transition(..., origin, job_id=None)`: raises `ValueError` unless
  `(origin == ORIGIN_JOB) == (job_id is not None)`, and unless `origin != ORIGIN_JOB or
  actor.is_operator`. Programming errors, not refusals — same class as the existing `origin` check at
  `:589-590`.
- Divergence resolution (`:701`) becomes `if origin != ORIGIN_RUNTIME:`. Today a flow's staging
  resolves divergences because it is recorded `actor`; keeping that is the no-behaviour-change path.
  `run_advanced_its_task` (`run_task_binding.py:955-975`) filters by `run_id`, which a job move never
  carries, so it is unaffected.

Why the job and not the firing (`JobRun.id`): `_prune_job_history` evicts `JobRun` rows, and an
append-only record must not name something that will disappear. The job is durable.

## D3 — What the history says

`_transition_view` (`tasks.py:1616-1638`) adds `job_id`, `job_name` and `job_kind` (`"flow"` or
`"loop"`; one `AIJob` + `Loop` lookup per distinct id in the response; `None` if not found). Both
staging callers are loop firings (`_do_fire_job` and `_stage_selection` both hold a `Loop`), and a
flow is a loop with a `spec_document_id` (`mcp_server.py:761` `create_flow` vs `:676` `create_loop`),
so labelling every row "Flow" would misname a plain loop's moves (R2). `TaskTransitionHistory.tsx`:

| origin | who | verb |
|---|---|---|
| `job` | `Flow <job_name>` when the job's loop has a `spec_document_id`, else `Loop <job_name>` (or `A scheduled job` when the job is not found) | `moved` |
| `runtime` | unchanged | `was moved for` |
| `actor` | unchanged (`You` / agent / `A run`) | `moved` |

The MCP `task_history` docstring (`mcp_server.py:322-334`) names the new origin.

## D4 — What the route returns when what it calls raises

`GET /tasks/{id}/transitions`: the job-name lookup is a read in the same session; a raise there is a
500 like any other read failure today, and the lookup is skipped entirely when no row has a `job_id`.
The scheduler's staging runs inside the firing's transaction: a `ValueError` from the new argument
check would abort the firing exactly as a refused transition does today — which is why the check is
exercised by a unit test rather than discovered in a live firing.

## D5 — Does every path that queues a loop's review carry the job? (R3)

- **Producers.** `InboundQueueEntry` has one constructor, `inbound_queue.new_entry`
  (`inbound_queue.py:24`); no path copies an entry. `origin_type="job"` is written at exactly two
  sites, `scheduler.py:3407` (`_do_fire_job`, plain jobs and loops alike) and `:3739`
  (`_stage_selection`); both hold `job`, so task 2.2 covers every job-origin entry. The other writers
  of `review_task_id` are the operator's trigger (`agent_trigger.py:1582`) and a divergence restaff
  (`run_divergence.py:259-267`, `:483`), which are not a job's by construction. Checkpoint entries
  (`checkpoint_cutover.py:133`, `checkpoint_trigger.py:239`) carry no review task. An entry returned
  to the queue after a failed run is the same row, so its `job_id` survives the retry.
- **The migration.** `inbound_queue_entries.job_id` and `task_transitions.job_id` go in one
  migration, nullable `String(64)`, no FK, no backfill. `TaskTransition.origin` has no CHECK
  constraint (`db/models.py:710` records why), so admitting `job` needs no table rebuild.
- **Readers of `origin`.** Only `apply_transition`'s divergence resolution
  (`task_transition_service.py:701`) and `run_task_binding.py:973` (`== ORIGIN_ACTOR`, filtered by
  `run_id`, which a job row never has) branch on it; F167's wedged-review recovery reads
  `actor_kind`, which stays `operator`.
- **A manual Run press** fires `_do_fire_job` too, so the selection it stages is recorded as the
  loop's (`origin="job"`), not "You". Deliberate: the loop chose the task; the operator chose only
  *when*. The `JobRun.trigger` that would distinguish them is not durable (D2's reason for naming the
  job).

## Interaction

- **B1 / S1** rewrites the attending helpers the flow's selection reads, and **S13** moves where the
  flow stages `under_review` (into the dispatch). Whichever of those lands first, the staging call it
  leaves must still pass `job_id`; the source scan in task 1.5 fails if a scheduler-side staging call
  drops it.
- **S13 is the sharp one** (`a-flow-stages-its-review-in-the-dispatch`, B1, R1 only). It stops the
  firing staging a review and leaves `:898` as the only place a flow's review is staged. R1 of this
  change recorded that whichever landed second must carry the job cause through the queue entry; R2
  moved that work **into this change** (Context, above), because the entry-delivered path already
  exists today. After R2, S13 needs nothing from this change beyond keeping `:898`'s cause read.
  S13's R2 has since recorded this change (its design *Collisions*, a governance sentence, and its
  task 1.14c) and names the build order: this change first, S13 rebasing onto
  `enter_selected_task(..., origin, job_id)` — the signature task 2.3 defines (operator review).
- **Divergence restaffs** are left recorded as the operator's request — **accepted by the operator
  2026-09-24** (a review staged late by a divergence restaff stays "You moved"). The spec's cause
  clause arguably reaches them too (the Hub acting on the operator's divergence policy); naming that
  cause is a separate, later question, and the `(origin, job_id)` signature leaves room for it.

## Round log

- R1 (2026-09-24): written. Not yet compared by R2/R3.
- R2 (2026-09-24): R1's claim that `agent_trigger.py:898` only transitions on an operator dispatch is false — the review task id is read from delivered entries, and flow- and divergence-queued entries carry one. The job cause now travels on `InboundQueueEntry.job_id`. Loop vs flow labelling corrected. Every other claim (`ORIGINS` at `task_transition_service.py:563-565`, divergence resolution at `:701`, the three callers, the pin at `test_flow_chain_end_to_end.py:342-352`, jobs never deleted `jobs.py:1174`, `TaskTransitionHistory.tsx:40-44`) re-read and holds.
- R3 (2026-09-24): every job-origin producer re-derived (two, both covered); no entry is copied; `origin` has no CHECK; its readers are unaffected. Added D5; recorded that a manual Run press is attributed to the loop. S13 still does not mention this change (B1 is at R1) — the B3 record's Final lists what B1's R2/R3 must check.
- Operator review (2026-09-24): D8 accepted as designed; `enter_selected_task` takes `(origin, job_id)` to match S13; task 1.5's scan made AST-based; `new_entry` line corrected; MODIFIED delta for *"The system may cause a transition without becoming an actor"*; control 1.3d. See the section at the top.
