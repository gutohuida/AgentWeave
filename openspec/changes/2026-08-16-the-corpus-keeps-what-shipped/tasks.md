# Tasks — The corpus keeps what shipped

## 1. Migration `0074`

- [x] 1.1 `hub/hub/migrations/versions/0074_archive_and_capability_phase.py`. Guard function mirrors
      `0058`/`0073`: read `sa.inspect(conn).get_table_names()`, no-op if `spec_documents` or `projects`
      is absent.
- [x] 1.2 `batch_alter_table("spec_documents", recreate="always")`: drop `ck_spec_documents_phase`,
      recreate it with `("exploring", "proposed", "approved", "archived", "current")`; add
      `ck_spec_documents_kind` (`kind IN (...)` over `spec_payload.KINDS`, which task 4.4 below has
      already grown to include `"capability"` — write the literal SQL list once both are decided, not
      as a separately-maintained copy); add `ck_spec_documents_kind_phase` (the cross-column CHECK from
      design D6).
- [x] 1.3 Guarded `op.create_table("spec_document_merges", ...)` per design D4/D6, columns, the
      `actor_kind = 'operator'` CHECK, and both indexes — same call shape as `0065`'s
      `spec_document_events`.
- [x] 1.4 `downgrade()`: reassign `archived` rows to `approved` and `current` rows to `approved` before
      dropping the two new CHECKs and restoring the three-value phase CHECK (design D6); drop
      `spec_document_merges`'s indexes then the table.
- [x] 1.5 Bump the migration-head assertion in `hub/tests/test_migrations.py` **and**
      `hub/tests/test_project_persistence.py` to `0074` (CLAUDE.md's standing instruction for this
      exact step).
- [x] 1.6 `alembic upgrade head` against a copy of a pre-`0074` database; confirm no error and that
      existing rows are unaffected (`kind='change-spec'`, `phase` one of the original three all satisfy
      both new CHECKs trivially). `alembic downgrade -1` then `upgrade head` again, round-trips clean.

## 2. Model

- [x] 2.1 `hub/hub/db/models.py`: `SPEC_PHASES` gains `"archived"`, `"current"`. Update the CHECK
      definition on `SpecDocument.__table_args__` to match `ck_spec_documents_phase`'s new values, and
      add `ck_spec_documents_kind` / `ck_spec_documents_kind_phase` as declared in the migration — the
      model and the migration must describe the same schema, per this codebase's existing convention of
      keeping `__table_args__` and its originating migration in agreement.
- [x] 2.2 New `SpecDocumentMerge` class, exactly as specified in design D4.
- [x] 2.3 `hub/hub/db/engine.py` or wherever `Base.metadata` is exercised for a fresh `create_all` —
      confirm `SpecDocumentMerge` is picked up with no additional registration (it will be, by
      inheriting `Base`, but verify the fresh-database test path exercises it).

## 3. Lifecycle (`hub/hub/spec_lifecycle.py`)

- [x] 3.1 `ARCHIVED = "archived"`, `CURRENT = "current"` module constants, beside the existing three.
- [x] 3.2 `TRANSITIONS` gains `(APPROVED, ARCHIVED)`. Nothing added for `CURRENT` — design D1.
- [x] 3.3 `create_document`: initial `phase` is `CURRENT` when `kind == "capability"`, else `EXPLORING`
      as today.
- [x] 3.4 `transition()`: the unknown-phase guard admits `ARCHIVED`, still refuses `CURRENT` as a
      `to_phase` (design D1 — the only door into `current` is creation). The operator-only check for
      `to_phase == APPROVED` gains a sibling for `to_phase == ARCHIVED`, same shape, same
      `PhaseError` type, new `code="archive_is_the_operators"`.
- [x] 3.5 `record_content` drops its `kind` parameter (design D3) — the caller (`save_document`) has
      already asserted `payload.kind == document.kind` before calling it, so there is nothing left for
      this function to vary. Update its one call site.

## 4. Service (`hub/hub/spec_service.py`)

- [x] 4.1 `save_document`: new refusal, before the existing `document.phase == APPROVED` check —
      `payload.kind != document.kind` → `SaveRefusedError(code="kind_is_fixed")` (design D3).
- [x] 4.2 `save_document`: new refusal — `document.kind == "capability" and actor.kind != "operator"` →
      `SaveRefusedError(code="capability_write_is_the_operators")` (design D2). Placed so it is checked
      regardless of phase, since a capability document's phase is always `current` and phase-based
      refusals don't otherwise touch it.
- [x] 4.3 New `merge_document(session, workspace, capability_document, source_documents, payload, *,
      actor, note)` in `spec_service.py` implementing design D5 steps 5–7 (the write via
      `save_document`, the `SpecDocumentMerge` rows, the `merged` event). Steps 1–4 (resolution and
      refusals) live in the API handler, matching this file's existing split between "the API resolves
      what a path names" and "the service acts once it has documents in hand."
