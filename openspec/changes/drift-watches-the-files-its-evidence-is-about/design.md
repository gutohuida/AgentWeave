# Design — drift watches the files its evidence is about

**Built on the recommended answer to F217's decision (bundle B6, "drift branch basis", moved out of
D13): narrow the footprint, then compare against the main line once the work has reached it
(option C below).** If the operator answers A (state the asymmetry and keep the basis), drop D3 and
the MODIFIED requirement, keep D1/D2/D4 (the narrowing is needed either way, because it is what
stops the flood), and add a sentence to the unwatched report naming the case. If the operator
answers B (switch basis without narrowing), this change is withdrawn: B floods (see the table).

Also built on the recommended answer to the sub-question **"what does evidence that names no file
watch?"** — nothing, reported (D2). If the operator answers "the whole tree, as today", D2's rule 4
becomes "the whole tree at that commit" and the flood returns for that evidence only.

**Round 1, 2026-09-24; corrected in R2 the same day.** Nothing here is implemented yet.

## Builds on B5's `a-footprint-names-the-line-of-work-its-commit-is-on` (added in R2)

Both changes edit `read_footprint`, `_take_footprint`, `capture_footprint` and
`restamp_run_footprints`. **B5's lands first** (it changes what `branch` means; this change changes
what `entries` means). This change is written against the code *after* B5, and assumes exactly:

| B5 piece | What this change relies on |
|---|---|
| D1: `"HEAD"` is never written; its migration rewrites stored `'HEAD'` to `''` | D3's "names no line of work" is `branch == ""`. B5 keeps `detect_drift`'s `ref == "HEAD"` guard for one release; this change keeps it and does not remove it. |
| D2: `line_of_work(root, commit, *, task_branch=None)`; `read_footprint(root, *, at=None, task_branch=None)` | `read_footprint` gains this change's keyword-only `locator`, `actor_kind`, `main_branch` **beside** B5's `task_branch`. `branch` is whatever B5 computes; `watched_files` never reads or writes it. |
| D2: `restamp_run_footprints` reads `Run.task_id` once per run | Rule 3's branch diff is computed once per run beside it (task 2.3). |
| D3: an agent whose run directory is gone is read at `agentweave/task/<id>`'s tip in `workspace.root` | `watched_files` runs at that root and commit; `merge-base` and `diff` are repository-wide, so rule 3 answers what it would in the task checkout. |
| D4: the merge reduction keeps the descendant commit | Unrelated: it reads `branch` and `commit_sha`, never `entries` or `watched_from`. |

B5 asks the second change's R2 to confirm that operator footprints on non-tip commits, which now
name a branch, *"do not flood"*. This change is what answers it: once a footprint watches only its
files (D1), a named branch is compared on those files only; and such a commit is usually already on
the main line, where D3 compares against `main` whatever the branch string says. If this change
landed first instead, the implementer rebases onto B5's signatures and migration number; no
decision here moves.

## Context

Read on HEAD `404c7d5`.

| Where | What it does today |
|---|---|
| `requirement_evidence.read_footprint` (`:512-553`) | `entries = tree_entries(root, commit)` — the whole tree. Its docstring: *"one unrelated commit on the compared ref drifts every requirement at once. Fixing it is a separate change, deliberately"* (`:519-522`). Without git: `hash_tree(root)`, the whole directory up to 2000 files (`:548`, `:631-651`). |
| `_take_footprint` (`:248-296`) | Chooses the root and, for an operator whose locator is a bare sha (`_COMMIT_ISH`, `:556`), the commit (F71). An agent's locator never moves the commit. |
| `restamp_run_footprints` (`:905-997`) | After a run's snapshot commit, rebuilds the footprint at that commit, again with the whole tree (`:969`). Called once, best-effort, from `agent_trigger.py:1791` with `main_branch=project.main_branch`. |
| `refresh_reachability` (`:1000-1054`) | Upgrade-only: re-asks `reachable_from_main` for rows not already `True`. Called by `POST /spec/drift/detect` (`spec.py:966`) **and** after any in-app integration that merged (`task_transition_service.py:908-913`). R1 said "only detect"; R2 corrected it. A merge made by the product therefore flips the basis without waiting for a scan. |
| `detect_drift` (`:1072-1178`) | For accepted evidence whose digest matches the requirement's, compares `footprint.entries` against `tree_entries(root, footprint.branch)` (git) or `hash_tree(root)` (paths). Skips evidence with an open candidate (`:1131`), a detached or vanished branch (`:1142-1152`), and a change whose `moved` equals the last resolution's fingerprint (`:1160-1163`). |
| `_changed` (`:1062-1069`) | Walks the **baseline's** paths. So an added file never drifts (F129's drive measured it), and every baseline path that differs does. |
| `footprint_view` (`spec.py:1147-1167`) | `kind`, `branch`, `commit_sha`, `reachable_from_main`, `outside_workspace_writes`. `entries` is not shown. Shared by the agent's recording response (`agent_actions.py:1235-1243`). |
| Readers of `EvidenceFootprint.entries` | `detect_drift` only (`grep -rn "\.entries\b" hub/hub`). Nothing else depends on it being the whole tree. |

