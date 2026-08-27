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

## Iteration 2 — F58-R1: the change is proposed, and two of its answers came out of the code rather than the exploration

**Done:** `openspec/changes/2026-08-27-work-is-isolated-per-task/` — `proposal.md`, `design.md`
(seven decisions, each with its rejected alternatives), `tasks.md` (8 phases, 55 tasks, tests first),
and six spec deltas. `npx openspec validate --all --strict` → **42 passed, 0 failed**, first try.
Propose only; R2 and R3 are still ahead of any implementation.

**Reconciliation:** branch, `git log` and `STATE.json` agree. `HEAD` was `468da44`, the branch is
`autonomous/2026-08-27-the-rest-of-the-work`, `parent_sha` `a90cad6` is in its history, tree clean.
Nothing to reconcile.

### The six open questions, closed

1. **What a task worktree is cut from** — the project's integration base (`Project.main_branch`,
   else `HEAD`), then each direct prerequisite's accepted evidence commit merged in. The option that
   *sounded* cleanest — make the dependency gate require *integrated* rather than `approved` — is
   **refused by the code**: `NOTHING_TO_MERGE` fires for every `paths`-footprint project, which
   `task_integration.py:150` calls "a supported project shape, not a degraded one", so that option
   would leave such a project permanently unable to advance a dependency chain. Also recorded: three
   of the six skip reasons are facts about the *operator's* checkout and cannot apply to a fresh task
   worktree, which is why the merge that could not happen into `main` can happen into the task branch.
2. **Moving `resolve_bound_task` above the workspace** — verified rather than assumed, as the
   exploration demanded. Three reads, no writes (`run_task_binding.py:218-223`, `:120`, and the
   conversation binding), and its own docstring states the invariant: *"Safe to read twice because
   the mutations never feed back into this"* (`:257-259`). `conversation` is available from `:362`.
   One real behaviour change, written into the spec delta: a request naming a nonexistent task is
   refused *before* a checkout is provisioned instead of after, so it stops leaving one behind.
3. **A turn with no bound task** — keeps the per-agent worktree, and that is not a legacy path: the
   workspace is keyed by what the turn is *about*, and "no task" is a permanent category
   (`db/models.py:1048-1049` says unbound runs are legitimate). The conversation binding is what
   stops the two schemes coexisting by accident.
4. **Migration** — no migration, made precise as **grandfather the task, not the branch**. A task
   with a prior run carrying a non-null `Run.snapshot_commit_sha` and no task branch of its own stays
   on the per-agent workspace for life. The discriminator is a recorded fact, and it is
   self-extinguishing: after this ships, no new task can enter that state. The alternative —
   *adopting* the per-agent branch as the task branch — was rejected in writing because it would ship
   the guarantee "one approval lands one task's work" while that guarantee was false, silently, for
   an unbounded set of tasks. That is this repository's named failure mode, chosen deliberately.
5. **Reaping** — release on either terminal status, after `integrate_task` runs, keeping the branch
   always. Both terminal statuses have operator-only exits (`task_transitions.py:145-150`), so the
   branch surviving is what makes a reopened task get its work back. The disk backstop is a visible
   count plus an explicit operator release; a hard cap that refuses turns and LRU eviction are both
   rejected with reasons.
6. **The two tests** — phase 1, and it opens with a warning that changes what the work is (below).

### What this round found that the exploration had not

- **Inverting the assertion in `test_rode_along_commits_names_what_actually_landed` would produce a
  red test that is red for the wrong reason.** Both fixtures build `agentweave/builder` *by hand*
  with `commit_on_branch(tmp_path, AGENT_BRANCH, …)` (`:307`, `:342`) and never touch worktree
  provisioning — so the shape of the branch is decided by the test, not by the product. Flipping
  `assert earlier in merged` alone fails against *any* implementation. `tasks.md` therefore names the
  fixture change (put `earlier` on a second task's branch) beside every assertion change, and opens
  with a paragraph saying so.
- **A silent-empty-list failure mode nobody had named.** `list_agent_branches` (`worktrees.py:551`)
  strips `refs/heads/agentweave/` and requires `_AGENT_NAME_RE` to match what remains. A task branch
  `agentweave/task/<id>` contains a `/` and fails, so `detect_conflicts` and
  `GET /worktrees/conflicts` would return `[]` forever and look healthy. Conflict detection is
  exactly what per-task isolation makes *more* likely to matter.
- **Task ids match the agent-name regex.** `_AGENT_NAME_RE` is `^[a-zA-Z0-9_-]{1,32}$`
  (`worktrees.py:65`) and task ids are `task-<12 hex>` (`spec_tasks.py:206`), so `agentweave/task-…`
  and `.agentweave/worktrees/task-…` would be indistinguishable from a real agent's. The `task/`
  segment is load-bearing, not cosmetic — `/` is not in that character class.
- **The exploration's guess at which capabilities this touches was wrong, and the correction is in
  `proposal.md`.** It named `agent-flows`, `agent-run-sandboxing` and `agent-conversation-workspace`.
  Checked: sandboxing's requirements say "the run's workspace" without saying how it is keyed;
  the review-checkout requirements are about a detached checkout at an evidence commit, unaffected
  because the branch survives release; `agent-flows` says nothing about workspaces. The requirement
  that actually carries the isolation guarantee is `operator-agent-creation`'s *"the scheduler
  provisions **that agent's** isolated worktree"* — which was not on the list.
- **`footprint_root` cannot be fixed by a derivation.** `RequirementEvidence.task_id` is
  agent-supplied and optional (`api/v1/agent_actions.py:840`), and deriving from `Run.task_id` gives
  the *author's* task tree for a **review** run, which is bound to the task it inspects but executes
  in a detached review checkout. So the run records the workspace it was actually given. That also
  corrects a case wrong today: a reviewer's evidence is currently footprinted at its own agent
  worktree, which is not the tree it reviewed.

### Verification

No code changed, so no suite was run and `green_at_arming` still stands for this tree. What was done
instead, because a propose round's failure mode is a plausible artifact that does not match the code:

- **Every file:line citation in the three artifacts was opened and checked mechanically** — 57
  (path, line, expected-text) assertions run as a script over the working tree, not read by eye.
  **Four were wrong and are fixed**: `_AGENT_NAME_RE` 112→65, `snapshot_worktree`'s `git add -A`
  463→459, `ConflictReport` 600→583, and the "supported project shape" sentence 142→150 (142 is
  `integration_targets`' `def` line, which is what the exploration cited — the sentence is eight
  lines below it).
- **The four MODIFIED requirement headers were matched against the live specs** so each delta
  replaces a requirement that exists: `agent-configuration:218`, `agent-context-onboarding:153`,
  `operator-agent-creation:63`, `task-lifecycle-governance:571`.
- `npx openspec show --json` was read back to confirm the deltas parse as intended: **8 deltas, 4
  MODIFIED and 4 ADDED**, none silently swallowed.
- `npx openspec validate --all --strict` → 42 passed, 0 failed. `npx openspec list` → 0/55 tasks.

**Contamination note, per the method:** every finding above came from reading the code against
artifacts I had just written, which is the weakest form of review and the reason R2 and R3 exist.
The citation sweep is the exception — it is mechanical and could have failed, and it did, four times.

**Left for R2/R3 deliberately**, written into `design.md` as open questions rather than answered
here: whether `commit_for_task_review` still resolves after a checkout is released (argued yes,
not executed); what `integration_targets` does when one task's evidence spans a grandfathered
per-agent branch *and* a later task branch, since it keys by `EvidenceFootprint.branch` and would
produce two targets; a re-derivation of the eleven "one workspace per agent" call sites from the
code rather than from the exploration's table; and the F70 wedged-review recovery against the
release-on-terminal rule.

**Next:** `F58-R2` — the first review round. Claim by claim, against the code, fixing the artifacts.

## Iteration 3 — F58-R2: the first review round, and it found a way for two agents to share one checkout

**Done:** the first independent review pass over
`openspec/changes/2026-08-27-work-is-isolated-per-task`, claim by claim against the code. No
implementation — R3 still has to run. All four questions R1 left open are closed, two of R1's
answers are **overturned**, one new decision (`D8`) was added, and 65 file:line citations were
re-verified mechanically. `npx openspec validate --all --strict` → 42 passed, 0 failed. Deltas: **9**
(was 8), 5 ADDED / 4 MODIFIED. Tasks: **66** (was 55).

**Reconciliation:** branch `autonomous/2026-08-27-the-rest-of-the-work`, `HEAD` was `6fe175b`,
`parent_sha` `a90cad6` in history, tree clean. `STATE.json` said iteration 2 / `F58-R2` next.
Everything agreed; nothing to reconcile.

### The finding that most changes the work — two agents, one task, one working tree

Under per-task isolation, nothing stops two live agent processes being given the **same directory on
the same branch**. Today that is impossible, but not because any rule says so — it is a *consequence*
of two unrelated facts: a checkout belongs to an agent (`worktrees.worktree_path`), and an agent may
have only one run in flight (`agent_trigger.py:439-445` refuses per `(project, agent)`). Keying the
workspace by task breaks the coupling and nothing else replaces it:

- `resolve_bound_task` takes the task from the delegation, the explicit `task_id`, or the
  conversation, and never consults `Task.assignee`;
- `bind_run_to_task` only fills `assignee` when it is **empty** (`run_task_binding.py:350-351`), so
  it cannot refuse a second holder either.

An operator starting task `T` on `builder-2` from the board while `builder-1` is already running on
`T` is an ordinary sequence of clicks. That is the silent lost update `worktrees.py`'s own module
docstring says the module exists to prevent, reintroduced along a new axis. Written up as **D8**,
with three deliberate exemptions (review turns, which take the review checkout; read-only agents;
grandfathered tasks) and a new spec requirement, *A task's checkout is worked by one turn at a time*.

**And a second-order catch inside my own D8.** The first draft said the refusal sits "beside the
existing per-agent one". It cannot: the per-agent 409 runs thirty lines before `repo_root` exists and
long before any binding is resolved, so the turn's task is not known there. The refusal has to go
immediately after D2's relocated `resolve_bound_task` — which makes **D2 a prerequisite of D8**, not
a neighbour. Corrected in both `design.md` and task 4.14.

### R1's grandfathering discriminator was wrong in both halves

R1 proposed reading it live: a prior run bound to the task with a non-null `snapshot_commit_sha`,
*and* no task branch of its own yet.

- **Under-inclusive, in the direction that loses work.** `snapshot_commit_sha` is written only from
  `worktrees.snapshot_worktree` (`agent_trigger.py:1524-1533`, `:2083-2092`), which returns `None`
  when the worktree is **clean** (`worktrees.py:457-458`). An agent that commits its own work ends
  its turn clean and records `NULL`. That task has real committed work on the per-agent branch, would
  not be grandfathered, and its next turn would start in a fresh checkout cut from the integration
  base **with all of its own prior work missing** — exactly the loss of continuity the two rejected
  alternatives were rejected for causing.
- **The second half is not a recorded fact at all.** "No task branch exists yet" is a `git rev-parse`
  against a ref an operator can delete, so a task could flip schemes mid-life because someone tidied
  up branches.

**Corrected:** the migration stamps `Task.workspace_scheme = 'agent'` for every task with at least
one run at that moment, and the resolver reads that column and nothing else. Deliberately
over-inclusive — a grandfathered task that had nothing to preserve loses only isolation it never had,
where the opposite error loses an agent's work — and self-extinguishing *by construction* rather than
by argument. The `operator-agent-creation` delta and tasks 4.4/4.5/4.11 were rewritten to match.

### The four open questions, closed

1. **`commit_for_task_review` after release** — D5 was right, and now for a checked reason rather than
   an argued one. It is a single `select` over `RequirementEvidence` joined to `EvidenceFootprint`
   (`requirement_evidence.py:653`) and touches no path at all; `ensure_review_checkout`
   (`worktrees.py:352`) resolves and `worktree add --detach`es **from `repo_root`**, against a ref
   store every worktree shares, and the task branch survives release.
2. **`integration_targets` producing two targets** — a false alarm, and the code says so in as many
   words: "work produced on two branches has to be merged twice, and silently dropping one of them
   would integrate half of what was approved" (`task_integration.py:178-180`). Merging twice is
   correct. D4 forbids the situation anyway.
3. **The eleven call sites, re-derived from the code** — see below. Four were missing.
4. **F70's wedged-review recovery** — no interaction. It leaves the task in `under_review`, which is
   not terminal, so release never fires, and the recovered turn takes the review checkout regardless.

### Four surfaces R1 and the exploration both missed, and one that does not exist

Re-derived by sweeping every reference to `worktree_path`, `branch_name`, `existing_worktree`,
`resolve_agent_workspace`, `ensure_worktree`, `release_worktree`, `list_agent_branches`,
`detect_conflicts`, `worktree_root` and every literal `.agentweave/worktrees` path across `hub/hub/`
and `src/`:

- `project_workspace.py:175-178` — refuses to register a project whose path runs through
  `.agentweave/worktrees`. A task checkout is the same hazard by a different path.
- `project_lifecycle.py:240-241` — refuses relocation while `.agentweave/worktrees` is non-empty. A
  project whose only live checkouts are *task* checkouts would relocate, breaking every git worktree
  registration (they store absolute paths).
- `api/v1/worktrees.py:148-156` (`GET /worktrees/{agent}`) — the **only** worktree endpoint with a UI
  caller, and its answer is wrong for every task-bound turn.
- `api/v1/agents.py:1162-1164` — "other agents work in separate worktrees … they cannot see yours".
  True per agent; false as written once a checkout belongs to a task.

**`WorktreesPanel.tsx` is a stub.** The proposal listed it as a surface that assumes one workspace per
agent. It assumes nothing: it renders a hard-coded `EmptyState` ("No worktree activity") and calls no
API. The operator-facing surface is `WorkspaceLocation` inside `AgentSettingsPage.tsx`, reading
`GET /worktrees/{agent}`. The `agent-configuration` delta was already written against *that*, so the
delta was right and the prose naming the component was wrong. Task 6.4 was rewritten and 6.4b added.

### Three more corrections to R1's reasoning

- **"Leaves nothing provisioned" was asserted with no mechanism.** By the time a prerequisite merge
  can conflict, `worktree add` has created the directory *and* the branch, and the failed merge has
  left `MERGE_HEAD`. The obvious cleanup is the wrong one: `release_worktree` **snapshots the dirty
  tree onto the branch** first (`worktrees.py:537-538`), so it would commit a conflicted merge as the
  agent's work and keep the branch carrying it. D1 now names the unwind explicitly — `merge --abort`,
  `worktree remove --force`, `branch -D`, `worktree prune`, in that order because git will not delete
  a checked-out branch — plus the one state neither provisioning nor release owns (a process killed
  mid-merge; `ensure_worktree`'s idempotent path at `:268-275` returns a registered directory
  unexamined).
- **D2 moves four observable answers, not one.** R1 recorded only the project-workspace 409
  precedence. The new position is also above the review-turn refusal (`:506-509`) and both `work_dir`
  400s (`:492-497`, `:511-516`). Task 3.2b pins all of them.
- **`list_agent_branches` has two filters, not one.** R1 named the `_AGENT_NAME_RE` match
  (`:565-566`); `append_record` also compares the registered worktree path against
  `worktree_path(repo_root, agent)` (`:567-568`). Relaxing only the regex changes nothing. Also
  corrected: "and look healthy" overstated it — `GET /worktrees` and `/worktrees/conflicts` have **no
  caller in `hub/ui/src/`** (a gap already recorded on 2026-08-18), so the degradation would be
  invisible rather than misleading.

### What held

- `resolve_bound_task` really is read-only, as R1 claimed and the exploration demanded be checked:
  `binding_for_delivery`'s one `select` (`:219-222`), `resolve_task_for_project`'s one
  `session.get` (`:120`), `binding_for_conversation`'s one `session.get` (`:402`). No writes.
- D5's release-after-integration ordering, D3's keying by what the turn is about, D6's `task/`
  segment being load-bearing, and D7's "record the workspace rather than derive it" all survived the
  round unchanged.
- The six skip reasons D1 leans on are exactly six: `ALREADY_INTEGRATED` is not one of them, because
  in that case the work *is* in the target.

### Verification

No code changed, so no suite was run; `green_at_arming` still stands for this tree. Instead:

- **65 (file, line, expected-text) assertions** run as a script over the working tree, covering every
  citation this round introduced or altered. **Nine were wrong on the first run and are fixed** —
  `ensure_worktree`'s idempotent block, `select(Run.id)`, the `ReviewTurnRefused` raise, the
  `work_dir` isolation guard, `ConflictInfo`, its `paths` field, `get_agent_workspace`'s docstring,
  its `worktree_path` call, and the endpoint's last line. Final run: **65/65, 0 wrong.**
- `npx openspec validate --all --strict` → 42 passed, 0 failed.
- `npx openspec show --json` read back: **9 deltas, 5 ADDED and 4 MODIFIED**, with D8's requirement
  parsed as its own ADDED requirement rather than folded into the grandfathering one.
- `npx openspec list` → 0/66 tasks.

**Contamination note, per the method:** D8, the D4 correction and the four missing call sites came
from reading the code against artifacts *someone else's process* wrote (R1 was a separate iteration),
which is the shape the discipline is for. The D8 placement error and the nine bad citations are the
opposite — mistakes I made this round and caught in the same round, which is weaker evidence and is
why R3 exists.

**Left for R3, written into `design.md` rather than left in my head:** whether a *flow* or a *job* can
start a second writing turn on one task by a route that never reaches `_trigger`'s guard (D8's blind
spot, since it has had one round of scrutiny rather than two); whether anything can write
`Task.workspace_scheme` after the migration, since "the set only shrinks" rests entirely on that;
and a sample of the load-bearing citations for the failure the mechanical sweep cannot catch — a line
that is right about the number and wrong about what it means.

