# Autonomous run — 2026-08-27, the rest of the work

**Branch:** `autonomous/2026-08-27-the-rest-of-the-work`, cut from `master` @ `a90cad6`
**Runner:** `claude`, model `claude-opus-5`, `unattended-full-access`
**Stop at:** 17:00 local. **Driver:** Windows Scheduled Task `AgentWeaveAutonomousSession`, one fresh
headless process per firing, every 5 minutes.

Newest entry at the **bottom**. Written for a human who was not watching.

## Iteration 0 — what was prepared, and what was decided before the run started

Prepared in an attended session on the morning of 2026-08-27, so the loop meets no question that
thirty seconds of operator time could have answered.

**The state of the world at arming.** `master` is at `a90cad6` and fully CI-green — run
`33052879055`, all nine cells including `hub-test` on Linux, which is the cell that had been red on
the overnight branch. It carries: last night's 12 work commits, the width-test race fix, the F70 and
F71 fixes the operator decided this morning, both in-flight openspec changes synced into
`openspec/specs` and archived, and this run's own brief. `openspec/changes/` holds nothing active,
so any change this run creates is its own.

**The round discipline is the point of this run.** The operator restated it twice this morning —
once as a requirement (*"If any spec is needed and explore follow the same pattern explore/propose
-> review -> review"*) and once as a reminder mid-preparation (*"Dont forget the explain/propose
review review pattern"*) — and asked for it to be recorded as a standing pattern, saying *"Take not
of this pattern I liked a lot."* It is `method_reminders[0]` and `limits[0]` in `STATE.json`, and
every change in the queue is expanded into its rounds rather than left as one item. **Never drop a
round to save time. Drop the last item in the queue instead.**

**Three decisions taken with the operator awake:**

1. **F58 goes all the way through implementation.** The operator was told plainly that this is the
   one item that can damage a repository — approving one task merged 13 files and 16 commits,
   including another task's unreviewed test — and was offered a stop-at-reviewed-proposal option.
   They chose full implementation. *Rejected:* stopping after the two review rounds for sign-off.
   The condition of that choice is the blast-radius limit written into `F58-IMPL` and repeated in
   `limits`: exercise it only against a throwaway project or an existing drive project, never
   against `proj-5e960453` (this repository) or `proj-18e5d4e0` (ledger-stress, which carries state
   other findings depend on), and stop rather than rewrite history in a repository this run did not
   create.
2. **Order: F58, Q4, Q5, approval-authority, Q8, then e2e.** The operator was told ~7.5 hours fits
   two or three changes and not five, and chose this order knowing it will not finish. *Rejected:*
   starting with the two already-scoped changes (Q4/Q5) to bank completed work early.
3. **Opus for everything.** *Rejected:* Sonnet-5, which is what ran last night and did well; and a
   split of Sonnet for implementation with Opus for the review rounds, which was rejected for adding
   a per-item model switch the driver would have to get right unattended.

**Two stalls found and removed during preparation, both of which would have cost the run:**

- **`parent_sha` cannot name its own commit.** The brief has to be committed before it has a SHA, so
  pinning `parent_sha` to the commit carrying the brief chases its own tail one commit at a time.
  Left as it was, the loop would have cut its branch from a tree holding *last night's* queue and
  worked the wrong list, silently. Resolved by branching from `origin/master` with `parent_sha` as a
  floor, plus a self-check naming what a correctly-cut `STATE.json` looks like — 22 items, `current:
  F58-EXPLORE`.
- **The driver refuses to run unless the branch already exists.** `run-iteration.ps1` stops with
  *"Current branch does not match STATE.json branch"* when they differ. The brief originally told
  the loop to cut its own branch on the first iteration, which would have deadlocked **every**
  firing — the loop could never reach the instruction telling it to fix the condition preventing it
  from running. So the branch is cut here, in the attended session, before the driver is installed.

**What is not verified.** The trial Hub on 8010 is up and answers `{"status":"ok"}`, but it is
running code from before this morning's work (`hub_started_on_sha` is `7219090`, now a distant
ancestor). Any item that drives it live must restart it first with `environment.restart_hub` and
confirm the **project list**, not `/health` — a Hub on a stale database still answers `ok`.

