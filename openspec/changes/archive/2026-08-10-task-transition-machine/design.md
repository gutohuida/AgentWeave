## Context

`update_task_for_actor` (`hub/hub/api/v1/tasks.py:172`) is the single function through which every
task mutation passes. Both routes reach it: the operator's
`PATCH /api/v1/projects/{id}/tasks/{task_id}` (`tasks.py:214`, passing `updated_by_run_id=None`) and
the agent plane's `PATCH /api/v1/agent-actions/tasks/{task_id}` (`agent_actions.py:234`, passing
`actor.run_id`). That shared choke point is the reason this change is small: there is one place to
put the machine, and the actor distinction already arrives there.

What it does today is `if body.status is not None: task.status = body.status` — no adjacency, no
actor rule — followed by `task.updated_by_run_id = updated_by_run_id`, a single mutable column
(`hub/hub/db/models.py:529`) that the next write erases.

Two constraints from `CLAUDE.md` shape the work: a new migration must guard for a missing table
because upgrades from an early revision reach it with only that revision's tables, and
`hub/hub/mcp_server.py` is spawned standalone and may import only stdlib + fastmcp, so anything it
restates needs a test asserting the two agree.

One useful thing already works: `_hub_request` (`hub/hub/mcp_server.py:132-162`) raises `HubAPIError`
with the parsed `detail` on any non-2xx. A refusal returned as a proper HTTP error therefore reaches
the agent as a tool failure without adapter changes — the requirement is to keep the detail readable
and prove it with a test, not to build a new failure path.

## Goals / Non-Goals

**Goals:**

- One declared transition map, enforced for every caller, with refusals that say what is reachable.
- An append-only history that can answer "who completed this, and who approved it" — a question the
  current schema cannot express at all.
- Author/reviewer separation for agent runs, with the operator explicitly exempt.
- A seam that B3's evidence checks and B4's completion gates plug into rather than sit beside.

**Non-Goals:**

- Deciding whether a task has *earned* a status (B3/B4), rendering the history (B5), or changing
  requirement traceability. See the proposal's Non-Goals.
- Backfilling history for tasks that predate the change.
- Reworking run identity — `AgentActor` is used as it stands.

## Decisions

### D1 — Enforce in `update_task_for_actor`, not in the routes

The two routes already converge there, so one implementation covers HTTP and MCP and cannot drift.

*Alternative rejected:* enforcing per route. That is two copies of the rule, and the MCP path would
be the one that gets forgotten — which is exactly how the current hole came to be reachable from
`update_task` in the first place.

### D2 — Pass the actor explicitly instead of inferring it from a null run id

`update_task_for_actor` currently takes `updated_by_run_id: Optional[str]`, and "operator" is
implied by `None`. The signature becomes an explicit actor (kind plus optional run id).

*Why:* "no run id" and "the operator" are not the same proposition. Today they coincide because only
two call sites exist, but a future path that loses a run id would silently acquire operator
privileges — including exemption from self-approval. Making the claim explicit means a caller has to
state it.

*Alternative rejected:* keep inferring. Cheaper now, and the failure mode is a privilege escalation
that no test would obviously catch.

### D3 — A `task_transitions` table, not a JSON column on `Task`

Columns: `id`, `project_id`, `task_id` (FK to `tasks.id`), `from_status`, `to_status`, `actor_kind`,
`run_id` (nullable), `created_at`. Indexed on `(task_id, created_at)`.

*Why a table:* the author/reviewer rule is a query — "the run of the most recent transition into
`completed`" — and rows answer it directly. `project_id` is denormalised so project-scoped reads do
not need a join, consistent with the rest of the schema.

*Alternative rejected:* a JSON list on `Task`. Read-modify-write on every transition, which is the
same last-writer-wins race the change exists to remove, and not queryable.

*Alternative rejected:* deriving history from the existing event log. `CLAUDE.md`'s capability spec
already states event logs MUST NOT be the only source of attribution, and events are a reporting
stream, not an integrity record.

### D4 — Append-only is enforced by having no write path, not by a database trigger

