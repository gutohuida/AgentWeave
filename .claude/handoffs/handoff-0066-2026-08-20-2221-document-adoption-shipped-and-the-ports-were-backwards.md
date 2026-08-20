# Handoff: document-adoption implemented and rehearsed, and the port prohibition was backwards

**Date:** 2026-08-20T22:21:03+01:00 · **Branch:** `master` · **HEAD:** `824d843`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive)
**Previous handoff:** `.claude/handoffs/handoff-0065-2026-08-20-1923-three-proposals-and-the-loop-deadlock.md`
**Status:** chunk complete. Working tree clean. **9 commits unpushed** — 5 mine, 4 from a
concurrent session (see "A second session is working in this tree").

## Goal

Implement `openspec/changes/document-adoption` — the first of the four proposals handoff 0065 left
proposed-but-unbuilt. The operator chose it from a readiness survey of all four.

The *why*: a specification document is a file plus a database row. The file is committed and
travels between machines; the row is machine-local and does not. Every capability except the read
path is keyed on the row, so a `spec/` tree that arrives from a clone, a copy, or that predates the
database is **readable and completely inert** — no phase, no requirements, no coverage, no tasks.
There was no way to mint a row for a file that already existed: `POST /documents` mints a row and
then renders a blank starter file over the path, so pointing it at a real document destroys it.
This repo's own corpus is the live case — 34 capability documents plus `spec/agentweave.html`, all
35 carrying a complete payload block, not one with a row.

## Current state

### `document-adoption` is complete — 38/38 tasks, `openspec list` reports ✓ Complete

Two new operator API routes, no UI, no migration, no model column:

| Route | What it does |
|---|---|
| `POST /api/v1/projects/{id}/project/documents/adopt` | body `{path}` — mints a row for one existing file |
| `POST /api/v1/projects/{id}/project/spec/adopt` | no body — sweeps the whole `spec/` tree |

Both take title and kind from the file's `aw-spec-payload` block, phase from its `aw-spec-status`
meta tag, and **never write to disk**. New module `hub/hub/spec_adoption.py` imports no writer at
all, which is how the read-only guarantee is structural rather than reviewed — there is a test
asserting the module's source contains no writer call.

`spec_lifecycle.create_document` gained an optional `phase` parameter. It is the only way an
adopted document can land at the phase its file records: `transition()` cannot reach `approved`
from a fresh row without walking it through `proposed` and approving it, which would invent a
history in order to record one that really happened on another machine.

### Two defects were found by implementing and by driving it, not by the spec

**D3a — a phase can be real and still be one the document cannot hold.** The database enforces
`capability ⟺ current` in a cross-column check (`ck_spec_documents_kind_phase`, added by migration
`0074`). So a `system-map` file reading `current`, or a `capability` reading `approved`, describes
a row SQLite refuses outright. Design D3 had not covered it. Adoption now treats such a phase
exactly as it treats an unrecognised one — default by kind, report what the file said — rather than
stranding a corpus over a metadata value the operator can neither see in the app nor easily repair.
Recorded as **D3a** in `design.md` with a new scenario in the spec delta.

**The `compare` bug, found by driving task 8.6 against a real document.** D3a's own fallback then
*hid* a real disagreement: `compare` was reading the phase adoption had already resolved, so a
`capability` hand-edited to `exploring` resolved back to `current`, matched the row, and the refusal
reported that file and row agreed — about a file that visibly said otherwise. `compare` now reports
the phase **as the file declared it** (`unrecognised_phase or phase`). This is the one that
justifies having driven group 8 at all: no unit test anyone would think to write produces a file
stating a phase its own kind forbids, yet that is exactly what a hand edit or a bad merge produces,
which is when the operator most relies on the report.

### Group 8 (human-only) was rehearsed rather than deferred

At the operator's instruction — *"Any test that you can do with playwright do it."* Driven against
a **throwaway Hub on port 8021**, a fresh database, and a byte-identical **copy** of this repo's
`spec/` tree registered as `proj-f8de11d8`.

| Check | Result |
|---|---|
| 8.1 corpus adopts | 35 adopted, 0 skipped, 0 diagnostics; `{capability: 34, system-map: 1}`; `{current: 34, exploring: 1}`; all 35 `phase_source: read`; **452 requirements indexed** |
| 8.2 nothing destroyed | sha256 of all 36 files identical before/after; copy still `diff -r`-equal to `<repo>/spec` |
| 8.3 phase bar | 9 Playwright tests, all pass |
| 8.4 `unfiled` gone | 33 filed / 2 unfiled → 35 filed, 0 diagnostics, real titles |
| 8.5 requirements | coverage reports 7 for `agent-charter`; `FR-` identifiers render in the iframe |
| 8.6 refusal | reports both differing fields with both values — after the fix above |

