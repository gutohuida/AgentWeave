# Design

## Context

Break 1 and break 7 of `openspec/explorations/2026-08-30-why-a-flow-cannot-land-its-work.md`, and
finding F124. The operator took D-B on 2026-08-30 and pre-authorised D4 (the default) and D5 (what
is merged) with their rationale and their cost-if-wrong. Those are inputs here, not decisions to
re-take; what this document decides is everything the operator's three sentences do not settle.

Round 1 wrote this against the code at `c326743`, after `a-flow-briefing-names-its-contract`,
`a-review-a-flow-cannot-staff-is-named` and `approval-refuses-unaccepted-evidence` had all been
implemented, and after DRIVE-1 measured the flow end to end.

## D1 — The per-task branch guarantee holds for loop tasks, verified rather than assumed

D5 made this a condition of relying on it, because `work-is-isolated-per-task` was written about
flows. Verified by reading the dispatch, not by reasoning about intent:

- `task_workspace.resolve_turn_workspace_inputs` (`task_workspace.py:58-101`) returns `UNBOUND` for
  exactly three reasons: no task, `task.workspace_scheme != 'task'`, and a task id
  `validate_task_id` refuses. **None of them mentions a loop, a flow, or a document.**
- `worktrees.takes_task_workspace` (`worktrees.py:638-649`) is `task_id is not None and
  is_writing_agent(config) and is_git_repo(repo_root)`. Same: nothing about how the task got there.
- `Task.workspace_scheme` defaults to `'task'` at the column (`models.py:739-741`) and is written by
  migration `0095` **and by nothing else** — a property `test_task_workspace_scheme.py` enforces by
  scanning the source.

So a loop task created today gets `agentweave/task/<task_id>`, cut from the project's main branch
(`task_workspace._integration_base`), holding that task's turns and nothing else.

**The exception is real and is handled, not waved through.** Three shapes reach approval with no task
branch: a task grandfathered by `0095` (`workspace_scheme == 'agent'`), a task whose only turns ran
under a read-only agent, and a project that is not a git repository. For the first two the work is on
`agentweave/<agent>`, which carries every task that agent ever touched — **merging it is F58**. This
change therefore never falls back to the agent branch; it records a skip that names the situation.

## D2 — The declaration is one nullable Boolean column, NULL meaning "the current default"

`Loop.work_needs_evidence: Mapped[Optional[bool]]`, nullable, no server default.

Nullable rather than `default=False` for the reason `Loop.control` already states in the same class
(`models.py:1405-1412`): a row that stores today's default keeps asserting it after the default
moves, so the resolution belongs at the point of use. Here that point is the merge-target resolver,
which reads `False if row.work_needs_evidence is None else row.work_needs_evidence`.

It also buys the thing this change needs for its own tests: "the operator said no" and "the operator
did not say" are distinguishable rows, so a later default flip is a one-line change with a
demonstrable effect rather than a data migration.

**Rejected: an enum naming the merge source** (`evidence` | `task_branch`). More honest about the
mechanism, and it would extend cleanly to a third source later. Rejected because the operator decided
a *declaration about evidence*, not a choice of merge mechanism — and a third value would be a new
way for work to reach `master`, which is a change of its own with its own rounds, not a spare slot to
leave open.

**Rejected: deriving it from `spec_document_id is None`.** It reads as free, and it is exactly the
implicit-requirements answer D-B rejected. It also collapses the case the product genuinely has: a
documentless loop whose individual tasks carry `requirement_ids` and whose operator does want the
evidence chain.

## D3 — Declared at creation, refused on edit

`create_loop` and `POST /jobs` accept it; `PATCH /jobs/{id}` refuses it with a sentence naming why.

The three fields that *are* editable go through the pending-edit machinery, whose whole rationale is
that *"a firing already under way keeps the definition it was briefed with"* (`models.py:1421-1426`).
That rationale is about a firing. This field is not read by a firing at all — it is read at the
moment of approval, by the transition service, per task. An edit would therefore not be deferred to a
firing boundary by that machinery; it would take effect on whichever task happened to be approved
next, which is the one property a staged edit exists to prevent.

