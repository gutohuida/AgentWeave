# Run log — 2026-08-16 night: the spec corpus, and loops as a first-class concept

Newest entry at the **bottom**. Written for someone who was asleep.

**Branch:** `autonomous/2026-08-16-spec-corpus-and-jobs`
**Parent:** `hub-native-experience` @ `b2b0cd5` — that is what this run is a diff against.
**Window:** 2026-08-16T21:35 → 2026-08-17T08:00 (+01:00)
**Driver:** Windows Scheduled Task `AgentWeaveAutonomousSession`, firing `claude -p` every 15
minutes. Each firing is a **fresh process** that reads `STATE.json`, does one iteration, commits,
pushes and exits. Nothing is held in memory between iterations — that is what makes it survive the
interactive session ending, which is what killed the 2026-08-15 attempt at forty minutes.

---

## Entry 0 — the limits, before any work

Recorded first so a later session inherits them even if this one dies mid-thought. Full text lives
in `STATE.json`'s `limits`; this is the short form.

1. **Stay on `autonomous/2026-08-16-spec-corpus-and-jobs`.** No commit, merge or rebase onto
   `hub-native-experience` or `master`. Merging back is the operator's decision, made awake.
2. **Nothing outward-facing.** No publish, release, PR, issue, force-push or history rewrite.
   Pushing *this* branch is required, not optional — it is what makes the work durable.
3. **Nothing destructive.** In particular: do not delete `hub/data/agentweave.db` (the preserved
   pre-migration original), and do not repoint the trial Hub's database.
4. **Install nothing new.** No new dependency in any language. The operator confirmed the spec cap
   but explicitly declined to authorise `pywebview` and declined to restate a general toolchain
   allowance. A package that seems necessary is a `decisions_for_user` entry, not a `pip install`.
5. **Never mark work complete because a plan exists.** Only verified implementation closes a task.
6. **Every claim measured or labelled unverified.** If it could not be run, the log says so.
7. **Decisions that are the operator's get written down, not guessed.**

### The one setting most likely to surprise a reader

`spec_round_protocol.at_cap` is **APPROVE AND EXECUTE**. Changed by the operator this session, in
these words: *"one more change after the 3 round spec cap approve and execute."* On the previous run
that gate shipped an artifact with its objections recorded and stopped, which is exactly why Q6
ended at 0/21. Tonight N2, N2b and N3 are expected to land as **working code**.

This delegates approval to the run for tonight, **in openspec only**. It does not touch the
product's own rule that only an operator may approve a spec document — that rule is code, in
`spec_lifecycle.transition`, and N2 must not weaken it while adding an operator-only archive act.

**N4 is the single exception**: spec only, no implementation, because implementing it needs
`pywebview` and no new dependency is authorised.

### Baseline — any red below is this run's own

Verified interactively at `b2b0cd5`, immediately before starting. Do not re-verify from scratch.

| Gate | Result |
|---|---|
| `pytest hub/tests/ -n 8` | 2068 passed, 11 skipped |
| `pytest tests/ -n 4` | 362 passed, 3 skipped |
| `npm test` | 921/921 |
| `npm run lint` | clean |
| `npx tsc --noEmit` | clean |
| `ruff check` | clean |
| `black --check` | 383 files clean |
| `openspec validate --changes --strict` | 17/17 |

Four of those were **red** at the start of the interactive session and were fixed before seeding:
the UI suite was flaky (a different `userEvent` test timed out on roughly every full run), UI lint
exited 1 on nine warnings, eight Python files had drifted out of `black` format, and Q6's own
`app-lifecycle` delta failed strict validation.

### Preparation already done — do not redo it

`/autonomous-prep` ran with the operator awake; eight `AskUserQuestion` rounds, and the resulting
plan was presented in full and explicitly approved before the run started. There is **no interview
left to do**. Every answer is in `STATE.json` under `limits`, `decisions_for_user` or
`spec_round_protocol`.

Four rulings are binding and must not be re-litigated:

- **Archiving is an operator act**, mirroring the existing rule that an agent cannot approve.
- **The corpus absorbs a finished change by explicit authored merge**, not automatic migration.
- **Capability documents sit outside the phase machine**, and carry a **dedicated phase value with
  no transitions** — not a permanent `approved`, because that row would lie about what it is.
- **The job system composes with AgentWeave's own primitives** and supports **many named loops** at
  different cadences, never a singleton.

One question is deliberately **open**: the task board at scale. The operator said *"Maybe make a
task board by spec? I don't know"* and meant it. N1 answers it with evidence; N2b acts on the
answer, or records why not.

### Two environment traps that cost the most if forgotten

- **Start the Hub from `hub/`, never the repository root.** `python -m uvicorn` puts the working
  directory on `sys.path[0]`, so this repo's own `hub/` directory shadows the installed `hub`
  package. The parent process survives, so migrations run and only the spawned server dies — 60
  seconds later, with its output already sent to `DEVNULL`.
- **`pytest` has no timeout plugin here.** `--timeout=` is an unrecognised argument and fails
  collection outright with exit 4.

Next: install the driver and release the branch to it. First work item is `N1-corpus-at-scale`.

---

## Entry 1 — N1: the corpus-at-scale exploration (2026-08-16T21:50 +01:00)

First iteration to actually run under the driver. Verified before starting: branch is
`autonomous/2026-08-16-spec-corpus-and-jobs`, `git log` head is `46e2a74` matching STATE.json's
implicit position (iteration 0, no heartbeat yet — this is genuinely the first firing), working
tree clean. No reconciliation needed.

Did the reading N1's `next_action` specified, in order: `openspec/specs/` (30 capability
directories, confirmed) and read `spec-document-authority/spec.md` in full (573 lines) as the
"what does a current-behaviour document read like" sample; `openspec/changes/` (17 unarchived, 67
archived, confirmed) and read one archived change's `specs/` delta
(`2026-08-14-what-the-product-actually-built/specs/task-lifecycle-governance/spec.md`) to see the
ADDED-Requirements delta convention concretely; `hub/hub/db/models.py` around `Task` (595-660) and
`SpecDocument`/`SPEC_PHASES` (1500-1580); `taskFilterStore.ts`, `App.tsx:330-358`, and
`SpecCoverageBar.tsx` to trace the existing outside-the-board filter mechanism end to end
(`onOpenTasks` → `setActiveTaskIds` → navigate → `TasksBoard` reads `activeTaskIds` and filters
every column, with a "Showing N tasks linked from…" banner). Also spot-checked
`hub/hub/api/v1/tasks.py` for an existing `spec_document_id` query filter — there isn't one yet
(the field is used to *populate* task responses, not to filter the list), which the document
states honestly as unverified/out-of-scope rather than assuming.

Wrote `openspec/explorations/2026-08-16-a-corpus-at-scale.md`, answering N1's five questions:

1. **Capability vs. change document** — the distinction already lives in file layout and prose
   (absolute requirements vs. ADDED/MODIFIED/REMOVED deltas); the Hub-side gap is only that
   `SpecDocument.kind` has never taken a second value. Recommends the capability/change split be a
   rendering-schema concern, not a new phase.
2. **The folder tree at scale** — `openspec/specs/` stays flat and fine at 30; the real scale risk
   is `openspec/changes/archive/` at 67, which is unindexed by capability. Recommends a
   capability-linkage index (Hub-side query, not a folder reorganization) over moving 67
   directories around, and separately flags that a *capability document's own length* (863 lines
   for `task-lifecycle-governance` today) is the sharper long-run risk than folder layout.
3. **What a finished delta does to the corpus** — ports the already-proven openspec convention
   (delta reviewed and hand-merged into the capability doc) into the Hub's data model, and
   separates "merge the delta" from "archive the change document" as two acts, not one, so evidence
   can keep accumulating on an already-merged change without forcing a premature archive.
4. **The task board at scale** — traces the existing `taskFilterStore`/`SpecCoverageBar` mechanism
   as proof a document-scoped filter is a second caller of code that already works, not new
   machinery: one new query plus one UI affordance, no schema change.
5. **What archiving does to a change's tasks** — recommends a *view-level* default-filter exclusion
   (archived document's tasks hidden from the unscoped board only if the task itself is also
   terminal; open tasks from archived documents stay visible), explicitly not a task mutation, and
   notes it composes with N2 (same query surface) without being decided by N1 which of N2/N2b
   implements it — restated from N2b's own brief rather than re-litigated.

Six numbered recommendations close the document, addressed to N2 and N2b by name, concrete enough
to spec from per N1's `output` requirement. No code changed; this item is spec-only by design.

**Verification**: read-only exploration work: no test suite applies. Confirmed the document exists
and reads coherently top to bottom after writing it (no separate "run tests" step for this item —
the deliverable is the document itself, and N1's `output` field asks only for a document, not
running code).

Advanced `current` to `N2-archive-and-capability` and wrote its `next_action`: round 1 (author) of
the change's spec artifacts, informed by N1's recommendations above, following N2's own `detail` in
the queue for the migration/lifecycle mechanics (0074, the SQLite CHECK-constraint recreate trap,
enforcing archive-is-operator-only inside `spec_lifecycle.transition`). N2b remains pending,
contingent on N1 as already stated — N1 did NOT conclude the board needs no scoping, so N2b is not
skipped.

---

## Entry 2 — N2 spec-round 1: the archive transition and the capability kind (2026-08-16T22:14 +01:00)

Verified before starting: branch `autonomous/2026-08-16-spec-corpus-and-jobs`, `git log` head
`2f7f22c` matching STATE.json, working tree clean. `current` was already `N2-archive-and-capability`
from entry 1's handoff. No reconciliation needed.