The 9 browser tests were verified to **all fail against an identical un-adopted project**
(`proj-2795a7b6`), which is what makes them evidence: every one of these documents renders the same
on disk with or without a row, so a test that passed either way would be measuring the app, not the
change.

### The operator corrected the port model — this is the most important thing in this handoff

> *"8010 is a test environment. 8000 is real usage."*

**The handoff chain has been carrying "Never touch the Hub on port 8010" as a standing prohibition,
and it is wrong.** It was repeated verbatim through several handoffs, including 0065. CLAUDE.md
never said it — CLAUDE.md's actual rule is narrower: never point the Hub *whose code you are
editing* at this repo, because a code change restarts the process and kills runs in flight.

The cost was real: this session stood up an entire throwaway Hub on port 8021 with a copied corpus
purely to avoid touching 8010, when **8010 was the correct place to test all along.** Saved as a
memory (`project_hub_ports_test_vs_real.md`). Do not carry the old prohibition forward.

### Machine state — three Hubs are running

| Port | What it is | State |
|---|---|---|
| **8000** | **The operator's real usage. Leave alone.** | running, untouched this session |
| **8010** | The **test** Hub, this repo as `proj-5e960453`. Safe to drive, including restarting it. | running, untouched this session, and **running pre-change code — its route list has no `adopt` in it** |
| **8021** | Throwaway rehearsal Hub started by this session — `py -3.11 -m uvicorn hub.main:app`, DB `%TEMP%\aw-adopt-check\adopt.db` | **still running.** Kill it when done; it serves nothing of value beyond the demo below |

The rehearsal projects on 8021, for clicking through:
`http://127.0.0.1:8021/?project=proj-f8de11d8&tab=spec` (adopted) versus
`http://127.0.0.1:8021/?project=proj-2795a7b6&tab=spec` (identical corpus, not adopted).
Key `aw_live_adoptioncheck0000000000000000`. Both workspaces are under
`%TEMP%\aw-adopt-check` and `%TEMP%\aw-adopt-control`; screenshots `adopted.png` and
`not-adopted.png` are in the former.

**Handoff 0065's claim that this repo is not registered as a project is wrong.**
`.agentweave/project.json` at the repo root holds `proj-5e960453`, matching CLAUDE.md. There is
also a `project.json.trial-8010-backup` beside it.

## Files touched

`git status --short` is empty and `git diff --stat HEAD` is empty — everything is committed.

**`54ca5b5` — Read a document's adoptable identity from its own file** (4 files, +501/-4)

- `hub/hub/spec_adoption.py` — **new, 256 lines.** `read_identity`, `identity_from_content`,
  `default_phase_for`, `AdoptableIdentity`, `AdoptionRefusal`, `FieldDifference`. Finished.
- `hub/hub/spec_payload.py` — added `has_payload_block()`. `extract_payload` returns `None` both
  for a missing block and an unparseable one, and the operator's remedy differs; this tells them
  apart without giving the block a second interpretation. `extract_payload` itself untouched.
- `hub/tests/test_spec_adoption_identity.py` — **new.** Finished.
- `openspec/changes/document-adoption/tasks.md` — group 1 ticked.

**`5130d7f` — Adopt one document, and report what the file and the row disagree on** (5 files, +548/-11)

- `hub/hub/api/v1/spec.py` — added `DocumentAdopt` schema, `_ADOPTION_REFUSAL_STATUS`, and
  `POST /documents/adopt`. Purely additive.
- `hub/hub/spec_adoption.py` — added `adopt()`, `AdoptionResult`, `compare()`.
- `hub/hub/spec_lifecycle.py` — `create_document` gained optional `phase`.
- `hub/tests/test_spec_adoption_api.py` — **new.** Finished.
- `openspec/changes/document-adoption/tasks.md` — groups 2 and 3 ticked.

**`0dcc1a2` — Adopt a whole corpus, and prove adoption never writes** (9 files, +737/-32)

- `hub/hub/spec_adoption.py` — added `adopt_corpus()`, `CorpusAdoption`, `phase_is_holdable()`.
- `hub/hub/api/v1/spec.py` — added `POST /spec/adopt`.
- `hub/hub/spec_lifecycle.py` — `create_document` now refuses an unholdable kind/phase pair with
  `phase_not_holdable` rather than letting it surface as an `IntegrityError` from the flush.
