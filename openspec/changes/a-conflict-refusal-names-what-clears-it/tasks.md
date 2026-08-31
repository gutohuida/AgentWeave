# Tasks

Round 1 wrote these. Rounds 2 and 3 may rewrite any of them; nothing here is implemented.

## 1. Reproduce F155 before changing a word

- [ ] 1.1 Write a failing test in `hub/tests/` that builds the F155 shape end to end: a project with
  a main branch, two tasks touching the same path, the second landed on the main branch first, and
  the first carrying **accepted** evidence whose footprint names a conflicting commit. Approve it,
  read the `409`, and assert today's sentence — that it says *"Resolve the conflict on the branch"*
  and does **not** name the commit. Assert today's wrong behaviour so the test flips.
- [ ] 1.2 Assert the consequence rather than the wording alone: resolve the conflict on the branch
  (a real merge commit on the task branch), approve again, and assert the refusal is **byte-for-byte
  identical** — that is the defect, and a test that only reads prose does not prove it.
- [ ] 1.3 Assert what does clear it, so the remedy the new sentence states is proven before it is
  stated: record fresh evidence naming the resolved commit on the same branch, accept it, approve,
  and assert the transition succeeds and integration records `merged` against the resolved commit.
  If this does not pass, design open question 1 is answered *no* and D2's wording is wrong.
- [ ] 1.4 Confirm 1.1 and 1.2 fail for the stated reason by reading the failure output, not by
  assuming.

## 2. The gate carries where the commit came from

- [ ] 2.1 Test `_check_mergeable`'s entries directly: an evidence-governed target produces an entry
  with `named_by_evidence` true and the evidence id; a branch-tip target produces one with it false
  and no evidence id.
- [ ] 2.2 Add the two keys in `_check_mergeable` (`hub/hub/requirement_gate.py:342-350`) from
  `Target.evidence_id`, with a comment naming `merge_targets`' two routes and why the provenance is
  per-target rather than per-project (design D1).
- [ ] 2.3 Confirm no consumer breaks on the wider entry. Round 1 checked and found that **nothing
  reads a key off `unmergeable`** — `to_dict` copies the list, `readableApiError` and
  `mcp_server._readable_detail` both return `message` alone. Re-check rather than inherit: a single
  reader appearing anywhere makes the composition a contract instead of a rendering.

## 3. The sentence

- [ ] 3.1 Test `_merge_detail` directly, as a pure composition, over five inputs: evidence-named;
  branch-tip; an entry with no `commit_sha`; a mixed list; and an empty list. Assert the
  evidence-named case does **not** contain "Resolve the conflict on the branch", contains the
  12-character commit, contains the word `record`, and ends in `ACCEPT_OR_GRANT`'s text.
- [ ] 3.2 Implement the composition: group by provenance, name the commit, reuse `ACCEPT_OR_GRANT`
  verbatim rather than restating it (design D2), and name the branch the fresh evidence must be
  recorded against.
- [ ] 3.3 Keep the branch-tip sentence's existing wording, and leave a comment saying it is
  deliberately unchanged because it is true on that route — so a later reader does not "fix" it into
  agreement with the other one.
- [ ] 3.4 Guard each optional piece independently (design D4); a missing `commit_sha` degrades to a
  sentence without one and never prints an empty sha.
- [ ] 3.5 Update `hub/ui/src/__tests__/taskIntegration.test.ts:43-56`'s fixture message to the new
  wording. Its two assertions are about the **sentence** — that the conflicting path and the target
  branch reach the reader — so they must still hold unchanged. If either has to be weakened, the new
  sentence has dropped something the old one carried, and that is a finding rather than a fixture fix.

## 4. The commit that left its branch (design D3)

- [ ] 4.1 Test it: an entry whose commit is reachable from its branch produces no such clause; one
  whose commit is not produces the clause; a branch that does not resolve produces no clause.
- [ ] 4.2 Implement it with `requirement_evidence.is_reachable_from`, `False` only — `None` says
  nothing. Comment the cost argument: this runs only on a path that has already run `merge-tree` and
  is already refusing.
- [ ] 4.3 Guard an empty or absent branch name before calling it.

## 5. Prove it in the product, not only in the suite

- [ ] 5.1 Extend the drive harness that produced F155 (`scripts/drive/t_drive1_flow_lands.py`) — or
  add a lane to it — that manufactures the conflict deliberately: two tasks, same path, one landed
  first. Assert the `409`'s `message` against the new requirements, and assert the drive can follow
  the sentence it is given to a `merged` outcome without any instruction the product did not supply.
- [ ] 5.2 Run it against a Hub restarted from this branch, against a **fresh** project — never
  `proj-5e960453` or `proj-18e5d4e0`. Every real agent turn binds Haiku.
- [ ] 5.3 Record what the drive found in `scripts/drive/FINDINGS.md`, including anything the new
  sentence still leaves a reader unable to do.

## 6. Green

- [ ] 6.1 `openspec validate a-conflict-refusal-names-what-clears-it --strict`.
- [ ] 6.2 `ruff check src/ hub/ tests/`; `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`; `mypy src/`.
- [ ] 6.3 The Hub suite in chunks, and `cd hub/ui && npm run lint && npx vitest run` for the changed
  UI test.
- [ ] 6.4 No UI source changed beyond a test fixture, so no bundle rebuild — confirm that rather than
  assume it.
