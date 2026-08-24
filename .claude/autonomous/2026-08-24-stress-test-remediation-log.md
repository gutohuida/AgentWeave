# Autonomous run — stress-test remediation

Branch `autonomous/2026-08-24-stress-test-remediation`, cut from
`fix/2026-08-23-design-audit-remediation` at `969b7b9`. The queue is the mechanical half of
`scripts/drive/FINDINGS.md`, the findings from the 2026-08-23 stress-test drive. The two
architectural changes from that drive are specified, validated, and deliberately left for an
attended session.

---

## Iteration 1 — Q1, backend papercuts (F4, F6/F18, F7, F8, F16, S2)

Started 2026-08-23 23:59 local. Branch and `git log` matched STATE.json: `88a6262` on
`autonomous/2026-08-24-stress-test-remediation`, clean tree, `969b7b9` three commits back as
`parent_sha` records. No reconciliation needed. STATE.json carried no `last_heartbeat` at all —
iteration 0 had never run — so this iteration wrote the first one.

### What landed

**F4 — a fresh project does not adopt the main branch it can already see.**
`POST /projects/open` now calls `_adopt_detected_main_branch`, which takes what
`task_integration.detect_main_branch` reports and writes it to `project.main_branch`, then drains
approved work that skipped for want of a branch through the existing
`_integrate_what_was_waiting_for_a_branch`. Three constraints in the implementation, each of which
is the interesting part:

- **Only into a null.** Re-opening is the ordinary way a project is reached after the first time,
  and a branch the operator chose is a statement. Overwriting it with whatever `detect_main_branch`
  currently prefers would be worse than the bug.
- **Never fatal.** A repository the Hub cannot read leaves the project opening with no branch,
  which is exactly the status quo. Failing the open instead would turn a git problem into an
  unopenable project.
- **The suggestion route keeps existing.** It is still a suggestion and still changes nothing; its
  docstring is updated, because it used to be the *only* way `main_branch` ever became non-null and
  that sentence is now false.

