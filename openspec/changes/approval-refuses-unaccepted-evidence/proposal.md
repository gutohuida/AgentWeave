## Why

```python
targets = await task_integration.integration_targets(session, task)
if not targets:
    return _record(IntegrationResult(outcome=SKIPPED, reason=NOTHING_TO_MERGE))
```

`hub/hub/task_transition_service.py:768-775`. The task is already `approved` by the time this line
runs, the transition row is already staged, and the sentence recorded is *"no accepted evidence
names a commit, so there is nothing to merge"* — while the commit sits in the database, on a branch,
in a `RequirementEvidence` row whose `review_state` is `awaiting`. Nobody ever accepted it, because
`Agent.can_accept_evidence` is `default=False` and **no code path anywhere confers it**: all four
`Agent(...)` construction sites omit it (`agents.py:665`, `:1593`, `:1704`,
`session_sync.py:95-105`), there is no YAML key for it, and the single writer is an operator PATCH
(`agents.py:2007-2012`).

So in a project the operator never hand-configured, the flow's terminal state means "approved" and
never means "shipped". That is **F122**, and it is the terminus of every drive of the loop so far.

The product anticipated this exactly and built an escape hatch that cannot open. The agent retry
route's own docstring (`agent_actions.py:315-319`):

> Reachable by an agent because one skip reason — nothing accepted names a commit — is one an agent
> can genuinely clear, by having a granted peer accept its evidence.

There is no granted peer. There is no route that makes one.

### This breaches a shipped requirement, and is not excused by the one that would excuse it

`task-lifecycle-governance` — **Approval integrates the approved work**:

> The transition into `approved` SHALL merge the approved work into the project's configured main
> branch, in the same operation that records the transition. […] a lifecycle whose terminal state
> carries no such meaning cannot answer whether anything it approved was ever shipped.

`task-lifecycle-governance` — **An integration that cannot proceed does not block approval** — is
the requirement that excuses a non-merging approval, and it excuses it by a **closed enumeration**:

> Integration cannot be attempted when the project has no configured main branch, when the project
> is not a repository, when the primary checkout has uncommitted changes to tracked files, or when
> the primary checkout is not on the main branch.

*"Nothing accepted names a commit"* is not in that list, and the work in question is not
unmergeable — it is unjudged. Today's behaviour breaches the first requirement and is excused by
neither.

### The operator's decision, taken 2026-08-30

**D-A: approval is REFUSED while evidence sits unaccepted.** Chosen over seeding a granted agent per
project, over a flow granting its resolved reviewer per task, and over leaving the machinery alone
while merely surfacing "approved but unmerged" — the last rejected because it leaves the breach
standing. Consequence, stated plainly by the operator: **a default project's first flow stalls
loudly rather than finishing silently wrong.** That is the intent. The grant becomes load-bearing,
so the refusal must name the remedy.

**Critical scoping constraint, and it is the whole design.** The refusal fires only where evidence
*exists* and is *unaccepted*. A task with no evidence at all stays approvable, or every research,
docs and decision task wedges. That is `_check_mergeable`'s own written rule
(`requirement_gate.py:161-163`): *"Approval must never be blocked by the absence of an integration,
only by one that would fail."* Evidence recorded-but-unaccepted **is** one that would fail.

### The half nobody would find by reading the refusal

Refusing is not enough, because **the natural repair sequence still merges nothing.** Both evidence
decision routes — `spec.py:864-891` (operator) and `agent_actions.py:1164-1201` (granted agent) —
call `requirement_evidence.decide`, commit, and return. `hub/hub/api/v1/spec.py` contains zero
references to integration. So for the approved-and-unmerged tasks that already exist, and for the
mixed case this change deliberately allows through, an operator who does exactly what the refusal
asks — accept the evidence — changes nothing on the main branch. Restating `approved` is a
deliberate no-op, so approving again cannot merge it either.

The product already solved this exact shape once, for a different cause. `projects.py:522` calls
`_integrate_what_was_waiting_for_a_branch` when the operator names a main branch, under the
requirement **Naming the main branch attempts the integrations that wanted one**, whose stated
reason is:

> Discharging that instruction at the moment the operator follows it is what makes the sentence
> true; leaving it undischarged means the system asked for something and then ignored it.

This change adds the sibling for acceptance. It is not an extra: **D3's "allow the mixed case"
answer below is only safe because this half exists.**

## What Changes

Two halves, one change, because either alone leaves the loop broken.

### 1. A new refusal beside `unmergeable`

`GateRefusal` (`requirement_gate.py:66-124`) gains a fourth list, `unaccepted`, in exactly the shape
`unmergeable` already has and for exactly its stated reason — *"not 'this is unproven' but 'this
cannot go in'"*. It is counted by `refuses`, carried by `to_dict()`, and given a sentence in
`detail()`. **No surface change is needed**: `main.py:406-415` serialises `refusal.to_dict()` for
every `TransitionRefusedError`, and the UI reads `message` off the structured detail
(`ui/src/__tests__/taskIntegration.test.ts`). The refusal reaches the operator's board and the
agent's `update_task` alike, through the one path both already use.

The predicate, stated as what would change if it were satisfied:

> Refuse where the task has **awaiting** evidence naming a git commit, and **no accepted** evidence
> names one.

Every clause of that is load-bearing, and D2/D3/D4 below defend each.

Placement: a new `_check_unaccepted`, called from `requirement_gate.evaluate` beside
`_check_mergeable`, sharing its preconditions. Rigor-independent for the same reason
`_check_mergeable` is — `DEFAULT_SPEC_RIGOR = "sketch"` blocks nothing, so anything placed behind
rigor is absent from a default project, which is how F122 survived.

The awaiting rows are found by a new `task_integration.awaiting_targets`, the *same query* as
`integration_targets` with `ACCEPTED` swapped for `AWAITING`. One query shape, so the refusal fires
exactly when acceptance would produce a target that is not there now (D5).

### 2. Accepting evidence attempts the integration that wanted it

A new `task_integration.tasks_skipped_for_want_of_accepted_evidence`, the sibling of
`tasks_skipped_for_want_of_a_main_branch` (`task_integration.py:343-390`) — approved tasks linked to
this evidence's requirement whose **most recent** integration attempt skipped with
`NOTHING_TO_MERGE`. Called from both decision routes, after the commit, wrapped so a git failure
never undoes the acceptance. Only that skip reason, on the same D8 reasoning the branch sibling
records: accepting evidence says nothing about a dirty checkout.

### What is deliberately not in scope

- **Break 7**, the "Try again" button that skips identically — queued with change D.
- **Splitting `NOTHING_TO_MERGE` into its three worlds.** After this change the awaiting world
  mostly stops reaching it; the rest is F124's, which is change D's.
- **Conferring the grant anywhere.** Explicitly rejected by the operator.
- **Rejected evidence.** It has been judged. Refusing on it would wedge a task whose author must now
  record better evidence, and the author cannot un-reject.

## Impact

- Specs: `task-lifecycle-governance` — one ADDED refusal requirement, one ADDED
  acceptance-triggers-integration requirement, one MODIFIED enumeration.
- Code: `hub/hub/requirement_gate.py`, `hub/hub/task_integration.py`,
  `hub/hub/api/v1/spec.py`, `hub/hub/api/v1/agent_actions.py`.
- No UI change, no migration, no new column.
- **Behaviour change an operator will notice**: in a project with no granted agent, a flow that
  records evidence now stalls at approval instead of finishing with nothing merged. That is D-A,
  chosen deliberately, and the refusal names both ways out.
