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
- [x] 1.5 **R3**: re-derive independently of R2.
      **Done — R2's central justification does not hold.** R2 argued that the criterion's
      `requirement` and the entry's `requirements` "cannot disagree" because both are validated
      against the same `known` set. But the approval route reads the file and parses it with
      `extract_payload`, **not** `validate_payload` (`api/v1/spec.py:1533-1537`), and
      `spec_adoption.py` never validates at all (`:39,190-230`). `validate_payload` therefore
      constrains what can be *saved through the Hub* and says nothing about what `materialise()`
      receives. D3's conclusion (match on `named`) survives on the replacement reason recorded in
      design: both fields come from the same file and are self-consistent within it. D6 is upgraded
      from prudent to load-bearing. New accepted consequence + test 3.12.
- [x] 1.6 **R3**: decide whether `agent-loops`' briefing bound must be modified.
      **Done — no, and the proposal's Capabilities section stands unchanged.** The criteria block
      (`scheduler.py:2456-2460`) and the prior checkpoint (`:2462-2471`) are appended to the same
      `lines` list in sequence, so criteria cannot displace or truncate the checkpoint; the only cap
      in `_compose_loop_briefing` is `_LOOP_BRIEFING_CHECKPOINT_CHARS = 4_000` (`:2043`) and it
      applies to the checkpoint alone. And the existing requirement is justified by growth *over
      time* ("a long-running loop's accumulated history"), which criteria do not do — they are fixed
      by the document. Residual length growth is accepted and recorded; the measurement moves to 5.4.
- [x] 1.7 **R3**: confirm the corpus measurement independently.
      **Done — holds, and more precisely than R1 stated it.** Re-run read-only against the live
      database: hand-made n=18 with 0 NULL and 0 `[]`; spec-materialised n=32 with **32 NULL and 0
      `[]`**. The field is never written by `materialise()` rather than written empty, which
      independently confirms task 2.4's instruction to leave it unset.

- [x] 1.8 **R4**: probe the reused helper (design D7) directly against hostile payloads rather than
      trusting the review's read of it. **Done.** Ran `criteria_by_requirement_key` from `hub/`
      over ten shapes. `None`, a non-dict payload, an absent key, `None`, a string, a dict and a
      list of scalars all degrade to `{}`; **`{"acceptance_criteria": 5}` raises
      `TypeError: 'int' object is not iterable`**, confirming the review's hole and making task
      2.1's `isinstance` guard load-bearing.
- [x] 1.9 **R4**: new finding — the helper preserves a missing handle as `None`, so D2's rendering
      emits the literal `"None: Given g, when w, then t"`, and a criterion declaring nothing at all
      emits `"None: Given None, when None, then None"`. Neither raises; **both violate the
      identifiability requirement the review's own fix added**, and the second injects noise into
      the reviewer's briefing. Recorded as design D8; changes task 2.3 and the delta spec.
- [x] 1.10 **R4**: check whether anything can overwrite a task's criteria after creation.
      **Done — nothing can.** `acceptance_criteria` is on `TaskCreate` only
      (`schemas/tasks.py:45,64`, written at `api/v1/tasks.py:770`); it is absent from `TaskUpdate`
      (`:120-142`) and from MCP `update_task(task_id, status, notes)`. The hazard of an agent
      clearing its own standard does not exist. But D5 is thereby **permanent** for the 32 existing
      tasks: no supported route can ever give them criteria.
- [x] 1.11 **R4**: the review's new scenario *"Attaching criteria changes nothing about which tasks
      exist"* was phrased as approving one document twice, which `existing_keys` makes a no-op and
      therefore vacuous. Reworded to two documents, and it now pins counts, titles and keys.

## 2. Implementation

- [ ] 2.1 Add the `isinstance(..., list)` guard **inside** `spec_reading.criteria_by_requirement_key`
      (`hub/hub/spec_reading.py:98`), not at this change's call site (design D7, corrected by the
      second review): the helper's other caller, `requirement_view` at `:130` reached from
      `read_spec_document` (`api/v1/agent_actions.py:1399`), parses the same unvalidated file with
      no `try`/`except`, so guarding only the new call site leaves the same `TypeError` returning a
      500 there. `hub/tests/test_spec_reading.py:213` already covers the helper.