Measured in R1: a git repo with `ledger.py` and `other.py` on `main`; operator evidence with
`locator: "ledger.py"`; a commit changing only `other.py`; `POST /spec/drift/detect` →
`raised: ["drift-…"]`, `observed: {"other.py": {…}}`. The probe was a throwaway test file, deleted.

### The options for F217's basis

| Option | What it does | What it breaks | What it releases |
|---|---|---|---|
| **A. State it** | Keep branch basis; say on the drift surface and in the spec that agent evidence is watched only on its own branch. | Nothing. | Honesty only: agent evidence is still never drift-checked after merge, and the flood (whole tree) remains. |
| **B. Switch basis, whole tree** | Compare reachable footprints against `main`. | Floods: an agent commit's whole tree against `main` differs in every file anybody else merged since. The docstring's objection (basis flips under an open candidate) also applies. | Agent evidence watched after merge, drowned. |
| **C. Narrow, then switch** (recommended) | Footprint = the files the evidence is about; compare against the footprint's branch until the work reaches `main`, then against `main`. | Evidence that names no file and changed nothing on a branch watches nothing (D2) — today it watches everything. Existing tests that relied on the whole tree are rewritten (tasks 1.9). One migration. | Agent evidence is watched where the product actually is; one unrelated commit raises nothing; the docstring's deferral is discharged on its own terms. |

The docstring's objection to switching bases — *"drift would flip bases underneath an open
candidate"* — does not survive narrowing, for three reasons checked against the code:
1. `reachable_from_main` only moves `None/False → True` (`refresh_reachability`'s filter,
   `:1028`). `restamp` can write `False` over `True`, but only together with a new `commit_sha`
   and new `entries` (`:966-976`): a new baseline, not a flip under the old one (R2). So for one
   baseline the basis flips at most once, and one way.
2. An open candidate is skipped before any comparison (`:1131`), so a flip cannot change it.
3. A resolution stores `resolved_fingerprint = observed` (`:1221`), which is `{path: {was, now}}`.
   After a fast-forward or a no-conflict merge, `main` holds the same blob the branch did, so the
   same change computes the same `moved` on either basis and is not re-raised.

What remains is a genuine case, stated in Risks: a merge whose result for a watched file differs
from the agent commit's blob raises a candidate at the first scan after the flip. The file on `main`
is then not the file that was verified, which is the question drift exists to ask.

## Decisions

### D1 — `watched_files`: one function decides what a footprint watches

New `requirement_evidence.watched_files(root, commit, tree, *, locator, actor_kind, main_branch)
-> (entries, watched_from)`, called by `read_footprint` (git branch) and by
`restamp_run_footprints`. `tree` is the `tree_entries(root, commit)` both callers already read. The
union of:

1. **`locator`** — the locator, normalised (`./` and backslashes stripped, posix), when it is a path
   in `tree`, or a directory prefix of paths in `tree` (all of them). Applies to agents and operators:
   F71's rule is about *which commit* an agent's locator may name, not which files it may name.
2. **`commit`** — operator only, where `locator_commit(locator)` named the commit (F71): the paths
   that commit changed, `git diff-tree --no-commit-id --name-only -r --root <commit>`.
3. **`branch`** — where the main branch resolves and `commit` is **not** reachable from it: the
   paths changed between `git merge-base <main> <commit>` and `<commit>`. `main` is `main_branch`
   when configured, else the first of `MAIN_BRANCH_NAMES` that resolves (the same fallback
   `is_reachable_from_main` uses, `:615-628`).

`entries = {path: tree[path] for path in union if path in tree}`. Paths the work deleted are not
watched (there is no blob to compare against). `watched_from` lists the sources that contributed at
least one path, in the order above; `[]` when none did.

Every git call goes through `_git`, which answers `None` on failure (`:475-490`). A `None` from a
source contributes nothing — recording evidence is never refused over what it watches, matching
the spec's *"an observation must not become a gate"* (`requirement-traceability/spec.md:310-312`).

Without a repository (`kind == "paths"`): only rule 1 applies, hashed with the same
`sha256` as `hash_tree`. The whole-directory walk is no longer used to *record*.

### D2 — Evidence that can name no file watches nothing, and says so

Today such evidence watches the whole tree, which is what makes every commit a candidate. Rule 4 of
the derivation is **nothing**: `entries = {}`, `watched_from = []`. This covers an operator's
observation with a free-text or URL locator on the main line, and an agent turn that committed
nothing new.

It is reported rather than silent (D4), because F217's second complaint is that the limit was
*"nowhere stated"*.

### D3 — The basis is the main line once the work has reached it

In `detect_drift`, for a git footprint (in this order; R2 made the order explicit):
- `reachable_from_main is True` → compare against the main branch **whatever `branch` says**,
  including `""` (a detached review checkout, or a non-tip commit B5 could not name) (resolved as in D1, rule 3; the
  project's `main_branch` is read once per scan, as `detect`'s route already does at `spec.py:965`).
  If the main branch does not resolve, raise nothing (unknown is not drift).
- otherwise → `footprint.branch`, unchanged, including the detached-HEAD and vanished-branch skips.