**Next:** `F58-R3` — the second independent review round, on what R2 missed.

## Iteration 4 — F58-R3: the final review round, and D8 would have thrown operator input away

**Done:** the second and final independent review pass over
`openspec/changes/2026-08-27-work-is-isolated-per-task`. No implementation. R3 was told to assume R2
had also got something wrong, and it had — **six corrections**, one of them the kind that only shows
up when you read the *caller* of the code a decision was written against. `npx openspec validate
--all --strict` → 42 passed, 0 failed. Deltas: **9**, 5 ADDED / 4 MODIFIED (unchanged). Tasks: **69**
(was 66).

**Reconciliation:** branch `autonomous/2026-08-27-the-rest-of-the-work`, `HEAD` was `c5aae39`, tree
clean, `STATE.json` said iteration 3 / `F58-R3` next. Everything agreed; nothing to reconcile.

### The finding: D8's refusal is transient, and it lands in the branch built for permanent failures

R2 asked R3 to check whether a *flow* or a *job* could start a second writing turn on one task by a
route that misses D8's guard. **The answer is no** — and asking it is what surfaced the real defect
one layer out.

Every route to a turn funnels the same way: `new_entry` → `schedule_agent` → `trigger_agent_directly`
(nine `new_entry` sites, twenty `schedule_agent` sites, and `trigger_agent_directly` has **exactly
one caller**, `turn_scheduler.py:125`). So the guard is reachable by everything. But `schedule_agent`
sorts a `TriggerAgentError` into two buckets and only `workspace_unavailable` is temporary.
Everything else falls to `turn_scheduler.py:165-183`, whose comment states its own premise: *"a
refusal raised here … repeats identically forever"*. It increments `delivery_attempts` and at
`DELIVERY_ATTEMPT_LIMIT` (`inbound_queue.py:174`, three) marks the entries `withdrawn`.

A collision with another agent is the one refusal in that set that does **not** repeat forever — it
clears when the holder's run ends. Three ticks of an ordinary flow would have thrown the message
away. The sibling per-agent rule never has this problem because it never reaches that branch:
`schedule_agent` reads the per-agent `running` fact itself at `:60-66` and returns
`terminal_failure=False`, leaving the entry queued.

R2 wrote D8 by reading `agent_trigger.py`, where the refusal is raised, and never read the caller
that decides what a refusal *means*. Closed with a transient marker in the shape
`workspace_unavailable` already establishes (task 4.15), plus a new spec scenario — *the refused
input is not thrown away*.

### Five more corrections

- **"Refused with a 409" is not observable.** `schedule_agent` never re-raises (`:206-209`), so
  `/trigger` answers **200 `queued`** with a `waiting_reason` (`agent_trigger.py:1011`, `:1030-1040`).
  The 409 is a field on an exception object, not an HTTP answer anybody sees — and the same is
  already true of the per-agent 409, which is defence-in-depth behind `schedule_agent`'s own check.
  The spec requirement never said 409 and was right; design D8 and task 4.12 both did, and now say
  which layer each fact is asserted at.
- **The spec delta was over-broad against its own decision.** D8 names three exemptions; the
  requirement stated two, and its opening — "while a writing turn is in flight for a task" — covers a
  **grandfathered** task, which D8 deliberately exempts. Fixed in the delta, not by narrowing D8.
- **D1 said "that commit" where the code returns a list.** `integration_targets` returns one target
  *per branch* and can return several for one prerequisite — the very fact R2 used to close open
  question 2 (`task_integration.py:178-180`). The tasks were already written against a
  `prerequisites` sequence, so only the prose was wrong.
- **D1 named only half the failure.** A recorded `commit_sha` whose object is no longer in the
  repository — an operator deleted the branch, the same hazard that killed half of R1's
  grandfathering discriminator — fails `git merge` without ever conflicting. Same unwind, different
  message, because "conflicts with yours" and "is no longer in this repository" ask the operator for
  different things. Task 2.6b added.
- **The `_trigger` that does not exist.** R2 called the function `_trigger` throughout. There is no
  `_trigger` in the tree; it is `trigger_agent_directly` (`agent_trigger.py:331`), and `_trigger`
  greps to nothing. Costs an implementer a search; corrected everywhere.

### What held, checked rather than argued

- **D5's premise — one writer.** "Released at a terminal status" is only a bound if every route
  passes it. Swept `hub/hub/` and `src/`: `task.status = to_status`
  (`task_transition_service.py:402`) is the **only** assignment to `Task.status` anywhere, there is
  no `update(Task).values(status=…)` (the one `update(Task)` sets `loop_id`, `api/v1/jobs.py:223-229`),
  and no migration writes it. Checked the other escape too — a task deleted while unfinished — and
  there is **no task-delete endpoint at all**; the only `@router.delete` in `api/v1/tasks.py` removes
  a dependency (`:1399`).
- **D7 reaches both spawn paths by construction.** `effective_work_dir` is assigned in exactly three
  places (`:521`, `:531`, `:541`), all before the single `Run(` at `:729`; the Claude/Codex split
  happens later and *inside* `_execute_run`, at `:1310`. One write, no way for the two runners to
  disagree. The blocks at `:1524`/`:2083` are run *finalisation* — where `snapshot_commit_sha` is
  written, which is why D4 cites them — and D7 does not depend on them.
