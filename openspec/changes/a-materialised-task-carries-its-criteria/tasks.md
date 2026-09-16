# Tasks: a materialised task carries its criteria

Round discipline: R1 wrote proposal/design/specs. **R2 and R3 each independently re-derive the
argument against the code before any of §2 is written.** Nothing below §1 may be ticked on the
strength of a plan existing — only on a real, verified result, with the command and its output named
in the task's own Done note.

## 1. Verification rounds, before any implementation

- [x] 1.1 **R2**: re-derive the problem against the code independently.
      **Done.** All four confirmed from the files: `materialise()`'s `Task(...)` at
      `spec_tasks.py:205-217` sets nine fields and not `acceptance_criteria`; `AcceptanceCriterion`
      is `key`/`requirement`/`given`/`when`/`then` at `spec_payload.py:91-100` and its `requirement`
      is tied to a requirement **key** by `validate_payload`'s `known` set (`:264-277`); the
      criteria block at `scheduler.py:2456-2460` sits at the same indent as the `description` block,
      **outside** the `if is_review` / `else` at `:2441-2452`, so it renders for both roles; and
      `_briefing_evidence_lines` returns `[]` when `is_review` at `:2316-2318`.
- [x] 1.2 **R2**: answer design D2's open question (criterion key prefixed or not).
      **Done — include it.** Reason recorded in design D2: the rendered string is the only carrier
      and D5 forbids backfill, so omission is lossy and irreversible while inclusion costs about a
      dozen characters. This overturns R1's reasoning, which had applied D1's "don't build for a
      consumer that does not exist" without weighing the asymmetry.
- [x] 1.3 **R2**: test D3's key-vs-identifier hazard *by measurement*.
      **Done — the hazard does not exist; D3 is rewritten.** Ran `validate_payload` directly from
      `hub/`: a task entry with `requirements=["REQ-0001"]` is **refused** —
      *"tasks[0].requirements[0]: names requirement 'REQ-0001', which this document does not
      define"* — while `requirements=["req-a"]` is accepted. Separately, `spec_identity.read_identity`
      returns a key→identifier map (`spec_identity.py:31-32,42-44`), so `materialise()`'s
      `by_identifier` branch at `:190` is a key-to-identifier remap, not identifier support.
      Consequence: match on the payload key the entry named, **not** the resolved row's `.key`,
      which `spec_index.py:216-218` explicitly allows to move.
- [x] 1.4 **R2**: verify that `validate_payload` refuses a criterion whose `requirement` names
      nothing. **Done — confirmed by running it**, not inferred: refused with
      *"acceptance_criteria[0].requirement: names requirement 'req-missing', which this document
      does not define"*; the control naming `req-a` was accepted.
- [x] 1.4b **R2**: new finding — `materialise_quietly` catches every exception and returns `[]`
      (`spec_tasks.py:416-423`), so a raise inside criteria-matching creates **no tasks at all**
      while the approval reports success. Recorded as design D6; adds tasks 2.5 and 3.11.
- [ ] 1.5 **R3**: re-derive independently of R2 — a fresh comparison of the proposal against the
      code, not a re-read of R2's notes. Report anything R2 confirmed that does not hold.
- [ ] 1.6 **R3**: measure the worst-case briefing a *valid* document can produce (most criteria
      attachable to one task) and decide whether `agent-loops`' briefing bound must be modified. If
      yes, this change gains a delta spec for `agent-loops` and the proposal's Capabilities section
      is corrected.
- [ ] 1.7 **R3**: confirm the corpus measurement independently — re-run the 18/18 vs 0/32 split
      read-only against the live database, and say whether it still holds.

## 2. Implementation

- [ ] 2.1 Read the document's `acceptance_criteria` inside `materialise()`, indexed by the
      requirement key each names.
- [ ] 2.2 For each created task, attach the criteria whose `requirement` is one of the names in that
      entry's own `requirements` list — `named`, **not** the resolved row's `.key` (design D3 as
      corrected by R2) — in document order (design D4).
- [ ] 2.3 Render each criterion to one string per design D2, prefixed with the criterion key
      (`<key>: Given ..., when ..., then ...`) per task 1.2.
