# Tasks — task dependencies

Groups 1–4 are observable but inert: edges exist and nothing enforces them. That is a good state to
sit in if the gate needs more confidence before it lands. Group 5 is the first that changes
behaviour.

## 1. The payload

- [x] 1.1 Add `depends_on: List[str]` to `spec_payload.Task`. Default empty — an existing document must validate unchanged. Landed `hub/hub/spec_payload.py:120-123`: `depends_on: List[str] = Field(default_factory=list, ...)`. An existing document with no `depends_on` key on any task validates unchanged — every existing `test_spec_payload.py` test still passes untouched (23 passed before this section's new tests were added).
- [x] 1.2 Write the `Field(description=...)`. These **are** the agent-facing instructions — *"One concrete unit of work, not 'build the whole thing'"* is how decomposition is taught today, and ordering gets taught in the same place. Say that keys name siblings in this document. Landed alongside 1.1: *"Keys of sibling tasks in THIS document — local only — that must be approved before this one may start. An imported entry (see `from`) is named the same way once declared, so it can be depended on like any other sibling. This is where ordering gets taught, the same place decomposition is."*
- [x] 1.3 Add the imported-entry shape: an entry naming another document's path and a task key in it, distinguishable from a locally-declared task. Decide whether that is a discriminator field on `Task` or a separate list, and record which in design D4 when you find out which reads better in a real payload. **Decided: a discriminator field on `Task` (`from_`, aliased to the reserved word `from`), single `tasks` list — not a separate `imported_tasks` list.** Wrote a realistic cross-document payload both ways before deciding (see the round-trip test added for 1.5, which is the shape that was actually tried): with a discriminator, an imported entry is `{key, from: {document, key}}` sitting in the same list a sibling's `depends_on` already indexes into by key — no second collection to cross-reference when materialising or rendering a nav strip. A separate `imported_tasks: List[dict]` list was the alternative on the table; it keeps ordinary `Task` structurally simple (no field that's required for one kind of entry and forbidden for another) but means every consumer of `depends_on` — the gate, the board, `materialise()` — has to look in two lists to resolve one key, and duplicate-key checking has to run across both rather than one. The discriminator also matches design D4's own diagram literally (the imported entry is drawn *inside* `tasks:`, marked "← IMPORTED", not in a second block) — that diagram is the design's illustration of its own decision, so departing from it would need a reason the design doesn't give. Recorded in `design.md` D4 (new subsection below the original decision) with the rejected alternative and why. Implementation: `ImportedFrom(_Part)` submodel (`document`, `key`) rather than a raw `Dict[str, str]`, so a malformed import (missing `document` or `key`) is a normal pydantic field error at payload validation, the same mechanism every other nested part already uses — not a new one. `description` and `requirements` became optional (`default=""` / `default_factory=list`) because an imported entry legitimately carries neither; this is a real, deliberate loosening of what payload *shape* validation enforces (previously both keys had to be present, even if empty, for any task), justified because nothing today enforces non-empty `description` at either the shape or completeness layer regardless (checked: no `spec_completeness.py` finding exists for a blank description), and `requirements` emptiness was already shape-legal (`test_a_task_with_no_requirements_is_well_formed_but_incomplete`) — so the change extends an existing permissiveness to cover the one field (`description`) that hadn't needed it before imports existed.
- [x] 1.4 Write its description too, including that the referenced document must be approved and why. Landed on `ImportedFrom.document` (`hub/hub/spec_payload.py`): *"Path of the document that owns this task. It must be approved: a task cannot import work from a document nobody has signed off on, and until it is, the imported dependency names nothing a reader or an approver can rely on."* — the "why" is stated, not just the rule, matching 1.2's standard and the task's own instruction.
- [x] 1.5 Round-trip test: a payload with dependencies and imports survives render → `extract_payload` → validate unchanged. `test_a_round_trip_with_local_dependencies_and_an_import_loses_nothing` (`hub/tests/test_spec_payload.py`) — a two-task payload (one imported entry, one local task with `depends_on: [that imported entry's key]`) through `payload_to_dict(validate_payload(...))` → `embed_payload` → `extract_payload`, asserts the recovered dict is byte-for-byte equal to what was stored, AND that re-validating the recovered dict produces the same dict again (not just JSON-equal once). Needed one supporting fix to make the round trip actually lossless: `payload_to_dict` now calls `model_dump(mode="json", by_alias=True)` — without `by_alias=True` the aliased `from_` field would have serialised back out as the key `"from_"` instead of `"from"`, silently renaming the field on every save. Two narrower tests also added: `test_a_local_depends_on_names_a_sibling_key` and `test_an_imported_entry_needs_no_description_or_requirements`. The file went from 20 tests to 23 (3 new, 0 removed, all 20 pre-existing ones still pass unchanged); ran `pytest hub/tests/test_spec_payload.py hub/tests/test_spec_declared_tasks.py hub/tests/test_spec_board_task_convergence.py -q` → **38 passed** (the latter two files exercise `materialise()` against the same `Task` shape and were unaffected). Also ran `ruff check`, `black --check` (reformatted the new test file once, then clean) and `mypy hub/spec_payload.py` — all clean.

**Added 2026-08-21, after 1.1–1.5 landed and after implementation had moved past this group.**
One more payload field, decided while this change was in flight so the corpus needs one migration
rather than two. Design D11.

**These three are outstanding and easy to miss**, because a worker walking groups in order is already
past group 1. Task 10.0 gates the change on them.

- [x] 1.6 Add `reviewer: Optional[str] = None` to `spec_payload.Task`. Optional, and a document that
      names none must validate and materialise exactly as it does today. Landed `hub/hub/spec_payload.py`
      (right after `from_`): `reviewer: Optional[str] = Field(default=None, ...)`. No alias, no
      wiring into `materialise()`, the completeness checks, or the gate — D11 is explicit that
      resolution belongs to `loop-becomes-a-flow`, not this change; this section owes only the field,
      its description, and preservation. `test_naming_no_reviewer_validates_and_materialises_as_before`
      confirms a task with no `reviewer` key validates with `reviewer is None` and nothing else about
      the task's shape changed; the full pre-existing `test_spec_declared_tasks.py`/
      `test_spec_board_task_convergence.py`/`test_spec_completeness.py` suites (54 tests, none of them
      touching `reviewer`) still pass unchanged, which is the "materialises exactly as before"
      guarantee for the field's absence.
- [x] 1.7 Write the `Field(description=...)` — these **are** the agent-facing instructions, the same
      standard 1.2 was held to. It must say what the name is resolved against and that an
      unresolvable one is kept rather than refused, because an author writing a document has no way
      to know which agents exist on the machine that will run it. Landed: *"Agent name this task's
      completion should be reviewed by, resolved against the roster when the task is claimed for
      review. Optional: an author writing a document has no way to know which agents exist on the
      machine that will run it, so an unresolvable name is kept rather than refused — resolution
      falls back to whatever the reviewing mechanism does when none is named or none resolves."*
- [x] 1.8 Round-trip test alongside 1.5's: a payload naming a reviewer survives render →
      `extract_payload` → validate unchanged, and one naming none is byte-identical to today's.
      Landed `test_a_named_reviewer_survives_round_trip` (same `payload_to_dict` →
      `embed_payload` → `extract_payload` → re-validate chain 1.5 already uses, for a task naming
      `reviewer: "codex-1"`) and `test_naming_no_reviewer_validates_and_materialises_as_before`
      (a task with no `reviewer` key validates to `reviewer is None`, matching every task in the
      corpus written before this field existed). `hub/tests/test_spec_payload.py` went from 62
      tests to 64 (2 new, 0 removed, all 62 pre-existing still pass unchanged). **Adding the field
      moved `test_spec_render.py`'s pinned byte-for-byte digest, exactly as 1.5's own comment
      already predicted would happen again**: `render_document` embeds the stored payload verbatim,
      so `_rich_payload()`'s one task grew a `"reviewer": null` in its embedded JSON. Confirmed the
      delta was confined to that one line by diffing the rendered output against the pre-change
      render (`git stash` on `spec_payload.py` alone, re-render, diff) rather than assuming it from
      the field's default — nothing else moved. Recaptured `_BASELINE_DIGEST` and extended its
      comment to record the fourth recapture and why, same discipline the comment already asks for.

**Verified, not assumed.** `pytest tests/test_spec_payload.py tests/test_spec_render.py tests/test_spec_declared_tasks.py tests/test_spec_board_task_convergence.py tests/test_spec_completeness.py -q` (from `hub/`) → **122 passed**. `ruff check` and `black --check` clean on `hub/hub/spec_payload.py`, `hub/tests/test_spec_payload.py`, `hub/tests/test_spec_render.py`; `mypy hub/spec_payload.py` → clean. Full CLI suite (`py -3.11 -m pytest tests/ -q` from the repo root) — not rerun this section (payload-schema change confined to the Hub); full `hub/tests/` suite (`py -3.11 -m pytest tests/ -q --ignore=tests/browser`, run in the **foreground** per `NEVER_BACKGROUND_AND_WAIT`, polled via blocking `TaskOutput` rather than ending the turn) → **2720 passed, 12 skipped, 1 xpassed, 0 failed in 1365.37s** — +2 over the prior baseline (2718), exactly the two new tests this section adds, zero failures. This is the rule run 1 learned the expensive way: this section adds a payload field, so the full suite was run rather than trusted to targeted files, and it is exactly what caught the render digest above.

## 2. Completeness checks

- [x] 2.1 Report a `depends_on` key that resolves to neither a local task nor an imported entry. Landed `hub/hub/spec_completeness.py` `check()`, code `depends_on_unresolved`: builds `all_task_keys` once per document (every `task.key`, local and imported alike — an imported entry's own key is exactly what a sibling depends on, per 1.2's field description), then reports each `depends_on` entry not in that set at `tasks[i].depends_on[j]`. Test: `test_an_unresolved_depends_on_key_is_reported`, plus two "not reported" tests for a sibling key and an imported entry's key (`hub/tests/test_spec_completeness.py`).
- [x] 2.2 Report a cycle among locally-declared tasks. Depth-first over the declared keys; the graph is small. Landed `_first_cycle()` in the same file: builds `local_edges` from `payload.tasks` filtered to `task.from_ is None` only (imported entries excluded — they are leaves by construction, cannot participate in a within-document cycle, matching the task's own note), plain DFS with a three-colour (unvisited/visiting/done) map and an explicit stack rather than recursion depth alone, so the returned cycle is the actual walked path for the message. `ruff` flagged the first draft's `WHITE/GRAY/BLACK` constants (N806) and a dict-comprehension (C420); renamed to lowercase and switched to `dict.fromkeys`. Test: `test_a_cycle_among_local_tasks_is_reported`, and `test_a_local_task_depending_on_an_imported_entry_is_not_a_cycle` guarding the exclusion specifically.
- [x] 2.3 Report an import naming a document that is not approved. Needed a lookup `spec_completeness.check()` itself does not have — per the task's own instruction, kept `check()` a pure function of its inputs (docstring now says so explicitly) and threaded a new `approved_document_paths: Optional[AbstractSet[str]]` parameter the same way `board_served` already is. The set is computed by a new `spec_lifecycle.approved_document_paths(session, project_id)` (`hub/hub/spec_lifecycle.py`, beside `list_documents`) — a plain `SpecDocument.path` query filtered to `phase == APPROVED`, current phase, not "ever approved" (`first_approved_at` is D6's rename rule, a different question; commented as such to keep the two from being conflated later). Both call sites in `hub/hub/spec_service.py` (`_apply_and_write`'s `SaveResult.blocking`, and `propose()`) now compute `approved_paths` beside their existing `board_served` fetch and pass it through. Code `import_not_approved`, message names both the local key, the imported key, and the document path. Tests: `test_an_import_naming_an_unapproved_document_is_reported`, `test_an_import_naming_an_approved_document_is_not_reported`.
- [x] 2.4 All three are **blocking**, never a submission refusal (design D7). Test that submitting a document with all three problems succeeds and returns all three in `blocking`. Landed as `test_a_document_with_all_three_dependency_problems_returns_all_three_findings`: a three-task payload carrying an unresolved `depends_on`, a two-task local cycle, and an unapproved import all at once, asserting `validate_payload` does not raise (none of these are shape problems) and `check()`'s returned codes are a superset of all three — the same pattern `test_every_problem_is_reported_not_just_the_first` already uses for the five pre-existing checks, extended rather than reinvented.
- [x] 2.5 State the limit in the cycle check's own message: cycles are detected within a document, not across documents. A reader who sees cycle detection will otherwise assume it is complete. Landed in the `dependency_cycle` `Finding.message` itself (not a comment): `"a cycle among locally-declared tasks: t1 -> t2 -> t1 — cycles are detected within this document only, not across documents"`. Asserted directly in `test_a_cycle_among_local_tasks_is_reported`.

**Verified, not assumed.** `pytest hub/tests/test_spec_completeness.py hub/tests/test_spec_payload.py hub/tests/test_spec_declared_tasks.py hub/tests/test_spec_board_task_convergence.py hub/tests/test_operator_authored_documents.py hub/tests/test_spec_capability_kind.py hub/tests/test_spec_index_writer.py -q` → **113 passed** (24 in the completeness file itself, up from 14 before this section — 10 new tests, 0 removed; the other six files exercise `spec_service.py`'s two call sites and confirm the new parameter didn't disturb existing submission/propose behaviour). `ruff check`, `black --check` (reformatted `spec_completeness.py` and the test file once — line-length wrapping only — then clean) and `mypy hub/spec_completeness.py hub/spec_lifecycle.py hub/spec_service.py` all clean. `git status --short` confirms scope: `hub/hub/spec_completeness.py`, `hub/hub/spec_lifecycle.py`, `hub/hub/spec_service.py`, `hub/tests/test_spec_completeness.py`, `openspec/changes/task-dependencies/tasks.md` — no file outside this section touched. Full Hub/CLI suites **not** rerun this iteration (targeted files cover every touched call path; section 2 of 10, matches `iteration_shape`'s "optional this section" framing) — due before section 3 or at latest before S3 as a whole is called done.

## 3. Storage

- [x] 3.1 Migration `0083` (head is `0082`). Bump the head assertions in **both** `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`. Landed `hub/hub/migrations/versions/0083_task_dependencies.py`, `down_revision = "0082"`. `HEAD_REVISION` bumped in `hub/tests/test_migrations.py:39` and the literal `"0082"` in `hub/tests/test_project_persistence.py:227`, both to `"0083"`.
- [x] 3.2 `task_dependencies` table: `task_id`, `depends_on_task_id`, project scope. Index both directions — the gate reads one way, the board reads both. Landed `TaskDependency` in `hub/hub/db/models.py` (right after `TaskRequirementReference`) and mirrored in the migration: `id`, `project_id` (FK `projects.id`), `task_id` and `depends_on_task_id` (both FK `tasks.id`), `created_at`. `uq_task_dependencies_pair` unique constraint plus `ix_task_dependencies_task` and `ix_task_dependencies_depends_on` — one index per direction, matching `task_requirement_links`' shape (`0067`), the stated precedent.
- [x] 3.3 **Decided: ForeignKey on both `task_id` and `depends_on_task_id`, `ondelete="CASCADE"`** — the design's own leaning. Recorded in `models.py`'s `TaskDependency` docstring, contrasted explicitly with `Question.blocked_task_id`: a question is a record of something that happened and stays true after the task it named is gone, but a dependency naming a task that no longer exists is not a fact worth keeping — a hole in a graph, so losing the edge with the task is correct. Noted honestly rather than glossed over: `PRAGMA foreign_keys` is never turned on for this app's SQLite connections (`project_lifecycle.py::_project_scoped_tables` says so directly) and nothing today deletes a `Task` at all — so the cascade is declarative, same footing as `JobRun.job_id`/`Loop.job_id`'s existing `ondelete="CASCADE"` columns, and takes effect the day either changes.
- [x] 3.4 `SpecDocument.first_approved_at`, nullable. Comment it against `explore_closed_at`: that one is **reset** on reopen (*"reopening genuinely reopens"*), and this one never is. Landed in `models.py` beside `explore_closed_at`, comment states both facts explicitly. **Extra, not separately listed as a subtask but required for the column to mean anything going forward**: wired `document.first_approved_at = datetime.now(timezone.utc)` into `spec_lifecycle.transition()` (`hub/hub/spec_lifecycle.py`), set only `if to_phase == APPROVED and document.first_approved_at is None` — beside the existing `explore_closed_at = None` reset on reopen, so a reader sees both in the same place. Without this the column would only ever be populated once, at migration time, and every document approved afterward would carry `first_approved_at: NULL` forever — silently breaking section 6's rename refusal for exactly the documents it matters most for. Verified with a direct unit test (`test_first_approved_at_is_set_once_and_survives_a_reopen`, `hub/tests/test_spec_archive.py`): set on first approval, unchanged through a reopen (`explore_closed_at` resets, `first_approved_at` doesn't), unchanged through a second approval.
- [x] 3.5 Backfill `first_approved_at` from the `kind="phase"` event history, whose detail carries `{"from", "to"}`. Landed `_backfill_first_approved_at()` in the same migration: one pass over `spec_document_events WHERE kind='phase' ORDER BY document_id, created_at`, parsing `detail` (a JSON column, raw text over a direct connection — same as `0067`'s own approach, not `json_extract`, which no migration in this project uses), keeping the *earliest* row per document whose `detail["to"] == "approved"`. Runs unconditionally whenever `spec_documents` is present (not gated on "column was just added this run") so it is idempotent under a repeat run, the same shape `0067`'s own backfill uses — it only ever writes where `first_approved_at IS NULL`. Tested with two migration-level tests inserting real event rows: `test_migration_0083_backfills_first_approved_at_from_phase_history` (four events including a reopen-then-reapprove, asserts the *earliest* approval wins, not the later one) and `test_migration_0083_leaves_a_never_approved_document_null` (no qualifying event → stays `NULL`, not guessed).
- [x] 3.6 Guard the migration for a missing table, as `0033`/`0034` do — an upgrade from an early revision reaches it with only that revision's tables. `task_dependencies`' creation is guarded on **three** conditions (`"task_dependencies" not in present and "tasks" in present and "projects" in present`) since it FKs both, matching `0052`'s own guard for `task_transitions` exactly (`0052` guards on `tasks` *and* `projects` for the same reason). `first_approved_at`/backfill is guarded on `spec_documents` alone (no FK dependency). Verified, not assumed: `test_migration_0083_is_guarded_when_tasks_and_spec_documents_do_not_exist` reuses the existing `_create_0034_conversations_state` early-revision fixture (`projects`/`conversations`/`runs` only, no `tasks`) and confirms the upgrade reaches head with `task_dependencies` absent — while also confirming `spec_documents` *does* exist and gets `first_approved_at` (it's created unconditionally by `0065`, unrelated to `tasks`, so this is the correct outcome, not a gap).

**Verified, not assumed.** `pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py -q` → **73 passed, 1 skipped** (4 new tests in `test_migrations.py` for 0083: guard, table+column shape, backfill-picks-earliest, never-approved-stays-null). `pytest hub/tests/test_spec_archive.py hub/tests/test_spec_documents_api.py hub/tests/test_spec_declared_tasks.py hub/tests/test_spec_board_task_convergence.py hub/tests/test_operator_authored_documents.py hub/tests/test_spec_capability_kind.py hub/tests/test_spec_completeness.py hub/tests/test_spec_payload.py hub/tests/test_migrations.py hub/tests/test_project_persistence.py -q` → **188 passed, 1 skipped**. `ruff check` and `black --check` clean on every touched file (black reformatted the new migration file once, then clean — Python-3.11-vs-3.12 AST-parse warning is environmental, not a formatting diff). `mypy hub/db/models.py hub/spec_lifecycle.py` → **clean, zero errors**; `mypy` on the migration file itself reports the same pre-existing "missing parameter type annotation" pattern every other migration in this project carries (confirmed against `0034` and `0067` directly) — not new noise. `git status --short` confirms scope: `hub/hub/db/models.py`, `hub/hub/spec_lifecycle.py`, `hub/hub/migrations/versions/0083_task_dependencies.py` (new), `hub/tests/test_migrations.py`, `hub/tests/test_project_persistence.py`, `hub/tests/test_spec_archive.py`, `openspec/changes/task-dependencies/tasks.md` — no file outside this section touched. Full Hub suite kicked off early per `iteration_shape`; result recorded in the log once it completes.

## 4. Materialisation

- [x] 4.1 `materialise()` creates the declared edges after creating the tasks, since an edge needs both ends. Landed `_materialise_edges()` in `hub/hub/spec_tasks.py`, called at the end of `materialise()` after the existing task-creation loop and its final `session.flush()`es. Runs a resolution pass (every declared entry's key → its `Task`, or an import's resolved target, or why not) followed by an edge-creation pass over every LOCAL entry's `depends_on`. `existing_keys`'s companion `local_tasks: Dict[str, Task]` (new) carries the actual row objects needed to create an edge — built once from a query that already existed (now selecting full `Task` rows instead of just `spec_task_key`), extended in the creation loop's own `existing_keys.add(key)` line rather than a second query.
- [x] 4.2 An imported entry **resolves to the existing task and never creates one**. **Found and fixed a real bug while writing the section's own tests**: the first implementation never checked `entry.get("from")` in the primary task-creation loop, so an import entry — whose `requirements` list is empty by construction (`spec_payload.py`'s `Task.requirements` defaults to `[]` for an imported entry) — fell through the "already served" skip (which requires a *non-empty* resolved `requirements` list) and materialised as an ordinary task. `test_an_import_resolves_to_the_existing_task_without_creating_one` caught it directly (`tasks_created` was 2, not 1) before this was tagged done. Fixed with one guard, right after the `key in existing_keys` check: `if isinstance(entry.get("from"), dict): continue`. `_resolve_import()` (new) does the actual resolution: `SpecDocument` by `(project_id, path)`, confirmed `phase == APPROVED`, then `Task` by `(spec_document_id, spec_task_key)`.
- [x] 4.3 An unresolvable import is preserved and reported, following `absorb_free_text`'s precedent (`spec_tasks.py:204-206`) rather than inventing a mechanism. **Decided: its own table, not `TaskRequirementReference`** — recorded with the reasoning in `design.md`'s D7 addendum (a dangling dependency and a dangling requirement are different facts with non-overlapping `reason` vocabularies). New `TaskDependencyReference` model (`hub/hub/db/models.py`, migration `0084`, `hub/tests/test_migrations.py`), `reason` one of `document_not_found` / `document_not_approved` / `key_not_found` / `malformed_import` / `not_declared` (the last for a purely local dangling key — a defensive branch `spec_completeness.depends_on_unresolved` should already prevent from reaching `approve()`, kept anyway since `materialise()` must never assume a caller upheld that). Rows are replaced wholesale per task on every `materialise()` call (`DELETE ... WHERE task_id = :id` before the pass), so a reference that resolves on a later approval is removed rather than left stale — `absorb_free_text`'s own `replace=True` default, same reasoning. Tested directly: `test_an_unresolvable_import_is_preserved_and_reported_not_raised` reproduces the actual race (propose while the import resolves, reopen the source document, then approve) through the real HTTP routes, and `test_materialise_never_raises_for_a_malformed_import` exercises `materialise()` at the unit level for a shape no validated payload can carry.
- [x] 4.4 Re-approving a revised document adds new edges and **does not touch existing tasks** — `spec_tasks.py:19-21`, *"a task that already exists is never touched."* **Decided: the rule is about the task row, not its incoming edges — a revision may add a new edge to an already-materialised task.** Full reasoning in `design.md`'s D5-adjacent D7 addendum: D5 already says the document is the only writer of edges, so refusing a revision's new `depends_on` on an existing task would make edges write-once for no reason D1–D7 gives. Implemented by having the edge-creation pass in `_materialise_edges()` iterate every declared LOCAL entry (via `local_tasks`, which holds both pre-existing and newly-created rows), not just what this call's task-creation loop returned in `created`. What is NOT reversible: an edge already recorded is never removed even if a later revision's `depends_on` drops the name — same one-directional caution `existing_keys` already gives task creation, made explicit in the function's own docstring.
- [x] 4.5 Test re-approval twice: no duplicate tasks, no duplicate edges. `test_re_approving_twice_creates_no_duplicate_edges` (exact same `edges()` set before and after a no-op re-approval) plus `test_a_revision_adds_a_new_edge_to_an_existing_task_without_touching_it` for the 4.4 case specifically (asserts zero new tasks, the new edge exists, and both task ids are unchanged from before the revision) — `hub/tests/test_spec_task_dependencies.py`.
- [x] 4.6 Test that a document declaring no dependencies materialises exactly as before. `test_a_document_with_no_dependencies_materialises_no_edges` — zero `TaskDependency` rows, zero `TaskDependencyReference` rows for a task with no `depends_on` at all. The full pre-existing `test_spec_declared_tasks.py` suite (11 tests, all task-creation behaviour predating this section) also still passes unchanged, which is the byte-for-byte "materialises exactly as before" guarantee for everything this section did not touch.

**New file**: `hub/hub/spec_tasks.py` gained `_resolve_import()` and `_materialise_edges()`, both private — the only public surface `materialise()`/`materialise_quietly()` is unchanged in signature and return type. New test file `hub/tests/test_spec_task_dependencies.py` (7 tests) rather than appending to the already-large `test_spec_declared_tasks.py`, matching how `test_spec_completeness.py` etc. are already split by concern.

**Verified, not assumed.** `pytest hub/tests/test_spec_task_dependencies.py hub/tests/test_spec_declared_tasks.py hub/tests/test_spec_board_task_convergence.py hub/tests/test_spec_completeness.py hub/tests/test_spec_payload.py hub/tests/test_operator_authored_documents.py hub/tests/test_spec_capability_kind.py hub/tests/test_migrations.py hub/tests/test_project_persistence.py hub/tests/test_spec_archive.py -q` → **174 passed, 1 skipped**. `ruff check`, `black --check` (reformatted `spec_tasks.py` and the new test file once, then clean) and `mypy hub/spec_tasks.py` (one real type error on the new `local_tasks` dict comprehension — `Task.spec_task_key` is `Optional[str]` even though the query filters it — fixed with an explicit `is not None` guard in the comprehension) all clean. `git status --short` confirms scope: `hub/hub/spec_tasks.py`, `hub/hub/db/models.py`, `hub/hub/migrations/versions/0084_task_dependency_references.py` (new), `hub/tests/test_migrations.py`, `hub/tests/test_project_persistence.py`, `hub/tests/test_spec_task_dependencies.py` (new), `openspec/changes/task-dependencies/design.md`, `openspec/changes/task-dependencies/tasks.md` — no file outside this section touched. Full Hub suite kicked off in the background per `iteration_shape`'s guidance for a section this central; result recorded below once it completes.

## 5. The gate — the first behaviour change

- [x] 5.1 Add the third guard in `task_transition_service`, beside `_guard_author_is_not_reviewer` and the `requirement_gate` call. **Same place, before the history row** — that placement is a requirement, not a style choice. Landed as a new module, `hub/hub/dependency_gate.py` (`evaluate(session, task) -> DependencyRefusal`), following `requirement_gate.py`'s own shape (a dataclass refusal with a `detail()`/`to_dict()`, a pure `evaluate` over the database). Called from `task_transition_service.apply_transition` (`hub/hub/task_transition_service.py`) immediately after `await _guard_author_is_not_reviewer(...)` and before the existing `if to_status == "approved":` requirement-gate block — both before `task.status = to_status` and before the `TaskTransition` row is constructed, same as the requirement gate.
- [x] 5.2 Gate `→ in_progress` only. Not `→ assigned`, not `→ rejected`. Landed as `if to_status == "in_progress":` around the call — the condition is on `to_status` alone, so it fires for `pending -> in_progress`, `assigned -> in_progress` and `blocked -> in_progress` alike (all three share this one destination), and never for a move to `assigned` or `rejected`. Tested directly: `test_assigning_a_gated_task_is_not_gated` and `test_rejecting_a_gated_task_is_not_gated` (`hub/tests/test_dependency_gate.py`) confirm a task with an unmet dependency still reaches `assigned`/`rejected` without a refusal.
- [x] 5.3 Gate the `blocked → in_progress` resume edge the same way. Follows from 5.2's `to_status`-only condition — no separate case was needed. Tested: `test_the_blocked_resume_edge_is_gated_the_same_way` (refused, stays `blocked`) and `test_the_blocked_resume_edge_succeeds_once_the_prerequisite_is_approved` (succeeds once the prerequisite reaches `approved`).
- [x] 5.4 Met means the prerequisite is `approved`. Nothing earlier. Landed as `dependency_gate.MET_STATUS = "approved"`, matching `TaskDependency`'s own model docstring verbatim ("may not start until `depends_on_task_id` is `approved`") — confirmed against design D2 before implementing: "met" is the depended-on **task's own status field** reaching `approved`, not a document-phase question (D2 is about the task lifecycle `completed -> under_review -> approved`, which already requires a second agent via author/reviewer separation — that is what stops a chain advancing with a single agent, for free, on this one gate). Tested with all six non-`approved`, non-`rejected` statuses parametrised (`test_a_prerequisite_short_of_approved_gates_the_move`) plus a dedicated `test_completed_is_not_enough_only_approved_is` naming D2's own risk directly.
- [x] 5.5 A distinct error type, so the refusal is distinguishable from an illegal transition and names the unmet prerequisites. Landed `DependencyUnmetError(TransitionRefusedError)` in `task_transition_service.py`, beside `GateUnsatisfiedError` and built the same way (`http_status = 409`, carries `.refusal`, `TransitionRefusedError`'s existing exception handler in `hub/hub/main.py` already renders any subclass's `.refusal.to_dict()` generically, so no route or handler needed a change). `DependencyRefusal.detail()` names every unmet/rejected prerequisite by title and id; `to_dict()` gives `{"code": "dependency_unmet", "unmet": [...], "rejected": [...], "message": ...}`. Tested: `test_the_refusal_shares_the_base_so_routes_catch_one_type`, `test_the_structured_refusal_round_trips_through_to_dict`, `test_every_unmet_prerequisite_is_named_not_just_the_first`, `test_one_approved_and_one_unmet_prerequisite_still_gates`.
- [x] 5.6 A prerequisite that is `rejected` gates permanently and the refusal says so — a different message from "not yet approved", because the remedy is different. Landed as two separate lists on `DependencyRefusal` (`unmet`, `rejected`), sorted in `evaluate()` by `prerequisite.status == "rejected"`; `detail()` renders each list with different wording ("was rejected and will not become approved on its own — reopen it, or edit the document..." vs. "is `'pending'`, not yet approved"). Tested: `test_a_rejected_prerequisite_gates_permanently_with_a_different_message` and `test_an_unmet_but_not_rejected_prerequisite_says_not_yet_approved` assert the two messages are mutually exclusive substrings, and `test_a_rejected_prerequisite_reads_differently_from_an_unmet_one_over_http` confirms the same split survives serialisation to the HTTP response body.
- [x] 5.7 Refuse recording a dependency for a task with no `spec_document_id`, stating that dependencies are declared by a document (design D5). **Not implemented — verified unreachable rather than invented a call site for it, as the task itself allows.** `TaskDependency` rows are created in exactly one place, `spec_tasks.py::_materialise_edges` (grepped `TaskDependency(` across `hub/hub/`, one non-test hit). Its `task` argument always comes from `local_tasks`, which is built exclusively from `Task` rows already filtered to `spec_document_id == document.id` (`materialise()`'s `existing_task_rows` query, `hub/hub/spec_tasks.py:123-135`) — so every `TaskDependency.task_id` this code can ever write already has a non-null `spec_document_id`, by construction, with no code path today that could pass it a hand-made task. Design D5's own text agrees this is about a *future* surface: "an operator who **tries** should get a refusal" describes an editing action nothing in the product exposes yet — there is no route or tool that lets an operator or agent declare a dependency directly. Adding a defensive check with no reachable caller would be exactly the "error handling for a scenario that can't happen" this codebase's own conventions ask not to add (`CLAUDE.md`). Revisit when `loop-notices-and-reacts` (S4) or any future operator-facing "add a dependency" action creates a second writer.
- [x] 5.8 Test every surface: operator route, agent HTTP, tool surface, jobs. The point of the placement is that all four are covered without knowing it — assert that rather than assume it. Traced all five call sites of `apply_transition` (`grep -rn "apply_transition("`) before writing anything: `api/v1/tasks.py:756` (`update_task_for_actor`, the **one choke point both the operator PATCH route and the agent-HTTP PATCH route share** — confirmed by reading both callers, `tasks.py:857` and `agent_actions.py:274`), `run_task_binding.py:254/394/445` (the **runtime/jobs surface** — binding a run to a task, parking on a question, releasing one), and `scheduler.py:907` (`assigned` only, not gated, no test needed). The **tool surface** is not a fifth call site: `mcp_server.py`'s `update_task` tool (`hub/hub/mcp_server.py:271`) is `_hub_request("PATCH", f"/tasks/{task_id}", ...)`, which resolves to `PATCH /api/v1/agent-actions/tasks/{id}` — the exact same route and code path the agent-HTTP test already drives, not a separate mechanism to test again. Landed: `hub/tests/test_dependency_gate.py` (direct `apply_transition`, both `operator()` and implicitly every actor since the gate has no actor branch), `hub/tests/test_task_transitions_api.py` (new section "The dependency gate reaches both transports" — operator PATCH and agent PATCH, both asserting the structured `dependency_unmet` body, one test each for gated/rejected/unblocked), `hub/tests/test_run_task_binding.py` (new section — `bind_run_to_task` with an unmet dependency leaves the task un-started and the run still bound, matching the existing `TransitionRefusedError` catch-all; the stale comment there claiming a refusal "cannot currently fire for `in_progress`" was corrected to say why it now can).
- [x] 5.9 Test that a task with no dependencies transitions exactly as before. Landed as `test_a_task_with_no_dependencies_starts_exactly_as_before` and `test_evaluate_refuses_nothing_for_a_task_with_no_rows` — the gate's query has nothing to iterate for a task with zero `TaskDependency` rows, so `refusal.refuses` is `False` by construction, not by a special case. The full pre-existing `test_task_transition_service.py` suite (34 tests, all predating this section, none of which construct a `TaskDependency`) also still passes unchanged, which is the same guarantee at the scale of the whole machine rather than one test.

**Verified, not assumed.** `pytest hub/tests/test_dependency_gate.py hub/tests/test_task_transitions_api.py hub/tests/test_run_task_binding.py hub/tests/test_task_transition_service.py hub/tests/test_task_transitions.py -q` → **159 passed**. Wider neighbourhood — `hub/tests/test_spec_task_dependencies.py hub/tests/test_spec_declared_tasks.py hub/tests/test_spec_board_task_convergence.py hub/tests/test_requirement_gate.py hub/tests/test_task_transitions_api.py -q` → **73 passed** (confirms materialisation and the requirement gate are undisturbed). `ruff check` and `black --check` clean on every touched file (`hub/hub/dependency_gate.py` new; `hub/hub/task_transition_service.py`, `hub/hub/run_task_binding.py`, and the three test files modified). `mypy` on the three touched non-test files, checked both individually (0 errors each) and together (298 vs. 297 baseline — the one new error is `DependencyUnmetError.__init__(self, refusal)` missing a parameter annotation, the exact same pre-existing pattern `GateUnsatisfiedError.__init__` already carries two classes above it, confirmed by diffing the error count with the change stashed). Full `hub/tests/` suite run this section (adds neither a table nor a payload field, but this is a genuine behaviour change on a shared choke point — leaned toward running it anyway per `iteration_shape`/`run2`'s own rule): **2696 passed, 12 skipped, 1 xpassed, 0 failed in 848.77s**, run from `hub/` (hence 12 skipped, not the repo-root invocation's 84 — same collection-directory difference iteration 3 already noted, not a regression). Zero failures — the whole suite, not just the touched neighbourhood, confirms nothing outside this section's stated scope broke.

## 6. The rename refusal

- [x] 6.1 Change `rename_document`'s check from `phase == APPROVED` to "has ever been approved". Landed: `hub/hub/spec_service.py:665` now checks `document.first_approved_at is not None` instead of `document.phase == spec_lifecycle.APPROVED`, with a comment at the check site (per D6) explaining why phase alone isn't enough and pointing at `spec_lifecycle.transition()` for the never-reset invariant. `first_approved_at` (migration 0083, section 3) is already set once on the first `-> approved` transition and never cleared — `spec_lifecycle.py:299-303`.
- [x] 6.2 Test the two holes this closes: approve → archive → rename, and approve → reopen → rename. Both must now refuse. Landed as `test_a_document_that_was_approved_and_then_archived_is_still_not_renamed` and `test_a_document_that_was_approved_and_then_reopened_is_still_not_renamed` in `hub/tests/test_spec_rename.py`, driven through the real `/documents/phase` and `/documents/rename` HTTP routes (not a hand-built `SpecDocument`). Both assert `422`/`document_approved` and that the file did not move.
- [x] 6.3 Test that a never-approved document still renames. Landed as `test_a_never_approved_document_still_renames` — takes a document through propose and back to exploring (reopened, never approved) and confirms the rename still succeeds at 200. The plain never-touched-approval path was already covered by the pre-existing `test_a_subject_becomes_the_documents_path`; confirmed rather than assumed.
- [x] 6.4 Check whether any existing test asserted the archived-rename path worked. If one does, it encoded the hole — fix the test and say so in the commit. Checked: no existing test in `test_spec_rename.py` exercised archive or reopen before renaming — the only pre-existing approved-refusal test (`test_an_approved_document_is_not_renamed`) checked the direct approved-phase case only. Nothing needed fixing; the hole was untested, not wrongly asserted.

**Verified, not assumed.** `pytest tests/test_spec_rename.py tests/test_spec_archive.py tests/test_migrations.py -q` from `hub/` → 100 passed, 1 skipped. `ruff check`/`black --check` on `hub/spec_service.py` and `tests/test_spec_rename.py` → clean. `mypy hub/spec_service.py` → no new errors attributable to this file. CLI baseline (`pytest tests/ -q` from repo root) → 404 passed, 3 skipped, exact match to run2_baseline. Full `hub/tests/` suite (adds no table, no payload field, so optional per run2's own rule — run anyway per iteration_shape's lean-toward-it note): `pytest tests/ -q --ignore=tests/browser` from `hub/` → **2699 passed, 12 skipped, 1 xpassed, 0 failed in 1386.00s (23m05s)** — +3 over iteration 11's own full-suite count (2696), exactly the three new tests this section adds. Zero regressions against run2's running baseline.

## 7. Reading dependencies

- [x] 7.1 Expose a task's prerequisites and dependents on the task read model. Landed: `TaskDependencyRef` (`hub/hub/schemas/tasks.py`) carries `id`/`title`/`status` — enough to render an edge without a second fetch — and `TaskResponse` gains `prerequisites` and `dependents`, read from `TaskDependency` at both ends.
- [x] 7.2 Expose derived state: gated, gated-on-rejected, running-on-regressed. Derived per request, not stored — a stored readiness column is a denormalised join that goes stale (design D1). Landed as `TaskResponse.dependency_state`, one of `gated` / `gated_on_rejected` / `running_on_regressed` / `None`, computed per request. The field's own comment states why it is not stored.
- [x] 7.3 A board endpoint returning one document's tasks with edges, in one call. The board must not N+1 its way to a layout. Landed as `GET /tasks/board` with an `_attach_dependencies` batch helper. **Caveat, stated rather than glossed: the no-N+1 property was NOT measured.** No query-count assertion exists — the helper is shaped to batch, and the tests confirm the endpoint returns correct edges, but nothing yet fails if a future edit reintroduces a per-card query. Worth a query-counting test before this is called done.
- [x] 7.4 Board list with outstanding counts, for the picker. Landed as `GET /tasks/boards`. `outstanding` excludes only `run_task_binding.TERMINAL_FOR_BINDING`, so a `rejected` task counts as resolved rather than outstanding even though it never reached `approved`.

**Verified by the interactive session, not by the firing that wrote it.** That firing stood down without committing when it found a concurrent session had committed to the branch. `pytest tests/test_task_dependency_reads.py tests/test_spec_task_dependencies.py tests/test_tasks.py tests/test_task_transitions_api.py tests/test_task_transition_service.py tests/test_task_blocked.py -q` from `hub/` → **104 passed** (10 of them the new file's). `ruff check` on `hub/api/v1/tasks.py`, `hub/schemas/tasks.py` and the new test file → clean. Full `hub/tests/` suite NOT re-run for this section — section 7 adds no table and no payload field, so it is optional per this run's own rule, and the section-6 run of 2699/0-failed already covers everything beneath it.

## 8. The board

- [x] 8.1 Layer assignment: longest-path depth, so a task sits below **everything** it depends on rather than below its first prerequisite. Landed: `assignDepths(tasks, edges)` (`hub/ui/src/lib/dependencyBoardLayout.ts`) — memoised DFS per task, `depth(t) = 1 + max(depth(p) for p in prerequisites(t))`, `0` for a task with none. Explicitly tested against the failure mode a first-prerequisite or shortest-path rule would produce (a diamond `a→b→d` and `a→d`, asserting `d` sits at depth 2, below `b`, not depth 1 from the direct edge alone). A prerequisite outside the board's own task set (an off-board import, task 8.7's territory) contributes nothing to depth rather than throwing. A cycle — which should never reach the board, `spec_completeness`'s `dependency_cycle` check refuses it at proposal — is guarded with a `visiting` set so a bug elsewhere degrades to a wrong layer, not a hung tab; tested directly.
- [x] 8.2 Top-to-bottom layout, converging edges drawn. Landed: `DependencyBoard.tsx` renders `groupByDepth`'s layers as stacked rows (shallowest first, top of the scroll), each a CSS grid of cards. Edges are a single absolutely-positioned `<svg>` behind the cards, one `<line>` per edge, coordinates measured from the real DOM (`useEdgeLines`) after layout via `getBoundingClientRect`, relative to the scrolling container so it holds under scroll — recomputed on mount, on window resize, and via a `ResizeObserver` on the container and every card (a layer reflowing can move cards below it without the container itself changing size). Converging edges (two prerequisites into one dependent) draw as two independent lines into the same point, which is what "converging" asks for at this stage — see the 8.12 addendum below for what is deliberately not attempted yet. An edge naming an off-board task (no matching card ref) is skipped rather than drawn to nowhere or thrown on.
- [x] 8.3 **Reuse `TaskCard`.** A board that grows its own card component is how the two views diverge (design, risks). Landed: `DependencyBoard.tsx` renders the real `TaskCard` per task (same `assigneeColorIndex`, `onOpenRequirement`, `onOpen` props `TasksBoard.tsx` passes it) and opens the same `TaskDetailDrawer` — one drawer for the whole board, exactly F5's pattern. No second card component exists anywhere in this diff.
- [x] 8.4 Confirm the status badge reads correctly **on its own, with no status column** — `TaskCard.tsx:235` already renders it, where it is currently redundant with the column. (Reworded 2026-08-21: it used to say "the only status signal", which D12's liveness cue makes false. The intent was always that the badge must not *need* the column, not that nothing else may appear.) Confirmed rather than built: `DependencyBoard.tsx` has no status column at all — position means depth (D8), never status — and `TaskCard` (reused whole per 8.3) always renders `StatusBadge` regardless. New test asserts two cards at the same depth, differing only in `status`, each still read correctly off their own badge.
- [x] 8.5 Document picker with outstanding counts, plus the standing "no document" board. Landed: `hub/ui/src/components/tasks/DependencyBoardView.tsx`, wrapping `DependencyBoard` with a picker row built on the already-landed `useTaskBoards()` (task 7.4/D9) — one pill per board (`title`, or "No document" for the `null`-keyed standing board) each showing `outstanding/total`, so choosing a board and seeing what remains are the same glance per D9. Defaults to the first *document* board (documents-first, "no document" last — the backend's own sort at `hub/hub/api/v1/tasks.py:783`), not the standing board, since the dependency view exists for documents that declare dependencies. Not yet mounted from `App.tsx` — still task 8.11's job — so reachable today only from its own tests.
- [x] 8.6 Collapse a layer whose tasks are all terminal; expandable. Do not collapse a partly finished layer. Landed: `isTerminalTask` (`dependencyBoardLayout.ts`, restating the backend's `run_task_binding.TERMINAL_FOR_BINDING` — `approved`/`rejected` — since the UI has no import path into `hub/hub/`) plus a per-layer toggle in `DependencyBoard.tsx`, keyed by depth. A layer collapses to a "`N` done" row by default only when *every* task in it is terminal; a layer with even one unfinished task never grows the toggle at all, so its rendering is byte-identical to before 8.6. Known, accepted limit rather than an oversight: an edge into or out of a *collapsed* layer's card is not drawn while collapsed — the same skip-if-no-card-ref behaviour 8.1/8.2 already give an off-board reference, not a special case added for this — noted here rather than built out further, matching 8.12's own "good enough, not unbounded polish" precedent.
- [x] 8.7 Imported entries drawn as off-board references naming their document. Landed across both sides of the fetch: `TaskDependencyRef` (`hub/hub/schemas/tasks.py`) gained `spec_document_id`, populated in `_attach_dependencies` (`hub/hub/api/v1/tasks.py`) for both an on-board ref (already known, `response.spec_document_id`) and an off-board one (added to the existing `other_rows` query rather than a second query). The frontend's `offBoardPrerequisites(tasks)` (`dependencyBoardLayout.ts`) reads every on-board task's own `prerequisites` list for an id not on this board — no second fetch, the ref was already attached — and `DependencyBoard.tsx` renders the result once, above every layer (these are referenced, not laid out, so they get no depth of their own), each a dashed pill naming the prerequisite and its document via `useTaskBoards()`'s already-cached titles (task 7.4). New backend test `test_board_prerequisite_ref_carries_its_own_document`; frontend covered both as pure-function tests (`offBoardPrerequisites`) and a rendered-board test.
- [x] 8.8 **The three stalled states, distinguished** (design D8): gated, waiting-on-review, gated-on-rejected. Surface "layer N is waiting on M reviews" at the layer, not only per card — this is the mitigation for the change's main risk and it is a display rule protecting a lifecycle rule. Landed: `dependencyStallState(task)` (`dependencyBoardLayout.ts`) reads each task's own `dependency_state` (7.2, already served) plus its `prerequisites`' statuses (also already served, no new fetch) to split D8's middle row out of the backend's single `"gated"` value — every unmet prerequisite `completed`/`under_review` means `waiting_on_review`, anything earlier stays plain `gated`; `gated_on_rejected` passes through unchanged. `layerStallSummary` (`DependencyBoard.tsx`) counts the three across a layer and renders "Layer N is waiting on M reviews[, K gated on an unmet prerequisite][, J gated on a rejected prerequisite]." above the layer, present only when at least one task in it is stalled. 5 new pure-function tests plus 3 rendered-board tests.
- [x] 8.9 Mark a running task whose prerequisite regressed. Landed on `TaskCard` itself (`hub/ui/src/components/tasks/TaskCard.tsx`), not `DependencyBoard` — `dependency_state === 'running_on_regressed'` is already attached to every `TaskResponse` a page fetches (7.2), not only a board's, so the flag is visible wherever the card is, matching D8's "awareness, not enforcement" (nothing here touches status; the gate only guards the `-> in_progress` edge). A red pill, "Prerequisite regressed", deliberately distinct from the existing amber "Stalled" divergence badge — that one means a run stopped reporting in, this one means a real prerequisite fact changed. 3 new tests in `taskDivergenceControls.test.tsx`.
- [ ] 8.10 No editing affordance for structure. Where an operator tries, say dependencies are changed by editing the document.
- [ ] 8.11 View toggle; the seven-column board unchanged.
- [x] 8.12 Decide what "good enough" edge routing is **before** implementing it. Crossing minimisation in a layered DAG is a known hard problem and an unbounded one to polish. Decided and landed together as a technical call rather than an operator one — see design.md's D8 addendum: a direct straight line per edge, no crossing minimisation or bundling, redrawn on layout change. Recorded rather than escalated to `decisions_for_user` because nothing about it is stored data or hard to reverse — it is one function, and 8.12's own wording already names the deferred part as "unbounded... to polish," not an open product question.

**Verified, not assumed — first pass (8.1, 8.2, 8.3, 8.12), 2026-08-21.** New files
`hub/ui/src/lib/dependencyBoardLayout.ts` (the pure layer-assignment functions, so they are not
tangled into a component export and do not trip `react-refresh/only-export-components`) and
`hub/ui/src/components/tasks/DependencyBoard.tsx`; extended `hub/ui/src/api/tasks.ts` with the
`TaskDependencyRef`/`prerequisites`/`dependents`/`dependency_state` fields the section 7 backend
already served but no frontend type carried yet, plus `useTaskBoard`/`useTaskBoards` (the latter
for 8.5, added now since it is a one-line wrap of an already-landed endpoint, not used by this
pass). New test files `hub/ui/src/__tests__/dependencyBoard.test.tsx` (9 tests: the longest-path
property directly, the cycle guard, the off-board-prerequisite skip, `groupByDepth`'s ordering, and
three component-level renders confirming layer placement, `TaskCard` reuse — including that the
drawer F5 already wires up still opens — and edge-count) and two more in `tasksApi.test.tsx` for
`useTaskBoard`'s request shape, including the `null` case (the standing "no document" board, which
must fire unlike `useDocumentTasks(null)`). `npx tsc --noEmit` clean. `npx eslint ... --max-warnings
0` on every touched file clean (the pure functions living in `lib/` rather than the component file
is what keeps that at zero rather than two fast-refresh warnings). Full `hub/ui` `vitest run`: **119
files / 1183 passed** — exactly baseline 1172 + 11 new tests, 0 failed, 0 regressed. **Not yet
wired into `App.tsx`'s `tasks` tab** — that is task 8.11 (the view toggle), deliberately a later
pass, so this component is reachable today only from its own tests, not from a running Hub. The
remaining tasks in this section (8.4–8.11, 8.13–8.16) are unstarted.

**Verified, not assumed — second pass (8.4, 8.5, 8.6), 2026-08-21.** New file
`hub/ui/src/components/tasks/DependencyBoardView.tsx` (picker + board); `dependencyBoardLayout.ts`
gained `isTerminalTask`; `DependencyBoard.tsx` gained the per-layer collapse toggle. New test file
`hub/ui/src/__tests__/dependencyBoardView.test.tsx` (4 tests: per-board counts, defaulting to the
first document board rather than "no document", switching on click, the all-empty state) plus 3
more added to `dependencyBoard.test.tsx` (the badge reading correctly with two different statuses
at the same depth; a fully-terminal layer collapsing by default and expanding on click; a
partly-finished layer never collapsing at all). One self-caught test bug before it shipped: the
first 8.4 test used `getByText(/pending/i)` against a task titled "Pending task", which matched
both the title and the badge and threw its own "multiple elements" error — fixed by titling the
cards nothing that echoes a status word and scoping the query to each card's own container
(`closest('.cursor-pointer')`) rather than the whole document. One test-only bug also caught before
shipping, not a product one: the first `dependencyBoardView.test.tsx` draft built each mocked
`useTaskBoard(id)` response as a fresh object literal *inside* the mock closure, so `edges` was a
new array reference on every render; `DependencyBoard`'s `useLayoutEffect` depends on that
reference and re-ran every render, hitting React's "Maximum update depth exceeded" guard. Real
usage never sees this — React Query holds a response reference steady between renders unless an
actual refetch changes it — so the fix was moving the mocked data to stable module-scope
constants, not touching `DependencyBoard.tsx` itself. `npx tsc --noEmit` clean. `npx eslint` on
every touched file, `--max-warnings 0`, clean. Full `hub/ui` `vitest run`, in the **foreground**:
**120 files / 1190 passed** — exactly the prior pass's 1183 + 7 new tests, 0 failed, 0 regressed.
No Python touched, so `ruff`/`black`/`mypy`/`pytest hub/tests/` were not run for this pass.

**Verified, not assumed — third pass (8.7, 8.8, 8.9), 2026-08-21.** This pass touched Python
(`TaskDependencyRef` gained a field), so per the run's own `lesson_from_run1` the full backend
suite was run rather than a targeted selection. Backend: `hub/hub/schemas/tasks.py` (`spec_document_id`
on `TaskDependencyRef`), `hub/hub/api/v1/tasks.py` (`_attach_dependencies` populates it from the
already-fetched rows on both sides, no new query). `ruff check` and `black --check` clean on both
files; `mypy` shows no new errors attributable to either (checked by grepping the two paths out of
the run's pre-existing 301-error baseline, unrelated files, zero hits). New backend test
`test_board_prerequisite_ref_carries_its_own_document` — targeted file
`pytest hub/tests/test_task_dependency_reads.py -q` → **11 passed**. Full `hub/tests/` suite, in
the **foreground** (started early, ~16 minutes): **2727 passed, 84 skipped, 1 xpassed, 0 failed in
964.22s** — up from run3's own 2699-passed baseline, the difference accounted for by the concurrent
interactive session's own uncommitted-then-committed work landing in the same tree during the run
(`022cd36`, `5f0c10f`), not this pass's; `git show --stat` on both confirms neither touches a file
this pass touched. Frontend: `dependencyBoardLayout.ts` gained `offBoardPrerequisites` and
`dependencyStallState`; `DependencyBoard.tsx` renders both; `TaskCard.tsx` gained the regressed-
prerequisite badge (8.9's real home — every page that serves `dependency_state`, not only the
board). 16 new tests: 3 pure-function (`offBoardPrerequisites`), 5 pure-function
(`dependencyStallState`), 2 rendered (8.7's off-board reference chip present/absent), 3 rendered
(8.8's layer summary — waiting-on-review wording, gated vs. gated-on-rejected in the same sentence,
silent when nothing is stalled), 3 rendered (8.9's badge on `TaskCard`, in
`taskDivergenceControls.test.tsx` next to the existing divergence-badge tests since both are "what
a card says when something is wrong"). One pre-existing-but-adjacent finding, not fixed here: `Icon`
names `"alert_triangle"` and `"help_circle"`, already used by `TaskCard.tsx` before this pass, are
not in `Icon.tsx`'s `ICONS` map — they render nothing and only warn to the console (confirmed by
reading the full map). This pass's own new icon uses `"link"`, which *is* mapped, deliberately
avoiding the same trap rather than also fixing the pre-existing one, which is out of this section's
scope. `npx tsc --noEmit` clean. `npx eslint` on every touched file, `--max-warnings 0`, clean (one
warning self-caught and fixed before shipping: an unmemoised `useMemo` dependency on a fresh
`board?.tasks ?? []` array — resolved by dropping the `useMemo`, since `offBoardPrerequisites` is
one cheap pass over already-fetched data and not worth a second dependency list to keep in step).
Full `hub/ui` `vitest run`, in the **foreground**: **120 files / 1206 passed** — exactly the prior
pass's 1190 + 16 new tests, 0 failed, 0 regressed. `openspec validate task-dependencies --strict`
and `--all --strict` both clean (42/42 — one more `spec/change` item than the prior pass's 41,
accounted for by the concurrent session's own new `diagnose-and-clear-a-broken-loop` proposal, not
this pass's).

**Verified, not assumed — fourth pass (8.10, 8.11), 2026-08-21.** No Python touched. Changed:
`hub/ui/src/components/tasks/DependencyBoardView.tsx` (the structure hint), `hub/ui/src/App.tsx`
(the `tasksView` toggle wiring the dependency board into the `tasks` tab for the first time), and
their two test files. `npx tsc --noEmit` clean. `npx eslint` on all four touched files,
`--max-warnings 0`, clean. Targeted (`dependencyBoardView.test.tsx`, `dependencyBoard.test.tsx`,
`App-mount.test.tsx`, `tasksApi.test.tsx`, `tasksBoardFilter.test.tsx`,
`blockedStaysInProgress.test.tsx`) → **58 passed**. Full `hub/ui` `vitest run`, in the
**foreground**: **120 files / 1208 passed** — exactly the prior pass's 1206 + 2 new tests, 0
failed, 0 regressed (the two `Error: boom` stack traces in the run's own console output are
`ErrorBoundary.test.tsx` intentionally throwing to test the boundary, not a failure — present in
every run of that file, not new here). `openspec validate task-dependencies --strict` and
`--all --strict` both clean (42/42). Full backend `hub/tests/` suite **not** rerun — this pass adds
no table and no payload field (`lesson_from_run1`'s trigger), and it is the first pass in section 8
to touch zero Python at all.

Remaining in section 8 (4 of 16 tasks): 8.13–8.16.

**Verified, not assumed — fifth pass (8.15, 8.16, then 8.13), 2026-08-21.** No new backend field or
table (`assignee_status` already existed on `TaskResponse`), so per `lesson_from_run1` the full
`hub/tests/` suite was not rerun; this is the second pass in a row touching zero Python. Changed:
`hub/ui/src/components/tasks/TaskCard.tsx` (the cue itself), `hub/ui/src/index.css` (the
`task-live-pulse` keyframes), new `hub/ui/src/lib/motion.ts` (`prefersReducedMotion()`), new
`hub/ui/src/__tests__/taskLivenessCue.test.tsx` (6 tests). `npx tsc --noEmit` clean. `npx eslint`
on all four touched/new files, `--max-warnings 0`, clean. Targeted
(`taskLivenessCue.test.tsx`, `taskDivergenceControls.test.tsx`) → **19 passed**. Full `hub/ui`
`vitest run`, in the **foreground**: **121 files / 1214 passed** — exactly the prior pass's 1208 +
6 new tests, 0 failed, 0 regressed. `openspec validate task-dependencies --strict` and
`--all --strict` both clean (42/42). Confirmed the compiled class survived the production build by
grepping the built CSS asset directly (`grep -c task-live-pulse hub/hub/static/ui/assets/*.css` →
1), not merely assumed from a clean `npm run build` exit code. **Live-browser verification is
partial, recorded honestly rather than overclaimed:** started the Vite dev server against 8010
(`AW_DEV_HUB=http://127.0.0.1:8010 npm run dev`, port 5173 already held by another process on this
machine so bound 5174 instead — confirmed via `netstat`, not assumed) and confirmed it served the
app (`curl` 200). Checked every task on `proj-ff695d96` (the trial Hub's one project with real
data) for a live `assignee_status: 'running'` via the real API — none was running at the time
(all `idle`), so the *pulsing* branch could not be photographed without spinning up a real agent
run, which this pass judged disproportionate to a CSS-styling check (cost, time, and touching a
project this run's own convention treats as read-only). The "off" branch (no cue on a card with no
live run) and the toggle/board around it were already verified live in the fourth pass and nothing
in this pass touches that path. The "on" branch's actual DOM output (the `task-live-*` testid, the
`task-live-pulse` class, and the `boxShadow` ring) **is** verified against real React output via
`@testing-library/react`'s `render()` — jsdom, not a mock renderer — which is why the test file
mocks only `window.matchMedia`, the one browser API jsdom does not implement meaningfully, rather
than the component itself. Dev server stopped (`Stop-Process`) before finishing the turn.

Section 8 is now **16/16, complete.** Rebuilt the UI bundle (`npm run build` +
`scripts/refresh_ui_bundle.py`) and committed `hub/ui/src` and `hub/hub/static/ui` together (8.13,
always last).
- [x] 8.10 No editing affordance for structure. Where an operator tries, say dependencies are changed by editing the document. Confirmed rather than built, in the same spirit as 8.4: no add/remove-edge affordance exists anywhere in `DependencyBoard.tsx` or `DependencyBoardView.tsx` — grepped both for any click handler that would mutate `depends_on`, found none, matching design D5 ("the document is the only writer of edges") by construction, not by care. The one gap: nothing *said* that, so an operator who came looking for an edit control would find silence rather than an explanation. Added `structureHint` in `DependencyBoardView.tsx`, rendered as a line below the document picker: "Dependencies are set in the document — edit its depends_on field to change them" for a document board, and D5's own stated consequence — "Hand-made tasks belong to no document, so they can never have a dependency" — for the standing "no document" board, rather than the same generic wording for both. New test in `dependencyBoardView.test.tsx` asserts both strings, one per board.
- [x] 8.11 View toggle; the seven-column board unchanged. Landed in `App.tsx`'s `tasks` tab: a `tasksView` state (`'board' | 'dependencies'`, default `'board'`) following the exact pattern the `activity` tab's `activitySubview` already established (two buttons, `aria-pressed`, no stored preference — opt-in per visit, same reasoning as `activitySubview`), switching between `TasksBoard` and the now-mountable `DependencyBoardView`. `onOpenRequirement` is built once in the tab branch and passed to whichever view is active, since `TaskCard`'s requirement chip means the same thing in both. `TasksBoard.tsx` itself was not touched — confirmed via `git diff --stat` showing zero lines changed in that file — so the seven-column board is verified unchanged, not merely assumed so. New test in `App-mount.test.tsx` ("Tasks contains Dependencies as an internal sub-view") mirrors the existing Activity/Logs test exactly: switches to Dependencies, back to Board, asserts the other view unmounts each time. **Verified live against 8010**, not only via `vitest`, per this task's own point being the one where the board becomes reachable from a running Hub: started `AW_DEV_HUB=http://127.0.0.1:8010 npm run dev` (Vite on `:5173`, IPv6-only loopback — reachable at `http://localhost:5173`, not `127.0.0.1`, worth noting since the first attempt connection-refused against the numeric address), then `py -3.11 scripts/uishot.py` against `proj-5e960453` (this repo's own trial project, empty of tasks) and, to see a populated board, `proj-ff695d96` ("aw-loop10", a different registered project on the same trial Hub with real `depends_on` data) — read-only, nothing in either project was mutated. Screenshots (not committed, cleaned up from `testbed/scratch/` after viewing) showed: the Board/Dependencies toggle rendering correctly with Board active by default; clicking Dependencies mounting the real picker, a real card layout, and 8.10's structure hint reading correctly beneath it; `aw-loop10`'s document board rendering all 5 of its real tasks in a single unlayered row, confirmed correct rather than a bug by checking the raw `/tasks/board` response directly — that document declares zero `depends_on` edges, so depth-0-for-everyone is the right layout, not evidence of anything broken.
- [x] 8.15 **The liveness cue.** A slow pulsing hue around a card whose task has a live run. It says something the badge does not — the badge says the task *is* `in_progress`, the cue says a run is executing *now*, and `has_open_divergence` exists because those two can disagree. Landed: the signal is `task.assignee_status === 'running'` — already the Hub's own liveness read (`effective_heartbeat_status` in `hub/hub/agent_status.py`, served on every `TaskResponse` since before this change), so this needed no new backend field. `TaskCard.tsx` computes `isLive` from it and applies a green ring (`boxShadow`) plus, when motion is allowed, a `task-live-pulse` class (new `@keyframes` in `index.css`) to the card's own root — no second card component, per D12's third constraint.
- [x] 8.16 Gate the animation on `prefers-reduced-motion`, degrading to a static hue, and confirm nothing is carried by colour or motion alone. Test both branches. Landed: new `hub/ui/src/lib/motion.ts` (`prefersReducedMotion()`, a plain `window.matchMedia` read — deliberately not a hook/subscription, since the accessibility floor is "never animate when asked not to," not "react live to an OS setting mid-session"). `TaskCard.tsx` reads it once per render and withholds the `task-live-pulse` class when true, while the `boxShadow` ring itself is unconditional on `isLive` alone — so reduced motion loses only the pulsing, never the cue, matching D12's "degrading to a static hue," not to nothing. The colour-or-motion-alone constraint was already met by the pre-existing `assignee_status` text pill a few lines below (renders the word "running"), asserted directly in the new tests rather than merely assumed. Both branches are genuinely tested, not just the CSS blanket rule relied on elsewhere in this codebase (`LoopTab.tsx`'s dot): `hub/ui/src/__tests__/taskLivenessCue.test.tsx` mocks `window.matchMedia` to each of `matches: true`/`matches: false` and asserts the class is present/absent accordingly, plus that the ring itself (`boxShadow`) survives the reduced-motion branch.
- [x] 8.13 **Always last in this section, whatever is added above it:** `make ui` after `npm run build`, and commit `hub/ui/src` and `hub/hub/static/ui` together. Left at 8.13 rather than renumbered — renumbering a group with a regex silently produced duplicate headers twice on 2026-08-21, and the ordering that matters here is the doing, not the numbering.

## 9. The loop's claim — without this the change deadlocks every loop

Design D10. Depends on `loop-notices-and-reacts` having landed the shared claim decision; if it has
not, this group builds against the current `_claim_loop_task` and that change adapts it instead.

- [x] 9.1 Test the deadlock first, before fixing it: a loop over a document declaring A → B, with A
      unapproved, must not claim B on every firing forever. Assert the current failure, then flip the
      assertion — the same order that caught the spin on 2026-08-20. Landed as
      `test_a_dependent_task_with_an_unapproved_prerequisite_is_never_claimed`
      (`hub/tests/test_loop_claim_dependency_gate.py`), with `dependent_b` created *before*
      `prereq_a` deliberately so `_loop_queue_order`'s `created_at.asc()` tiebreak would pick the
      dependent under the old code. **Mutation-checked rather than assumed**: temporarily restored
      the pre-section-9 `_claim_loop_task` (plain `.limit(1)`, no gate check) and confirmed this
      test fails, claiming `task-9-1-b` instead of `task-9-1-a` — the exact deadlock. An earlier
      draft of the test created the prerequisite first, which happened to pass against the old code
      by insertion-order coincidence rather than by exercising the gate; caught by the same
      mutation check and fixed before landing.
- [x] 9.2 Test: a queue holding an older gated task and a newer startable one claims the newer, and
      leaves the older with its status and no assignee. Landed as
      `test_an_older_gated_task_is_skipped_for_a_newer_startable_one`. Also mutation-checked: fails
      against the pre-section-9 code (claims the older, gated task).
- [x] 9.3 Test: a queue where every task is gated claims nothing, and the job stays enabled with no
      stop reason recorded. Landed as
      `test_a_queue_where_every_task_is_gated_claims_nothing_and_stays_enabled` — a chain of three
      (rejected blocker → pending prereq → pending dependent) so every claimable candidate is
      gated at once, confirming `_claim_loop_task` returns `None` and `_loop_stop_reason` still
      does too (gated, not drained).
- [x] 9.4 Test: approving the prerequisite makes the gated task claimable on the next firing, with no
      other action. Landed as `test_approving_the_prerequisite_makes_the_dependent_claimable` —
      walks the prerequisite through `in_progress → completed → under_review → approved` via
      `apply_transition` directly, touching the dependent not at all, then reclaims.
- [x] 9.5 Test the agreement directly — every task a firing claims can move to `in_progress` without
      the dependency gate refusing it. This is the whole property; assert it rather than inferring it
      from the cases above. Landed as
      `test_every_claimed_task_would_be_accepted_by_the_dependency_gate`: claims from a queue with a
      gated task alongside a startable one, then asserts `dependency_gate.evaluate` on whatever was
      claimed does not refuse (skipped for an already-`in_progress` claim, which needs no fresh
      check).
- [x] 9.6 Implement the skip using the **same** dependency determination the gate in group 5 uses.
      A second implementation is the drift `_loop_queue_order`'s comment records; import it. Landed:
      new `_first_startable_candidate(session, loop)` in `hub/hub/scheduler.py` walks the ordered
      claimable-status query and calls `dependency_gate.evaluate` per candidate — no second
      readiness computation. `_claim_loop_task` is now a one-line wrapper over it.
- [x] 9.7 Skip unstartable tasks in queue order rather than stopping at the first one. Landed in the
      same walk: a gated candidate is appended to a `gated` list and the loop continues to the next
      candidate; `in_progress` always returns immediately (already running, no fresh gate check —
      design D8's "flagged, not stopped").
- [x] 9.8 Distinguish the two stall reasons: waiting on work that can still be approved, versus gated
      on a `rejected` prerequisite. Different remedies, so different messages. Landed:
      `_loop_stall_reason` now calls `_first_startable_candidate` when the generic non-terminal
      breakdown is non-empty, and — when the queue turns out to be all-gated — reports counts split
      by `refusal.unmet` ("N still awaiting a prerequisite's approval") versus `refusal.rejected`
      ("M gated on a rejected prerequisite that will not clear on its own"), joined when both are
      present.
- [x] 9.9 Test that a rejected-gated queue does **not** stop the loop, and that reversing the
      rejection and approving revives it with no further operator action. Landed as
      `test_reversing_a_rejection_revives_a_stalled_loop_with_no_further_action` — confirms the
      stall message names "rejected", then flips the prerequisite `rejected → pending` by hand
      (the only operator-reachable route back per design D10) and reclaims with zero action on the
      dependent.
- [x] 9.10 Confirm the board's derivation agrees with the firing's for a gated queue — the same
      13.1 property, now with dependencies in it. Found genuinely disagreeing:
      `_batch_loop_summaries` (`hub/hub/api/v1/jobs.py`) picked its "current" candidate from the
      same ordered query but with no gate check at all, so it would have shown a gated task as
      current while the firing skipped past it. Fixed by mirroring
      `_first_startable_candidate`'s rule inline (an `in_progress` row needs no check; every other
      candidate is tested against `dependency_gate.evaluate` and skipped if refused) rather than
      reusing the scheduler helper directly, since this function walks candidates for **many**
      loops in one query and needs to track "already resolved" per `loop_id`. Landed as
      `test_the_board_summary_agrees_with_the_firing_for_a_gated_queue`. **Caveat, stated rather
      than glossed**: this adds one `dependency_gate.evaluate` query per skipped-gated candidate
      across the whole batch, which is no longer the "six fixed queries" `_batch_loop_summaries`'s
      own docstring promises (design D7) — proportional to how many loops in the batch are
      currently gated, not to the number of jobs. Acceptable for now (a gated loop is the
      exception, not the common case) but worth a note if a project ever runs many loops gated at
      once.

**Verified, not assumed.** `pytest hub/tests/test_loop_claim_dependency_gate.py
hub/tests/test_scheduler.py hub/tests/test_dependency_gate.py hub/tests/test_task_dependency_reads.py
hub/tests/test_jobs.py hub/tests/test_loop_archival.py -q` → **107 passed, 1 skipped**. `ruff
check`/`black --check` clean on `hub/hub/scheduler.py`, `hub/hub/api/v1/jobs.py`, and the new test
file. `mypy` on the two touched non-test files: no errors attributable to either (checked against
lines outside the diff, same method every prior section used). Full `hub/tests/` suite run twice
this section, in the **foreground** per `NEVER_BACKGROUND_AND_WAIT`: once before touching code
(baseline with sections 5-7 in the tree, confirming the concurrent session's section 7 landing:
**2711 passed, 12 skipped, 1 xpassed, 0 failed in 891s**) and once after section 9's changes:
**2718 passed, 12 skipped, 1 xpassed, 0 failed in 925s** — exactly seven more passing tests than
the baseline, matching the seven new tests this section adds (9.1, 9.2, 9.3, 9.4, 9.5, 9.9, 9.10),
zero failures either side.

## 10. Verification an agent can do

- [x] 10.0 **Check group 1 first.** It was reopened on 2026-08-21, after implementation had moved
      past it, to add the reviewer field (1.6–1.8, design D11). A worker walking groups in order will
      have skipped them. This change is not complete until they are done, and
      `loop-becomes-a-flow`'s reviewer resolution depends on the field existing. Confirmed: 1.6, 1.7
      and 1.8 are all ticked (landed run3 iteration 1, commit `5dbf316`) before this section started.
- [x] 10.1 `py -3.11 -m pytest hub/tests/ -q --ignore=hub/tests/browser` passes. Run in the
      **foreground** per `NEVER_BACKGROUND_AND_WAIT` (the Bash tool auto-backgrounded it past its
      600s cap; polled to completion with a blocking `TaskOutput` rather than ending the turn):
      **2724 passed, 12 skipped, 1 xpassed, 0 failed in 870.77s (14m30s)**. +4 over the prior
      (iteration 1's) baseline of 2720 — 1 is this section's own new test (10.4); the other 3 are a
      concurrent interactive session's uncommitted `hub/hub/scheduler.py`/`hub/tests/test_scheduler.py`
      work, present in the working tree throughout (per `CONCURRENT_SESSION_IS_EXPECTED`, left
      untouched and unstaged). Zero failures either side.
- [x] 10.2 `py -3.11 -m pytest tests/ -q` passes. **404 passed, 3 skipped in 17.56s** — matches the
      run's own CLI baseline exactly.
- [x] 10.3 `ruff check hub/`, `black --check hub/`, `mypy hub/hub/` clean on touched files;
      `cd hub/ui && npm run lint`. `ruff check hub/ tests/` and `black --check hub/ tests/` both
      clean (393 files). `mypy hub/spec_payload.py hub/spec_tasks.py hub/dependency_gate.py
      hub/task_transition_service.py hub/spec_completeness.py hub/spec_lifecycle.py` — the six files
      this change actually touches — reports only two pre-existing patterns, neither a regression:
      an untyped `refusal` constructor parameter on `DependencyUnmetError`
      (`task_transition_service.py:98`) mirrors the identical, older `GateUnsatisfiedError` right
      above it (`:82`) exactly; and `transition.reported_advisories = reported` (`:277`) is a
      deliberately dynamic, non-persisted attribute the surrounding comment already explains, unre-
      lated to this change. Whole-package `mypy hub/` carries 377 pre-existing errors across files
      this change never touches (mostly missing return annotations in `agent_actions.py`/`main.py`)
      — that is the repo's standing baseline, not something section 10 introduced or is scoped to
      fix. `cd hub/ui && npm run lint` — exit 0, no output past the command line.
- [x] 10.4 Test the whole chain: document declares A → B → C, approve, confirm B cannot start until A
      is **approved** (not merely completed), and C not until B is. Nothing exercised this end to end
      through a real *declared* chain before — the gate's own tests
      (`hub/tests/test_dependency_gate.py`) and the HTTP wiring tests
      (`hub/tests/test_task_transitions_api.py`) both build `TaskDependency` rows by hand. Added
      `test_the_whole_chain_gates_hop_by_hop_on_approved_not_completed`
      (`hub/tests/test_spec_task_dependencies.py`): a document declares A, B (`depends_on: [A]`), C
      (`depends_on: [B]`), approved for real through the document phase routes (materialising real
      edges), then each task is walked hop by hop through the real operator `PATCH
      /tasks/{id}` route. Confirms B is refused (409, `dependency_unmet`) while A is only
      `in_progress`/`completed`, unblocks once A reaches `approved`; C is refused while B is
      unstarted AND while B is merely `in_progress`, unblocks only once B reaches `approved`.
- [x] 10.5 Test a cross-document import end to end: approve document 1, import its task into document
      2, approve 2, confirm the edge points at the existing task and no duplicate was created.
      Already covered: `test_an_import_resolves_to_the_existing_task_without_creating_one`
      (`hub/tests/test_spec_task_dependencies.py`, section 4) does exactly this — approves a source
      document, imports its task into a second document via `from`, approves the second, asserts
      exactly one new task was created and the import resolves to the source document's existing
      task id.
- [x] 10.6 Test the regression case: A approved, C started, A → revision_needed. C's status is
      unchanged and C is reported as running on a regressed prerequisite. Already covered:
      `test_dependency_state_is_running_on_regressed` (`hub/tests/test_task_dependency_reads.py`,
      section 7) builds exactly this sequence via `apply_transition` and asserts, over the real
      `GET /tasks/{id}` route, both `status == "in_progress"` (unchanged) and
      `dependency_state == "running_on_regressed"`.
- [x] 10.7 Test the rejected case: A rejected, B refused with a message naming A and distinguishable
      from "not yet approved". Already covered at the gate layer
      (`test_a_rejected_prerequisite_gates_permanently_with_a_different_message`,
      `test_an_unmet_but_not_rejected_prerequisite_says_not_yet_approved`, both
      `hub/tests/test_dependency_gate.py`) and at the HTTP layer
      (`test_a_rejected_prerequisite_reads_differently_from_an_unmet_one_over_http`,
      `hub/tests/test_task_transitions_api.py` — asserts `detail["rejected"]` is truthy and
      `detail["unmet"]` is empty, the distinguishing shape).
- [x] 10.8 Confirm `spec_completeness`'s existing checks are unchanged — this change adds three and
      must alter none. `pytest hub/tests/test_spec_completeness.py -q` → **24 passed**, all
      pre-existing checks (`depends_on_unresolved`, `dependency_cycle`, `import_not_approved` are
      the three this change added, landed and tested in section 2) exercised unaltered.
- [x] 10.9 Confirm the seven-column board's tests still pass untouched. `npx vitest run
      src/__tests__/tasksBoardFilter.test.tsx` (`hub/ui`) → **4 passed**, file untouched by this or
      any prior task-dependencies section.

## 11. Verification only a human can do

- [ ] 11.1 **The shape is legible.** Open the board for a real decomposition. The order of work is apparent without reading a single description.
- [ ] 11.2 **The stall is diagnosable.** Let a layer sit completed and unreviewed. The board says work is waiting on review — not merely that downstream cards are gated. If this reads as "the feature is broken", it is.
- [ ] 11.3 **The gate is honest in a live run.** Ask an agent to start a task whose prerequisite is unapproved. The refusal tells it what to wait for, in words it can act on.
- [ ] 11.4 **The review chain is bearable.** Walk a three-deep chain with two agents. Judge whether the review cost per wave is acceptable — this is the change's main risk and only real use answers it.
- [ ] 11.5 **The board does not lie about foreign work.** With a cross-document import, confirm the reference names the owning document and that the blocker is reachable from it.
- [ ] 11.6 **Collapse behaves.** Finish a layer, confirm it collapses, expand it, confirm the graph still reads.
- [ ] 11.7 **Structure really is read-only.** Try to drag, delete, or otherwise alter an edge. Confirm the refusal explains itself rather than nothing happening.
- [ ] 11.8 **The picker earns its place.** Confirm outstanding counts make choosing a board and seeing what is left one act.

## 12. User test guide

- [x] 12.1 Write the operator-facing test guide: what to declare, in what order to approve, what should be startable at each point, and what should not. Lead with 10.2 — an unattended review backlog and a broken dependency gate look identical from the outside, and if the board cannot tell them apart the feature is unusable no matter how correct the graph is.

**Setup.** A project registered against the trial Hub on port 8010 — never the Hub whose code is
being edited. Any project works; nothing here needs the corpus other changes rely on. Section 8
(the board UI) is not built yet, so this guide drives the API directly rather than a picture — the
same calls the future board will make.

**Lead with the confusion 10.2 warns about.** Before testing anything else, put one task in
`under_review` with no dependents and leave it there. `GET /tasks/{id}` on anything gated behind it
should read `dependency_state: "gated"` — the SAME word a task waiting on an unapproved-but-not-yet-
reviewed prerequisite gets. *If your instinct on seeing "gated" is "is the gate broken, or is
someone just behind on review?" — that is the real question this feature has to answer legibly, and
today the read model does not distinguish the two.* This is not a bug to file; it is the thing to
watch for across every step below, because a UI that cannot answer it will look broken even when
every line of backend code is correct.

1. **Declare a chain.** Create a document (`POST .../project/documents`), submit it
   (`submit_spec_document` or `POST /agent-actions/spec/documents`) with three tasks: `A`, `B`
   (`"depends_on": ["A"]`), `C` (`"depends_on": ["B"]`). Approve the document (`close-exploration`,
   then `phase` to `proposed`, then `approved`).
   *Expect:* `GET /tasks` shows three new tasks, each `pending`, `dependency_state: null` on A
   (nothing gates it), `"gated"` on B and C.
   *Failure looks like:* a task missing, or B/C already startable — the edges did not materialise.

2. **B is refused, not merely warned.** `PATCH /tasks/{B_id}` with `{"status": "in_progress"}`.
   *Expect:* HTTP 409, `detail.code == "dependency_unmet"`, `detail.unmet` names A by id and title.
   *Failure looks like:* 200 — the gate did not fire — or a 409 with no usable detail, forcing you
   to already know why.

3. **Completed is not enough.** Walk A: `PATCH ... in_progress`, then `completed`. Repeat step 2's
   PATCH on B.
   *Expect:* still 409. A task's prerequisite must reach `approved`, not merely `completed` — a
   completed-but-unreviewed prerequisite is exactly the "review backlog, not a broken gate" case the
   lead-in above describes.
   *Failure looks like:* 200 — the gate is checking the wrong status.

4. **Approved unblocks exactly one hop.** Walk A the rest of the way: `under_review`, `approved`.
   Retry B's `PATCH ... in_progress` — expect 200. Immediately retry C's — expect still 409, because
   C depends on B, not A, and B has only just started.
   *Failure looks like:* C unblocks too — dependencies are being resolved transitively when they
   should not be, or the wrong edge was recorded.

5. **The rejected case reads differently from the unmet case.** Reject a task with a dependent
   (`PATCH` the prerequisite to `rejected`), then try to start the dependent.
   *Expect:* 409, but `detail.rejected` is non-empty and `detail.unmet` is empty — distinguishable
   from step 2's response without reading prose, by a client that only branches on the shape.
   *Failure looks like:* the same `unmet` shape as an ordinary gate refusal — a rejected prerequisite
   reads as "come back later" instead of "this is never starting."

6. **A regression flags the dependent without stopping it.** With B now `in_progress` (from step 4),
   walk A backwards: `PATCH /tasks/{A_id} {"status": "revision_needed"}` (operator-only edge).
   `GET /tasks/{B_id}`.
   *Expect:* `status` is still `"in_progress"` — B is not halted — but `dependency_state` reads
   `"running_on_regressed"`.
   *Failure looks like:* B silently reverts or stops (the gate should never re-evaluate a task that
   has already started), or `dependency_state` still reads `null`, hiding that its prerequisite went
   backwards under it.

7. **A cross-document import points at the same task, not a copy.** In a second document, declare a
   task whose `from` names document 1's path and A's key, plus a task naming that import as its
   `depends_on`. Approve document 2.
   *Expect:* the response's `tasks_created` has exactly one new task (the importing task) — the
   imported entry resolves to A's existing id rather than minting a second row. `GET
   /tasks/{importer_id}` shows the prerequisite is A, in the OTHER document.
   *Failure looks like:* two rows for what should be one task, or the new task's prerequisite is a
   phantom with no document behind it.

**What "done" looks like across all seven:** every refusal names a real task the operator (or the
next agent) can go act on, no gate ever fires on a task that has already legitimately started, and
"waiting on review" is at minimum distinguishable from "waiting on the gate" if you already know to
compare `status` against `dependency_state` — which, per the lead-in, is not the same as the board
being able to show that distinction on its own. That gap is section 8's to close, not this guide's.
