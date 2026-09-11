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
afterwards"* (`openspec/specs/agent-flows/spec.md:220-222`). Once the guard refuses an evidence
author, that shipped sentence **compels** the ladder to exclude it too. So the two halves are not a
preference for belt and braces: repairing only the guard breaches an existing requirement, and
repairing only the ladder leaves the silent failure standing. The corpus reaches the operator's
verdict independently.

### What R2 changed: the enumeration of call sites was wrong, and the corpus already forbids the gap

R2 re-derived this change from the code without reading R1's argument first, and the four claims it
was sent to break came back **three survived, one false**. The false one is not a detail: it is the
Impact section's *"no other module changes"*.

**R2-A — the proposal as written breaches a requirement that already shipped.** `POST /agent/trigger`
asks `review_dispatch_refusal` (`hub/hub/api/v1/agent_trigger.py:452-490`) whether a hand-named
reviewer may be dispatched, and that function's only authority check is
`agent_that_completed(...) == reviewer`. On an operator-completed task there is no completer, so it
permits. `enter_selected_task` then permits too — `_guard_reviewer_is_not_the_author` compares the
same completer. The review turn *runs*, and only when the reviewer records its verdict does the new
fallback refuse it. `task-lifecycle-governance` has shipped the rule against exactly this since the
dispatch paths were unified:

> A review that cannot be staffed SHALL be refused **before a turn is started**, and the refusal
> SHALL be the one the attempted staffing produced rather than a restatement of it. Refusing after a
> turn has begun is not sufficient: the cost of the turn has already been paid and the reviewer's
> conclusion has nowhere to go.
> (`openspec/specs/task-lifecycle-governance/spec.md:1719-1722`)

And the state it leaves behind is one the product is specified **not** to recover: the task sits in
`under_review` held by an agent that no transition on it names, which
`task-lifecycle-governance:384-389` says SHALL be reported as a review genuinely in progress. So the
wedge is permanent and invisible, which is the shape of `F45`, `F70` and `F161` — a review that ran
and whose verdict has nowhere to go. R2 adds `review_dispatch_refusal` to the change (§3.5, §4.9)
and the MODIFIED requirement that carries it.

**R2-B — there is a *third* reviewer resolution, and it recomposes the exclusion.**
`run_divergence._answer_failed_review` (`hub/hub/run_divergence.py:374-421`) answers a review that
was staffed and then said nothing. It builds its own exclusion — the silent reviewers, this run's
agent, and `agent_that_completed` **if it names one** — and hands it to the shared ladder. On an
operator-completed task the author term is empty, so the ladder may resolve an agent that worked the
task. After this change it may resolve the **evidence author**, whose verdict the new guard then
refuses: exactly what `agent-flows:220-222` forbids the Hub to resolve, and which R1 cited as the
reason the ladder half is compelled. The same sentence compels this call site.

This is also a defect **today**, before this change, and R2 filed it as `F316 (A)`: an agent that
worked an operator-completed task can be resolved as the replacement reviewer after a silent review
and approve the work, because both guards permit where no completer is recorded. `F142` widened the
exclusion on two call sites and never reached the third. `task_is_claimable_by`'s own comment says
why that matters — *"two compositions of the same three terms are free to drift"* — and there are
three compositions, not two. Folding the repair in here rather than leaving it to `F316` is the
cheaper order: the fix is to make that call site *call* the union instead of recomposing it, which
picks up this change's fourth source for free.

**R2-C — D5's argument was right and its evidence was thin.** R1 justified *not* scoping by evidence
`kind` from one docstring in `mcp_server.py`. Two stronger facts were available and neither was
cited. First, a partial vocabulary **does** exist — `db.models.EVIDENCE_KINDS`, six values — and
nothing validates against it; `F306`'s own live reproduction recorded `kind='implementation'`, which
is not one of the six, and it stored fine. R1's *"there is no vocabulary to scope by"* is therefore
false as written while its conclusion holds. Second, the corpus forbids closing it: *"The set of
kinds SHALL be open to additions"* (`requirement-traceability:123-125`) and *"Constrained values
SHALL be constrained identically on both surfaces, and **open ones SHALL stay open**"*
(`agent-capability-plane:850`). Scoping by `kind` is not merely unimplementable; it is
prohibited. `design.md` D5 now says so, and notes that `review_record` — the one of the six kinds a
reviewer would plausibly use — appears nowhere in the product but the tuple.

**R2-D — the three surviving claims.** *No existing test's expectation changes*: R1 measured 15
files and 210 tests; R2 re-measured against the **whole** Hub suite with the prototype applied (§see
tasks 4.8). *The guard's fallback must be the evidence term alone*: re-derived from the code rather
than from R1's quoted probe — `enter_selected_task` writes `task.assignee = agent` and only then
transitions, and `apply_transition` runs its guards **before** the status change, so at the moment
`_guard_author_is_not_reviewer` reads the task the assignee is the reviewer by construction, not by
coincidence of timing. A union fallback refuses every flow-staffed review of operator-completed
work. *`scheduler.py:625` and `:1574` need no edit*: both call the union; confirmed by reading.

