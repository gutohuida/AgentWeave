## Context

The full investigation is `openspec/explorations/2026-08-27-per-task-worktrees.md` (337 lines, nine
sections). Every file:line below was opened and read on 2026-08-27 on branch
`autonomous/2026-08-27-the-rest-of-the-work`. This document closes the six open questions that
exploration ends with, in the order it ranked them.

What exists today, stated so the decisions below can be checked against it rather than against
memory:

| fact | where |
|---|---|
| One worktree per agent, at `.agentweave/worktrees/<agent>` on `agentweave/<agent>` | `worktrees.py:139`, `:144` |
| Provisioned lazily on a writing turn, from `HEAD`, reusing an existing branch | `worktrees.ensure_worktree`, `:259-300` |
| Chosen at `agent_trigger.py:535`, before the turn's task is known at `:558` | `api/v1/agent_trigger.py` |
| Released only when an agent leaves the roster | `api/v1/session_sync.py:131` |
| `release_worktree` snapshots, removes the checkout, keeps the branch, reports unmerged commits | `worktrees.py:516-548` |
| Approval merges the evidence commit with `--no-ff`, ancestry and all | `task_integration.py:289-299` |
| A dependency is met at `approved`, and the gate sits on `-> in_progress` only | `dependency_gate.py:31`, `task_transition_service.py:375-380` |
| Integration is best-effort and never blocks approval | `task_transition_service.py:434-435`, `tests/test_task_integration.py:14` |
| Evidence's footprint root is `existing_worktree(root, actor)` — actor only, no task | `requirement_evidence.py:270-285` |

## Goals

- One approval lands one task's work.
- No history is guessed at, split, or rewritten by this change.
- The number of live checkouts is bounded by work in flight rather than by tasks ever created.
- A turn is never silently started on a base that lacks what the task was told to build on.

## Non-Goals

Listed in `proposal.md`. The two that shape the decisions below: no re-opening of the mechanism
choice, and no splitting of existing per-agent branches.

---

## D1 — What a task workspace is cut from

**Decision.** A task workspace is a linked git worktree at `.agentweave/tasks/<task_id>` on branch
`agentweave/task/<task_id>`, created from the project's **integration base** — `Project.main_branch`
when it is set and resolves, and the project checkout's `HEAD` otherwise. Immediately after
creation, for each **direct** prerequisite of the task (`TaskDependency`) whose accepted evidence
names a commit that is not already reachable from the new branch, that commit is merged into the
task branch. A merge that conflicts leaves nothing provisioned and refuses the turn, naming the
prerequisite whose work could not be brought in.

**Why the prerequisite merge is needed at all.** The dependency objection was dissolved on the
grounds that a prerequisite must be `approved` before its dependent may start, and approval merges.
The first half holds — `MET_STATUS = "approved"` (`dependency_gate.py:31`) and the gate is on
`-> in_progress` (`task_transition_service.py:375-380`). The second half does not: integration is
best-effort, and six paths leave a task `approved` with its work not on the main branch —
`NO_MAIN_BRANCH`, `NOT_A_REPOSITORY`, `NOTHING_TO_MERGE`, `CHECKOUT_DIRTY`, `CHECKOUT_ELSEWHERE`,
and a `FAILED` conflict (`task_integration.py:52-70`, `:289-305`). Today a dependent inherits that
work anyway *when the same agent holds both tasks*, because it is literally the same branch. The
mechanism that is F58 is quietly carrying dependent work.

**Why provisioning-time merge succeeds where approval-time integration skipped.** Three of the six
skip reasons are facts about the operator's own checkout — `CHECKOUT_DIRTY`, `CHECKOUT_ELSEWHERE`,
and `NO_MAIN_BRANCH`'s consequence — and none of them applies to a freshly created task worktree,
which is clean and on its own branch by construction. So the merge that could not happen into
`main` can happen into the task branch. `NOTHING_TO_MERGE` needs no merge: there is no commit,
because the prerequisite's evidence was a `paths` footprint, which `integration_targets` documents
as "a supported project shape, not a degraded one" (`task_integration.py:150`). `NOT_A_REPOSITORY`
has no worktrees at all and is out of scope by construction.

**Transitivity is free and should be stated rather than assumed.** If A → B → C and each was
provisioned this way, B's branch already contains A's work, so merging B's evidence commit into C
brings A's too. Direct prerequisites are therefore sufficient, *provided* every link was provisioned
under this scheme. A grandfathered link (D4) breaks that chain, which is why D4 makes grandfathering
per-task and self-extinguishing rather than open-ended.

**Rejected: make the dependency gate require *integrated*, not merely `approved`.** This was the
cleanest-sounding option — it removes the divergence between the two facts at the source rather than
compensating for it. It is refused by `NOTHING_TO_MERGE`: a project whose evidence uses `paths`
footprints has no commit to integrate, ever, so a dependency chain in such a project could never
advance. That is a supported project shape (`task_integration.py:150`), so this option would take a
working product configuration and make it permanently stuck.

