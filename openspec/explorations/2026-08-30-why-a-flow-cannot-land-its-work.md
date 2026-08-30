# Exploration — Why a flow cannot land its work, and what to do about it

**Date:** 2026-08-30
**Status:** Explored against the code at `345c149`. Two operator decisions taken (§6). Not yet
proposed.
**Purpose:** The durable record of a deep read of the flow machinery, so the changes that follow do
not re-derive it. Every claim below was read in the code and carries a `file:line`. Findings
F122, F124, F140, F142, F143 and F47/F120 are all explained by what is written here.

---

## 1. The one sentence

**The flow's definition of "done" is the task lifecycle's definition of "decided", and those are
not the same thing.**

`_loop_stop_reason` (`hub/hub/scheduler.py:320-338`) counts a task drained when its status is in
`TERMINAL_FOR_BINDING` = `{approved, rejected}`. Integration runs *after* the transition into
`approved` and cannot affect it. So an approved-but-unmerged task is drained, the job is disabled,
and `loop_ending.py:54` records `ending_state = "completed"`.

**`hub/hub/scheduler.py` contains zero references to integration.** The module that decides a flow
is finished has never heard of the module that decides whether work landed.

```
   THE TASK LIFECYCLE                    THE EVIDENCE LEDGER
   ══════════════════                    ═══════════════════
   in_progress                           record_evidence
       │  only the holder may finish          │  open to anyone
       ▼                                      ▼
   completed  ──────────┐               review_state: awaiting
       │                │                     │  needs can_accept_evidence
       ▼                │                     │  ← default False, every agent
   under_review         │                     ▼
       │                │                accepted
       ▼                │                     │
   approved  ◀──────────┘                     ▼
       │   BAND_TERMINAL              integrate_task reads ACCEPTED EVIDENCE,
       │                              never task status
       └──────────────────────────────▶ ├─ MERGED
                                        └─ SKIPPED "nothing to merge"
   _loop_stop_reason: "drained"
   counts approved as done ────────────▶ never consulted
```

## 2. The only road to `main`

There is **exactly one `git merge` into a project's main branch in the whole tree**:
`hub/hub/task_integration.py:289-300`. Its sole input is `Target`, produced only by
`integration_targets` (`task_integration.py:142-186`), which is the entire chain in one query —
**four conjunctive conditions**:

1. a `TaskRequirementLink` row for the task,
2. `RequirementEvidence.review_state == ACCEPTED`,
3. an `EvidenceFootprint` of `kind == "git"`,
4. a non-null `commit_sha`.

Nothing pushes; no route accepts a commit sha to merge; `worktrees.py:387-399`'s other `git merge`
writes to a *task* branch and is itself evidence-derived.

`integrate_task` has exactly four call sites: the transition into `approved`
(`task_transition_service.py:462`), `retry_integration` from the operator route
(`tasks.py:1142`), the agent route (`agent_actions.py:309`), and project-settings save for the
`NO_MAIN_BRANCH` case only (`projects.py:522`).

**Accepting evidence is not one of them.** Both decision routes (`spec.py:864-891`,
`agent_actions.py:1164-1201`) call `requirement_evidence.decide`, commit, and return.
`hub/hub/api/v1/spec.py` contains zero references to integration.

## 3. The seven breaks

| # | Break | Where | Normative status |
|---|---|---|---|
| 1 | A loop is documentless **by definition**, so it can never merge | `mcp_server.py:653-661` | Omission — no requirement covers loop integration |
| 2 | The briefing never names `update_task`, a status, or "completed" | `scheduler.py:1764-1777` | **Gap in the corpus** — nothing defines what causes `in_progress → completed` |
| 3 | `is_review` computed, then dropped before the briefing is built | `scheduler.py:2356-2366`, `:2713` | Contradicts design D4 on the prompt channel |
| 4 | Review arm drops an unattributable task with a bare `continue` | `scheduler.py:1365-1369` | **Breaches `agent-flows:134`** |
| 5 | `can_accept_evidence` false on every agent a project creates | `models.py:268-270` | **Breaches `task-lifecycle-governance:638`** |
| 6 | Accepting evidence triggers no integration | `spec.py:864-891` | Same breach, second route |
| 7 | "Try again" offered on a reason it can never clear | `TaskIntegrationNote.tsx:42-45` | **Breaches `:865`** |

