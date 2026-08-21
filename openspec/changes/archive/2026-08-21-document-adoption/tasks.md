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

- [x] 4.1 Add the corpus-wide adoption route: `discover()` the `spec/` tree, adopt each untracked adoptable document, skip the rest with a stated reason per path.
- [x] 4.2 Follow reindex's response shape — a per-path map plus a diagnostics list — so the two operations read alike.
- [x] 4.3 Surface `discover()`'s truncation diagnostic when `MAX_DISCOVERED_DOCUMENTS` is hit, so a truncated sweep is never presented as complete.
- [x] 4.4 Ensure a single unadoptable document cannot abort the sweep.
- [x] 4.5 Test repeatability: a second run adopts nothing, reports every path as already tracked, and creates no duplicate rows.

## 5. The read-only guarantee

- [x] 5.1 Test that a successful adoption leaves the file **byte-identical**. Assert on bytes, not on the row — a row-only assertion passes against the current destructive behaviour and is worthless.
- [x] 5.2 Test that a refused adoption leaves the file byte-identical, for each refusal reason.
- [x] 5.3 Test that corpus-wide adoption leaves every file in the tree byte-identical.
- [x] 5.4 Mutation-check the three tests above: confirm each fails if a write is introduced into the adoption path. **Done in two passes** — a write on the success path fails 5.1 and 5.3 (and the module's no-writer check); a write on the refusal path fails all three parametrised cases of 5.2. A single mutation would have left 5.2 unproven.

## 6. Downstream reachability

- [x] 6.1 Test that an adopted document's requirements resolve by identifier through the existing lookup.
- [x] 6.2 Test that an adopted change-spec document accepts a phase transition (close-exploration).
- [x] 6.3 Test that reindex files a previously `unindexable_document` after adoption, with its real title and kind, and stops reporting it as unindexable.
- [x] 6.4 Test that `GET /specs` reports a non-null `document_id` and phase for an adopted document.

## 7. Verification the agent can run

- [x] 7.1 `py -3.11 -m pytest hub/tests/ -q --ignore=hub/tests/browser` — full suite green, no new failures. **2578 passed, 12 skipped, 1 xpassed, 0 failed** (2026-08-20).
- [x] 7.2 `py -3.11 -m ruff check` and `black --check --target-version py311` clean.
- [x] 7.3 Confirm no migration was added and no model column changed — this change touches no schema. `git status` on `hub/hub/migrations/` and `db/models.py` is empty.
- [x] 7.4 Confirm `POST /documents` is byte-for-byte unchanged, and that its own tests still pass. The diff on `api/v1/spec.py` removes **zero** lines — it is purely additive.
- [x] 7.5 Confirm neither `spec_manifest.py` twin was touched (design D7); if either was, synchronise both and run `hub/tests/test_spec_manifest_roundtrip.py`. Neither is modified.

## 8. Verification only a human can do

**Rehearsed 2026-08-20, then run for real the same day.** The rehearsal came first, deliberately:
the first run of a route that *could* overwrite a corpus should not be against the corpus. It used a
throwaway Hub on port 8021, a fresh database, and a **byte-identical copy** of this repository's
`spec/` tree (35 documents) registered as `proj-f8de11d8`. Browser assertions live in
`hub/tests/browser/test_adopted_corpus.py` and were shown to **fail on an identical un-adopted
project** (`proj-2795a7b6`), so they measure adoption rather than the app rendering.

**The real run then followed §9 against the trial Hub on 8010 and this repository's own corpus as
`proj-5e960453`** — every figure below reproduced exactly, `git status --short spec/` stayed empty
across both adoption runs, and the same 9 browser tests passed against the real project. Getting
there needed one correction the chain had wrong: `proj-5e960453` does not exist in
`<repo>/hub/data/agentweave.db`, only in `~/.agentweave/hub/profiles/beta/agentweave.db`, so 8010
was restarted against that database (operator's call) before §9 had a target at all.

What remains open is the three judgements a browser must not be allowed to tick.

- [x] 8.1 **The corpus adopts.** Register this repo as a project, run corpus-wide adoption over `spec/`, and confirm the response lists 34 capability documents plus `spec/agentweave.html`. **Rehearsed:** 35 adopted, 0 skipped, 0 diagnostics; kinds `{capability: 34, system-map: 1}`; phases `{current: 34, exploring: 1}`; all 35 `phase_source: read`, none defaulted; 452 requirements indexed.
- [x] 8.2 **Nothing was destroyed.** Run `git status` and `git diff --stat` on `spec/` afterwards. **The expected result is no change at all.** This is the single most important check in the list. **Rehearsed:** sha256 of all 36 files taken before and after — identical; the copy still `diff -r`-equal to `<repo>/spec`; and `git status --short spec/` in the real repo empty throughout.
- [x] 8.3 **The Spec tab gained a lifecycle.** Open the Spec tab; documents that previously showed no phase now show one, and the phase bar is populated. **Factual half automated** — `quiet-hours` and `project-instructions` render a `current` phase chip and the enforcement control; the `system-map` home renders `exploring`, so the bar reads each document rather than printing a constant. On the un-adopted control the phase bar does not render at all and the title falls back to the path. **Taste, still open:** does the populated bar read as informative, or as clutter?
- [x] 8.4 **`unfiled` is gone.** Run reindex after adoption and confirm `project-instructions` and `quiet-hours` are filed with real titles rather than path-derived ones. **Rehearsed:** before reindex 33 filed / 2 unfiled — exactly those two; after, 35 filed, zero diagnostics, titles `Project instructions` and `Quiet hours`, and `spec/index.json` written with 35 documents.
- [x] 8.5 **Requirements arrived.** Open a document with requirements and confirm coverage renders against it. **Factual half automated** — the coverage control reports a positive count (7 for `agent-charter`) and the rendered document carries its minted `FR-` identifiers; neither renders on the un-adopted control. **Taste, still open:** is the coverage summary useful at a glance?
- [x] 8.6 **The disagreement report reads clearly.** Adopt an already-adopted path and confirm the refusal explains itself in terms the operator can act on. **Rehearsed, and it found a defect** — see below. Now: agreement reports an empty list; a real corpus document edited outside the Hub reports `title -> file: 'Quiet hours, revised' | row: 'Quiet hours'` and `phase -> file: 'exploring' | row: 'current'`. **Taste, still open:** is *"adoption does not update an existing record from its file"* the right thing to say to someone who expected it to?

### What 8.6 found

Driving 8.6 against a real document surfaced a defect the unit tests could not have: the phase
disagreement **was not reported at all**. D3a defaults a phase the document's kind cannot hold, and
`compare` was reading the *resolved* phase — so a `capability` file hand-edited to `exploring`
resolved back to `current`, matched the row, and the operator was told the file and the row agreed
about a file that visibly said otherwise. `compare` now reports the phase **as the file declared
it**. Covered by two new tests. This is the second finding in this change that appeared only on
contact with a real corpus.

### Left for the operator

1. ~~**Run it for real.**~~ **Done 2026-08-20.** §9 was run end to end against 8010 and
   `proj-5e960453`: 35 adopted, 452 requirements, 0 diagnostics; sha256 of all 36 `spec/` files
   identical before and after; the second run skipped all 35 as `document_exists` with no
   differences; the 409 and 422 refusals read as written and left their files untouched; reindex
   filed `project-instructions` and `quiet-hours` with real titles, a 16-line pure insertion into
   `spec/index.json` with nothing removed. **This repository's corpus is now tracked.**
2. **The three taste judgements** marked "still open" above — the only thing left in this section.

## 9. User test guide

- [x] 9.1 Write the operator-facing test guide for this change: what to run, in what order, what a correct result looks like, and what a wrong one looks like. Lead with 8.2 — the check that the files were not modified — because that is the failure this change exists to prevent.

**Setup.** This repository, registered as a project (`proj-5e960453`), against the trial Hub on
port 8010 — never the Hub whose code is being edited. Its own `spec/` tree is the real case: 34
capability documents plus `spec/agentweave.html`, every one carrying a payload block, not one of
them with a row.

**Before anything else, make sure `spec/` is committed and clean.** `git status --short spec/`
should print nothing. Every check below compares against that, and a dirty tree makes step 1
unreadable.

1. **The check that matters — nothing is written.** Run corpus adoption:

   ```bash
   curl -X POST http://127.0.0.1:8010/api/v1/projects/proj-5e960453/project/spec/adopt \
     -H "Authorization: Bearer $AW_KEY"
   ```

   Then, immediately: `git status --short spec/` and `git diff --stat spec/`.
   *Expect:* **both print nothing at all.** Not "only whitespace changed", not "just the status
   line" — nothing.
   *Failure looks like:* any modified file under `spec/`. That is `POST /documents`' behaviour
   leaking into adoption, and it means a document was overwritten with a placeholder. Stop and
   restore from git before doing anything else.

2. **The corpus arrived.** Read the response from step 1.
   *Expect:* 35 entries under `documents`, 35 paths in `adopted`, `skipped` empty, `diagnostics`
   empty. Each adopted entry carries the document's real title and `"phase_source": "read"`.
   *Failure looks like:* fewer than 35; a `discovery_truncated` diagnostic (the tree is bigger than
   the Hub will walk); or titles that read like paths rather than like subjects.

3. **Running it twice is safe.** Run the exact same command again.
   *Expect:* `adopted` empty, all 35 in `skipped`, each with `"code": "document_exists"` and an
   empty `differences` list.
   *Failure looks like:* anything adopted a second time, or a `differences` list with entries in it
   — the second means a file has moved underneath its row since step 1, which should not have
   happened in the space of one command.

4. **The Spec tab gained a lifecycle.** Open the Spec tab in the app.
   *Expect:* documents that previously showed no phase now show one, and the phase bar is
   populated. Capability documents read `current`.
   *Failure looks like:* phases still blank, or a capability document showing something other than
   `current`.

5. **`unfiled` is gone.** Run reindex, then open the Spec tab again.
   *Expect:* `project-instructions` and `quiet-hours` are filed, with their real titles rather than
   names derived from their paths. No `unindexable_document` diagnostics in the reindex response.
   *Failure looks like:* either document still unfiled — the exact symptom this change was written
   for.

6. **Requirements arrived.** Open a document that declares requirements and look at coverage.
   *Expect:* coverage renders against real requirement identifiers.
   *Failure looks like:* an empty coverage view on a document that visibly lists requirements.

7. **The refusal explains itself.** Adopt one already-adopted path by hand:

   ```bash
   curl -X POST http://127.0.0.1:8010/api/v1/projects/proj-5e960453/project/documents/adopt \
     -H "Authorization: Bearer $AW_KEY" -H "Content-Type: application/json" \
     -d '{"path":"spec/capabilities/agent-charter/spec.html"}'
   ```

   *Expect:* a 409 whose message says the document is already tracked and that adoption does not
   update an existing record from its file, plus a `differences` list.
   *Failure looks like:* a bare "conflict" with nothing to act on, or — worse — a 200.

8. **A hand-written file is refused, not mangled.** Put any HTML file with no payload block under
   `spec/`, adopt that path, then check it with `git status`.
   *Expect:* a 422 naming the missing payload, and the file untouched.
   *Failure looks like:* a row created for it, or the file rewritten. Delete the test file
   afterwards.