- **D4's stamp is enforceable**, and R3 sharpened the test rather than the decision. Task 4.11 said
  "grep the tree" without saying for what; a grep for `.workspace_scheme =` alone passes against
  `Task(workspace_scheme=…)` and `.values(workspace_scheme=…)`. All three forms named now, plus the
  default the design never stated (`'task'`).
- **The citation sample came back clean.** Four load-bearing ones re-read for what the line *means*:
  `worktrees.py:457-458` (snapshot returns `None` on a clean tree — D4's whole correction rests on
  it), `:537-538` (release snapshots onto the branch *before* removing — D1's "do not reuse
  `release_worktree`"), `:268-275` (the idempotent path validates the *registration*, not the tree's
  state), `run_task_binding.py:350-351` (`assignee` filled only when empty — D8's premise). All four
  say what the design says. Two rounds of mechanical sweeping appear to have worked.

### Verification

No code changed, so no suite was run; `green_at_arming` still stands for this tree.

- **35 (file, line, expected-text) assertions** over every citation R3 introduced. **Ten were wrong
  on the first run** — my own line numbers, all off by 1–9 — and were corrected against the tree:
  `TriggerAgentError.__init__`, the abandonment block, `integration_targets`' comment, the
  `integrate_task` call, `update(Task)`, and the scheduler's assignee/running block (`1274-1283`, not
  `1281-1291`). Re-run as **14 range assertions** (does the cited span actually contain the claimed
  text): **14/14**.
- A scan of every `file.py:line` citation in all six artifacts for a path that does not resolve or a
  line past EOF: **one hit**, `tests/test_task_integration.py:14`, which is pre-existing
  `hub/`-relative shorthand consistent with the rest of the document. Left.
- `npx openspec validate --all --strict` → 42 passed, 0 failed.
- `npx openspec show --json` read back: 9 deltas, 5 ADDED / 4 MODIFIED, and the D8 requirement now
  parses **four** scenarios including the new *refused input is not thrown away*.
- `npx openspec list` → 0/69 tasks.

**Contamination note, per the method:** the D8 caller finding, the grandfathering over-breadth in the
delta and both D1 corrections came from reading the code against artifacts a *previous iteration*
wrote, which is the shape the discipline is for. The ten bad line numbers are mine, caught in the
same round by the same script — weaker evidence, and the reason the sweep is run rather than trusted.

**R3 is clean.** Two rounds have now run against this change; the remaining uncertainty is in phases
5–8 of `tasks.md`, which R3 read for consistency with its own corrections and no further. That is
recorded in `design.md` under "What R3 caught" rather than left in my head. **Implementation starts
next.**

**Next:** `F58-IMPL` phase 1 — make the suite able to tell the implementations apart.

## Iteration 5 — F58-IMPL phase 1: the test that was supposed to fail passed, and why

**11:07–11:2x, 2026-08-27.** Branch `autonomous/2026-08-27-the-rest-of-the-work` at `db57cf5`,
matching STATE.json. Phase 1 of `openspec/changes/2026-08-27-work-is-isolated-per-task/tasks.md`,
tasks 1.1–1.3, and nothing else. Test-only by design: no production code was touched.

### The finding: the fixture phase 1 specified does not discriminate

Task 1.3 says 1.1 must **fail** against unmodified production code, and that a 1.1 which passes
means the fixture does not build the case. Written exactly as 1.1 specified — `earlier` on
`agentweave/task/<other-task-id>`, `demonstrated` on this task's own branch **cut from `main`**,
both names spelled out in the test — **it passes.** Measured, not reasoned:

```
py -3.11 -m pytest hub/tests/test_task_integration.py -q -k another_tasks_commits
1 passed, 25 deselected, 5 warnings in 1.57s
```

The reason is structural rather than a fixture slip. Two branches cut from `main` by hand are
separable *whatever the product does*, because nothing in `task_integration.py` looks at how the
branch was made: `integration_targets` reads the footprint's recorded `commit_sha`, and
`commits_riding_along` is `git rev-list main..<sha>`. If the test decides that `earlier` is not in
`demonstrated`'s ancestry, then it is not, today and after the change alike. That is precisely what
the phase preamble complains about — "the shape of the branch is decided by the *test*, not by the
product" — and R1 wrote a fixture that changes *which* shape the test decides without removing the
test's authority to decide it. Inverting the assertion alone is red for the wrong reason; hardcoding
the new branch names is **green for the wrong reason**, which is worse, because a vacuous green is
silent.

### What 1.1 is instead, and why that is red for the right reason

Per 1.3's own instruction — fix the fixture, do not weaken the assertion — both branch names now
come from the product:

```python
earlier = commit_on_branch(tmp_path, worktrees.task_branch_name(other), "unrelated.py", "wip\n")
git(tmp_path, "checkout", "-q", "main")
demonstrated = commit_on_branch(tmp_path, worktrees.task_branch_name(task), "done.py", "ok\n")
```

Observed failure text, verbatim, against unmodified production code:

```
>       earlier = commit_on_branch(tmp_path, worktrees.task_branch_name(other), "unrelated.py", "wip\n")
                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: module 'hub.worktrees' has no attribute 'task_branch_name'

hub\tests\test_task_integration.py:362: AttributeError
```

This is red because **the product cannot say where a task's work goes** — which is the defect F58
names, at the level phase 1 can reach. It goes green at task 2.3, which implements
`task_branch_name`. It does not, and this phase does not claim it does, discriminate *provisioning*:
that a turn bound to a task is actually given that branch is phases 3 and 7's, and no test in this
file can reach it because this file never triggers an agent. Recorded in `tasks.md` above phase 1
rather than left in this log, so an implementer reading only the change sees it.

### 1.2, and the one assertion the task did not name

`test_later_commits_on_the_branch_are_not_merged` gains the earlier-commit case its docstring
already described: `groundwork.py` committed on this task's own branch *before* the evidence commit,
asserted to land. That is the case option (b) — squashing the evidence commit's diff — would break,
and nothing covered it. It passes today, as 1.3 predicted.

One assertion had to move that 1.2 did not name. The test asserted `rode_along_commits == []` under
the comment "a branch with exactly one commit ahead of main has nothing to ride along", which stops
being true the moment a groundwork commit exists: `rev-list main..demonstrated` now yields it. It is
`== [earlier]` now — the groundwork lands **and** the record still says which commit was the
reviewed one. A strengthening (it pins that the two facts stay separate), and flagged in `tasks.md`
rather than made quietly.

The old name `test_rode_along_commits_names_what_actually_landed` survives in the new docstring, in
the exploration, and in `FINDINGS.md:2672`; the docstring says it is the inversion of that test, so
the history reads without a rename hunt.

### Verification

- `py -3.11 -m pytest hub/tests/test_task_integration.py -q` → **25 passed, 1 failed** in 29.77s.
  The one failure is `test_another_tasks_commits_do_not_ride_along`, intended, with the text above.
  No other test in the file moved — 25 is the whole rest of it.
- The hardcoded-name variant was run as a controlled comparison and reverted from a backup, not
  edited back by hand; `grep -c worktrees.task_branch_name` = 2 confirms the restore.
- `py -3.11 -m ruff check src/ hub/ tests/` → All checks passed.
  `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` → 495 files unchanged.
  (`ruff` is not on PATH in Git Bash here; `py -3.11 -m ruff` is.)
- `npx openspec validate 2026-08-27-work-is-isolated-per-task --strict` → valid.
  `npx openspec list` → 3/69 tasks.
- No Hub was started or touched; no job exists to disable. `green_at_arming` otherwise stands.

### Two reconciliations

- **Queue statuses were stale.** STATE.json still had `F58-R2` as `current` and `F58-R3` as
  `open`, though both ran (iterations 3 and 4, commits `c29616d` and `90a6e76`). Both are `done`
  now, with the discrepancy recorded in their `outcome` rather than silently overwritten. The
  `next_action` text, not the queue, is what has been steering this run.
- **An interactive session committed on this branch mid-iteration.** `e90be76`
  (`docs(handoff): 0093`) landed at 11:10:31, between the iteration-5 claim and this commit. It is
  documentation only and touched nothing this iteration did; staging explicit paths is what kept the
  two apart.

**Next:** `F58-IMPL` phase 2 — task workspace paths, names and provisioning (tasks 2.1–2.9). 2.3 is
what turns this iteration's red green, and phase 2 should confirm that transition explicitly rather
than only running its own new tests.

## Iteration 6 — F58-IMPL phase 2: the guard that no test could fail, and the flag that mattered instead

*Appended by iteration 7. Iteration 6 wrote this draft to disk, committed and pushed
`fed29cf`, and died before appending it. The full-suite line below is iteration 7's
measurement; everything else is iteration 6's own account, and iteration 7 re-ran its
headline numbers independently — see the next entry.*

**11:15–11:5x, 2026-08-27.** Branch `autonomous/2026-08-27-the-rest-of-the-work` at `9c64f9c`,
matching STATE.json. Phase 2 of `openspec/changes/2026-08-27-work-is-isolated-per-task/tasks.md`,
tasks 2.1–2.9, and nothing else. No review round was opened: R2 and R3 both ran, and the discipline
is done for this change.

### What was built

`hub/hub/worktrees.py` gains the per-task half of the module it already had for agents:

- `validate_task_id`, `task_root`, `task_worktree_path`, `task_branch_name` (2.3) — pure, and
  refusing anything that is not `task-` followed by **lowercase** hex. Lowercase is not
  pedantry: two ids differing only in case are two git refs but one directory on Windows and
  macOS, so accepting both would let one task's checkout be handed to another. The test names
  that reason.
- `ensure_task_worktree(repo_root, task_id, base, prerequisites=())` (2.7), with the unwind
  written out in D1's order — `merge --abort`, `worktree remove --force`, `branch -D`,
  `worktree prune`, each `check=False`, and only then raise. `release_worktree` is **not** reused,
  and the docstring says why: it snapshots the dirty tree onto the branch first, which here would
  commit a conflicted merge as though it were the agent's work.
- The mid-merge refusal (2.7b), on the idempotent path, for the one state a process killed between
  `worktree add` and the unwind can leave.
- `release_task_worktree` (2.9), returning the same `ReleaseResult` as `release_worktree` rather
  than a second dataclass. `snapshot_worktree` gained a keyword-only `message=` for it — a task's
  branch does not belong to an agent's turn, and "Auto-snapshot: task-ab12cd34ef56's turn" would
  have been a small lie in the git history.
- `.agentweave/tasks/` in `repo_hygiene.EXCLUDE_PATTERNS` (2.8).

`hub/tests/test_task_worktrees.py` is new: 21 tests, red first, all 21 failing with
`AttributeError` before any of the above existed.

### The finding: 2.5's guard was a branch no test could fail

Task 2.5 asks that a prerequisite already reachable from `base` "is not merged a second time", and
the obvious implementation is a `merge-base --is-ancestor` check before the merge. It was written,
and then mutation-tested:

```
# guard stubbed to `if False and already_here.returncode == 0:`
py -3.11 -m pytest hub/tests/test_task_worktrees.py -q
21 passed
```

The mutation survived, so the guard was doing nothing the suite could see. Measured directly, on a
throwaway repository rather than reasoned about:

```
$ git merge --no-ff -m "bring in" $ANC
Already up to date.
exit=0
count before: 2
count after: 2
```

