# Tasks

Round 1 wrote these. Rounds 2 and 3 may rewrite any of them; nothing here is implemented.

## 1. Reproduce F155 before changing a word

- [x] 1.1 Write a failing test in `hub/tests/` that builds the F155 shape end to end: a project with
  a main branch, two tasks touching the same path, the second landed on the main branch first, and
  the first carrying **accepted** evidence whose footprint names a conflicting commit. Approve it,
  read the `409`, and assert today's sentence — that it says *"Resolve the conflict on the branch"*
  and does **not** name the commit. Assert today's wrong behaviour so the test flips.
- [x] 1.2 Assert the consequence rather than the wording alone: resolve the conflict on the branch
  (a real merge commit on the task branch), approve again, and assert the refusal is **byte-for-byte
  identical** — that is the defect, and a test that only reads prose does not prove it.
- [x] 1.3 Assert what does clear it, so the remedy the new sentence states is proven before it is
  stated: record fresh evidence **from a checkout of the branch the refusal names**, accept it,
  approve, and assert the transition succeeds and integration records `merged` against the resolved
  commit. Round 2 answered design open question 1 at the source -- the agent route is safe because
  `_take_footprint` gates the named-commit path on `actor.kind == "operator"` (`requirement_evidence.py:282`) -- so this test's job
  is to hold that answer, not to discover it.
- [x] 1.3a Assert the operator hazard round 2 found, as an **xfail or an explicit non-guarantee**:
  an operator recording evidence whose `locator` is the resolved sha, once that commit is no longer
  exactly one branch's tip, gets `branch=""` from `_branch_at` and does **not** supersede. This
  change does not fix that -- it is prose-only -- but the wording must not promise it away, and a
  test naming it is what stops a later reader assuming it works. If the test shows the hazard is
  unreachable, delete it and say so; if it shows it is reachable, file it as a finding.
- [x] 1.3b Assert the two properties D6 rests on, because the sentence is only true if they hold:
  fresh evidence for a **different** requirement on the same branch also supersedes, and a restamp
  of the stale row does not move it in the `observed_at` ordering.
- [x] 1.3c Assert round 3's correction to D2a, because round 2 stated it as a construction and it is
  a precondition: with `Run.workspace_dir` absent or pointing at a released directory,
  `footprint_root` (`requirement_evidence.py:334-340`) falls back to the per-agent checkout and then
  to `workspace.root`, which is on the **main** branch. Record fresh evidence in that state and
  assert it does **not** supersede -- `newest` gains a second key rather than replacing the first.
  This is the same non-guarantee as 1.3a reached from the agent route, and the wording must not
  promise it away. If it proves unreachable, delete it and say so.
- [x] 1.4 Confirm 1.1 and 1.2 fail for the stated reason by reading the failure output, not by
  assuming.

## 2. The gate carries where the commit came from

- [x] 2.1 Test `_check_mergeable`'s entries directly: an evidence-governed target produces an entry
  with `named_by_evidence` true and the evidence id; a branch-tip target produces one with it false
  and no evidence id.
- [x] 2.2 Add the two keys in `_check_mergeable` (`hub/hub/requirement_gate.py:342-350`) from
  `Target.evidence_id`, with a comment naming `merge_targets`' two routes and why the provenance is
  per-target rather than per-project (design D1).
- [x] 2.2a Add `recorded_by_task` and `recorded_by_another_task` to the same entry, from
  `Target.task_id` (`task_integration.py:263`), on the same terms `_check_unaccepted` already does
  (`requirement_gate.py:383-386`) -- design D7. No new query: the value is already on the target.
- [x] 2.2b Test the attribution directly: evidence recorded by this task sets
  `recorded_by_another_task` false; evidence recorded by a **different** task against a shared
  requirement sets it true and carries that task's id. Build the shared-requirement shape for real
  rather than by patching the flag -- the population is what is in doubt, not the boolean.
- [x] 2.3 Confirm no consumer breaks on the wider entry. Round 2 corrected round 1 here: no
  **product-code** consumer reads a key off `unmergeable`, but
  `scripts/drive/t_row17_integration.py:273-282` reads `commit_sha` and `paths` off the refusal
  body. Both keep their meaning under additive keys. Re-check the whole set rather than inheriting
  either round's list.

## 3. The sentence

- [x] 3.1 Test `_merge_detail` directly, as a pure composition, over five inputs: evidence-named;
  branch-tip; an entry with no `commit_sha`; a mixed list; and an empty list. Assert the
  evidence-named case does **not** contain "Resolve the conflict on the branch", contains the
  12-character commit, contains the word `record`, and ends in `ACCEPT_OR_GRANT`'s text.
