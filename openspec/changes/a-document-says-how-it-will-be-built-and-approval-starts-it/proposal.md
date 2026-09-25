# Proposal — a document says how it will be built, and approval starts it

**Round 1, 2026-09-25**, from an interactive explore with the operator on request **R1** (F377).
Second of two changes; it builds on `a-flow-is-configured-from-its-own-tab`. **Round 2,
2026-09-25**, re-derived it against the code (design.md, "Round 2"). **Nothing here is
implemented yet.**

## Why

Approving a document creates its board (`hub/hub/api/v1/spec.py:1620-1631`), but nothing then works
that board. The operator's only way to start a flow is to ask an agent to call `create_flow`, which
F376 showed can be refused by a setting the operator never saw, and which lost a whole night. Three
more things are wrong at the same moment:

- **Nobody asks how the change will be built.** The exploring interview (`launchability.py:357-370`,
  `api/v1/agents.py:1574-1587`) covers what to build and never who builds it, how often, or when to
  stop. So approval has nothing to act on.
- **The flow's settings are chosen by whoever happens to create it**, after approval, away from the
  conversation where the work was understood.
- **Approval says nothing about what it did.** `materialise_quietly` (`spec_tasks.py:472-493`) turns
  a total failure into a log warning and returns `[]`. The response's `tasks_created: []` reads the
  same for "declared nothing" as for "blew up". Tasks skipped as `already_served`, and dependencies
  recorded as not honoured, are invisible too.

## What Changes

The operator's decisions from the explore are marked *(operator)*.

- **The exploring interview asks "How will this be built?"** It nudges towards a flow: parallel
  tasks, self-review, stops when the queue empties. If the operator chooses a flow, the agent asks
  for the default agent (from the project's open agents, now listed in the spec turn), the stop
  condition and the cadence. "No flow" is a valid answer. *(operator)* Only change documents are
  asked, since only they must answer (R2).
- **A new payload section, `delivery`:** `{"mode": "flow", "agent", "stop_when_queue_empties",
  "stop_at", "cron"}` or `{"mode": "none"}`. `submit_spec_document` gains the parameter (MCP and
  HTTP prose).
- **Proposing requires it.** A change document with no `delivery` is refused at propose with a
  completeness finding, and so is a flow delivery missing an agent or a stop condition. It is not
  checked at approval, so documents proposed before this change stay approvable. *(operator:
  forced)*
- **The document shows its delivery**, and, **before approval, flags it as stale** when the named
  agent is not an open agent on the project. The flag is computed each time the document is read,
  never written into the file. *(operator: stale is shown)*
- **Approval creates the flow**, with the operator as the actor (so `allow_agent_jobs` never
  applies). It is named after the document, and its first firing is on the **next scheduled tick**.
  If the flow cannot be created (agent not open on the project, document claimed in a race, bad
  cadence, no stop condition, a stop time already past), **the document is still approved**, and
  the report says why. *(operator)* A flow that already declares the document, as on a re-approval,
  is reported as the document's flow, not as a refusal (R2). At approval the operator may pick a
  replacement agent for a stale delivery. The document is not edited; the report records the choice.
- **The board is always created**, flow or not, as today. *(operator)*
- **Every approval writes an approval report:** tasks created, tasks skipped as already served,
  dependencies not honoured, a total failure to create the board (now caught in a savepoint, so it
  can no longer undo the approval), and the flow created or not created with the reason. It is
  stored as a document event, returned when the document is read, and shown on the document. When
  no flow was created, it offers change 1's **Start a flow…** for as long as no flow declares the
  document. A board that fails part-way leaves none of its tasks behind (R2).

## Capabilities

### Modified Capabilities

- `spec-document-authority`: ADDS "A change document declares how it will be built before it is
  proposed", "The exploring interview asks how the change will be built", and "A document's delivery
  is checked against the roster when it is read".
- `agent-flows`: ADDS "Approving a document creates the flow its delivery declares".
- `task-lifecycle-governance`: ADDS "Approval reports what it created and what it could not".

## Impact

- **Backend:**
  - `spec_payload.py`: an optional `Delivery` model.
  - `spec_completeness.py`: new finding codes.
  - `launchability.py`, `api/v1/agent_trigger.py` and `api/v1/agents.py`: interview text for
    change documents, plus a roster line in spec turns.
  - `mcp_server.py`: the `submit_spec_document` parameter; `.claude/rules/mcp-server.md` applies.
  - `spec_render.py`: a Delivery section.
  - `api/v1/spec.py`: `set_phase` creates the flow and writes the report; `GET` returns the report and
    the stale state.
  - `spec_tasks.py`: savepoint and outcome.
  - `api/v1/jobs.py`: the flow-creation body is extracted into `build_flow_rows`, which flushes
    and never commits and which both routes call. `POST /jobs` then commits once, so a failed loop
    insert no longer leaves its job row behind.
- **UI:** `SpecPhaseBar.tsx` (the stale strip and the approve-time agent choice), a new
  `SpecApprovalReport.tsx` in `SpecDocumentPanel.tsx`, `api/spec.ts`, `hooks/useSSE.ts` (loops
  refresh on `job_created`, the document on agent archive), and a bundle refresh.
- **No migration.** The report is a `spec_document_events` row with a new `kind`, a column that has
  no CHECK constraint (`db/models.py:2109-2149`).
- **Order:** after change 1. Also after `a-document-moves-forward-only-through-its-checks` (B5: it
  moves the checks into `transition()`, the base the propose gate builds on) and after
  `a-loop-that-is-gone-lets-go-of-its-document` (B11: the claim and adoption path this reuses).
  Rebase the interview text onto `an-at-mention-an-agent-wrote-reads-no-file` if it lands first
  (it edits `spec_turn_notice`). `a-specification-is-read-in-results-that-fit` edits the
  neighbouring `read_spec_document` prose, not these lines.
- **Pinned text:** `hub/tests/test_spec_turn_notice.py` and `test_exploring_interview_medium.py` pin
  the interview wording, and the new question is added beside those pins, not in place of them.
- **Test churn (R2):** `test_spec_documents_api.py:564` pins one event per approval, which becomes
  two, and the change-spec fixtures that are proposed in seven test files gain a `delivery`.