`git merge --no-ff <ancestor>` is a no-op. The guarantee 2.5 names is git's, not ours, and the
guard was a line whose deletion nothing would notice — which is the failure mode this repository
names as a defect source. **It was deleted.** The comment in its place records the measurement, so
a later reader does not "restore the missing check", and the test's own docstring says out loud
that it does not discriminate any control flow of ours.

### What the same mutation pass found instead

`--no-ff` *is* load-bearing, and nothing was testing it. The task branch sits at `base`, and a
prerequisite is typically `base` plus one commit — so a plain `merge` **fast-forwards**: the task
branch tip becomes the prerequisite's own commit, two tasks share a branch tip, and the act of
bringing the work in leaves no record at all. That is F58's shape reappearing inside the fix for
F58. The test now pins the commit count at three (base, prerequisite, merge) and asserts
`HEAD != prerequisite`:

```
# `--no-ff` removed from the merge
FAILED test_a_prerequisite_not_reachable_from_the_base_is_merged_in
1 failed, 20 passed
```

So phase 2 removed one untestable line and added one real assertion, on the same pass. The net is
one fewer branch in the module and one more thing that cannot silently regress.

### Verification

- `py -3.11 -m pytest hub/tests/test_task_worktrees.py -q` → **21 passed**. All 21 were run red
  first, against the tree as phase 1 left it: `21 failed, 5 warnings in 2.05s`, every one of them
  on a name that did not exist yet. (The per-test tracebacks were not kept; the summary line and
  the count are what is claimed here.)
- **The phase-1 red is green, and 2.3 is what turned it.** `hub/tests/test_task_integration.py`
  went from **25 passed / 1 failed** (iteration 5, `AttributeError: module 'hub.worktrees' has no
  attribute 'task_branch_name'`) to **26 passed**. That is the whole point of phase 1 paying off,
  and it is recorded here as both a before and an after because phase 2's own instruction asked
  for exactly that.
- Three mutations, three named failures:
  - `.agentweave/tasks/` removed from `EXCLUDE_PATTERNS` → `test_seeding_writes_the_block` and
    `test_git_agrees_about_the_hubs_own_files` fail.
  - `branch -D` removed from the unwind → `test_a_conflicting_prerequisite_leaves_no_checkout_and_no_branch`
    **and** `test_a_prerequisite_commit_missing_from_the_repository_says_so` fail. Both, because
    `worktree add -b` has already made the branch by the time either failure is detected.
  - `--no-ff` removed → the case above.
  - The fourth mutation is the finding above: it *survived*, and the code changed rather than the
    test.
- `py -3.11 -m pytest hub/tests/test_task_worktrees.py hub/tests/test_worktrees.py hub/tests/test_repo_hygiene.py -q`
  → 74 passed. `test_task_integration.py test_review_checkout.py test_session_sync.py` → 55 passed.
- Full hub suite: **not run by this iteration** — the process died before it. Filled in by
  iteration 7 against the same tree: `py -3.11 -m pytest hub/tests/ -q` → **3263 passed,
  84 skipped, 1 xpassed, 0 failed** in 18m25s. That is `green_at_arming`'s 3242 plus exactly
  the 21 tests added here, with the skip count unmoved.
- `py -3.11 -m ruff check src/ hub/ tests/` → All checks passed.
  `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` → 496 files unchanged.
- `npx openspec validate 2026-08-27-work-is-isolated-per-task --strict` → valid.
  `npx openspec list` → **14/69 tasks**, up from 3/69.
- No Hub was started or touched; no job exists to disable.

### Two things deliberately left for later phases

- `list_agent_branches` still cannot see a task branch — `task/<id>` fails `_AGENT_NAME_RE` after
  the prefix strip, and the checkout path fails the second filter too. That is D6's recorded
  degradation and phase 6's task, not a regression introduced here: nothing rendered these lists
  before and nothing does now.
- Nothing calls `ensure_task_worktree` or `release_task_worktree` yet. Phase 2 is the mechanism;
  phases 3 and 4 are what choose it, and phase 5 is what releases it. **A task is not complete on
  the strength of a mechanism existing either** — the wiring is phases 3–5's to prove.

**Next:** `F58-IMPL` phase 3 — resolving the task before the workspace (tasks 3.1–3.4, D2). It is a
prerequisite of phase 4's task 4.14, so the order is not free.

## Iteration 7 — the interrupted close-out, reconciled: phase 2 re-verified from the outside

**12:30–12:51, 2026-08-27.** Branch `autonomous/2026-08-27-the-rest-of-the-work` at `60a471c`,
matching STATE.json. No new implementation. Iteration 6 committed and pushed phase 2 (`fed29cf`)
and then died before appending its log entry or rewriting STATE.json, leaving its draft at
`.claude/autonomous/iter6-entry.md` and one line — the full hub suite — as a placeholder. This
iteration's whole job was to close that out **without trusting the draft**: re-run the evidence
independently, fill in the missing line, and hand phase 3 to the next firing.

### What was re-measured, not read

Every number below was produced by this iteration against the tree at `60a471c`, not copied from
the draft.

- `py -3.11 -m pytest hub/tests/test_task_worktrees.py hub/tests/test_worktrees.py hub/tests/test_repo_hygiene.py hub/tests/test_task_integration.py -q`
  → **100 passed** in 84.73s. That is the draft's 74 and its 26 in one run, and it includes the
  phase-1 red: `test_task_integration.py` is green, so 2.3 did turn it.
- `hub/tests/test_task_worktrees.py` collects **21 tests**, the count the draft claims — and
  `grep -c "mock\|Mock\|monkeypatch"` over it is **0**. Every one of them builds a real repository
  and runs real `git`, so what they pin is git's behaviour and not a stub's imitation of it. That
  matters more than usual here, because the finding below is a claim *about git*.
- `py -3.11 -m pytest hub/tests/ -q` → **3263 passed, 84 skipped, 1 xpassed, 0 failed** in
  18m25s. `green_at_arming` recorded 3242 passed / 84 skipped, so the delta is exactly the
  21 tests phase 2 added and nothing else — no test moved from passing to skipped to hide a
  regression. The single `xpassed` is
  `test_agent_trigger_overrides.py::test_a_conversation_whose_model_changed_attributes_usage_per_turn`,
  whose `xfail` is `strict=False` and documents a *fixture* defect
  (`:memory:` resolves to a StaticPool shared across sessions); it passes or xfails by
  timing, and either outcome is green. Recorded here so a later run that sees 3262/1 xfailed
  does not go looking for a regression.
- `py -3.11 -m ruff check src/ hub/ tests/` → All checks passed.
  `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` → 496 files unchanged.
- `npx openspec validate 2026-08-27-work-is-isolated-per-task --strict` → valid.
  `npx openspec list` → **14/69 tasks**. Phase 2's boxes (2.1–2.9, including 2.6b and 2.7b) are all
  ticked in `tasks.md`; phase 3 onward is untouched.
- No Hub was started or touched; no job exists to disable.

### The draft's central finding reproduces independently

Phase 2 deleted a `merge-base --is-ancestor` guard on the grounds that `git merge --no-ff <ancestor>`
is a measured no-op — a claim load-bearing enough that a deleted guard rests on it. Re-measured this
iteration in a throwaway repository built from scratch, not the one the draft used:

```
count before: 2
Already up to date.
exit=0
count after: 2
```

Same result. The guarantee task 2.5 names is git's, and the comment that replaced the guard is
accurate.

### Read, not just run

`fed29cf` is 602 insertions across five files, and the diff was read rather than accepted on the
strength of its tests. Two things worth recording because a later phase depends on them:

- `ensure_task_worktree` merges prerequisites **only on the creation path**. The idempotent path
  and the resumed-branch path (`branch_exists`) both skip the merge, and the docstring says why:
  the all-or-nothing unwind is safe only because the branch is seconds old. Phase 5's release keeps
  the branch, so the resumed path is the one phase 5 makes reachable — the two designs agree.
- `_unwind_task_worktree` is deliberately not `release_task_worktree`, because releasing snapshots
  the dirty tree first and would commit a conflicted merge as the agent's work. Anything in phases
  3–5 that wants to "just reuse release" has to read that docstring first.

### What phase 2 leaves for later, unchanged from the draft

Nothing calls `ensure_task_worktree` or `release_task_worktree` yet — phases 3 and 4 choose it,
phase 5 releases it. `list_agent_branches` still cannot see a task branch; that is D6's recorded
degradation and phase 6's task, not a regression.

### The reconciliation itself, as a finding

The iteration-6 process was interrupted **after** its code commit and **before** its state write,
which is the one ordering that leaves a branch whose git history is ahead of its STATE.json. It
cost this iteration a full cycle to close, and the only reason it cost just one is that iteration 6
had written its entry to a file on disk before committing. Draft the entry to disk **before** the
commit, not after: the draft is what made the difference between reconciliation and re-doing phase 2
blind.

**Next:** `F58-IMPL` phase 3 — resolving the task before the workspace (tasks 3.1–3.4, D2). It is a
prerequisite of phase 4's task 4.14, so the order is not free.

## Iteration 8 — F58-IMPL phase 3: the task is resolved before any workspace exists

**12:52–13:30, 2026-08-27.** Branch `autonomous/2026-08-27-the-rest-of-the-work` at `b4e2d04`,
matching STATE.json (`git log` verified before any work: `b4e2d04` release, `3a8f70d` log,
`60a471c` claim, `fed29cf` phase 2 — exactly what iteration 7 recorded). Phase 3 only. Phase 4 not
started. No review round was owed: R2 and R3 both ran for this change.

### What moved, and what that costs

One call. `resolve_bound_task` left `agent_trigger.py:558` — a hundred lines *below* the workspace
decision — and now sits at `:489`, immediately after `repo_root = workspace_root.root` and above
everything that provisions anything. `spec_document_for_task`, `_render_hub_agent_context` and the
staging block all still read the same `binding` value; only the resolution moved.

The diff is small and the blast radius is not. **Four refusals change relative order**, and phase 3
existed to choose which one wins in each case rather than discover it afterwards. The new file
`hub/tests/test_task_resolved_before_workspace.py` (6 tests) pins all four plus a positive control.

### The pre-move red, measured before the move and not after

The five precedence tests were written first and run against the tree as phase 2 left it:

```
4 failed, 2 passed
FAILED test_a_task_that_does_not_exist_is_refused_and_provisions_no_worktree
FAILED test_a_missing_task_outranks_work_dir_on_a_review_turn
FAILED test_a_missing_task_outranks_work_dir_for_a_writing_agent
FAILED test_a_missing_task_outranks_an_unresolvable_review_target
```

That split is the whole design, visible as a measurement rather than an argument:

- The **four reds are exactly the four answers D2 said would move.** Three of them failed by
  raising the *other* refusal (`TriggerAgentError: work_dir cannot be combined with a review turn`,
  `... cannot override workspace isolation for a writing agent`, and
  `TriggerAgentError: task task-review has no recorded evidence, so there is no commit to review`).
- The **two greens are the two things that must not move**: `test_an_unavailable_workspace_still_
  wins_over_the_task_refusal` (D2's preserved precedence — it passed before *and* after, which is
  the only way to state "unchanged") and the positive control below.

The fourth red is the interesting one, because the refusal was already correct and the *side effect*
was not:

```
>       assert not worktrees.worktree_path(repo, "writer").exists()
E       AssertionError: assert not True
E        +  where True = exists()
E        +    where exists = WindowsPath('.../repo/.agentweave/worktrees/writer').exists
```