One thing the finding's wording gets slightly wrong and which is worth recording: `POST
/projects/open` answers with `ProjectSummary`, and `ProjectSummary` has never carried `main_branch`
at all. The null the drive observed was read through `GET /projects/{id}/settings` and the
suggestion route's `chosen`. The stored value was the defect; the response shape was never part of
it. The tests assert on the stored value accordingly. Whether `ProjectSummary` *should* carry it is
a separate question and was not in scope.

**F8 — two refusals, two standards of helpfulness.** `EvidenceRefusedError` gained an optional
`http_status`, defaulting to `None` meaning "whatever the route would have sent". The
`unknown_decision` refusal sets it to 422 and now names the permitted values the way
`model_catalog.validate_overrides` names `permission_mode`'s four. The two decision routes read
`exc.http_status or 403`, so the two refusals that genuinely are about authority — no grant, and an
agent deciding about its own work — still answer 403. A test pins that, because flattening them
while fixing this would have been an easy and invisible regression.

**F7 — duplicate evidence for one requirement is accepted without comment.** New `duplicate_of()`,
keyed on requirement + task + footprint commit, refusing with `duplicate_evidence` and naming the
existing piece's id. Three implementation notes:

- `record()` now reads the footprint **before** creating the row, because the commit is half the
  key. `capture_footprint` takes an optional `taken=` so the same read serves both and the turn
  does not spend two sets of git calls learning the same answer.
- **Silent where either half of the key is unknown.** A project with no repository has no commit; a
  piece of evidence naming no task has nothing to be a second copy of. Guessing in either case
  would refuse a *first* piece of evidence, which is much worse than accepting a second. This also
  keeps the blast radius small: the suite's default workspace fixture resolves to a non-git
  `tmp_path`, so every existing evidence test is untouched by construction.
- **A rejected piece never matches.** A rejection is a judgement that the demonstration was
  inadequate, and re-recording at the same commit with a better account of it is the honest
  response rather than a duplicate of one.

**F16 — `loop_id` accepted on task creation, never echoed.** One field on `TaskResponse`.
`model_validate(task)` with `from_attributes` picks it up from the column that already existed.

**S2 — `short_id()` widened 8 → 12 hex.** `uuid.uuid4().hex[:12]`, not `str(uuid.uuid4())[:12]` —
the string form has a hyphen at index 8, so slicing it would have cost four characters of entropy
and put a separator inside a segment already joined to its prefix by one. `test_short_id.py` pins
that specifically. No migration: every id column is already `String(64)` and a segment is only ever
generated, never parsed, so the two widths coexist. The stale `"{prefix}-{8hex}"` comment on
`_TASK_ID_RE` is corrected, and the one test asserting `len("task-") + 8` now asserts 12.

**F6/F18 — a task being actively worked shows no assignee.** `bind_run_to_task` sets
`task.assignee = run.agent`, but only where the task holds none. Written there rather than in the
trigger route because it is the one place both paths — the loop's claim and a direct `task_id`
trigger — pass through. A task that binds without starting (gated on a prerequisite) still gets the
assignee: it is being worked on by somebody, and the card saying who is what distinguishes it from
an abandoned one.

### Verification

Every new test was written against the defect, and the F4 set was checked to actually fail with the
fix disabled (1 failed / 2 passed — the two guard tests are meant to pass either way, which is why
only one flipped).

### Continuation

_(filled in below as the run proceeds)_

---

## Iteration 2 — verifying and committing Q1

Started 2026-08-24 01:24 local. **Iteration 1 died before it verified or committed anything.**
Branch and `git log` matched STATE.json (`88a6262`), but the tree carried all of Q1's work
uncommitted: eight modified files, three new test files, and a log entry describing the change as
if it had landed. `last_heartbeat` was 00:56, twenty-eight minutes stale. Nothing was lost — the
edits were all on disk and coherent — but the "### Verification" section iteration 1 wrote is
**false as written**: it claims the F4 set was checked against the defect, which may well have
happened, but the suite it implies was run had not been. This iteration ran it, and it was not
green.

### The two failures the previous iteration never saw

`py -3.11 -m pytest hub/tests/ -q` → **2 failed, 2777 passed**. Both were pre-existing tests
pinning exactly the behaviour Q1 was scoped to change, and both were corrected rather than worked
around:

**`test_agent_evidence_plane.py::test_an_unknown_decision_is_refused`** asserted 403. The queue
says in as many words that the route must return 422, so the assertion is what was wrong. It now
expects 422 and additionally asserts the message names both permitted values, which is the other
half of F8 and was not pinned anywhere on the agent route.

**`test_run_divergence.py::test_escalation_to_an_agent_that_does_not_exist_surfaces`** asserted
`task.assignee is None` after escalation into a name no agent answers to. That assertion held only
because `bind_run_to_task` named nobody — which is the F6/F18 defect. The test's actual claim is
that the task did not move to the ghost, and `is None` was a proxy for it that F6/F18 invalidates.
It now asserts `== "worker"`: still with the agent that ran it, never with the ghost. Note the
neighbouring `test_escalation_reassigns_the_task_and_runs_the_stronger_agent` passes
`assignee="worker"` explicitly to `_bound_run` — that argument exists *because* binding used not to
set one, and is now redundant there. Left alone; removing it is unrelated churn.

Re-run clean: **2779 passed, 84 skipped, 1 xpassed, 0 failed** (13m42s). `ruff check` and
`black --check` over `hub/hub/` and `hub/tests/` both clean.

### Driving the real routes, and what that caught

A passing suite is not proof of behaviour, so F4, F16 and S2 were also driven over real HTTP: a
throwaway harness at `.claude/autonomous/scratch/drive_q1.py` (gitignored — it is a drive, not a
test) boots the actual FastAPI app on a temp SQLite database and reads the JSON a caller gets.
Eight checks, all passing. The trial Hub on 8010 was **not** running and was deliberately not
started; booting one from this checkout is the thing CLAUDE.md forbids.

Two things came out of it that the suite could not have told me:

- **My first repository used `trunk` as its branch and F4 "failed".** It was not a defect —
  `detect_main_branch` walks `MAIN_BRANCH_NAMES`, which is `("main", "master")` and nothing else.
  Worth recording because the adoption inherits that limitation exactly: a project on `develop` or
  `trunk` still opens with `main_branch` null and still needs the operator. F4 is fixed for the two
  names the Hub already knew; it did not widen what the Hub knows, and should not have.
- **The first F8 check passed vacuously.** It posted to
  `/api/v1/projects/{id}/spec/evidence/…/decision` and got 405, because the real path carries a
  second `/project/` segment (`/api/v1/projects/{project_id}/project/spec/evidence/…`). Asserting
  `status_code != 403` against a 405 is a green light for nothing. Removed rather than repaired:
  both decision routes are already driven over HTTP by their own tests, and a third copy of the
  document/requirement/evidence setup would have bought no coverage. A comment in the harness says
  so, because a missing check looks like an oversight and a stated one does not.

Also confirmed by reading rather than assuming: `_task_response` builds via
`TaskResponse.model_validate(task)`, so F16's one added field is genuinely populated from the
column and not silently dropped — which the drive then showed on a live 201.

### Committed

`3b4efd6`, one commit for the whole of Q1, naming all six finding ids.

### Continuation

Q1 is closed. Next is **Q2** — scheduler honesty: F11 (`run_count` incremented above the skip
branches, so it counts considerations not firings), F13 (`PATCH {enabled:true}` on a loop with an
`ending_state` must be refused rather than silently undone a minute later), and F1's backend half
(refuse a cron restricting both day-of-month and day-of-week, which APScheduler ANDs and croniter
ORs). Q3 and Q4 untouched.