So the honest answer is that it is not editable, and the refusal says the remedy: create a loop with
the declaration you want. That matches D-B's own wording, *declares at creation*.

Cost if this is wrong: an operator who chose wrong must archive the loop and make another, keeping
its tasks (`tasks.py:624-651` already handles offering a task to a successor loop). Cheap, and
reversible by a later change that adds the edit, which cannot be said of the opposite mistake.

## D4 — Supplying the field does not opt a job into being a loop, and is refused rather than ignored

`_loop_opts_in` (`jobs.py:103-105`) stays exactly as it is: purpose, stop time, queue-emptiness.
Adding the new field to it would let `POST /jobs {work_needs_evidence: false}` create a loop with no
stop condition, which every other path in the product refuses outright.

`agent-loops` pins the opt-in set with a scenario, and pins the consequence with a second one — *"an
update supplies a loop field for a job that has never been opted into being a loop → the request is
rejected"*. **Read it carefully: it says "an update".** The `PATCH` path enforces this; the `POST`
path does not, and `spec_document_id` is the standing precedent — `create_job` reads it only inside
the `if _loop_opts_in(...)` block, so a create that supplies it without opting in has it silently
dropped.

This change does **not** follow that precedent for its own field, and the difference is the point:
`spec_document_id` being dropped costs a loop its queue source, which the operator sees immediately
in a loop that never fills. A dropped `work_needs_evidence` is invisible until an approval writes —
or fails to write — to the operator's main branch, weeks later. So `POST /jobs` refuses it where the
job is not opting into a loop, naming what to supply instead.

Whether the same treatment should be extended to `spec_document_id` is **not** this change's
business, and it should not be swept in. Note it as a finding if implementing this makes it obvious.
## D5 — A second resolver takes the repository root; `integration_targets` itself is not modified

`integration_targets` stays a pure database query. The branch-tip answer needs `git rev-parse`, so
the resolution is a new function that takes the repository root, alongside the existing one:

```
integration_targets(session, task)          # accepted evidence. Unchanged. Pure DB.
merge_targets(session, task, root)          # what approval would actually merge.
```

`merge_targets` returns `integration_targets(...)` when evidence governs the task, and the task
branch tip when the task's loop declares it does not.

`integration_targets` has exactly four call sites, confirmed by grep rather than recalled
(`tasks.py:1074`, `requirement_gate.py:277`, `task_transition_service.py:773`,
`task_workspace.py:155`). **Three move to `merge_targets`; one stays, and the split is a decision:**

- `task_transition_service.integrate_task` and `requirement_gate._merge_situation` move. Both already
  hold a root, and both are asking what approval writes. `retry_integration` moves with the first,
  since it reaches the merge through it.
- `api/v1/tasks.task_integration_preview` **moves too, and this overrides its own docstring**, which
  says *"no git subprocess, no conflict probe"*. Those are two claims, and only the second is
  load-bearing: the objection recorded there is to the preview becoming a second gate. One
  `rev-parse` is not a gate, and a preview that reports no target for the one task shape whose target
  is not in the database would be silent about exactly the case this change exists to fix — the
  drawer would say "nothing will merge" beside an approve button that merges. The docstring is
  amended to say what is actually deliberate: no conflict probe. It needs a root, which it gets the
  same way `_merge_situation` does.
- `task_workspace._prerequisite_commits` **stays on `integration_targets`.** It builds what a *new*
  task branch is seeded with, and merging a prerequisite's branch tip into a successor's branch would
  carry work nobody accepted into a checkout an agent is about to write in. The accepted-evidence
  answer is the conservative one and stays. An evidence-free loop's prerequisite work reaches the
  successor another way: the dependency gate holds a task until its prerequisites are approved,
  approval merges them into the main branch, and `_integration_base` cuts the successor's branch from
  that same main branch. **Rounds 2 and 3 should check that chain rather than take it from here** —
  it is the one place in this design where a decision rests on the interaction of three shipped
  mechanisms rather than on one line of code.