**Queue:** 22 items. `F58-EXPLORE` → `F58-R1/R2/R3/IMPL` → `Q4` ×4 → `Q5` ×4 → `QA` ×4 → `Q8` ×4 →
`QE2E`. The last is the operator's explicit fallback — *"If it finishes way earlier do another
e2e-loop with fixes"* — and is gated on every item above it being closed.

**Expect this queue to be unfinished at 17:00.** It is ordered so that stopping anywhere leaves
complete changes rather than a row of half-written proposals. `decisions_for_user` opens with the
pre-authorisation that says so, so no iteration needs to ask.

## Iteration 1 — F58-EXPLORE: the exploration exists, and it corrects the document that ordered it

**Done:** `openspec/explorations/2026-08-27-per-task-worktrees.md`, 337 lines, nine sections.
Exploration only, as the queue item required — no proposal, no code, no re-opening of option (c).

**Reconciliation:** branch, `git log` and `STATE.json` agree. `HEAD` is `24b68af`, the branch is
`autonomous/2026-08-27-the-rest-of-the-work`, `parent_sha` `a90cad6` is its grandparent. Tree was
clean at start. Nothing to reconcile.

### What the exploration establishes that was not established before

**1. The rejected options were re-run, not re-read — and (a) is worse than the record says.** Built
`testbed/f58demo2`: one per-agent branch carrying two tasks interleaved, `B1 · A1 · B2 · A2`, task
A's evidence naming `A2`. Each mechanism run against a `git reset --hard` back to base so no run
contaminated the next. Files landing on `main`:

| mechanism | lands | verdict |
|---|---|---|
| today, `merge --no-ff A2` | `A1 A2 B1 B2` | ships all of task B |
| (a) `cherry-pick base..A2` | `A1 A2 B1 B2` | identical to today |
| (a) `cherry-pick A1..A2` | `A2 B2` | ships `B2` **and drops `A1`** |
| (b) squashed diff of `A2` | `A2` | task A's own `A1` missing |
| (c) task branch cut from `main` | `A1 A2` | correct |

The third row is new. The exploration of record said the tighter form of (a) merely fails to
separate interleaved tasks; measured, it **also loses a commit of the approved task's own work**. It
ships partial work and somebody else's work in the same merge. That strengthens (c) rather than
weakening it, so the decision stands untouched.

**2. Why the green test is green, which is the part that had never been written down.**
`test_later_commits_on_the_branch_are_not_merged` commits *after* the evidence commit (`:311`) and
asserts that commit stays out. A descendant of the target is excluded by **every** candidate
mechanism — merge, cherry-pick range, squash, per-task branch alike — so the assertion restates
git's ancestry ordering rather than testing the guarantee its docstring names. Thirty-three lines
below it, `test_rode_along_commits_names_what_actually_landed` (`:342`) builds the *earlier*-commit
case and asserts the earlier commit **still lands**. The suite therefore contains one test whose
docstring says the bug cannot happen and one that pins the bug as expected, and both pass. Written
into the exploration as a mandatory `tasks.md` item for R1: the second test's assertion must be
**inverted**, not deleted, and the first must gain the earlier-commit case.

**3. The dependency objection holds — and the citation that dissolved it has drifted.** Verified by
line: `dependency_gate.MET_STATUS = "approved"` (`:31`); the gate fires on `-> in_progress` only
(`task_transition_service.py:375-380`); `integrate_task` runs on `to_status == "approved"`
(`:434-435`). Two corrections to the exploration of record, both carried into the document: its
citation `task_transition_service.py:375` now lands on the **dependency gate's own `if`**, not on
`integrate_task` (which is at 435); and it never stated which edge the gate sits on, which is the
load-bearing part of the argument — because the gate is on `-> in_progress`, the dependent may not
*begin* until the prerequisite is merged.

