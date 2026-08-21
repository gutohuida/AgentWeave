## 1. Vocabulary — kinds and phases

- [x] 1.1 Add tests in `hub/tests/` asserting a `capability` entry is accepted by `load_manifest`, that a `capability` paired with any phase other than `current` is refused, that a `change-spec` at `archived` is accepted, and that a status outside the phase vocabulary is refused with an `invalid` index whose documents are still listed
- [x] 1.2 Add `capability` to `VALID_KINDS` in `hub/hub/spec_manifest.py`
- [x] 1.3 Replace `_expected_status` and the `living`/`draft`/`approved` model with validation against the phase vocabulary `{exploring, proposed, approved, archived, current}`, deriving the permitted set from the lifecycle constants rather than restating the strings
- [x] 1.4 Add the kind/phase pairing rule: `capability` → `{current}`, all other kinds → `{exploring, proposed, approved, archived}`
- [x] 1.5 Mirror 1.2–1.4 into `src/agentweave/spec_manifest.py`, keeping the two twins textually parallel and importing nothing between them
- [x] 1.6 Add the twin-agreement test asserting both modules expose identical kind and phase sets
- [x] 1.7 Confirm 1.1 and 1.6 pass and that no previously passing manifest test regressed

## 2. Serialisation — `dump_manifest`

- [x] 2.1 Add a round-trip test: `load_manifest(dump_manifest(m))` returns a manifest equal to `m`, covering every kind and every legal kind/phase pair
- [x] 2.2 Add a test that `dump_manifest` output is byte-stable — dumping the same manifest twice produces identical text, with deterministic key and document order
- [x] 2.3 Implement `dump_manifest(manifest) -> str` in `hub/hub/spec_manifest.py`, pure and filesystem-free, emitting `version`, `home` and `documents`
- [x] 2.4 Mirror `dump_manifest` into `src/agentweave/spec_manifest.py`
- [x] 2.5 Confirm 2.1 and 2.2 pass against both twins

## 3. Writing the file — `write_index`

- [x] 3.1 Add tests: writing an index for a project makes `compute_state` report every discovered document as `filed` rather than `unindexed`, and the index state as `valid`
- [x] 3.2 Add tests for arrangement preservation — a recorded `home`, `parent` and `order` all survive a rebuild unchanged
- [x] 3.3 Add tests for the derived cases — order is a stable path sort and identical across two rebuilds; `parent` is null; an ambiguous `home` is left unset and still reports `home_ambiguous`; a recorded `home` naming a missing document is not replaced and still reports `home_missing`
- [x] 3.4 Implement `write_index(workspace, manifest)` in `hub/hub/spec_documents.py`, resolving through `ProjectWorkspace.resolve_relative` like every other path in the module
- [x] 3.5 Implement the manifest builder: read the existing index, carry forward `home`/`parent`/`order` for documents still on disk, derive what is missing per the design, and take `path`/`title`/`kind`/`status` from the project's `SpecDocument` rows
- [x] 3.6 Confirm 3.1–3.3 pass

## 4. The operator route

- [x] 4.1 Add a route test: `POST /spec/reindex` writes `spec/index.json`, and a subsequent document listing reports documents as `filed`
- [x] 4.2 Add a test that no agent-facing surface can write the index — the MCP tool surface exposes no such tool, and the route rejects a non-operator credential
- [x] 4.3 Wire the manifest write into `reindex` in `hub/hub/api/v1/spec.py`, after the requirement-index rebuild and inside the existing commit
- [x] 4.4 Extend the route's response to report what was written — the index path and the document count — without changing the existing `documents`/`references` keys
- [x] 4.5 Confirm 4.1 and 4.2 pass

## 5. Verification against this repository

- [x] 5.1 Run the full `hub/tests/` suite and confirm no regression against the pre-change baseline
- [x] 5.2 Run `py -3.11 -m ruff check` and `py -3.11 -m black --check` on every changed Python file
- [x] 5.3 Against a Hub serving this repo, rebuild the index for `spec/` and confirm all three real documents — two `capability`/`current`, one `change-spec`/`archived` — report `filed` with zero `intrinsic_metadata_conflict` diagnostics
- [x] 5.4 Confirm the written `spec/index.json` parses via the CLI twin as well as the Hub's, proving the round trip crosses the module boundary
- [x] 5.5 Perform one mutation check: revert a single validation rule, watch a named test fail, restore it
- [x] 5.6 Record in `openspec/explorations/2026-08-20-dogfooding-findings.md` any friction this change surfaced that is not already an entry
