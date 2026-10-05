## Context

The motivation and measurements are in the proposal and in the exploration's 2026-10-05 section. The
facts this design rests on were read at `b8ec760`:

- **The payload keeps unknown fields but never validates by kind.** `SpecPayload`
  (`hub/hub/spec_payload.py:210-237`) is `extra="allow"`. `validate_payload` (`:256-361`) checks
  only that `kind` is in `KINDS`.
- **Completeness branches on kind exactly once**, for delivery (`spec_completeness.py:251-252`).
  `no_requirements` (`:167-174`) fires on any payload with no requirements.
- **Approval** (`api/v1/spec.py` `set_phase`, `:1761-1890`) runs, in order: the transition,
  `materialise_quietly`, `_approval_flow` (change-spec only, `:1979-1983`), the approval report, the
  re-render, the broadcasts, the commit, and then `_hand_job_to_scheduler`.
- **Who created a document** is recorded on its `created` event: actor, actor kind and run
  (`spec_lifecycle.py:233`, `models.py:2135-2140`). An agent creation records
  `Actor(kind="agent", name, run_id)` (`agent_actions.py:1586`), and `Run.conversation_id` names the
  conversation.
- **A Hub-queued turn** is `inbound_queue.new_entry(...)` plus `turn_scheduler.schedule_agent(...)`,
  with a `conversation_id` (F67). The precedent is `agent_trigger.py:2507-2523`.
- **`origin_type` is a DB CHECK** limited to `operator`, `agent`, `job`, `checkpoint`, `divergence`
  and `evidence` (`models.py:655`).
- **The corpus index** (`spec/index.json`) holds `parent`. It is written only by the operator's
  reindex and arrange routes (`api/v1/spec.py:1431`, `:1551`), and a rename does not update it.

## Goals / Non-Goals

**Goals:**
- a roadmap an agent can create, holding ordered slices;
- a slice document linked to the roadmap;
- approval that can start the next slice;
- guidance every authoring agent reads.

**Non-goals:** listed in the proposal. In particular, nothing here touches task size, the requirement
gate or migrations. Those belong to the sibling change `a-task-may-serve-a-whole-slice`.

## Decisions

**D1. Slices are a typed payload field, and validation becomes kind-aware.**
- Add `Slice(_Part)` with `key`, `title`, `intent`, `done` and `builds_after: List[str]`, and
  `slices: List[Slice] = []` on `SpecPayload`.
- `validate_payload` gains the first per-kind rules:
  - `slices` only on `roadmap`;
  - `requirements`, `acceptance_criteria` and `tasks` empty on `roadmap`;
  - unique slice keys;
  - every `builds_after` key resolves to another slice of the same roadmap.
- These are refusals at **submit**, not phase findings, because the shape is wrong whatever the
  phase.
- *Alternative:* leave `slices` as an untyped extra. Rejected: nothing would validate it, render it
  or return it on the agent read (`agent_actions.py:1542-1544` lists the extras it returns).

**D2. The slice-to-roadmap link is in the slice's payload, not the corpus index.**
- `roadmap: {document: <path>, slice: <key>}` is optional on a change-spec.
- *Alternative:* set the manifest `parent`. Rejected:
  - `spec-corpus-map` makes placement the operator's;
  - a fresh document is absent from the index until reindex;
  - a rename leaves the recorded parent stale.
- The payload link has none of these problems, and it is written by the agent that writes the
  slice.

**D3. Completeness gains a roadmap branch and two link findings.**
- For `kind == roadmap`:
  - `no_requirements` is replaced by `roadmap_without_slices`;
  - `non_goals_empty` still applies;
  - delivery does not apply, as today.
- For a change-spec with `roadmap`:
  - `roadmap_not_approved` (the document is missing or not approved);
  - `roadmap_slice_unknown` (the key is not among its slices).
