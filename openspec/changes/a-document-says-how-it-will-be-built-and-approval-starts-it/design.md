# Design — a document says how it will be built, and approval starts it

**Round 1, 2026-09-25.** Decisions the operator made in the explore are marked **(operator)**. The
rest are this round's and are open to R2/R3. One of them, D5b, is flagged for the operator.

## The shape

```
exploring ── interview adds "How will this be built?" (D2) ──┐
   │                                                          │
submit_spec_document(…, delivery={mode, agent, stop, cron}) ◀┘   (D1, D3)
   ▼
propose ── refused while delivery is unanswered or incomplete (D4)
   ▼
proposed ── the page shows Delivery; STALE if its agent is not open (D5)
   ▼
[Approve] ── the board is materialised, as today, now inside a savepoint (D7)
          ── the flow is created from delivery, operator as actor, first
             firing on the next tick; a failure does not undo approval (D6)
          ── an approval report is written (D7)
   ▼
approved ── the report is on the page; "Start a flow…" if none was made (change 1)
```

## D1 — `delivery` is an optional payload field; "required" is a completeness finding

```python
class Delivery(_Part):
    mode: Literal["flow", "none"]
    agent: Optional[str] = None               # flow: default agent, by name
    stop_when_queue_empties: bool = False     # flow: at least one stop condition
    stop_at: Optional[str] = None             # flow: ISO-8601
    cron: str = "*/5 * * * *"                 # flow: the create_flow default
```

`SpecPayload.delivery: Optional[Delivery] = None`. It must **not** be a required Pydantic field.
`validate_payload` re-runs on stored payloads in `propose` (`spec_service.py:770-773`), in
`rerender_phase` (`:800-804`, which returns silently on error) and in the capability merge. A
required field would make every existing document fail those. This is how `depends_on`, `from` and
`reviewer` were added: optional, `SCHEMA_VERSION` still 1 (`spec_payload.py:176-200`, `:235-239`).
`validate_payload` checks shape only: `mode` is one of two values, and `cron` parses (croniter) when
present.

Name and message are not in `delivery`. The flow is named after the document's title, and its
message is change 1's default (`Work the next task of "<title>".`). Both are editable later in change
1's panel.

## D2 — The interview asks, in prose, and the agent can see the roster (operator)

Both instruction sites get one more duty, worded to fit each:

- `SPEC_PHASE_DUTIES["exploring"]` (`agents.py:1574-1587`): *"Before the document is ready to
  propose, ask how it will be built. Recommend a flow when the work splits into tasks: a flow starts
  every task whose prerequisites are met, has finished work reviewed by another agent, and can stop
  when its queue empties. If the operator wants a flow, ask which agent works it by default (from the
  agents listed below), when it stops, and how often it fires (every 5 minutes unless they say
  otherwise). 'No flow' is a valid answer: the tasks still go on the board."*
- `spec_turn_notice` exploring branch (`launchability.py:357-370`): one short line, *"Ask how it will
  be built (a flow, recommended, or no flow) before it is ready to propose; record the answer as
  `delivery`."*