**What R2 did not measure, stated so R3 does not inherit it as settled.** The whole-suite run above
was made against a prototype of §1–§3.4 only. The two call sites R2 adds — §2.4 and §3.5 — were
found by reading and are **not** in any prototype anyone has run; their blast radius is unmeasured,
and `tasks.md` 4.8 says so rather than letting the 210-test number spread to code it never touched.
`F316`'s own reachability argument is likewise derived from the code and has not been driven.

**R2-E — one residue R1 did not name, now in `design.md` D7.** This change leaves the
*agent-completed* arm exactly as it was, by design: where agent `A` is recorded as completing a task,
the exclusion is `{A}` alone, so an agent `B` that recorded evidence for that task may still be
staffed to review it and its approval is not refused. That is outside `F306`'s scope and outside the
operator's verdict, and it is the obvious next question a reader will ask.

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

- **Capabilities:** six MODIFIED requirements, three of them added by R2. `agent-flows`: the source
  enumeration behind claimability, the operator-finished staffing arm, and — **R2** — the resolution
  that answers a review which gave no verdict, whose second pass must exclude the author by the same
  determination as the first. `task-lifecycle-governance`: the self-approval guard gains its
  fallback, and — **R2** — the dispatch requirement gains the refusal that keeps it *before* a turn
  is started, while the flow-cannot-staff requirement loses a sentence that becomes false (*"on a
  task with no recorded completion any agent may be dispatched"*). No requirement is ADDED, REMOVED
  or RENAMED, and every MODIFIED body carries its shipped scenarios unchanged plus the new ones.
- **Source:** three modules, not one (**corrected by R2 — R1 claimed "no other module changes"**).
  `hub/hub/task_transition_service.py` (the new function, the union, the guard);
  `hub/hub/api/v1/agent_trigger.py` (`review_dispatch_refusal`, so the operator's route refuses the
  evidence author *before* a review turn is started rather than after); and
  `hub/hub/run_divergence.py` (`_answer_failed_review`, the third reviewer resolution, which
  recomposes the exclusion from the completer alone). The two call sites named in the verdict —
  `hub/hub/scheduler.py:625` (`task_is_claimable_by`) and `:1574` (the review-staffing arm) — do
  call `agents_that_may_have_authored` and are fixed by fixing it; R1's error was believing they
  were the only two places that decide who may review. **Python only; no UI bundle rebuild.**
- **Blast radius on the existing suite: R1 measured zero and R2 measured one — and the one is the
  test that encodes `F306`'s own precondition.** The whole Hub suite, run against a prototype of
  §§1–§3.4 under `py -3.11`: **1 failed, 4044 passed, 86 skipped** (25m44s).
  `tests/test_approval_refuses_unaccepted_evidence.py::test_the_agent_plane_sees_the_refusal`
  drives a task `assigned → in_progress → completed → under_review` with the **operator's** key,
  has agent `builder` record the evidence, then has `builder` request `approved` and asserts `409`
  — the evidence-not-accepted refusal. With the guard's fallback in place that request is refused
  `403` first, by the author rule. Reproduced in isolation (1.05s), and the file's 31 tests all pass
  on the reverted tree: deterministic, caused by the change, not a flake.

  **The expectation that changes is the right one to change.** That fixture is an operator-completed
  task whose evidence came from the agent now asking to approve it — `F306` exactly — and the test
  currently asserts the request gets *past* the author guard. `tasks.md` 4.11 restaffs it with a
  second agent rather than weakening the guard, and says so, because "make the failing test pass"
  here means reopening the hole.

  **Why R1 missed it.** R1 chose its 15 files by a rule — *the suites that seed evidence through
  `hub/tests/review_evidence.py`, plus the review, guard and staffing suites*. This file has its own
  `record_evidence` helper and imports from `test_task_integration`, so the rule excluded it. A file
  list chosen by how a suite seeds its fixtures is a guess about which suites reach the code.

- **R1's blast-radius paragraph, kept because its reasoning is still instructive and only its
  number was wrong.** The union and the guard fallback
  were prototyped in the working tree and 15 test files were run against the prototype — the 7 that
  seed evidence through `hub/tests/review_evidence.py` (whose default is `actor_kind="agent"`), plus
  the 8 review, guard and staffing suites. **210 existing tests, all passing.** The prototype was
  then reverted; nothing in it is committed. The reason nothing breaks is worth writing down: those
  tests complete their tasks through `_completed_by`, an *agent* completion, so `attribution.agent`
  is set and the union path is never reached; and where the union path *is* reached, the evidence
  actor is already in `agents_that_worked`. The verdict predicted one affected test file; R1's
  measurement said none, and the whole-suite run says the verdict was right and R1 was wrong — by
  exactly one file, and by the one whose fixture is `F306`. **The explanation above is still
  correct about the 15 files it covered**, which is what makes it worth keeping: it is a true
  account of a sample presented as an account of the population. The mutation table in `tasks.md`
  §4.7 was written on the strength of "all this coverage is new" and stays required either way.
- **New behaviour an operator can see:** a project whose only other agent is the evidence author now
  reports *"could not staff this step"* on a review it used to staff. That is the cost the verdict
  priced knowingly: *"the cost of excluding an agent that did nothing is a review the flow reports
  it could not staff, which the operator sees and resolves; the cost of including an agent that
  wrote the work is a self-approval nobody sees."*
- **Not in scope:** `F167` (B), the adjacent residual on the same repair, which fails closed; and
  any change to who may *decide* evidence (`requirement_evidence.may_accept`).
