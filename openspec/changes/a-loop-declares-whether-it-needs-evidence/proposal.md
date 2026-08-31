## Why

```python
if spec_document_id is not None:
    raise HubAPIError(
        400,
        "a loop that declares a specification document is a flow: call create_flow instead, ...",
    )
```

`hub/hub/mcp_server.py:665-672`. A loop is **documentless by definition** — that is the sentence
that separates it from a flow, and it is deliberate. Follow it forward:

```
loop has no spec document  →  the project mints no SpecRequirement rows for it
  →  record_evidence("FR-1") answers 404 "this project has no requirement FR-1"
                                                        (agent_actions.py:1041-1044)
  →  no evidence  →  no accepted footprint  →  integration_targets() == []
  →  "no accepted evidence names a commit", permanently, for every loop task ever
```

`integration_targets` (`task_integration.py:211-227`) is the sole producer of a `Target`, and
`Target` is the sole input to the only `git merge` into a project's main branch in the whole tree
(`task_integration.py:300-372`, the merge itself at `:348-360`). Its four conditions are conjunctive and the first is a
`TaskRequirementLink` row. A loop has no requirements to link.

**F124 said loop tasks *happen to* lack requirement links. The truth is stronger: the definition of
a loop excludes it from the only mechanism that reaches the main branch.** Every loop task that has
ever been approved recorded `outcome='skipped'`, `reason=NOTHING_TO_MERGE`, and left its work on a
branch. That is break 1 of the seven
(`openspec/explorations/2026-08-30-why-a-flow-cannot-land-its-work.md`).

### The button offered on top of it

`TaskIntegrationNote.tsx:88-101` renders "Try again" for **every** non-`merged` outcome except one
whose reason contains `no main branch set`. So the F124 terminus does get a button; pressing it
calls `POST /tasks/{id}/integrations/retry`, which re-runs `integrate_task`, which asks
`integration_targets` the same question and gets the same empty list, and appends a second identical
skip. That is break 7, and it breaches a shipped requirement — `task-lifecycle-governance`, *An
integration that was skipped can be attempted again*:

> Where a skip names a cause the operator can put right, it SHALL point at the remedy that works…
> An instruction that fails silently is worse than none, because it spends the operator's confidence
> as well as their time.

The UI decides retryability by string-matching one reason. Every reason it does not recognise gets a
button, so the default is "offer it", and the two reasons that are genuinely terminal — nothing to
merge, and a commit already in the target — are the ones that get it.

### The operator's decision, taken 2026-08-30

**D-B: a loop declares at creation whether its work needs evidence.** Chosen over loops never
merging, over implicit requirements, and over retiring loops.

> When a loop declares its work does not need evidence, its tasks must be able to land without the
> requirement/evidence chain; when it declares that it does, the existing chain applies unchanged.

Two follow-on decisions were pre-authorised with their rationale:

**D4 — the default is that a loop's work does NOT need evidence.** *"A loop today can never merge
anything at all, so defaulting to evidence-free is what makes the feature work and regresses
nothing — no existing loop is landing work that could break."*

**D5 — what an evidence-free loop task merges is the task's own branch,
`agentweave/task/<task_id>`,** because `work-is-isolated-per-task` guarantees it carries that task's
work and nothing else. Emphatically **not** the agent branch `agentweave/<agent>`, which carries
every task that agent ever touched — that is F58 exactly, severity A.

D5 attached a condition: **verify the per-task guarantee holds for LOOP tasks specifically**, since
that change was written about flows. It does, and the verification is in design D1 — the workspace
scheme is keyed on `Task.workspace_scheme`, never on whether a task belongs to a loop or a flow.

## What Changes

Three parts. The first is the declaration, the second is what it makes possible, the third is break 7
— and the third is not optional garnish: this change adds a *new* terminal skip reason, so shipping
it without fixing the button would put a second unclearable "Try again" on screen.

### 1. A loop declares whether its work needs evidence

`Loop` gains one nullable Boolean column, `work_needs_evidence`; `create_loop`, `POST /jobs` and the
operator's own job form all gain the matching optional control. Nullable, with **NULL meaning "the product's current default"** rather
than a stored copy of today's answer — the identical reasoning `Loop.control` already states
(`models.py:1405-1412`): *"a row storing today's default would keep saying it after the default
moved."*