### Break 1 — a loop can never land work, structurally

`create_loop` refuses `spec_document_id` outright (`mcp_server.py:653-661`): *"a loop that declares
a specification document is a flow: call create_flow instead."* So:

```
loop has no spec document → project has no SpecRequirement rows for it
  → record_evidence("FR-1") 404s "this project has no requirement FR-1"  (agent_actions.py:1041)
  → no evidence → no accepted footprint → integration_targets() == []
  → "no accepted evidence names a commit", permanently, for every loop task ever
```

F124 said loop tasks *happen to* lack requirement links. The truth is stronger: **the definition of
a loop excludes it from the only mechanism that reaches the main branch.**

### Break 2 + 3 — the briefing

`_compose_loop_briefing` (`scheduler.py:1732-1833`) is the whole instruction. Its flow branch
(`:1764-1777`) says, in full, about ending:

> **Finish the task below and stop.** Do not pick up the next item and do not hand the work to
> anyone — routing is the flow's job, and the next firing decides who does what. Record what a
> reviewer will need (see `submit_checkpoint_notes`); somebody else reads it.

| Named? | |
|---|---|
| `update_task` — the only tool that moves a task | **No** |
| `record_evidence` — *"This is what lets approved work merge"* (its own docstring) | **No** |
| the word `completed`, or any target status | **Never appears** |
| `submit_checkpoint_notes` | **Yes** — and `agents.py:835-838` excludes it from the tool inventory |

There is no `finish_turn` tool; ending a turn is ending the process. Nothing gates `→ completed` on
evidence or notes — the only check is that the calling run is the bound holder
(`_guard_run_holds_the_task`, `task_transition_service.py:231-295`).

`_compose_loop_briefing` has **no `is_review` parameter**. It is computed at both call sites, passed
to `_briefing_checkpoint`, and dropped on the very next line. So a reviewer gets the implementation
briefing verbatim — *"Finish the task below and stop"* plus the task's implementation description
and acceptance criteria — while the **context** channel (`agents.py:1121-1172`) simultaneously says
*"This is a review turn. You are reviewing someone else's work, not doing your own."* Two channels
built by two modules that never see each other. F143 is the agent noticing.

### Break 2's real shape — five correct decisions composing into an infinite waste loop

```
1. Briefing says "Finish and stop", names no tool/status     ✔ true to design D8
2. Agent works, never calls update_task                      ← never told to
3. Divergence correctly detected (run_advanced_its_task)     ✔ run-task-binding:206 satisfied
4. POLICY_RETRY → POLICY_FLOW, surfaced only                 ✔ "retry would race the flow"
                                     (run_divergence.py:743-752)
5. severity = "info"                                         ✔ indistinguishable from healthy
                                     (run_divergence.py:793-800)   multi-turn work
6. Next firing re-claims, re-briefs, re-does                 ← forever, reported busy
```

Every link is individually correct and defensible. **The system's chosen remedy is the mechanism
that reproduces the fault, and its severity grading makes the loop look like health.** This is
*not* a breach of `run-task-binding:206/:368` — the divergence really is recorded.

### Break 4 — the quietest line in the flow

```python
author = await agent_that_completed(session, task.id)
if author is None:
    continue          # records NOTHING
```

`scheduler.py:1365-1369`. Not `unstaffed`, not `deferred`, not `in_flight`, not `gated`; no log, no
event, no SSE. The F64 fix that would surface a specific reason (`stall_reason = unstaffed[0][1]`)
is defeated because `unstaffed` is empty — so the operator gets the generic histogram
`"loop queue is stalled: no claimable task among 1 open (1 completed)"` assembled by a `GROUP BY
status` (`scheduler.py:1515-1551`) that knows nothing about why.

`agent_that_completed` (`task_transition_service.py:123-147`) **does not filter on `actor_kind`**.
An operator's `→ completed` row is selected as the most recent completion and yields `None`, so
`None` is ambiguous between *"nobody completed this"* and *"the operator did"* — and **no caller
distinguishes them**. Seven callers, split: two guards permit on `None`, `task_is_claimable_by`
refuses, the review arm drops.