The service exposes `record_transition` and reads. No update or delete against the table exists in
application code, and a test asserts none appears.

*Alternative rejected:* database-level immutability triggers. SQLite and Postgres would need
different implementations, and it protects against a threat — someone editing rows out of band —
that already implies filesystem access to the database.

### D5 — The map is declared once, in the Hub, and pinned to the existing status lists by test

The statuses are declared twice already (`src/agentweave/constants.py:280`,
`hub/hub/schemas/tasks.py:15`). The map is a third file's worth of knowledge and must not become a
third copy of the *statuses*. It is defined in a new Hub module, and a test asserts its key set
equals both existing lists exactly — so adding a status without declaring its transitions fails
rather than producing a status nothing can reach.

**An edge carries who may take it.** The operator decisions of 2026-08-10 (Open Questions 1–3,
resolved) do not produce a second map for operators — they produce one map whose edges name their
permitted actors. Most edges are open to both; a few are the operator's alone.

The map, following the lifecycle in `CLAUDE.md`:

| From | To | Who may |
|---|---|---|
| `pending` | `assigned`, `in_progress` | both |
| `assigned` | `in_progress`, `pending` | both |
| `in_progress` | `completed`, `assigned` | both |
| `completed` | `under_review` | both |
| `under_review` | `approved`, `revision_needed`, `rejected` | both — subject to actor separation |
| `revision_needed` | `in_progress` | both |
| `pending`, `assigned`, `in_progress`, `completed`, `revision_needed` | `rejected` | **operator only** |
| `approved` | `revision_needed` | **operator only** |
| `rejected` | `pending` | **operator only** |

Consequences worth stating: `approved` and `rejected` are **not** terminal, but their only exits
belong to the operator. An agent that reaches either has finished with the task. And "the operator is
bound by the map" (D9) remains true — the operator has *more edges*, not permission to ignore the
map, so a forced-move override is not needed and is not built.

### D6 — Refusals are typed HTTP errors with distinct codes

- Illegal transition → **409 Conflict**, detail naming the current status and reachable set.
- Actor not permitted (self-approval) → **403 Forbidden**, detail naming the rule.

*Why not 422:* the request is well-formed. What is wrong is the state or the actor, and conflating
those with a schema failure would make the agent try to fix its payload.

### D7 — Restating the current status is a no-op that records nothing

Otherwise a retried call — which the agent plane can produce — manufactures a `completed → completed`
transition, and the "who completed this" query starts returning the retrying run.

### D8 — No backfill

The migration creates an empty table. A pre-existing task's history begins at its next transition.
Inventing a synthetic "created as pending" row would put a claim in an integrity record that nothing
observed.

### D10 — Creation is constrained, and the transports are levelled by narrowing

Found by the 2026-08-10 scan, after the first draft: the machine was walkable around. `Task` is
constructed in exactly one place (`hub/hub/api/v1/tasks.py:65`) — the choke-point premise holds for
creation as it does for update — but that one place applies `status=body.status`, and both
`TaskCreate` and `AgentTaskCreate` (`hub/hub/api/v1/agent_actions.py:71`) validate membership in the
eight without caring *which* of the eight. A task could therefore be born `approved`.

Entry statuses are `pending` and `assigned`. `assigned` is included because creating a task already
directed at an agent is ordinary, and forcing `pending` then an immediate transition would add a
recorded move that says nothing.

*On the transport asymmetry:* MCP's `create_task` never exposed `status`, so it was already
narrower than HTTP — which `agent-capability-plane` forbids. Levelling by **narrowing HTTP** rather
than widening MCP is the choice that also fixes the hole; widening MCP would have propagated it.

*Creation records no transition.* A history entry describes a move. The entry status is a property
of the task, already visible on it, and inventing a `∅ → pending` row would put a non-event in an
integrity record (consistent with D8).

### D11 — One small UI slice, because otherwise the operator's authority is theoretical

