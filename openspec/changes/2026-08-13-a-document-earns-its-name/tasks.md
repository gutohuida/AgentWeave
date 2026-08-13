# Tasks — A document earns its name

## 1. Minting a placeholder

- [ ] 1.1 New `hub/hub/spec_naming.py`: colour and mythic-animal word lists, lowercase ASCII single
      words so the path contract holds by construction.
- [ ] 1.2 `mint_placeholder_path(taken)` — random pair, bounded retry against a `taken` predicate,
      short random suffix as the bounded fallback. Never an unbounded search.
- [ ] 1.3 `slugify(subject)` — the Python port of `hub/ui/src/lib/specDocumentName.ts`: NFKD, strip
      combining marks, lowercase, collapse to `-`, trim. Truncate against the *whole path* budget
      (`SPEC_PATH_MAX_LENGTH` less the `spec/changes/` prefix and `/spec.html` suffix), not a bare
      slug length.
- [ ] 1.4 `document_path_for(subject)` — slug to full path, `None` when the slug is empty.

## 2. Creation mints when not told

- [ ] 2.1 `DocumentCreate.path` becomes `Optional[str]`.
- [ ] 2.2 `POST /project/documents` mints when `path` is absent, checking both the database and the
      filesystem for a free name.
- [ ] 2.3 The title fallback stops using the last path segment — a placeholder must never become a
      title. Absent title stays empty; the agent mints the real one on submit.
- [ ] 2.4 The response carries the path (already in `_document_view`); confirm and keep.

## 3. Rename

- [ ] 3.1 `spec_lifecycle.rename_document(session, workspace, document, subject, *, actor)`.
- [ ] 3.2 Refusals, all before anything moves: approved document; empty slug; target occupied by
      another document row or by an existing file; resulting path fails `validate_spec_path`. Each
      states which condition applied.
- [ ] 3.3 Order per design D5: validate → check free → update column and pending queue entries in
      the transaction → move the file → record the event.
- [ ] 3.4 Move with `Path.replace` onto the resolved new path, parents created first. Remove the now
      empty old directory only when it is empty.
- [ ] 3.5 Update `InboundQueueEntry.spec_document` where it names the old path **and the entry is not
      yet delivered**. Delivered entries are history and stay.
- [ ] 3.6 Record a `renamed` event carrying both paths. No CHECK constraint on
      `spec_document_events.kind`, so no migration.
- [ ] 3.7 Agent route `POST /spec/documents/rename` in `hub/hub/api/v1/agent_actions.py`, taking
      `{path, subject}` with `extra="forbid"`, returning `{path, previous_path}`.
- [ ] 3.8 Emit `spec_updated` carrying both paths.

## 4. The tool

- [ ] 4.1 `rename_spec_document(path, subject)` in `hub/hub/mcp_server.py` — **above the `__main__`
      guard**, which stays last.
- [ ] 4.2 Docstring states that the subject is prose, that the Hub derives the path, and that the
      return names the path to use for the rest of the turn.
- [ ] 4.3 Add it to `_tool_surface_lines` in `hub/hub/api/v1/agents.py` so the described surface
      matches the served one — `test_tool_surface_matches_server.py` fails the build otherwise.

## 5. The turn notice

- [ ] 5.1 `spec_turn_notice(EXPLORING)` gains the rename instruction: rename as soon as the interview
      establishes the subject.
- [ ] 5.2 Later phases do not get it — a proposed or approved document has already been named.

## 6. The UI stops guessing

- [ ] 6.1 `NewConversationSurface.tsx:75` and `ConversationView.tsx:165` stop calling
      `documentPathFor`; they create without a path and read the minted one from the response.
- [ ] 6.2 Delete `documentPathFor` from `hub/ui/src/lib/specDocumentName.ts`, and the module itself
      if `slugify` has no other caller. Update `specDocumentName.test.ts` accordingly.
- [ ] 6.3 The open-document reference follows a rename: on `spec_updated` carrying `previous_path`,
      swap `SpecDocumentPanel`'s path, update router state, invalidate the old query key.

## 7. The renderer (folded in from `the-spec-tool-reaches-the-agent` task 6.1)

- [ ] 7.1 `_acceptance` in `hub/hub/spec_render.py` sorts criteria by their requirement's position in
      `payload.requirements`, **stably**.
- [ ] 7.2 Open questions render "None outstanding" when the list is empty.

## 8. Tests — agent-verifiable

Everything here is asserted by the suite; none of it requires a human.

- [ ] 8.1 `hub/tests/test_spec_naming.py` — minted path matches `spec/changes/<word>-<word>/spec.html`
      and passes `validate_spec_path`; two mints differ across a sample; a `taken` predicate that
      refuses the first N candidates still yields a free path; a predicate refusing everything
      terminates rather than hanging; slugify cases including accents, punctuation-only input
      (`None`), and a subject long enough to exercise the whole-path budget.
- [ ] 8.2 `hub/tests/test_spec_documents_api.py` — create with no path returns a minted one; create
      with a path is unchanged; the minted path shares no word with the title; the title is not the
      placeholder.
- [ ] 8.3 `hub/tests/test_spec_rename.py` — new. Subject becomes path; file moved and old path gone;
      identifier, content, requirement identifiers and events unchanged; pending queue entry follows;
      delivered queue entry does not; refusals for approved, empty slug, occupied path; nothing moved
      on refusal.
- [ ] 8.4 `hub/tests/test_mcp_tool_schemas.py` — the rename tool's schema takes `subject` and **no**
      destination path.
- [ ] 8.5 `hub/tests/test_mcp_server_stdio_surface.py` — the tool is in the spawned surface.
- [ ] 8.6 `hub/tests/test_spec_turn_notice.py` — exploring carries the rename instruction; later
      phases do not.
- [ ] 8.7 `hub/tests/test_spec_render.py` — criteria grouped by requirement order; stable within a
      requirement; "None outstanding" on an empty list.
- [ ] 8.8 UI: `specDocumentName.test.ts` updated; a test that creating sends no path and adopts the
      returned one; a test that `spec_updated` with `previous_path` moves the open panel.
- [ ] 8.9 `pytest hub/tests/ -q` and `pytest tests/ -q`, run separately with the Python311
      interpreter. `npx vitest run` and `npx tsc --noEmit` from `hub/ui`.
- [ ] 8.10 `ruff check hub/ src/`, `black` on every file touched.
- [ ] 8.11 `npx openspec validate --changes --strict` and `--specs --strict`.
- [ ] 8.12 `hub/hub/static/ui` refreshed from `hub/ui/dist` after `npm run build`, confirmed with
      `diff -rq`.

## 9. Human-only verification

These cannot be asserted by a test and need the operator in front of the running app.

- [ ] 9.1 **Is the placeholder pleasant?** Create a document from the composer and look at what it is
      called. `amber-griffin` is a judgement about tone, not a property.
- [ ] 9.2 **Does the rename feel timely?** Watch a real interview and judge whether the agent renames
      at the moment the subject becomes clear, too eagerly, or not at all.
- [ ] 9.3 **Does the panel move cleanly?** Whether the open document following a rename reads as the
      same document moving or as a jump to a different one.
- [ ] 9.4 **Is the reordered acceptance table more readable?** Compare against the live
      `amber-griffin` document.

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
