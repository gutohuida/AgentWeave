# Handoff: the openspec corpus now lives in AgentWeave, and two blockers had to fall first

**Date:** 2026-08-20T11:17:36+01:00 · **Branch:** `loop/2026-08-20-spec-corpus-migration` · **HEAD:** `bb663e1`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive + a self-paced `/loop`)
**Previous handoff:** `.claude/handoffs/handoff-0061-2026-08-20-0845-project-portability-shipped-and-identity-restored.md`
**Status:** chunk complete. Both openspec changes done and verified; the corpus is migrated and live
in the operator's Hub. 9 commits ahead of `origin/master`, **nothing pushed**, no PR opened.

## Goal

The operator asked to move their development into AgentWeave: *"read the entire project and the
openspec and create a full agentweave spec for agentweave... the idea is to take my dev into
agentweave so I can start."* They then chose **"Fix the index first, then migrate"** and **"All 33,
faithfully"**, and asked for the work to run as a `/loop` for the day with a running notes file of
frictions.

The *why* matters for later judgement calls: this is the dogfooding migration CLAUDE.md describes.
Friction encountered while using the spec flow is a **deliverable**, not an obstacle — "when it
frustrates you, that is a finding."

## Current state

**The corpus is migrated, committed, and live in `proj-5e960453` on the port-8000 Hub.**

- **33 documents `filed`** — 32 migrated openspec capabilities plus one authored system map at
  `spec/agentweave.html`, which is the corpus `home`.
- **442 requirements** in the Hub's requirement index, identifiers minted by the Hub.
- `spec/index.json` written, `manifest: valid`, orders unique 10–330, **zero index diagnostics**.
- **4 documents `unfiled`** — see "the adoption gap" below. Their content is untouched.

**Both openspec changes are complete, validated (`npx openspec validate --changes --strict`), and
have every task checked.** Neither is archived yet.

1. `openspec/changes/writable-spec-index/` — `spec/index.json` could not be written at all.
   Nothing in the product wrote it, and the manifest's vocabulary could not describe the Hub's own
   output (`VALID_KINDS` lacked `capability`; `spec_render.py:386` writes the lifecycle *phase* into
   `aw-spec-status` while the manifest expected a kind-derived `living`/`draft`/`approved`).
2. `openspec/changes/operator-authored-documents/` — `PUT /documents/{path}/content`. **An agent
   cannot write a capability document at all** (`spec_service.py:128`), and no route reached the
   operator branch the service already had. `spec-document-authority:1046` already required *"the
   same submission from the operator succeeds"*; it was satisfiable only in-process.

**The adoption gap (finding 17, the most significant of the day, NOT fixed).** `POST /documents`
builds a placeholder payload and passes it to `save_document`, which **renders it over the file**
(`hub/hub/api/v1/spec.py:1141-1153`). So a document that exists on disk with no database row has
exactly two possible fates: stay `unfiled` forever, or be destroyed to be filed. Files travel; no
Hub can adopt them. This is the mirror image of the project-adoption fix shipped 2026-08-19.

**Live operator activity, discovered while writing this handoff.** The operator created a new
exploration through the app: `spec/changes/project-usage-by-provider-agent-and-model-on-the-control-page-and-subagent-visibility/spec.html`
(`change-spec`, `exploring`, 16.6 KB, so an agent filled it in). It is **untracked in git** and reads
`unfiled` only because the index was written before it existed — the Hub *does* hold its row, so a
plain reindex will file it. Deliberately not touched.

**Machine state:**

- **The port-8000 Hub was restarted** at ~10:30 with the operator's explicit approval, using
  `C:\Users\huida\.agentweave\hub\start-hub-8000.bat`. It now runs today's code. Zero runs were in
  flight; the three agents (Architect, Developer, Tester) were idle and are untouched.
- **A throwaway Hub is running on port 8020** — database `testbed/corpus-import-hub/data/hub.db`,
  project `proj-e9ea6a91` at `testbed/corpus-import/`, bootstrap key
  `aw_live_corpusimport0000000000000000`. It holds a full 34-document dry run. Kill it when done;
  `testbed/corpus-import*` are throwaway.