**Evidence always governs a flow**, and the default says so. `Loop` is the row for a flow as well
as a loop — `spec_document_id` is the only thing that separates them — so "the product's current
default" has to be *evidence governs a flow, and does not govern a documentless loop*. A flat default
of "no evidence needed" would resolve that way for every flow too, and every flow task would merge
its branch tip instead of the commit its accepted evidence names, retiring both F58's protection and
`approval-refuses-unaccepted-evidence` in the process. Round 2 found that; design D10 has the
derivation. The operator's declaration, where one was made, still wins over the default.

**And evidence governs any task that is actually wired into the evidence chain, flow or not.** A
documentless loop's task created with `requirement_ids` gets real requirement links, can record
evidence — `record_evidence` resolves an identifier against the *project's* index and never consults
the task's loop — and **merges today**, through the ordinary route, with no change at all. So the
premise D4's default rests on, *"a loop today can never merge anything at all"*, has a counterexample,
and a default that stopped at "is this a flow" would silently switch that task to its branch tip.
Worse than substituting one commit for another: evidence recorded by another task against a shared
requirement is in scope for this task's integration by design, and a per-task branch tip cannot carry
it, so a commit that merges today would stop merging with nothing recording the loss. Round 3 found
that; design D11 has the derivation. **The branch tip is therefore the default for exactly one
population — a task on a documentless loop with no requirement link of any kind**, which is the
population this proposal's Why describes and the only one for which nothing is being displaced.

The declaration is made **at creation and never edited**. That is D-B's own word — *declares at
creation* — and it is also the honest engineering answer: the loop's answer decides what approval
writes into the operator's main branch, and a mid-flight edit would change what a queue that is
already half-approved does with the rest of itself. A `PATCH` supplying it is refused with a
sentence saying so. This deliberately does **not** join the three pending-edit fields
(`pending_purpose`, `pending_stop_at`, `pending_stop_when_queue_empties`).

Supplying the field **does not opt a job into being a loop.** The opt-in set stays the three fields
`agent-loops` enumerates, and the shipped rule *"A loop field cannot be set on a job that is not a
loop → the request is rejected"* covers the new field unchanged.

### 2. An evidence-free loop task merges its own branch

Where a task belongs to a loop whose declaration is "no evidence needed", the merge target is
resolved from the task's branch tip instead of from accepted evidence.

The commit, never the branch: `git rev-parse --verify refs/heads/agentweave/task/<id>` produces one
sha, and that sha is what `integrate` merges, so the module's first rule — *merge a commit, never a
branch* — is upheld rather than excepted. `commits_riding_along` still reports what else came with
it, and `IntegrationResult.rode_along` still surfaces it, so F58's safety net is unchanged.

This is the change the transition service already anticipated in writing
(`task_transition_service.py:606-613`), where release is ordered after integration:

> The order is defence against the change that would make it matter — **resolving the target from
> the branch tip instead** — which is the exact shape of F58.

That defence now becomes load-bearing rather than theoretical, and `test_release_happens_after_integration`
already guards it.

Three shapes get a stated answer rather than a merge:

- **No branch** — a grandfathered task (`workspace_scheme == 'agent'`), a read-only agent's task, or
  a project that is not a repository never had a task branch cut. There is nothing safe to merge and
  the agent branch is not a substitute. A new skip reason names this, and it is terminal.
- **A branch whose tip is already in the main branch** — no new constant needed: `integrate`'s
  existing `ALREADY_INTEGRATED` guard asks the repository and says so.
- **A loop that declares its work DOES need evidence** — unchanged in every respect. Its tasks can
  still carry `requirement_ids` individually (`TaskCreate.requirement_ids`, reachable through
  `initial_tasks` and through `create_task`), so this is a coherent declaration and not a promise the
  product cannot keep.

The drawer moves with it. `integration-preview` resolves its targets the same way, so it stops
answering "nothing will merge" beside an approve button that merges. It still runs no conflict probe.

The gate moves with it too. `requirement_gate._merge_situation` resolves what *would* merge, so an
evidence-free loop task gets the same pre-approval conflict check every evidence-backed task gets,
and `_check_unaccepted`'s "nothing else would merge" arm answers correctly for it without a second
rule being written.

### 3. Retry is offered only where retrying could change the answer

The Hub says whether an attempt is worth repeating; the UI stops guessing from prose. Every skip
reason is classified at its source in `task_integration`, the classification rides on the integration
row in the API response, and `TaskIntegrationNote` renders the button from that field instead of
string-matching `no main branch set`.

