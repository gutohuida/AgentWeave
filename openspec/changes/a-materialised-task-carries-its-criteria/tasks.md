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
      **Annotated after the third review: this conclusion is right and its reasoning was incomplete.**
      The design's own test had two clauses -- displace the checkpoint *or overrun the job message* --
      and this answered only the first. The second review answered the second clause and added an
      `agent-loops` delta; the third review showed the figure justifying it was `362 x 12 x 3`
      rather than an observation, and the delta was removed. Net effect is this row's answer, but
      nobody should read it as having been established here.
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

- [x] 2.1 Add the `isinstance(..., list)` guard **inside** `spec_reading.criteria_by_requirement_key`
      (`hub/hub/spec_reading.py:98`) **and inside `statements_by_key` (`:72`)**, not at this
      change's call site (design D7). Two reasons, both found by review: the helper's other caller,
      `requirement_view` at `:130` reached from `read_spec_document`
      (`api/v1/agent_actions.py:1399`), parses the same unvalidated file with no `try`/`except`, so
      a call-site guard leaves the identical `TypeError` returning a 500 there; and task 2.2's
      ordering now reads `payload["requirements"]`, whose `or []` at `:72` is the same hole.
- [x] 2.2 Call `criteria_by_requirement_key(payload)` **once, before the per-entry loop** (design
      D6/D7). For each created task: reduce its entry's `requirements` names with
      **`dict.fromkeys(...)`**, preserving first-appearance order — **not a `set`**, whose iteration
      order for strings varies between processes, so two approvals of the same file would store the
      criteria in different orders (against the delta spec's ordering requirement). Collect every
      criterion the helper grouped under any of those names, then apply **one stable sort** keyed by
      `position.get(<the requirement key the criterion was grouped under>, len(position))`, where
      `position` comes from task 2.7. **The criterion dicts the helper returns do not carry their
      requirement** — `spec_reading.py:104-111` builds `key`/`given`/`when`/`then` only — so the sort
      key must come from the group the criterion was collected from, not from a field of it. A
      literal reading that looks for `criterion["requirement"]` gets `None` for every criterion, every
      key collapses to `len(position)`, and no sorting happens.
      **Relationship to `spec_render._acceptance`** (`hub/hub/spec_render.py:314-318`): same sort key,
      same `len(position)` fallback, and identical output for any document that ever passed
      `validate_payload`. It is **not** the same function — `_acceptance` sorts the flat criteria
      list while D7's helper groups first, so where **two or more** of an entry's requirements are
      absent from `payload["requirements"]` they share the `len(position)` tie key and this groups
      them by requirement where `_acceptance` would interleave them. That divergence is accepted and
      is what the delta spec's ordering requirement now states. **Do not concatenate per-requirement
      groups in the entry's own order**: that drops any criterion whose requirement is absent from
      `payload["requirements"]`, which the `len(position)` fallback deliberately keeps, sorted last.
      Match on `named`, the payload key, **not** the resolved row's `.key` (design D3).
- [x] 2.7 Build the `position` map by enumerating the keys of
      **`spec_reading.statements_by_key(payload)`** — not by iterating `payload["requirements"]`
      directly. Three reasons: that helper already carries task 2.1's guard, so the map is built
      through one guarded read rather than a second hand-rolled one; it returns only entries that are
      dicts with a non-empty string `key`, so a malformed element cannot raise here (a bare
      `{r["key"]: i for i, r in enumerate(payload["requirements"])}` raises
      `TypeError: string indices must be integers` on a string element); and it is what makes
      mutation 4.16 discriminating — an inline `isinstance` guard at this call site would satisfy the
      words "a guarded read" while leaving the helper's own hole open and 4.16 flipping nothing.
      `materialise()` has never read `requirements` before this change, so this is new exposure, not
      existing behaviour.
- [x] 2.3 Render each criterion to one string per design D2 and D8: prefix the handle
      **only when it is a non-empty string** (`<key>: Given ..., when ..., then ...`), otherwise
      render `Given ..., when ..., then ...` with no prefix. Never emit the literal `None` for an
      absent part.
- [x] 2.6 Skip a criterion whose `given`, `when` and `then` are all **absent or empty** (design D8) —
      it states no standard. `spec_payload.py:96-100` sets no `min_length` on any of the three, so
      `""` passes `validate_payload` and a test written against `is None` alone would emit
      `"Given , when , then "`. A partially absent one is still attached, with the parts it has.
- [x] 2.5 Make the whole path total (design D6): no indexing that can raise, no assumption that the
      stored payload's `acceptance_criteria` is present, is a list, or holds well-formed entries.
- [x] 2.4 Leave `acceptance_criteria` unset when a task resolves no requirement, or when no
      criterion names any of its requirements — not an empty list where `None` is today's value,
      unless a test establishes that readers cannot tell the difference.

## 3. Tests

Each pins a scenario from `specs/spec-document-authority/spec.md`.

**Done, all 25.** Written as `hub/tests/test_spec_criteria_reach_the_task.py`.
`py -3.11 -m pytest tests/test_spec_criteria_reach_the_task.py -q` from `hub/` — **25 passed**;
with the two neighbouring suites (`test_spec_declared_tasks.py`, `test_spec_reading.py`) — **45
passed, 0 failed**. `ruff check` and `black --check --target-version py311` on the new file — clean.
A section that passes on its first run pins nothing until it has been shown able to fail, so before
closing this: two mutations applied together — `rank = 0` in `_criteria_for_entry` (4.8b's shape)
and both `isinstance(raw, list)` guards replaced by `or []` (4.10/4.16's shape) — flipped **exactly
six**: 3.11, 3.15, 3.18, 3.22, 3.24, 3.25, and nothing else. Reverted with `git checkout`; the
suite is green again at 45. That is a smoke test of the section, not §4 — §4 applies all seventeen
properly, one at a time.

- [x] 3.1 A task's criteria follow its requirements.
      **Done** — `test_3_1_a_tasks_criteria_follow_its_requirements`.
- [x] 3.2 Criteria belonging to other requirements are not attached.
      **Done** — `test_3_2_criteria_belonging_to_other_requirements_are_not_attached`.
- [x] 3.3 A task naming several requirements carries all their criteria.
      **Done** — `test_3_3_a_task_naming_several_requirements_carries_all_their_criteria`.
- [x] 3.4 A task naming no requirement carries no criteria, and approval is not refused.
      **Done** — `test_3_4_a_task_naming_no_requirement_carries_no_criteria`.
- [x] 3.5 A requirement with no criteria contributes nothing, and approval is not refused.
      **Done** — `test_3_5_a_requirement_with_no_criteria_contributes_nothing`.
- [x] 3.6 Criteria for a SINGLE requirement keep the order the document wrote them in (the stable
      half of design D4). The cross-requirement half is 3.15's; an earlier wording said only "order
      follows the document", which became ambiguous when D4 was reversed. **The fixture's criterion
      keys MUST NOT be in alphabetical order**, or mutation 4.4 (sort by key within a requirement)
      produces the same list and flips nothing.
      **Done** — `test_3_6_criteria_for_one_requirement_keep_the_order_the_document_wrote`.
- [x] 3.7 A requirement whose row `key` has drifted from the payload key still gets its criteria —
      the case D3 now turns on. Replaces R1's key-vs-identifier test, which pinned a case task 1.3
      measured to be impossible.
      **Done** — `test_3_7_a_requirement_whose_row_key_has_drifted_still_gets_its_criteria`.
- [x] 3.11 A stored payload whose `acceptance_criteria` is malformed (absent, not a list, a scalar,
      or holding entries without the expected fields) still creates its tasks, with no criteria and
      no raise (design D6/D7). **One of the shapes MUST be a list holding a NON-DICT element** (a
      string, say — or `acceptance_criteria: "abc"`, whose characters iterate as non-dicts).
      `spec_reading.py:105-111` reads every field with `.get()`, so a dict merely missing `key`,
      `given`, `when` or `then` raises nothing even with the skip removed, and mutation 4.6 would
      flip on no shape in the list. Assert through `materialise_quietly`, since that is the path approval
      uses and the one that would hide a raise. **The document MUST declare at least two tasks and
      the test MUST assert that both exist** — that is what proves totality. (An earlier wording
      required "the fault reachable on the second entry"; that is unconstructible, because a
      payload-level malformation is uniform across entries and, with the index built once before
      the loop, raises before any `session.add`.) **A payload that never passed `validate_payload`
      is the realistic case, not a contrived one** — see task 1.5.
      **Done** — `test_3_11_a_malformed_criteria_block_still_creates_every_declared_task`.
- [x] 3.13 A task's criteria carry the criterion key, and two criteria on the same requirement are
      distinguishable from one another (design D2). Without this, D2's decision — argued as
      irreversible because D5 forbids backfill — is pinned by nothing.
      **Done** — `test_3_13_criteria_carry_their_key_and_are_distinguishable`.
- [x] 3.14 An entry naming the same requirement twice attaches that requirement's criteria once,
      not twice (task 2.2).
      **Done** — `test_3_14_an_entry_naming_a_requirement_twice_attaches_its_criteria_once`.
- [x] 3.15 Criteria interleaved in the document are attached in `payload.requirements` declaration
      order, stable within a requirement — the order `spec_render._acceptance` uses. **The entry
      MUST list its requirements in the reverse of `payload.requirements` order**, or the test does
      not discriminate: a naive entry-order implementation and the correct one agree whenever the
      two orders coincide. (Inverted from its original form, which asserted payload order.)
      **Done** — `test_3_15_interleaved_criteria_follow_the_documents_requirement_order`.
- [x] 3.21 An entry whose requirements are all already served by existing work creates no task, and
      the approval is not refused — the `already_served` skip at `spec_tasks.py:169,196-202`, which
      no round had named and which makes scenario 1's premise satisfiable while its conclusion fails.
      **Done** — `test_3_21_an_entry_already_served_by_hand_made_work_creates_no_task`.
- [x] 3.22 `requirement_view` over a payload whose `acceptance_criteria` is a scalar returns rather
      than raising — the `read_spec_document` path (`api/v1/agent_actions.py:1399`). Without this,
      nothing distinguishes D7's guard-in-the-helper from a guard at the call site, since 3.18
      passes either way.
      **Done** — `test_3_22_requirement_view_survives_a_scalar_criteria_block`.
- [x] 3.23 A criterion whose `requirement` is absent from `payload["requirements"]` is still
      attached, sorted last — the `len(position)` fallback `spec_render._acceptance` uses and the
      group concatenation dropped. **The document MUST write the absent-requirement criterion BEFORE
      the present-requirement one**, or the test passes under a raw-document-order implementation too
      and discriminates nothing. Pins the delta spec's *"A criterion whose requirement the document
      no longer lists is still attached"* scenario — which exists because the spec's own "attaches
      no others" sentence had to be reworded from *resolves* to *names* for this case to be legal at
      all (fourth review, B1).
      **Done** — `test_3_23_a_criterion_whose_requirement_is_no_longer_listed_is_attached_last`.
- [x] 3.24 A payload whose `requirements` is a scalar creates every declared task **carrying the
      criteria its entries name** and does not raise (task 2.7's new exposure, the
      `statements_by_key` hole). **The fixture MUST declare criteria that match the entry's names**,
      or the test does not reach the guard: matching is on `named` (design D3) and is independent of
      `payload["requirements"]`, so an implementation short-circuiting on an empty criteria set never
      builds the `position` map at all. An earlier wording asserted "with no criteria", which is
      wrong on both counts — a scalar `requirements` costs the ordering, not the criteria.
      **Done** — `test_3_24_a_scalar_requirements_block_costs_the_ordering_not_the_criteria`.
- [x] 3.26 A payload whose `requirements` is a **list holding a non-dict element** creates every
      declared task, carrying the criteria its entries name, and does not raise. Distinct from 3.24:
      this shape passes an `isinstance(raw, list)` guard and only a per-element check survives it.
      Pins task 2.7's choice of `statements_by_key` over a hand-rolled comprehension, which 3.24 and
      3.25 cannot — they are satisfied by either.
      **Done** — `test_3_26_a_requirements_list_holding_a_non_dict_element_still_materialises`.
- [x] 3.25 `requirement_view` over a payload whose `requirements` is a scalar returns rather than
      raising — the same `read_spec_document` path as 3.22 (`api/v1/agent_actions.py:1399` →
      `spec_reading.py:129`, which calls `statements_by_key` with no `try`/`except`). 3.22 covers
      only the `acceptance_criteria` half of D7's guard-in-the-helper argument; without this the
      `statements_by_key` half is pinned by nothing and the 500 stands.
      **Done** — `test_3_25_requirement_view_survives_a_scalar_requirements_block`.
- [x] 3.16 A criterion with no handle is attached with its given/when/then and **no `None` appears
      anywhere in the rendered string** (design D8). Assert on the string, not on the model field —
      the defect is in what a reader sees.
      **Done** — `test_3_16_a_criterion_with_no_handle_renders_without_the_literal_none`.
- [x] 3.17 A criterion with no given, no when and no then is not attached, and the task is still
      created (design D8, task 2.6).
      **Done** — `test_3_17_a_criterion_that_states_nothing_is_not_attached`.
- [x] 3.18 A payload whose `acceptance_criteria` is a scalar (`5`) creates every declared task with
      no criteria and no raise — the exact `TypeError` task 1.8 measured, through
      `materialise_quietly`.
      **Done** — `test_3_18_a_scalar_criteria_block_creates_every_task_with_no_criteria`.
- [x] 3.19 Two documents declaring the same tasks, one with criteria and one without, create the
      same tasks with the same titles and keys, differing only in criteria (the review's scenario as
      R4 reworded it — the one-document phrasing was vacuous under `existing_keys`).
      **Done** — `test_3_19_attaching_criteria_changes_nothing_about_which_tasks_exist`.
- [x] 3.12 A file whose task entries and criteria use different namespaces attaches no criteria to
      those tasks, creates them anyway, and does not raise (design D3's accepted consequence).
      **Done** — `test_3_12_a_file_whose_tasks_and_criteria_use_different_namespaces`.
- [x] 3.8 Every attached criterion carries its given, its when and its then.
      **Done** — `test_3_8_every_attached_criterion_carries_its_given_its_when_and_its_then`.
- [x] 3.9 Re-approval does not revisit or duplicate criteria on an already-created task (design D5).
      **Done** — `test_3_9_re_approval_does_not_revisit_or_duplicate_criteria`.
- [x] 3.10 A created task's criteria render into a loop briefing as one line per criterion — the
      `scheduler.py:2456-2460` path, not only the model field. **Assert
      `all(isinstance(c, str) for c in task.acceptance_criteria)` here**: the delta spec's *"a form
      the existing readers of that field already accept"* is otherwise pinned by nothing executable,
      since `scheduler.py:2459`'s f-string stringifies any object and the only other check is the
      human drive at 6.3.
      **Done** — `test_3_10_criteria_render_into_a_loop_briefing_one_line_each`.

## 4. Mutation checks

Each mutation is applied to the implementation, the suite is run, the result recorded, and the
mutation reverted with `git checkout`. A mutation that flips no test means the tests above do not
pin what they claim to.

**Section note — all seventeen were applied individually and every one flipped its named target;
none flipped nothing.** Harness: `testbed/scratch/mutate_amtci.py` (throwaway, gitignored) applies
one mutation's edits by exact-anchor replacement, runs
`py -3.11 -m pytest tests/test_spec_criteria_reach_the_task.py -q --no-header -rf` from `hub/`,
parses the `FAILED`/`ERROR` lines, then `git checkout -- hub/hub/spec_tasks.py
hub/hub/spec_reading.py` before the next. Baseline before the run: **25 passed in 14.10s**. After
the run `git status --short` and `git diff --stat` are both empty — the implementation is
byte-identical to HEAD. Rows below name the rows that flipped, not only the target; a mutation
reaching more than its target is reported as measured rather than trimmed.

- [x] 4.1 Match criteria on the resolved row's `.key` instead of the entry's `named` → 3.7 fails.
      **Done — 3.7 flipped, and only 3.7** (1 failed, 24 passed). Mutation: in `materialise()`,
      resolve `row` first and `names.append(row.key if row is not None else named)`.
- [x] 4.6 Let a malformed criterion entry raise instead of being skipped → 3.11 fails by producing
      **no tasks at all**. Corrected: an earlier wording expected a committed partial board, which
      contradicted design D6 as corrected — with the index built once before the loop (task 2.2) a
      payload-level malformation raises before the first `session.add`/`flush`
      (`spec_tasks.py:218-219`), so a prefix is not reachable.
      **Done — 3.11 flipped, and only 3.11** (1 failed, 24 passed). Mutation: removed
      `if not isinstance(entry, dict): continue` from `criteria_by_requirement_key`'s loop, so
      `"abc"` and `["ac-alpha", 7]` reach `entry.get`. The failure is exactly the predicted shape —
      3.11 asserts both declared tasks exist on every malformed shape and got an empty board,
      because the `AttributeError` escapes the index build and `materialise_quietly` swallows it.
- [x] 4.7 Render without the criterion key → 3.13 fails.
      **Done — 3.13 flipped** (17 failed, 8 passed). Mutation: `_render_criterion` returns `body`
      unconditionally. It reaches far beyond its target — 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.9, 3.10,
      3.13, 3.14, 3.15, 3.17, 3.19, 3.21, 3.23, 3.24, 3.26 — because `RENDERED_ALPHA` and its
      siblings carry the handle and nearly every assertion compares whole rendered strings. Breadth
      is not weakness here: 3.13 is the row that states *why* the handle is there (design D2), and
      it fails.
- [x] 4.8 Order criteria by raw `payload.acceptance_criteria` position instead of by requirement
      → 3.15 fails. **Inverted from its original form**, which mutated toward grouping and would
      have been satisfied by the prescribed implementation itself once D7 mandated the helper — the
      contradiction the second review found.
      **Done — 3.15 flipped, and 3.23 with it** (2 failed, 23 passed). Mutation needed **two**
      files: `criteria_by_requirement_key` had to stamp `_raw_position` onto each grouped criterion
      (`for _raw_position, entry in enumerate(raw)`) before `_criteria_for_entry` could
      `collected.sort(key=lambda item: item[1].get("_raw_position", 0))`. **Recorded as measured:
      raw-payload order is not reachable inside the helper boundary D7 prescribes** — the grouped
      dicts carry only `key`/`given`/`when`/`then`, so this alternative implementation cannot be
      written without changing `spec_reading` too. That makes 4.8 a weaker discriminator than it
      reads: the algorithm it mutates toward is one D7 already forecloses. 4.8b, which needs no
      such scaffolding, is what actually pins the ordering. 3.23 flipping alongside is correct —
      its absent-requirement criterion is written first in the document, which is precisely the
      fixture built to catch raw-document order.
- [x] 4.12 Skip the de-duplication of an entry's repeated requirement names → 3.14 fails.
      **Done — 3.14 flipped, and only 3.14** (1 failed, 24 passed). Mutation:
      `for name in dict.fromkeys(names)` → `for name in names`.
- [x] 4.9 Always prefix the handle, including when it is absent → 3.16 fails (the string contains
      `None:`).
      **Done — 3.16 flipped, and only 3.16** (1 failed, 24 passed). Mutation: `_render_criterion`
      returns `f"{key}: {body}"` without the `isinstance(key, str) and key.strip()` test, so a
      handle-less criterion renders the literal `None:` — the D8 hole reproduced deliberately.
- [x] 4.10 Remove the `isinstance(..., list)` guard from task 2.1 → 3.18 fails, and fails by
      creating no tasks, which is D6's failure mode reproduced deliberately.
      **Done — 3.18 flipped, with 3.11 and 3.22** (3 failed, 22 passed). Mutation:
      `raw = payload.get("acceptance_criteria") or []` in `criteria_by_requirement_key`. All three
      are the same hole seen from three angles: 3.18 through `materialise()` (empty board), 3.11
      through `materialise_quietly` (same), 3.22 through `requirement_view`, which has no `try`
      and so surfaces the `TypeError: 'int' object is not iterable` task 1.8 measured.
- [x] 4.11 Attach criteria that state nothing → 3.17 fails.
      **Done — 3.17 flipped, with 3.11** (2 failed, 23 passed). Mutation: removed
      `if not parts: return None` from `_render_criterion`, so a criterion with no given/when/then
      renders as `"ac-empty: "` and is attached. **This row was flagged in `next_action` as one of
      the two most likely to be already satisfied by the prescribed implementation; it is not** —
      the skip is a real decision with a real test behind it. 3.11 comes along because one of its
      five malformed shapes yields criteria that state nothing.
- [x] 4.2 Attach every criterion in the document regardless of requirement → 3.2 fails.
      **Done — 3.2 flipped, with 3.1, 3.4, 3.12, 3.19, 3.21** (6 failed, 19 passed). Mutation:
      `for name in dict.fromkeys(list(names) + list(criteria_index))` in `_criteria_for_entry`.
      The five companions are the rows that assert a task carries a *specific* list: attaching
      everything breaks each of them, including 3.4 (a task naming nothing now carries the lot) and
      3.12 (the different-namespace file now attaches criteria it must not).
- [x] 4.3 Drop the `then` from the rendered string → 3.8 fails.
      **Done — 3.8 flipped** (15 failed, 10 passed). Mutation: removed the `then` block from
      `_render_criterion`. Same breadth as 4.7 and for the same reason — whole-string comparisons
      against `RENDERED_ALPHA`. 3.8 is the row that states the clause-level requirement, and it
      fails on its own `f"then {AC_ALPHA['then']}" in line` assertion.
- [x] 4.4 Sort criteria by key within a requirement instead of keeping written order → 3.6 fails.
      **Done — 3.6 flipped, and only 3.6** (1 failed, 24 passed). Mutation:
      `collected.sort(key=lambda item: (item[0], str(item[1].get("key"))))`. 3.6's deliberately
      non-alphabetical keys (`zebra, apple, mango`) are what make it the single discriminator.
- [x] 4.8b Order by the ENTRY's requirement list instead of `payload.requirements` → 3.15 fails.
      Without this the ordering is unpinned: 4.8 mutates toward a third algorithm (raw payload
      position) and does not discriminate the entry-order implementation from the correct one.
      **Done — 3.15 flipped, and only 3.15** (1 failed, 24 passed). Mutation:
      `for rank, name in enumerate(dict.fromkeys(names))`, dropping the `position` lookup entirely.
      This is the row that carries the ordering: it needs no cross-module scaffolding, it mutates
      toward an implementation a reasonable author would actually write, and exactly one test
      stands between the two.
- [x] 4.14 Drop criteria whose requirement is absent from `payload.requirements` instead of sorting
      them last → 3.23 fails.
      **Done — 3.23 flipped, with 3.24** (2 failed, 23 passed). Mutation:
      `if name not in position: continue` replacing the `position.get(name, len(position))`
      fallback. 3.24 comes along necessarily: its `requirements` block is a scalar, so `position`
      is empty and *every* name is "absent" — under this mutation a scalar `requirements` costs the
      criteria as well as the ordering, which is exactly the conjunction 3.24 exists to deny.
- [x] 4.15 Move the guard from inside the helper to this change's call site → 3.22 fails.
      **Done — 3.22 flipped, and only 3.22** (1 failed, 24 passed). Mutation: guard removed from
      `criteria_by_requirement_key` and re-added around `materialise()`'s `criteria_index =` call.
      3.18 and 3.11 correctly stay green — the call site protects `materialise()` — and 3.22, which
      goes through `requirement_view`, is left exposed. This is D7's argument measured rather than
      asserted: the guard has to live in the helper because `materialise()` is not its only caller.
- [x] 4.16 Remove the guard from `statements_by_key` → **3.25** fails. Retargeted from 3.24, which
      exercises `materialise()` and is therefore protected by `materialise_quietly`'s catch-all; 3.25
      goes through `requirement_view`, which has no `try`/`except` and is where removing the guard
      actually surfaces.
      **Done — 3.25 flipped, and 3.24 with it** (2 failed, 23 passed). Mutation:
      `raw = payload.get("requirements") or []`. **The retarget was right and its stated reason is
      wrong, as measured**: `materialise_quietly`'s catch-all does not protect 3.24, it converts the
      raise into an empty board, and 3.24 asserts the tasks exist — so it fails too, just not by
      raising. The retarget still stands on its real merit: 3.25 is the row where the `TypeError`
      itself reaches the caller. Noted here rather than silently corrected, per the round
      discipline — an argument can be wrong while everything it argues about is right.
- [x] 4.17 Build the `position` map with a bare `{r["key"]: i for i, r in enumerate(raw)}` over a
      `raw` guarded only against not being a list, instead of through `statements_by_key` (task 2.7)
      → **3.26** fails. This is the one behavioural difference between the two readings: a list
      holding a non-dict element passes an `isinstance(raw, list)` guard and then raises
      `TypeError: string indices must be integers`, which `statements_by_key`'s per-element
      `isinstance(entry, dict)` skip does not.
      **Done — 3.26 flipped, and only 3.26** (1 failed, 24 passed). Mutation written exactly as the
      row describes, `isinstance(_raw, list)` guard included. The prediction holds to the letter:
      3.24 (scalar `requirements`) stays green because the list guard catches it, and only 3.26's
      `["not a requirement", ALPHA]` gets through to raise. The row is the whole justification for
      task 2.7 and it discriminates on one test.
- [x] 4.5 Attach criteria to tasks resolving no requirement → 3.4 fails.
      **Done — 3.4 flipped, and only 3.4** (1 failed, 24 passed). Mutation:
      `_criteria_for_entry(names or list(criteria_index), criteria_index, position)`, so an entry
      with no `requirements` falls back to the whole document. **Also flagged in `next_action` as
      likely already-satisfied; it is not** — 3.4 asserts `acceptance_criteria is None`, the unset
      state task 1.7 measured on all 32 existing rows, and the mutation makes it a populated list.

## 5. Whole-suite and quality gates

- [x] 5.1 `py -3.11 -m pytest tests/ -q` from `hub/` — full suite, zero new failures. Record the
      counts.
      **Done.** `py -3.11 -m pytest tests/ -q` from `hub/`, backgrounded so §5.2-5.4 ran while it
      executed: **4440 passed, 86 skipped, 0 failed, 42:02** (2522.39s). Against the guarded
      green-tree baseline recorded at the top of tonight's log (4415 passed, 86 skipped, 0 failed,
      27:46 at `6d70710`): **+25 passed** — exactly the new `test_spec_criteria_reach_the_task.py`
      file added in §3, nothing else moved — **86 skipped unchanged, 0 failed both times.** Zero
      new failures, the actual bar, not zero failures. The longer wall-clock is this machine's own
      variance run to run, not a regression signal by itself; the counts are what the bar measures.
      Some `RuntimeError: Event loop is closed` warnings appear during teardown of unrelated
      previously-existing tests (aiosqlite worker-thread cleanup racing an already-closed loop) —
      cosmetic pytest teardown noise counted in the 261 warnings, not a failure, and not touched by
      this change's files.
- [x] 5.2 `ruff check src/ hub/ tests/`, `black --check src/ hub/hub/ hub/tests/ tests/
      --target-version py311`, `mypy src/` — clean.
      **Done.** `ruff check src/ hub/ tests/` — "All checks passed!". `black --check src/ hub/hub/
      hub/tests/ tests/ --target-version py311` — "578 files would be left unchanged." `mypy src/`
      — "Success: no issues found in 22 source files."
- [x] 5.3 `openspec validate --strict a-materialised-task-carries-its-criteria` — passes.
      **Done.** `npx openspec validate a-materialised-task-carries-its-criteria --strict` —
      "Change 'a-materialised-task-carries-its-criteria' is valid."
- [x] 5.4 Measure what this actually adds to a briefing (carried from R3's task 1.6): for a real
      approved document, record the character count the criteria block contributes against the
      4,000-character checkpoint bound it sits beside. The ceiling is three requirements' worth of
      criteria (`spec_completeness.MAX_REQUIREMENTS_PER_TASK = 3`), but that cap is enforced only on
      the transition to `proposed`, so do not assume it for an adopted document. Record the number;
      propose a bound only if the measurement asks for one.
      **Done.** Port 8000's database (`~/.agentweave/hub/data/agentweave.db`) holds exactly one
      `approved`-phase document, `spdoc-97d90a3506f5` ("Loop engine with a dashboard for agent
      loops") — read via a `mode=ro` SQLite URI only (`projects`, `spec_documents`, `tasks`
      tables), never started/migrated/written. Rather than re-deriving the render from the raw
      spec payload, measured the *actual persisted* `tasks.acceptance_criteria` for every task
      already materialised from that document (the real output of `materialise()` on a real
      approval, not a reconstruction) and rendered each exactly as `_compose_loop_briefing` does
      (`"Acceptance criteria:"` + one `"- {criterion}"` line per entry, joined with `\n`,
      `scheduler.py:2456-2460`). 13 of the document's materialised tasks carry criteria (2-9
      criteria each). **Largest block: 1,307 characters** (`task-0be2ed219dd8`, 9 criteria) —
      **33% of the 4,000-character checkpoint bound**, well clear of it. No bound is being
      proposed: the measurement does not ask for one at today's real scale, and per task 1.6 the
      criteria block sits beside the checkpoint's own budget rather than inside it, so it cannot
      displace the checkpoint either way. Recorded as the residual task 1.6 already named: a
      future document with more or larger criteria per task could still push a single block close
      to or past 4,000 characters — unmeasured until a document that large actually exists.

## 6. Drive

- [ ] 6.1 On the **trial** Hub (`:8010`, from source, per `.claude/reference/hubs.md`) — never
      `:8000` — approve a document declaring a task with criteria, and confirm the created task
      carries them.
- [ ] 6.2 Confirm they reach a real turn: fire a loop on that task and read the briefing the agent
      actually received, rather than inferring it from the model field.
- [ ] 6.3 Confirm the task drawer renders them in the UI without a bundle change.

## 7. Close-out

- [ ] 6.4 Confirm the briefing still spawns with a large criteria block. No bound is being added
      (design open question 2), so this is the check that the accepted residual risk is really
      benign: drive a task whose criteria
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