**Rejected: cut from the base and state the gap in the turn context.** Cheapest, and it puts the
problem on the agent. Refused because the product's own position on this class of thing is already
recorded: `operator-agent-creation`'s no-repository requirement makes "tell the agent" the whole
mitigation *only where no mechanism exists*. Here a mechanism exists and costs one merge.

**Rejected: cut from the agent's current branch.** That is today's behaviour renamed, and it
reintroduces exactly the property this change removes.

**Rejected: always cut from `HEAD`, as `ensure_worktree` does today.** `HEAD` is whatever the
operator's checkout happens to be sitting on, including a feature branch or a detached commit. The
branch approval will merge *into* is `Project.main_branch`, so cutting from anything else means the
task branch's merge base with the integration target is arbitrary. `HEAD` survives only as the
fallback for a project with no main branch named, where there is nothing better and today's
behaviour is already `HEAD`.

**Consequence to accept.** Provisioning can now fail for a reason that is about *another* task. The
refusal is explicit and names that task; it joins `IsolationUnavailableError`, which already refuses
a turn when a workspace cannot be prepared (`agent_trigger.py:536-541`).

## D2 — Resolving the task before the workspace

**Decision.** `resolve_bound_task` moves from `agent_trigger.py:558` to immediately after
`repo_root` is established (`:469`) and before the review-turn block at `:483`. `binding` is then
consumed unchanged where it is today (`:749`).

**Verified, not assumed** — the exploration flagged this as the single largest structural obstacle
and required the "Reads only" docstring at `run_task_binding.py:247` to be checked rather than
believed. It performs exactly three database reads and no writes:

| call | what it does |
|---|---|
| `binding_for_delivery` → `select(InboundQueueEntry).where(id.in_(ids))` | `run_task_binding.py:218-223` |
| `resolve_task_for_project` → `session.get(Task, task_id)` | `:120` |
| `binding_for_conversation` | reads the conversation's binding; runs only where no task was named |

Its own docstring states the invariant that makes moving it safe: "Safe to read twice because the
mutations never feed back into this" (`:257-259`). The staging that mutates — `rebind_conversation`,
`bind_run_to_task`, `record_response_run` — stays at `:749`, before delivery, which is what commits.

**Inputs are available at the new position.** `conversation` is resolved at `:362`, `project_id`,
`queue_entry_ids` and `task_id` are parameters.

**The one observable change, stated because it is a behaviour change.** `resolve_task_for_project`
raises `TaskBindingError` for a task id that is absent or belongs to another project, and that is
handled globally at `main.py:364`. After the move, that refusal is raised *before* a worktree is
provisioned instead of after. A request naming a nonexistent task therefore stops leaving a checkout
behind. Precedence against the project-workspace 409 is unchanged, because the move is to a point
*after* `resolve_project_workspace`.

**Rejected: move it to the top of the function, before the workspace is resolved.** It would invert
the precedence between "this project's directory is unavailable" (409, with `directory_state`) and
"that task does not exist", changing which error an operator sees when both are true.

**Rejected: leave the resolution where it is and re-read the binding a second time, earlier.** Two
reads of the same fact in one turn is the restated-fact pattern this codebase repeatedly names as a
defect source, and it costs the same queries.

## D3 — A turn with no bound task

**Decision.** The workspace is keyed by what the turn is about: a task workspace when the turn is
bound to a task, and the agent's own workspace — `.agentweave/worktrees/<agent>` on
`agentweave/<agent>`, exactly as today — when it is not.

The per-agent workspace is therefore not legacy. It is the workspace for work that is not a task,
which is a real and permanent category: exploration, chat, questions, and scheduled work
(`db/models.py:1048-1049` says so of `Run.task_id`: "unbound is legitimate").

**This does not leave two schemes alive by accident.** A follow-up typed into the composer with no
task id still resolves to the task, because the conversation carries the binding
(`binding_for_conversation`, `run_task_binding.py:284-289`), and that is a requirement of
`run-task-binding` already ("A conversation carries the binding, and its runs inherit it"). Only a
genuinely unbound conversation gets the agent workspace.

**Rejected: refuse a writing turn that has no task.** It breaks ordinary chat, and `Run.task_id`'s
own documentation says unbound runs are legitimate.

**Rejected: give an unbound turn a throwaway workspace per conversation.** Unbounded in the same way
per-task workspaces would be without D5, with no terminal event to reap on — a conversation has no
"finished".

## D4 — Migration: grandfather the task, never the branch

**Decision.** No migration. Existing `agentweave/<agent>` branches and checkouts are left exactly as
they are. A task that **already carries committed work on a per-agent branch** resolves to that
per-agent workspace for the rest of its life, and is never given a task workspace.

