## 1. Reading a document's identity from its file

- [x] 1.1 Add a function that, given workspace and path, returns a document's adoptable identity — title and kind from `extract_payload`, phase from `aw-spec-status` via the existing `_SpecHeadParser` — or a stated reason it cannot be adopted. Read-only; no write path.
- [x] 1.2 Apply the phase fallback from design D3: `current` for `kind == "capability"`, `exploring` otherwise, when the status metadata is absent or names no known phase. Return whether the phase was read or defaulted, and the unrecognised value where there was one.
- [x] 1.3 Return a distinct refusal for a file with no payload block versus one whose payload is present but unparseable, so the response can say which.
- [x] 1.4 Unit tests for 1.1–1.3 against fixture documents: payload present, payload absent, payload malformed, status absent, status unrecognised, capability versus change-spec defaulting.

## 2. Adopting one document

- [x] 2.1 Add the single-document adoption route. Resolve the path through `ProjectWorkspace`, refuse anything escaping the `spec/` tree before reading the file.
- [x] 2.2 Refuse with a stated reason when the path already has a row; do not create, do not modify.
- [x] 2.3 On success, call `spec_lifecycle.create_document` with the identity from task 1, then `spec_index.reindex_from_file` to index its requirements. Neither writes to disk.
- [x] 2.4 Set `content_digest` from the file as found (design D6), so later drift detection has a baseline.
- [x] 2.5 Add request/response schemas: the adopted document's id, path, title, kind, phase, whether the phase was read or defaulted, and the requirement-index result.
- [x] 2.6 Register the route and confirm it is operator-authenticated, not run-credential authenticated.

## 3. Reporting disagreement without resolving it

- [x] 3.1 When adoption is refused because a row exists, compare the file's title, kind and phase against the row's and report each differing field with both values.
- [x] 3.2 Report an empty difference list when file and row agree, rather than omitting the field — an absent list and an empty one must not be ambiguous to a reader.
- [x] 3.3 Assert in a test that neither the row nor the file changes when a disagreement is reported.

## 4. Adopting a corpus

- [ ] 4.1 Add the corpus-wide adoption route: `discover()` the `spec/` tree, adopt each untracked adoptable document, skip the rest with a stated reason per path.
- [ ] 4.2 Follow reindex's response shape — a per-path map plus a diagnostics list — so the two operations read alike.
- [ ] 4.3 Surface `discover()`'s truncation diagnostic when `MAX_DISCOVERED_DOCUMENTS` is hit, so a truncated sweep is never presented as complete.
- [ ] 4.4 Ensure a single unadoptable document cannot abort the sweep.
- [ ] 4.5 Test repeatability: a second run adopts nothing, reports every path as already tracked, and creates no duplicate rows.

## 5. The read-only guarantee

- [ ] 5.1 Test that a successful adoption leaves the file **byte-identical**. Assert on bytes, not on the row — a row-only assertion passes against the current destructive behaviour and is worthless.
- [ ] 5.2 Test that a refused adoption leaves the file byte-identical, for each refusal reason.
- [ ] 5.3 Test that corpus-wide adoption leaves every file in the tree byte-identical.
- [ ] 5.4 Mutation-check the three tests above: confirm each fails if a write is introduced into the adoption path.

## 6. Downstream reachability

- [ ] 6.1 Test that an adopted document's requirements resolve by identifier through the existing lookup.
- [ ] 6.2 Test that an adopted change-spec document accepts a phase transition (close-exploration).
- [ ] 6.3 Test that reindex files a previously `unindexable_document` after adoption, with its real title and kind, and stops reporting it as unindexable.
- [ ] 6.4 Test that `GET /specs` reports a non-null `document_id` and phase for an adopted document.

## 7. Verification the agent can run

- [ ] 7.1 `py -3.11 -m pytest hub/tests/ -q --ignore=hub/tests/browser` — full suite green, no new failures.
- [ ] 7.2 `py -3.11 -m ruff check` and `black --check --target-version py311` clean.
- [ ] 7.3 Confirm no migration was added and no model column changed — this change touches no schema.
- [ ] 7.4 Confirm `POST /documents` is byte-for-byte unchanged, and that its own tests still pass.
- [ ] 7.5 Confirm neither `spec_manifest.py` twin was touched (design D7); if either was, synchronise both and run `hub/tests/test_spec_manifest_roundtrip.py`.

## 8. Verification only a human can do

These cannot be closed by the agent. They need the operator, a browser, and this repository's own
corpus — which is the case that motivated the change.

- [ ] 8.1 **The corpus adopts.** Register this repo as a project, run corpus-wide adoption over `spec/`, and confirm the response lists 34 capability documents plus `spec/agentweave.html`.
- [ ] 8.2 **Nothing was destroyed.** Run `git status` and `git diff --stat` on `spec/` afterwards. **The expected result is no change at all.** This is the single most important check in the list.
- [ ] 8.3 **The Spec tab gained a lifecycle.** Open the Spec tab; documents that previously showed no phase now show one, and the phase bar is populated.
- [ ] 8.4 **`unfiled` is gone.** Run reindex after adoption and confirm `project-instructions` and `quiet-hours` are filed with real titles rather than path-derived ones.
- [ ] 8.5 **Requirements arrived.** Open a document with requirements and confirm coverage renders against it.
- [ ] 8.6 **The disagreement report reads clearly.** Adopt an already-adopted path and confirm the refusal explains itself in terms the operator can act on.

## 9. User test guide

- [ ] 9.1 Write the operator-facing test guide for this change: what to run, in what order, what a correct result looks like, and what a wrong one looks like. Lead with 8.2 — the check that the files were not modified — because that is the failure this change exists to prevent.
