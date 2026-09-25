# Design — a document says how it will be built, and approval starts it

## Round 2, 2026-09-25

An independent re-derivation against HEAD `1cddc75`. Every *(operator)* decision stands; two of
them could not work exactly as R1 wired them, and the smallest fix for each is below. Three claims
were **measured** on SQLAlchemy 2.0.50 + aiosqlite 0.22.1 + Python 3.11.9 (this machine's stack),
in a scratch script, not argued.

**Changed:**

1. **D6: the flow's rows must be flushed inside the savepoint.** Loops carry a partial unique index
   on `spec_document_id` while unarchived (`ux_loops_spec_document_live`, `db/models.py:1572`). R1's
   `create_job_record` "does not commit" but said nothing about flushing, so a claim race would
   surface as an `IntegrityError` at `set_phase`'s **outer** commit and roll back the approval, the
   one outcome the operator ruled out. The function now flushes each row it adds.
2. **D6: the extraction is simpler and stays in `api/v1/jobs.py`.** There is no `jobs_service`
   module (`hub/hub/services/` holds only `__pycache__`). The helpers the body calls
   (`_check_agent_exists`, `_check_spec_document_conflict`) raise `HTTPException` and are shared
   with `update_job` (`jobs.py:1018, 1027`). So the extracted `build_flow_rows` raises
   `HTTPException` as they do, and `set_phase` catches that. A typed `JobCreateRefused` would mean
   converting the shared helpers and changing no answer. The route commits **once**: today it
   commits the job (`:734`) before the loop's commit (`:764`) can fail, which leaves an enabled job
   with no loop. That is F54's shape, and B11's design names it (`:177`). The extraction fixes it.
3. **D6/D7: after a savepoint rolls back, nothing touched inside it may be read. (Measured.)**
   Rolling back a SAVEPOINT expires every ORM object modified within it, and reading an expired
   attribute in this async stack raises `MissingGreenlet`. That includes objects changed by a bulk
   `UPDATE`. `_adopt_document_tasks` is such an `UPDATE` (`jobs.py:262-270`) over the tasks
   materialise just created. So if the flow's savepoint rolls back after adoption, R1's unchanged
   `[task.id for task in created]` (`spec.py:1640`) raises **after** the commit: the approval stands
   and the operator gets a 500. `MaterialiseOutcome` therefore carries plain values, never ORM rows.
4. **D6: "usable agent" is one function, not `_check_agent_exists`.** `_check_agent_exists`
   (`jobs.py:181-236`) accepts **any** name when the project has no `Agent` rows and no legacy
   `ProjectSession` agents (`:224-226`). It also accepts any name in legacy session data, *even one
   archived as an `Agent` row*, because `known` is tested before `archived` (`:212-215`). So a
   delivery the page reports stale could still produce a flow at approval, and that flow would fail
   every five minutes (F33). `delivery_agent_state(session, project_id, name)` (an open `Agent` row
   is `ok`, an archived row is `archived`, anything else is `unknown`) now serves both `GET /spec`
   and `set_phase`, and `set_phase` creates nothing unless it answers `ok`.
5. **D6: a flow already declaring the document is not a refusal.** On a re-approval after a reopen,
   the first approval's flow still claims the document. R1's path would hit
   `_check_spec_document_conflict` and report *"could not be created: already claimed"* on a
   healthy document. `set_phase` now looks first, and the report names the existing flow. The 409
   path remains for a genuine race. Test 1.6 is rewritten.
6. **D6: approval creates nothing a create would refuse or silently mis-create.** A flow delivery
   with no stop condition at approval can still happen: it was proposed before B5, or D4's
   approval-time exclusion lets it through. `create_job` would make it a plain job with no loop and
   drop the document (F157), or refuse it under B11. It is now reported and not created. A
   `stop_at` already past is reported and not created too (R2's choice: the flow would end at its
   first firing). The name is cut to `JobCreate.name`'s 256 characters, because a title may be 512
   (`spec.py` `DocumentCreate.title`).
7. **D6: the new flow is announced.** `set_phase` emits `job_created` (broadcast and
   `persist_event`) as the route does. `useSSE`'s `job_created` case also invalidates the loops
   key: today only `job_fired` does (`useSSE.ts:521-535`). Without that, change 1's phase-bar lookup
   would keep offering **Start a flow…** beside the flow approval just made.
8. **D7: `already_served` names declared task keys, not requirement keys.** Materialise skips a
   declared *entry* when every requirement it names is served by a hand-made task
   (`spec_tasks.py:263-268`). It is the entry that is not created, so the report names the entry's
   key and the requirements that made it redundant.
9. **D7: the savepoint claim holds, and so does a second defect R1 did not name. (Measured.)**
   Without a savepoint, a flush failure inside materialise makes `set_phase`'s commit raise
   `PendingRollbackError`: a 500, and the approval is lost. A non-database exception raised after
   `session.add` leaves the partial board pending, and today it is committed with
   `tasks_created: []`. The savepoint fixes both. **pysqlite caveat (measured):** a SAVEPOINT
   issued before any write in the transaction becomes the outermost transaction, and its RELEASE
   commits. It holds in `set_phase` only because `begin_nested()` first flushes the phase row and
   event `transition()` just wrote. That is now stated as `materialise_quietly`'s precondition.
10. **D2: the question goes to change documents only.** `SPEC_PHASE_DUTIES` is keyed by phase and
    printed for every kind. Asking a baseline or roadmap "how will this be built" contradicts D4,
    which requires `delivery` of change-specs only. The question is now a kind-conditional line in
    the open-document block. `spec_turn_notice` gains `kind=None`, and `None` adds nothing, which
    keeps `an-at-mention-an-agent-wrote-reads-no-file`'s byte-identical pin (its task 1.12) and its
    last line intact.
11. **D2: the text-collision claim is corrected.** `a-specification-is-read-in-results-that-fit`
    edits `read_spec_document`'s prose (`agents.py:1236-1250`, `mcp_server.py:1908-1935`), not
    `submit_spec_document`'s (`:1194-1222`). The only real overlap is D3's `include` note.
12. **D4: `check()` receives no kind.** Its signature is `check(payload, *, board_served,
    approved_document_paths)` (`spec_completeness.py:106-111`). The gate reads `payload.kind ==
    "change-spec"`.
13. **D5: the stale flag follows the roster without a reload.** Archiving an agent broadcasts
    `agent_archived`, not `spec_updated`, so the `spec/<path>` query would stay stale. The
    `agent_archived`, `agent_unarchived` and `agent_created` cases now invalidate the `spec` key
    prefix too.
14. **D5: the Delivery section is rendered only when `delivery` is present**, so every existing
    document re-renders byte-identically and no render pin moves.
15. **D5b: `delivery_agent` is refused where it cannot be honoured.** `PhaseRequest` is a
    `RequestModel` (`extra="forbid"`, whose rule is to honour a field or name it). It answers 400,
    before the transition, unless `to == approved` and the payload declares a flow.
16. **D7: the report offers Start a flow… only while no unarchived flow declares the document**
    (change 1's D3 lookup), not "when none was created". The operator may start one afterwards, and
    change 1's phase bar would then show a second, contradicting control.
17. **Test churn R1 did not name:** `test_spec_documents_api.py:564` pins *"approval adds one
    event"*, which becomes two. Seven test files (about 15 call sites) propose change-spec fixtures
    with no `delivery`, and each fixture gains `{"mode": "none"}`.

**Checked and held:** `set_phase`'s shape and the materialise call (`spec.py:1589-1639`);
`materialise_quietly` as the only caller and its swallow-and-`[]` (`spec_tasks.py:472-493`);
materialise stamps `loop_id` only from a loop that already exists (`:176-180, 284`), so for a new
document it stamps nothing, and `_adopt_document_tasks` stamps the rows afterwards, which makes
R1's order correct. `_hand_job_to_scheduler` commits first (`jobs.py:570`). `add_job` registers a
`CronTrigger` and fires nothing at once (`scheduler.py:2906-2944`). `SpecDocumentEvent.kind` is
`String(32)` with no CHECK (`models.py:2128`). The only code reading events by kind filters
`kind == "content"` (`run_divergence.py:651`), so a new kind is misread nowhere. `record_event`'s
signature (`spec_lifecycle.py:98-119`). B5 excludes by code at `APPROVED` (`phase_blockers`, its D1),
which is the seam D4 extends. Save reports completeness in `blocking` (`spec_service.py:261-273`).
`_Part` keeps unknown fields (`spec_payload.py:58-63`), so an un-restarted Hub preserves a submitted
`delivery`. The agent-actions submit takes `document: Any` (`agent_actions.py` `SpecDocumentSubmission`),
so `delivery` needs no route change. `test_mcp_tool_schemas.py` already pins `object` dict
parameters (`scope`, `evidence`: `:285-305`), so a `Dict` parameter is the house pattern. The
interview pins in `test_spec_turn_notice.py` and `test_exploring_interview_medium.py` are substring
checks and survive an added line. `test_agents_self_registered.py:726`'s "no `### Team`" pin
survives a roster line that is not a Team section. The first line of every ADDED requirement carries
SHALL. None duplicates an existing requirement. *"Approval creates the work its document declares"*
(`task-lifecycle-governance`) is about which tasks are created, and the report requirement adds
beside it without changing any of its statements.

---

**Round 1, 2026-09-25.** Decisions the operator made in the explore are marked **(operator)**. The
rest are this round's and are open to R2/R3. One of them, D5b, is flagged for the operator.

## The shape

```
exploring ── interview adds "How will this be built?" (D2, change-specs) ─┐
   │                                                                     │
submit_spec_document(…, delivery={mode, agent, stop, cron}) ◀────────────┘   (D1, D3)
   ▼
propose ── refused while delivery is unanswered or incomplete (D4)
   ▼
proposed ── the page shows Delivery; STALE if its agent is not open (D5)
   ▼
[Approve] ── the board is materialised, as today, now inside a savepoint (D7)
          ── the flow is created from delivery, operator as actor, first
             firing on the next tick, inside its own savepoint; a failure
             does not undo approval (D6)
          ── an approval report is written (D7)
   ▼
approved ── the report is on the page; "Start a flow…" while no flow declares it (change 1)
```

## D1 — `delivery` is an optional payload field; "required" is a completeness finding

```python
class Delivery(_Part):
    mode: Literal["flow", "none"]
    agent: Optional[str] = None               # flow: default agent, by name
    stop_when_queue_empties: bool = False     # flow: at least one stop condition
    stop_at: Optional[str] = None             # flow: ISO-8601 with a timezone
    cron: str = "*/5 * * * *"                 # flow: the create_flow default
```

`SpecPayload.delivery: Optional[Delivery] = None`. It must **not** be a required Pydantic field.
`validate_payload` re-runs on stored payloads in `propose` (`spec_service.py:768-772`), in
`rerender_phase` (`:803-807`, which returns silently on error) and in the capability merge. A
required field would make every existing document fail those. This is how `depends_on`, `from` and
`reviewer` were added: optional, `SCHEMA_VERSION` still 1 (`spec_payload.py:39`). `validate_payload`
checks shape only: `mode` is one of two values, `cron` parses (croniter, a Hub dependency), and
`stop_at`, when present, parses as an ISO-8601 datetime carrying a timezone. A naive time is refused
for the reason `cron_day_ambiguity_reason` exists: the Hub would otherwise pick which clock it
means. Whether a flow can actually be created from these values is still `set_phase`'s question
(D6). The day-field ambiguity check stays there, reported rather than refused at save.

Name and message are not in `delivery`. The flow is named after the document's title, cut to
`JobCreate.name`'s 256 characters, and its message is change 1's default (`Work the next task of
"<title>".`). Both are editable later in change 1's panel.

## D2 — The interview asks, in prose, and the agent can see the roster (operator)

Only for **change-spec** documents (R2): D4 requires `delivery` of no other kind, so no other kind
is asked. `SPEC_PHASE_DUTIES` is keyed by phase alone, so the duty is **not** added there:

- **Canonical context, open-document block** (`agents.py:1860-1944`). When the row's `kind ==
  "change-spec"` and its phase is `exploring`, one more line follows `SPEC_PHASE_DUTIES[phase]`:
  *"- Before the document is ready to propose, ask how it will be built. Recommend a flow when the
  work splits into tasks: a flow starts every task whose prerequisites are met, has finished work
  reviewed by another agent, and can stop when its queue empties. If the operator wants a flow, ask
  which agent works it by default (from the open agents listed here), when it stops, and how often
  it fires (every 5 minutes unless they say otherwise). Record the answer as `delivery`. 'No flow'
  is a valid answer: the tasks still go on the board."* The block already reads the row
  (`:1876-1879`); it reads `row.kind` beside `row.phase`.
- **Turn notice** (`launchability.spec_turn_notice`, `:316-373`) gains a keyword `kind:
  Optional[str] = None`. For `phase == "exploring"` and `kind == "change-spec"`, one line is
  appended to the exploring lines, **before** the unwritten-path line: *"Ask how it will be built (a
  flow, recommended, or no flow) before it is ready to propose; record the answer as `delivery`."*
  `agent_trigger._spec_phase_for` (`agent_trigger.py:385`) returns the row's kind too, and the one
  call site (`:1183`) passes it. With `kind=None` the output is byte-identical to today's.

It is asked **in the reply**, like the rest of the interview (`agents.py:1578-1583`). It is not an
`ask_user` fork. The contradicting lines at `:1918-1926` ("ending this turn without submitting or
calling `ask_user` is not a way to finish") are left as they are. This change does not arbitrate
between them; it only adds a question the existing interview already knows how to ask.

**The roster.** The canonical context prints `### Team` only when there are peers
(`agents.py:1963-1985`), so a single-agent author sees no roster. When a change-spec document is
open at `exploring` or `proposed`, the open-document block gains one line: *"- Open agents on this
project: a, b, c."* It is built from `roster`, which the function already reads
(`:1691-1694`, every `lifecycle == "open"` agent, the author included), so there is no second
query. It is not a `### Team` heading, so `test_agents_self_registered.py:726` still holds.

## D3 — The tool surface carries `delivery`

- `mcp_server.submit_spec_document` gains `delivery: Optional[Dict[str, Any]] = None`, passed into
  the `optional` dict (`:1867-1880`), and a docstring paragraph describing its two shapes. It is
  typed `Dict`, like `scope` and `evidence`, not `Any` (the F35 reversal, `:1774-1788`) and not a
  TypedDict (`test_structured_parameters_do_not_use_a_closed_object_type`).
- `agents.py`'s HTTP prose for `submit_spec_document` (`:1194-1222`) names `delivery` in its
  `args` and in the `http_note`'s list of keys that go inside `document`.
- `test_tool_surface_matches_server.py` fails until `args` names it. `test_mcp_tool_schemas.py`'s
  `wanted` map (`:294-302`) gains `"delivery": "object"`.
- No route changes. The agent-actions submission takes `document: Any` and `_Part` keeps unknown
  keys, so an un-restarted Hub stores a submitted `delivery` unchanged and simply does not check it.
- `a-specification-is-read-in-results-that-fit`, if it has landed, adds `delivery` to the sections
  `read_spec_document` can `include`.

## D4 — Proposing is refused without an answer (operator: forced)

New findings in `spec_completeness.check()`, when `payload.kind == "change-spec"` (R2: `check`
receives only the payload, `spec_completeness.py:106-111`; capability documents never pass through
propose):

| Code | When |
|---|---|
| `delivery_unanswered` | `delivery` is absent |
| `delivery_flow_incomplete` | `mode == "flow"` with no `agent`, or with neither `stop_when_queue_empties` nor `stop_at` |

Each finding's message says what to ask the operator. **They gate `proposed` only.** Once
`a-document-moves-forward-only-through-its-checks` lands, `transition()` calls
`phase_blockers(..., to_phase=APPROVED)`, and that change already filters `import_not_approved` out
by code at `APPROVED` (its D1). These two codes are added to the same filter. Without that, a
document proposed before this change could never be approved. At approval, an absent `delivery`
means no flow, and the report says *"No delivery was declared."* A flow delivery that reaches
approval incomplete is reported and not created (D6).

Save still reports them in `blocking`, as it reports every finding (`spec_service.py:261-273`), so the
author sees them while drafting, as the next thing to ask.

## D5 — The delivery is shown, and a stale agent is flagged when the document is read (operator)

- `spec_render.py` gains a **Delivery** section after Tasks (`:584`), **only when `delivery` is
  present**, so a document without one renders byte-identically. For a flow: *"Built by a flow.
  Default agent: dev. Stops when the queue empties. Fires every 5 minutes."* For none: *"No flow.
  The tasks go on the board and are started by hand."* Static, like every other section.
- **The stale flag is not in the file.** Agent state changes independently of the document, and any
  rewrite off a transition registers as divergence (`spec_lifecycle.divergence`, `:378`). `GET
  /spec` computes `delivery_status` on each read, beside `_divergence_fields` (`spec.py:140-185`),
  for a change-spec document at `exploring` or `proposed`: `{"state": "ok" | "stale" | "none" |
  "absent", "agent": "...", "reason": "archived" | "unknown"}`. It is omitted for every other
  document.
- **One definition of usable (R2).** `delivery_agent_state(session, project_id, name) -> "ok" |
  "archived" | "unknown"`: an `Agent` row with `lifecycle == "open"` is `ok`, one with `"archived"`
  is `archived`, and no row is `unknown`. `GET /spec` and `set_phase` (D6) both call it.
  `_check_agent_exists` is not the definition, because it accepts any name on an empty roster and
  any name in legacy `ProjectSession` data (R2 change 4). Agent lifecycle is `open | archived`
  (`models.py:307`).
- `SpecPhaseBar` shows a stale delivery as a warning strip above Approve: *"Delivery names dev2,
  which is archived. Approving will not start a flow unless you choose another agent."* The bar
  reads `delivery_status` from the `spec/<path>` query the panel already holds.
- **Freshness (R2).** `useSSE`'s `agent_archived`, `agent_unarchived` and `agent_created` cases
  (`useSSE.ts:465, 569-570`) also invalidate `['project', pid, 'spec']`, so the strip appears or
  clears without a reload.

**D5b — at approval, the operator may choose the agent for a stale delivery (R1's decision, not the
operator's; confirm).** The strip carries a select of open agents and "No flow". The choice is sent
as `delivery_agent` (or `delivery_agent: ""` for no flow) in the phase request body (`PhaseRequest`).
It is used for this flow only and recorded in the report. The document is not edited: approving
never rewrites the author's content. The alternative is to send the document back to the author to
fix. That costs a turn and a reopen to change one name, so R1 chose the override. The operator decides.

R2: `set_phase` answers **400**, before the transition, when `delivery_agent` is sent and either
`to != "approved"` or the payload declares no flow. `PhaseRequest` refuses what it cannot honour
(`RequestModel`, `extra="forbid"`). The UI sends the field only from the strip, and the strip exists
only when `delivery_status` does, so a bundle talking to an un-restarted `:8000` never sends it
(that Hub would 422 the unknown field).

## D6 — Approval creates the flow, and a failure does not undo approval (operator)

- **One creation path (R2: reshaped).** `create_job`'s body (`jobs.py:593-819`) splits in two. The
  first part is request-only, stays in the route, and runs first as today: the agent-job allowance,
  the `session_mode` and `work_needs_evidence` refusals, `initial_tasks` parsing, the F265 seeding
  rule and `_check_initial_tasks`. The second part becomes
  `build_flow_rows(session, project_id, body: JobCreate, *, created_by_run_id) -> Tuple[AIJob,
  Optional[Loop]]`, beside the helpers in `api/v1/jobs.py`. It runs `_check_agent_exists`, the
  croniter and day-ambiguity checks, and `_check_spec_document_conflict` when the job opts in. It
  then adds the job and **flushes**; an `IntegrityError` there becomes today's 409 *"Job with ID …
  already exists"*. When the job opts in, it adds the loop, runs `_adopt_document_tasks` (and B11's
  `loop_tasks_adopted` events, which B11 already writes with `commit=False`), and **flushes**; an
  `IntegrityError` there becomes today's 409 *"document … is already claimed by another loop"*. It
  raises `HTTPException` as the helpers do and **never commits**. The route then commits once,
  refreshes, seeds `initial_tasks`, builds the summary, hands the job to the scheduler and
  broadcasts, exactly as now. Every refusal keeps its status and detail. The one behaviour change is
  that a failed loop insert no longer leaves the job row committed.
- **`delivery_agent_state` gates it.** `set_phase` resolves the agent (`delivery_agent` if sent,
  else `delivery.agent`) and calls `build_flow_rows` only when that answers `ok`. Otherwise the
  report states *"dev2 is archived"* or *"dev2 is not an agent on this project"*, with no call
  made.
- **A flow already declaring the document is reported, not refused (R2).** Before creating
  anything, `set_phase` looks for an unarchived loop whose `spec_document_id` is the document: the
  re-approval after a reopen. If one exists, nothing is created, and the report names it: *"The flow
  <name> already builds this document."* Materialise has already stamped the new tasks with that
  loop's id (`spec_tasks.py:176-180, 284`; B11 restricts that lookup to live loops).
- **Not created, and reported (R2):** a flow delivery with no agent, or with no stop condition
  (possible for a document proposed before B5, or through D4's approval-time exclusion), and a
  `stop_at` that has already passed.
- **In `set_phase`**, after `materialise_quietly` (`spec.py:1628-1631`) and before the commit
  (`:1633`), when `document.phase == "approved"`, the document is a change-spec, `delivery.mode ==
  "flow"`, and none of the cases above applies:
  1. `async with session.begin_nested():` (SAVEPOINT).
  2. `build_flow_rows` with `name=<title>[:256]`, `agent`, the default message, `cron`, the stop
     condition, and `spec_document_id=document.id`, and `created_by_run_id=None`. The allowance
     gate is a request-level check that stays in the route, so it is never reached. `allow_agent_jobs`
     never applies, since the operator is the actor.
  3. `_adopt_document_tasks`, inside it, stamps `loop_id` on the tasks just materialised. For a
     document with no earlier loop they carry `NULL` at this point, so adoption is what binds them.
  4. `HTTPException` (the 400s and 409s above) rolls back to the savepoint, and its `detail`
     becomes the reason (`str()` if not a string). Any other exception rolls back to the savepoint,
     is logged with its traceback, and records *"The flow could not be created."*
- **Nothing touched inside a rolled-back savepoint is read afterwards (R2, measured).** The response
  and the report are built from `MaterialiseOutcome`'s plain values (D7) and from the plain values
  `set_phase` captured before the flow's savepoint. `document` itself is not modified inside it.
- After the commit, a created job goes to `_hand_job_to_scheduler`, and the first firing is the next
  cron tick (`scheduler.py:2906-2944`). Nothing fires at once. *(operator: first scheduled tick)*
  `set_phase` then does what the route does after its commit: it broadcasts `job_created` and calls
  `persist_event(..., "job_created", ...)`. `useSSE`'s `job_created` case invalidates
  `['project', pid, 'loops']` as well as jobs, and `useSetSpecPhase` invalidates both on success,
  so change 1's phase bar shows **Flow: <name>** rather than **Start a flow…**.
- `a-loop-that-is-gone-lets-go-of-its-document` excludes archived loops from the claim and adoption
  path. This change inherits its behaviour and does not restate it.
- **Only this door creates a flow.** An adopted document registered straight at `approved`
  (`spec_adoption.PHASES`) never passes through `set_phase`. It gets no flow and no report; change 1's
  **Start a flow…** covers it.

## D7 — The approval report

- **The board in a savepoint.** `materialise_quietly` runs `materialise` inside `async with
  session.begin_nested():`. Without it (R2, measured), a flush error mid-way makes the commit at
  `spec.py:1633` raise `PendingRollbackError`. The route 500s and the approval is rolled back, the
  one outcome its docstring says must not happen. A non-database exception after some
  `session.add` leaves those rows pending, and today they are committed as a partial board beside
  `tasks_created: []`. **Precondition, stated in its docstring:** the enclosing transaction has
  already written, so the SAVEPOINT is nested. Under pysqlite, a SAVEPOINT issued first becomes the
  outermost transaction and its RELEASE commits. In `set_phase`, `begin_nested()` flushes the phase
  row and event `transition()` wrote, which satisfies it.
- It returns `MaterialiseOutcome(created: List[CreatedTask], already_served: List[ServedEntry],
  failed: Optional[str])`, plain dataclasses and not ORM rows. `CreatedTask` is `(id, key, title)`.
  `ServedEntry` is `(key, requirements)`: a declared entry skipped because a hand-made task already
  serves every requirement it names (`spec_tasks.py:263-268`). `failed` is the exception's class
  and message. Each list is in the payload's declaration order.
- **Dependencies not honoured** are read after materialisation, still inside the transaction, from
  `TaskDependencyReference` rows (`models.py:2422-2450`: task, reference, reason) for the tasks this
  document owns. They are ordered by the task's declaration position, then by reference. Reasons are
  `not_declared`, `local_task_not_materialised`, the import reasons (`malformed_import`,
  `document_not_found`, `document_not_approved`, `key_not_found`) and the writer's refusals
  (`missing`, `cycle`). Because `_materialise_edges` rewrites these rows per task on every approval,
  they describe this approval's state.
- **Stored** as one `SpecDocumentEvent` with `kind="approval_report"`, written by
  `spec_lifecycle.record_event` (`:98-119`) after the flow's savepoint and before the commit,
  outside any savepoint, actor operator. No migration: `kind` is `String(32)` with no CHECK
  constraint. The only kind-filtering reader is `run_divergence.py:651` (`kind == "content"`). It is
  named `approval_report` at the storage layer only. The API field is `approval_outcome`, because
  tasks already have an unrelated `approval_report` response field (`api/v1/tasks.py:91-104`).
- **Returned** by `GET /spec` as `approval_outcome` for an approved change document: the newest
  such event by `created_at`, chosen by the Hub so the UI never picks. It is also returned in
  `set_phase`'s response beside `tasks_created`, which keeps its shape (ids) and is built from
  `outcome.created`.
- **Shown** by a new `SpecApprovalReport.tsx`, mounted in `SpecDocumentPanel.tsx` under the phase
  bar. It lists what was created, then each problem, in the order the Hub returns. It offers change
  1's **Start a flow…** only while change 1's lookup finds no unarchived flow declaring the document
  (R2), so it never contradicts the phase bar. It stays visible while the document is approved. It
  is a record, not an alert; it has no dismiss.
- `useSpecEvents` (`api/spec.ts:151-177`) already invalidates `spec/<path>` on `spec_updated`, which
  `set_phase` broadcasts. The report rides that key, and no new query key is needed.

## Risks and order

- **After change 1** (the dialog and the document→flow lookup), **B5's
  `a-document-moves-forward-only-through-its-checks`** (the gate's base, and the approval-time
  exclusion D4 depends on), and **B11's `a-loop-that-is-gone-lets-go-of-its-document`** (the claim
  path, the live-loop materialise lookup, and the `commit=False` adoption event that
  `build_flow_rows` carries).
- **Text collisions:** `an-at-mention-an-agent-wrote-reads-no-file` edits `spec_turn_notice` and
  appends its D6 sentence as the notice's last line. The delivery line goes before it, and
  `kind=None` keeps its byte-identical pin. `a-specification-is-read-in-results-that-fit` edits the
  `read_spec_document` prose, not the lines this change edits. Rebase onto whichever has landed.
- **Test churn:** `test_spec_documents_api.py:564` pins one event per approval, and it becomes two
  (phase and `approval_report`). The earlier-events-unchanged half still holds. Change-spec
  fixtures that are proposed (`test_agent_created_documents.py`, `test_spec_archive.py`,
  `test_spec_board_task_convergence.py`, `test_spec_documents_api.py`, `test_spec_index_writer.py`,
  `test_spec_merge.py`, `test_spec_rename.py`) gain `"delivery": {"mode": "none"}`.
- `an-agent-can-be-paused-and-keeps-its-input` (REVISING) may add a paused state. If it lands,
  `delivery_agent_state` answers `ok` for a paused agent; only archived and unknown agents are stale.
- **`:8000` skew:** the bundle's report panel reads a field an un-restarted `:8000` does not return.
  It must render nothing when `approval_outcome` is absent, and the strip, absent
  `delivery_status`, never sends `delivery_agent`. Interview text and tool changes reach `:8000`'s
  agents only after its restart onto the tool-server pin (F354, now built).