The root is a deliberate exemption (`task_transition_service.py:262`): *"The operator is untouched
in both halves… An operator marking a card done is a statement by a person, and has never needed a
binding."* `Actor.__post_init__` (`task_transitions.py:64-67`) makes an operator-with-agent
**unconstructible**, so `actor_agent` is NULL by invariant, not by accident.

### Break 5 + 6 — the grant, and the missing edge

`can_accept_evidence` is `default=False, server_default="0"` (`models.py:268-270`) with a written
rationale: *"Producing evidence is open to anyone; accepting it is the controlled act… deliberately
not conferred by a charter — behaviour is not authority."*

**All four `Agent(...)` construction sites omit it**: operator create (`agents.py:665`),
`request_agent` (`agents.py:1593`), self-registration (`agents.py:1704`), and YAML roster sync
(`session_sync.py:95-105`). There is no YAML key for it. The single writer is an operator PATCH
(`agents.py:2007-2012`).

Most pointed: the agent retry route's own docstring (`agent_actions.py:309-324`) names this exact
loop — *"one skip reason — nothing accepted names a commit — is one an agent can genuinely clear,
by having a granted peer accept its evidence."* **The product anticipated the failure and built the
escape hatch; the hatch depends on a grant no code path ever confers.**

### Break 7 — the button that cannot work

`TaskIntegrationNote.tsx:42-45` offers "Try again" for every non-`merged` outcome except one whose
reason contains `no main branch set`. So the F122/F124 terminus **does** get a button, which skips
again identically. `integration-preview` (`tasks.py:1041-1091`) already computes `will_merge:
false` from the same source and the card never asks it.

## 4. `NOTHING_TO_MERGE` conflates three worlds

One flat string (`task_integration.py:54`), emitted from two sites
(`task_transition_service.py:637`, `tasks.py:1079`):

| World | Truth | Right response |
|---|---|---|
| evidence exists, unaccepted (F122) | **waiting on someone** | name who must accept |
| no requirement link possible (F124) | **impossible by construction** | never retryable |
| task genuinely had no code | **correctly nothing** | settled, fine |

The module's own comment claims *"none of them means anything went wrong"*; F124 disproved that.

## 5. What the corpus already requires

**Four of the seven breaks are breaches of shipped requirements** — so most of this work is
*enforcing* the corpus, not amending it.

`task-lifecycle-governance:638` — **Approval integrates the approved work**

> The transition into `approved` SHALL merge the approved work into the project's configured main
> branch, in the same operation that records the transition. […] a lifecycle whose terminal state
> carries no such meaning cannot answer whether anything it approved was ever shipped.
> […] Evidence that is awaiting review or has been rejected SHALL NOT contribute a commit to
> integrate.

`task-lifecycle-governance:720` — **An integration that cannot proceed does not block approval**,
with a **closed enumeration**: no main branch, not a repository, dirty checkout, checkout not on
main. **"No accepted evidence names a commit" is not in that list.** Today's behaviour therefore
breaches `:638` and is not excused by `:720`.

`agent-flows:134` — *"WHEN no agent can be resolved or found for a task THEN the operator is
notified, **naming the task**"*. Break 4 breaches this.

`task-lifecycle-governance:865` — *"Where a skip names a cause the operator can put right, it SHALL
point at the remedy that works… An instruction that fails silently is worse than none."* Break 7
breaches this.

`task-lifecycle-governance:359` — **there SHALL NOT be a third actor kind**, with the scenario
*"WHEN the set of actor kinds is enumerated THEN it contains agent run and operator, and nothing
else."* This **forecloses** the obvious F47/F120 repair. The same requirement blesses the
alternative: *"The system SHALL be able to move a task… acting **as** the responsible run rather
than as an actor of its own kind"*, which is what `origin=runtime` already implements.

> **Trap.** `task_transition_service.py:317-318` gives a *narrower* reason for having no third kind
> ("the system acts as the run rather than instead of it") which does **not** obviously reach the
> flow's claim, where no run exists yet. Do not reason from the code comment alone — the shipped
> requirement is categorical and its stated reason (actor kind is what the transition map and
> author/reviewer separation are keyed on) does reach it.

### The one genuine requirement-vs-requirement conflict