**The discriminator is a fact, not a heuristic:** the task has at least one prior run bound to it
(`Run.task_id == task.id`) whose `snapshot_commit_sha` is non-null (`db/models.py:1078-1085`), and no
task branch of its own exists yet. `snapshot_commit_sha` is the auto-snapshot commit that run
produced, so a non-null value is proof that work for this task was committed onto that agent's
branch.

**It is self-extinguishing.** After this ships, a task's first writing turn creates its task branch,
so no new task can ever enter the grandfathered state. The set is fixed at the moment of the change
and only shrinks as those tasks terminate.

**Why not adopt the per-agent branch as the task branch.** It is continuous and it is a lie: the
adopted branch carries other tasks' commits, so the change would ship a guarantee — "one approval
lands one task's work" — that is false for an unbounded set of tasks, silently. This repository's
named failure mode is a guarantee whose test cannot fail; shipping one deliberately is worse than a
discontinuity that is visible. Grandfathering keeps those tasks explicitly under the *old* scheme,
where `rode_along_commits` already reports what came along.

**Why not start the in-flight task clean from the base.** The agent's own prior work would be absent
from its checkout with no explanation, mid-task. That is a real loss of continuity for the exact
tasks a person is watching.

**Why not split the branch.** There is no record of which commit belonged to which task. That
absence is F58 itself, so any split is a guess.

**`retry_integration` keeps working** (`task_transition_service.py:440`), because nothing is renamed
or deleted: an approved task whose integration skipped still has its commit on the branch it was
made on.

**A grandfathered task's prerequisites are not merged into its workspace** (D1 does not apply to a
per-agent workspace), which is precisely today's behaviour for that task. Stated rather than left to
be discovered.

## D5 — Release, and what bounds the disk

**Decision.** A task workspace is released when its task reaches a terminal status (`approved` or
`rejected`), *after* the transition's own integration has run. Release is `release_worktree`'s
existing discipline (`worktrees.py:516`): snapshot any uncommitted change onto the branch first,
remove the checkout directory, **never** remove the branch, and report commits the branch carries
beyond the primary checkout's HEAD.

**Ordering against integration is load-bearing.** `integrate_task` runs at
`task_transition_service.py:434-435` on `-> approved`. Release must follow it, or a snapshot taken
at release could add a commit after the evidence commit — harmless to the merge, but the merge must
already have happened for that to be true, and reversing the order makes it depend on timing.

**Neither `approved` nor `rejected` is a dead end**, and this is why keeping the branch is not
merely tidy: `approved -> revision_needed` and `rejected -> pending` are both legal, operator-only
edges (`task_transitions.py:145-150`). A reopened task's next writing turn re-provisions its
workspace, and `ensure_worktree`'s existing branch-reuse path restores the work — the branch was
never deleted.

**Review is unaffected.** A review turn uses a detached checkout at the evidence commit
(`ensure_review_checkout`, `worktrees.py:352`), and that commit stays reachable from the task branch,
which survives release. A task released at `approved` can still be reviewed, re-reviewed, or
inspected.

**The bound.** Live task workspaces are bounded by tasks not yet finished, rather than by tasks ever
created. The project's workspace surface reports how many exist, and offers the operator an explicit
release for any one of them, which is the same `release_worktree` call.

**Rejected: keep the checkout on `rejected`.** The exploration's own reading was that a rejected
task's work is what an operator most wants to look at. Refused because the branch survives release,
so nothing is lost — `git checkout agentweave/task/<id>` still reaches it — and an exception to the
bound that only an operator reading the source would know about is worse than a uniform rule.

**Rejected: release when the task leaves the agent-actionable band.** It would reap at `completed`
and `under_review`, i.e. every time work goes out for review, and re-provision on every
`revision_needed`. It bounds slightly tighter at the cost of churning a checkout on the most common
loop in the product.

**Rejected: a hard cap that refuses a turn.** Refusing to start work because a *different* task's
checkout exists is a failure the operator cannot act on in the moment.

**Rejected: evicting the least-recently-used workspace automatically.** Silently deleting a checkout
holding an agent's in-flight work is the outcome `release_worktree`'s whole design exists to avoid.

## D6 — Naming, and the parse that would silently break

**Decision.** Task branches are `agentweave/task/<task_id>` and task checkouts live under
`.agentweave/tasks/<task_id>`, a sibling of `.agentweave/worktrees/` and `.agentweave/reviews/`.

**The extra path segment is not cosmetic.** Agent names are validated by
`_AGENT_NAME_RE = ^[a-zA-Z0-9_-]{1,32}$` and task ids are `task-<12 hex>` (`spec_tasks.py:206`),
which **matches that regex**. So `agentweave/task-ab12cd34ef56` would be indistinguishable from the
branch of an agent named `task-ab12cd34ef56`, and `.agentweave/worktrees/<task-id>` indistinguishable
from that agent's checkout. The `task/` segment cannot appear in an agent name, because `/` is not in
the character class.