- `hub/tests/test_spec_adoption_corpus.py` — **new.** Corpus sweep + the byte-identity suite.
- `hub/tests/test_spec_adoption_downstream.py` — **new.** Group 6.
- `hub/tests/test_spec_adoption_identity.py` — added the D3a cases.
- `openspec/changes/document-adoption/design.md` — added **D3a**.
- `openspec/changes/document-adoption/specs/spec-document-adoption/spec.md` — amended the phase
  requirement, added a scenario.
- `openspec/changes/document-adoption/tasks.md` — groups 4–7 ticked.

**`85f70ba` — Write the operator test guide** (1 file, +71/-1)

- `openspec/changes/document-adoption/tasks.md` — §9, inline, matching the convention the archived
  changes use (the guide lives in `tasks.md`, not a separate file).

**`f07c2db` — Report a disagreement the file states but adoption resolves away** (6 files, +247/-13)

- `hub/hub/spec_adoption.py` — the `compare` fix.
- `hub/tests/browser/test_adopted_corpus.py` — **new, 145 lines, 9 Playwright tests.** Finished.
- `hub/tests/test_spec_adoption_api.py` — 2 new tests for the fix.
- `hub/tests/test_spec_adoption_corpus.py`, `test_spec_adoption_downstream.py` — corrected both
  fixtures, which gave the `system-map` home `current`, a combination no real corpus can contain.
- `openspec/changes/document-adoption/tasks.md` — group 8 recorded.

**Not in git — memory:**
`~/.claude/projects/C--Users-huida-Documents-projects-AgentWeave/memory/project_hub_ports_test_vs_real.md`
plus a line in that directory's `MEMORY.md`.

## Key decisions

1. **A separate adoption route, not a flag on `POST /documents`** (design D1, pre-existing).
   Confirmed in implementation: creation renders a starter file over its path, so a flag would
   leave the destructive behaviour one missing parameter away.
2. **`create_document` gains `phase` rather than adoption setting `document.phase` directly.**
   `spec_lifecycle`'s whole purpose is that phase is owned there; assigning the column from another
   module would put phase-setting outside the module that exists to own it. *Rejected:* post-create
   assignment.
3. **A phase the kind cannot hold is defaulted and reported, never refused** (D3a). *Rejected:*
   refusing the document (strands a corpus over an invisible metadata value) and relaxing the
   database constraint (load-bearing, predates this change).
4. **`compare` reports the phase as the file declared it, not as adoption resolved it.** *Rejected:*
   comparing resolved values, which is what produced the bug.
5. **Rehearsed group 8 on a copy rather than the real corpus.** The reasoning was sound — the first
   run of a route that *could* overwrite a corpus should not be against the corpus — but the
   *port* choice underneath it was based on the wrong prohibition (see the ports section). A future
   rehearsal can use 8010 directly.
6. **A whole-tree byte snapshot, not per-file checks.** A route that wrote a new file, deleted one,
   or moved one would pass a check that only compared the documents it was handed.
7. **Mutation-checked in two passes.** A write on the success path fails the single-document and
   whole-tree assertions but leaves the refusal tests green; it took a second mutation on the
   refusal path to prove those bite. One pass would have shipped three tests that proved nothing.

## Constraints and user directives (verbatim)

From this session:

- *"8010 is a test environment. 8000 is real usage."*
- *"Any test that you can do with playwright do it. Just leave the tests that I need to do and
  guide me with what I need to test"*
- *"What specs can we implement right now?"* — answered with a readiness survey; the operator then
  chose `document-adoption`.
- Chosen via AskUserQuestion: **"document-adoption (Recommended)"**, and **"Neither — leave both
  open"** on the two standing questions (register this repo / delete `proj-adf8a200`).

Standing, carried forward and **still in force**:

- Never `git add -A`; stage paths explicitly. (Load-bearing this session — it is the only reason
  the concurrent session's work never got swept into mine.)
- Never mark a task complete on the strength of a plan existing.
- `hub/hub/static/ui` is a committed build artefact — after `cd hub/ui && npm run build`, run
  `python scripts/refresh_ui_bundle.py` (`make` is not on PATH in Git Bash here).
- Keep the two `spec_manifest.py` twins (`hub/hub/` and `src/agentweave/`) in sync by hand.
- `hub/hub/mcp_server.py` may import **only** stdlib + fastmcp.
- `approve_tool_call` has **no return annotation** — do not add one.
- From memory: commit each completed checkpoint without asking first; specs must carry test guides
  split into agent-verifiable and human-only.

**Superseded:** *"Never touch the Hub on port 8010"* from handoffs 0064 and 0065. Wrong — 8010 is
the test environment. See above.

## Dead ends

- **`git checkout <file>` to undo a scratch mutation reverted an hour of uncommitted work.** I used
  it to remove a deliberately-introduced mutation and it restored the file to the last commit,
  destroying the group-4 additions (`adopt_corpus`, `CorpusAdoption`, `phase_is_holdable`) which
  were not yet committed. Rewritten from context. **Copy the file to `/tmp` first and restore from
  the copy** — that is what the second and third mutation passes did.
- **A heredoc-based Python one-liner that inserts a line containing `\n` mangles it.** Two attempts
  produced `SyntaxError: unterminated string literal` in `spec_adoption.py`, which then broke
  conftest import and made every test in the package error. Write the mutation to a file, or use a
  payload with no escapes.
- **Playwright's Python `get_by_role(name=...)` does not accept a callable.** It raises
  `AttributeError: 'function' object has no attribute 'replace'`. Use `re.compile(...)`.
- **`page.get_by_text` does not reach the rendered spec document** — the document body renders
  inside an `iframe`. Use `page.frame_locator("iframe").first`. A test that forgets this reports
  requirements missing when they are one frame down.
- **A payload fixture without an `aw_identity` map indexes zero requirements.** Not a bug —
  `requirements_from_payload` deliberately skips a requirement with no minted identifier, because
  indexing under an invented handle is how a link comes to point at the wrong requirement. A
  fixture omitting it proves requirement indexing works when it was simply skipped.
- **`ProjectWorkspace` takes `path_key`, not `mode`.** `ProjectWorkspace(project_id=..., root=...,
  path_key=...)`.
- **Deleting a registered project's directory breaks it permanently until the marker is restored** —
  `.agentweave/project.json` must be recreated with the same `project_id`, or every route returns
  `project_marker_invalid`.

## Verification

**Ran, and passed:**

- `py -3.11 -m pytest hub/tests/ -q --ignore=hub/tests/browser` → **2580 passed, 12 skipped,
  1 xpassed, 0 failed** (844s). Baseline before this session was 2508 (handoff 0064).
- `py -3.11 -m ruff check hub/` → clean. `black --check --target-version py311 hub/hub hub/tests` →
  382 files unchanged.
- `AW_HUB_URL=http://127.0.0.1:8021 AW_HUB_API_KEY=... AW_HUB_PROJECT_ID=proj-f8de11d8 py -3.11 -m
  pytest tests/browser/test_adopted_corpus.py` (from `hub/`) → **9 passed**.
- The same 9 against `AW_HUB_PROJECT_ID=proj-2795a7b6` (identical corpus, not adopted) → **9
  failed**, which is the point.
- Corpus adoption over a copy of this repo's real `spec/`: 35 adopted, 0 skipped, 0 diagnostics,
  452 requirements, and sha256 of all 36 files identical before and after.
- Mutation check, two passes, described under Key decisions 7.
- `openspec validate document-adoption` → valid. `openspec list` → ✓ Complete.
- No migration added, no model column changed, `git status` on `hub/hub/migrations/` and
  `db/models.py` empty, neither `spec_manifest.py` twin touched, and the diff on
  `hub/hub/api/v1/spec.py` **removes zero lines**, so `POST /documents` is byte-for-byte unchanged.

**NOT tested — do not claim otherwise:**

- **Adoption has never run against a real registered project.** Everything above is a copy in
  `%TEMP%`. The repo's own corpus is still untracked, and the Hub on 8010 does not have the code.
- **No UI exists for adoption and none was tested**, because none was built.
- **The three taste judgements in group 8 are open** and are explicitly the operator's.
- **CI has not been checked** for any of the 9 unpushed commits.
- **The concurrent session's loop work is unverified by me.** I did not read `scheduler.py`'s
  changes beyond the first 40 lines of the diff, did not review their tests, and their commits are
  included in the 2580-passing figure only incidentally.
- `py -3.11 -m pytest tests/` (the CLI suite) was **not** run. The change touches only `hub/`.

## Git state

- **Branch:** `master`. **HEAD:** `824d843`. **Working tree clean.**
- **9 commits unpushed.** Mine: `54ca5b5`, `5130d7f`, `0dcc1a2`, `85f70ba`, `f07c2db`. The
  concurrent session's: `7d4ff6e`, `a0f7ef4`, `9d9b20e`, `824d843`. (`71ca8b0`, also theirs, was
  already pushed.)