`TaskBindingError` was raised in both worlds. Before the move, the writing agent's worktree and
branch were already on disk by the time it fired — a mistyped task id left a checkout behind for an
agent that never ran. That assertion is the one that fails if the call ever slides back down the
function, and it is why the test restores the **real** `resolve_agent_workspace`: the suite stubs it
to a no-op by default (`conftest.py::_no_real_worktree_provision`), which would have made this test
pass for the wrong reason and proved nothing.

After the move: **6 passed.**

### Reachability — recorded because it bounds what these tests are evidence of

Traced while writing 3.1, and it is not what the design implies. The explicit `task_id` argument is
the only route by which `resolve_task_for_project`'s refusal reaches this code path at all:

- `POST /agent/trigger` validates `body.task_id` **itself**, at `agent_trigger.py:941-945`, before
  it ever calls into the turn. An operator typing a bad task id is refused there, above all of this,
  and always was.
- The drain path (`turn_scheduler.py:125`) does **not** pass `task_id` — it passes
  `queue_entry_ids`, and the delegated branch of `resolve_bound_task` deliberately *swallows*
  `TaskBindingError` (`run_task_binding.py:270-276`: "refusing to start would let removing a row
  cancel work the agent was legitimately asked to do").
- `grep` finds no other caller of `trigger_agent_directly` in `hub/hub/` at all.

So the observable consequence of the move — "a nonexistent task leaves no worktree behind" — is
today reachable only through a direct call to `trigger_agent_directly(task_id=...)`, which is what
the tests do (the same thing the sibling precedence test at `test_agent_trigger.py:2081` does). This
is **not** a reason the move is wrong: the reordering is what makes the binding available to phase 4,
which is the point, and the four precedence changes are real for any caller that does pass one. It
*is* a reason not to describe phase 3 as fixing a live operator-facing leak. It is a preparatory
reorder with four defensible side effects, and phase 4 is what makes it load-bearing.

### Task 3.4 — what was read, not assumed

3.4 is not satisfiable by assertion, so here is the reading. Every line between the new call site
(`:489`) and the old one (`:576`) was read, and the check was done **by name** on the three inputs
`resolve_bound_task` consumes.

*Every assignment target in the traversed region*, extracted mechanically rather than by eye:
`yolo`, `resume_session_id`, `session_mode`, `env`, `project_is_repo`, `review_task_id`,
`review_context`, `workspace`, `effective_work_dir`, `isolated_workspace`, `task_document`.

**None of `conversation`, `queue_entry_ids` or `task_id` is among them.** Every occurrence of those
three names in the region is a keyword argument passed by value (`conversation=conversation`,
`queue_entry_ids=queue_entry_ids`, `task_id=task_id`), plus one `task_id=review_task_id` at
`:529` — which is `prepare_review_turn`'s *parameter* name, not this function's local. No attribute
assignment (`conversation.<x> = ...`) and no in-place list mutation of `queue_entry_ids` occurs
either; both were grepped for explicitly, not skimmed.

Three further things the reading turned up that the task did not ask for and that matter anyway:

1. **The region performs no database write of any kind.** `grep -E "session\.(add|commit|flush|
   delete|merge)"` over lines 496-575 returns nothing. Of the four callees, three take no session
   at all — `resolve_agent_env(runner, config)` (`launchability.py:137`),
   `seed_repo_excludes(root)` (`repo_hygiene.py:83`), `is_git_repo(path)` /
   `ensure_review_checkout(repo_root, agent, sha)` (`worktrees.py:109,547`) — and the fourth,
   `prepare_review_turn`, reads only: its one DB call besides `session.get(Task, ...)` is
   `requirement_evidence.commit_for_task_review` (`:653-712`), and an AST pass over that module
   confirms all four of its `session.add` sites live in `record`, `_apply_footprint`, `decide` and
   `detect_drift` — none of them inside `commit_for_task_review`.
2. **Two reads of the queue entries swapped order, and the swap is inert.** `resolve_bound_task`'s
   `binding_for_delivery` now runs *before* `_review_task_from_entries` instead of after. Both
   `SELECT` from the same `InboundQueueEntry` rows and neither writes, so nothing either observes
   can have been changed by the other.
3. `_review_task_from_entries` has locals named `review_task_id` and `task_id` in its
   comprehensions. Different scope, no bearing — recorded only so the next reader doing this grep
   does not stop on them the way this one did.

### One stale claim the move created, found by the reading and fixed

`binding_from_entries`'s docstring (`run_task_binding.py:155-173`) justified its arrival-order
tie-break by asserting that a mixed batch — one entry naming work, another naming a review — can no
longer reach it, "so every entry `binding_from_entries` now sees is already the same kind". After
the move that sentence is **false**: `_review_task_from_entries` is the thing that refuses a mixed
batch with a 409, and it now runs *after* `resolve_bound_task`. A hand-built mixed batch is seen by
`binding_from_entries` for the few statements between the two.

No behaviour changed — the 409 still fires, before any run exists, and
`test_agent_trigger.py:2081` still gets both task ids in its detail (it is in the full-suite run
below). Nothing is bound from what `binding_from_entries` returns in that window. But the sentence
was load-bearing *as a reason*: a later reader taking it at face value could replace the tie-break
with an assertion that the entries are one kind, and that assertion would now fire. The docstring
now says which of the two runs first and that the tie-break must stay total. This is the
restated-fact failure mode this codebase keeps naming, arriving on schedule inside a change whose
whole content is a reordering.

### Verification

- `py -3.11 -m pytest hub/tests/test_task_resolved_before_workspace.py -q` → **6 passed**, from
  **4 failed / 2 passed** on the pre-move tree. Both runs are quoted above.
- The neighbourhood the reorder actually touches, run as its own set before the full suite:
  `test_agent_trigger.py test_run_task_binding.py test_review_turn.py test_conversation_task_binding.py`
  `test_task_integration.py test_task_worktrees.py` → **157 passed** in 103s.
- Full hub suite: `py -3.11 -m pytest hub/tests/ -q` → **3269 passed, 84 skipped,
  1 xpassed, 0 failed** in 17m56s. Iteration 7 measured **3263 / 84 / 1 xpassed** on the
  phase-2 tree, so the delta is exactly the six tests added here and nothing else — no test
  moved from passing to skipped, and the skip count did not move at all. The lone `xpassed`
  is the known `strict=False` fixture defect iteration 7 wrote up
  (`test_agent_trigger_overrides.py::test_a_conversation_whose_model_changed_attributes_usage_per_turn`);
  it passes or xfails by timing and either outcome is green.
- `py -3.11 -m ruff check src/ hub/ tests/` → All checks passed.
  `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` → 497 files unchanged
  (496 plus the new test file).
- `npx openspec validate 2026-08-27-work-is-isolated-per-task --strict` → valid.
  `npx openspec list` → **19/69 tasks**, up from 14/69: 3.1, 3.2, 3.2b, 3.3, 3.4.
- No Hub was started or touched; no job exists to disable.

### What phase 3 does not do

Nothing yet *uses* the earlier answer. `binding` is resolved above the workspace decision and the
workspace decision still ignores it — a turn bound to a task still gets the agent's own worktree.
That is phase 4's task 4.14, and phase 3 is its prerequisite, which is why the order was not free.
**A task is not complete on the strength of a prerequisite existing**, and this one is not claiming
otherwise: what phase 3 closes is the four precedence questions, measured red then green.

**Next:** `F58-IMPL` phase 4 — choosing the workspace from the binding (D1, D3, D4). It is the
largest phase in the change and the first one whose failure is visible to an agent at runtime.

## Iteration 9 — F58-IMPL phase 4A: the stamp, and the fourth spelling of a write

**13:20–13:51, 2026-08-27.** Branch `autonomous/2026-08-27-the-rest-of-the-work` at `7eef7a4`,
matching STATE.json (`git log` verified before any work: `7eef7a4` release, `7826661` phase 3,
`44b3917` claim, `b4e2d04` release — exactly what iteration 8 recorded). Tree clean. Phase 4A only:
tasks **4.5** and **4.11** of `openspec/changes/2026-08-27-work-is-isolated-per-task/tasks.md`,
design D4. **4B was not started** — the resolver (4.9, 4.10, 4.14) is untouched and the column is
written by the migration and read by nobody, which is exactly the state phase 4A is supposed to
leave. No review round was owed: R2 and R3 both ran for this change, and R3 is what corrected both
of these tasks.

### What shipped

Three files, one of them new twice over:

- `hub/hub/db/models.py` — `Task.workspace_scheme`, `String(16)`, `default="task"`,
  `server_default="task"`, `nullable=False`. No CHECK constraint, matching `status`, `priority` and
  `divergence_policy` on the same table: a table-level CHECK naming a column makes that column
  undroppable in SQLite, and this migration has a working downgrade *because* of that omission.
- `hub/hub/migrations/versions/0095_task_workspace_scheme.py` — adds the column and stamps
  `'agent'` on every task that had at least one `Run` at that moment.
- `hub/tests/test_task_workspace_scheme.py` — 10 tests, new file.
- Head assertions bumped in **both** `hub/tests/test_migrations.py` (`HEAD_REVISION`) and
  `hub/tests/test_project_persistence.py:227`. The CLAUDE.md checklist names both and the second is
  the one that goes red late; it needed two `sed` attempts because the line number had drifted, and
  the fix was to grep for the assertion rather than trust the offset.

### The discriminator, and the one test that is the whole argument

The rule is *the existence of a `Run`* — not its status, not its outcome, not what it committed.
R1 proposed "a prior run with a non-null `snapshot_commit_sha`" and R2 rejected it because
`snapshot_worktree` returns `None` for a clean tree (`hub/hub/worktrees.py:457-458`), so an agent
that **commits its own work** ends its turn clean and records `NULL`. Under R1's rule that task —
the one with the most real work on the per-agent branch — would *not* be grandfathered, and its next
turn would start in a fresh task checkout cut from the integration base with its own history gone.

Task 4.5 said to assert that case **by name**, and the measurement below is why that wording
mattered rather than being belt-and-braces. Reinstating R1's discriminator in the migration
(`AND snapshot_commit_sha IS NOT NULL`):

```
FAILED test_a_task_whose_runs_committed_nothing_is_grandfathered_too
FAILED test_the_migration_is_idempotent_over_an_already_migrated_column
2 failed, 8 passed
```

**`test_the_migration_stamps_the_agent_scheme_on_exactly_the_tasks_that_had_a_run` does not fail.**
Its four-task table has both grandfathered tasks carrying at least one run with a non-null snapshot,
so R1's wrong rule produces the same answer there. The broad "exactly these tasks" test — the one
that reads like the assertion that covers everything — is blind to the exact error the review round
found. Only the by-name test catches it. That is the shape of finding this repository keeps
producing, arriving inside the test written to prevent it.

### The four mutations against the migration, each caught by a named test

| Mutation | Failed |
|---|---|
| R1's discriminator (`AND snapshot_commit_sha IS NOT NULL`) | `test_a_task_whose_runs_committed_nothing_is_grandfathered_too` (+1) |
| Drop the missing-`tasks` guard | `test_the_migration_is_a_no_op_when_tasks_is_missing` |
| Drop the separate `runs` guard (`if True:`) | `test_the_column_is_added_but_nothing_is_stamped_when_runs_is_missing` |
| Drop `server_default="task"`, make it nullable | 4 tests, incl. `test_an_existing_row_is_never_left_null` |

`runs` is guarded **separately** from `tasks` rather than in one `{tasks, runs} <= present` check,
because a synthetic chain can reach `0095` with one and not the other: a database with tasks and no
runs table has no runs to grandfather, which is the correct answer and not an error. The third row
is that decision made falsifiable.

### The finding: R3's three-form source scan would have been vacuous

Task 4.11 requires a source scan proving nothing outside the migration writes the column, because
"the grandfathered set can only shrink" is true if and only if that one write is the only write.
R1 scanned for one form; **R3 corrected it to three** — `.workspace_scheme =`, `workspace_scheme=`
and `values(workspace_scheme` — on the grounds that a scan for one form passes against a real write
in either of the others.

Implementing it showed the same hole one level down. All three are **Python** write forms, and the
migration's own write is raw SQL: `UPDATE tasks SET workspace_scheme = 'agent'`. That matches none
of them. So R3's scan would have:

1. exempted `0095` from a scan `0095` never triggered — an allow-list entry that proves nothing, and
   a test that is green over a source tree it never really examined; and
2. **missed a runtime raw-SQL write anywhere else in the Hub**, which is a real way to write this
   column — `session.execute(text(...))` is used across `hub/hub/`.

Measured rather than argued. With a probe write appended to `hub/hub/task_integration.py`:

```
_PROBE_SQL = "UPDATE tasks SET workspace_scheme = 1"

R3 three forms      -> NO OFFENDERS (test would pass)
with the SQL form   -> ['hub\hub\task_integration.py']
```

So the scan ships with **four** forms, the fourth being `set workspace_scheme` (the source is
lowercased first). Two consequences, both deliberate:

- The migration's `UPDATE` is spelled **literally** rather than interpolated from its own `_TABLE`
  and `_COLUMN` constants, so the one exempted file actually matches the scan. A write hidden behind
  an f-string is a write the scan cannot see, and the exemption would go vacuous again.
- The test carries a second assertion, `matched_allowed`, that fails if the migration matches none
  of the four forms. Mutating the migration's SQL back to the f-string form fails that assertion by
  name — the test refuses to be vacuous rather than trusting the next author to notice.

Four source-scan mutations, all caught: an attribute write in `hub/hub/run_task_binding.py`, a
keyword write in `src/agentweave/task.py`, the raw-SQL write above, and the vacuous-exemption case.

What the scan still cannot see, recorded in its docstring rather than chased:
`setattr(task, "workspace_scheme", ...)` and any write assembled from a variable. Both are visible
in review in a way an ordinary assignment is not, and a scan that tried to catch them would match
its own docstring.

### The real-data dry run — seven tasks R1's rule would have restarted from nowhere

Synthetic rows prove the migration does what it says. They cannot say whether the correction R2 made
matters in practice, so the migration was run against a **copy** of the trial Hub's own database
(`~/.agentweave/hub/profiles/beta/agentweave.db`, 14 MB, real accumulated state). The copy only —
the live file is untouched and still at `0094`, and no Hub was started.

```
version before: 0094          version after: 0095
tasks total:                47      agent 22 / task 25
tasks with >=1 run:         22      nulls: 0
R1 rule would have stamped: 15      rows disagreeing with the rule: 0
```

**Seven of the operator's own tasks separate the two rules.** Each has at least one run and no run
with a non-null `snapshot_commit_sha` — which is precisely the shape R2 predicted from
`snapshot_worktree`'s clean-tree return: an agent that committed its own work. Under R1's
discriminator those seven would have been left on the task scheme and their next turn started in a
fresh checkout cut from the integration base, with their own commits absent. The review round did
not catch a hypothetical; it caught 7/22 of the grandfathered set on the one real database this
project has.

The `rows disagreeing with the rule` line is the whole stamp recomputed independently in SQL and
compared against what the migration wrote — 0, over 47 real rows.

**Carry this into 4B:** the trial Hub's live database is at `0094` and this branch's head is `0095`.
Restarting that Hub from this checkout will run the migration against those 47 rows for real.

### Verification

- `py -3.11 -m pytest hub/tests/test_task_workspace_scheme.py -q` → **10 passed**.
- Mutation table above: **8 mutations, 8 caught by a named test**, each run and restored.
- Full hub suite: `py -3.11 -m pytest hub/tests/ -q` → **3280 passed, 84 skipped, 1 xpassed,
  0 failed** in 17m41s. Iteration 8 measured **3269 / 84 / 1 xpassed**, so the delta is **+11 and
  I added 10 tests.** That extra one was chased down rather than waved through, because an
  unexplained +1 is indistinguishable from a test that started being collected for a bad reason:

  ```
  collected here, without the new file : 3355
  collected in a clean worktree at 7eef7a4 : 3354
  diff of the two node-id lists:
  > test_no_console_flash.py::test_every_spawn_reaches_console_suppression[0095_task_workspace_scheme.py]
  ```

  `test_every_spawn_reaches_console_suppression` is parametrized over every Hub source file
  (`ids=lambda p: p.name`), so **adding a source file adds a case** — the migration is now itself
  asserted to contain no unsuppressed subprocess spawn. +10 new tests, +1 parametrised case, and
  nothing else moved: skips unchanged at 84, the lone `xpassed` still the known `strict=False`
  fixture defect from iteration 7. The measurement was taken in a throwaway `git worktree` at
  `7eef7a4`, which was removed afterwards (`git worktree list` back to the repo plus the six
  pre-existing agent worktrees).
- `py -3.11 -m pytest tests/ -q` (CLI suite) → **440 passed, 3 skipped**.
- `py -3.11 -m ruff check src/ hub/ tests/` → All checks passed.
  `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` → 499 files unchanged
  (498 plus the new test file; black reformatted it once before this was clean).
  `py -3.11 -m mypy src/` → Success, 22 source files.
- `npx openspec validate 2026-08-27-work-is-isolated-per-task --strict` → valid.
  `npx openspec list` → **21/69 tasks**, up from 19/69: 4.5 and 4.11.
- No Hub was started or touched; no job exists to disable. The trial Hub is on an older revision of
  this branch and does not see `0095` — nothing pointed at that database was run.

### Which spec text 4A actually closes

`specs/operator-agent-creation/spec.md`, "Work already under way keeps the checkout it started in",
has five normative paragraphs. Two of them are entirely about *recording* and are closed here:

- *"The set of covered tasks SHALL be recorded once, when per-task isolation is introduced, and
  SHALL NOT be recomputed afterwards"* — the column plus the source scan. The scan is the only thing
  that can hold "shall not be recomputed"; the rest is a comment.
- *"The recorded set SHALL cover every task that has already been worked at all, whether or not a
  commit can be found for it"* — `test_a_task_whose_runs_committed_nothing_is_grandfathered_too`,
  and 7 real rows on the trial database.

The three remaining paragraphs and all four scenarios are about which checkout a *turn* gets, which
nothing yet decides. None of them is claimable on 4A, and none is marked.

### What phase 4A does not do

The column exists and **nothing reads it.** No turn resolves differently, no worktree path changed,
and a task stamped `agent` is indistinguishable from one stamped `task` at runtime today. That is
phase 4B (4.9, 4.10, 4.14) and it is the first thing an agent could see fail. A task is not complete
on the strength of a prerequisite existing, and 4A does not claim otherwise: what it closes is *who
is grandfathered*, fixed at migration time and falsifiable in eight places.

One thing worth carrying into 4B: `0095` is now the head, so the trial Hub's database
(`profiles/beta`) is one revision behind this branch. Any restart of that Hub from this checkout
will run `0095` against real rows — which is the migration's first real exercise, and the first
place the stamp becomes observable.

**Next:** `F58-IMPL` phase 4B — the resolver (4.1–4.4, 4.6–4.10), which is where the column starts
being read.

---

## Iteration 10 — 2026-08-27 13:55 → F58-IMPL phase 4B, the resolver

**Queue item:** `F58-IMPL`, phase 4B — tasks 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.8, 4.9 and 4.10 of
`openspec/changes/2026-08-27-work-is-isolated-per-task/tasks.md`, designs D1, D3 and D4. 4C
(4.12–4.16, the D8 refusal) deliberately untouched, as the queue instructed. No review round owed:
R2 and R3 both ran for this change.

**What 4B is.** Phase 4A added `Task.workspace_scheme` and nothing read it. This is the phase where
it is read, and where a turn first executes somewhere other than it used to. Three pieces:

- `worktrees.resolve_turn_workspace(repo_root, agent, config, *, task_id, base, prerequisites)` —
  the seam. A turn bound to a task runs in `.agentweave/tasks/<id>` on `agentweave/task/<id>`; a
  turn bound to nothing runs in `.agentweave/worktrees/<agent>` on `agentweave/<agent>`, unchanged.
- `hub/hub/task_workspace.py` — the session-aware half, turning "this turn is bound to task X" into
  the three plain values `worktrees` takes, because that module does not read the database.
- `agent_trigger.py` calls the seam in place of `resolve_agent_workspace`, at what phase 3 left as
  the position below the relocated `resolve_bound_task`.

### The design decisions this phase actually had to take

**`task_id=`, not `task=`.** The task text offered `task=None`; `worktrees` is independent of the
DB/session layer by construction and must not start accepting ORM objects, so the seam takes an id.

**It delegates rather than restates.** `resolve_turn_workspace` sends *all three* shared-checkout
answers back through `resolve_agent_workspace` — unbound, read-only, and not-a-repository — instead
of reimplementing any of them. That is the whole content of tasks 4.7 and 4.8: the precedences they
protect keep exactly one implementation each, and the two guards in the new function read as *which
scheme applies* rather than as a second copy of *what a shared checkout is*.

**`base=None` with a task id raises.** Substituting `HEAD` would cut the branch from wherever the
operator's checkout happens to be sitting, which is the option D1 rejected by name. A missing base
is a programming error and says so.

**A third route to the per-agent workspace, which nobody had named.** `validate_task_id` accepts
`task-` followed by hex — what `short_id` mints — and nothing in the schema enforces it. The
resolver had no answer for a row that arrived another way. Two answers were available: refuse every
turn on that task, or run it where it ran before. The second is chosen. The first is an outage on
data the Hub cannot repair; the second is precisely what grandfathering already means, and it is
logged because unlike an unbound or a stamped task it is not a shape the product expects to see.

This was **measured, not anticipated**: the Hub suite alone carries hundreds of task rows with ids
of that shape (`task-9-1-a`, `task-bind-approved`, `task-blk-3`, …), and one of them was sitting in
`test_task_resolved_before_workspace.py`'s closing test, where it would have kept that test green
while quietly exercising the fallback instead of the ordinary bound path.

`TurnWorkspace` collapses all three routes to `task_id=None` deliberately — the caller has no
decision left to make between them.

### The test 4B's own list did not contain

Every test tasks 4.1–4.8 name passes against a `_prerequisite_commits` that returns `()`
unconditionally. So does the whole of phase 2, which proves only that `ensure_task_worktree` merges
what it is *given*. That is the exact shape of F58 — a guarantee stated in a docstring with nothing
able to fail on it — so a test for 4.10's own half was written:
`test_a_prerequisites_accepted_commits_are_in_the_task_checkout` puts the prerequisite's commit on
a branch `main` cannot reach, wires up the real `TaskDependency` → `TaskRequirementLink` →
`RequirementEvidence(accepted)` → `EvidenceFootprint(git)` chain that `integration_targets` reads,
and asserts the file lands in the *dependent* task's checkout and not in the project checkout.

A second unnamed case was added for D1's "set **and resolves**" half of the base rule, which task
4.6 shortened to "set": a `main_branch` naming a ref the repository no longer has falls back to
`HEAD` rather than failing the `worktree add` and refusing the turn.

### Verification

`hub/tests/test_turn_workspace.py`, 11 tests, all observing the **spawned process's `cwd`** rather
than a return value — the only fact an agent can act on, and the one F58 is about.

**Eight mutations, eight caught by a named test.** Each applied to the source, run, and restored:

| mutation | test that went red |
|---|---|
| the binding ignored (always the agent workspace) | 6 tests, incl. `…runs_in_the_tasks_own_checkout` |
| grandfathering branch removed | `test_a_grandfathered_task_keeps_the_per_agent_checkout` |
| `is_writing_agent` guard removed | `test_a_read_only_agent_shares_the_project_checkout_…` |
| `is_git_repo` guard removed | `test_a_project_that_is_not_a_repository_runs_the_turn_in_place` |
| base always `HEAD` | `test_the_base_is_the_projects_main_branch_when_it_is_set` |
| base taken unverified | `test_a_main_branch_that_does_not_resolve_falls_back_to_head` |
| prerequisites dropped | `test_a_prerequisites_accepted_commits_are_in_the_task_checkout` |
| id validation removed | `test_a_task_id_the_product_could_not_have_minted_…` |

The first mutation initially left `test_the_base_is_head_when_no_main_branch_is_set` green — an
agent branch is cut from `HEAD` too, so the ref assertion alone did not discriminate the scheme.
The test now asserts the directory as well, and the docstring says why that assertion is not
redundant.

### The two failures I did not stage, and what they changed

**Both were the tests, not the behaviour, and both only appeared under load.** That is worth saying
first, because "it passes alone and fails in the suite" is the shape a real defect also takes, and
each was chased to a mechanism rather than retried until green.

**Run 1 — the log assertion.** The first full-suite run came back **1 failed / 3291 passed / 84 skipped / 1 xpassed** (18m22s),
and the failure was the unmintable-id test — which had passed eleven times running on its own. Its
`caplog.records` was *empty* after three thousand siblings had run. `test_migrations.py:545` already
records this unreliability and responds by dropping its log assertion; that was not available here,
because "it is logged rather than silent" is half of the decision this test exists to pin. The
assertion now patches `task_workspace.logger.warning` directly, which is immune to whatever global
logging state the suite has accumulated by then, and mutation M8 was re-run against the new form to
confirm it still goes red. Second full run below.

The *test* was measuring something it could not reliably see, which is the same defect class as a
test that passes while its guarantee is false — just pointed the other way.

**Run 2 — a race in the harness, and the more interesting of the two.** The second full run came
back **2 failed / 3290 passed** (19m42s): both two-turn tests, each with `cwd` `None` on the
*second* turn, and neither had ever failed alone. The cause is in `_turn`, not in the product:
`trigger_agent_directly` returns as soon as it has scheduled `_execute_run` as a background task,
and the spawn happens inside that task. `_turn` waited on `agent_trigger._background_runs` — which
on a loaded machine has not been populated yet at the moment it looks, so the drain finds nothing,
returns immediately, and reports `None` for a turn that was about to resolve perfectly well.

It now waits for **the fact it returns** — `"cwd" in captured` — before draining and settling. That
also strengthens the nine single-turn tests, which were relying on the same drain happening to be
late enough. A green run of those nine was, until this, partly luck.

### Three harness changes, each a way the suite could have gone green proving nothing

1. `conftest.py`'s autouse `_no_real_worktree_provision` now stubs `ensure_task_worktree` too.
   Stubbed at *that* function rather than at `resolve_turn_workspace` on purpose: a test restoring
   the real `resolve_agent_workspace` still sees the real precedence, and only the git commands are
   defaulted away.
2. `test_task_worktrees.py` takes `ensure_task_worktree` by **named import** — the treatment
   `test_worktrees.py` already documents for `resolve_agent_workspace`. Without it that entire file
   (21 tests) silently tested the new stub; all 8 of its provisioning tests went red the first
   time it ran alongside the new file, which is how this was found rather than argued.
3. `test_task_resolved_before_workspace.py`'s closing test now names a valid id and asserts the
   **task** checkout. See the unmintable-id note above for why leaving it alone would have been
   worse than a failure.

### Suite counts, and the one number that had to be explained

| | |
|---|---|
| Hub suite (third run, clean) | **3292 passed, 84 skipped, 1 xpassed, 0 failed** — 18m31s |
| iteration 9's baseline | 3280 passed / 84 skipped / 1 xpassed |
| delta | **+12** |

11 of those are `test_turn_workspace.py`. The twelfth is the free parametrised case
`test_no_console_flash.py::test_every_spawn_reaches_console_suppression` adds for every new Hub
source file — here `hub/hub/task_workspace.py` — exactly as iteration 9 predicted it would for
`0095`. Skips unchanged at 84; the lone `xpassed` is still the known `strict=False` fixture defect
from iteration 7.

- CLI suite: **440 passed, 3 skipped**.
- `py -3.11 -m ruff check src/ hub/ tests/` → All checks passed.
  `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` → 501 files unchanged
  (499 plus `task_workspace.py` and `test_turn_workspace.py`).
  `py -3.11 -m mypy src/` → Success, 22 source files.
- `npx openspec validate 2026-08-27-work-is-isolated-per-task --strict` → valid.
  `npx openspec list` → **30/69 tasks**, up from 21/69: 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.8, 4.9, 4.10.
- `npm run lint` not run: no file under `hub/ui/` was touched this phase. Task 8.7 owns it.
- No Hub was started or touched; no job exists to disable. The trial Hub is still on an older
  revision of this branch and has not seen `0095`.

### Carry into the next iteration — 6.5 is now a live falsehood, not a latent one

`api/v1/agents.py:1160` tells an isolated agent "This is an isolated git worktree on branch
`agentweave/<agent>`". As of this phase that sentence is **false for every task-bound turn**: the
agent is on `agentweave/task/<id>`. Task 6.5 owns the fix and phase 6 is not optional for this
change. Before 4B this was a sentence that would become wrong; after 4B it is wrong. The same
applies to the line below it ("Other agents work in separate worktrees on their own branches"),
which stops being true per-agent once a checkout belongs to a task.

That is the strongest reason not to stop this change before phase 6: it would leave the product
telling agents something untrue about their own workspace, which is the failure class F58 itself
belongs to.

## Iteration 11 — 2026-08-27 15:10 → F58-IMPL phase 4C, the refusal that had to exist by 4B

Tasks 4.12, 4.13, 4.14, 4.15, 4.16 and 8.5b of
`openspec/changes/2026-08-27-work-is-isolated-per-task`. **36/69 tasks**, up from 30.

Phase 4B is what made this urgent rather than tidy. Before it, two agents triggered on one task got
two different checkouts and nothing was lost; as of 4B they get **the same one**, on the same
branch, and until this iteration nothing refused it. That window was exactly one iteration long.

### What the refusal is, and the one thing it took to write

"One process per checkout" was never a rule in this codebase. It was a *consequence* of two
independent facts — a checkout belonged to an agent (`worktrees.worktree_path`), and an agent may
have one run in flight (`agent_trigger.py`'s per-agent 409). Keying the workspace by task removes
the coupling, and nothing else stands in: `resolve_bound_task` never consults `Task.assignee`, and
`bind_run_to_task` fills `assignee` only when it is empty. Two ordinary clicks on the board hand two
live processes one working tree.

`trigger_agent_directly` now refuses a writing turn bound to a task another agent's running run is
bound to, naming that agent. `run_task_binding.tasks_held_by_a_running_turn` answers
`task_id -> holder` in one query, shared with the flow scheduler.

### Where it went, which is not where task 4.14 said

**4.14 said "immediately after the relocated `resolve_bound_task`". That is wrong, and the
implementation deviates from it deliberately.** That line is the first place where the turn's *task*
is known — but D8's three exemptions are every one of them a statement about the turn's
**workspace**, not about its binding. Written there, each exemption becomes a restated clause, and a
restated clause is what drifts apart from the thing it is supposed to mirror.

It is instead the last line before anything is provisioned: below `resolve_turn_workspace_inputs`
(which reads, including the grandfathering read) and above `worktrees.resolve_turn_workspace` (the
first call that touches the disk). Its condition is a new predicate,
`worktrees.takes_task_workspace(repo_root, config, task_id)`, factored out of
`resolve_turn_workspace`'s own first line — so the refusal covers *exactly* the turns that get a
task checkout, and a change to either moves both.

All three exemptions then fall out with no clause of their own. A review turn never enters this
branch (`review_context` pre-empts the whole workspace resolution). A read-only agent, a
non-repository project and a grandfathered task all share a checkout that two agents have always
shared.

**This is not a matter of taste, and the mutation is the evidence.** Writing the guard where 4.14's
text says, keyed on `binding.task`, turns *all three* exemption tests red at once. The naive reading
of the task is a real defect that would have forbidden reviewing a task while it is worked, running
a read-only analyst, and continuing a grandfathered task — three things that are safe today.

### The correction that would have thrown away operator input

R3 caught this in the artifacts and phase 4C had to carry it: `schedule_agent` sorts every
`TriggerAgentError` into two buckets, and the terminal one increments `delivery_attempts` and
withdraws the entry at three. That branch's own comment gives its reason — a refusal raised there
"repeats identically forever". A collision with another turn is the one refusal in the set that does
**not**: it clears when that turn ends. Three ticks of an ordinary flow would have discarded the
message.

`TriggerAgentError` gains **`transient`**, and it is named for the classification rather than for
the cause. `workspace_unavailable` was a cause from which `schedule_agent` *derived* temporariness;
a second cause-named flag would have made that derivation an `or` growing with every future
refusal. `workspace_unavailable=True` now implies `transient` (it keeps its own name because it also
selects the `queue_agent_paused` operator event), and `schedule_agent` asks the classification once.
A transient refusal that is not the paused-workspace one records nothing at all — the same shape the
sibling per-agent rule already has, because a queue waiting its turn is the system working.

### The flow scheduler's counterpart (4.16)

`decide_firing` gains the per-task counterpart of `running`, asked once before the walk. A candidate
whose task is held by a different agent's turn is appended to `_cannot_staff` rather than skipped —
finding F23's reason, one column over: a bare `continue` made a flow whose work was being done
report itself stalled with `current_tasks: []`.

The test's task has **no assignee at all**, which is the half the per-agent view cannot see. The
existing busy branch finds nobody to recognise as busy, so without this the firing staffs its
default agent onto a checkout somebody else is using.

**The first version of this was placed wrong, and reviewing my own diff caught it.** I wrote the
check below the agent resolution, mirroring the sibling branch. That is a defect: the
`default_taken = True` arm runs *before* it, so a firing that hit a collision on its first candidate
consumed the job's own agent for a selection it was about to drop, and the default agent then sat
idle for the rest of the walk while a later ready task fell through to an empty `free` pool. A held
task cannot be staffed onto anybody, so the question does not depend on who was resolved — and
reaching the old position with `holder == agent` was impossible in any case, because all three arms
exclude an agent that is running. Hoisted to the top of the ordinary-work arm.

### Verification

`hub/tests/test_task_turn_collision.py`, 7 tests. Two of them are not on 4.12–4.16's list:

- **the refusal is per *task*, not per project.** A guard keyed on "any running run exists"
  satisfies 4.12 word for word and serialises the whole project down to one writing turn — the
  opposite of what per-task isolation is for. Caught by M3.
- **the review exemption is asserted end to end**, not as an absence. It wires the real
  `TaskRequirementLink` → `RequirementEvidence(accepted)` → `EvidenceFootprint(git)` chain so
  `prepare_review_turn` succeeds, and asserts the spawned `cwd` is a checkout **of the reviewed
  commit** while another agent holds the task.

**Seven mutations, seven caught by a named test.** Each applied to the source, run, restored:

| mutation | test that went red |
|---|---|
| M1 the refusal removed | `…second_agent_is_refused…`, `…entry_queued_and_delivers_it…` |
| M2b scoping dropped, keyed on `binding.task` | `…read_only_agent_is_not_refused…`, `…grandfathered_task_is_not_refused` |
| M3 keyed on any running run rather than this task | `test_a_turn_on_a_different_task_is_not_refused` |
| M4 the refusal classified permanent | `…entry_queued_and_delivers_it_when_the_task_is_free` |
| M5b transient refusals reach the abandonment branch | same |
| M5c `terminal_failure` derived from the old flag | same |
| M6 the flow counterpart removed | `…flow_records_a_task_another_agents_turn_holds…` |
| M7 the guard moved above the review branch (4.14's own text) | **all three** exemption tests |

**Two mutations I got wrong first, and both are worth recording** — they are the same class of
error the whole mutation discipline exists to catch, pointed at the check rather than at the code.

- My first M2 replaced only the `if` condition and left the body reading `turn_workspace.task_id`,
  so a grandfathered turn looked up `.get(None)`, found nothing and was not refused. The mutation
  reported the read-only test red and the grandfathered test green, and the green was the
  mutation's fault, not the test's. M2b changes condition and body together.
- My first M5 turned `elif not transient:` into `elif False:`, which *disables* abandonment
  entirely — indistinguishable from correct behaviour. The discriminating mutation is
  `elif not transient:` → `else:`, i.e. abandonment for transient refusals too.

**8.5b's second half could not be done as written, and that is a result rather than a gap.** It asks
to restore the refusal and confirm the review case still passes. With the placement above, no
deletion or restoration can break the review case — the guard lives in a branch review turns never
enter. The mutation that *does* discriminate it is a placement change (M7), which is a stronger
statement than the one 8.5b asked for: it says the exemption survives the specific wrong turn a
future reader is most likely to take.

**One guard has no test and says so in this entry.** `holder != agent` is unreachable today: an
agent's own second turn is refused thirty lines earlier by the per-agent 409. It is kept as
defence-in-depth against that check being relaxed, and no test claims to cover it.

### The failure I did not stage, and it was iteration 10's own harness

The first full run came back **2 failed / 3297 passed**:
`test_turn_workspace.py::test_a_read_only_agent_shares_the_project_checkout_bound_to_a_task_or_not`
died on `Path(None)` for its *second* turn, and
`test_project_workspace_unavailable.py::test_relocate_repairs_and_redrains_queued_work` found two
runs where it asserts one.

Neither is mine, and neither is flakiness to be retried. **Both were reproduced on unmodified
`HEAD`** — `git stash`, run the two files, and a two-turn test fails the same way (a different one
that time, which is itself the tell: it is whichever two-turn test loses the race, not a particular
test).

The cause is a scoping bug in the `_turn` harness iteration 10 wrote, and
`test_project_workspace_unavailable.py` already had the diagnosis written down for its own version
of it: *"Awaited **inside** the patch, and that is the whole of F40's real cause."*
`trigger_agent_directly` returns as soon as it has scheduled `_execute_run`, and the spawn happens
inside that task — so a `with patch(...)` that closes on the return **releases the patch before the
call it is patching happens**. Under load the background run then reaches the real
`PtySession.spawn`, fails for want of a `claude` binary, and no `cwd` is ever captured.

Iteration 10 fixed the *second* race on top of this one (waiting on `_background_runs`, which is
not populated yet when the drain looks) and left the first in place, because in isolation the spawn
usually wins. The wait and the drain now sit **inside** the patch, in both
`test_turn_workspace.py::_turn` and the new file's `_spawned_cwd`. `test_turn_workspace.py` (11
tests, three of them two-turn) and `test_project_workspace_unavailable.py` then pass together.

Worth stating plainly: **a harness that releases its own patch too early makes a green suite an
accident of timing.** Nine of that file's tests were passing on luck, which is the same defect class
as a test that passes while its guarantee is false.

### Suite counts

| | |
|---|---|
| Hub suite | **3299 passed, 84 skipped, 1 xpassed, 0 failed** — 18m01s |
| iteration 10's baseline | 3292 passed / 84 skipped / 1 xpassed |
| delta | **+7**, all of them `test_task_turn_collision.py` |

No new Hub *source* file this phase, so there is no free parametrised case from
`test_no_console_flash.py` — `takes_task_workspace` and `tasks_held_by_a_running_turn` were added to
files that already existed.

- CLI suite: **440 passed, 3 skipped**.
- `py -3.11 -m ruff check src/ hub/ tests/` → All checks passed.
  `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` → 502 files unchanged.
  `py -3.11 -m mypy src/` → Success, 22 source files.
- `npx openspec validate 2026-08-27-work-is-isolated-per-task --strict` → valid.
  `npx openspec list` → **36/69**, up from 30/69: 4.12, 4.13, 4.14, 4.15, 4.16, 8.5b.
- `npm run lint` not run: no file under `hub/ui/` was touched. Task 8.7 owns it.
- No Hub was started or touched; no job exists to disable.

### Carry into the next iteration

Phase 5 (release on approval) is next in the change's own order, but **task 6.5 is still the live
falsehood** iteration 10 flagged: `api/v1/agents.py:1160` tells an isolated agent it is "on branch
`agentweave/<agent>`", which has been false for every task-bound turn since 4B. Nothing in 4C
changed that. Phase 6 is not optional for this change.

The spec delta for D8 (`specs/operator-agent-creation/spec.md`) already reads as implemented —
including the sentence "An agent that works in the project's shared checkout rather than an isolated
one SHALL NOT be refused", which is a broader and more accurate statement of the exemption set than
tasks.md 4.13's three-item list. Where the two disagree, the delta is right.

---

## Iteration 12 — 2026-08-27 16:12 → F58-IMPL phase 5, and the ordering nobody could have observed

**Unit of work.** `next_action`'s phase 5 — release the task's checkout when the task is finished
(design D5), tasks 5.1 through 5.7 of
`openspec/changes/2026-08-27-work-is-isolated-per-task/tasks.md`. All seven are ticked; the change
stands at **43/69**, up from 36.

Branch and `git log` matched STATE.json on arrival (`bce0bcd`, tree clean). Nothing to reconcile.

### What now happens

`task_transition_service.release_task_workspace` runs inside `apply_transition`, after
`integrate_task`, for both terminal statuses (`approved`, `rejected`). It removes
`.agentweave/tasks/<id>` and **never** the branch, writing a `task_worktree_released` event with the
branch, whether there was an uncommitted change, the snapshot commit if one was made, and the
commits the branch carries beyond the primary checkout's HEAD — `warn` when there are unmerged ones,
`info` otherwise, the same severity rule `session_sync.py` already uses for a per-agent release.

Two scoping decisions are in the code rather than in this entry, both with the reasoning beside
them: a **grandfathered** task (`workspace_scheme == 'agent'`) returns before touching anything,
because the checkout its turns used belongs to the *agent* and outlives every task on it; and every
failure is swallowed, logged, and recorded as `task_worktree_release_failed`, because approval is a
judgement that the work was good and a `git` exit code is not grounds to reverse a human judgement.
That is integration's existing rule, restated for the same reason.

`persist_event(..., commit=False)` in both places. This runs inside `apply_transition`, whose
caller commits; the default would land the transition row early, ahead of the contract the module
states of itself.

### The test that would not have discriminated what it claimed to

Task 5.2 asks for a test that "release happens **after** `integrate_task`: the integration row for
the approval records `merged`, and the merged commit is the evidence commit rather than a snapshot
made during release." Written literally, **that test passes under both orderings** — and finding
that out is the most useful thing this phase produced.

`integration_targets` resolves the commit from the newest accepted evidence *footprint*, a database
row. It does not read a working directory and it does not read the branch tip. So a release that ran
first, snapshotting a dirty tree onto `agentweave/task/<id>` and advancing that branch, would leave
the merged sha **exactly the same**: still the evidence commit, because that is the only thing
integration ever looks up. The assertion as written observes nothing about order.

So the test observes the order directly instead. `worktrees.release_task_worktree` is wrapped in a
spy that records what `main` carried *at the moment release was called*; the assertion is that the
evidence commit was already there. Under the reversed order it is not, and the test fails. The
docstring says all of this, because a future reader who simplifies the spy away would be restoring
a test that proves nothing while appearing to prove the thing in its own name.

Worth naming plainly: **D5's ordering argument is still right, and it is defensive rather than
load-bearing today.** The design says reversing it "makes it depend on timing" — true, and the
mechanism by which it would bite is a future change that resolves the integration target from the
branch rather than from the footprint, which is precisely the F58 shape. The order costs nothing and
removes a way for that change to be silently wrong.

### The eight tests, and what each is for

`hub/tests/test_task_release.py`, new file.

| Test | Task | What fails if it goes |
|---|---|---|
| `…removes_its_checkout_and_keeps_the_branch` | 5.1 | the whole of D5 on the ordinary path |
| `…rejected_task_is_released_too_and_keeps_its_branch` | 5.3 | rejected tasks leak a directory each, forever |
| `…uncommitted_change_is_snapshotted_onto_the_branch_before_release` | 5.1 | approving a task destroys a turn's unfinished edit |
| `test_release_happens_after_integration` | 5.2 | the ordering, observed as above |
| `…reopened_task_is_re_provisioned_with_its_prior_work` | 5.4 | a revision request becomes "start over from the integration base" |
| `test_review_still_resolves_and_checks_out_after_release` | 5.5 | a reviewer cannot see work whose author's checkout is gone |
| `…release_that_raises_is_recorded_and_the_transition_stands` | 5.7 | a `git` failure reverses an approval |
| `…grandfathered_task_has_no_checkout_to_release` | (D4 boundary) | release takes a workspace away from an agent still using it |

The grandfathering test provisions a task checkout anyway and then asserts it **survives**, so it
pins that the *scheme* decides rather than what happens to exist on disk. A test that merely
asserted absence would pass with the scoping removed.

### Two things the fixtures made me measure rather than assume

- **`commit_for_task_review` keys on `RequirementEvidence.task_id`**, not on the requirement the
  task serves. A run bound to a task sets it; the bare `Run` row these tests use does not, so 5.5
  links the evidence to the task explicitly and says why in a comment. Without that the function
  returns its "no recorded evidence" refusal and the test would have looked like a release defect.
- **`worktrees.GitCommandError(args, returncode, stderr)`** takes the git argv as a list, not a
  message. A one-string construction raises `TypeError` at the point it is supposed to be
  simulating a git failure — which is how 5.7 first failed.

### Not done here, deliberately

**Task 8.3** — the mutation check for this phase (remove the release call, confirm 5.1 fails) — is a
phase 8 task and stays open. It is named here so the next iteration does not have to rediscover that
phase 5 has an outstanding proof.

**Phase 6's task 6.5 is still the live falsehood** flagged in iterations 10 and 11:
`api/v1/agents.py:1160` tells an isolated agent it is on `agentweave/<agent>`, which has been false
for every task-bound turn since 4B. Nothing in phase 5 touches it. Phase 6 remains not optional.