Read N1's exploration in full before writing anything, as `next_action` required, plus the code it
grounds itself in: `hub/hub/spec_lifecycle.py` (the whole file — `transition()`'s operator-only
approval check is the shape everything else in this round copies), `spec_service.py` (`save_document`,
`rename_document` — the ordering discipline "everything that can be refused is refused before anything
moves" is reused rather than reinvented), `spec_payload.py` (`SpecPayload`, `KINDS`, `validate_payload`)
and `spec_render.py`, `hub/hub/db/models.py` around `SpecDocument`/`SPEC_PHASES`, migrations `0058` and
`0073` (the two prior CHECK-constraint-recreate migrations this round's `0074` follows), `0065` (the
guarded plain-`create_table` idiom the new `spec_document_merges` table follows), and
`hub/hub/api/v1/spec.py` and `agent_actions.py` end to end to see which routes are operator-credentialed
versus agent-credentialed.

**One correction to N1, found by reading code N1 had not read this closely.** N1's recommendation 1
said a capability document needs a distinct payload schema (absolute requirements vs. a
change-spec's ADDED/MODIFIED/REMOVED delta), reasoning from the *openspec file* convention. Reading
`spec_payload.py` shows the Hub's `SpecPayload` has never modelled a delta at all — every document's
`requirements` field is a flat, absolute list, `change-spec` included, because nothing in the Hub's own
JSON payload has ever had ADDED/MODIFIED/REMOVED semantics; that convention exists only in the
hand-authored `openspec/` markdown files N1 read. So a capability document needs **no schema change** —
recorded as design D2's correction, with the reasoning, rather than silently doing something different
from what N1 recommended.

**One latent bug found while tracing the write path, fixed in the same change rather than filed
separately.** `spec_service.save_document` → `spec_lifecycle.record_content` sets `document.kind =
payload.kind` on **every** content submission, unconditionally — an agent's payload can silently
reclassify a document's `kind` today, and nothing has ever needed a document's `kind` to be trustworthy
enough to notice. Once `kind='capability'` starts governing which phase a document is allowed to
occupy (this change's whole point), that same drift would let a submission defeat the coupling. Design
D3 pins `kind` at creation and refuses a submission whose `kind` disagrees with the document's own —
argued in the design doc as belonging in this change, not a follow-up, because shipping the coupling
without it ships a coupling with a known hole.

Wrote the full artifact set at
`openspec/changes/2026-08-16-the-corpus-keeps-what-shipped/`:

- **`proposal.md`** — the gap, what changes, capabilities touched (`spec-document-authority` only,
  modified — this is additive machinery inside its existing domain, not a new capability area),
  impact, and six explicit non-goals (no task-board scoping — that's N2b; no merge-before-archive
  requirement; no general capability-document content editor beyond creation and merge; no unarchive
  transition; no `openspec/` reorganisation; no import of openspec's existing 30+67 documents).
- **`design.md`**, eight sections: D1 the two new phase values and the one new transition, enforced in
  `transition()` exactly where approval already is; D2 capability documents (created directly at
  `current`, written only by the operator, and the schema correction above); D3 the kind-pinning fix;
  D4 the new `spec_document_merges` table — chosen over N1's left-open JSON-field alternative because
  an unindexed JSON scan does not answer "what touched this capability" as a query, and given a
  `CHECK actor_kind = 'operator'` stronger than every other actor-kind CHECK in the schema, because this
  table exists specifically to make the operator's-authorship rule true; D5 the merge endpoint
  (`POST /project/documents/{path}/merge`, operator-only, sources named by path, must be `approved` or
  `archived`); D6 migration `0074` in two pieces (the `ck_spec_documents_phase` recreate plus two *new*
  CHECKs — a `kind` vocabulary CHECK that has never existed before, and a cross-column
  `(kind='capability') <=> (phase='current')` CHECK in the shape `0058` already established for
  `origin_type`/`origin_agent` — and a guarded plain `create_table` for the merge table); D7 the three
  UI changes (an Archive button, a latent "Reopen shows for every non-exploring phase" bug fix that
  becomes load-bearing once `archived`/`current` exist, a muted chip treatment); D8 states explicitly
  what this leaves untouched for N2b (no task is read or written by anything in this change).
- **`tasks.md`** — 11 sections, unchecked: migration, model, lifecycle, service, API, the agent-route
  refusal (which needs no code change if D2's refusal is placed correctly — task 6.1 says to confirm
  this by reading and by test, not assume it), UI, agent-verifiable tests, driven-against-the-running-Hub
  checks, human-only verification, and a user test guide. Task 8.5 deliberately leaves one edge case
  undecided rather than silently picking an answer: can a capability document itself be cited as a merge
  *source*? Design D5 doesn't rule it out and probably should — flagged for round 2 or for whoever
  implements to resolve, not guessed at here.
- **`specs/spec-document-authority/spec.md`** — three ADDED requirements (archiving, the capability
  kind, the authored merge) and two MODIFIED (the phase-transition requirement gains `current`'s
  no-transitions rule; the approval-is-the-operator's requirement gains archiving as its sibling, with
  a scenario stating the refusal holds "regardless of caller" — the same wording this session's own
  `spec_lifecycle.py` docstring uses for why the check lives in the function and not the route).

**Validation friction worth recording**, since CLAUDE.md asks every friction with the spec flow itself
to be recorded rather than worked around: `openspec validate --strict` refused the merge requirement
with "must contain SHALL or MUST" even though the full paragraph plainly contains SHALL — the parser
only reads the **first physical line** of the requirement's opening paragraph, not the full sentence
after a hand-wrapped line break. Every existing requirement in the corpus that wraps its opening
sentence happens to have its modal verb before the first line break by accident of phrasing; this one
didn't. Rewrote the sentence so SHALL appears in line one. This is a real authoring trap for anyone
writing openspec by hand — worth a line in a later pass over the `openspec-propose` skill's own
guidance, not something to fix in this run.

**Verification**: `npx openspec validate 2026-08-16-the-corpus-keeps-what-shipped --strict` → valid.
`npx openspec validate --changes --strict` → **18 passed, 0 failed** (17 baseline + this one), matching
the `verified_green_at_b2b0cd5` baseline plus one. No code was touched this iteration — round 1 is
author-only per `spec_round_protocol` — so `pytest`/`npm test`/etc. are unchanged from baseline and were
not re-run; nothing in this iteration could have moved them.

`current` stays `N2-archive-and-capability`. Advanced `next_action` to round 2: a cold review against
the four binding rulings and N2's own queue detail, with explicit call-outs to the judgment calls this
round made on its own authority (the schema correction, the kind-pinning bundling, the table-over-JSON
choice, the cross-column CHECK, path-based source naming) so round 2 does not have to rediscover them
from scratch — and a reminder that `at_cap`/on-approval means proceed straight to implementation in the
same run, tasks.md section by section, not stop at another artifact.

---

## Entry 3 — N2 spec-round 2: cold review, one load-bearing gap found and fixed (2026-08-16T22:23 +01:00)

Verified before starting: branch `autonomous/2026-08-16-spec-corpus-and-jobs`, `git log` head
`b07b1f6` matching STATE.json, working tree clean. `current` already `N2-archive-and-capability`,
`next_action` already round 2. No reconciliation needed.

Read `next_action`'s checklist in full and read code cold rather than trusting round 1's own
account of it: `hub/hub/spec_lifecycle.py` end to end (`transition()`, `create_document`,
`record_content`), `hub/hub/spec_service.py` (`save_document`, `rename_document`, `propose`),
`hub/hub/spec_payload.py` (`KINDS`, `validate_payload`, `SpecPayload`), `hub/hub/db/models.py`
around `SpecDocument`/`SPEC_PHASES` and every `actor_kind` CHECK in the file, migrations `0058`
(the cross-column CHECK precedent) and `0073` (the batch-recreate precedent), and
`hub/hub/api/v1/spec.py` (`_operator`, `_require_document`, `create_document`, `set_phase`,
`agent_actions.py`'s `submit_spec_document`) to see the actual write paths rather than take
`design.md`'s account of them.

**Confirmed accurate, no action needed:** D2's correction of N1 (verified directly in
`spec_payload.py` — `SpecPayload.requirements` really is one flat shape for every `kind`, no delta
schema anywhere); D4's actor_kind CHECK claim (every existing `actor_kind` CHECK in `models.py` is a
plain `IN ('operator', 'agent', 'system')` — six of them, grep'd — so the new table's
`CHECK actor_kind = 'operator'` really is stronger than the rest, not a stray tightening); D6's
cross-column CHECK precedent (`0058`'s `origin_type`/`origin_agent` pair is exactly that shape);
`0073`'s batch-recreate-with-guard idiom matches what D6 claims for `0074`; `agent_actions.py`'s
`submit_spec_document` really does catch `SaveRefusedError` generically (`code=exc.code`, no fixed
mapping) — task 6.1's conditional ("if the route maps a fixed set of codes, extend it") correctly
hedges on a premise that turns out false, not a bug.

**One load-bearing gap, found by tracing the write path rather than trusting the design doc's
account of it.** `spec_payload.KINDS` is `("baseline", "system-map", "roadmap", "change-spec")`
today, and `validate_payload` refuses any `payload.kind` outside it — unconditionally, before
either of D2's or D3's new refusals ever run. Design D2 states in prose that `KINDS` "gains
`capability` as a valid value," but round 1's `tasks.md` never turned that into a checklist item —
no task anywhere touches `spec_payload.py`. Traced the consequence concretely: the *existing,
unchanged* `create_document` API route (`hub/hub/api/v1/spec.py:810`) already calls
`spec_service.save_document` immediately after creating any document, of any kind, to write its
initial scaffold (`payload = {"kind": document.kind, "title": ..., ...}`). So creating a capability
document at all — not merging into one, just creating the empty scaffold task 8.4 tests — would hit
`validate_payload`, find `kind="capability"` outside `KINDS`, and refuse `payload_invalid` before
D2's phase or D3's kind-pinning logic ever run. The entire mechanism this change exists to build
would be unreachable from its own first step.

**Fixed in place, not just flagged.** Added task 4.4 to `tasks.md` (`spec_payload.py`: `KINDS`
gains `"capability"`), marked load-bearing with the reasoning above so whoever implements does not
skip it as a nice-to-have. Fixed task 1.2's wording, which had computed the migration's
`ck_spec_documents_kind` CHECK as `spec_payload.KINDS + ("capability",)` — now that 4.4 makes
`KINDS` include it directly, that concatenation would just duplicate the value in the SQL `IN`
list; reworded to reference `spec_payload.KINDS` directly once both tasks are done, so there is one
source of the vocabulary, not two that happen to agree today. Fixed a dangling cross-reference in
`design.md` D2 (`"(§ D5)"` — D5 never mentions `KINDS` at all) and added a short "Round 2
correction" paragraph there stating the gap and the fix, so a reader of `design.md` alone sees why
task 4.4 exists without having to find this log entry.

**One clarification, not a gap.** Task 8.5 flagged "can a capability document itself be a merge
source?" as an edge case design D5 doesn't rule out and should. Reading D5 step 4 again: it already
refuses any source document whose `phase` is not `(APPROVED, ARCHIVED)`, and a capability document's
phase is always `current` — so citing one as a source is *already* refused today, by the same
`source_not_finished` code, as a pure side effect of the phase gate, no extra code required. Not
actually undecided; reworded task 8.5 to say so and to note the only real open question is whether
`source_not_finished` is the right *message* for a document that was never a change (nice-to-have,
not a blocker) — so the test still needs writing, but the implementer isn't asked to invent
behaviour that already falls out of D5.

**Verification**: `npx openspec validate 2026-08-16-the-corpus-keeps-what-shipped --strict` →
valid. `npx openspec validate --changes --strict` → **18 passed, 0 failed**, unchanged from round
1's count (a revision, not a new change). No code touched this iteration — round 2 revising an
artifact is still artifact-only work — so `pytest`/`npm test` are unchanged from baseline and were
not re-run.

`current` stays `N2-archive-and-capability`. Advanced `next_action` to round 3: a fresh cold check
specifically of whether task 4.4's fix is complete and correctly placed (does anything else assume
`KINDS` is the original four-tuple? — `ck_spec_documents_kind`'s literal SQL list in the migration
file needs to be written from the *post-4.4* `KINDS`, not copy-pasted from this round's now-stale
description of it), plus a final pass over anything this round didn't have time to re-derive from
scratch (the UI section, the human-only verification list, the user test guide) — and then, per
`spec_round_protocol.at_cap` (round 3 is the cap), record any remaining objections in `design.md`
and proceed straight to implementation in the same run, `tasks.md` section by section: migration
0074 first (task 4.4 done first within that pass, since 1.2 now depends on it being decided), then
model, lifecycle, service, API, agent-route refusal, UI, then the test sections.

---

## Entry 4 — N2 round 3: one more gap found, then implemented and shipped end to end (2026-08-16T23:12 +01:00)

Verified before starting: branch `autonomous/2026-08-16-spec-corpus-and-jobs`, `git log` head
`594fe57` matching STATE.json, working tree clean. `current` already `N2-archive-and-capability`,
`next_action` already round 3 (the cap). No reconciliation needed.

**Round 3 review**, reading code cold rather than trusting rounds 1-2's account of it. Re-derived
task 4.4 directly from `spec_payload.py` — confirmed `KINDS` was still the original four-tuple and
the fix is exactly as load-bearing as round 2 said. Then, per round 3's specific brief (does
anything else assume `KINDS` is the original four-tuple), grepped every occurrence of the four kind
strings across `hub/hub` rather than trusting the design doc's account of where they live. Found a
second gap task 4.4 alone did not close: `hub/hub/mcp_server.py`'s `SpecKind` Literal is a *restated*
copy of `spec_payload.KINDS` (CLAUDE.md: `mcp_server.py` may import only stdlib + fastmcp, so
anything it needs from the Hub is restated there) — and
`test_mcp_tool_schemas.py::test_spec_kind_agrees_with_the_payload_validator` asserts the two sets are
equal. The moment `KINDS` gained `capability`, that existing test would fail deterministically. Traced
the consequence to confirm it was a test-honesty issue and not a security hole: `submit_spec_document`
(the tool using `SpecKind`) only writes to a document that already exists, and document creation is
reached only through the operator's own project credential with a hardcoded operator actor — no
agent-reachable route creates a document of any kind, capability included. So the fix (task 4.5, added
to `tasks.md`) keeps the restated type honest; it does not open or close a door. Also checked and
ruled out two false positives from the same grep: `spec_manifest.VALID_KINDS` and the UI's
`SpecEntry.kind` TS union both name the same four strings but belong to the unrelated on-disk
manifest/index subsystem (`spec/index.json`), never read or written by anything this change touches —
recorded in `tasks.md` as confirmed-out-of-scope rather than silently ignored. Re-read the UI plan (D7)
against the real `SpecPhaseBar.tsx` and confirmed the Reopen-narrowing bug and the insertion points
were both exactly as designed. `npx openspec validate 2026-08-16-the-corpus-keeps-what-shipped
--strict` -> valid after recording the finding in both `design.md` and `tasks.md`.

**Implementation, `tasks.md` section by section, per `spec_round_protocol.at_cap`:**

- **Migration 0074** — `batch_alter_table` recreating `ck_spec_documents_phase` (five values), adding
  `ck_spec_documents_kind` (first-ever CHECK on that column) and the cross-column
  `ck_spec_documents_kind_phase`; a guarded `create_table` for `spec_document_merges` following
  `0065`'s shape. Verification caught a real harness bug before it became a shipped-migration bug: a
  first hand-rolled upgrade/downgrade/upgrade round-trip script showed the post-round-trip schema
  reverting to the pre-migration three-value CHECK with `alembic_version` still reading `0074` —
  looked exactly like a broken migration. Traced it to the test harness, not the migration: the script
  called `Base.metadata.create_all` through `hub.db.engine`'s module-level `engine` singleton, which is
  constructed from `settings.database_url` at import time — before the script's patch of that setting
  ever took effect — so `create_all` silently ran against the real default database
  (`hub/data/agentweave.db`, the preserved pre-migration backup CLAUDE.md explicitly warns not to
  touch) while alembic's own upgrade correctly targeted the tmp file. This did write one new, empty
  `spec_document_merges` table into `hub/data/agentweave.db` — `create_all` is additive-only (creates
  missing tables, never alters or drops existing ones), so no existing row in any of that file's 42
  other tables was touched; confirmed by reading its table list and row counts before moving on.
  Re-ran the round-trip with an explicitly-constructed async engine bound to the tmp path instead of
  the module singleton — clean: `create_all` + `alembic upgrade head` (mirroring the real `init_db()`
  sequence) produces every new constraint, and `downgrade -1` + `upgrade head` round-trips back to the
  identical shape. Bumped all 12 head assertions (`test_migrations.py` x11 including the two inside
  `test_migration_0073_*` functions that upgrade to head and were previously asserting the old head,
  `test_project_persistence.py` x1) — script-driven since they are mechanically identical lines,
  verified the exact line set first.
- **Model** — `SPEC_PHASES` gains `archived`/`current`; new `SPEC_KINDS` local constant (restated,
  same non-cross-import convention `SPEC_PHASES` already follows) backing the two new CHECKs on
  `SpecDocument.__table_args__`; new `SpecDocumentMerge` class exactly per design D4.
- **Lifecycle** (`spec_lifecycle.py`) — `ARCHIVED`/`CURRENT` constants; `TRANSITIONS` gains
  `(APPROVED, ARCHIVED)` only; `create_document` picks `CURRENT` for `kind == "capability"`;
  `transition()`'s unknown-phase guard admits `ARCHIVED`, still refuses `CURRENT` as a `to_phase` (the
  only door into `current` is creation); a new operator-only check for `to_phase == ARCHIVED`, same
  shape as the existing approval check, `code="archive_is_the_operators"`; `record_content` drops its
  now-redundant `kind` parameter, one call site updated.
- **Service** (`spec_service.py`) — `save_document` reordered so `validate_payload` runs first, then
  two new refusals before the existing `document.phase == APPROVED` check (both design D2 and D3 ask
  for this ordering): `kind_is_fixed` (`payload.kind != document.kind`) and
  `capability_write_is_the_operators` (`document.kind == "capability" and actor.kind != "operator"`).
  New `merge_document()` — steps 5-6 of design D5 (write via `save_document`, one `SpecDocumentMerge`
  row plus one `merged` event per source); commit/broadcast stay the route's job, matching every other
  function in this file.
- **`spec_payload.py`** — `KINDS` gains `capability` (task 4.4); the `kind` field's docstring updated
  to match, since it is agent-facing.
- **`mcp_server.py`** — `SpecKind` gains `capability` (task 4.5).
- **API** (`spec.py`) — `MergeRequest` model; `POST /project/documents/{path}/merge` following design
  D5's refusal order. One deviation from the letter of task 5.2, recorded because it changes tested
  behaviour: `_require_document`'s generic 404 (document not found) does not name the path, but design
  D5 step 3 explicitly wants the missing source named — wrote the source-resolution loop inline
  instead of reusing `_require_document` so the 404 detail states the actual missing path; verified by
  a dedicated test. Audited every other route in the file plus `agents.py`'s `SPEC_PHASE_DUTIES` dict
  and `launchability.py`'s exploring/else branch for a closed-set phase assumption (task 5.4) — both
  degrade gracefully for the two new phases, no fix needed, recorded rather than silently assumed
  clean.
- **UI** — `SpecPhaseBar.tsx`: Reopen narrowed to `proposed`/`approved`; new Archive button (`approved`
  only, existing `useSetSpecPhase` mutation, no new hook); muted chip color for `archived`/`current`.
  `spec.ts`: `SpecDocumentRecord.phase` union gains the two literals. 13 new cases added to the
  existing `specPhaseBar.test.tsx` rather than a new file. `npm run build` + `refresh_ui_bundle.py`.

**A second harness-adjacent finding, caught by `/health` after restarting the trial Hub rather than by
any test**: `refresh_ui_bundle.py`'s fingerprint folds in `git status --porcelain` (so an uncommitted
edit still moves the fingerprint) — running it before committing `hub/ui/src` stamps a fingerprint
that includes a dirty suffix the post-commit clean tree no longer reproduces, so `/health` reported
`ui_stale` even though the bundle was byte-identical to what was committed. Re-running the script
against the clean, committed tree produced a matching fingerprint; only `ui-build-stamp.json` changed
(confirmed via `git status` — no asset content differed), committed separately. Worth a line in a
later pass over that script or its own instructions: build-then-commit is the wrong order for this
fingerprint design; commit-then-build (or refresh again post-commit) is what actually produces an
accurate stamp.

