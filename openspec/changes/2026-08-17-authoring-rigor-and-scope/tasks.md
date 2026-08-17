# Tasks — rigor-gated editing, in-position proposals, authoring scope

Ordered per `design.md`: data model (1) before the functions that use it (2), functions before the
routes that call them (3), backend before UI (4), F1-F3 (rigor gating) independent of F4 (tool
scoping) so either can land first — F4 is sequenced last only because it touches a different module
(`runner_commands.py`) with no shared code, not because it depends on F1-F3.

## 1. Data model — `spec_edit_proposals`

- [ ] 1.1 Add `SpecEditProposal` to `hub/hub/db/models.py` per `design.md` D3's column table. Index on
      `(document_id, status)`.
- [ ] 1.2 New migration (next head after 0074) adding the table. Guard for a missing parent table the
      way 0033/0034/0073/0074 do. No `CheckConstraint` naming a column — `status`/`unit_kind`/
      `change_kind` are validated in the one writer function (D3), not at the schema layer.
- [ ] 1.3 Bump the head assertions in `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py` (CLAUDE.md).

## 2. F1/F2 — the diff-and-propose path

- [ ] 2.1 In `hub/hub/spec_service.py`, add `async def propose_edit(...)` per `design.md` D1/D2: diff
      the incoming payload's requirements (by stable id) and metadata bundle against the document's
      currently stored content; create one `SpecEditProposal` row per changed unit; create none for a
      no-op submission.
- [ ] 2.2 In `save_document()`, branch on `document.rigor`: `sketch` keeps today's path unchanged;
      `contract`/`gate` calls `propose_edit()` instead of writing, and returns a `ProposeResult` (new
      response shape — created proposal ids/units, and which units were unchanged) instead of
      `SaveResult`.
- [ ] 2.3 Unit tests: a `gate`-rigor document's submission creates the expected proposals and does not
      change the live document (assert both); a `sketch`-rigor document's identical submission still
      applies immediately (regression guard — this is the one path that must not change); an
      unchanged resubmission against `contract`/`gate` creates zero proposals and is not reported as
      an error; a submission changing three requirements and the summary creates exactly four
      proposals (three `modify` + one `metadata`).

## 3. F3 — accept, reject, attribution, staleness

- [ ] 3.1 `async def accept_proposal(...)` and `async def reject_proposal(...)` in `spec_service.py`
      per `design.md` D4: operator-only, enforced in the function; refuses a non-`pending` proposal;
      `accept_proposal` refuses on digest mismatch (D5, sets `status="stale"`) and otherwise applies
      the unit, calls `spec_lifecycle.record_content` with the new optional `accepter` parameter
      alongside the existing proposer actor, sets `status="accepted"`.
- [ ] 3.2 Extend `spec_lifecycle.record_content` (additive `accepter: Optional[Actor] = None`
      parameter) so existing single-actor callers are unaffected and the accepted-proposal path can
      record both names on the resulting `SpecDocumentEvent` — dual attribution needs both fields to
      exist somewhere reachable from the event; if `SpecDocumentEvent` cannot cleanly carry a second
      actor without its own schema change, use `SpecEditProposal`'s own
      `proposer_actor_*`/`resolved_by_actor_name` columns as the attribution record instead and have
      `record_content` cite the proposal id — decide and note which, do not silently assume.
- [ ] 3.3 Routes in `hub/hub/api/v1/spec.py`: `GET /documents/{path}/proposals` (list pending, each
      with both payloads for a diff view), `POST /documents/{path}/proposals/{id}/accept`, `POST
      .../reject` — following the existing `RigorRequest`/`_document_view` pattern.