**F156 is adjacent and is not fixed here.** `integration-preview`'s `will_merge` is
`bool(main_branch and targets)` and answered `true` for a task the gate refused. Renaming it is a
one-word repair in a different requirement's territory; this change only stops the preview lying by
*omission* about loop tasks.

## D6 — What the merge target actually is, and what happens when there is none

```
branch = worktrees.task_branch_name(task.id)          # agentweave/task/<id>
tip    = git rev-parse --verify refs/heads/<branch>   # one commit sha, or nothing
```

`Target(commit_sha=tip, branch=branch, evidence_id=None, requirement_id=None, task_id=task.id)`.

The three optional fields are `None` because there is no evidence row to point at, and `Target`'s own
docstring says they exist so a refusal can name the evidence it is waiting on. A refusal about
unaccepted evidence cannot arise for a target that came from a branch, so nothing reads them.

Exactly one target, never a list. A task has one branch by construction; the per-branch reduction in
`integration_targets` exists because *evidence* can name commits on several.

**No branch, or a branch that does not resolve** → no target, and `integrate_task` records
`SKIPPED` with a new reason:

> `NO_TASK_BRANCH = "this task has no branch of its own, so there is nothing to merge"`

Terminal, and classified as such by D7. It covers a grandfathered task, a read-only agent's task, and
a task whose branch was deleted by hand. It deliberately does **not** fall back to the agent branch.

**A branch whose tip is already in the main branch** needs no new constant. `integrate` asks
`is_reachable_from` before it asks anything about the working tree, and records `ALREADY_INTEGRATED`
naming the commit and the target. That is the true statement, and it is already written.

**An evidence-free loop task whose branch has one commit that is the base itself** — the turn changed
nothing, `snapshot_worktree` returned `None`, and the branch tip is the main branch's own commit.
`ALREADY_INTEGRATED` again, correctly: the tip is reachable from the target.

## D7 — Retryability is classified at the source, not string-matched in the browser

A single mapping in `task_integration`, beside the reason constants it classifies, and a predicate
the API calls:

| Reason | Retryable | Why |
|---|---|---|
| `CHECKOUT_DIRTY` | yes | the operator commits or stashes, then retries — the sentence says so |
| `CHECKOUT_ELSEWHERE` | yes | the operator switches branch, then retries |
| workspace unavailable | yes | transient; the directory can come back |
| `FAILED` (any reason) | yes | the merge was clean at approval, so the world moved; it can move back |
| `NO_MAIN_BRANCH` | no | the settings save re-attempts (`projects.py:522`); a button here would race it |
| `NOT_A_REPOSITORY` | no | nothing an operator does on this screen changes it |
| `NOTHING_TO_MERGE` | no | after `approval-refuses-unaccepted-evidence`, this means no commit was ever recorded; accepting evidence already re-attempts by itself |
| `NO_TASK_BRANCH` | no | the branch does not exist and retrying cannot make one |
| `ALREADY_INTEGRATED` | no | it is in; there is nothing to repeat |

The default inverts. Today an unrecognised reason gets a button; here an unclassified reason gets
none, because this change adds a reason and the failure mode being fixed is precisely a button
appearing on a reason nobody thought about. A skip whose reason is not in the table is not retryable
until somebody decides it is.

**The classification travels on the integration row**, as a `retryable` boolean in
`_integration_view` (`tasks.py:1090-1119`), which is the one shape both the read route and the retry
route return. The UI renders the button from it and deletes its `NO_MAIN_BRANCH` string constant.

**The `retry` route is not gated on it.** It stays available to the operator and to agents for any
approved task, per the shipped requirement's *"Retrying SHALL be available to the operator and to
agents, and SHALL be refused for a task that is not approved."* This change is about what is
*offered*, not about what is permitted — and a retry against an unretryable reason is harmless: it
appends a row saying the same thing. Narrowing the route would breach the requirement it is meant to
satisfy.

## D8 — The gate sees what will merge, which is one change, not two rules