- [ ] 2.5 Make the whole path total (design D6): no indexing that can raise, no assumption that the
      stored payload's `acceptance_criteria` is present, is a list, or holds well-formed entries.
- [ ] 2.4 Leave `acceptance_criteria` unset when a task resolves no requirement, or when no
      criterion names any of its requirements — not an empty list where `None` is today's value,
      unless a test establishes that readers cannot tell the difference.

## 3. Tests

Each pins a scenario from `specs/spec-document-authority/spec.md`.

- [ ] 3.1 A task's criteria follow its requirements.
- [ ] 3.2 Criteria belonging to other requirements are not attached.
- [ ] 3.3 A task naming several requirements carries all their criteria.
- [ ] 3.4 A task naming no requirement carries no criteria, and approval is not refused.
- [ ] 3.5 A requirement with no criteria contributes nothing, and approval is not refused.
- [ ] 3.6 Criterion order follows the document (design D4).
- [ ] 3.7 A requirement whose row `key` has drifted from the payload key still gets its criteria —
      the case D3 now turns on. Replaces R1's key-vs-identifier test, which pinned a case task 1.3
      measured to be impossible.
- [ ] 3.11 A stored payload whose `acceptance_criteria` is malformed (absent, not a list, or holding
      entries without the expected fields) still creates its tasks, with no criteria and no raise
      (design D6). Assert through `materialise_quietly`, since that is the path approval uses and
      the one that would hide a raise.
- [ ] 3.8 Every attached criterion carries its given, its when and its then.
- [ ] 3.9 Re-approval does not revisit or duplicate criteria on an already-created task (design D5).
- [ ] 3.10 A created task's criteria render into a loop briefing as one line per criterion — the
      `scheduler.py:2456-2460` path, not only the model field.

## 4. Mutation checks

Each mutation is applied to the implementation, the suite is run, the result recorded, and the
mutation reverted with `git checkout`. A mutation that flips no test means the tests above do not
pin what they claim to.

- [ ] 4.1 Match criteria on the resolved row's `.key` instead of the entry's `named` → 3.7 fails.
- [ ] 4.6 Let a malformed criterion entry raise instead of being skipped → 3.11 fails, and fails by
      producing *no tasks*, which is the point of D6.
- [ ] 4.2 Attach every criterion in the document regardless of requirement → 3.2 fails.
- [ ] 4.3 Drop the `then` from the rendered string → 3.8 fails.
- [ ] 4.4 Sort criteria by key instead of document order → 3.6 fails.
- [ ] 4.5 Attach criteria to tasks resolving no requirement → 3.4 fails.

## 5. Whole-suite and quality gates

- [ ] 5.1 `py -3.11 -m pytest tests/ -q` from `hub/` — full suite, zero new failures. Record the
      counts.
- [ ] 5.2 `ruff check src/ hub/ tests/`, `black --check src/ hub/hub/ hub/tests/ tests/
      --target-version py311`, `mypy src/` — clean.
- [ ] 5.3 `openspec validate --strict a-materialised-task-carries-its-criteria` — passes.

## 6. Drive

- [ ] 6.1 On the **trial** Hub (`:8010`, from source, per `.claude/reference/hubs.md`) — never
      `:8000` — approve a document declaring a task with criteria, and confirm the created task
      carries them.
- [ ] 6.2 Confirm they reach a real turn: fire a loop on that task and read the briefing the agent
      actually received, rather than inferring it from the model field.
- [ ] 6.3 Confirm the task drawer renders them in the UI without a bundle change.

## 7. Close-out

- [ ] 7.1 Update `openspec/explorations/2026-09-16-the-flow-costs-more-than-the-work.md` §12 to
      record item 1 as built, and note that per design D5 the effect is only measurable on tasks
      created after this ships.
- [ ] 7.2 `openspec archive` once the operator has approved.

## 8. Human-only, not agent-verifiable

- [ ] 8.1 Whether the rendered criterion line reads well to a person in the task drawer.
- [ ] 8.2 Whether criteria in the briefing measurably shorten a review turn — needs a real project
      over real time, and per design D5 only on newly created tasks.