- **The port-8010 Hub was never touched**, per the standing prohibition.

## Files touched

Everything below is committed except where noted. `git status` shows exactly one untracked path
(the operator's new exploration, above).

**Hub product source:**

- `hub/hub/spec_manifest.py` — `VALID_KINDS` gains `capability`; phase vocabulary and
  `permitted_phases()` replace `_expected_status`; new `dump_manifest()` and `build_manifest()`;
  new `manifest_duplicate_order` validation. **Finished.**
- `src/agentweave/spec_manifest.py` — the CLI twin, mirrored by hand (no import relationship).
  **Finished.**
- `hub/hub/spec_documents.py` — new `build_index()` and `write_index()`. **Finished.**
- `hub/hub/api/v1/spec.py` — `PUT /documents/{path}/content` (operator authoring); `reindex` now
  writes the manifest and accepts an optional `home`; new `DocumentContent` and `ReindexRequest`
  models; `Any` added to the typing import. **Finished.**
- `hub/hub/spec_service.py` — docstring and refusal message corrected (they said "through a merge";
  the check forbids only non-operators). **Finished.**
- `hub/hub/spec_lifecycle.py` — same correction in `create_document`'s docstring. **Finished.**

**Tests (all passing):**

- `hub/tests/test_spec_index_writer.py` — **new**, 20 tests.
- `hub/tests/test_spec_manifest_roundtrip.py` — **new**, 18 tests, incl. twin agreement and a
  tripwire asserting no transition leaves `current`.
- `hub/tests/test_operator_authored_documents.py` — **new**, 16 tests.
- `hub/tests/test_spec_manifest.py`, `hub/tests/test_spec.py`, `tests/test_spec_manifest.py` —
  updated off the retired `living`/`draft` statuses.

**Tooling and config:**

- `scripts/migrate_openspec_corpus.py` — **new**, 414 lines. The converter.
- `openspec/config.yaml` — two live bugs fixed: rules were keyed `spec:` where the schema expects
  `specs:` (so "every requirement must be falsifiable" had **never** applied), and the injected
  context still forbade `spec/` and `.agentweave/`, contradicting the 2026-08-16 migration.
- `.gitignore` — added `.migration/`.

**Artefacts:**

- `openspec/changes/writable-spec-index/` and `openspec/changes/operator-authored-documents/` —
  proposal, design, specs delta, tasks. Both complete.
- `openspec/explorations/2026-08-20-dogfooding-findings.md` — **17 findings**, 445 lines.
- `spec/` — 33 new files (32 capabilities + `spec/agentweave.html`) + `spec/index.json`.
  **18,034 insertions.**

## Key decisions

1. **Fix the index before migrating.** *Rejected:* migrating anyway. *Reason:* all 33 documents
   would have landed `unindexed` with no home, titles, hierarchy or ordering.
2. **Manifest `status` becomes the lifecycle phase.** *Rejected:* translating between the two
   vocabularies. *Reason:* no total mapping exists — `current` and `exploring` have no kind-derived
   counterpart and `living` has no phase, so translation would have to invent values.
3. **Build the operator content route rather than spend agent runs.** *Rejected:* 33 agent runs.
   *Reason:* it is **impossible**, not merely expensive — `spec_service.py:128` refuses a capability
   write from any non-operator actor.
4. **`given: ""` for the 1,270 scenarios (97.6%) that state no GIVEN.** *Rejected:* authoring a
   starting state for each. *Reason:* 1,270 pieces of prose in no source that nobody would review,
   inside documents whose purpose is to state current behaviour accurately. The schema accepts `""`.
5. **Skipped `project-instructions` in the import.** *Reason:* a hand-translated document already
   existed there with **authored** GIVEN clauses; importing would replace better work with worse.
6. **Did not create rows for the pre-existing documents.** *Reason:* `POST /documents` renders a
   placeholder over the file. Filing them would destroy them. Left `unfiled` and recorded.
7. **Home is the authored system map**, not an arbitrary capability. *Reason:* `_select_home`
   refuses to guess, correctly — but that left a multi-document corpus unwritable, so `reindex`
   gained an optional `home` the operator supplies.
8. **Dropped "SSE, never polling" from the system map.** *Reason:* not true —
   `hub/ui/src/api/permissions.ts:52`, `questions.ts:51`, `unaskedQuestions.ts:42` set
   `refetchInterval`. Recorded as a limit rather than asserted.

## Constraints and user directives (verbatim)

- *"I still want to do this but let's do it inside a loop for todays work."*
- *"Also while migrating take notes on what we can improve, what we're lacking and what would be
  nice to implement in the agentweave spec."*
- *"stops at 17"* — the loop ends at 17:00.
- *"Just delete it"* — re: the Default Project row and its three agents (done; see Verification).
- Chosen via AskUserQuestion: **"Fix the index first, then migrate"**, **"All 33, faithfully"**,
  **"Restart your 8000 Hub and import there"**, **"Keep both for now, decide later"** (re:
  `openspec/specs/`).
- Standing, from `CLAUDE.md`: **do not restart, stop, or reconfigure the Hub on port 8010**; do not
  touch `hub/data/agentweave.db`; never mark a task complete on the strength of a plan existing;
  stage paths explicitly; keep the two `spec_manifest` twins in sync by hand.
- Standing, from memory: commit each completed checkpoint without asking first.

## Dead ends

- **`openspec new change "2026-08-20-writable-spec-index"`** → `Change name must start with a
  letter`, despite every archived change being date-prefixed. Both changes are therefore named
  without a date prefix.
- **Bash heredocs containing apostrophes** (`operator's`) broke with `unexpected EOF while looking
  for matching '`. Use the `Write` tool for JSON/prose files instead.
- **`ProjectWorkspace(root=...)`** — needs `project_id`, `root`, `path_key`, in that order.
- **`GET .../project/documents?path=...`** does not return one document's requirements; it lists
  documents. Read the payload out of the rendered HTML's `<script id="aw-spec-payload">` instead.
- **`POST /documents/phase`** takes `path` and `to` as **query params** plus a JSON body
  (`{"reason": ...}`). And it cannot reach `approved` directly — the real sequence is
  `close-exploration` → `propose` → `phase?to=approved`.
- **`POST /documents/propose` answers `200` with a `blocking` array when it refuses.** The status
  code proves nothing. Completeness needs every requirement covered by *both* an acceptance
  criterion and a task.
- **`py -3.11 -m black`** warns and refuses without `--target-version py311` on this machine.

## Verification

**Ran, and passed:**

- `py -3.11 -m pytest hub/tests/ -q --ignore=tests/browser` → **2537 passed, 12 skipped, 1 xpassed,
  0 failures** (13m49s). Baseline in handoff 0061 was 2474; after change 1 it was 2521.
- `py -3.11 -m pytest tests/ -q` (CLI) → **404 passed, 3 skipped**.
- `py -3.11 -m ruff check` and `black --check --target-version py311` on every changed file — clean.
- `npx openspec validate --changes --strict` → **2 passed, 0 failed**.
- **Two mutation checks**, each by reverting and watching named tests fail, then restoring:
  removing `capability` from `VALID_KINDS` (2 tests fail); swapping the operator actor for an agent
  actor in the content route (2 tests fail).
- **Full dry run** on the 8020 throwaway Hub: 33 capabilities → 437 requirements, 1301 criteria;
  `unindexed`/`home_ambiguous` before reindex → **34/34 `filed`, manifest `valid`, zero
  diagnostics** after.
- **Fidelity spot-check** against source: `opencode-config` 4/4 and `project-instructions` 3/3
  statements carried **verbatim**; criteria counts equal scenario counts exactly.
- **Live on the 8000 Hub:** 33 filed / 4 unfiled, 442 requirements, `manifest: valid`, orders
  unique. Screenshot of the Spec tab confirms the system map renders as home with its 8 requirements
  and the drift banner reporting the unfiled documents.
- **`proj-default` deleted** from the 8000 Hub (204). It now lists only `AgentWeave`.
- The three pre-existing `spec/` documents are **byte-identical** — confirmed by `git status`
  showing no modification to them.

**NOT tested — do not claim otherwise:**

- **The browser suite has still not been run** (unchanged since handoff 0061). Its fixtures are
  additionally known to be decayed — the three `taste-pass` jobs it asserts on by name exist in
  neither database.
- **No UI regression testing.** The one screenshot confirms the Spec tab renders; nothing else in
  the UI was exercised, and no `vitest`/`tsc`/`eslint` run happened this session (no UI source was
  changed).
- **The migrated documents' prose was not read end-to-end.** Fidelity was verified by counts,
  verbatim spot-checks on 2 of 33, and schema validation on all 33 — not by reading 12,368 lines.
- **`spec/index.json` has never been round-tripped through a *different* machine**, which is the
  portability claim the whole first change rests on.
- **Nothing was pushed and no PR was opened.** CI has not seen any of this.

## Git state

- **Branch:** `loop/2026-08-20-spec-corpus-migration`, **9 commits** ahead of `origin/master`
  (`63ef94e`). No upstream set for this branch; nothing pushed.
- **HEAD:** `bb663e1`.
- **Uncommitted:** exactly one untracked path —
  `spec/changes/project-usage-by-provider-agent-and-model-on-the-control-page-and-subagent-visibility/`
  (the operator's live exploration; not mine to commit).
- `master` is unchanged and still at `63ef94e`.
- `.migration/` is gitignored (converter staging output; regenerate with `--out`).

## Next steps

1. **Reindex so the operator's new exploration is filed.** One call, non-destructive, preserves the
   existing arrangement and appends the new document at order 340:
   ```bash
   curl -s -X POST -H "Authorization: Bearer aw_live_71b0560849ca74d02b882593ad4d10b1" \
     -H "Content-Type: application/json" -d '{}' \
     "http://127.0.0.1:8000/api/v1/projects/proj-5e960453/project/spec/reindex"
   ```
   Then commit the resulting `spec/index.json` change together with that new document.
2. **Build document adoption (finding 17).** Given a file whose path has no row, read its rendered
   payload via `extract_payload` — it already carries `title`, `kind`, `schema_version` and the
   `aw_identity` block with previously minted identifiers — and create the row from it **without
   rewriting the file**. This is what lets the 4 unfiled documents join the index, and it completes
   the portability story. Needs its own openspec change.
3. **Push the branch and open a PR** so CI sees 9 commits and 18k insertions before any merge.
4. **Fix `summaryForEvent`** — no case for `project_adopted` or `agent_created`, so both render
   their own type twice and drop the payload (`hub/ui/src/lib/eventSummary.ts`, which already names
   this failure mode in a comment at lines 11-12).
5. **Correct stale facts in `CLAUDE.md`:** the trial-Hub table says this repo is registered on 8010
   (it is not — that database has no `proj-5e960453`), and it claims 21 `@mcp.tool()` when there are
   **22**.

## Open questions for the user

- **Retire `openspec/specs/`?** Deferred by explicit choice today ("keep both for now"). It now
  duplicates the same 33 capabilities, which is exactly the two-sources drift CLAUDE.md warns about.
- **Should `project-instructions` be re-imported?** Skipped to preserve its authored GIVEN clauses.
  It stays `unfiled` until document adoption exists.
- **`D-a13`** — should the Hub carry an agent's "please add this task" request with a one-click
  accept? Open since handoff 0060.
- **`D-naming`** — `openspec/explorations/2026-08-18-candidate-names.md` still unresolved.

## Read on resume

- `openspec/explorations/2026-08-20-dogfooding-findings.md` — **read this first.** 17 findings, the
  session's main deliverable besides the code. Finding 17 is the live one.
- `hub/hub/spec_documents.py` — `build_index`/`write_index`, and the ordering rule that a new
  document goes *after* an arranged corpus.
- `hub/hub/spec_service.py:91-155` — `save_document`'s refusal ladder; the capability/operator check
  at :128 is the centre of the second change.
- `scripts/migrate_openspec_corpus.py` — the converter, including which limits it records and why
  `given` is left empty.
- `openspec/changes/operator-authored-documents/design.md` — why the operator route is the missing
  half of an existing boundary rather than a new power.
- `spec/agentweave.html` — the authored system map; its `evidence.limits` states exactly which
  claims were checked and which were dropped.