- `requirement-traceability:117` — *"Where a project has granted no agent that capability,
  acceptance SHALL fall to the operator. **That is a supported way to work, not a degraded one.**"*
- `loop-becomes-a-flow` design D11 — *"A reviewer's turn can end at `approved`, so **a queue can
  drain without the operator in it.** That is what makes an unattended flow possible at all."*

Both shipped. In a default project they cannot both hold. **Resolved by the operator in §6.**

### Two silences worth naming

1. **No requirement defines what causes `in_progress → completed`.** `:1389` says who *may*,
   `:1010` says it is not gated on evidence, `:21` says the edge is legal. F140 is the absence of a
   requirement as much as a defect in one.
2. **No requirement connects a flow's ending to whether its work shipped.** Making a flow refuse to
   report `completed` with unmerged work **adds** a requirement.

## 6. Operator decisions, 2026-08-30

**D-A. Approval is REFUSED while evidence sits unaccepted.**
Chosen over: seeding a granted agent per project; a flow granting its resolved reviewer per task;
and leaving the machinery alone while surfacing "approved but unmerged" (rejected because it leaves
`:638` breached).

Consequence, stated plainly: a default project's first flow will **stall loudly** rather than
finish silently wrong. That is the intent. The grant becomes load-bearing, so **the refusal must
name the remedy** — accept the evidence yourself, or grant an agent — per `:865`'s principle.

**Critical scoping constraint.** The refusal must fire only when evidence exists and is
*unaccepted*. A task with **no evidence at all** must still be approvable, or every research,
docs and decision task wedges. This is exactly `_check_mergeable`'s own rule
(`requirement_gate.py:157-163`): *"Approval must never be blocked by the absence of an integration,
only by one that would fail."* Evidence recorded-but-unaccepted **is** one that would fail.

**D-B. A loop declares at creation whether its work needs evidence.**
Chosen over: loops never merging; implicit requirements; retiring loops. When a loop declares its
work does not need evidence, its tasks must be able to land without the requirement/evidence chain;
when it declares that it does, the existing chain applies unchanged.

## 7. Where the repair belongs

`requirement_gate._check_mergeable` (`requirement_gate.py:153-194`) already draws exactly the line
this problem needs, and its docstring is the argument for D-A:

> Deliberately **not** conditional on rigor. Rigor is a claim about how well the work must be
> proven; this is a claim about whether it can go where approval puts it. A conflicting branch
> approved at `sketch` would record an approval that silently integrates nothing.

`GateRefusal` already carries `unmergeable` as a class distinct from `blocking`
(`requirement_gate.py:73-76`) — *"not 'this is unproven' but 'this cannot go in'"*. **The
unaccepted-evidence refusal is a sibling of `unmergeable`, on the same rationale, and must be
equally rigor-independent.** `DEFAULT_SPEC_RIGOR = "sketch"` (`models.py:1796`) blocks nothing, so
anything placed behind rigor is absent from a default project — which is how F122 survived.

## 8. Tripwires for whoever implements this

- **`TERMINAL_STATUSES` is declared twice**: derived from the band at `task_transitions.py:329`,
  and hardcoded at `task_transition_service.py:485`. They answer documented*ly* different questions
  and coincide today. A change to what terminal means reaches the first and silently misses the
  second; `api/v1/worktrees.py:27` imports the hardcoded one.
- **`test_flow_chain_end_to_end.py:342-355`** pins the flow's misattribution with a **set
  equality**, deliberately, *"so that fixing it, or a genuine operator action appearing, both fail
  here."* Any attribution change must update it.
- **`test_task_transitions.py:55-59`** asserts `actors <= {ACTOR_RUN, ACTOR_OPERATOR}` over the
  whole map — a third kind fails it.
- **`test_task_transitions.py:473-496`** is a source scan restricting `origin="runtime"` to
  `run_task_binding.py` and `task_transition_service.py`.
- **`enter_selected_task` has three callers** (`scheduler.py` ×2, `agent_trigger.py:774`), and the
  third is a *genuine* operator action. Any actor change must not sweep it up.
- One codebase comment describes a merge that cannot happen
  (`task_transition_service.py:249`): *"that reviewer… approves, and `task_integration` merges."*
  It is aspirational in a default project — evidence of intent, not of behaviour.