- Both findings block at proposed **and** at approved, unlike `import_not_approved`, which approval
  drops (`spec_service.py:919-925`). A slice of a roadmap that has been reopened must wait for it.
- The lookup follows the pattern `import_not_approved` already uses to resolve another document.
- So re-ordering slices means reopening the roadmap and approving it again. That answers the
  exploration's open question 3, with no new mechanism.

**D4. "Draft the next slice" is an option on the operator's approval request, and its turn is the
operator's.**
- `PhaseRequest` gains `draft_next_slice: bool = False`. The app sends `true` by default when the
  document names a roadmap slice.
- After the approval commits, if asked and the payload has `roadmap`:
  1. Resolve the next slice: the entry after the approved key in the roadmap's list.
  2. Resolve the author: the `created` event with `actor_kind == "agent"`.
  3. Resolve the conversation: `Run.conversation_id` of that event's run.
  4. Queue one entry with `origin_type="operator"`, `hop_depth=0` and `spec_document=<roadmap
     path>`, then call `schedule_agent`.
- *Why the roadmap is the turn's spec document (review round):*
  - An operator entry's `spec_document` becomes the turn's (`turn_scheduler.py:370`).
  - That makes it a specification turn: no file-write tools (`api/v1/agent_trigger.py:1430`,
    `:1450`), and the spec notice (`launchability.py:334`).
  - A drafting turn must not be able to implement, so the binding is needed. The slice document
    would be the wrong one, because the next slice does not exist yet.
  - The roadmap is approved, so `SPEC_PHASE_DUTIES["approved"]` ("Implement against it",
    `api/v1/agents.py:1726-1729`) is wrong for it. D6 adds a roadmap duty.
- The message is fixed Hub text. It names:
  - the roadmap path;
  - the approved slice and its tasks;
  - the next slice's key, title, intent and done criterion;
  - the instruction to read how the approved slice's tasks went (notes, evidence) before drafting,
    and to write the new slice as a change document that names the roadmap slice.
- The response carries
  `next_slice: {state: queued|last_slice|no_author|no_conversation|not_a_slice, slice?, agent?}`.