The same scan found the task board is read-only: `useUpdateTask` exists in
`hub/ui/src/api/tasks.ts:34` and has **no callers**, and every button in `TasksBoard.tsx` and
`TaskCard.tsx` is a filter or an expander. D9 gives the operator exclusive edges — early rejection,
reopening — that they could not reach anywhere in the product.

So `TaskCard` gains a status action offering **only the transitions legal for the operator from the
current status**, derived from the same map. Offering all eight and letting the API refuse would
teach the operator to expect failure from their own controls.

*Alternative rejected:* ship backend-only and rewrite the human verification steps to use `curl`.
Honest, but it leaves half the design unusable, and the test guide would be verifying the API rather
than the product.

*Alternative rejected:* defer the operator edges to B5. That keeps B1 backend-pure, but ships a
machine whose refusals the operator cannot override anywhere — the worst intermediate state.

### D13 — The UI reads one actor-scoped map, not per-task permissions

Settled before implementation (it was parked inside task 7.1, and an unmade decision inside a task
list is where estimates break). The client needs to know which moves to offer without holding a
second copy of the map in TypeScript. Three options were considered:

1. **`allowed_transitions` on the task response.** Rejected. The legal set is *per-actor*, so the
   same task would return different JSON to an agent and to the operator. A representation that
   varies by who asked breaks the assumption every consumer and every cache makes about a resource —
   including React Query, whose key is the task, not the task-and-asker.
2. **A per-task permissions endpoint.** Rejected. A board with forty cards makes forty requests to
   render, and the answer is identical for every card in the same status.
3. **One actor-scoped map endpoint** — chosen. It returns the caller's own view of the map,
   `{from_status: [reachable...]}`, once. The client derives a card's options from the task's
   current status by lookup.

This keeps the map single-sourced (option 3 serves the same declaration the service enforces),
costs one request per session rather than per task, and leaves the task response actor-independent.
A stale map can still offer a move that has since become illegal, which is why task 7.3 requires the
refusal to be surfaced rather than swallowed.

### D12 — Assignment stays ungoverned, and that is recorded rather than silently omitted

`TaskUpdate.assignee` can be set by any actor, with no entitlement check. It is one of the three
things the operator named as depending on agents remembering, so its absence here needs a reason:
an assignment rule worth having ("only the assignee may complete") depends on knowing which run is
working which task, and that binding does not exist
(`openspec/explorations/2026-08-10-enforcing-the-development-cycle.md`). Building assignment rules
first would mean guessing at the edge that change will create.

### D15 — `completed → under_review` stays, and the question stays open

Task 9.6 asked the operator, after real use, whether the separate review hop is meaningful or an
empty formality an agent performs twice in a row. Answered 2026-08-10: **too early to say.**

The reasoning is worth keeping, because it is a better answer than either option on offer.
`under_review` currently holds nothing — no evidence, no reviewer assignment, no gate outcome —
so judging it now would be judging an empty state, and it would feel like a formality *whatever it
is eventually for*. B3 is what gives it content. Deciding on today's experience would settle the
question on the wrong evidence.

So the map is unchanged, and this is not deferred indefinitely: it is deferred to the point where
the state has something in it. Revisit when B3 lands.

*Alternatives considered and not taken, recorded so they need not be re-derived:* merging the two
statuses so `completed` means done-and-awaiting-review, with author/reviewer separation guarding
`completed → approved` (one fewer move, same protection); or auto-advancing, where an agent's move
to `completed` also records `completed → under_review` (keeps the audit distinction, removes the
click, costs two rows per completion).

## Risks / Trade-offs

- **The map is wrong for how the operator actually works, and legal moves start getting refused.**
  → The three uncertain edges are Open Questions, answered before implementation rather than
  discovered in use. The map is one declaration, so correcting it is a one-line change plus a test.

- **Existing tests and seeded fixtures move tasks in ways the map forbids.** → **Smaller than first
  estimated.** This section originally predicted the suite would "light up". A scan on 2026-08-10
  found only `hub/tests/test_codex_appserver.py` mentions `approved` or `under_review` at all, and
  incidentally. Triage remains a task (6.1) but should be budgeted as minutes, not as a phase. The
  original estimate is corrected here rather than left standing, because an inflated risk is as
  misleading as a missed one.