**A parse breaks silently unless it is changed with the naming.**
`worktrees.list_agent_branches` (`:551`) strips `refs/heads/agentweave/` and requires what remains to
match `_AGENT_NAME_RE`; `task/<id>` contains a `/` and fails. `detect_conflicts` (`:608`) is built
entirely on that list, so `GET /worktrees/conflicts` would return an empty list forever and look
healthy. Conflict detection between concurrently-worked branches is exactly the thing per-task
isolation makes *more* likely to matter, so it must be extended to task branches rather than left to
degrade.

**`repo_hygiene.EXCLUDE_PATTERNS` must gain `.agentweave/tasks/`** (`repo_hygiene.py:59-69`). Without
it, `snapshot_worktree`'s `git add -A` commits an entire second checkout onto a branch — the exact
reason `.agentweave/worktrees/` and `.agentweave/reviews/` are already listed there.

**Task ids get their own validator**, mirroring `validate_agent_name`, rather than reusing it. A
value that becomes both a path component and a git ref suffix is validated at the boundary in this
module by convention (`worktrees.py:127`).

## D7 — Where a run's evidence is footprinted from

**Decision.** `Run` gains a column recording the workspace directory the run actually executed in,
written at spawn. `requirement_evidence.footprint_root` resolves an agent's footprint to that
recorded directory when it still exists, falling back to the project checkout as it does today.

**Why a recorded fact rather than a derivation.** `footprint_root` today infers the directory from
the actor alone (`requirement_evidence.py:285`: `existing_worktree(root, actor) or workspace.root`).
Under per-task isolation the correct answer depends on the turn, not the agent, and every available
derivation is wrong in some case: `RequirementEvidence.task_id` is supplied by the agent and
optional (`api/v1/agent_actions.py:840`, `body.task_id`), so it can be absent or wrong; deriving from
`Run.task_id` gives the wrong tree for a **review** run, which is bound to the task it is inspecting
(`run-task-binding`, "A run started to review a task binds to that task") but executes in a detached
review checkout. Recording what the run was actually given makes all five cases — task workspace,
per-agent workspace, grandfathered task, review checkout, and no-repository project — one rule.

**This also corrects a case that is wrong today**: a reviewer recording evidence is currently
footprinted at *its own* agent worktree, which is not the tree it reviewed.

**Rejected: pass the task id into `footprint_root`.** It moves the same derivation one level out and
still cannot answer for a review run.

**Rejected: keep `worktrees.py` responsible for the answer.** That module states it is "deliberately
independent of any DB/session layer" (`worktrees.py:27-30`) and the answer now depends on database
state. The base commit and the prerequisite commits of D1 are passed *into* it for the same reason.

## Risks

- **Provisioning a task workspace is more expensive than provisioning an agent's** — a `worktree
  add` plus up to N merges, on the first writing turn of a task. Bounded by the number of direct
  prerequisites, which is small in practice, and it happens once per task.
- **Disk.** Measured on this repository: 2028 tracked files, 37.7 MiB of working tree, so nineteen
  live task checkouts would be ~716 MiB. D5 bounds the live set to unfinished tasks and makes the
  count visible; it does not make a checkout small.
- **The cost precedent cited when option (c) was chosen points the other way.** Review checkouts are
  bounded because `ensure_review_checkout` *re-points* one directory per agent (`worktrees.py:352`).
  A task workspace cannot be re-pointed — it holds in-flight work by definition — so the bound has
  to come from D5's release, not from that precedent. Recorded here because the decision was taken
  partly on that citation.
- **Two schemes coexist for a bounded period** (D4). Every surface that lists workspaces must
  therefore be able to show both, or an operator will conclude a task's work has vanished.

## Open questions for R2 and R3

1. Does `commit_for_task_review` (`requirement_evidence.py:653`) still resolve, and does the
   reviewer still see the work, once a task's checkout has been released at `approved`? D5 argues
   yes because the branch survives; it has not been executed.
2. What does `integration_targets` group by when a task's evidence spans a grandfathered per-agent
   branch *and* a later task branch — it keys `newest` by `EvidenceFootprint.branch`
   (`task_integration.py:180-186`), so such a task would produce two targets and merge twice. Is
   that right, or should the change forbid the situation?
3. Does anything else assume one workspace per agent that this document has not listed? The
   exploration tabulated eleven call sites; R3 should re-derive that list from the code rather than
   from the table.
4. The F70 wedged-review recovery added 2026-08-27 reassigns a review without moving its status —
   check it against D5's release-on-terminal rule.
