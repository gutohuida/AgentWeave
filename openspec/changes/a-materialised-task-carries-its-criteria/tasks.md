# Tasks: a materialised task carries its criteria

Round discipline: R1 wrote proposal/design/specs. **R2 and R3 each independently re-derive the
argument against the code before any of §2 is written.** Nothing below §1 may be ticked on the
strength of a plan existing — only on a real, verified result, with the command and its output named
in the task's own Done note.

## 1. Verification rounds, before any implementation

- [ ] 1.1 **R2**: re-derive the problem against the code independently — do not read R1's prose
      first. Confirm or refute, each from the file: `materialise()` never assigns
      `acceptance_criteria`; the criteria exist on the payload with a `requirement` key; the
      briefing renders the field for reviewers; `_briefing_evidence_lines` returns `[]` for reviews.
- [ ] 1.2 **R2**: answer design D2's open question (criterion key prefixed or not) and record the
      reason in design.md.
- [ ] 1.3 **R2**: test D3's key-vs-identifier hazard *by measurement*, not by reading — construct a
      declared task naming its requirement by identifier and a criterion naming it by key, and
      establish what the proposed matching would do.
- [ ] 1.4 **R2**: verify the design.md claim that `spec_payload.validate_payload` already refuses a
      criterion whose `requirement` names nothing (`spec_payload.py:272-288`). Run it; do not infer.
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
- [ ] 2.2 For each created task, attach the criteria of the requirement rows that entry resolved,
      matching on the rows' `key` (design D3), in document order (design D4).
- [ ] 2.3 Render each criterion to one string per design D2, including the decision from task 1.2.
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
- [ ] 3.7 The key-vs-identifier case from design D3 and task 1.3.
- [ ] 3.8 Every attached criterion carries its given, its when and its then.
- [ ] 3.9 Re-approval does not revisit or duplicate criteria on an already-created task (design D5).
- [ ] 3.10 A created task's criteria render into a loop briefing as one line per criterion — the
      `scheduler.py:2456-2460` path, not only the model field.

## 4. Mutation checks

Each mutation is applied to the implementation, the suite is run, the result recorded, and the
mutation reverted with `git checkout`. A mutation that flips no test means the tests above do not
pin what they claim to.

- [ ] 4.1 Match criteria on requirement *identifier* instead of key → 3.7 fails.
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