- [ ] 2.2 Call `criteria_by_requirement_key(payload)` **once, before the per-entry loop** (design
      D6/D7). For each created task, take its entry's `requirements` names — de-duplicated,
      first-appearance order — and concatenate their groups **in `payload.requirements` declaration
      order**, keeping each group's internal order (design D4 as reversed by the second review, to
      match `spec_render._acceptance` at `hub/hub/spec_render.py:305-318`). Match on `named`, the
      payload key, **not** the resolved row's `.key` (design D3). A repeated name is not refused
      anywhere — `spec_payload.py:279-285` checks membership only, and the approval path does not
      validate — so the de-duplication is load-bearing, not tidiness.
- [ ] 2.3 Render each criterion to one string per design D2 and D8: prefix the handle
      **only when it is a non-empty string** (`<key>: Given ..., when ..., then ...`), otherwise
      render `Given ..., when ..., then ...` with no prefix. Never emit the literal `None` for an
      absent part.
- [ ] 2.6 Skip a criterion whose `given`, `when` and `then` are all absent (design D8) — it states
      no standard. A partially absent one is still attached, with the parts it has.
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
- [ ] 3.11 A stored payload whose `acceptance_criteria` is malformed (absent, not a list, a scalar,
      or holding entries without the expected fields) still creates its tasks, with no criteria and
      no raise (design D6/D7). Assert through `materialise_quietly`, since that is the path approval
      uses and the one that would hide a raise. **The document MUST declare at least two tasks with
      the fault reachable on the second**, and the test MUST assert that *both* exist — a
      single-entry fixture passes accidentally and proves nothing, because the flush is inside the
      per-entry loop (`spec_tasks.py:218-219`). **A payload that never passed `validate_payload` is
      the realistic case, not a contrived one** — see task 1.5.
- [ ] 3.13 A task's criteria carry the criterion key, and two criteria on the same requirement are
      distinguishable from one another (design D2). Without this, D2's decision — argued as
      irreversible because D5 forbids backfill — is pinned by nothing.
- [ ] 3.14 An entry naming the same requirement twice attaches that requirement's criteria once,
      not twice (task 2.2).
- [ ] 3.15 Criteria that interleave in the document are attached **grouped by requirement, in
      `payload.requirements` declaration order, stable within a requirement** — the same order
      `spec_render._acceptance` renders the document's own acceptance table in (design D4 as
      reversed). **This test is inverted from its original form**, which asserted payload order.
- [ ] 3.20 A criteria block longer than the bound is included up to it and the truncation is
      visible, not silently dropped (the `agent-loops` delta). Assert on the composed briefing.
- [ ] 3.21 An entry whose requirements are all already served by existing work creates no task, and
      the approval is not refused — the `already_served` skip at `spec_tasks.py:169,196-202`, which
      no round had named and which makes scenario 1's premise satisfiable while its conclusion fails.
- [ ] 3.16 A criterion with no handle is attached with its given/when/then and **no `None` appears
      anywhere in the rendered string** (design D8). Assert on the string, not on the model field —
      the defect is in what a reader sees.
- [ ] 3.17 A criterion with no given, no when and no then is not attached, and the task is still
      created (design D8, task 2.6).
- [ ] 3.18 A payload whose `acceptance_criteria` is a scalar (`5`) creates every declared task with
      no criteria and no raise — the exact `TypeError` task 1.8 measured, through
      `materialise_quietly`.
- [ ] 3.19 Two documents declaring the same tasks, one with criteria and one without, create the
      same tasks with the same titles and keys, differing only in criteria (the review's scenario as
      R4 reworded it — the one-document phrasing was vacuous under `existing_keys`).