- ~~**Author/reviewer separation is only as good as run identity.**~~ **This was wrong, and live
  use proved it within an hour.** The original text accepted that "a single agent could complete on
  one run and approve on its next" and filed it as collusion to be handled by B3/B4. It is not an
  edge case: **every turn is a new run**, so a run-based check is satisfied by an agent merely
  continuing its own work, and it forbade nothing. On 2026-08-10 the operator's agent completed
  `task-4c9b26e7` on `run-1ecc4ec7` and approved it on `run-6d704bb8`, and the rule passed it.
  → Fixed in **D14**: the comparison is on agent identity, and `task_transitions` records
  `actor_agent` (migration `0053`). The lesson worth keeping is that "accepted limitation" was the
  wrong category for something on the main path — it should have been a design error.

- **`completed → under_review` as a separate hop may just become a formality an agent always does
  twice in a row.** → Left as-is for now; if it proves to be noise, collapsing it is a map edit.

- **MCP failure text is the agent's only feedback.** If `detail` is unreadable, a refused agent
  cannot self-correct and will retry blindly. → The reachable-set text is part of the requirement,
  and a test asserts the detail survives `_readable_detail` intact.

### D14 — Author and reviewer are distinct *agents*, not distinct runs

Added 2026-08-10 after the first live run. The rule as first built compared `run_id`; see the
struck-through risk above for why that forbade nothing.

`TaskTransition` therefore records `actor_agent` alongside `run_id`, and
`_agent_that_completed` reads it. The column is **denormalised rather than joined through `runs`**:
this is an integrity record and has to answer "who approved this" on its own, without depending on
a run row that may later be pruned.

*Rows written by 0052 keep `actor_agent` NULL*, and the rule treats NULL as "not the same agent", so
a task completed before the fix stays approvable rather than becoming permanently stuck. That is the
honest outcome — the agent that completed it was never recorded, and inventing one would put a guess
into the record whose whole value is that everything in it happened.

*What this still does not claim:* two different agents under the same operator can review each
other, which is the intended shape rather than a gap; and nothing here judges whether a review was
diligent, which is B4's evidence gates.

## Migration Plan

1. New revision after `0051_add_queue_entry_spec_document`, creating `task_transitions`, guarded for
   a missing `tasks` table in the manner of `0033`/`0034`. A second revision, `0053`, adds
   `actor_agent` (D14).
2. Bump the head assertions in `hub/tests/test_migrations.py` and
   `hub/tests/test_project_persistence.py` (`CLAUDE.md` requires both).
3. No data migration; the table starts empty (D8).
4. **Rollback:** the revision's downgrade drops the table. Because `Task.status` remains the
   materialised current value, dropping the history loses the audit trail but leaves every task in a
   valid state and the application working.

### D9 — The operator gets more edges, not an exemption from the map

Resolved with the operator 2026-08-10 (Open Questions 1–3):

- **Early rejection is the operator's.** A task can turn out obsolete at any point, but abandoning
  work is a judgement call. `rejected` is reachable from any non-terminal status **for the
  operator**; an agent may only reject at `under_review`, where rejecting is a review outcome rather
  than a decision to stop.
- **Terminal statuses are reopenable, by the operator.** Things get found after approval. Without
  `approved → revision_needed` the only recourse is a new task, which severs the history this change
  exists to build.
- **No forced-move override.** Because the operator's extra authority is expressed *as edges*, they
  are still bound by the map, and every operator move is a legal transition rather than a bypass.
  The history therefore always describes a legal sequence — which is what makes it worth reading.

*Alternative rejected:* an explicit override recording forced moves. More honest if the operator
genuinely needed to break the model, but with the edges above they do not, and it would add a second
path that every gate in B3/B4 would then have to account for.

## Open Questions

1. **Does `in_progress → completed` need to be restricted to the assignee?** Any run may currently
   complete any task. That is a broader assignment-ownership question than this change, and is noted
   rather than assumed.
