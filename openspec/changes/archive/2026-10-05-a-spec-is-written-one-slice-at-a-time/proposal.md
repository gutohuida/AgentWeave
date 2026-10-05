## Why

**Tier 1.** Source: `openspec/explorations/2026-09-29-specs-that-evolve-by-slice.md`, section *2026-10-05: re-grounded at `9dd11cc`* (operator decisions Q13–Q16, and 2026-10-05's split, trigger and Q14 answers).

A product spec run today means one change document that holds the whole request. The only two real
runs on record (`:8000`, LoopEngine, read with `mode=ro`) each grew to 77 requirements and 32 tasks.
The first took 19 h from creation to approval and grew 5 → 9 → 19 → 77 requirements over 19
whole-document resubmissions in one night. Its delivery then cost about six times its authoring and
landed 12 of 47 tasks. Nothing in the product pushes back on size:
- The tool docs every authoring agent reads (`hub/hub/mcp_server.py` `create_spec_document`,
  `submit_spec_document`) and `SPEC_PHASE_DUTIES` (`hub/hub/api/v1/agents.py:1704-1729`) never mention
  it.
- The only slicing advice is in an optional seeded charter (`hub/hub/data/charters/spec.md:91-92`).
- The `roadmap` kind that could hold the plan is vocabulary only. An agent cannot create one
  (`hub/hub/api/v1/agent_actions.py:1588`), it has no slices, and the completeness check would refuse
  it for having no requirements (`hub/hub/spec_completeness.py:167-174`).

So a large request should become **a roadmap plus one small slice**. The next slice is drafted only
once the current one is built, so what was learned building slice N shapes slice N+1 (F496,
amended 2026-10-05).

## What Changes

- **An agent may create a `roadmap`** as well as a `change-spec` (`create_spec_document` gains a
  `kind`). Capability documents stay refused.
- **A roadmap carries ordered slices, and no requirements or tasks.**
  - The payload gains `slices[]`, each with a key, title, intent, done criterion and builds-after.
  - These are validated, rendered, and returned on the agent read.
  - Completeness for a roadmap asks for slices, not requirements. A roadmap's approval materialises
    nothing.
- **A change document may name the roadmap slice it specifies**, as `roadmap: {document, slice}`.
  Proposing it is refused unless that roadmap is approved and holds that slice. The link lives in
  the slice's own payload, not in the corpus index, because only the operator may set a document's
  place in the index (`spec-corpus-map`) and a rename does not update it.
- **Approving a slice can ask for the next one, which is drafted once the slice is built.** The
  approval request takes `draft_next_slice`, on by default in the app.
  - The Hub records the request. When every task linked to the slice has been approved or rejected,
    it queues a turn, as the operator, to the agent that created the approved slice, in the
    conversation where that agent created it. The turn names the built slice's tasks and their
    outcomes, and asks it to draft the next slice in the roadmap's order.
  - The approval response says what happened: waiting for tasks, queued (no tasks), last slice, or
    no authoring agent.
  - No new queue origin is added, so no migration is needed.
- **Authoring guidance where every agent reads it.** The tool docs and `SPEC_PHASE_DUTIES` say:
  - a request larger than one slice becomes a roadmap plus slice 1;
  - a slice is about a dozen requirements or fewer, as a few tasks;
  - later slices are recorded in the roadmap, not specified.
- **Non-goals:**
  - Hard limits on requirements per document or per slice: the guidance is measured, not enforced.
  - Amendments to approved documents.
  - Slice-end review.
  - The 3-requirement ceiling and rejected-evidence gating, which belong to the sibling change
    `a-task-may-serve-a-whole-slice`.
  - Placing slices in the corpus tree (`spec/index.json` stays operator-arranged).
  - A new queue origin, or any migration.
  - Drafting more than one slice ahead.
  - Changing how a slice's own tasks are materialised.

## Capabilities

### New Capabilities
- `spec-roadmaps`: the roadmap document's slices, the slice-to-roadmap link, drafting the next slice
  once the approved one is built, and the authoring guidance that prefers a roadmap and a slice over one large document.

### Modified Capabilities
- `agent-document-creation`: "An agent may begin only a change specification" becomes "An agent may
  begin a change specification or a roadmap".
- `spec-document-authority`: "Who may start a document is determined by its kind…" now lets an agent
  create a roadmap.

## Impact

- **Hub:**
  - `spec_payload.py` (`Slice`, `slices`, `roadmap` link, per-kind validation);
  - `spec_completeness.py` (roadmap and slice-link findings);
  - `spec_render.py`;
  - `agent_actions.py` (create kind, read view);
  - `mcp_server.py` (`create_spec_document`, `submit_spec_document` parameters and docs);
  - `api/v1/agents.py` (`SPEC_PHASE_DUTIES`);
  - `api/v1/spec.py` `set_phase` (`draft_next_slice`, queueing through `inbound_queue.new_entry` and
    `turn_scheduler.schedule_agent`, the same pattern as `agent_trigger.py:2507-2523`);
  - `task_transition_service.apply_transition` (the last task of a requested slice closing queues
    the drafting turn, through the new `slice_drafting.py`).
- **UI:** the approval control gains "Draft the next slice" for a document that names a roadmap
  slice. The bundle is refreshed, and it reaches `:8000` on its next reload.
- **No migration.** On `:8000`, no existing document carries `slices` or `roadmap`, so nothing
  existing changes behaviour.
