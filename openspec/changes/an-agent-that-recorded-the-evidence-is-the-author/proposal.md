## Why

`F306` (severity A, `scripts/drive/FINDINGS.md`) was **measured on a live Hub** on 2026-09-09: agent
`r7af142d` recorded `record_evidence(task_id='task-930385ddb031', kind='implementation')`, the
operator walked the task `pending → in_progress → completed` by hand, the flow fired, and the flow
staffed **`r7af142d`** as the reviewer of its own code. Sequence 19 of that task's history is
`under_review → approved`, `actor_kind='run'`, `actor_agent='r7af142d'`. Nothing refused it and
nothing recorded that it happened.

The verdict is the operator's, taken in session on 2026-09-10 (`spec-queue/DECISIONS.md`, *"F306 and
F312, decided 2026-09-10 evening"*): **repair both defences, and count every evidence row regardless
of `review_state`.** This proposal does not re-litigate that. What it adds is what R1 measured.

### The hole, in one line

`agents_that_may_have_authored` (`hub/hub/task_transition_service.py:253-283`) is the union of
exactly three records — transitions, `assignee`, runs bound to the task. A fourth record exists and
is not a source: `requirement_evidence.actor`. On the arm where the **operator** completes the work,
all three legitimate sources are legitimately empty, the ladder gets `exclude=set()`, and the
function's own docstring has already ruled that value out.

The function's stated principle decides this: *"a record associating an agent with a task is
sufficient to exclude it, and a source's silence is not evidence that the agent did not work it."*
It was applied to three of four sources, and by its own standard the missing one is the **strongest**
— the other three are circumstantial (this agent moved it / holds it / ran about it), while an
`implementation` evidence row is the agent asserting *"this is my implementation of this task"*,
carrying the very commit the reviewer is then handed.

### What R1 measured, and what it changed

Four things were unverified when this change was queued. All four are now measured. The probe was a
throwaway pytest module against the real functions (`hub/tests/`, `py -3.11`), deleted afterwards;
every number below is its output.

**1. The ladder picks deterministically — and that makes F306 systematic, not a coin flip.**
`FINDINGS.md` recorded *"Unverified: whether ordering is deterministic"*, and `DECISIONS.md` flagged
it as R1's question. `_agents_that_are_free` (`hub/hub/scheduler.py:1025-1040`) orders the roster by
`Agent.name`, and rung 2 of `resolve_reviewer` returns the **first** candidate not excluded and not
already taken. Measured both ways round:

| agents created in this order | free pool returned | reviewer picked | picked again |
|---|---|---|---|
| `zz-probe`, `aa-probe` | `['aa-probe', 'zz-probe']` | `aa-probe` | `aa-probe` |
| `aa2-probe`, `zz2-probe` | `['aa2-probe', 'zz2-probe']` | `aa2-probe` | — |

Insertion order does not decide; name order does, and repeating the call returns the same agent. So
an author whose name sorts first among the free agents is selected as its own reviewer on **every**
firing for **every** task it authored — not occasionally. The measured live case (`r7af142d`, pool of
two) is the general case, and severity A is reinforced rather than merely retained.

**2. The defect reproduces at unit level, with the attribution the code claims.**
An operator-completed task carrying one agent-authored evidence row:

```
ATTRIBUTION:      CompletionAttribution(recorded=True, actor_kind='operator', agent=None)
EXCLUSION TODAY:  set()
LADDER PICKS:     aa-author-probe        <- the agent that recorded the evidence
```

**3. The obvious shape of the guard's fallback is refuted by measurement.** `FINDINGS.md` offered
*"have `_guard_author_is_not_reviewer` fall back to `agents_that_may_have_authored`"*. It cannot:
`enter_selected_task` writes `task.assignee = <reviewer>` before it transitions the task to
`under_review` (`hub/hub/scheduler.py:816`), so by the time the reviewer records its verdict the
assignee term of that union **is the reviewer**. Measured at approval time, with `AUTHOR` holding the
evidence row and `REVIEWER` staffed by the flow:

```
UNION AT APPROVAL TIME (assignee=reviewer):  {'zz-reviewer-g'}
REVIEWER IN UNION: True
```