**4. A place where (c) is a regression, which nobody had named.** Integration is best-effort and
approval is not — `test_task_integration.py:14` states it outright: *"Nothing here may block an
approval."* Six paths leave a task `approved` with its work **not** on `main`: `NO_MAIN_BRANCH`,
`NOT_A_REPOSITORY`, `NOTHING_TO_MERGE` (every `paths`-footprint project, a supported shape),
`CHECKOUT_DIRTY`, `CHECKOUT_ELSEWHERE`, and a `FAILED` conflict. Today, if one agent holds both
tasks, the dependent inherits the prerequisite's work anyway because it is the same branch — the
mechanism that *is* F58 is quietly carrying dependent work. A fresh per-task worktree cut from
`main` would not. This is now open question 1 for R1, with three candidate shapes and no choice
made here.

**5. Cost and the reaper, measured.** `ledger-stress`: 3 agents, **19 tasks**, 5 linked checkouts
today (3 working, 2 review). Per-task, that is up to 19 working checkouts. This repository is 2028
tracked files / **37.7 MiB** of working tree, so 19 task worktrees is **~716 MiB**. Agents are
bounded by the roster; tasks are bounded by nothing. And **there is no reaper**: the only path that
removes a working worktree is `session_sync.py:131`, on roster removal. Also recorded honestly —
the precedent cited when the decision was taken (*"a review checkout is bounded and reused"*) is
precedent for the **opposite** property: `ensure_review_checkout` bounds by re-pointing, which a
task worktree cannot do because it holds in-flight work. The cost argument has to be made on its
own rather than borrowed. That does not change the decision; it changes what R1 must carry.

**6. The largest structural obstacle, found by reading the trigger path.**
`resolve_agent_workspace` is called at `agent_trigger.py:535`. `resolve_bound_task` does not run
until `:558`. **The workspace is chosen before the Hub knows which task the turn is about.**
`resolve_bound_task` documents itself as *"Reads only"* (`run_task_binding.py:247`), so moving it
earlier looks safe — the exploration says explicitly that this must be verified rather than assumed.
Related and unanswered: what workspace a writing agent gets on a turn with **no** bound task at all
(ad-hoc composer turns, chat).

**7. Migration, with the call sites enumerated.** Eleven sites assume "one worktree per agent, found
by agent name alone", tabulated in the document — including `requirement_evidence.footprint_root`
(`:270`, `:285`), which resolves evidence's footprint from the actor with no task in hand, and
`api/v1/agents.py:1160`, which tells the agent its branch name in its own turn context. Four
migration questions with no answer today. My reading is recorded as *input to R1, not a decision*:
the honest migration is **no migration** — leave existing `agentweave/<agent>` branches untouched so
nothing is lost and `retry_integration` keeps working, provision per-task worktrees only for work
started after the change, and give the operator a read-only surface naming legacy branches that
still carry unmerged commits.

### Verification

No code changed, so the suite is unaffected and was not re-run — the green recorded in
`green_at_arming` still stands for this tree. The verification appropriate to this unit of work was
done instead, and it was not cheap: **every file:line citation in the document was opened and read**,
which caught three off-by-one citations of my own (`NO_MAIN_BRANCH` 51→52, `integration_targets`
141→142, `commits_riding_along` 186→189) and one substantive error (line 375 is the dependency
gate's `if`, not a comment block), all corrected before commit. Every git-behaviour claim was
**measured in a throwaway repository** rather than reasoned about — `testbed/f58demo` reproduces F58
from first principles with no Hub involved, `testbed/f58demo2` runs the four-mechanism comparison.
Both are gitignored and left in place as evidence.

**Not done, deliberately:** no live drive against the trial Hub. It is still running `7219090`, a
distant ancestor, and nothing in this document depends on a running instance — every claim is a file
read at `24b68af` or a raw-git experiment.

**Contamination note, per the method:** the four-mechanism comparison is a test I designed myself
against a hypothesis I already held, so it inherits my blind spots. What it is *not* is a
confirmation of the answer I expected — row three came out worse than I predicted from the
exploration of record. The reproduction in `testbed/f58demo`, by contrast, reproduces a failure
found live by someone else on 2026-08-26 and is the stronger of the two.

**Next:** `F58-R1` — propose `work-is-isolated-per-task` from this document. The exploration ends
with six open questions ordered by what they block; R1 closes them in `design.md` with rejected
alternatives, and questions 1 and 2 are the ones that decide the shape of the change.