- I deliberately did not push, because more than half the unpushed commits are not mine to push.

## A second session is working in this tree

Commits from another Claude session interleave with mine throughout the log. They picked up handoff
0065's **next-step 1** and closed it:

- `71ca8b0` Reproduce the loop spin, and record it as verified — **the §3 spin was live.**
- `7d4ff6e` Skip a stalled loop firing instead of spawning an agent to do nothing
- `a0f7ef4` Record L0 as done, and what the fix left open
- `9d9b20e` Explore who guarantees the review handoff, and resolve the fork
- `824d843` Let the loop claim a task a reviewer sent back

They touch `hub/hub/scheduler.py`, `hub/tests/test_scheduler.py`, and
`openspec/explorations/2026-08-20-the-loop-under-dependencies.md`. **No file overlaps with mine.**
Staging explicit paths is the only reason that stayed true — a single `git add -A` would have
mixed the two.

## Next steps

1. **Restart the Hub on 8010 so it has the adoption code, then run the sweep for real.** It is the
   test environment and this is what it is for. Stop the process on 8010, restart it per CLAUDE.md
   (`cd hub && DATABASE_URL="sqlite+aiosqlite:///$(pwd)/data/agentweave.db" agentweave --port 8010`
   — **from `hub/`, never the repo root**, or the child dies on an import shadow 60 seconds later
   with its output already sent to `DEVNULL`), then follow §9 of
   `openspec/changes/document-adoption/tasks.md` against `proj-5e960453`. §9 step 1 is the one that
   matters: run the sweep, then `git status --short spec/`, and **the correct output is no output
   at all.** Confirm the route exists first: `curl -s http://127.0.0.1:8010/openapi.json | grep
   adopt`.
2. **Kill the rehearsal Hub on 8021** once its demo is no longer wanted, and remove
   `%TEMP%\aw-adopt-check` and `%TEMP%\aw-adopt-control`.
3. **Decide whether to push**, and whether the concurrent session's 4 commits go up with mine.
4. **Or start `agent-created-documents`** — 35 tasks, the smallest of the three remaining
   proposals, fully unblocked, all three of its open questions carry recommendations.
   `/openspec-apply-change agent-created-documents`.
5. **Or archive `document-adoption`** now that it reports ✓ Complete — but not before step 1, since
   its §8 records a rehearsal rather than a real run. `writable-spec-index` and
   `operator-authored-documents` are also still complete-and-unarchived, open since handoff 0065.

## Open questions for the user

- **Should adoption have a UI?** Right now the only operator path is curl. For the "I just cloned
  this repo" case that is arguably the wrong shape. I offered to record it as a finding against the
  change and the operator moved to the handoff without answering, so it is unrecorded.
- **The three taste judgements** in group 8: does the populated phase bar inform or clutter; is
  "7 no work linked" useful at a glance; is *"adoption does not update an existing record from its
  file"* the right thing to say to someone who expected it to update.
- **Push the 9 commits?** Including the other session's 4.
- **Retire `openspec/specs/`?** Open since handoff 0062.
- **Delete `proj-adf8a200`** (the operator's home directory registered as a project on 8000)? Open
  since handoff 0063; the operator said "leave open" this session.
- **Adoption's own three open questions**, all deferred by design and unanswered: re-adoption /
  refresh-from-file; whether adoption should set `rigor`; whether corpus adoption should run
  reindex itself.

## Read on resume

- `openspec/changes/document-adoption/tasks.md` — **first.** §8 is what was rehearsed and what
  remains; §9 is the operator procedure for next-step 1.
- `hub/hub/spec_adoption.py` — the whole change in one file, 463 lines, heavily commented with the
  reasoning behind D3a and the `compare` fix.
- `openspec/changes/document-adoption/design.md` — D1–D7 plus **D3a**, and the three open questions.
- `hub/tests/browser/test_adopted_corpus.py` — the Playwright harness and, in its docstring, exactly
  how to run it against a live Hub.
- `openspec/explorations/2026-08-20-the-loop-under-dependencies.md` — the other session revised it;
  §10's L0–L5 table is where their work and the `task-dependencies` proposal meet.
- `CLAUDE.md` — the trial-Hub section, read alongside the ports correction above, since the two
  have to be reconciled.