- *Alternatives:*
  - A new `spec` origin (rejected: a CHECK-constraint migration makes this Tier 2, and it touches
    `:8000`'s database on restart).
  - Manual only (rejected: Q13 says the agent drafts).
- The operator answered on 2026-10-05: an option on approval. The attribution is honest because
  the operator asked for it in the same request.

**D4a. The drafting turn waits for the slice to be built (F496, operator, 2026-10-05).**
- Drive A showed the D4 turn ran seconds after approval, with the slice's only task `pending`, so
  "read how the tasks went" had nothing to read. The operator chose option (b): fire when built.
- At approval the request is resolved as in D4 (next slice, author, conversation; same refusal
  states). If it resolves, a `next_slice_requested` event is written on the slice document, with
  `{roadmap, slice, agent, conversation_id}`. Event kinds have no CHECK, so there is no migration.
- If no linked task is open, the turn is queued in the approval request (state `queued`). That is a
  re-approval after a reopen: a change document cannot be proposed without tasks. Otherwise the
  response says `waiting`, with `open_tasks`.
- `apply_transition` (`task_transition_service.py`), the one function every status write passes
  through, calls `slice_drafting.on_task_closed` when a task with a `spec_document_id` reaches
  `approved` or `rejected`. Once no linked task is open and the request has no `next_slice_queued`
  event yet, it queues the entry (as D4, plus each task's id, title and final status), writes
  `next_slice_queued`, and schedules the agent from an `after_commit` listener, the
  `defer_broadcast` pattern (`sse.py:130-164`). It runs in a savepoint, and a failure is logged and
  never fails the transition.
- *Why rejected counts as closed:* nothing more happens to a rejected task unless the operator
  reopens it; the turn is told it was rejected. *Why once:* a reopen-and-approve must not draft
  the same slice twice.
- *Rejected:* (a) keep the approval trigger and reword (no learning); (c) both (needs an amend path
  for an already-proposed N+1).

**D5. Agents may create a roadmap.**
- `create_spec_document` (MCP and `agent_actions.py:1548-1612`) gains
  `kind: "change-spec" | "roadmap" = "change-spec"`.
- Anything else is refused, and the refusal names both kinds.
- The minted path stays under `spec/changes/`. Separating roadmap paths is not needed for any
  scenario here.

**D6. The guidance goes where every authoring agent reads it.**
- The docstrings of `create_spec_document` and `submit_spec_document`, plus one `SPEC_PHASE_DUTIES`
  bullet (`api/v1/agents.py:1704-1729`), say:
  - a request larger than one slice becomes a roadmap plus slice 1;
  - a slice is about a dozen requirements or fewer, as a few tasks;
  - later slices are recorded in the roadmap.
- *Alternative:* an enforced cap. Rejected: METRICS measures whether the guidance holds first.
- The seeded charter's bullet (`data/charters/spec.md:91-92`) is reworded to match.
- An approved **roadmap** gets its own duty in place of `approved`'s, where the context names the
  open document's phase (`api/v1/agents.py:2172`): "its slices are specified one at a time as
  change documents that name it; do not implement from the roadmap".

**D7. Rendering.**
- `spec_render.py` gains a Slices section for roadmaps, and a "Slice S2 of *Roadmap title*" line
  on a linked change document.
- The agent read view returns `slices` and `roadmap`.

## Risks / Trade-offs

- **[Agents ignore the guidance and still write one big document.]** Acceptance drive B measures it
  on a real model. If it fails, the next step is an enforced size finding, decided from that
  measurement.
- **[The drafting turn lands in a long authoring conversation and is expensive.]** The turn is
  briefed with a checkpoint like any other, and is capped by the runner as today. The conversation
  is the one that holds the spec context Q13 wants. If the drive shows the cost is too high, a fresh
  conversation is a one-line change.
- **[An approval that queues a turn could double-queue on a retried request.]** Approving an
  already-approved document is refused by the phase machine, so the queueing step runs once per
  approval.
- **[Real agent drives on `:8010`.]** DEAD-ENDS (2026-10-05) records that Claude agents there carry
  no MCP config. Drive A uses stub-provider agents, as F490 and F495 did. Drive B needs a real model
  holding the spec tools (see the review round below).

## Review round (task 0.1, 2026-10-05, at `a10b32d`)

Every Context fact was re-read at its cited lines and holds, with two path corrections: the queue
precedent is `api/v1/agent_trigger.py:2507-2523` and the CHECK is `db/models.py:655`.
- **D3:** `check()` is a pure function (`spec_completeness.py:105-125`). Its two callers
  (`spec_service.py:266-275` on save, `:910-914` at the transition) resolve the roadmap
  (phase and slice keys) and pass it in, as they already pass `approved_document_paths`.
- **D4:** the drafting entry carries the roadmap as `spec_document`, and D6 adds a roadmap duty
  (both recorded above).
- **The drives:** a roadmap is proposed only after the operator closes its exploration
  (`explore_not_closed`, `spec_service.py:945-953`), so drive A's step (c) closes it first.
- **R1, the runner for drive B:** Copilot `cp5` (`runner-72c07eca7e75`) with a Haiku model
  override.
  - Copilot runs hold the MCP tools; the stub-provider drives used them.
  - A Claude run on `:8010` gets `--permission-prompt-tool` only with `mcp_args`
    (`runner_commands.py:241-248`). Without an approver its `aw-tool` Bash calls need approval
    (DEAD-ENDS 2026-10-05), so it cannot reach the spec tools.

## Migration Plan

None. No schema or column changes. Rollback is a revert. On `:8000`, no document carries `slices`
or `roadmap`, so existing behaviour is unchanged.

## Open Questions

- None open. R1 is answered in the review round.