It is asked **in the reply**, like the rest of the interview (`:1579-1583`). It is not an `ask_user`
fork. The contradicting lines at `:1918-1935` ("ending this turn without submitting or calling
`ask_user` is not a way to finish") are left as they are. This change does not arbitrate between
them; it only adds a question the existing interview already knows how to ask.

**The roster.** The canonical context prints `### Team` only when there are peers
(`agents.py:1970-1985`), so a single-agent author sees no roster. In a spec turn at `exploring` or
`proposed`, the open-document block gains one line: *"Open agents on this project: a, b, c."* (every
`lifecycle == 'open'` agent, the author included).

## D3 — The tool surface carries `delivery`

- `mcp_server.submit_spec_document` gains `delivery: Optional[Dict[str, Any]] = None`, passed into
  the `optional` dict (`:1858-1880`), and a docstring paragraph describing its two shapes.
- `agents.py`'s HTTP prose for `submit_spec_document` (`:1194-1222`, its `args` and `http_note`)
  names `delivery`.
- `test_tool_surface_matches_server.py` keeps the two renderings in step. `test_mcp_tool_schemas.py`
  pins the object schema.
- `a-specification-is-read-in-results-that-fit`, if it has landed, adds `delivery` to the sections
  `read_spec_document` can `include`.

## D4 — Proposing is refused without an answer (operator: forced)

New findings in `spec_completeness.check()`, for `kind == "change-spec"` only (capability documents
never pass through propose):

| Code | When |
|---|---|
| `delivery_unanswered` | `delivery` is absent |
| `delivery_flow_incomplete` | `mode == "flow"` with no `agent`, or with neither `stop_when_queue_empties` nor `stop_at` |

Each finding's message says what to ask the operator. **They gate `proposed` only.** Once
`a-document-moves-forward-only-through-its-checks` lands, `phase_blockers(..., to_phase=APPROVED)`
runs completeness at approval too, and these two codes are excluded there, as that change already
excludes `import_not_approved`. Without the exclusion, a document proposed before this change could
never be approved. At approval, an absent `delivery` means no flow, and the report says *"No delivery
was declared."*

Save still reports them in `blocking`, as it reports every finding (`spec_service.py:261-273`), so the
author sees them while drafting.

## D5 — The delivery is shown, and a stale agent is flagged when the document is read (operator)

- `spec_render.py` gains a **Delivery** section after Tasks. For a flow: *"Built by a flow. Default
  agent: dev. Stops when the queue empties. Fires every 5 minutes."* For none: *"No flow. The tasks
  go on the board and are started by hand."* Static, like every other section.
- **The stale flag is not in the file.** Agent state changes independently of the document, and any
  rewrite off a transition registers as divergence (`spec_lifecycle.divergence`, `:378-390`). `GET
  /spec` computes `delivery_status` on each read, beside `_divergence_fields` (`spec.py:140-185`):
  `{"state": "ok" | "stale" | "none" | "absent", "agent": "...", "reason": "archived" | "unknown"}`.
  A stale state is computed only for `exploring` and `proposed` documents.
- `SpecPhaseBar` shows a stale delivery as a warning strip above Approve: *"Delivery names dev2,
  which is archived. Approving will not start a flow unless you choose another agent."*

**D5b — at approval, the operator may choose the agent for a stale delivery (R1's decision, not the
operator's; confirm).** The strip carries a select of open agents and "No flow". The choice is sent
as `delivery_agent` (or `delivery_agent: ""` for no flow) in the phase request body (`PhaseRequest`).
It is used for this flow only and recorded in the report. The document is not edited: approving
never rewrites the author's content. The alternative is to send the document back to the author to
fix. That costs a turn and a reopen to change one name, so R1 chose the override. The operator decides.

## D6 — Approval creates the flow, and a failure does not undo approval (operator)

- **One creation path.** `create_job`'s body (`jobs.py:592-818`) is inline, and its helpers raise
  `HTTPException`. Extract the part after request parsing into
  `jobs_service.create_job_record(session, project_id, body, *, actor) -> (AIJob, Optional[Loop])`,
  which raises a typed `JobCreateRefused(status, detail)` and **does not commit**. The route maps the
  refusal back to the same status and detail, so its answers do not change. `_hand_job_to_scheduler`
  commits the session itself (`:571`), so both callers call it **after** their own commit.
- **In `set_phase`**, after `materialise_quietly` (`spec.py:1628-1631`) and before the commit
  (`:1633`), when `document.phase == "approved"`, the document is a change-spec, and `delivery.mode
  == "flow"`:
  1. `session.begin_nested()` (SAVEPOINT).
  2. `create_job_record` with `name=<title>`, `agent=delivery_agent or delivery.agent`, the default
     message, `cron`, the stop condition, and `spec_document_id=document.id`; `actor` is the operator.
     No agent headers means `_require_agent_job_allowance` never applies (`:39-40`).
  3. The existing `_adopt_document_tasks` (`:239-270`) inside it stamps `loop_id` on the tasks just
     materialised.
  4. On `JobCreateRefused` (unknown or archived agent 400, claim 409, cron 400), roll back to the
     savepoint and record the refusal's `detail` as the reason. On any other exception, roll back to
     the savepoint and record *"The flow could not be created"*, with the log line.
- After the commit, a created job is handed to the scheduler (`_hand_job_to_scheduler`), so the
  first firing is the next cron tick (`scheduler.py:2906-2944`). Nothing fires at once. *(operator:
  first scheduled tick)*
- `a-loop-that-is-gone-lets-go-of-its-document` excludes archived loops from the claim and adoption
  path. This change inherits its behaviour and does not restate it.
- **Only this door creates a flow.** An adopted document registered straight at `approved`
  (`spec_adoption.PHASES`) never passes through `set_phase`. It gets no flow and no report; change 1's
  **Start a flow…** covers it.

## D7 — The approval report

- **The board in a savepoint.** `materialise_quietly` wraps `materialise` in `begin_nested()`.
  Without it, a flush error mid-way leaves the session unusable, and the commit at `spec.py:1633`
  could then fail and roll back the approval, the one outcome its docstring says must not happen. It
  returns a `MaterialiseOutcome(created, already_served, failed: Optional[str])` instead of a bare
  list. `already_served` names the requirement keys that hand-made tasks already served
  (`spec_tasks.py:228, 266`).
- **Dependencies not honoured** are read after materialisation from `TaskDependencyReference` rows for
  the tasks this document owns (`models.py:2422-2450`: task, reference, reason).
- **Stored** as one `SpecDocumentEvent` with `kind="approval_report"`, written in the same
  transaction by `spec_lifecycle.record_event` (`:98-119`), actor operator. No migration: `kind` has
  no CHECK constraint. It is named `approval_report` at the storage layer only; the API field is
  `approval_outcome`, because tasks already have an unrelated `approval_report` response field
  (`api/v1/tasks.py:91-104`).
- **Returned** by `GET /spec` as `approval_outcome` (the latest such event) for an approved document,
  and in `set_phase`'s response beside `tasks_created`.
- **Shown** by a new `SpecApprovalReport.tsx`, mounted in `SpecDocumentPanel.tsx` under the phase
  bar. It lists what was created, then each problem. When no flow was created, it offers change 1's
  **Start a flow…**. It stays visible while the document is approved. It is a record, not an alert;
  it has no dismiss.
- `useSpecEvents` (`api/spec.ts:151-177`) already invalidates `spec/<path>` on `spec_updated`, which
  `set_phase` broadcasts. The report rides that key, and no new query key is needed.

## Risks and order

- **After change 1** (the dialog and the document→flow lookup), **B5's
  `a-document-moves-forward-only-through-its-checks`** (the gate's base, and the approval-time
  exclusion D4 depends on), and **B11's `a-loop-that-is-gone-lets-go-of-its-document`** (the claim
  path).
- **Text collisions:** `an-at-mention-an-agent-wrote-reads-no-file` edits `spec_turn_notice`, and
  `a-specification-is-read-in-results-that-fit` edits the same `agents.py` prose. Rebase onto
  whichever has landed.
- `an-agent-can-be-paused-and-keeps-its-input` (REVISING) may add a paused state. If it lands, a
  paused agent is not stale; only archived and unknown agents are.
- **`:8000` skew:** the bundle's report panel reads a field an un-restarted `:8000` does not return.
  It must render nothing when `approval_outcome` is absent. Interview text and tool changes reach
  `:8000`'s agents only after its restart onto the tool-server pin (F354, now built).