`requirement_gate._merge_situation` builds `accepted` from `integration_targets`. It becomes
`merge_targets`, and the field is renamed to what it now holds. Two consequences, both wanted, and
both falling out rather than being written:

1. `_check_mergeable` conflict-tests the branch tip before approval, so an evidence-free loop task
   that would not merge is refused with its conflicting paths named, exactly as an evidence-backed
   one is. Without this, break 1's fix would ship the one class of merge that has never been
   pre-checked.
2. `_check_unaccepted` refuses only when nothing else would merge (`if situation.accepted: advisory`).
   For an evidence-free loop task there is a target, so stray awaiting evidence produces an advisory
   rather than a refusal — which is right: approval merges something, so the refusal's own stated
   rationale is not met.

`_merge_situation` already returns `None` — never refusing — for a project with no main branch, an
unresolvable workspace, a non-repository, or a missing branch. All four remain reasons not to know
rather than reasons to refuse, and an evidence-free loop task in such a project approves exactly as
it does today.

## D9 — Naming

`work_needs_evidence`, on the column, the schema, and the `create_loop` parameter.

D4's instruction was to name it for what it means to the operator. This is the sentence an operator
would say: *does this loop's work need evidence before it can land?* Considered and rejected:
`requires_evidence` (reads as a constraint on the caller rather than a fact about the work),
`evidence_required` (same, and inverts oddly when false), `merge_source` (names the mechanism, which
is what D4 said not to do), `lands_without_evidence` (double negative at every call site).

## Tripwires

- **`approval-refuses-unaccepted-evidence` also MODIFIES *An integration that cannot proceed does not
  block approval*, and is not archived yet.** This change's MODIFIED must be written against **that
  change's text**, not against `openspec/specs/`. Archive order matters: C before D. If D is archived
  first, C's older sentence overwrites D's.
- **`test_release_happens_after_integration`** (`hub/tests/test_task_release.py:278`) observes that release runs after
  integration *directly*, because the merged sha could not discriminate it while the target came from
  a database row. After this change the ordering is load-bearing for real: releasing first snapshots
  a dirty tree onto the task branch and moves the tip past what the gate conflict-tested. That test
  must stay, and a second one should assert the tip is what the gate saw.
- **`Loop` has three `pending_*` columns and a `pending_edit_at` sentinel** whose stated invariant is
  "non-NULL iff at least one of the three is set". Adding a fourth editable field would break that
  invariant silently; D3's answer is that this field is not editable, which keeps it intact.
- **`hub/hub/mcp_server.py` may import only stdlib and fastmcp.** The new parameter is passed
  through `_job_effect` as a dict key; nothing is imported.
- **`hub/hub/api/v1/agents.py:960-975`** restates every job/loop tool's signature as prose in the
  agent's tool inventory. A new parameter that is not added there leaves the agent reading a
  signature the Hub no longer has.
- **Migration `0100` follows `0099`**, and the head assertions in `hub/tests/test_migrations.py` and
  `hub/tests/test_project_persistence.py` both move. Guard for a missing `loops` table the way
  `0033`/`0034` do — an upgrade from an early revision reaches `0100` with only that revision's
  tables.
- **The UI bundle is committed.** `cd hub/ui && npm run build`, then
  `py -3.11 scripts/refresh_ui_bundle.py`, and `hub/ui/src` and `hub/hub/static/ui` are committed
  together.

## Open question for rounds 2 and 3

**Attack the default.** D4's rationale is that no existing loop merges anything, so an evidence-free
default regresses nothing. That is true of *history* and says nothing about *tomorrow*: from this
change onward, approving any loop task in a project with a configured main branch writes to that
branch, including tasks whose loop only ever wrote notes — `snapshot_worktree` commits whatever the
turn left dirty, so "this loop produces no code" does not mean "this loop's branch has no commits".
D4's `raise_it_if` names one trigger (an existing loop path that merges today; there is none). The
question a later round should answer on its own evidence is whether the *first* approval in a project
that never asked for this is a surprise the operator would call a defect — and if so, whether the
answer is a different default or a louder statement at creation, rather than silence and a merge.