- [ ] 3.4 Unit tests: an agent-kind actor attempting accept/reject is refused, proposal status
      unchanged (mirrors `test_spec_rigor.py`'s operator-only test if one exists — reuse its pattern);
      accepting applies only the targeted unit, leaving sibling pending proposals untouched; accepting
      a proposal whose digest has moved (simulate: accept a second proposal first, then attempt the
      first) is refused and marked `stale`; a rejected proposal leaves the live document byte-identical
      to before rejection; the resulting event/record names both proposer and accepter distinctly and
      both survive a second read.

## 4. F2 UI — in-position rendering

- [ ] 4.1 `GET /spec/documents?path=` (or the operator equivalent already used by the Spec tab) surfaces
      pending proposals per requirement id and the metadata unit, reusing 3.3's list route.
- [ ] 4.2 The requirement renderer (wherever `SpecCoverageBar`/`SpecPhaseBar`/the document view render
      a requirement today) shows a pending-proposal indicator at that requirement, with accept/reject
      controls an operator can use without leaving the document.
- [ ] 4.3 The metadata proposal (if any) shows at the document's summary/problem/scope section with
      the same controls.
- [ ] 4.4 `npm run lint`, `npx tsc --noEmit`, `npm test` clean; rebuild the UI bundle
      (`cd hub/ui && npm run build && python scripts/refresh_ui_bundle.py`) and commit source + bundle
      together (CLAUDE.md).

## 5. F4 — authoring turns lose file-write tools

- [ ] 5.1 In `hub/hub/runner_commands.py`'s `build_command`, when the triggering call passes
      `spec_document` (threaded from `agent_trigger.py:267` the same way it already reaches
      `_spec_phase_for`), append `--disallowedTools "Edit,Write,NotebookEdit"` for Claude and force
      `--sandbox read-only` for Codex, per `design.md` D6. Confirm the flag composes correctly with an
      already-present `--allowedTools "mcp__agentweave__*"` (both can be present on the same command —
      confirm the CLI accepts both, do not assume).
- [ ] 5.2 Extend `spec_turn_notice()` (`hub/hub/launchability.py:222-264`) with a line stating the
      restriction is in effect and that discovered implementation work should be proposed via
      `create_task` — only once 5.1 makes it mechanically true, not before.
- [ ] 5.3 Unit tests: `build_command` with `spec_document` set includes the restriction flag for both
      Claude and Codex branches; `build_command` with `spec_document` unset is byte-identical to
      before this change (regression guard — this is the path every non-spec turn takes).
- [ ] 5.4 Live check against the trial Hub (`testbed/scratch/`, gitignored, delete after): trigger an
      agent with a specification document open, confirm the spawned process's actual command line (not
      just the constructed string) carries the restriction; confirm `create_task` still succeeds in
      the same turn.

## 6. Retire 14.15

- [ ] 6.1 Update `openspec/changes/2026-07-30-hub-native-experience/tasks.md`'s 14.15 line from
      "confirmed superseded design, needs re-wording or explicit retirement" to a waived closure
      citing this change's `design.md` D7, matching the waive-with-reason convention this run's N6
      pass already used elsewhere in that file. Do this only once this change's own tasks are
      implemented and merged — not as part of authoring it.

## 7. Whole-stack verification

- [ ] 7.1 `pytest hub/tests -n 8` full suite green against the session's last recorded baseline count
      plus this change's new tests.
- [ ] 7.2 `pytest tests/ -n 4` unchanged (CLI side untouched by this change).
- [ ] 7.3 `openspec validate --changes --strict` and `--specs --strict` both clean.
- [ ] 7.4 `ruff check hub/ src/`, `black --check` on every touched file, `npm run lint`,
      `npx tsc --noEmit` all clean.

## 8. User test guide

**Setup.** A project with a specification document at `gate` rigor carrying at least two requirements
(promote one from `sketch` through `contract` to `gate` if none exists — `spec_rigor.py`'s promotion
check needs stable, non-duplicate requirement ids, already true of any document that reached 14.1's
identifier requirement).

1. **Ask an agent to revise two requirements on the gate-rigor document.** — *Expect:* the document's
   text does not change immediately. Two pending proposals appear, each shown at the requirement it
   targets, not buried in a separate screen.
2. **Accept one proposal, leave the other pending.** — *Expect:* only the accepted requirement's text
   changes; the other requirement still shows its original text with its proposal still pending.
3. **Reject the remaining proposal.** — *Expect:* the requirement's text is exactly what it was before
   either proposal existed — no leftover marker, no partial text.
4. **Check who gets credit.** Find where the accepted change's history is shown. — *Expect:* it names
   both the agent that proposed it and you (the operator) as the one who accepted it — not just one or
   the other.
5. **Open a specification document in the chat composer and ask the agent to fix a bug it notices in
   the code while reading around the spec.** — *Expect:* it cannot edit the file directly (no Edit/
   Write tool succeeds); it should instead say it created a task for the fix, and that task should
   exist on the board afterward.
6. **Repeat step 1's edit against a `sketch`-rigor document instead.** — *Expect:* this one still
   applies immediately, no proposal, unchanged from how editing worked before this change existed.

**Where it would go wrong:** if step 1 shows the document already changed, the gate did not engage. If
step 3 shows any trace of the rejected text, "no residue" was not achieved. If step 5's agent still
edits the file, F4's tool restriction did not reach the actual spawn command — check the real process
command line, not just the code that builds it.