- [x] 3.2 Implement the composition: group by provenance, name the commit on **both** routes (open
  question 2, answered yes), reuse `ACCEPT_OR_GRANT` verbatim rather than restating it (design D2),
  and state the branch the resolved commit must be **on** and be recorded **from** -- never
  instructing the reader to supply a branch, which is not a field they have (design D2a).
- [x] 3.3 Keep the branch-tip sentence's existing wording, and leave a comment saying it is
  deliberately unchanged because it is true on that route — so a later reader does not "fix" it into
  agreement with the other one.
- [x] 3.3a Name the **source** branch in the prose as well as the main branch, and phrase the
  remedy's condition against the source branch rather than an ambiguous "the branch" (design D8).
  Today `_merge_detail` reads only `target_branch` (`requirement_gate.py:172`), which is
  `situation.main_branch`, so without this the remedy reads as an instruction to put the resolved
  commit on the main branch. Test that both branch names appear and that the remedy's clause is
  attached to the source one.
- [x] 3.3b Render the attribution where `recorded_by_another_task` is true, and word the remedy so it
  does not address the reader as though the branch were theirs (design D7). Assert the same-task case
  names no other task. Do **not** invent an instruction about whom to approach; the requirement
  forbids it.
- [x] 3.4 Guard each optional piece independently (design D4); a missing `commit_sha` degrades to a
  sentence without one and never prints an empty sha.
- [x] 3.5 Update `hub/ui/src/__tests__/taskIntegration.test.ts:43-56`'s fixture message to the new
  wording. Its two assertions are about the **sentence** — that the conflicting path and the target
  branch reach the reader — so they must still hold unchanged. If either has to be weakened, the new
  sentence has dropped something the old one carried, and that is a finding rather than a fixture fix.
- [x] 3.6 Update `scripts/drive/t_row17_integration.py:284-288`, which asserts the refusal's message
  contains both `"resolve"` and `"approve"` lowercased. On the evidence route the new sentence may
  contain neither word in that form. Replace the assertion with one that reads the new requirement --
  that the message names the commit and states a remedy the reader can take -- rather than deleting
  it. This is a consumer round 1 did not have; a red drive here is the change working, not failing.

## 4. The commit that left its branch (design D3)

- [x] 4.1 Test it: an entry whose commit is reachable from its branch produces no such clause; one
  whose commit is not produces the clause; a branch that does not resolve produces no clause.
- [x] 4.2 Implement it with `requirement_evidence.is_reachable_from`, `False` only — `None` says
  nothing. Comment the cost argument: this runs only on a path that has already run `merge-tree` and
  is already refusing.
- [x] 4.3 Guard an empty or absent branch name before calling it.

## 5. Prove it in the product, not only in the suite

- [x] 5.1 Extend the drive harness that produced F155 (`scripts/drive/t_drive1_flow_lands.py`) — or
  add a lane to it — that manufactures the conflict deliberately: two tasks, same path, one landed
  first. Assert the `409`'s `message` against the new requirements, and assert the drive can follow
  the sentence it is given to a `merged` outcome without any instruction the product did not supply.
- [x] 5.2 Run it against a Hub restarted from this branch, against a **fresh** project — never
  `proj-5e960453` or `proj-18e5d4e0`. Every real agent turn binds Haiku.
- [x] 5.3 Record what the drive found in `scripts/drive/FINDINGS.md`, including anything the new
  sentence still leaves a reader unable to do.

## 6. Green

- [x] 6.1 `openspec validate a-conflict-refusal-names-what-clears-it --strict`.
- [x] 6.2 `ruff check src/ hub/ tests/`; `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`; `mypy src/`.
- [x] 6.3 The Hub suite in chunks, and `cd hub/ui && npm run lint && npx vitest run` for the changed
  UI test.
- [x] 6.4a Do **not** sync or archive this change into `openspec/specs/` before
  `a-loop-declares-whether-it-needs-evidence` is archived (design D9). This requirement's
  discriminator names the branch-tip route, which that change ADDS and which no shipped requirement
  describes today; landed first, it would sit beside
  `openspec/specs/task-lifecycle-governance/spec.md:638` -- *"SHALL NOT be the agent's branch"* --
  with the reconciliation only in an unarchived change. Round 3 checked and found no breach, only
  this ordering.
- [x] 6.4 No UI source changed beyond a test fixture, so no bundle rebuild — confirm that rather than
  assume it.