A fallback to the union would refuse every flow-staffed review of an operator-completed task — the
exact path this change exists to make work. `DECISIONS.md` had already worded it correctly (*"The
guard falls back to the **evidence actors** when there is no completer"*); this is the measurement
that shows why the wording is load-bearing rather than casual.

**4. Scoping the fourth source by evidence `kind` is both unimplementable and unnecessary.**
`FINDINGS.md` proposed scoping *"by `kind` so a reviewer's own evidence does not exclude the reviewer
that produced it"*. There is no vocabulary to scope by: `record_evidence`'s own contract says
`kind` is *"Not a closed list; use a word that describes it"* (`hub/hub/mcp_server.py:1365-1366`), and
`requirement_evidence.record` stores whatever arrives. And the case it was defending against is not
on the product's path — `_briefing_evidence_lines` returns nothing at all for a review turn, with the
comment *"A reviewer records a verdict, not evidence for work it did not do"*
(`hub/hub/scheduler.py:2103-2104`). The residue is stated in `design.md` D5 rather than designed
against.

### The ladder half is required by a requirement that already shipped

`agent-flows` already states: *"The Hub SHALL NOT resolve, as a task's reviewer, an agent that could
not record a verdict on it. An agent is barred from judging work it completed, so naming it would
produce a review refused on arrival; the resolution SHALL exclude it rather than discover the refusal
afterwards"* (`openspec/specs/agent-flows/spec.md:221-224`). Once the guard refuses an evidence
author, that shipped sentence **compels** the ladder to exclude it too. So the two halves are not a
preference for belt and braces: repairing only the guard breaches an existing requirement, and
repairing only the ladder leaves the silent failure standing. The corpus reaches the operator's
verdict independently.

## What Changes

- A **fourth source** of authorship: the agents that recorded evidence against the task. Its own
  function, `agents_that_recorded_evidence_for`, keyed on `actor_kind = 'agent'` and a non-empty
  `actor`, called by `agents_that_may_have_authored`. It is its own function because it has a second
  consumer that must **not** see the other three terms (below) — which is R1's answer to the third
  question `DECISIONS.md` left open.
- **`_guard_author_is_not_reviewer` falls back to that source alone** when no agent is recorded as
  completing the task. Not to the union: see measurement 3.
- **Every evidence row counts, regardless of `review_state`.** The operator's verdict, unchanged
  here: an agent whose evidence was rejected, or is still awaiting review, still authored the work.
- **No migration.** `RequirementEvidence` already carries `task_id`, `actor` and `actor_kind`, so
  the fourth source mirrors `agents_of_runs_bound_to` exactly.
- **No change to what an operator may do.** `POST /spec/evidence` records an operator's evidence as
  `Actor(kind="operator")` (`hub/hub/api/v1/spec.py:801-833`), and the `actor_kind` filter is what
  keeps `F306`'s own *"a truly untouched task is reachable and is not affected"* case working: an
  operator may still supply the evidence naming a commit and have any agent review it.

## Impact

- **Capabilities:** `agent-flows` (two MODIFIED requirements — the source enumeration behind
  claimability, and the operator-finished staffing arm), `task-lifecycle-governance` (one MODIFIED
  requirement — the self-approval guard gains its fallback).
- **Source:** `hub/hub/task_transition_service.py` (the new function, the union, the guard). No
  other module changes: both call sites named in the verdict — `hub/hub/scheduler.py:625`
  (`task_is_claimable_by`) and `:1574` (the review-staffing arm) — call
  `agents_that_may_have_authored` and are fixed by fixing it. **Python only; no UI bundle rebuild.**
- **Blast radius on the existing suite: measured, and it is zero.** The union and the guard fallback
  were prototyped in the working tree and 15 test files were run against the prototype — the 7 that
  seed evidence through `hub/tests/review_evidence.py` (whose default is `actor_kind="agent"`), plus
  the 8 review, guard and staffing suites. **210 existing tests, all passing.** The prototype was
  then reverted; nothing in it is committed. The reason nothing breaks is worth writing down: those
  tests complete their tasks through `_completed_by`, an *agent* completion, so `attribution.agent`
  is set and the union path is never reached; and where the union path *is* reached, the evidence
  actor is already in `agents_that_worked`. The verdict predicted one affected test file; the
  measurement says no existing test's expectation changes, which is a stronger claim and is why the
  new coverage in `tasks.md` is mutation-checked rather than trusted.
- **New behaviour an operator can see:** a project whose only other agent is the evidence author now
  reports *"could not staff this step"* on a review it used to staff. That is the cost the verdict
  priced knowingly: *"the cost of excluding an agent that did nothing is a review the flow reports
  it could not staff, which the operator sees and resolves; the cost of including an agent that
  wrote the work is a self-approval nobody sees."*
- **Not in scope:** `F167` (B), the adjacent residual on the same repair, which fails closed; and
  any change to who may *decide* evidence (`requirement_evidence.may_accept`).