**A third real gap, caught only by running the full suite, not by anything in `tasks.md`**:
`test_project_delete_api.py` maintains a hand-written `PROJECT_SCOPED_TABLE_NAMES` list and a
`_seed_full_project` helper, checked against the live model registry by a dedicated sweep-coverage
test. `spec_document_merges` carries a `project_id` column, so it is automatically part of the live
delete sweep (`project_lifecycle.py`'s `_project_scoped_tables()` introspects `Base.metadata`
directly — no code change was needed there, cascade-delete already covers the new table correctly) —
but the test's hand-written list didn't know about it, failing the sweep-coverage test and, downstream,
the two orphan-check tests whose seed helper left the new table at zero rows. Fixed by adding the table
name to the list and one seed row (capability/change ids both point at the same seeded document row —
no CHECK forbids that, and nothing about an orphan check cares which document either FK names).

**Verification, all green:**
- `pytest hub/tests/ -n 8`: 2089 passed, 11 skipped (baseline 2068/11 — +21 new: 7
  `test_spec_archive.py`, 6 `test_spec_capability_kind.py`, 8 `test_spec_merge.py`).
- `pytest tests/ -n 4`: 362 passed, 3 skipped — unchanged from baseline.
- `npm test`: 934/934 (baseline 921 — +13 in `specPhaseBar.test.tsx`).
- `npm run lint`, `npx tsc --noEmit`: clean.
- `ruff check hub/ src/`: clean. `black --check`: clean after auto-formatting 5 files (line-wrapping
  only, re-tested after).
- `npx openspec validate --changes --strict`: 18/18. `--specs --strict`: 30/30.
- Driven against the running Hub (restarted twice — once onto the implementing commit, once more
  after the bundle-stamp fix — `/health` returned status ok, no `ui_stale`, before trusting any
  observation): all five of section 9's checks, live, against `proj-5e960453` (this repo's own trial
  project) with a directly-minted run credential standing in for a live agent process (same technique
  the Python test suite uses — no Claude/Codex process needed to exercise the HTTP surface). 9.1
  created a capability document, confirmed phase current and a refused approve attempt (409
  illegal_transition). 9.2 approved an ordinary change (materialising one task), archived it, and
  confirmed the task's status/updated/spec_document_id were byte-identical before and after via two
  GETs. 9.3 merged the archived change into the capability document, confirmed one merge recorded, a
  `spec_document_merges` row queried directly from the trial database, and the rendered HTML on disk
  showing the merged content with the capability kind/status metadata. 9.4 named a still-proposed
  source and got 409 source_not_finished naming the actual path and phase. 9.5 used the run credential
  against the agent route targeting the capability document and got 422
  capability_write_is_the_operators.

**Teardown, not left in place.** This repo is itself the trial project's registered working
directory, so the verification writes above landed as real files under `spec/` in this checkout, not
in some other project's sandbox — `git status` surfaced an untracked `spec/capabilities/n2-drive-test/`
and two `spec/changes/n2-drive-test*/` trees. Rather than commit synthetic test debris into the
tracked `spec/` corpus or leave the trial database inconsistent with the filesystem, deleted both
sides: every dependent row (`spec_requirements`, `spec_requirement_revisions`,
`task_requirement_links`, `requirement_evidence`, `spec_document_events`, `spec_document_merges`,
`task_requirement_references`, `task_transitions`, the one materialised `Task`, the three
`SpecDocument` rows, the synthetic `Run`) via direct SQLite deletes against the trial database, then
`rm -rf` the three directories. Verified zero rows and zero files remain named `n2-drive-test`
afterward. The Hub itself is untouched — this was cleanup of my own verification data, not of
anything else in either project.

