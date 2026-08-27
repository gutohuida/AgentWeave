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
creation, for each **direct** prerequisite of the task (`TaskDependency`), every commit its accepted
evidence names that is not already reachable from the new branch is merged into the task branch. A
merge that fails leaves nothing provisioned and refuses the turn, naming the prerequisite whose work
could not be brought in.

**Commits, plural, and the failure is not only conflict — both corrected in R3.** The Hub layer gets
these commits from `integration_targets(session, task)` (`task_integration.py:142`), which is
already exactly this query: newest **accepted** `git` footprint, one per distinct branch, `paths`
footprints contributing nothing. It returns a *list*, and open question 2 above closed on the fact
that more than one target is deliberate (`task_integration.py:178-180`). So a single prerequisite can
contribute more than one commit, and D1 said "that commit" throughout. The tasks were already
written against a `prerequisites` sequence, so only this prose was wrong.

The second correction is the failure mode. `integration_targets` returns a `commit_sha` recorded in
the database; nothing guarantees the object is still reachable in the repository. Ordinarily it is —
the prerequisite's branch survives release by D5, and a grandfathered prerequisite's per-agent branch
survives by D4 — but a branch is a ref an operator can delete, which is the same hazard that killed
half of R1's grandfathering discriminator. `git merge <sha>` for an unknown revision fails without
ever reaching a conflict. It takes the same unwind and the same refusal; what changes is the message,
which must distinguish "the prerequisite's work conflicts with yours" from "the prerequisite's
recorded commit is no longer in this repository", because those ask the operator for different
things.

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

**What unwinds a half-provisioned workspace — added in R2, because "leaves nothing provisioned" was
asserted with no mechanism behind it.** By the time a prerequisite merge can conflict, `worktree add`
has already created the directory *and* the branch, and the failed merge has left `MERGE_HEAD` and
conflict markers in the tree. Nothing in `worktrees.py` cleans that up today, and the obvious
candidate is the wrong one: `release_worktree` (`:516`) *snapshots the dirty tree onto the branch*
before removing the checkout, so reusing it here would commit a conflicted merge as though it were
the agent's work, and then keep the branch carrying it. Provisioning therefore unwinds by its own
sequence, and the order is forced by git — a branch that is checked out in a worktree cannot be
deleted:

1. `git merge --abort` in the new checkout, so the index is not left mid-merge;
2. `git worktree remove --force <path>`;
3. `git branch -D <branch>` — safe unconditionally, because this branch was created seconds ago by
   this same call and carries nothing that was not already reachable from the base;
4. `git worktree prune`, matching `ensure_worktree`'s own defence (`:279-280`) against metadata
   outliving a directory.

Only then is `IsolationUnavailableError` raised. Each step is `check=False`: a cleanup step that
fails must not replace the refusal the operator needs to read with a second, less useful one.

**And the hazard the all-or-nothing rule does not cover.** If the Hub process dies between the
`worktree add` and the unwind, the next turn finds a registered task worktree with an unfinished
merge in it. `ensure_worktree`'s idempotent path returns any correctly-registered directory
unexamined (`:268-275`), so the task version must additionally refuse a checkout that is mid-merge
rather than hand the agent a tree full of conflict markers and let it decide what happened. Stated
here rather than left to be discovered, because it is the one state this design can produce that
neither provisioning nor release owns.

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

