# Tasks — task dependencies

Groups 1–4 are observable but inert: edges exist and nothing enforces them. That is a good state to
sit in if the gate needs more confidence before it lands. Group 5 is the first that changes
behaviour.

## 1. The payload

- [x] 1.1 Add `depends_on: List[str]` to `spec_payload.Task`. Default empty — an existing document must validate unchanged. Landed `hub/hub/spec_payload.py:120-123`: `depends_on: List[str] = Field(default_factory=list, ...)`. An existing document with no `depends_on` key on any task validates unchanged — every existing `test_spec_payload.py` test still passes untouched (23 passed before this section's new tests were added).
- [x] 1.2 Write the `Field(description=...)`. These **are** the agent-facing instructions — *"One concrete unit of work, not 'build the whole thing'"* is how decomposition is taught today, and ordering gets taught in the same place. Say that keys name siblings in this document. Landed alongside 1.1: *"Keys of sibling tasks in THIS document — local only — that must be approved before this one may start. An imported entry (see `from`) is named the same way once declared, so it can be depended on like any other sibling. This is where ordering gets taught, the same place decomposition is."*
- [x] 1.3 Add the imported-entry shape: an entry naming another document's path and a task key in it, distinguishable from a locally-declared task. Decide whether that is a discriminator field on `Task` or a separate list, and record which in design D4 when you find out which reads better in a real payload. **Decided: a discriminator field on `Task` (`from_`, aliased to the reserved word `from`), single `tasks` list — not a separate `imported_tasks` list.** Wrote a realistic cross-document payload both ways before deciding (see the round-trip test added for 1.5, which is the shape that was actually tried): with a discriminator, an imported entry is `{key, from: {document, key}}` sitting in the same list a sibling's `depends_on` already indexes into by key — no second collection to cross-reference when materialising or rendering a nav strip. A separate `imported_tasks: List[dict]` list was the alternative on the table; it keeps ordinary `Task` structurally simple (no field that's required for one kind of entry and forbidden for another) but means every consumer of `depends_on` — the gate, the board, `materialise()` — has to look in two lists to resolve one key, and duplicate-key checking has to run across both rather than one. The discriminator also matches design D4's own diagram literally (the imported entry is drawn *inside* `tasks:`, marked "← IMPORTED", not in a second block) — that diagram is the design's illustration of its own decision, so departing from it would need a reason the design doesn't give. Recorded in `design.md` D4 (new subsection below the original decision) with the rejected alternative and why. Implementation: `ImportedFrom(_Part)` submodel (`document`, `key`) rather than a raw `Dict[str, str]`, so a malformed import (missing `document` or `key`) is a normal pydantic field error at payload validation, the same mechanism every other nested part already uses — not a new one. `description` and `requirements` became optional (`default=""` / `default_factory=list`) because an imported entry legitimately carries neither; this is a real, deliberate loosening of what payload *shape* validation enforces (previously both keys had to be present, even if empty, for any task), justified because nothing today enforces non-empty `description` at either the shape or completeness layer regardless (checked: no `spec_completeness.py` finding exists for a blank description), and `requirements` emptiness was already shape-legal (`test_a_task_with_no_requirements_is_well_formed_but_incomplete`) — so the change extends an existing permissiveness to cover the one field (`description`) that hadn't needed it before imports existed.
- [x] 1.4 Write its description too, including that the referenced document must be approved and why. Landed on `ImportedFrom.document` (`hub/hub/spec_payload.py`): *"Path of the document that owns this task. It must be approved: a task cannot import work from a document nobody has signed off on, and until it is, the imported dependency names nothing a reader or an approver can rely on."* — the "why" is stated, not just the rule, matching 1.2's standard and the task's own instruction.
- [x] 1.5 Round-trip test: a payload with dependencies and imports survives render → `extract_payload` → validate unchanged. `test_a_round_trip_with_local_dependencies_and_an_import_loses_nothing` (`hub/tests/test_spec_payload.py`) — a two-task payload (one imported entry, one local task with `depends_on: [that imported entry's key]`) through `payload_to_dict(validate_payload(...))` → `embed_payload` → `extract_payload`, asserts the recovered dict is byte-for-byte equal to what was stored, AND that re-validating the recovered dict produces the same dict again (not just JSON-equal once). Needed one supporting fix to make the round trip actually lossless: `payload_to_dict` now calls `model_dump(mode="json", by_alias=True)` — without `by_alias=True` the aliased `from_` field would have serialised back out as the key `"from_"` instead of `"from"`, silently renaming the field on every save. Two narrower tests also added: `test_a_local_depends_on_names_a_sibling_key` and `test_an_imported_entry_needs_no_description_or_requirements`. The file went from 20 tests to 23 (3 new, 0 removed, all 20 pre-existing ones still pass unchanged); ran `pytest hub/tests/test_spec_payload.py hub/tests/test_spec_declared_tasks.py hub/tests/test_spec_board_task_convergence.py -q` → **38 passed** (the latter two files exercise `materialise()` against the same `Task` shape and were unaffected). Also ran `ruff check`, `black --check` (reformatted the new test file once, then clean) and `mypy hub/spec_payload.py` — all clean.

## 2. Completeness checks

- [ ] 2.1 Report a `depends_on` key that resolves to neither a local task nor an imported entry.
- [ ] 2.2 Report a cycle among locally-declared tasks. Depth-first over the declared keys; the graph is small.
- [ ] 2.3 Report an import naming a document that is not approved.
- [ ] 2.4 All three are **blocking**, never a submission refusal (design D7). Test that submitting a document with all three problems succeeds and returns all three in `blocking`.
- [ ] 2.5 State the limit in the cycle check's own message: cycles are detected within a document, not across documents. A reader who sees cycle detection will otherwise assume it is complete.

## 3. Storage

- [ ] 3.1 Migration `0083` (head is `0082`). Bump the head assertions in **both** `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`.
- [ ] 3.2 `task_dependencies` table: `task_id`, `depends_on_task_id`, project scope. Index both directions — the gate reads one way, the board reads both.
- [ ] 3.3 **Decide the foreign key** (design D3, open). `Question.blocked_task_id` deliberately has none — *"the block record must outlive a deleted task rather than cascade or refuse"* — and the reasoning may not transfer. Record the decision and its reason in `models.py`, either way.
- [ ] 3.4 `SpecDocument.first_approved_at`, nullable. Comment it against `explore_closed_at`: that one is **reset** on reopen (*"reopening genuinely reopens"*), and this one never is. The comment is the whole point — the two columns look identical and behave oppositely.
- [ ] 3.5 Backfill `first_approved_at` from the `kind="phase"` event history, whose detail carries `{"from", "to"}`.
- [ ] 3.6 Guard the migration for a missing table, as `0033`/`0034` do — an upgrade from an early revision reaches it with only that revision's tables.

## 4. Materialisation

- [ ] 4.1 `materialise()` creates the declared edges after creating the tasks, since an edge needs both ends.
- [ ] 4.2 An imported entry **resolves to the existing task and never creates one**. This is the one new rule in a mature function — do not let it grow a second.
- [ ] 4.3 An unresolvable import is preserved and reported, following `absorb_free_text`'s precedent (`spec_tasks.py:204-206`) rather than inventing a mechanism.
- [ ] 4.4 Re-approving a revised document adds new edges and **does not touch existing tasks** — `spec_tasks.py:19-21`, *"a task that already exists is never touched."* Decide explicitly whether that covers *edges* of an existing task, which did not exist when the rule was written, and record the answer.
- [ ] 4.5 Test re-approval twice: no duplicate tasks, no duplicate edges.
- [ ] 4.6 Test that a document declaring no dependencies materialises exactly as before.

## 5. The gate — the first behaviour change

- [ ] 5.1 Add the third guard in `task_transition_service`, beside `_guard_author_is_not_reviewer` and the `requirement_gate` call. **Same place, before the history row** — that placement is a requirement, not a style choice.
- [ ] 5.2 Gate `→ in_progress` only. Not `→ assigned`, not `→ rejected`.
- [ ] 5.3 Gate the `blocked → in_progress` resume edge the same way.
- [ ] 5.4 Met means the prerequisite is `approved`. Nothing earlier.
- [ ] 5.5 A distinct error type, so the refusal is distinguishable from an illegal transition and names the unmet prerequisites.
- [ ] 5.6 A prerequisite that is `rejected` gates permanently and the refusal says so — a different message from "not yet approved", because the remedy is different.
- [ ] 5.7 Refuse recording a dependency for a task with no `spec_document_id`, stating that dependencies are declared by a document (design D5).
- [ ] 5.8 Test every surface: operator route, agent HTTP, tool surface, jobs. The point of the placement is that all four are covered without knowing it — assert that rather than assume it.
- [ ] 5.9 Test that a task with no dependencies transitions exactly as before.

## 6. The rename refusal

- [ ] 6.1 Change `rename_document`'s check from `phase == APPROVED` to "has ever been approved".
- [ ] 6.2 Test the two holes this closes: approve → archive → rename, and approve → reopen → rename. Both must now refuse.
- [ ] 6.3 Test that a never-approved document still renames.
- [ ] 6.4 Check whether any existing test asserted the archived-rename path worked. If one does, it encoded the hole — fix the test and say so in the commit.

## 7. Reading dependencies

- [ ] 7.1 Expose a task's prerequisites and dependents on the task read model.
- [ ] 7.2 Expose derived state: gated, gated-on-rejected, running-on-regressed. Derived per request, not stored — a stored readiness column is a denormalised join that goes stale (design D1).
- [ ] 7.3 A board endpoint returning one document's tasks with edges, in one call. The board must not N+1 its way to a layout.
- [ ] 7.4 Board list with outstanding counts, for the picker.

## 8. The board

- [ ] 8.1 Layer assignment: longest-path depth, so a task sits below **everything** it depends on rather than below its first prerequisite.
- [ ] 8.2 Top-to-bottom layout, converging edges drawn.
- [ ] 8.3 **Reuse `TaskCard`.** A board that grows its own card component is how the two views diverge (design, risks).
- [ ] 8.4 Confirm the status badge reads correctly as the only status signal — `TaskCard.tsx:235` already renders it, where it is currently redundant with the column.
- [ ] 8.5 Document picker with outstanding counts, plus the standing "no document" board.
- [ ] 8.6 Collapse a layer whose tasks are all terminal; expandable. Do not collapse a partly finished layer.
- [ ] 8.7 Imported entries drawn as off-board references naming their document.
- [ ] 8.8 **The three stalled states, distinguished** (design D8): gated, waiting-on-review, gated-on-rejected. Surface "layer N is waiting on M reviews" at the layer, not only per card — this is the mitigation for the change's main risk and it is a display rule protecting a lifecycle rule.
- [ ] 8.9 Mark a running task whose prerequisite regressed.
- [ ] 8.10 No editing affordance for structure. Where an operator tries, say dependencies are changed by editing the document.
- [ ] 8.11 View toggle; the seven-column board unchanged.
- [ ] 8.12 Decide what "good enough" edge routing is **before** implementing it. Crossing minimisation in a layered DAG is a known hard problem and an unbounded one to polish.
- [ ] 8.13 `make ui` after `npm run build`, and commit `hub/ui/src` and `hub/hub/static/ui` together.

## 9. The loop's claim — without this the change deadlocks every loop

Design D10. Depends on `loop-notices-and-reacts` having landed the shared claim decision; if it has
not, this group builds against the current `_claim_loop_task` and that change adapts it instead.

- [ ] 9.1 Test the deadlock first, before fixing it: a loop over a document declaring A → B, with A
      unapproved, must not claim B on every firing forever. Assert the current failure, then flip the
      assertion — the same order that caught the spin on 2026-08-20.
- [ ] 9.2 Test: a queue holding an older gated task and a newer startable one claims the newer, and
      leaves the older with its status and no assignee.
- [ ] 9.3 Test: a queue where every task is gated claims nothing, and the job stays enabled with no
      stop reason recorded.
- [ ] 9.4 Test: approving the prerequisite makes the gated task claimable on the next firing, with no
      other action.
- [ ] 9.5 Test the agreement directly — every task a firing claims can move to `in_progress` without
      the dependency gate refusing it. This is the whole property; assert it rather than inferring it
      from the cases above.
- [ ] 9.6 Implement the skip using the **same** dependency determination the gate in group 5 uses.
      A second implementation is the drift `_loop_queue_order`'s comment records; import it.
- [ ] 9.7 Skip unstartable tasks in queue order rather than stopping at the first one.
- [ ] 9.8 Distinguish the two stall reasons: waiting on work that can still be approved, versus gated
      on a `rejected` prerequisite. Different remedies, so different messages.
- [ ] 9.9 Test that a rejected-gated queue does **not** stop the loop, and that reversing the
      rejection and approving revives it with no further operator action.
- [ ] 9.10 Confirm the board's derivation agrees with the firing's for a gated queue — the same
      13.1 property, now with dependencies in it.

## 10. Verification an agent can do

- [ ] 10.1 `py -3.11 -m pytest hub/tests/ -q --ignore=hub/tests/browser` passes.
- [ ] 10.2 `py -3.11 -m pytest tests/ -q` passes.
- [ ] 10.3 `ruff check hub/`, `black --check hub/`, `mypy hub/hub/` clean on touched files; `cd hub/ui && npm run lint`.
- [ ] 10.4 Test the whole chain: document declares A → B → C, approve, confirm B cannot start until A is **approved** (not merely completed), and C not until B is.
- [ ] 10.5 Test a cross-document import end to end: approve document 1, import its task into document 2, approve 2, confirm the edge points at the existing task and no duplicate was created.
- [ ] 10.6 Test the regression case: A approved, C started, A → revision_needed. C's status is unchanged and C is reported as running on a regressed prerequisite.
- [ ] 10.7 Test the rejected case: A rejected, B refused with a message naming A and distinguishable from "not yet approved".
- [ ] 10.8 Confirm `spec_completeness`'s existing checks are unchanged — this change adds three and must alter none.
- [ ] 10.9 Confirm the seven-column board's tests still pass untouched.

## 11. Verification only a human can do

- [ ] 11.1 **The shape is legible.** Open the board for a real decomposition. The order of work is apparent without reading a single description.
- [ ] 11.2 **The stall is diagnosable.** Let a layer sit completed and unreviewed. The board says work is waiting on review — not merely that downstream cards are gated. If this reads as "the feature is broken", it is.
- [ ] 11.3 **The gate is honest in a live run.** Ask an agent to start a task whose prerequisite is unapproved. The refusal tells it what to wait for, in words it can act on.
- [ ] 11.4 **The review chain is bearable.** Walk a three-deep chain with two agents. Judge whether the review cost per wave is acceptable — this is the change's main risk and only real use answers it.
- [ ] 11.5 **The board does not lie about foreign work.** With a cross-document import, confirm the reference names the owning document and that the blocker is reachable from it.
- [ ] 11.6 **Collapse behaves.** Finish a layer, confirm it collapses, expand it, confirm the graph still reads.
- [ ] 11.7 **Structure really is read-only.** Try to drag, delete, or otherwise alter an edge. Confirm the refusal explains itself rather than nothing happening.
- [ ] 11.8 **The picker earns its place.** Confirm outstanding counts make choosing a board and seeing what is left one act.

## 12. User test guide

- [ ] 12.1 Write the operator-facing test guide: what to declare, in what order to approve, what should be startable at each point, and what should not. Lead with 10.2 — an unattended review backlog and a broken dependency gate look identical from the outside, and if the board cannot tell them apart the feature is unusable no matter how correct the graph is.