`detect_drift` already runs after `refresh_reachability` in the same request (`spec.py:966-973`), so
a merge performed by integration or by hand in a terminal is noticed by the scan that follows it.

Without a repository: observe by hashing only the baseline's paths (a missing file observes `None`
and so drifts, as `_changed` already reads it), instead of `hash_tree` over the whole directory.

### D4 — Watching is visible

- `EvidenceFootprint.watched_from` (JSON, nullable). Migration adds the column; existing rows stay
  `NULL`. Guard for a missing table as `0033`/`0034` do; bump the head assertions in
  `test_migrations.py` and `test_project_persistence.py` (`.claude/rules/db-migrations.md`).
- `detect_drift` skips a footprint whose `watched_from` is `NULL` (recorded before this change —
  its `entries` are a whole tree) or `[]`.
- `footprint_view` adds `watched_from` and `watched_count` (`len(entries)`). The agent's recording
  response shares this view; two added keys, no removed ones.
- `GET /spec/drift` adds a top-level `unwatched` array: accepted, digest-current evidence whose
  footprint watches nothing, each `{evidence_id, requirement: {identifier, document}, summary,
  actor, reason}` with `reason` one of `names_no_file` (`[]`), `recorded_before_watching`
  (`NULL`), or `no_footprint`. **`no_footprint` was added in R2**: evidence whose workspace could not
  be resolved at record time has no footprint row (`_apply_footprint`'s docstring), and
  `detect_drift` inner-joins the footprint, so that evidence is not scanned today either and was
  missing from R1's list. Ordered by `produced_at, id` (the order `for_requirement` uses). The
  existing `drift` array is unchanged.

### D5 — What each touched route answers when the function it calls raises

- `POST /spec/evidence` and the agent's `record_evidence` (`agent_actions.py:1207`):
  `watched_files` cannot raise on a git failure (`_git` → `None`); a database error is an unhandled
  500 before commit, as today. The new git calls add at most four subprocesses per recording
  (`rev-parse` of the main branch, `diff-tree`, `merge-base`, `diff`), each with `_git`'s 15-second
  timeout.
- `POST /spec/drift/detect` — as today; the added `merge-base`/`diff` calls are at record and
  re-stamp time, not scan time. The scan reads one tree per distinct ref, as today.
- Re-stamp — already wrapped (`agent_trigger.py:1790-1800`): a failure keeps the record-time
  footprint and logs.
- `GET /spec/drift` — one more query (footprints of accepted evidence, joined), no git.

## Goals / Non-Goals

**Goals:** a commit to a file no evidence is about raises nothing; agent evidence is watched after
its work lands; what is not watched is listed with the reason.

**Non-Goals:** any UI (the second change of this slice); re-footprinting legacy rows (Open Question
1); superseding an open candidate when its requirement is reworded (the model's comment at
`models.py:2643-2644` promises it, nothing does it; noted for the operator, not carried).

## Risks / Trade-offs

- **A merge that combines both sides of a watched file raises a candidate after the flip.** Correct
  by the feature's own question, and at most once per such merge; the operator answers it once and
  the resolution fingerprint holds.
- **Branch-diff watching over-approximates** where a task branch merged prerequisites: their files
  are watched too. Over-watching a few files is the cheaper error than watching the whole tree.
- **An operator who records "ran it" on `main` with no locator loses drift for that evidence.** That
  evidence never had a reachable drift signal (F129), and the unwatched list names it and the fix
  (name a file or commit in the locator).

## Open Questions

1. **Legacy footprints.** Recommended: not scanned, listed as `recorded_before_watching`. The
   alternative is to scan them as today (whole tree) — a flood for exactly the rows the operator's
   live database already holds. Nothing reaches drift today, so neither choice changes what an
   operator sees until the second change ships.

## Round log

### Round 2 — 2026-09-24 (B6 R2)

Re-derived from `requirement_evidence.py` (`_take_footprint`, `read_footprint`,
`restamp_run_footprints`, `refresh_reachability`, `detect_drift`, `_changed`, `resolve_drift`),
`spec.py` (`detect_drift`, `list_drift`, `footprint_view`), `agent_actions.py:1207,1235-1243`,
`agent_trigger.py:1775-1801`, `task_transition_service.py:900-913`, `task_integration.py:517` (a
real `git merge`, so `is_reachable_from` holds after integration), and B5's change. Held: the
whole-tree claim (`:539`, `:969`), `detect_drift` as the only reader of `entries`, reasons 2 and 3
for the flip's safety. Corrected: `refresh_reachability` has a second caller; reason 1 ignored
restamp; the basis order for a reachable footprint with no branch; the agent recording route also
needs `main_branch`; `no_footprint` was missing from `unwatched`; task 1.7 passes today and is a
control. Added "Builds on B5".

### Round 1 — 2026-09-24 (B6 R1)

Derived from `requirement_evidence.py`, `spec.py`, `agent_trigger.py:1775-1800`, `worktrees.py:987`,
both specs, and a throwaway probe (above). F217 re-verified by reading `:1140-1152` (unchanged since
it was filed); the whole-tree claim re-verified by measurement.