**Three further precedences move, and R1 named only one of them.** The proposed position is above
the review-turn block and above every `work_dir` check, so a request that is wrong in two ways now
reports the task refusal where it used to report the other one. Specifically, a request naming a
nonexistent task *and* combining `work_dir` with a review turn (400, `:492-497`), *or* overriding
isolation with `work_dir` as a writing agent (400, `:511-516`), *or* carrying a traversing `work_dir`
(400, `:523-525`), *or* whose review target cannot be resolved (`ReviewTurnRefused` → 409,
`:506-509`) now answers "that task does not exist" instead. This is the right order — the task id is
the most specific thing the request said, and it is the one that decides which workspace the turn
would even have got — but it is a change to four observable answers, not one, and the tests in phase
3 pin the boundary rather than only the workspace 409.

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
(`binding_for_conversation`, defined at `run_task_binding.py:388` and reached from
`resolve_bound_task` at `:289`), and that is a requirement of `run-task-binding` already ("A
conversation carries the binding, and its runs inherit it"). Only a genuinely unbound conversation
gets the agent workspace.

**Rejected: refuse a writing turn that has no task.** It breaks ordinary chat, and `Run.task_id`'s
own documentation says unbound runs are legitimate.

**Rejected: give an unbound turn a throwaway workspace per conversation.** Unbounded in the same way
per-task workspaces would be without D5, with no terminal event to reap on — a conversation has no
"finished".

## D4 — Migration: grandfather the task, never the branch

**Decision.** No migration. Existing `agentweave/<agent>` branches and checkouts are left exactly as
they are. A task that **already carries committed work on a per-agent branch** resolves to that
per-agent workspace for the rest of its life, and is never given a task workspace.

**The discriminator, corrected in R2.** R1 proposed reading it live: a prior run bound to the task
whose `snapshot_commit_sha` is non-null (`db/models.py:1073-1080`), *and* no task branch of its own
yet. Both halves were checked against the code in R2 and both are wrong.

*The first half is under-inclusive, and it fails silently in the direction that loses work.*
`snapshot_commit_sha` is written only from `worktrees.snapshot_worktree`
(`agent_trigger.py:1524-1533`, `:2083-2092`), which returns `None` when the worktree is **clean**
(`worktrees.py:457-458`). An agent that commits its own work — which the product permits, and which
`snapshot_worktree`'s own docstring frames as the normal case by calling itself a "best-effort,
internal safety net" — ends its turn clean and records `NULL`. That task has real committed work on
the per-agent branch and would *not* be grandfathered, so its next turn would be started in a fresh
task checkout cut from the integration base with all of its own prior work missing. That is exactly
the loss of continuity the two rejected alternatives below were rejected for causing.

*The second half is not a recorded fact at all.* "No task branch exists yet" is a `git rev-parse`
against a ref an operator can delete, so a task mid-life could flip from the task scheme back to the
per-agent scheme because someone tidied up branches — and flip silently, into the scheme this change
exists to leave.

**So the discriminator is stamped once, by the migration, and then only read.** The migration that
adds the column sets `Task.workspace_scheme = 'agent'` for every task that has **at least one run**
at that moment, and leaves every other task and every task created afterwards on the default. The
resolver reads that column and nothing else.

**Deliberately over-inclusive, and that is the safe direction.** A task with a prior run that
committed nothing gets grandfathered too, and keeps today's behaviour for the rest of its life
rather than gaining isolation it could have had. The cost of that error is that F58 persists a
little longer for a fixed, shrinking set of tasks — where `rode_along_commits` already reports what
came along. The cost of the opposite error is an agent silently losing its own work mid-task. Those
are not comparable, so the rule errs the cheap way.

**It is self-extinguishing by construction rather than by argument.** The column is written by the
migration and by nothing else, so the grandfathered set is literally fixed at the instant the change
ships and can only shrink. R1's version had to *reason* that no new task could enter the state; this
one cannot express it.

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

**R3 checked the premise this rule stands on: one writer.** "Released when its task reaches a
terminal status" is only a bound if every route to a terminal status passes the release. Swept across
`hub/hub/` and `src/`: `task.status = to_status` (`task_transition_service.py:402`) is the **only**
assignment to `Task.status` anywhere, there is no `update(Task).values(status=…)` (the one
`update(Task)` in the tree sets `loop_id`, `api/v1/jobs.py:223-229`), and no migration writes it.
`apply_transition` is the sole route, so a release placed beside `integrate_task` inside it cannot be
gone around. R3 also checked the other way a task could escape the bound — being deleted while
unfinished — and there is no task-delete endpoint at all; the only `@router.delete` under
`api/v1/tasks.py` removes a *dependency* (`:1399`). The set of live task checkouts is therefore
genuinely bounded by unfinished tasks.

**One consequence of placing it inside the transaction, stated because a reviewer will ask.**
`apply_transition` does not commit; its caller does. So a release removes a directory before the
transition is durable, and a rollback would leave a task back in `in_progress` with no checkout.
That is self-healing rather than lossy, and for the reason D5 already gives twice: the branch is
never deleted, so the next writing turn re-provisions from it with the work intact — the same path a
reopened task takes. `integrate_task` sits in the same position and does git merges from there, so
this is the established shape rather than a new exposure.

**Neither `approved` nor `rejected` is a dead end**, and this is why keeping the branch is not
merely tidy: `approved -> revision_needed` and `rejected -> pending` are both legal, operator-only
edges (`task_transitions.py:147-152`). A reopened task's next writing turn re-provisions its
workspace, and `ensure_worktree`'s existing branch-reuse path restores the work — the branch was
never deleted.

**Review is unaffected, and R2 checked this rather than arguing it.** Open question 1 asked whether
`commit_for_task_review` still resolves once the checkout is gone. It does, and it cannot not:
`commit_for_task_review` (`requirement_evidence.py:653-700`) is a single `select` over
`RequirementEvidence` joined to `EvidenceFootprint`, ordered by `produced_at`. It touches no
filesystem path, so releasing a checkout cannot affect it. The second half — does the reviewer still
see the work — turns on `ensure_review_checkout` (`worktrees.py:352`), which resolves the commit and
runs `worktree add --detach` **from `repo_root`**, not from the task's checkout, against a ref store
every worktree shares. The task branch survives release, so the commit stays reachable and the
checkout succeeds. A task released at `approved` can still be reviewed, re-reviewed, or inspected.

**The F70 wedged-review recovery does not interact with this** (open question 4). It routes a task
whose named reviewer is its own author back through the reviewer ladder *without moving its status*,
which means the task stays in `under_review` — not a terminal status, so nothing is released, and
the recovered review turn takes the detached review checkout rather than the task workspace either
way. The rule and the recovery do not meet.

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
`worktrees.list_agent_branches` (`:553`) strips `refs/heads/agentweave/` and requires what remains to
match `_AGENT_NAME_RE`; `task/<id>` contains a `/` and fails. `detect_conflicts` (`:609`) is built
entirely on that list, so it would never see a task branch. Conflict detection between
concurrently-worked branches is exactly the thing per-task isolation makes *more* likely to matter,
so it must be extended to task branches rather than left to degrade.

**R2 correction: the regex is only the first of two filters, and R1 named one.** `append_record`
also requires the registered worktree's own path to equal `worktree_path(repo_root, agent)`
(`:567-568`) — the check that keeps a review checkout out of the list. A task checkout lives at
`.agentweave/tasks/<id>`, so it fails that comparison too. Relaxing the regex alone changes nothing;
the record has to be classified as agent-or-task and matched against the corresponding path, which
is why the task below says "keyed by workspace" rather than "allow a slash".

**R2 correction: "and look healthy" overstated it.** Nothing renders this. `GET /worktrees` and
`GET /worktrees/conflicts` have no caller anywhere in `hub/ui/src/` — a gap already established on
2026-08-18 and still true — so the degradation would be invisible rather than misleading. It is
still worth fixing, because it is a published API and because the fix is where the conflict feature
gets built from, but the urgency argued above belongs to the *absence* of a caller, not to this
change.

**`repo_hygiene.EXCLUDE_PATTERNS` must gain `.agentweave/tasks/`** (`repo_hygiene.py:59-69`). Without
it, `snapshot_worktree`'s `git add -A` commits an entire second checkout onto a branch — the exact
reason `.agentweave/worktrees/` and `.agentweave/reviews/` are already listed there.

**Task ids get their own validator**, mirroring `validate_agent_name`, rather than reusing it. A
value that becomes both a path component and a git ref suffix is validated at the boundary in this
module by convention (`worktrees.py:126`).

## D7 — Where a run's evidence is footprinted from

**Decision.** `Run` gains a column recording the workspace directory the run actually executed in,
written at spawn. `requirement_evidence.footprint_root` resolves an agent's footprint to that
recorded directory when it still exists, falling back to the project checkout as it does today.

**Why a recorded fact rather than a derivation.** `footprint_root` today infers the directory from
the actor alone (`requirement_evidence.py:285`: `existing_worktree(root, actor) or workspace.root`).
Under per-task isolation the correct answer depends on the turn, not the agent, and every available
derivation is wrong in some case: `RequirementEvidence.task_id` is supplied by the agent and
optional (`api/v1/agent_actions.py:841`, `body.task_id`), so it can be absent or wrong; deriving from
`Run.task_id` gives the wrong tree for a **review** run, which is bound to the task it is inspecting
(`run-task-binding`, "A run started to review a task binds to that task") but executes in a detached
review checkout. Recording what the run was actually given makes all five cases — task workspace,
per-agent workspace, grandfathered task, review checkout, and no-repository project — one rule.

**This also corrects a case that is wrong today**: a reviewer recording evidence is currently
footprinted at *its own* agent worktree, which is not the tree it reviewed.

**R3 checked that one write reaches both spawn paths, because the two runners execute by completely
separate code.** It does, and by construction rather than by discipline. `effective_work_dir` is
assigned in exactly three places — the `work_dir` override (`agent_trigger.py:521`), the review
checkout (`:531`) and the resolved workspace (`:541`) — all before the single `Run(` construction at
`:729`. The Claude/Codex split happens later and *inside* `_execute_run`, at `:1310`
(`if use_codex_app_server: await _execute_codex_appserver_run(...)`), by which point the row is
already written. So there is one place to write the column and no way for the two runners to
disagree. The two blocks at `:1524` and `:2083` are the per-runner run *finalisations* — where
`snapshot_commit_sha` is written, which is why D4 cites them — and D7 does not depend on them.

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


## D8 — One turn at a time in a task's checkout

**Found in R2. This is the finding that most changes the shape of the work.**

Today, "one process per checkout" is not a rule anywhere in the code — it is a *consequence* of two
independent facts. A checkout belongs to an agent (`worktrees.worktree_path`), and an agent may have
only one run in flight at a time: `trigger_agent_directly` refuses with a 409 while a `running` row
exists for that `(project, agent)` (`agent_trigger.py:439-445`). Keying the workspace by task breaks the
coupling. Nothing anywhere refuses a second *agent* bound to the same task:
`resolve_bound_task` takes the task from the delegation, the explicit `task_id`, or the
conversation, and never consults `Task.assignee`; and `bind_run_to_task` only fills `assignee` when
it is empty (`run_task_binding.py:350-351`), so it cannot refuse either. An operator starting task
`T` from the board on `builder-2` while `builder-1` is already running on `T` is an ordinary
sequence of clicks, and under D1 it hands two live agent processes the **same working directory on
the same branch**.

That is the silent lost update `worktrees.py`'s own module docstring says the whole module exists to
prevent, reintroduced along a new axis. It has to be closed by this change, not after it.

**Decision.** A task's checkout admits one writing turn at a time. `trigger_agent_directly` gains a
second refusal, in the same shape as the existing per-agent one: while a `running` run is bound to
this task and belongs to a *different* agent, a writing turn bound to that task is refused, naming
the agent that holds it. **The refusal is transient, and must be classified as such** — see the two
sections below, which is where R3 found this decision incomplete.

**It cannot sit beside its sibling, and that is worth stating because the obvious reading is that it
should.** The per-agent 409 runs at `agent_trigger.py:439-445`, thirty lines before `repo_root`
exists and long before any binding is resolved — at that point the turn's task is simply not known.
So this refusal goes immediately after the relocated `resolve_bound_task` (D2), which is the first
line in the function where "which task is this turn about" has an answer. **D2 is therefore a
prerequisite of D8, not merely a neighbour of it**: without the move there is no point in
`trigger_agent_directly` where this check could be written at all.

**R3: the refusal is transient, and the branch it lands in is built for permanent failures.** This
is the correction that matters most in this round, because D8 as R2 left it would silently *drop an
operator's input*. `trigger_agent_directly` has exactly one caller — `turn_scheduler.schedule_agent`
(`turn_scheduler.py:57`, `:125`) — and everything that starts a turn reaches it the same way, by
appending an `InboundQueueEntry` and calling `schedule_agent` (nine `new_entry` sites and twenty
`schedule_agent` sites across `hub/hub/`). `schedule_agent` sorts a `TriggerAgentError` into two
buckets, and only `workspace_unavailable` is treated as temporary. Everything else falls to
`turn_scheduler.py:165-183`, whose comment states the reasoning in as many words: *"a refusal raised
here … repeats identically forever"*. It increments `delivery_attempts` on every selected entry and,
at `DELIVERY_ATTEMPT_LIMIT` (`inbound_queue.py:174`, three), marks them `withdrawn` and broadcasts
`queue_entry_abandoned`.

A collision with another agent is the one refusal in that set that does **not** repeat forever — it
clears the moment the holder's run ends. Left in the terminal bucket, three ticks of an ordinary
flow would throw the message away. The sibling rule never has this problem because it never reaches
that branch: `schedule_agent` reads the per-agent `running` fact itself, before it calls
(`turn_scheduler.py:60-66`), and returns `waiting_reason="agent is already running"` with
`terminal_failure=False`, leaving the entry queued for the next tick.

So D8 is only complete with the classification: the per-task refusal carries a transient marker in
the same shape `workspace_unavailable` already establishes, and `schedule_agent` leaves the entry
queued and reports a waiting reason instead of counting an attempt.

**R3: and "a 409" is not what an operator observes, so the requirement must not promise one.** Since
`schedule_agent` converts every `TriggerAgentError` into a `ScheduleResult` and never re-raises
(`turn_scheduler.py:206-209`), the `/trigger` route answers **200 with `status: "queued"` and a
`waiting_reason`** (`agent_trigger.py:1011`, answered at `:1030-1040`). That is the correct operator experience — the
input is accepted and will run when the task is free — but it means the 409 is an internal status on
an exception object, not an HTTP answer anybody sees. The same is already true of the per-agent 409,
which is defence-in-depth behind `schedule_agent`'s own check rather than a reachable response. The
spec requirement is therefore written as "refuses to start", not as a status code, and the tests
assert at the layer each fact actually lives in.

**R3: the flow scheduler needs a counterpart, for the reason F23 already established.** No flow or
job bypasses the guard — that was open question 5, and the answer is no, because every route funnels
through `schedule_agent`. But the flow scheduler does not *rely* on the sibling refusal either: it
pre-empts it. A candidate whose `assignee` is mid-turn is recorded in `_cannot_staff` and skipped
(`scheduler.py:1274-1283`), and finding F23 is precisely the record of what happens when such a
candidate is dropped silently instead — a flow with every agent busy reported itself as stalled with
`current_tasks: []`. D8 introduces a second way for a candidate to be unstartable that the walk
cannot see: two loops racing on one task, or a task left `in_progress` with no assignee. Those turns
should be recorded the way F23's are rather than discovered from an abandoned entry.

Three cases deliberately fall outside it. A **review** turn is bound to the task it inspects
(`run-task-binding`) but never touches the task workspace — `review_context` pre-empts workspace
resolution entirely (`agent_trigger.py:527-532`) — so it is not refused. A **read-only** agent
shares the project checkout and has no isolation to collide over. And a **grandfathered** task (D4)
is worked in per-agent checkouts, where the old coupling still holds and this refusal would forbid
something that is safe today.

**Rejected: let them share, and rely on git.** Git does not arbitrate two processes editing the same
working tree; it arbitrates two *branches*. Concurrent edits to one checkout are last-write-wins at
the filesystem, and the end-of-turn `snapshot_worktree` of whichever finishes second would commit
both agents' half-finished work under one agent's name.

**Rejected: give the second agent its own checkout of the same branch.** Git refuses outright — a
branch may be checked out in only one worktree — so this is not available without detaching, which
loses the branch the whole design is built on.

**Rejected: queue the second turn instead of refusing it.** The product has a queue and this looks
like it belongs in it, but the existing per-agent collision is a 409 and not a queue, and answering
the same class of collision two different ways is the inconsistency an operator cannot predict.
Worth revisiting as its own change if it turns out to bite; not worth inventing here.

## The surfaces that assume one workspace per agent, re-derived from the code

Open question 3 asked for this list to come from the code rather than from the exploration's table.
It was re-derived in R2 by sweeping every reference to `worktree_path`, `branch_name`,
`existing_worktree`, `resolve_agent_workspace`, `ensure_worktree`, `release_worktree`,
`list_agent_branches`, `detect_conflicts` and `worktree_root` across `hub/hub/` and `src/`, and every
literal `.agentweave/worktrees` path. **Four sites the exploration's table and R1 both missed:**

| site | what it does | why it matters here |
|---|---|---|
| `project_workspace.py:175-178` | refuses to register a project whose path runs through `.agentweave/worktrees` | the same guard is needed for `.agentweave/tasks`, or a task checkout becomes registrable as a project |
| `project_lifecycle.py:240-241` | refuses to relocate a project while `.agentweave/worktrees` is non-empty | a project with only *task* checkouts would relocate, and every git worktree registration — which stores absolute paths — would break |
| `api/v1/worktrees.py:148-156` (`GET /worktrees/{agent}`) | answers "where does this agent work, and on which branch" | it is the **only** worktree endpoint with a UI caller, and under per-task isolation its answer is wrong for every task-bound turn |
| `api/v1/agents.py:1162-1164` | tells the agent "other agents work in separate worktrees … they cannot see yours" | true per agent, false per task once a task's checkout can outlive its agent's involvement |

**And one claim in the proposal that R2 had to correct.** `WorktreesPanel.tsx` was named as a surface
that assumes one workspace per agent. It assumes nothing: it is a stub that renders a hard-coded
`EmptyState` ("No worktree activity") and calls no API at all. The operator-facing workspace surface
is `WorkspaceLocation` inside `AgentSettingsPage.tsx`, which reads `GET /worktrees/{agent}` through
`api/workspace.ts` and renders the working directory and branch. That is the thing that will lie to
an operator, and the `agent-configuration` delta is already written against it — so the delta was
right and the prose naming the component was wrong.

## What R2 answered, and what is left for R3

R1 ended this document with four open questions. All four are closed above; the answers are recorded
where the decision they belong to lives, not here.

1. **`commit_for_task_review` after release** — closed in D5. It is a pure database query and cannot
   be affected by a checkout; `ensure_review_checkout` resolves against `repo_root`'s shared ref
   store, and the branch survives release. D5's argument was right, and is now backed by the code
   rather than by the argument.
2. **`integration_targets` keying by `EvidenceFootprint.branch`** — closed, and it was a false
   alarm. One target per branch is *deliberate*: the code says so in as many words
   (`task_integration.py:178-180`, "work produced on two branches has to be merged twice, and
   silently dropping one of them would integrate half of what was approved"). Merging twice is the
   correct behaviour, not a defect. And D4 forbids the situation anyway — a grandfathered task never
   acquires a task branch, so its evidence cannot span both schemes. Nothing to change.
3. **The call sites** — re-derived from the code in the table above. Four were missing, and one
   named component turned out to be a stub.
4. **The F70 wedged-review recovery** — closed in D5. It leaves the task in `under_review`, which is
   not terminal, so release never fires; and the recovered turn takes the review checkout regardless.

## What R3 caught

R2 left three things for R3 and asked it to assume R2 had also got something wrong. It had.

**The one that changes the work: D8's refusal was transient, classified as permanent, and would have
dropped input.** Written up in D8 above. R2 asked whether a flow or a job could reach a second
writing turn by a route that misses the guard; the answer is **no** — every route funnels through
`new_entry` → `schedule_agent` → `trigger_agent_directly`, which has exactly one caller — but asking
that question is what surfaced the real defect one layer out. The guard is reachable by everything;
what happens *after* it fires is wrong. Three ticks of an ordinary flow would have marked the queue
entry `withdrawn`. R2 wrote D8 by reading `agent_trigger.py`, where the refusal is raised, and never
read the caller that decides what a refusal means.

**D8's "409" was a promise about something an operator cannot see.** `schedule_agent` never
re-raises; `/trigger` answers 200/`queued` with a waiting reason. The spec requirement never said
409 and was already right; the design prose and task 4.12 both did, and are corrected.

**The spec delta was over-broad against its own decision.** D8 names three exemptions; the
requirement in `operator-agent-creation` stated two, and its opening sentence — "while a writing turn
is in flight for a task" — covers a grandfathered task, which D8 deliberately exempts. Fixed in the
delta, not by narrowing D8.

**D1 said "that commit" where the code returns a list, and named only half the failure.** Both
corrected in D1: `integration_targets` returns one target per branch and can return several for one
prerequisite, and a recorded commit whose object is no longer in the repository fails the merge
without conflicting.

**D4's stamp holds, and R3 sharpened the test rather than the decision.** "Only the migration writes
this column" is enforceable — `Task.status`'s single writer is the existing proof that this codebase
holds invariants of exactly that shape, and `test_task_attribution.py` is the precedent for asserting
one by scanning the source. But task 4.11 said "grep the tree" without saying for what, and a grep
for `task.workspace_scheme =` alone passes against `Task(workspace_scheme=…)` and
`update(Task).values(workspace_scheme=…)`. Named in the task now, along with the default the design
never stated.

**The citation sample came back clean.** Four of the load-bearing ones were re-read for what the line
*means* rather than for the line number: `worktrees.py:457-458` (snapshot returns `None` on a clean
tree — D4's whole correction rests on it), `:537-538` (release snapshots onto the branch *before*
removing — D1's "do not reuse `release_worktree`"), `:268-275` (the idempotent path validates the
registration and not the tree's state — task 2.7b), and `run_task_binding.py:350-351` (`assignee` is
filled only when empty — D8's premise). All four say what the design says they say. So do
`agent_trigger.py:439-445`, `:469`, `:492-497` and `task_transition_service.py:434-435`, checked in
passing. Two rounds of mechanical sweeping appear to have worked.

**One naming slip, worth a line because it costs an implementer a grep.** R2 called the function
`_trigger` throughout. There is no `_trigger` in the tree; it is `trigger_agent_directly`
(`agent_trigger.py:331`), and `_trigger` matches nothing. Corrected everywhere it appeared.

**What R3 did not do.** It did not re-run the 65-assertion citation sweep — R2 ran it twice and the
sample above suggests the remaining yield is low. It did not review phases 5–8 of `tasks.md` claim by
claim; they were read for consistency with the corrections above and no further. If a third round is
ever wanted, that is where it should start.