- [x] 4.4 **Load-bearing, found in round 2 review — without this, nothing else in this change works.**
      `hub/hub/spec_payload.py`: `KINDS` gains `"capability"`. `validate_payload` checks
      `payload.kind not in KINDS` (line 216) unconditionally, before either of 4.1/4.2's refusals ever
      run — and the *existing, unchanged* `create_document` API route already calls `save_document`
      immediately after creating any document (`hub/hub/api/v1/spec.py`'s `create_document`, payload
      `{"kind": document.kind, ...}`). So creating a capability document at all — not merging into one,
      just creating the empty scaffold — would call `validate_payload` with `kind="capability"` and be
      refused `payload_invalid` ("kind must be one of baseline, system-map, roadmap, change-spec") if
      this task is skipped. Design D2 states the `KINDS` change in prose but round 1's `tasks.md` never
      turned it into a checklist item; this task closes that gap. No other code change needed at the
      Pydantic layer — `SpecPayload.kind` is already a bare `str`, not a Python enum.

- [x] 4.5 **Found in round 3 review.** `hub/hub/mcp_server.py`'s `SpecKind = Literal["baseline",
      "system-map", "roadmap", "change-spec"]` (line 787) is a restated copy of `spec_payload.KINDS`,
      not an import — `mcp_server.py` may import only stdlib + fastmcp (CLAUDE.md). It must be updated
      to include `"capability"` too, or `hub/tests/test_mcp_tool_schemas.py::
      test_spec_kind_agrees_with_the_payload_validator` (`assert set(typing.get_args(mcp_server.SpecKind))
      == set(KINDS)`) fails the moment task 4.4 lands — a mechanical, deterministic breakage, not a
      judgment call. Verified this does not change agent-reachable behaviour: `submit_spec_document`
      (the MCP tool using this type) only writes content to a document that already exists
      (`hub/hub/api/v1/agent_actions.py:1099`'s route 404s otherwise), and document *creation*
      (`spec.py:811`'s `create_document`) is reached only through the operator's own project credential
      (`Depends(get_project)`, hardcoded `actor=_operator()`) — there is no agent-reachable route that
      creates a document at all. So an agent could construct a schema-valid call naming
      `kind="capability"` against an *existing* capability document, but `save_document`'s task-4.2
      refusal (`capability_write_is_the_operators`) still catches it exactly as it would any other
      caller — this task keeps the restated type honest, it does not open a new door.
      **Also confirmed out of scope, not a gap:** `hub/hub/spec_manifest.py`'s `VALID_KINDS` and
      `hub/ui/src/api/spec.ts`'s `SpecEntry.kind` union (line 15) both name the same four strings but
      belong to the unrelated on-disk manifest/index subsystem (`spec/index.json`, "filed" /
      "unindexed" / "unfiled" documents) — a different `kind` vocabulary for a different content type,
      never read or written by anything this change touches. Left untouched.

## 5. API (`hub/hub/api/v1/spec.py`)

- [x] 5.1 `MergeRequest` Pydantic model per design D5, `extra="forbid"`.
- [x] 5.2 `POST /project/documents/{path:path}/merge`: resolve the capability document
      (`_require_document`), refuse `not_a_capability` if its `kind` is not `capability`, resolve every
      `from_changes` path via `_require_document` (404 naming the missing one), refuse
      `source_not_finished` for any source not in `(APPROVED, ARCHIVED)`, call
      `spec_service.merge_document(...)`, commit, broadcast `spec_updated` for the capability document's
      path, return `_document_view(document)` plus the created merge ids.
- [x] 5.3 `_document_view`: no change needed — `kind` and `phase` are already surfaced; confirm the
      response for a capability document reads sensibly (`kind: "capability"`, `phase: "current"`,
      `explore_closed: false` since `explore_closed_at` is never set for one — note this in the response
      rather than treating it as a defect, since nothing reads `explore_closed` for a document that
      never explores).
- [x] 5.4 `GET /project/documents` (`list_documents`) and any other route that lists documents by
      `phase` or filters — audit for an implicit assumption that `phase` is one of the original three
      (e.g., a hardcoded `IN` clause anywhere outside `spec_lifecycle.py`); fix any found, or state in
      the log that none exist.

## 6. Agent route refusal (`hub/hub/api/v1/agent_actions.py`)

- [x] 6.1 `submit_spec_document`: confirm — by reading, and by test 8.x below — that the new
      `save_document` refusal (task 4.2) reaches this route with no code change here required (design
      D2's point: the refusal lives one layer down). If the route currently catches `SaveRefusedError`
      by a fixed set of `code` values and maps unrecognised ones to a generic 500, extend that mapping
      to include `capability_write_is_the_operators` and `kind_is_fixed` so the agent gets a legible
      refusal rather than an opaque failure.

## 7. UI (`hub/ui/src`)

- [x] 7.1 `SpecPhaseBar.tsx`: narrow the "Reopen" condition to `phase === 'proposed' || phase ===
      'approved'` (design D7 — fixes the latent bug for `archived`/`current` as a side effect of adding
      them).
- [x] 7.2 `SpecPhaseBar.tsx`: new "Archive" button, `phase === 'approved'` only, calling
      `useSetSpecPhase` with `to: 'archived'`. No new mutation hook.
- [x] 7.3 Phase chip: muted visual treatment for `archived` and `current` (CSS/token choice, not a new
      component).
- [x] 7.4 `hub/ui/src/api/spec.ts` (or wherever `useSpecDocuments`'s response type lives): confirm the
      TypeScript type for `phase` includes the two new literals so a UI branch on `document.phase`
      type-checks against all five rather than silently widening to `string`.
- [x] 7.5 `cd hub/ui && npm run build && python ../../scripts/refresh_ui_bundle.py` after the above,
      confirming `hub/hub/static/ui/ui-build-stamp.json` updates and `diff -rq` between `dist/` and the
      committed bundle reports no difference (CLAUDE.md's standing rule for any `hub/ui/src` change).

## 8. Tests — agent-verifiable

Everything here is asserted by the suite; none of it requires a human.

- [x] 8.1 `hub/tests/test_migrations.py`: head is `0074`; `0074` upgrades cleanly from `0073` on a
      populated database (existing rows satisfy both new CHECKs); downgrade round-trips (task 1.6,
      turned into an assertion).
- [x] 8.2 `hub/tests/test_project_persistence.py`: head assertion updated to `0074`.
- [x] 8.3 New `hub/tests/test_spec_archive.py`: an approved document archives when the operator calls
      `transition(to_phase=ARCHIVED)`; an agent actor calling the same is refused with
      `archive_is_the_operators`; archiving a `proposed` or `exploring` document is refused as an
      illegal transition (not in `TRANSITIONS`); archiving does not touch the document's requirements,
      digests, or any `Task` row; an archived document has no legal outgoing transition (attempting
      `to_phase="exploring"` from `archived` is refused).
- [x] 8.4 New `hub/tests/test_spec_capability_kind.py`: creating a document with `kind="capability"`
      lands it at `phase="current"` with no `explore_closed_at`; `transition()` refuses any `to_phase`
      against it, including `"current"` itself (unknown-phase-for-transition, per design D1); an
      agent's `submit_spec_document` against a capability document is refused
      `capability_write_is_the_operators`; the identical payload submitted by the operator succeeds; a
      payload whose `kind` differs from the document's recorded `kind` is refused `kind_is_fixed`,
      tested against a capability document and, separately, against an ordinary `change-spec` document
      (design D3's fix is not capability-specific).
- [x] 8.5 New `hub/tests/test_spec_merge.py`: a merge from an approved change document into a capability
      document writes the payload, creates one `SpecDocumentMerge` row per named source, and one
      `"merged"` event on the capability document; a merge naming a source still `exploring` or
      `proposed` is refused `source_not_finished`; a merge naming a source whose `kind` is `capability`
      (a capability document cannot itself be a merge source) — **round 2 note: this is not actually
      undecided.** D5 step 4 already refuses any source whose `phase` is not `(APPROVED, ARCHIVED)`,
      and a capability document's phase is always `current` (D1) — so citing one as a source is already
      refused today, by the same `source_not_finished` code, as a side effect of the phase gate, with no
      extra code needed. The only real decision left is whether `source_not_finished` is the right
      *message* for a document that was never a change to begin with — worth a distinct error string in
      the same refusal branch if it is easy, not worth a new refusal path if it is not. Assert the
      refusal happens; treat the message wording as a nice-to-have, not a blocker. A merge against a non-capability
      target document is refused `not_a_capability`; two merges from different changes into the same
      capability accumulate two rows, not one overwritten row; a merge's payload is still subject to
      every existing `save_document` refusal (e.g. malformed payload → `payload_invalid`, unchanged
      behaviour).
- [x] 8.6 `hub/tests/test_spec_documents_api.py` (existing file): add coverage for the new
      `POST /project/documents/{path}/merge` route's request/response shape, and for
      `POST /project/documents/phase?to=archived` going through the ordinary phase route with no new
      endpoint needed.
- [x] 8.7 `hub/tests/test_spec_lifecycle.py` or equivalent existing coverage of `transition()`: extend
      the existing table-driven tests (if any) to cover the two new phase values rather than duplicating
      them in a new file, if an existing file already parametrises over `SPEC_PHASES`/`TRANSITIONS`.
- [x] 8.8 UI: `SpecPhaseBar.test.tsx` (existing or new) — "Reopen" absent for `archived` and `current`
      fixtures; "Archive" present only for `approved`; phase chip renders the literal phase name for all
      five values.
- [x] 8.9 `pytest hub/tests/ -n 8` and `pytest tests/ -n 4` — both green, counts recorded in the log
      against the `verified_green_at_b2b0cd5` baseline in `STATE.json`.
- [x] 8.10 `cd hub/ui && npm test`, `npm run lint`, `npx tsc --noEmit` — all clean.
- [x] 8.11 `ruff check hub/ src/` and `black --check` on every file touched — clean.
- [x] 8.12 `npx openspec validate --changes --strict` (this change validates) and
      `npx openspec validate --specs --strict` (the modified `spec-document-authority` delta merges
      cleanly) — both clean.

## 9. Driven against the running Hub

Not a test — the real HTTP surface, the real database, real files. Restart the trial Hub
(`environment.restart_command` in `STATE.json`) onto the implementing commit first; confirm `/health`
reports `ok` before trusting any observation.

- [x] 9.1 Create a document with `kind="capability"` via the API; confirm it appears at `phase:
      "current"` and that `POST /project/documents/phase?to=approved` against it is refused.
      Driven against the restarted trial Hub (commit 55af280): created `spdoc-6b4fb89d` at
      `spec/capabilities/n2-drive-test/spec.html`, landed at `phase: "current"`; the approve attempt
      returned 409 `illegal_transition`.
- [x] 9.2 Approve an ordinary change document (materialising its tasks, as today), then archive it;
      confirm its tasks are unchanged (`GET` the tasks, compare `spec_document_id` and `status` before
      and after). Created `spdoc-c30f9725`, submitted content via a directly-minted run credential
      (mirroring the test suite's technique — no live agent process needed), closed exploration,
      proposed, approved (materialised `task-b3fd0764`), then archived. `GET` on the task before and
      after archiving returned byte-identical `status`, `updated`, and `spec_document_id`.
- [x] 9.3 Merge that archived change into the capability document created in 9.1, citing it by path;
      confirm the capability document's content updates and `GET
      /project/documents` (or wherever merges surface, if anything does yet — this change ships no
      dedicated merge-history UI) shows the row exists at the database level.
      `POST .../merge` returned 200 with `merged: 1`; queried `spec_document_merges` directly —
      `spmrg-ef98fcdc` (capability_document_id=spdoc-6b4fb89d, change_document_id=spdoc-c30f9725,
      actor_kind=operator); `GET /project/spec` on the capability path shows the rendered HTML with
      `aw-spec-kind: capability`, `aw-spec-status: current`, and the merged content.
- [x] 9.4 Attempt the same merge again with a source still in `proposed`; confirm `source_not_finished`.
      A second change document (`spdoc-...`, proposed but not approved) named as `from_changes`
      returned 409 `source_not_finished`, message naming the path and its actual phase.
- [x] 9.5 Attempt to write capability-document content through the ordinary agent route
      (`submit_spec_document`, using a live run's credential rather than the operator's project
      credential); confirm the refusal. Returned 422 `capability_write_is_the_operators`.

## 10. Human-only verification

- [ ] 10.1 **Does "Archive" read as final?** Look at the button beside "Approve" — is it clear this is a
      different kind of action from the reversible phase moves nearby?
- [ ] 10.2 **Is a capability document's phase bar quiet enough?** With no controls rendering for
      `current`, confirm the bar does not look broken or empty — it should read as "there is nothing to
      decide here," not "something failed to load."

## 11. User test guide

**Setup.** Hub running on `:8010`. A project with at least one approved document.

1. **Archive an approved document.** Open an approved document. Click "Archive."
   - *Expect:* the phase chip changes to `archived`. No task on the board changes status.
2. **Archiving is not available earlier.** Open a document still in `proposed` or `exploring`.
   - *Expect:* no "Archive" control anywhere in the phase bar.
3. **A capability document has no decisions to make.** Create a document with kind `capability` (via
   whatever surface this change's own UI work exposes, or the API directly if none does yet).
   - *Expect:* its phase reads `current`. No "Propose," "Approve," "Archive" or "Reopen" button appears
     — only the phase chip and the enforcement (rigor) control.
4. **A capability document rejects an ordinary agent edit.** Ask an agent, in conversation, to submit
   content directly against the capability document's path.
   - *Expect:* the agent's submission is refused; the operator sees the document unchanged.
5. **A merge names its source.** Using the merge route, submit updated content for the capability
   document, citing the archived change from step 1.
   - *Expect:* the capability document's content updates to what was submitted.

**Where it would go wrong:** if step 1 changes a task's status, task 8.3's isolation assertion is
incomplete; if step 4 succeeds, task 4.2's refusal is not actually wired into the path the agent uses.