**Not done, deliberately** — section 10 (human-only: does Archive read as final, is a capability
document's phase bar quiet without looking broken) genuinely needs a person looking at the UI; left
unchecked in `tasks.md` for the operator rather than guessed at from a screenshot.

Committed as `5e36209` (the implementation) and `55af280` (the bundle-stamp correction), both on this
branch.

`current` advances to `N2b-task-board-at-scale`. Read N1's exploration section 4-5 before setting
`next_action`: N1 does not recommend skipping N2b — it recommends two concrete pieces: (1) a "show
this document's tasks on the board" affordance, generalizing the exact mechanism
`SpecCoverageBar`/`taskFilterStore.activeTaskIds` already proves live (a new `taskIds` source, not new
UI machinery) — verified in this session that `TasksBoard.tsx` really does filter by `activeTaskIds`
membership; (2) archiving retiring a document's completed tasks from the board's default (unscoped)
view only — a task's status/assignee/every other field is untouched, this is a view-level query
filter, and N1's own coordination note says explicitly this exclusion belongs to whichever of N2/N2b
lands second — since N2 just landed, that is N2b's job, not a duplicate of anything N2 shipped
tonight (confirmed: N2's design D8 states explicitly no task is read or written by anything in that
change). `next_action` set to N2b's own round 1: author `proposal.md`/`design.md`/`tasks.md`/spec
delta in `openspec/changes/`, grounded in N1's two recommendations above rather than re-deriving them,
then round-robin per `spec_round_protocol`.

## Entry 5 — N2b round 1 (author)

Authored `openspec/changes/2026-08-16-the-board-scoped-by-document/` — `proposal.md`, `design.md`,
`tasks.md`, and a `task-lifecycle-governance` spec delta. Grounded directly in N1's sections 4-5 and
N2's design D8 handoff, re-derived nothing.

**Read before designing, not assumed:** `hub/hub/api/v1/tasks.py`'s `list_tasks` (only `agent`,
`status`, `offset`, `limit` today); `hub/ui/src/api/tasks.ts`'s `useTasks()`, called with no
arguments from three other places besides the board (`App.tsx`, `OverviewPage.tsx`,
`QualityHealthPanel.tsx` — confirmed by grep, all three want the *full* task list, which is why the
exclusion had to be opt-in rather than a new default); `TasksBoard.tsx`'s existing
`activeTaskIds`/`taskFilterStore` mechanism (client-side membership filter over whatever `useTasks()`
returned); `SpecCoverageBar.tsx`'s `onOpenTasks` wiring through `SpecDocumentPanel.tsx` to
`App.tsx:352-355`; `run_task_binding.TERMINAL_FOR_BINDING = ("approved", "rejected")`, already
imported in `tasks.py` — confirmed by reading the file's own import block, not assumed; `Task.
spec_document_id` (indexed, nullable) and `SpecDocument.phase`/`spec_lifecycle.ARCHIVED` (from N2,
already landed this session).

**The one real design decision, not just plumbing:** whether the archived-and-terminal exclusion
belongs at `GET /tasks`'s *default* (every caller gets it) or behind an opt-in parameter only the
board's own fetch requests. Traced the alternative through before rejecting it: if the exclusion
applied by default, the MCP `list_tasks` tool and the Overview/Quality pages would silently start
losing rows with no code change on their part, and — the concrete bug, not a hypothetical one — the
existing `SpecCoverageBar` task-count links (which pass specific task ids into `activeTaskIds` and
expect `TasksBoard` to find them inside whatever `useTasks()` returned) would show "Showing N tasks"
banners for documents that had since been archived while displaying zero of them, because the
excluded rows would never have reached the client to be filtered by id in the first place. Design D1
solves this with two independent, `elif`-ordered query parameters (`spec_document_id` always shows
everything; `exclude_archived_completed` defaults `false` and is opt-in) rather than one default
behaviour change — every existing caller of `GET /tasks`, agent-facing or UI, is unaffected unless it
explicitly asks for the new behaviour.

**New affordance kept separate from `SpecCoverageBar` rather than folded in**, because that
component returns `null` when a document has no requirements and no diagnostics
(`SpecCoverageBar.tsx:87`) — a condition unrelated to whether the document declared tasks. Folding
the new "N tasks declared by this document" link inside that early return would hide it exactly when
it is least discoverable any other way. A second, independent `SpecDocumentTasksLink.tsx` with its
own null-guard avoids coupling two facts that are not actually related.

**Corrected one filename assumption while writing `tasks.md`**: initially referenced
`hub/tests/test_tasks_api.py` and a nested `hub/ui/src/components/.../__tests__/` layout by pattern-
matching N2's tasks.md without checking. Listed the actual directories before finalizing: the backend
file is `hub/tests/test_tasks.py` (confirmed present), and every UI test in this repo lives flat
under `hub/ui/src/__tests__/` — including `tasksBoardFilter.test.tsx`, which already tests exactly
the `activeTaskIds` mechanism this change extends, so task 3.5 targets it directly instead of
inventing a new file. Fixed before this was committed, not left for round 2 to catch.

**Not yet done — this is round 1 only.** `npx openspec validate --changes --strict` is clean (19/19,
this change included). No code has been touched; `hub/hub/api/v1/tasks.py`,
`hub/ui/src/api/tasks.ts`, `TasksBoard.tsx`, and the new `SpecDocumentTasksLink.tsx` all remain as
they were at N2's implementation commit. Per `spec_round_protocol`, the next iteration reads this
change **cold** — without re-deriving the reasoning above from memory, verify it independently
against the actual files — and either approves (moving straight to implementation, since round 1 is
below the 3-round cap) or raises objections for round 2. `current` stays `N2b-task-board-at-scale`;
`next_action` set to N2b round 2 (cold review).

## Entry 6 — N2b round 2 (cold review, one real gap found and fixed) (2026-08-16T23:37 +01:00)

Read `proposal.md`, `design.md`, `tasks.md`, and the spec delta cold — none of Entry 5's reasoning
taken on trust — and independently re-verified the four things `next_action` named:

1. **`hub/hub/api/v1/tasks.py` imports.** Read the file's own import block (lines 1-40).
   `TERMINAL_FOR_BINDING` is already imported (`from ...run_task_binding import (TERMINAL_FOR_BINDING,
   ...)`, line 29). Neither the `spec_lifecycle` module nor `SpecDocument` is imported today — only
   `from ...spec_lifecycle import Actor as SpecActor` (line 35), which does not give access to
   `spec_lifecycle.ARCHIVED`. Task 1.1's claim holds exactly as stated.
2. **`useTasks()` call sites.** Grepped `hub/ui/src` directly: `App.tsx:131`,
   `QualityHealthPanel.tsx:25`, `OverviewPage.tsx:75`, plus `TasksBoard.tsx:35` — exactly the three
   named besides the board. (`projectScopedApiContract.test.tsx` also calls it with no arguments in
   four places, but as a test file consuming the same default-`false` optional argument, it needs no
   change and design D2 doesn't claim otherwise.)
3. **Test file identities.** `hub/tests/test_tasks.py` exists;
   `hub/ui/src/__tests__/tasksBoardFilter.test.tsx` exists and is exactly where `activeTaskIds`'s
   board-level filtering is already tested (read it in full — see finding below).
4. **The `elif`-ordering / entry-point argument.** Traced `App.tsx:352-355`'s `onOpenTasks` handler
   (`setActiveTaskIds` then navigate) and confirmed both `SpecCoverageBar.tsx:238`'s existing wiring
   and design D3's new `SpecDocumentTasksLink` receive the *same* `onOpenTasks` prop threaded through
   `SpecDocumentPanel.tsx:64/238` — they are literally the same callback, not two paths that could
   drift apart. `TasksBoard.tsx:47` reads `activeTaskIds` from the same store `setActiveTaskIds`
   writes to, and `useTasks({ excludeArchivedCompleted: activeTaskIds === null })` (task 2.3) flips to
   `false` the instant either link is clicked. Holds for both entry points because they share one
   underlying mechanism.

Also independently checked facts design.md cites without a specific line reference, rather than take
them as given: `TERMINAL_FOR_BINDING: Tuple[str, ...] = ("approved", "rejected")` at
`run_task_binding.py:272`; `ARCHIVED = "archived"` at `spec_lifecycle.py:31`; `Task.spec_document_id`
is `Mapped[Optional[str]]`, `String(64)`, `nullable=True`, `index=True` at `models.py:641`. All match
the design's claims exactly. Checked the codebase's existing style for `.in_(select(...))` without
`.scalar_subquery()` (`scheduler.py:218` does the same thing) — D1's subquery snippet is consistent
with how this codebase already writes this, not a novel pattern that might not actually execute.

**The gap.** Read `tasksBoardFilter.test.tsx` in full rather than skimming for the filename match
task 3.5 needed. Its `vi.mock('@/api/tasks', ...)` stubs `useTasks: () => ({ data: TASKS, isLoading:
false })` — a zero-argument function that ignores whatever options `TasksBoard.tsx` passes it and
always returns the same static array. Per design D2, `TasksBoard.tsx` itself carries no code that
excludes an archived-and-terminal task — that exclusion is entirely server-side, expressed only in
which argument `useTasks()` receives. Traced `TasksBoard.tsx` end to end to confirm: `activeTaskIds`
(lines 150-151, 238) is the *only* filter the component applies to the array it already has, and it's
a client-side membership check unrelated to document phase or task status. So task 3.5 as round 1
wrote it — "add a case... confirm it is absent from the default board render" — names an assertion
this test file's own mock cannot produce: the mock discards the argument that would need to carry the
exclusion, so every seeded task would render regardless of what `TasksBoard.tsx` passed. This is the
same class of gap N2's own round 2 found (Entry 3): a task naming a behaviour the scaffolding named
around it cannot exercise, caught by reading the file rather than trusting the filename match.

**Fixed, not deferred.** Recorded as design D5 ("Round 2 correction," following N2's own convention)
and revised tasks.md's 3.5 directly: make the existing mock argument-sensitive (return a filtered
array when `excludeArchivedCompleted` is true, standing in for the server-side exclusion this
proposal actually builds), so the "absent from the default view" half of the test exercises real
logic and the "present once `activeTaskIds` includes it explicitly" half continues to exercise
`TasksBoard.tsx`'s real, unchanged client-side filter. Confirmed no existing call site in this
codebase already asserts on a mocked hook's arguments (grepped; none do), so this is the minimal fix
rather than a new pattern invented from nothing.

**No other objections.** Everything else in round 1's design and tasks — the `elif` ordering, the
`IN`-subquery-over-join choice, the separate `SpecDocumentTasksLink` component instead of folding
into `SpecCoverageBar`, the query-key-includes-options React Query rationale, the non-goals — checks
out against the actual files with no further gap found.

`npx openspec validate --changes --strict` clean, 19/19, this change included, after the tasks.md
edit. Per `spec_round_protocol`, round 2 found and fixed a real gap, which does not by itself approve
the change — the cap is 3 and this is round 2, so the next iteration reads the corrected artifact
**cold** for round 3, the same discipline this entry applied to round 1's work. If round 3 finds
nothing further, it proceeds straight to `approve-and-execute` (cap reached, `at_cap` binding for
tonight). `current` stays `N2b-task-board-at-scale`; `next_action` set to N2b round 3 (cold review of
the corrected artifact, specifically D5 and the revised task 3.5, then implementation if clean).

## Entry 7 — N2b round 3 (cap, cold review — clean) → approve-and-execute (2026-08-17T00:23 +01:00)

Read `proposal.md`, `design.md`, `tasks.md`, and the spec delta cold, independently re-verifying
every line-numbered claim against the actual files rather than trusting rounds 1/2's own re-checks:
`tasks.py`'s import block (`TERMINAL_FOR_BINDING` already imported, `SpecDocument`/`spec_lifecycle`
not), `tasks.ts`'s `useTasks()` (still zero-arg) and its three invalidation call sites at the exact
claimed line numbers, `TasksBoard.tsx`'s `activeTaskIds` filter at lines 150-151/238,
`SpecCoverageBar.tsx`'s early return at line 87, `SpecPhaseBar.tsx`'s document lookup at line 30
(byte-for-byte the pattern D3's new component copies), `run_task_binding.py:272`'s
`TERMINAL_FOR_BINDING` tuple, `spec_lifecycle.py:31`'s `ARCHIVED`, `Task.spec_document_id`'s exact
column definition, the flat `__tests__/` convention, and `tasksBoardFilter.test.tsx`'s mock in full
(confirmed D5's fix target — the zero-argument stub — was real, not a round 2 misreading). Everything
held. No further gap found in the artifact itself. Per `spec_round_protocol.at_cap` (binding for
tonight): round 3 is the cap, so this proceeds straight to implementation in the same iteration
regardless.

**Implemented tasks.md sections 1-4.** Backend: `list_tasks` gains `spec_document_id` and
`exclude_archived_completed`, applied per design D1's `elif` ordering. UI: `useTasks()` gains the
options argument, new `useDocumentTasks()`, `TasksBoard.tsx` opts in on its default view, new
`SpecDocumentTasksLink.tsx` rendered beside `SpecCoverageBar`. All exactly as designed — **but two
real defects surfaced only once the code actually ran, past all three rounds of reading it**, plus a
third-party test file that needed updating and a live-environment hygiene issue. Recorded as design
D6/D7 rather than silently fixed, per this change's own convention (D5 already set the precedent):

1. **D6 — the NULL-handling bug.** D1's own stated guarantee ("a task with a null
   `spec_document_id` simply never matches `.in_(archived_ids)`, so the `~(...)` leaves it in the
   result") is wrong about SQL. `IN` on a NULL left operand evaluates to NULL, not `false`; `NULL &
   true` is NULL; `~NULL` is NULL; and `WHERE` drops a NULL-evaluating row exactly like a `false`
   one. The result was the *opposite* of the design's own guarantee — every unlinked task with a
   terminal status would have been silently excluded from the default board, the one class of task
   the whole feature exists to never touch. Caught immediately by task 3.1's own test
   (`test_exclude_archived_completed_hides_only_terminal_tasks_from_archived_documents`, seeded with
   exactly that case) failing on the first run, not by inspection. Fixed with an explicit
   `Task.spec_document_id.isnot(None)` AND'd in before `.in_()` — a real boolean, so it
   short-circuits the whole expression to `false` (not NULL) for an unlinked row.
2. **D7 — `list_shared_tasks` calls `list_tasks` as a plain function.** `agent_actions.py`'s
   `list_shared_tasks` (the route behind the MCP `list_tasks` tool) calls `tasks.list_tasks(...)`
   directly as Python, forwarding only the parameters it already knew about. FastAPI only substitutes
   real values for `Query(...)` defaults when a route is dispatched through the framework itself — a
   direct call left the two new parameters bound to raw `fastapi.Query` sentinel objects, and the
   pre-existing `test_agent_task_crud_retains_create_and_latest_update_runs` caught it immediately:
   `sqlalchemy.exc.ProgrammingError: Error binding parameter 2: type 'Query' is not supported`. Fixed
   by forwarding `spec_document_id=None, exclude_archived_completed=False` explicitly — also the
   *correct* value for this route on its own merits, since proposal.md's non-goals already commit to
   this tool seeing every task unchanged.
3. **`projectScopedApiContract.test.tsx`, not caught by any round.** Two of its behavioral tests
   assert `client.getQueryData(['project', 'proj-a', 'tasks'])` — the exact pre-D2 query key. Once
   `useTasks()`'s key gained the trailing `{ excludeArchivedCompleted }` object, that exact-match
   `getQueryData` call returned `undefined` (`invalidateQueries`'s prefix match, which D2's own
   reasoning checked, is not the same operation). Fixed by updating both assertions to the new key
   shape; ran the file in isolation before and after to confirm.
4. **Live-verification hit a stale trial Hub process, not a code defect.** The first live-verification
   pass restarted the trial Hub, got `/health: ok`, and still found `task-a` present in the
   `exclude_archived_completed=true` result — looked like a fourth real bug until `Get-NetTCPConnection`
   showed the process actually bound to `:8010` had a `CreationDate` of 23:08 that night, before this
   iteration's commits: a leftover Hub process from N2's own session, still alive, still answering
   `/health` correctly. The new `uvicorn` invocation had silently failed to bind the already-taken
   port and exited — `/health` was answering from **old code** the whole time. Killed the stale
   process (confirmed the port free via `Get-NetTCPConnection` before restarting, not assumed), started
   clean, re-ran: 19/19 checks passed. Recorded in tasks.md 4.1 so the next person restarting this Hub
   checks the owning process's actual start time against `/health` succeeding, not just the response
   itself — a 200 from `/health` proves *a* Hub is up, not *which* commit it is running.

**Verification, all green, both before and after the D6 fix (the first backend run was red, exactly
once, on the bug D6 records):**
- `pytest hub/tests/ -n 8`: 2093 passed, 11 skipped (baseline 2089/11 — +4 new `test_tasks.py`
  functions). One `test_agent_trigger.py::test_spawn_failure_broadcasts_run_failed_event` failure
  under `-n 8` did not reproduce standalone or on a clean second full run — xdist flakiness, not
  caused by this change.
- `pytest tests/ -n 4`: 362 passed, 3 skipped — unchanged.
- `npm test`: 943/943 (baseline 934 — +9: 4 in new `tasksApi.test.tsx`, 4 in new
  `specDocumentTasksLink.test.tsx`, 1 new case in `tasksBoardFilter.test.tsx`).
- `npm run lint`, `npx tsc --noEmit`: clean.
- `ruff check hub/ src/`: clean after `--fix` resolved one import-order violation `tasks.py`'s new
  `spec_lifecycle` import introduced. `black --check`: clean after reformatting `test_tasks.py` once.
- `npx openspec validate --changes --strict`: 19/19. `--specs --strict`: 30/30.
- **Driven against the running Hub** (restarted, discovered stale per finding 4 above, killed,
  restarted clean, confirmed `/health: ok` with no `ui_stale` against the genuinely new process):
  all of section 4's checks, live, against `proj-5e960453` (this repo's own trial project) with a
  directly-minted run credential (same technique N2 used) — created a document declaring two tasks,
  approved it (materialising both), moved one to `rejected` and the other to `in_progress`, archived
  the document, confirmed `exclude_archived_completed=true` hides exactly the rejected one,
  `spec_document_id=<doc>` still shows both, the unfiltered default still shows both, and — the D7
  regression's actual live surface — `GET /api/v1/agent-actions/tasks` returns 200 rather than 500.
  19/19 checks in the verification script itself.
- **UI bundle**: built and stamped before commit, committed, then re-stamped and committed again
  (N2's own Entry 4 finding — the fingerprint folds in `git status --porcelain`, so a pre-commit stamp
  never matches the post-commit clean tree).

**Teardown, not left in place.** The live verification's own script has one wrong column name on its
first teardown attempt (`task_requirement_references` is keyed by `task_id`, not the guessed
`requirement_key`) — caught by the raised `OperationalError`, and since it errored before `commit()`
nothing had actually been deleted, so nothing was lost. Fixed and re-run cleanly. The on-disk
`spec/n2b-live-verify/spec.html` the verification wrote (this repo is the trial project's own working
directory) is not something the DB-only teardown touches — removed by hand; `git status` confirmed
clean afterward. The verification script itself, `testbed/scratch/n2b_live_verify.py`, is gitignored
by `testbed/.gitignore` and left in place rather than deleted — reusable for the next person who
needs to drive this same document/task flow live.

Committed as `b4b31d7` (implementation) and `20e963e` (post-commit bundle re-stamp), both on this
branch.

`current` advances to `N3-job-system`. Per `STATE.json`'s queue, N3 is the keystone remaining item:
many named loops as a first-class Hub concept, composing with existing primitives (questions, runs,
tasks, agents/runners/charters) rather than reinventing them, modelled on `STATE.json`'s own proven
shape but explicitly NOT a port of it. Two operator notes bind its shape (composition over
reinvention; many named loops at different cadences, never a singleton) — both already recorded in
`decisions_for_user` and `queue[3].detail`; read them before drafting rather than re-deriving. This is
a keystone item and, per `spec_round_protocol`, gets its own three-round cap starting fresh: author,
cold review, cold review/cap. `next_action` set to N3 round 1 (author proposal.md/design.md/tasks.md
and a spec delta in `openspec/changes/`, scope-ceiling reminder: model + API + visibility ONLY, the
Hub actually spawning/re-entering iterations is explicitly out of scope for tonight).

## Entry 8 — N3 round 1 (AUTHOR): `openspec/changes/2026-08-16-many-named-loops`

Wrote `proposal.md`, `design.md`, `tasks.md`, and two spec deltas (new capability `agent-loops`;
`task-lifecycle-governance` modified) for the job-system keystone item. Spec only — no code this
iteration, per the three-round protocol's own discipline (N2 and N2b both authored round 1 before
touching code).

**Grounded in the running code, not the abstract, before drafting.** Read `hub/hub/db/models.py`'s
`AIJob`/`JobRun` (1123/1160) and `hub/hub/scheduler.py::_do_fire_job` end to end first. Two things
that changed the shape of the proposal from what `queue[3].detail` assumed:

1. **`AIJob` already spawns real work.** `queue[3].detail`'s framing — "everything that makes the
   overnight loop actually work lives in `STATE.json` on disk, outside the product" — is true of the
   *semantics* but not of execution: `_do_fire_job` already creates a `Conversation`, enqueues a real
   `InboundQueueEntry`, and calls `schedule_agent` — no synthetic message, no watchdog, the direct
   spawn path task 3.10 (an earlier change) already built. This mattered for the scope-ceiling
   reading: "the Hub actually spawning or re-entering iterations is explicitly out of scope" cannot
   mean "don't let jobs fire" (they already do, unconditionally); it has to mean "don't build the
   thing that decides to fire when the existing cron/manual trigger would not have, and don't build
   the thing that picks the next queue item for an agent." Design D4's stop-condition check is
   written to hold exactly that line: it only ever *skips* a fire the scheduler was already about to
   make, never causes one.
2. **A real, present-tense traceability gap, not a hypothetical one.** `JobRun` records
   `session_id`, but `scheduler.py:283` only sets it from `job.last_session_id` when resuming — a
   fresh (`session_mode="new"`) firing's `JobRun.session_id` is `None` forever, even though the
   function builds a `Conversation` object two lines later and never attaches its id to the row it
   writes. Confirmed by reading the function, not assumed: nothing else in `hub/hub/*.py` writes
   `JobRun.conversation_id` because the column does not exist yet. This became design D3 — the
   proposal's own single highest-value line, a one-line fix, and the fact that makes every other
   piece of visibility possible (open questions per loop, a firing's own output log) a join instead
   of new storage.

**Composition, checked against each of the operator's named primitives, not asserted:**
- Iteration → `JobRun`, already exists, gains one column (`conversation_id`), not a new table.
- Decisions for the operator → the existing `Question`/`ask_user` machinery, reached via
  `conversation_id`, no new column on `Question` at all.
- Queue item → `Task`, gains one column (`loop_id`), exactly mirroring `spec_document_id`'s own
  established shape (nullable, indexed, deliberately no FK — the SQLite undroppable-CHECK-column trap
  `Task.spec_document_id`'s own comment and `0074`'s comment both document).
- Narrative log → `AgentOutput` + the activity timeline, already keyed on `conversation_id` — reached
  the same way, not rebuilt.
- A loop's operator → deliberately **not** touched. `AIJob.agent` already names who runs it; nothing
  in this proposal adds a second notion of "whose loop is this."
- The *task-list scoping mechanism itself* — `GET /tasks?loop_id=` is a third `elif` arm beside the
  `spec_document_id`/`exclude_archived_completed` pair `2026-08-16-the-board-scoped-by-document`
  shipped earlier tonight (N2b). Literally the second caller N2b's own design predicted having.

**Pre-authorised default honoured explicitly**: new table (`loops`), not new columns on `AIJob`/
`JobRun` beyond the one traceability column D3 adds — and D1 states in writing why `JobRun.
conversation_id` and `Task.loop_id` are *not* overloading in the sense the default warns against
(they are the join keys a table naturally needs to relate to another, not a redefinition of what
`AIJob`/`JobRun`/`Task` already mean).

**Rejected a `Loop.status` enum** (design D1) in favour of reading "is this loop firing" off the
`AIJob.enabled` flag that already exists, with a new `stop_reason` (nullable) distinguishing a loop
that stopped itself from one an operator merely paused with the existing, unchanged `toggle_job`
path. One boolean field the Hub already had, plus one nullable reason field, instead of a second
status vocabulary that could disagree with the first.

**Rejected a `GET /loops` router** (design D5) in favour of embedding an optional `loop` object on
the existing `JobResponse` — a loop has no field of its own the underlying job does not already
carry (no independent cron, message, or agent), so a separate endpoint would only mean stitching two
responses together for a relationship that is always 1:1. "Many named loops" is answered by the
existing Jobs page listing many jobs, some of which now carry a loop block.

**Explicit non-goal, stated in both proposal.md and design D7, because it is the item's own trickiest
judgment call and the one round 2's cold review should press hardest on**: nothing here lets a loop
choose its own next queue item, mark one done and start the next, or resume a conversation on the
Hub's initiative. The stop-condition check (D4) is the only place this proposal's code runs on its
own — and it can only ever *prevent* an already-scheduled fire, never cause one. Composing this into
something that actually drives itself is named as future work, not folded in quietly.

`npx openspec validate --changes --strict`: 20/20 (19 prior + this one). No code touched, so the
green baseline from `20e963e` (`pytest hub/tests -n 8` 2093/11, `pytest tests/ -n 4` 362/3, `npm
test` 943/943) is untouched and not re-run this iteration — nothing changed that those suites cover.

`next_action` set to N3 round 2 (cold review — a fresh reading against the actual `AIJob`/`JobRun`/
`Task`/scheduler code this iteration cited, checking in particular: does D4's skip-check really only
ever prevent a fire and never cause one; does the `elif` ordering in D2 actually compose with the
`spec_document_id`/`exclude_archived_completed` pair from N2b without a fourth interaction case
nobody considered; is `list_jobs`' N+1 risk from task 4.4 real and, if so, is round 1 right to leave
it as a task-level warning rather than a design decision).

## Entry 9 — N3 round 2 (REVIEWER): cold review against the real code, three findings fixed, approved early

**2026-08-17T00:54:47+01:00.** Round 1 (Entry 8) authored `2026-08-16-many-named-loops`. This
iteration is the cold review `spec_round_protocol` calls for: a fresh reading against the actual
`AIJob`/`JobRun`/`Task`/`scheduler.py`/`tasks.py`/`jobs.py`/`models.py` code the proposal cites, not
a re-read of round 1's own reasoning. Read every artifact top to bottom, then verified each concrete
claim against the live source rather than trusting the prose:

- **D3's traceability gap is real.** `scheduler.py:308-316` constructs `JobRun(...)` with no
  `conversation_id` field, even though `conversation` is already a live local variable two blocks
  above (`:292-298`). Confirmed, not re-derived from round 1's say-so.
- **D4's "only ever prevents a fire, never causes one" claim holds.** Read `_do_fire_job` end to end:
  `job.last_run`/`run_count`/`next_run` are updated unconditionally (`:271-281`) *before* the existing
  `_job_agent_skip_reason` check (`:322`), and the queue entry that actually starts a conversation
  (`:344` `new_entry(...)`) is created only *after* that check passes — the proposed
  `_loop_stop_reason` check slots into the identical position, so it can only ever suppress the
  `entry = new_entry(...)` call that follows it, never trigger one on its own. Also confirms task
  3.4's question (does skip-path bookkeeping still run) is already answered by the code: yes, stats
  update before any skip check, existing or proposed.
- **The `elif` composition with N2b's `spec_document_id`/`exclude_archived_completed` pair is
  genuinely safe** — `tasks.py:421-439` today is exactly `if spec_document_id: ... elif
  exclude_archived_completed: ...`, two branches, mutually exclusive by construction. Adding `loop_id`
  as a second `elif` makes three, still mutually exclusive, no fourth interaction case anyone missed.
  Design.md's own prose called this a "fourth `elif` arm," which was simply a miscount (task-level
  wording in tasks.md 4.5 already said "third" correctly) — fixed in place, cosmetic, not a design
  problem.
- **`hub/hub/api/v1/agent_actions.py`'s `list_shared_tasks`** (the direct-call site tasks.md 4.5
  warns about) is confirmed real: it calls the tasks module with `spec_document_id=None,
  exclude_archived_completed=False` hardcoded — exactly the D7-regression shape from
  `-the-board-scoped-by-document` that already bit this session once tonight. Already correctly
  flagged in tasks.md; nothing to add.
- **`Question.conversation_id`/`declined` fields**, D5's `open_questions` query depends on both —
  confirmed present (`models.py:875`, `:894`) and indexed.

**Two findings elevated beyond cosmetic, both fixed in `design.md`/`tasks.md` this iteration rather
than deferred to a round 3:**

1. **`list_jobs`'s N+1 risk is worse than the task-level note implied.** `jobs.py:178-191` shows
   `list_jobs` today runs **exactly one query, full stop** — it does not even fetch history the way
   `get_job` does (`get_job` adds one). Naively computing `queue`/`current_task`/`open_questions` per
   job inside a loop would turn a single-query endpoint into `1 + 4×L` queries where `L` grows with
   exactly the thing this whole change exists to support ("many named loops"). Added **design D7**:
   four fixed batch queries (`loops WHERE job_id IN (...)`, a grouped `tasks` count, a single ordered
   `tasks` fetch for `current_task` picked in Python per loop, a grouped `questions JOIN job_runs`
   count) computed once over the whole page, with `get_job` reusing the same batch functions on a
   one-element id list rather than a separate single-job path. Renumbered the old D7 ("what this
   leaves for a future change") to D8 to keep the sequence intact. `tasks.md` 4.4 now points at D7
   instead of a loose "watch the shape" warning.
2. **The `purpose is not None` opt-in boundary (D6) is unambiguous server-side but not
   client-side.** A controlled React form whose textarea state starts at `''` and always serialises
   `purpose: ""` in the request body — rather than omitting the field when the collapsed loop section
   is untouched — would opt every job into being a loop regardless of operator intent, because the
   server cannot distinguish "sent empty on purpose" from "sent empty because the form always sends
   it." Added an explicit note to tasks.md 5.1 naming this as a real client-side requirement, not
   merely a server-side rule to restate.

**No fundamental architectural objection survived cold reading.** The composition claims (`Loop`↔
`AIJob` FK, `Task.loop_id`/`JobRun.conversation_id` as join keys not new storage, no `Loop.status`
enum, no `GET /loops` router) all check out against the real schema and call sites, not just round
1's own prose. Per `spec_round_protocol`'s "or on earlier reviewer approval" clause: **this round
approves early**, having fixed what it found rather than deferring to a round 3 that would find the
same two things again. `npx openspec validate 2026-08-16-many-named-loops --strict`: valid, both
before and after the amendments. No code touched; green baseline from `20e963e` untouched.

`next_action` set to implementation, starting with tasks.md sections 1-3 (migration `0075`, models,
scheduler) — the layers everything else depends on — leaving API/UI/tests for the iteration(s) after,
the same incremental pacing N2/N2b used rather than attempting the whole tasks.md list in one turn.

## Entry 10 — N3 implementation slice 1: migration 0075, models, scheduler wiring (sections 1-3)

**2026-08-17T01:25:57+01:00.** Picked up mid-flight: the previous iteration (heartbeat taken over at
01:04:08 per driver.log) had already written the full implementation for tasks.md sections 1-3 —
migration `0075_add_loops_and_traceability.py`, the `Loop` model plus `Task.loop_id`/
`JobRun.conversation_id` columns, and the scheduler's `_loop_stop_reason` check and
`conversation_id` wiring in `_do_fire_job` — but exited without committing, leaving the tree dirty
(driver.log's own note for that firing: "Still running. I'll wait for the completion notification,"
i.e. it treated an in-process implementation as a background task and returned before it actually
finished landing the commit). This iteration is a genuine continuation, not a redo: read every
diff against the actual code before trusting it, then verified rather than re-implemented.

**What was already there, checked line by line against the design:**
- `hub/hub/migrations/versions/0075_add_loops_and_traceability.py` — three additive changes (new
  `loops` table, `tasks.loop_id`, `job_runs.conversation_id`), each guarded for a missing table the
  way `0071`/`0073` do, matching design and tasks.md 1.1/1.2 exactly. `downgrade()` reverses all
  three in dependency order.
- `hub/hub/db/models.py` — `Loop` class placed after `JobRun`, matching design D1: `job_id` unique
  FK with `ondelete="CASCADE"`, `purpose` non-null defaulting `""`, `stop_at`/`stop_when_queue_empties`/
  `stop_reason`/`stopped_at`, no `status` enum (round 2's rejection honoured). `Task.loop_id` beside
  `spec_document_id` with the same "deliberately not a ForeignKey" comment reasoning. `JobRun.
  conversation_id` beside `session_id` with a comment distinguishing resume-input from what-actually-
  fired.
- `hub/hub/scheduler.py` — `_loop_stop_reason(session, job)` checks `stop_at`/`stop_when_queue_empties`
  against `Task.loop_id`-scoped non-terminal counts (using `TERMINAL_FOR_BINDING`, the same terminal
  set the rest of the codebase already uses); wired into `_do_fire_job` after the existing
  `_job_agent_skip_reason` check and before `new_entry(...)`, so it can only ever suppress a fire,
  never cause one — matches round 2's D4 verification exactly. On stop: writes the `JobRun` as
  `skipped` with the reason, stamps `loop.stop_reason`/`stopped_at`, sets `job.enabled = False`,
  calls `self.remove_job(job.id)` (confirmed the right call — `_do_fire_job` is a `JobScheduler`
  method with its own wrapper, not the module-level `get_scheduler()` path), persists `job_run_skipped`
  and a new `loop_stopped` event, and broadcasts `loop_stopped` over SSE. `conversation_id=
  conversation.id` added to the `JobRun(...)` construction (task 3.1).
- Test files: `test_migrations.py`/`test_project_persistence.py` head assertions bumped `0074`→`0075`
  (11 + 1 occurrences, matching the recount tasks.md 6.1 records, including two stale f-string
  messages a naive replace would have missed). `test_project_delete_api.py` adds `Loop` to the
  project-scoped-tables sweep test and seeds one row — checked this is actually exercised by
  `project_lifecycle.py`'s generic `Base.metadata`-introspecting delete (`_project_scoped_tables()`,
  `project_lifecycle.py:184`), not a hand-maintained table list, so `Loop` carrying `project_id` was
  already swept correctly before this test even existed; the test documents that fact rather than
  fixing a gap.

**Verified rather than trusted:**
- `pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py
  hub/tests/test_project_delete_api.py -q` → 63 passed, 1 skipped.
- `pytest hub/tests/ -n 8 -q` → **2093 passed, 11 skipped** — exact match to the `20e963e` baseline,
  confirming the new migration/model/scheduler code introduced no regression anywhere else in the
  suite.
- `pytest tests/ -n 4 -q` → **362 passed, 3 skipped** — exact match to baseline (untouched by this
  slice, run anyway per the standing discipline of never trusting a green claim without re-running).
- `npx openspec validate --changes --strict` → 20/20 clean.
- `ruff check` and `black --check` on every touched Python file → clean.
- Did not re-run the alembic upgrade/downgrade/upgrade round-trip tasks.md 1.3 already recorded as
  verified live by the prior iteration (`%TEMP%\aw_0075_test.db`) — `test_alembic_upgrade_head_fresh_file_db`
  and the guarded-migration tests exercise the same upgrade path end to end and passed, which is
  sufficient re-confirmation without repeating a manual scratch-file run.

**Committed as-is, no code changes needed.** tasks.md sections 1-3 plus the 6.1 slice of section 6
were already correctly implemented; this iteration's job was verification and landing, not authorship.
Sections 4-9 (API, UI, remaining tests, live Hub verification, human-only, user test guide) remain.

`next_action` set to tasks.md section 4 (API: `JobCreate`/`JobUpdate` schema fields, `create_job`/
`update_job` Loop-row logic per D6, `LoopSummary`/`JobResponse.loop`, the D7 batch-query shape for
`list_jobs`/`get_job`, and `list_tasks`'s `loop_id` filter including the `agent_actions.py` direct-
call-site fix task 4.5 names). Section 4 has no UI dependency and no migration dependency beyond what
just landed, so it is the next self-contained slice.

## Entry 11 — N3 implementation slice 2: the API layer (tasks.md section 4) + a real bug found and fixed

**2026-08-17T01:48:16+01:00.** Implemented tasks.md section 4 in full: `JobCreate`/`JobUpdate` gain
the loop fields, `create_job`/`update_job` apply design D6's opt-in rule, `LoopSummary` +
`JobResponse.loop` per D5, `list_jobs`/`get_job` compute it via a new `_batch_loop_summaries` helper
implementing D7's four fixed queries, and `list_tasks` gains `loop_id` with the `agent_actions.py`
direct-call-site forward (task 4.5).

**Schema (`hub/hub/schemas/jobs.py`):** `JobCreate` gains `purpose: Optional[str]` (max 4000),
`stop_at: Optional[datetime]`, `stop_when_queue_empties: bool = False`. `JobUpdate` gains the same
three as `Optional` (including `stop_when_queue_empties: Optional[bool] = None` — deliberately not a
bare `bool` default, since an update must be able to tell "not supplied" from "explicitly false")
plus `stop_reason: Optional[str]`. New `LoopSummary` matches design D5 exactly; `JobResponse.loop:
Optional[LoopSummary] = None`.

**API (`hub/hub/api/v1/jobs.py`):**
- `_loop_opts_in(purpose, stop_at, stop_when_queue_empties)` — the one-place statement of D6's "at
  least one field, and a bare `False` doesn't count" rule, used by both `create_job` and `update_job`
  rather than two independent copies.
- `_batch_loop_summaries(session, job_ids)` — D7's four queries: `Loop` rows by `job_id IN (...)`;
  grouped `(loop_id, status) -> count` for the queue; one ordered `Task` fetch across all loops with
  `current_task` picked per loop in Python (first row per `loop_id`, since the ORDER BY already puts
  an in-progress/blocked row before a pending one); and open-question counts via a `DISTINCT
  (job_id, conversation_id)` subquery joined to `Question` — the DISTINCT matters: a resume-mode job
  that fired twice on the same conversation would otherwise join the same question row once per
  firing and overcount, which the design's own prose (`IN (SELECT DISTINCT conversation_id ...)`)
  was written to avoid and a naive `JobRun JOIN Question GROUP BY job_id` would not have. `get_job`
  and `list_jobs` both call this with their respective id lists — no separate single-job path.
- `create_job`: creates a `Loop` row after the `AIJob` commits, iff `_loop_opts_in`; response carries
  the fresh summary (`queue={}`, `current_task=None`, `open_questions=0` — correct, since the job
  cannot have fired yet).
- `update_job`: computes `loop_fields_supplied` first (any of the four), then — if the job has no
  `Loop` row — either 400s (`_loop_opts_in` false, matching the exact design wording) or creates one
  (`_loop_opts_in` true, the first-time-PATCH-opt-in case task 4.3 names). Placed *before* the
  existing name/message/cron/session_mode/enabled mutations so a rejected loop update never leaves
  unrelated fields half-applied in the session (nothing was committed yet either way, but ordering
  makes the intent explicit rather than accidental).
- `get_job`'s hand-built `job_dict` gains a `"loop"` key from the same batch helper.

**Tasks (`hub/hub/api/v1/tasks.py`, `hub/hub/api/v1/agent_actions.py`):** `list_tasks` gains
`loop_id: Optional[str] = Query(None)` as a third `elif` arm beside `spec_document_id`/
`exclude_archived_completed` (confirmed unchanged two-arm shape before editing, per the standing
instruction — it still was). `agent_actions.list_shared_tasks` forwards `loop_id=None` explicitly at
its direct call site — this is precisely the shape of regression `-the-board-scoped-by-document` hit
once already tonight (a direct function call not forwarding a new parameter), so it was not skipped.

**A real bug found by writing task 6.3's tests, not assumed away:** `_loop_stop_reason` (landed in
Entry 10) compared `datetime.now(timezone.utc)` against `loop.stop_at` read back from SQLite. SQLite
round-trips `DateTime(timezone=True)` as **naive** — the exact trap `hub/hub/agent_status.py`'s
`heartbeat_is_stale` already has a guard for (`observed_at.tzinfo is None: observed_at =
observed_at.replace(tzinfo=timezone.utc)`), which `_loop_stop_reason` did not repeat. The comparison
raised `TypeError: can't compare offset-naive and offset-aware datetimes`, caught by `_do_fire_job`'s
outer `try/except`, which recorded the fire as a plain **failure** — never reaching the loop-stop
branch, never disabling the job, never setting `loop.stop_reason`. A loop's `stop_at` would have
silently never stopped anything in the real product; only exercising the path end-to-end (not just
reading the code) surfaced it. Fixed by restoring UTC tzinfo before comparing, with a comment naming
`agent_status.py` as the precedent so a future reader does not have to rediscover why. Test
`test_loop_with_past_stop_at_skips_the_fire_and_disables_the_job` failed against the unfixed code and
passes now — confirmed by actually watching it fail first, not written after the fix.

**Tests added, all passing (section 6.2-6.4):**
- `hub/tests/test_jobs.py` (+5): plain job carries `loop: null` across create/get/list; `purpose`
  alone opts a job into a loop; PATCHing a loop field onto a plain job is 400; PATCH opts a plain job
  into a loop for the first time; PATCH updates an existing loop's `purpose` in place.
- `hub/tests/test_tasks.py` (+1): `GET /tasks?loop_id=X` scopes to exactly that loop's tasks
  regardless of status, and the `agent-actions` router's own `list_tasks` call site still returns 200
  and is unaffected by loop scoping it was never asked for (task 6.4's own regression-shape check).
- `hub/tests/test_scheduler.py` (+3): a past `stop_at` skips the fire, disables the job, stamps
  `loop.stop_reason`/`stopped_at`, and a second manual attempt still refuses;
  `stop_when_queue_empties=True` with zero non-terminal tasks stops the same way; the same flag with
  one `pending` task naming the loop does **not** stop — the fire proceeds through the full direct-
  execution path (mocked PTY spawn, same pattern `test_fired_job_creates_a_run_via_direct_execution`
  already uses) and `JobRun.conversation_id` is populated.

**Verified, not trusted:**
- `pytest hub/tests/test_scheduler.py hub/tests/test_jobs.py hub/tests/test_jobs_crud.py
  hub/tests/test_tasks.py hub/tests/test_agent_actions_coordination.py
  hub/tests/test_agent_actions_governed.py -q` → 81 passed, 3 skipped, before the full-suite run.
- `pytest hub/tests/ -n 8 -q` → **2102 passed, 11 skipped** — exactly `20e963e`'s 2093 plus the 9
  tests added this iteration (5+1+3), no other change anywhere in the suite.
- `pytest tests/ -n 4 -q` → **362 passed, 3 skipped** — exact match to baseline, untouched by this
  slice.
- `ruff check hub/ src/` and `black --check` (whole tree, not just touched files) → clean.
- `npx openspec validate --changes --strict` → 20/20. `--specs --strict` → 30/30.
- Did not yet run `hub/ui` checks (`npm test`/`lint`/`tsc`) — no UI file touched this slice; task 6.7
  explicitly deferred to section 5, recorded as such in tasks.md rather than ticked early.

tasks.md: section 4 (4.1-4.5) and the 6.2/6.3/6.4/6.6/6.8/6.9 slice of section 6 checked off, with
6.6's counts and 6.7's deferral recorded inline. Sections 5 (UI), 7 (driven-against-the-running-Hub),
8 (human-only), 9 (user test guide) remain.

`next_action` set to tasks.md section 5 (UI): `hub/ui/src/api/jobs.ts` (`Job`/`JobCreate`/
`JobUpdate` types, task 5.1's "omit unless the loop section was touched" client-side rule — a
controlled form must not serialise `purpose: ""` just because the field exists, or every job becomes
a loop the instant the form renders it), `hub/ui/src/api/tasks.ts` (`useTasks({ loopId })`, task 5.2 —
check whether that alone covers `JobCard`'s need before adding a second hook), `JobForm.tsx`'s
collapsed "Make this a loop" section (5.3), `JobCard.tsx`'s loop block (5.4), then the mandatory
`npm run build && python scripts/refresh_ui_bundle.py` **twice** (5.5) — once before commit, once
after, since the bundle fingerprint folds in `git status --porcelain` (the same two-pass discipline
N2 and N2b both already hit). Section 5 depends on section 4's response shape, which is now stable
and committed. Section 7 (driven against the running Hub) still waits until section 5 lands, per
tasks.md's own note — no point restarting the trial Hub before there's a UI to exercise it with.

## Entry 12 — N3 implementation slice 3: the UI layer (tasks.md section 5) + a real design gap closed

**2026-08-17T02:19:42+01:00.** Implemented tasks.md section 5 in full — `many-named-loops` now has a
working UI: creating a job can opt it into being a loop, and a loop's card shows its purpose, stop
condition, queue and current item.

**API (`hub/ui/src/api/jobs.ts`, `hub/ui/src/api/tasks.ts`):** `Job` gains `loop?: LoopSummary | null`;
`JobCreate`/`JobUpdate` gain the three/four loop fields, all optional — `JobForm.tsx` only spreads
them into the submit payload when the collapsed section was actually opened (`loopEnabled`), never as
`purpose: ''`/`stop_when_queue_empties: false` defaults, matching design D6's server-side "`purpose is
not None`" opt-in rule from the client side too. `useTasks()` gains `loopId?: string`, read the same
way `excludeArchivedCompleted` already is; the two are mutually exclusive in the querystring builder
(`loopId` wins if both are somehow passed), matching the server's `if/elif` chain exactly — confirmed
`useTasks({ loopId })` alone covers `JobCard`'s need, so no second `useLoopTasks` hook was added.

**UI (`JobForm.tsx`, `JobCard.tsx`, `JobsPage.tsx`, `App.tsx`):** `JobForm` gets a collapsed-by-default
"Make this a loop" toggle revealing a purpose textarea, a `datetime-local` stop-at input, and a
stop-when-queue-empties checkbox. `JobCard` gains a new `LoopBlock` sub-component, rendered only when
`job.loop` is present — purpose, an Active/Stopped badge, the stop reason when stopped, queue counts
per status, the current item (title + status), and an open-questions count. `LoopBlock` owns its own
`useTasks({ loopId })` call so a plain job never triggers that fetch at all. The current-item line is
the click target: clicking it calls `onOpenTasks` with every task id the loop's own `useTasks` fetch
returned — the identical `setActiveTaskIds` cross-tab mechanism `SpecDocumentTasksLink` already proved
live for the spec-coverage bar. `onOpenTasks` is threaded `App.tsx` (where it does
`setActiveTaskIds` + `navigateTo(..., 'tasks')`, byte-for-byte the same shape as the existing spec-
coverage wiring a few lines above it) → `JobsPage.tsx` → `JobCard.tsx`.

**A real design gap found while wiring the click-through, not assumed away:** `LoopSummary` — in both
`hub/hub/schemas/jobs.py` and its frontend mirror — never carried the `Loop` row's own `id`. Design D2
scopes `GET /tasks?loop_id=` by `Task.loop_id`, which stores the *loop's* id, not the *job's* — the two
are different values (`Loop.job_id` is a separate unique column). Without `loop.id` in the response, no
caller anywhere could ever construct a working `?loop_id=` query; the "current item, linking into the
task board scoped to `?loop_id=`" line in tasks.md 5.4 was, as written, unimplementable. Added `id: str`
to `LoopSummary` and populated it at both construction sites in `hub/hub/api/v1/jobs.py`
(`_batch_loop_summaries`, used by `get_job`/`list_jobs`/`update_job`, and `create_job`'s zero-history
construction) — checked first that no test constructs a bare `LoopSummary(...)` or asserts on the
response dict missing `id` (none do; existing assertions only check `loop["purpose"]`), so this was a
strict addition with no call site to update elsewhere.

**Tests added (task 6.5), all passing:**
- `hub/ui/src/__tests__/jobCard.test.tsx` (new, 4 cases): a plain job shows no loop block even
  expanded; a loop with purpose/queue/current-item/open-questions renders all of it and an "Active"
  badge scoped inside the block (disambiguated from the job header's own "Active"/"Paused" badge via
  `within`); a stopped loop shows "Stopped" and its reason and "No current item"; clicking the current
  item calls `onOpenTasks` with every task id the mocked `useTasks({ loopId })` returned, and is not
  clickable at all when `onOpenTasks` is omitted.
- `hub/ui/src/__tests__/tasksApi.test.tsx` (+1 case): `useTasks({ loopId, excludeArchivedCompleted })`
  requests `?loop_id=<id>` only — confirms the priority ordering, not just that `loopId` works alone.

**Verified, not trusted:**
- `npx tsc --noEmit` → clean (caught the missing frontend `LoopSummary.id` immediately — the JobCard
  code referencing `loop.id` failed to compile before the backend fix was even written, which is what
  surfaced the gap in the first place, before any test did).
- `npx vitest run` on the two new/changed test files → 9/9 passed, before the full suite run.
- `npm test` (full suite) → **948 passed** — the 943 baseline plus exactly the 5 new cases (4 + 1),
  no other change anywhere. `npm run lint` → clean. `npm run build` → clean (one pre-existing >500kB
  chunk-size warning, unrelated to this slice).
- `pytest hub/tests/test_jobs.py hub/tests/test_scheduler.py hub/tests/test_jobs_crud.py
  hub/tests/test_tasks.py -q` → 60 passed, 3 skipped, before the full-suite run (confirms the
  `LoopSummary.id` addition broke nothing in the job/loop/task test files specifically).
- `pytest hub/tests/ -n 8 -q` → run **twice**. First run: 2101 passed, 1 failed
  (`test_agent_trigger.py::test_spawn_failure_marks_run_failed`), 11 skipped — reran that one test
  standalone (`pytest tests/test_agent_trigger.py::test_spawn_failure_marks_run_failed -q`) and it
  passed, confirming the exact known `-n 8` xdist flake `verified_green_at_20e963e` already named
  rather than a regression from this slice's changes. Second full run, started in the background while
  other verification proceeded: **2102 passed, 11 skipped, zero failures** — the flake did not recur,
  and the count exactly matches the unchanged baseline (this slice added no new Python test).
- `pytest tests/ -n 4 -q` → **362 passed, 3 skipped** — exact match, untouched by this slice.
- `ruff check hub/ src/` and `black --check` (whole tree) → clean.
- `npx openspec validate --changes --strict` → 20/20. `--specs --strict` → 30/30.

**The two-pass bundle-refresh discipline, followed exactly as tasks.md 5.5 specifies:** built and
refreshed `hub/hub/static/ui` once before staging (`8814d1d`), then, per the standing rule this session
already hit twice (N2, N2b) — the fingerprint folds in `git status --porcelain`, so a pre-commit
refresh always stamps a dirty-tree suffix a post-commit clean tree can't reproduce — rebuilt and
refreshed a second time against the clean, committed tree. Confirmed via `git status` that only
`ui-build-stamp.json` changed the second time (same asset content hash, `index-BqLeC6Wd.js`), committed
separately as `619fd5a`.

tasks.md: section 5 (5.1-5.5) and 6.5/6.6/6.7 checked off, all with their verification recorded inline.
Sections 1-6 of `many-named-loops` are now fully implemented and green. Remaining: section 7 (driven
against the running trial Hub — not yet restarted onto this commit), section 8 (human-only, cannot be
completed unattended — will be recorded as findable-but-unverified rather than ticked), section 9
(user test guide — tasks.md already has a draft; needs checking against what actually got built rather
than assumed correct).

`next_action` set to tasks.md section 7: restart the trial Hub onto `619fd5a` (checking the owning
process's actual `CreationDate`, not just `/health`, per N2b's standing lesson), then drive 7.1-7.4 —
a `stop_when_queue_empties` loop with an empty queue skipping its fire and disabling itself; a second
loop with one task naming it firing normally and recording `JobRun.conversation_id`; `GET /tasks?loop_id=`
and `GET /jobs/{id}`'s `loop.queue`/`loop.current_task` both reflecting the seeded task; then a full
teardown of every row created, confirmed by `git status` staying clean (this repo is that project's own
working directory, so nothing here should ever go dirty from a live-Hub check). Sections 8 and 9 close
out N3 once section 7 lands. Once N3 is fully closed, `current` advances to `N4-q6-decisions`.

## Entry 13 — N3 closes: section 7 driven live, section 8 recorded, section 9 corrected. No code changed.

**2026-08-17T02:43:11+01:00.** Closed out `many-named-loops` entirely. No source file changed this
iteration — only `openspec/changes/2026-08-16-many-named-loops/tasks.md` (sections 7-9) and this log.
`current` advances to `N4-q6-decisions`.

**Restart, done correctly this time:** the running Hub (PID 22760) predated `619fd5a` by two hours
(`CreationDate` 00:21:54 vs the commit landing ~02:19) — `/health` still reported `{"status":"ok"}`
with no `ui_stale`, exactly the trap N2b's own finding named. Killed it, freed `:8010`, restarted from
`hub/` per the documented command; the new process (PID 32276, `CreationDate` 02:35:09) is after every
commit on this branch.

**Section 7, driven against the live trial Hub** (`testbed/scratch/n3_live_verify.py`, gitignored,
deleted after this run rather than kept — nothing later in the queue needs a job/loop live check the
way N2b's document/task script was kept for reuse): 16/16 assertions passed.
- 7.1: a `stop_when_queue_empties` loop created with zero tasks, fired manually via
  `POST /jobs/{id}/run` → **409** `"loop queue is empty"`. Subsequent `GET` showed `enabled: false`
  and `loop.stop_reason` naming it — exactly design D4's contract.
- 7.2: `TaskCreate` has no client-settable `loop_id` (confirmed by reading the schema before assuming
  a task-creation endpoint would take one) — seeded the task with a direct SQLite insert, the same
  technique N2/N2b used for a run credential. Fired the second loop's job: the manual fire did *not*
  report the empty-queue skip (confirming `_loop_stop_reason` read the seeded task and let the fire
  proceed). `JobRunResponse` and `get_job`'s hand-built history dict both omit `conversation_id`
  (checked, per the task's own instruction, before assuming) — read `job_runs.conversation_id`
  directly instead: populated. Downstream, `trigger_agent_directly` raised its own "no runner bound"
  `TriggerAgentError` for the placeholder agent name (it has no `Agent` row at all), caught by
  `schedule_agent` — confirmed by reading `agent_trigger.py:299` first that this is a graceful,
  no-spawn refusal, not a real process launch, before firing anything against the live instance.
  `conversation_id` was already committed on the `JobRun` row before that call, so the no-runner
  outcome downstream never touched what this task verifies.
- 7.3: `GET /tasks?loop_id=<loop>` returned the seeded task; `GET /jobs/{id}` showed
  `loop.queue.pending >= 1` and `loop.current_task.id` matching it.
- 7.4: the script's own `finally` block deleted every task/loop/job/run row it created;
  `git status --porcelain` empty afterward.

**A real design detail found while writing 7.2's teardown check, not assumed away:** `Conversation`
rows are created *before* either `_job_agent_skip_reason` or `_loop_stop_reason` runs in
`_do_fire_job` (`scheduler.py` lines ~317-334 build/reuse the conversation; both skip checks come
after, and whichever branch commits, commits the already-`session.add`-ed conversation along with
it). Verified directly: firing a brand-new empty-queue loop still leaves behind exactly one
`Conversation` row for that agent, carrying no message. Pre-existing scheduler behaviour — true of
the older agent-skip path too, not introduced by this change — so out of scope to change tonight, but
it made the draft user test guide's step 4 claim ("the fire does not start a new conversation")
false in a way an operator could actually notice. Not queued as a fix (scope ceiling: model + API +
visibility only); recorded in `prep_notes.backlog` below for whoever picks up loop/scheduler work
next.

**Section 8, human-only, left unticked with reasoning recorded inline** (tasks.md now says why): a
live screenshot this iteration — `?project=proj-5e960453&tab=jobs`, card expanded via
`page.get_by_label("Expand job details")` — shows a job named `screenshot-loop-demo` with a green
"Active" loop badge, its purpose text, "Queue: 1 pending: 1", and a blue clickable current-item line
("Fix flaky test_agent_trigger.py (pending)"). Consistent with both 8.1 and 8.2's intent, but "does
this look unchanged" and "does this read as an extension, not a second concept" are judgments an
agent should not tick on the operator's behalf. Screenshot and demo job/task were throwaway
(`testbed/scratch/n3_expand_shot.py`, deleted after use) and torn down via direct SQL delete;
`git status` confirmed clean.

**Section 9, checked against the actual UI, one correction made:** steps 1-2 of the draft guide
matched the screenshot exactly (purpose text, queue count, current-item link) — confirmed rather than
assumed. Step 4's "the fire does not start a new conversation" was corrected to "the agent is not
triggered and no turn is queued for it," per the `Conversation`-row finding above, and a note was
added distinguishing the loop block's own "Active"/"Stopped" badge from the job header's separate
"Active"/"Paused" badge (`JobCard.tsx` lines 26 and 125-127 render two different badges with
overlapping label text — the guide's "the 'Active' badge is gone" was ambiguous about which one).

**Verified, not trusted:** `npx openspec validate --changes --strict` → 20/20, unchanged (only
`tasks.md` checkbox/prose edits, no spec-delta touched). No Python or UI test suite re-run this
iteration — no source file changed, so `verified_green_at_iteration_12_commit_619fd5a` still holds as
the baseline for the next code-touching iteration.

`many-named-loops` is now 33/35 tasks checked (the 2 remaining are 8.1/8.2, explicitly left to the
operator). Left unarchived deliberately — archiving an openspec change is not gated behind the same
operator-only rule as archiving a *spec document* inside the product (that is N2's own concern), but
N6's own scope is "the 13 pre-08-16 changes"; `many-named-loops` is dated 2026-08-16 and completing
tonight, so it is not stale backlog and archiving it is left to whoever runs N6 or the operator,
not automatic on task completion.

`next_action` set to N4-q6-decisions: read the "# Amendments — 2026-08-16, before implementation"
section at the end of `openspec/changes/2026-08-16-one-hub-and-a-window-of-its-own/design.md` and
resolve A1 (verify-only, already fixed), A2 (pywebview forfeits Playwright testability), and A3 (the
instance-profile concept, `cmd_reset`'s blast radius, repo-root shadowing). Run the spec-round
protocol on the revision. **SPEC ONLY — do not implement**; at_cap's approve-and-execute does not
apply to N4 because implementation would need pywebview, which is not authorised.

## Entry 14 — N4 round 1 (authored): all three amendments resolved in Q6's own design.md, proposal.md, spec delta, and tasks.md. No code changed.

**2026-08-17T02:53:43+01:00.** Worked N4-q6-decisions. Read the "# Amendments — 2026-08-16, before
implementation" section at the end of
`openspec/changes/2026-08-16-one-hub-and-a-window-of-its-own/design.md` and resolved all three in
place. Only four files touched, all inside that change directory — `design.md`, `proposal.md`,
`specs/app-lifecycle/spec.md`, `tasks.md` — confirmed via `git status --porcelain` before writing
this entry. No source file changed. `current` stays `N4-q6-decisions`; this is round 1 of the
spec-round protocol on the amended scope (see below for why the round count restarts).

**A1 — verified, not touched.** Re-checked live rather than trusting the amendment's own claim:
`tests/test_cli.py` exists, holds four classes (`TestTransportJsonAtomicWrite`,
`TestSubprocessRunHasTimeout`, `TestTwoInstancesDoNotCollide`, `TestDownloadWithSha256`) — confirmed
by `grep -n "^class Test"`. `tasks.md` section 4 already carries the 2026-08-16 correction
acknowledging the file exists and instructing extension, not creation. This amendment was closed
before this iteration; recorded a verification note in `design.md`'s new "Amendments resolved"
section rather than leaving it silently implied.

**A2 — resolved by making the mitigation a binding constraint, not an argument.** The amendment's own
text already contained the right answer ("that argument only works if the shell stays thin... D3 must
say so") — it just hadn't been written into D3 as a requirement. Added a "Testability, resolved"
paragraph to D3 in `design.md`: `_open_app_window_native` SHALL contain no logic beyond
`webview.create_window`/`webview.start`, the fallback's exception catch, and the already-resolved
URL/title arguments. Backed it with a new task (`tasks.md` 3.5) — a diff-review check, explicitly not
a runtime assertion, since there is no window Playwright can attach to test against. Playwright still
cannot drive the WebView2 window itself; that limitation is named as accepted, not solved, both in
`design.md` and in a new sentence added to `proposal.md`'s Impact section, rather than left implicit.

**A3 — resolved with a new design decision, D6 ("Named profiles"), carried through to an
implementable spec.** This was the larger piece of work — the amendment's own sketch (`--profile
dev --port 8010`, a profile carries the database/PID file/port together, profiles live beside
`data/`) became D6 in `design.md`, grounded against the actual current code (`_hub_pid_file` at
`cli.py:431`, its seven call sites at `cli.py:151,158,431,454,787,799,975`, `cmd_reset` at
`cli.py:966`) rather than restated from the amendment alone — confirmed by reading `cli.py` directly
before writing D6, not assumed from the amendment's table. D6 makes explicit what the amendment left
open only as a sketch: `DATABASE_URL` still wins over `--profile`-computed paths (unchanged rule, now
stated for the profile case too); `cmd_reset --profile <name>` scopes to exactly one profile with no
sweep-all mode; Docker gets no profile-equivalent in this decision (named, deferred); and a short list
of things D6 deliberately does NOT do (profile discovery, a remembered per-profile port, rename/delete
beyond `reset`) so a future round doesn't have to rediscover the boundary. Carried through the whole
document set, not left as a design-only decision the way A2's mitigation could be:
- `proposal.md` — new "What Changes" bullet, a new "Non-Goals" pair (Docker profile-equivalent;
  discovery/port-memory/rename-delete), and a Testability line in Impact for A2.
- `specs/app-lifecycle/spec.md` — new ADDED requirement "A named profile selects a separate,
  deliberate instance" with five scenarios (no-collision, default-profile-unaffected,
  DATABASE_URL-still-wins, reset-scopes-to-one-profile — the last one directly answering A3's
  "reset's blast radius is ambiguous" complaint).
- `tasks.md` — seven new tasks: 1.4-1.7 (flag, PID namespacing, `cmd_reset --profile`, explicit
  non-scope), 2.5-2.8 (collision test extending `TestTwoInstancesDoNotCollide`'s existing pattern,
  default-unaffected regression test, `DATABASE_URL`-wins test, reset-scoping test), 6.6 (human-only:
  run two profiles side by side, confirm independent stop/reset), and a fourth numbered step added to
  the user test guide (section 7) walking an operator through starting a second named instance
  alongside the default one. Task count: 21 → 30. Verified the insertion didn't break numbering —
  `grep -n "^- \[ \] [0-9]"` over the whole file shows a clean, gapless sequence in every section.

**One ordering mistake caught and fixed before commit:** first pass inserted new task 3.5
(A2's thin-shell check) *before* the pre-existing 3.4, out of numeric order in the file body despite
being numbered after it. Caught by re-reading the section after the edit rather than trusting the
edit succeeded silently; swapped the two blocks so 3.4 precedes 3.5 in both number and position.

**Why round 1, not a continuation of the original count:** the round-3 gate that originally shipped
this change (referenced by `spec_round_protocol` in `STATE.json`) evaluated the *original* 21-task
proposal — D6 did not exist yet, so that gate never saw it. Recorded explicitly in `design.md`'s new
"Amendments resolved" section: this revision restarts the round count at 1 for the amended scope,
consistent with the operator's own framing of the amendments needing "a further review round" before
implementation, not framed as continuing the original count toward the cap.

**Verified, not trusted:** `npx openspec validate --changes --strict` → 20/20, including this change
clean. No source file touched, so `verified_green_at_iteration_12_commit_619fd5a` still holds as the
Python/UI baseline — nothing here required re-running either suite.

**Still SPEC ONLY, per `next_action`'s instruction — no pywebview installed, no `--profile` code
written.** `at_cap`'s approve-and-execute does not apply to N4 for the same reason it did not before
this iteration: implementing D3 needs `pywebview`, which `limits` explicitly withholds authorization
for.

`next_action`: round 2 of the spec-round protocol on this amended `one-hub-and-a-window-of-its-own` —
a **cold** review (a fresh read of `design.md`, `proposal.md`, the spec delta, and `tasks.md` as they
now stand, not a continuation of this iteration's own authoring context) checking specifically: (1)
does D6 actually close A3's three named consequences (dual-writer collision, blind `stop`/`status`,
ambiguous `reset` blast radius) — not just gesture at them; (2) is the thin-shell constraint added for
A2 concrete enough that task 3.5 is actually checkable, or does it still leave room for judgment calls
disguised as a check; (3) do the seven new tasks in section 1/2/6/7 collectively cover D6 end to end
(flag parsing, path resolution, PID namespacing, reset scoping, and the DATABASE_URL-precedence edge
case) without a gap; (4) is anything now inconsistent across the four edited files (e.g., a task
referencing a scenario name that does not match the spec delta's actual requirement title). If the
cold review finds no blocking gap, record APPROVE and this change is 3-round-eligible again for a
*future* iteration's implementation pass — implementation is still gated on `pywebview` authorization
per `limits`, so approval alone does not trigger `at_cap`'s execute clause here. If the review does
find gaps, fix them in the same iteration if small, or record a targeted round-3 next_action if not.

## Entry 15 — N4 round 2 (cold review): one real gap found and fixed — a named profile with no `--port` would silently collide with the default profile's port. APPROVE recorded. N4 done; `current` advances to N5.

**2026-08-17T03:07:40+01:00.** Worked N4-q6-decisions, round 2: a cold review of the amended
`2026-08-16-one-hub-and-a-window-of-its-own` change as it stood after iteration 14's round 1 — fresh
read, not a continuation of that iteration's own authoring context, checking the four questions
`next_action` posed.

**(1) Does D6 close A3's three named consequences?** The three original ones (dual-writer via
`DATABASE_URL`, blind `stop`/`status` via the PID file, ambiguous `reset` blast radius) all check out
against D6's database/PID-file/reset text. But cold review found a **fourth**, self-inflicted by D6
and never in A3's original table because A3 predates D6: read `src/agentweave/cli.py` directly (not
assumed from the design's own prose) and confirmed `--port` already defaults to `DEFAULT_HUB_PORT`
(8000) on every subparser — bare invocation (`cli.py:1076`), `status` (`:1105`), `stop` (`:1109`).
Round 1's D6 said "`--port` stays required alongside `--profile`" but nothing in `tasks.md` or the
spec delta actually enforced that — an operator who ran `agentweave --profile dev` without `--port`
would silently resolve to the same port the default profile normally uses, a real TCP-level bind
collision that profile-namespaced database and PID-file paths do nothing to prevent (they namespace
*identity*, not the socket). This is exactly the kind of gap "does it close the consequences, not just
gesture at them" was written to catch.

**Fixed in this same round, not deferred**, per `next_action`'s instruction that a small gap gets
fixed inline: `design.md`'s D6 "Port" bullet now states the requirement is enforced, not aspirational,
and explains why (`--port`'s existing `default=8000` means an operator who forgets it gets a value,
not an error, unless something checks). Added `tasks.md` **1.8** (implementation — flags the
passed-vs-default distinction argparse's plain `default=8000` can't make on its own, so this needs a
sentinel or `sys.argv` check, not a value comparison) and **2.9** (regression test, mutation-checked).
Added a **new spec scenario**, "A named profile without an explicit port is rejected," under the
`app-lifecycle` ADDED requirement, plus a SHALL sentence in the requirement body. Added **6.7**
(human-only: confirm the error message is legible, not a raw traceback) and a fourth bullet to
section 7 step 4's user guide walking an operator through the failure case, plus a matching line in
"Where it would go wrong."

**(2) Is the A2 thin-shell constraint concrete enough for task 3.5?** One looseness closed: D3's
allowed list ("no logic beyond `webview.create_window`/`webview.start`, the fallback's exception
catch...") did not say whether task 3.2's mandated diagnostic print on a caught exception counted as
part of "the exception catch" or as forbidden extra logic — a reviewer checking 3.5 would have had to
guess. Closed by naming the print explicitly as part of the permitted catch, in both D3's paragraph and
the amendments-resolved note.

**(3) Do the tasks (now nine after 1.8/2.9) cover D6 end to end — flag parsing, path resolution, PID
namespacing, reset scoping, `DATABASE_URL` precedence — without a gap?** Re-checked item by item
against that five-part list: 1.4 (flag + resolution + precedence), 1.5 (PID), 1.6 (reset), 2.5-2.8 each
mirror an implementation task with a test, 2.9 now covers the port gap. No further gap found.

**(4) Is anything now inconsistent across the edited files?** Checked task-to-scenario references
(2.5 against `TestTwoInstancesDoNotCollide`, 6.6/6.7 against the spec's "Two profiles do not collide,"
"Reset targets exactly one profile," and the new "A named profile without an explicit port is
rejected" scenarios, section 7 against the same) — all consistent. `proposal.md` was left untouched
this round (confirmed by `git status --porcelain` — only `design.md`, `tasks.md`, and the spec delta
changed): it documents D6 at the same level of detail it always has (no PID-filename shape, no port
requirement) and adding one task-level detail without the others would have made the inconsistency
worse, not better.

**Verdict recorded in `design.md`'s new "Round 2 — cold review, 2026-08-17" section: APPROVE**, with
the port gap fixed inline rather than deferred to a round 3. Task count: 30 → 32 (21 original + this
round's 1.8/2.9; iteration 14's D6 additions already brought it from 21 to 30).

**Verified, not trusted:** `npx openspec validate --changes --strict` → 20/20, this change clean after
all of this round's edits. Gapless numbering re-confirmed with `grep -n "^- \[ \] [0-9]"` across the
whole file. `git status --porcelain` showed exactly the three edited files, nothing else — no source
file touched, so `verified_green_at_iteration_12_commit_619fd5a` still holds as the Python/UI baseline
(unchanged since iteration 12, N4 never touched source).

**Still SPEC ONLY.** No `pywebview` installed, no `--profile`/`--port`-requirement code written.
`at_cap`'s approve-and-execute does not apply here — approving the *spec round* is not the same gate as
authorizing the *dependency* `limits` withholds; the change is 3-round-eligible again but implementation
stays blocked on `pywebview` until the operator says otherwise.

**N4-q6-decisions is done — both rounds closed, change approved for a future implementation pass.**
`current` advances to `N5-architecture-proposals`. `next_action`: read
`openspec/explorations/2026-08-15-where-agentweave-fits.md` (178 lines); first correct its §2 error in
place or via a dated addendum — it currently concludes "the operator has, in practice, already run the
comparison and picked the competitor for the harder job," which the operator has directly said is
false: "The one thing that it got wrong is that I chose the openspec before my spec. It was just a
matter that my spec didn't exist when I started with agentweave. So until it catches up in maturity I
could not use it." — chronology, not a verdict. Then
propose one or more architectures building from the exploration's surviving narrow claim (durable
cross-session state, addressable bound identity, an operator-facing UI), accounting for a world where
tonight's N2 (archive/capability phases) and N3 (many-named-loops) have already shipped. Thinking
documents only, no code — same shape as N1.

## Entry 16 — N5: fixed the false §2 conclusion, then proposed three architectures grounded in tonight's own N2/N3. N5 done; `current` advances to N6 (fallback).

**2026-08-17T03:21:35+01:00.** Worked N5-architecture-proposals as scoped by `next_action`.

**Part 1 — the correction.** Read `openspec/explorations/2026-08-15-where-agentweave-fits.md` in
full before touching anything, per the instruction not to build on top of a known-false conclusion.
§2 closed with "...it means the operator has, in practice, already run the comparison and picked the
competitor for the harder job (developing AgentWeave itself)." The operator said this directly, this
session, before the run started: "The one thing that it got wrong is that I chose openspec before my
spec... chronology, not a verdict." Fixed via a dated blockquote addendum inserted immediately after
the sentence (left the original prose intact rather than silently rewriting history in a document
whose own header says "nothing here is asserted from memory") — quotes the operator verbatim, states
the correction, and notes the gap it points at (this repo needed a mature spec tool before its own
spec tool was mature enough to use on itself) is one this migration is actively closing, not a
standing preference. This was a two-line target but the instruction was explicit not to skip it even
though it "looks like a one-liner."

**Part 2 — three architecture proposals**, written in a new document,
`openspec/explorations/2026-08-17-architecture-proposals.md`, built from the surviving narrow claim
(durability, addressable bound identity, an operator-facing UI) rather than a re-survey, and
deliberately accounting for tonight's own N2 (`2026-08-16-the-corpus-keeps-what-shipped`: archived
phase, `kind='capability'` at phase `current`, operator-authored merge) and N3
(`2026-08-16-many-named-loops`: `Loop` wraps `AIJob`, `Loop.purpose`/`stop_at`/
`stop_when_queue_empties`, queue is `Task.loop_id`) having already shipped rather than treating them
as hypothetical. Grounded both change summaries by reading their actual `proposal.md`/`design.md`
this iteration rather than trusting memory of the STATE.json queue-item prose, which predates their
implementation and could have drifted.

- **Proposal A — loops as a fourth roster citizen.** `Loop` today has a free-text `purpose` and no
  charter, no roster-page presence. Bind it to a charter (reusing the existing mechanism verbatim,
  not forking it) and surface it on the same roster page as agents, badge-distinguished. Cheapest of
  the three: one nullable FK column, one UI badge.
- **Proposal B — a spec-drift verification loop.** N2 gives capability documents somewhere to live;
  nothing re-reads them, so they can go stale the same day they're merged. Propose a named loop whose
  queue is one task per capability document, checking shipped behaviour against the document and
  recording divergence as `Evidence` — explicitly barred from editing the capability document itself,
  because N2's authored-merge rule stays intact. Tied this back to the governance angle from
  `where-agentweave-fits.md` §1 (EU AI Act / NIST audit-trail language) as the same shape turned
  inward rather than chased as a buyer.
- **Proposal C — retire `STATE.json`: run the autonomous session itself as a `Loop`.** The sharpest
  test of the durability claim: this very run is proof by counterexample that the tool best
  positioned to demonstrate durable cross-session state doesn't yet trust its own product to hold it.
  Scoped honestly — explicitly does NOT propose the Hub firing Claude Code from inside a loop (N3's
  scope ceiling, inherited deliberately) and names the real blocker (the autonomous session's actual
  unit of work has no equivalent to "fire a Hub-registered agent through a Hub-managed runner," since
  this process is neither). Recommended as the next exploration to deepen, not the next change to
  propose.

Also wrote an explicit "What NOT to build now" section (no second execution path beside `AIJob`; no
exception letting the verification loop write capability documents; no forked charter-editing UI for
loops) and a sequencing recommendation (A first if any ship — cheapest and makes B legible; B is the
highest-leverage next *spec* change, keeps N2's `current` phase honest; C is highest long-term value
but least ready to spec tonight).

**Verified, not trusted:** `npx openspec validate --changes --strict` → 20/20 (exploration docs are
outside `--changes` validation by design — this just confirms nothing else broke). `git status
--porcelain` showed exactly the two intended files: the corrected `2026-08-15-...md` and the new
`2026-08-17-...md`. No source file touched, so `verified_green_at_iteration_12_commit_619fd5a` still
holds — nothing here required re-running either suite.

**N5-architecture-proposals is done** — both the correction and the proposals, sized to one iteration
as `next_action` allowed ("ship one solid document this iteration... rather than rushing a shallow
survey" — three proposals in one document judged sufficient rather than shallow, since each is
grounded in this session's own shipped changes rather than generic). `current` advances to
`N6-openspec-backlog`, the fallback item: archive the pre-08-16 openspec changes sitting in
`openspec/changes/` (13 of the current 19 unarchived predate 2026-08-16). `next_action`: for each
pre-08-16 change, read its `tasks.md`, tick any human-only-verification item that has real recorded
evidence from this session or a prior one, explicitly waive (with a stated reason, not an invented
one) any that cannot be verified unattended, then archive via the openspec CLI. Do not tick anything
on the strength of a plan existing (CLAUDE.md, restated in STATE.json's queue item). If time runs out
before all 13 are reached, stop after a clean batch rather than leaving one half-edited — commit
whichever are actually archived, and leave `next_action` naming which remain.
