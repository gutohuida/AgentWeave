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
