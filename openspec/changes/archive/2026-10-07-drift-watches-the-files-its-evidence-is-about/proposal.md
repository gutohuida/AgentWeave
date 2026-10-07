# Proposal — drift watches the files its evidence is about

**Round 1, 2026-09-24** (bundle B6, slice S5b, part 1 of 2). Findings: **F217 (C)**, whose branch
basis was a D13 decision item and is decided here as a recommendation, plus the **whole-tree
footprint defect** that `read_footprint`'s own docstring defers (`hub/hub/requirement_evidence.py:519-522`)
and F215's entry measured (*"one commit changing one file … raised 44 drift candidates"*,
`scripts/drive/FINDINGS.md` under F215). The defect has no finding number of its own; this change
carries it because the second half of S5b (`drift-is-scanned-and-answered-on-the-document`) makes
drift reachable, and reachable drift over whole-tree footprints is a flood. **Nothing here is
implemented yet.**

## Why

Drift is the product's way of asking *"the implementation changed after this was verified — which
one was wrong?"*. Two things make its answer wrong today, and both sit in what a footprint watches.

**1. A footprint watches the whole tree.** `read_footprint` stores `entries = tree_entries(root,
commit)` — every blob in the repository (`requirement_evidence.py:539`), and `restamp_run_footprints`
does the same (`:969`). `detect_drift` then walks every baseline path (`_changed`, `:1062-1069`). So a
commit to *any* tracked file raises a candidate for *every* accepted piece of evidence footprinted on
that branch. Measured in R1 on `404c7d5` with a throwaway test: operator evidence whose locator is
`ledger.py`, then a commit changing only `other.py` → **one candidate, `observed: {"other.py": …}`**.
The spec already says a footprint holds *"the changed blob identifiers"* and, without a repository,
*"the changed paths"* (`openspec/specs/requirement-traceability/spec.md:269-272`); the implementation
has never matched it.

**2. An agent's evidence stops being watched the moment its work lands (F217).** `detect_drift`
compares each footprint against `footprint.branch` (`:1140-1152`). An agent is always footprinted in
its own worktree, so its evidence is compared against `agentweave/<agent>` or a task branch —
branches nothing commits to once the work has merged (task release keeps the branch,
`worktrees.py:987-993`, so the comparison keeps succeeding and keeps finding nothing). The operator's evidence, taken on `main`, is compared against
`main`. F217 drove it: one commit on `main` to a file both pieces of evidence covered raised a
candidate for the operator's and **none** for the agent's, although the agent's footprint already
read `reachable_from_main: true`. The asymmetry falls entirely on the agent plane, which is where
the product intends most evidence to come from.

The two are one problem. The docstring defers (2) because *"answering that needs the changed paths
rather than the whole tree"* (`:1092-1095`). Switching the basis to `main` without narrowing would
compare an agent commit's whole tree against `main` and raise every file anybody else merged.

## What Changes

- **A footprint watches the files its evidence is about**: the path its locator names (a file, or
  the files under a directory), the files changed by the commit an operator's locator names, and the
  files changed on its line of work since that line left the main line. `entries` holds those paths
  and their blob ids (or content hashes, without a repository), not the whole tree.
- **A footprint records why it watches what it does** — a new nullable `watched_from` column on
  `evidence_footprints`, a list drawn from `locator`, `commit`, `branch`. `[]` means it could name no
  file and watches nothing; `NULL` means it was recorded before this change.
- **Drift compares against the main line once the work has reached it.** A git footprint whose
  `reachable_from_main` is true is compared against the project's main branch; one that is not yet
  there is compared against the branch it names, as today.
- **Evidence that watches nothing says so**: `GET /spec/drift` gains an `unwatched` list (accepted
  evidence whose footprint watches no file, or that has no footprint at all, with the reason), and
  the footprint view reports
  `watched_from` and how many files it watches, so the recorder sees it at the moment of recording.
- **Footprints recorded before this change are not scanned**, and are listed as unwatched with the
  reason `recorded_before_watching`. Nothing in the product can reach drift today (F129), so no
  operator loses a signal they had.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `requirement-traceability` — adds *"A footprint watches the files its evidence is about"*.
- `spec-document-authority` — modifies *"Drift is assessed against the line of work a footprint
  names"*: the main line becomes the basis once the work has reached it.

## Impact

- `hub/hub/requirement_evidence.py` — `read_footprint`, `_take_footprint`, `restamp_run_footprints`,
  `capture_footprint`, `detect_drift`, `hash_tree`'s use in detection; a new `watched_files` helper.
- `hub/hub/db/models.py` (`EvidenceFootprint.watched_from`) and one migration (next free revision
  at IMPL time; other bundles may also add one).
- `hub/hub/api/v1/spec.py` — `footprint_view`, `list_drift` (`unwatched`), `record_evidence` passes
  the project's main branch.
- `hub/tests/test_requirement_drift.py` — several tests record evidence with no locator and rely on
  the whole tree; they are rewritten on purpose (tasks 1.9).
- No UI. No agent-plane or MCP change beyond `footprint_view`'s two added keys, which the agent's
  `record_evidence` response shares (`agent_actions.py:1235-1243`).

Cross-bundle: **builds on B5's `a-footprint-names-the-line-of-work-its-commit-is-on`, which lands
first** (same four functions; B5 moves `branch`, this moves `entries`). design.md's "Builds on B5"
section lists exactly which of B5's pieces this change assumes (added in R2).

F215 (bundle B5) quotes the 44-candidate measurement in its own entry. B5 should not
carry the narrowing; it is here.
