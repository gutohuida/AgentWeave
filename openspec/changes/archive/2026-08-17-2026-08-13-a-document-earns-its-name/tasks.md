# Tasks — A document earns its name

## 1. Minting a placeholder

- [x] 1.1 New `hub/hub/spec_naming.py`: colour and mythic-animal word lists, lowercase ASCII single
      words so the path contract holds by construction.
- [x] 1.2 `mint_placeholder_path(taken)` — random pair, bounded retry against a `taken` predicate,
      short random suffix as the bounded fallback. Never an unbounded search.
- [x] 1.3 `slugify(subject)` — the Python port of `hub/ui/src/lib/specDocumentName.ts`: NFKD, strip
      combining marks, lowercase, collapse to `-`, trim. Truncate against the *whole path* budget
      (`SPEC_PATH_MAX_LENGTH` less the `spec/changes/` prefix and `/spec.html` suffix), not a bare
      slug length.
- [x] 1.4 `document_path_for(subject)` — slug to full path, `None` when the slug is empty.

## 2. Creation mints when not told

- [x] 2.1 `DocumentCreate.path` becomes `Optional[str]`.
- [x] 2.2 `POST /project/documents` mints when `path` is absent, checking both the database and the
      filesystem for a free name.
- [x] 2.3 The title fallback stops using the last path segment — a placeholder must never become a
      title. A payload's title may not be empty, so an absent one becomes the literal `Untitled
      exploration`; the agent mints the real one when it submits.
- [x] 2.4 The response carries the path (already in `_document_view`); confirm and keep.

## 3. Rename

- [x] 3.1 `spec_service.rename_document(session, workspace, document, subject, *, actor)` — in
      `spec_service` rather than `spec_lifecycle` as first planned, because it needs the workspace as
      well as the session, which is exactly the split those two modules already keep.
- [x] 3.2 Refusals, all before anything moves: approved document; empty slug; target occupied by
      another document row or by an existing file; resulting path fails `validate_spec_path`. Each
      states which condition applied.
- [x] 3.3 Order per design D5: validate → check free → update column and pending queue entries in
      the transaction → move the file → record the event.
- [x] 3.4 Move with `Path.replace` onto the resolved new path, parents created first. Remove the now
      empty old directory only when it is empty.
- [x] 3.5 Update `InboundQueueEntry.spec_document` where it names the old path **and the entry is not
      yet delivered**. Delivered entries are history and stay.
- [x] 3.6 Record a `renamed` event carrying both paths. No CHECK constraint on
      `spec_document_events.kind`, so no migration.
- [x] 3.7 Agent route `POST /spec/documents/rename` in `hub/hub/api/v1/agent_actions.py`, taking
      `{path, subject}` with `extra="forbid"`, returning `{path, previous_path}`.
- [x] 3.8 Emit `spec_updated` carrying both paths.

## 4. The tool

- [x] 4.1 `rename_spec_document(path, subject)` in `hub/hub/mcp_server.py` — **above the `__main__`
      guard**, which stays last.
- [x] 4.2 Docstring states that the subject is prose, that the Hub derives the path, and that the
      return names the path to use for the rest of the turn.
- [x] 4.3 Add it to `_tool_surface_lines` in `hub/hub/api/v1/agents.py` so the described surface
      matches the served one — `test_tool_surface_matches_server.py` fails the build otherwise.

## 5. The turn notice

- [x] 5.1 `spec_turn_notice(EXPLORING)` gains the rename instruction: rename as soon as the interview
      establishes the subject.
- [x] 5.2 Later phases do not get it — a proposed or approved document has already been named.

## 6. The UI stops guessing

- [x] 6.1 `NewConversationSurface.tsx:75` and `ConversationView.tsx:165` stop calling
      `documentPathFor`; they create without a path and read the minted one from the response.
- [x] 6.2 Delete `documentPathFor` from `hub/ui/src/lib/specDocumentName.ts`, and the module itself
      if `slugify` has no other caller. Update `specDocumentName.test.ts` accordingly.
- [x] 6.3 The open-document reference follows a rename: on `spec_updated` carrying `previous_path`,
      swap `SpecDocumentPanel`'s path, update router state, invalidate the old query key.

## 7. The renderer (folded in from `the-spec-tool-reaches-the-agent` task 6.1)

- [x] 7.1 `_acceptance` in `hub/hub/spec_render.py` sorts criteria by their requirement's position in
      `payload.requirements`, **stably**.
- [x] 7.2 Open questions render "None outstanding" when the list is empty.

## 8. Tests — agent-verifiable

Everything here is asserted by the suite; none of it requires a human.

- [x] 8.1 `hub/tests/test_spec_naming.py` — minted path matches `spec/changes/<word>-<word>/spec.html`
      and passes `validate_spec_path`; two mints differ across a sample; a `taken` predicate that
      refuses the first N candidates still yields a free path; a predicate refusing everything
      terminates rather than hanging; slugify cases including accents, punctuation-only input
      (`None`), and a subject long enough to exercise the whole-path budget.
- [x] 8.2 `hub/tests/test_spec_documents_api.py` — create with no path returns a minted one; create
      with a path is unchanged; the minted path shares no word with the title; the title is not the
      placeholder.
- [x] 8.3 `hub/tests/test_spec_rename.py` — new. Subject becomes path; file moved and old path gone;
      identifier, content, requirement identifiers and events unchanged; pending queue entry follows;
      delivered queue entry does not; refusals for approved, empty slug, occupied path; nothing moved
      on refusal.
- [x] 8.4 `hub/tests/test_mcp_tool_schemas.py` — the rename tool's schema takes `subject` and **no**
      destination path.
- [x] 8.5 `hub/tests/test_mcp_server_stdio_surface.py` — the tool is in the spawned surface.
- [x] 8.6 `hub/tests/test_spec_turn_notice.py` — exploring carries the rename instruction; later
      phases do not.
- [x] 8.7 `hub/tests/test_spec_render.py` — criteria grouped by requirement order; stable within a
      requirement; "None outstanding" on an empty list.
- [x] 8.8 UI: `specDocumentName.test.ts` deleted with the module it covered; `newConversationSurface`
      asserts creation sends no path and adopts the minted one; new `specDocumentRename.test.tsx`
      asserts `spec_updated` carrying `previous_path` moves the open document and leaves every other
      case alone.
- [x] 8.9 `pytest hub/tests/ -q` — **1688 passed, 10 skipped**. `pytest tests/ -q` — **360 passed,
      3 skipped**. `npx tsc --noEmit` clean. `npx vitest run` — 828 passed; two unrelated files
      (`chartersUi`, `runnersUi`) hit the 5s per-test timeout under full-suite load and pass in
      isolation, which they also do at `HEAD`.
- [x] 8.10 `ruff check hub/ src/` — clean. `black` — clean on every file touched.
- [x] 8.11 `npx openspec validate --changes --strict` — 11 passed. `--specs --strict` — 30 passed.
- [x] 8.12 `hub/hub/static/ui` refreshed from `hub/ui/dist` after `npm run build`, `diff -rq`
      reports no difference.

## 8b. Driven against the running Hub

Hub restarted onto the implementing commit, health `ok`, project `aw-loop-4`. Not a test — the real
HTTP surface, the real database, real files.

- Created with **no path**: `spec/changes/russet-thunderbird/spec.html`, phase `exploring`, file on
  disk, `<title>` carrying the operator's sentence and the path carrying none of it.
- Created a **second document with the identical title**: `spec/changes/indigo-salamander/spec.html`.
  Two distinct names where the old client-side fallback produced `exploration` twice and refused the
  second as `document_exists`.
- Renamed over the agent route with the subject `Personal reading tracker` →
  `spec/changes/personal-reading-tracker/spec.html`, `previous_path` returned, **file moved and the
  `russet-thunderbird` directory gone**.
- Refusals, live: `???` → `subject_unusable`; a name another document holds → `document_exists`.
- **`../../../etc/passwd` as the subject** → `spec/changes/etc-passwd/spec.html`. An ordinary
  hyphenated name inside the exploration root, which is the point of taking a subject rather than a
  path.
- Artefacts created for this check were removed afterwards; `amber-griffin` is untouched.

## 9. Human-only verification

These cannot be asserted by a test and need the operator in front of the running app.

- [x] 9.1 **Is the placeholder pleasant?** Create a document from the composer and look at what it is
      called. `amber-griffin` is a judgement about tone, not a property.
      **Answered by the operator, 2026-08-16: pleasant, keep it.** The document in `aw-loop10` was
      minted `spec/changes/ivory-salamander/spec.html`, titled "Untitled exploration", and was
      visible under that name for 71 seconds before the agent renamed it.
- [ ] 9.2 **Does the rename feel timely?** Watch a real interview and judge whether the agent renames
      at the moment the subject becomes clear, too eagerly, or not at all.
      **WAIVED for archiving, 2026-08-17.** `.claude/autonomous/2026-08-15-judgement-evidence.md`
      §9.2 has a measured artefact from `spec_document_events`: created 11:00:53, run 1 starts
      11:01:11 (+18s), renamed 11:02:04 — +53s into the turn, 19s before it ended. The placeholder
      was visible 71s total, renamed after the agent read the code and before it replied. The
      timing is real and recorded; "timely" itself is still a felt call, so left unticked rather
      than claimed done.
- [ ] 9.3 **Does the panel move cleanly?** Whether the open document following a rename reads as the
      same document moving or as a jump to a different one.
      **WAIVED for archiving, 2026-08-17.** judgement-evidence.md §9.3 states this explicitly:
      "Not captured. Requires watching the UI during the rename. Still open — needs a live run with
      the Spec panel open." No unattended path exists to drive an interview through a live rename
      and observe the panel transition; left unticked rather than fabricated.
- [x] 9.4 **Is the reordered acceptance table more readable?** Compare against the live
      `amber-griffin` document.
      **Verified 2026-08-17, code-level rather than felt.** judgement-evidence.md §9.4 traced the
      described defect (criteria rendering in raw submission order, e.g. FR-8, FR-8, FR-7) to
      `hub/hub/spec_render.py`'s `_acceptance`, which now sorts stably by requirement order.
      `hub/tests/test_spec_render.py::test_acceptance_criteria_are_grouped_by_requirement_order`
      encodes exactly that regression (docstring: "The live document ran FR-8, FR-8, FR-7 —
      submission order, not requirement order") and passes today, confirmed live: `pytest
      hub/tests/test_spec_render.py -k acceptance_criteria_are_grouped -v` → 1 passed. This is a
      direct proof the described defect is fixed, not an aesthetic judgment call.

## 10. User test guide

**Setup.** Hub running on `:8010`. Open a project in the specification workspace.

1. **A document is born nameless.** Start a new exploration from the composer with an opening message
   like *"I want something to keep track of my reading."* Look at the document's path in the panel.
   - *Expect:* `spec/changes/<colour>-<animal>/spec.html` — two arbitrary words. **Not** anything
     derived from your sentence.
2. **A second one does not collide.** Start another exploration, with the same opening sentence.
   - *Expect:* a different placeholder. Before this change the second attempt could be refused as
     `document_exists`.
3. **The agent names it.** Answer the agent's interview questions until the subject is clearly
   established, then let it reply.
   - *Expect:* the document's path changes to something like
     `spec/changes/personal-reading-tracker/spec.html`, and the panel you are looking at follows it
     without you clicking anything.
   - *Expect on disk:* the file is at the new path and the old directory is gone.
4. **Content survived.** Read the document after the rename.
   - *Expect:* identical content, same requirement identifiers (`FR-1`…), nothing renumbered.
5. **An approved document is fixed.** Take a document to `approved`, then ask the agent to rename it.
   - *Expect:* a refusal that says the document is approved. The path does not change.
6. **The table reads in order.** Open a document with several acceptance criteria.
   - *Expect:* the Requirement column runs `FR-1, FR-1, FR-2, FR-3…` — never back to a lower number.
7. **Questions are accounted for.** Open a document that has no open questions.
   - *Expect:* the open-questions section says none are outstanding, rather than being absent.

**Where it would go wrong:** if step 3 leaves the panel on a dead path, D6 is incomplete; if step 3
renames but a turn already queued fails, task 3.5 is incomplete.