- [ ] 3.12 A file whose task entries and criteria use different namespaces attaches no criteria to
      those tasks, creates them anyway, and does not raise (design D3's accepted consequence).
- [ ] 3.8 Every attached criterion carries its given, its when and its then.
- [ ] 3.9 Re-approval does not revisit or duplicate criteria on an already-created task (design D5).
- [ ] 3.10 A created task's criteria render into a loop briefing as one line per criterion — the
      `scheduler.py:2456-2460` path, not only the model field.

## 4. Mutation checks

Each mutation is applied to the implementation, the suite is run, the result recorded, and the
mutation reverted with `git checkout`. A mutation that flips no test means the tests above do not
pin what they claim to.

- [ ] 4.1 Match criteria on the resolved row's `.key` instead of the entry's `named` → 3.7 fails.
- [ ] 4.6 Let a malformed criterion entry raise instead of being skipped → 3.11 fails, **and fails
      by leaving a committed partial board** (the entries before the fault, with no dependency
      edges), not by producing no tasks. Record which rows survived: that is the observation the
      mutation exists to make, and the reason 3.11 needs two entries.
- [ ] 4.7 Render without the criterion key → 3.13 fails.
- [ ] 4.8 Order criteria by raw `payload.acceptance_criteria` position instead of by requirement
      → 3.15 fails. **Inverted from its original form**, which mutated toward grouping and would
      have been satisfied by the prescribed implementation itself once D7 mandated the helper — the
      contradiction the second review found.
- [ ] 4.12 Skip the de-duplication of an entry's repeated requirement names → 3.14 fails.
- [ ] 4.13 Remove the criteria bound from the briefing → 3.20 fails.
- [ ] 4.9 Always prefix the handle, including when it is absent → 3.16 fails (the string contains
      `None:`).
- [ ] 4.10 Remove the `isinstance(..., list)` guard from task 2.1 → 3.18 fails, and fails by
      creating no tasks, which is D6's failure mode reproduced deliberately.
- [ ] 4.11 Attach criteria that state nothing → 3.17 fails.
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
- [ ] 5.4 Measure what this actually adds to a briefing (carried from R3's task 1.6): for a real
      approved document, record the character count the criteria block contributes against the
      4,000-character checkpoint bound it sits beside. The ceiling is three requirements' worth of
      criteria (`spec_completeness.MAX_REQUIREMENTS_PER_TASK = 3`), but that cap is enforced only on
      the transition to `proposed`, so do not assume it for an adopted document. Record the number;
      propose a bound only if the measurement asks for one.

## 6. Drive

- [ ] 6.1 On the **trial** Hub (`:8010`, from source, per `.claude/reference/hubs.md`) — never
      `:8000` — approve a document declaring a task with criteria, and confirm the created task
      carries them.
- [ ] 6.2 Confirm they reach a real turn: fire a loop on that task and read the briefing the agent
      actually received, rather than inferring it from the model field.
- [ ] 6.3 Confirm the task drawer renders them in the UI without a bundle change.

## 7. Close-out

- [ ] 6.4 Confirm the briefing still spawns with a large criteria block: drive a task whose criteria
      approach the bound and verify the run starts. The briefing reaches the runner as one
      command-line argument (`scheduler.py:3088`, `runner_commands.py:268`), and `pty_runner.py:68-88`
      records a prior incident on that path — measure it, do not reason about it.
- [ ] 6.5 Add one sentence to `submit_spec_document`'s docstring in `hub/hub/mcp_server.py` saying
      that a requirement's acceptance criteria become the standard rendered into the implementer's
      and the reviewer's turn — the parallel of the existing "approving the document creates these
      as real tasks" line for `tasks` (`mcp_server.py:1731-1735`), which has no counterpart for
      `acceptance_criteria`. **`.claude/rules/` loads extra rules for `mcp_server.py` edits — read
      them first.**
- [ ] 7.1 Update `openspec/explorations/2026-09-16-the-flow-costs-more-than-the-work.md` §12 to
      record item 1 as built, and note that per design D5 the effect is only measurable on tasks
      created after this ships.
- [ ] 7.2 `openspec archive` once the operator has approved.

## 8. Human-only, not agent-verifiable

- [ ] 8.1 Whether the rendered criterion line reads well to a person in the task drawer.
- [ ] 8.2 Whether criteria in the briefing measurably shorten a review turn — needs a real project
      over real time, and per design D5 only on newly created tasks.