Retryable: a dirty checkout, a checkout parked elsewhere, an unavailable workspace, and an outright
merge failure — each is a condition an operator changes and then re-attempts. Not retryable: no main
branch (which points at the setting, whose save already re-attempts), not a repository, nothing to
merge, no branch for the task, and already integrated.

### What is deliberately not in scope

- **Making a loop's briefing mention any of this.** `_briefing_evidence_lines` (`scheduler.py:1915`)
  already says nothing when a task has no requirement links, which is every evidence-free loop task,
  so nothing false is said today. What an agent would gain from being told "your branch is what
  lands" is a claim about the *briefing*, which is change A's subject, and it should be argued there
  on its own evidence rather than smuggled in here.
- **Splitting `NOTHING_TO_MERGE` into the three worlds §4 of the exploration names.** One of the
  three is removed by this change and one was removed by `approval-refuses-unaccepted-evidence`;
  what remains is a single true statement about a task that produced no commit anybody is waiting on.
- **Editing the declaration after creation**, and the pending-edit machinery that would need.
- **F154, F155, F156.** Filed, reproduced, and outside this change's subject.

## Impact

- Specs: `agent-loops` — one ADDED requirement. `task-lifecycle-governance` — one ADDED requirement
  for the branch-tip target, one MODIFIED skip enumeration, one MODIFIED retry requirement.
  `task-dependencies` — one MODIFIED requirement, *A task's checkout carries the work it depends
  on*, added in round 3. Its opening sentence already requires a successor's checkout to carry its
  prerequisites' work *"whether or not that work reached the project's main branch"*; its mechanism
  sentence names accepted evidence as the source, because evidence was the only source when it was
  written. Without that amendment this change would breach the requirement for every evidence-free
  loop task.
- Code: `hub/hub/db/models.py` (one column), a new migration `0100`, `hub/hub/schemas/jobs.py`,
  `hub/hub/api/v1/jobs.py`, `hub/hub/task_integration.py`, `hub/hub/task_workspace.py`,
  `hub/hub/task_transition_service.py`,
  `hub/hub/requirement_gate.py`, `hub/hub/api/v1/tasks.py`, `hub/hub/mcp_server.py`,
  `hub/hub/api/v1/agents.py` (the tool-inventory sentence for `create_loop`),
  `hub/ui/src/api/tasks.ts`, `hub/ui/src/components/tasks/TaskIntegrationNote.tsx`,
  `hub/ui/src/api/jobs.ts` and `hub/ui/src/components/jobs/JobForm.tsx` — the operator's own
  loop-creation form, added in round 2 because without it the declaration is an agent-only control
  over what the operator's main branch receives.
- A UI change, so the bundle is rebuilt and `hub/hub/static/ui` is committed with `hub/ui/src`.
- **Behaviour change an operator will notice, and it is the whole point:** in a project with a
  configured main branch, approving a loop task now merges that task's branch into it. Before this
  change, approving a loop task merged nothing, ever. A loop that only ever wrote notes still has
  commits on its branch — `snapshot_worktree` commits whatever the turn left dirty — so "this loop
  produces no code" is not a reason it will not merge. An operator who does not want that says so at
  creation, and D4 chose which way round the default points.
- **A task cannot be attached to a loop after it exists** — round 2 said it could, reading the
  schema's "write-once" comment rather than the route, and round 3 corrected it (design D13).
  `PATCH /tasks/{id}` refuses `loop_id` unconditionally whenever it is supplied, without consulting
  the current value, and the only four writes to the column are all at creation or restricted to
  flows. So the one route by which a task carrying requirement links reaches an evidence-free loop
  is a single `create_task` call supplying both — and that is closed on its own terms by the default
  above (design D11), not by narrowing `loop_id`.
- **A prerequisite's work reaches its successor without depending on the main-branch merge having
  succeeded.** `_prerequisite_commits` asks the same question, restricted to prerequisites that are
  already `approved`. Without it, this change would create the first task shape whose prerequisite
  work has only one route to a successor — the main branch — while `integrate` skips on an ordinary
  dirty checkout and approval stands regardless. The cost, stated rather than discovered: a
  prerequisite branch tip that will not merge cleanly refuses the successor's turn instead of being
  silently absent. Design D12, the decision round 2 left open.
