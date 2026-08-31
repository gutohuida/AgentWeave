# Design — `approval-refuses-unaccepted-evidence`

Round 1. The operator's decision D-A (2026-08-30) settles *whether* to refuse; everything below is
*what exactly*, and each of the three pre-authorised defaults is checked against the code rather
than adopted.

---

## D1 — the refusal lives in `requirement_gate`, and the pre-authorised default survives the check

**Pre-authorised default:** in `requirement_gate`, as a sibling of `GateRefusal.unmergeable`, on
`_check_mergeable`'s own rationale. **Raise it if:** placing it there forces `requirement_gate` to
import something that creates a cycle, or the refusal needs to fire somewhere `apply_transition`
does not reach.

Both escape conditions were checked and neither holds.

**No cycle.** `_check_mergeable` already does `from . import project_workspace, task_integration`
locally, inside the function, with the reason written at `task_transition_service.py:550-552`:
`requirement_gate` reads coverage, which reads the models. The new check needs one more fact — the
*awaiting* rows — and that query belongs in `task_integration`, which already imports
`requirement_evidence` at module level (`task_integration.py:34`) and therefore already has
`AWAITING` in scope. Nothing new is imported by `requirement_gate` at all.

**`apply_transition` reaches every approval.** Verified by enumerating every call site rather than
asserting it: `api/v1/tasks.py:1309` (the operator route, and the agent route through the shared
`update_task_for_actor` — `agent_actions.py:275-289` delegates to it), `run_task_binding.py:440`
(`in_progress`), `:662` (`blocked`), `:750` (`in_progress`), `:813` (`in_progress`),
`scheduler.py:824` (`under_review`) and `:826` (`assigned`), `agent_trigger.py:728`
(`enter_selected_task`). **Exactly one of them can pass `approved`**, and it is the one route both
planes share. The rule that no route assigns `Task.status` directly is what makes a single
enforcement point sufficient, and it is the same rule the requirement gate and the dependency gate
already rest on.

So: a new `_check_unaccepted(session, task, refusal)`, called from `evaluate` beside
`_check_mergeable`, and a fourth list on `GateRefusal`.

**Rigor-independent, and this is not a stylistic choice.** `DEFAULT_SPEC_RIGOR = "sketch"`
(`models.py:1796`), and `_enforced_requirements` filters `sketch` out entirely — so anything behind
rigor is *absent* from a default project. That is how F122 survived to be found by a drive rather
than by a test. The same argument `_check_mergeable`'s docstring makes ("rigor is a claim about how
well the work must be proven; this is a claim about whether it can go where approval puts it")
carries verbatim.

---

## D2 — "evidence sits unaccepted" is narrower than the pre-authorised default, and the difference is a wedge

**Pre-authorised default:** evidence rows for this task in `review_state == 'awaiting'`; rejected
evidence is not this case. **Raise it if:** the honest predicate needs to distinguish evidence
recorded against a requirement this task is not linked to.

The `awaiting`-not-`rejected` half is right and is adopted unchanged, with the default's own reason:
rejected evidence has been judged, the author cannot un-reject it, and refusing on it wedges a task
whose only legitimate next move is to record better evidence.

**The default is too wide in a way that matters.** Taken literally — *any* awaiting row — it refuses
approval on evidence that could never have merged anything. `integration_targets`
(`task_integration.py:142-186`) requires four conjunctive conditions, and two of them are about the
*footprint*: `EvidenceFootprint.kind == "git"` and `commit_sha IS NOT NULL`. Its own docstring says
so:

> A `paths` footprint contributes nothing: there is no commit, so there is nothing that could be
> merged. That is a supported project shape, not a degraded one.

So an awaiting row with a `paths` footprint, or none, would still merge nothing after acceptance.
Refusing on it is a pure wedge with no possible remedy — the operator accepts it and approval is
refused again, for the same reason, forever. And it is not a hypothetical shape: it is the shape
of the research, docs and decision tasks the operator's own scoping constraint exists to protect.

**Adopted predicate:** an awaiting `RequirementEvidence` row, linked to this task through
`TaskRequirementLink`, carrying an `EvidenceFootprint` of `kind == "git"` with a non-null
`commit_sha`. Which is to say: **refuse only where accepting would change what integration merges.**

**On the raise-it-if.** The link-based scope *is* the discriminator the question asks about, and it
is not a choice: it is the scope `integration_targets` itself uses. Evidence is recorded against a
*requirement*, and `RequirementEvidence.task_id` exists (`models.py:2348-2350`) but integration
**does not read it** — it joins `TaskRequirementLink` on `requirement_id`. See D6 for the
consequence, which is real and is accepted deliberately rather than by omission.

---

## D3 — the mixed case is ALLOWED, and the default survives *only because half 2 is in this change*

**Pre-authorised default:** ALLOW where some accepted evidence already names a commit; record the
awaiting rows as an advisory. **Raise it if:** round 2 finds the awaiting evidence routinely names a
*newer* commit than the accepted one, which would make allowing it merge stale work.

The queue flagged this as the default most likely to be wrong. Checked against the code, it is
right — but not for the reason the default gives, and not unconditionally.

**The default's own reason is incomplete.** It argues that "integration will merge it and approval
keeps its meaning". Read against `integration_targets`, what is actually merged is *the newest
accepted footprint per distinct branch*. So in the mixed case the newer, unaccepted commit is
genuinely left behind, and the task is genuinely approved with work outside the product. That is
the exact defect this change exists to remove, arriving one commit smaller.

**What makes it right anyway is the second half of this change.** Accepting the outstanding evidence
now *triggers* integration for the already-approved task, so the mixed case converges: approval
merges what has been judged, and each later acceptance merges what it judged. The sequence has a
terminating state in which everything accepted is in the product, reached without reopening the
task and without the operator doing anything the refusal did not already ask for.

**So the answer is conditional, and the condition is stated as a design constraint:** the mixed case
may be allowed *because* acceptance integrates. Were half 2 dropped from this change for any reason,
the mixed case would have to become a refusal. Round 2 and round 3 should treat that as a coupling
to check rather than a sentence to agree with.

### Round 2: the coupling was checked, and half 2 as round 1 specified it does not carry it

Round 1 was right to name this a coupling and right to ask for it to be measured. Measured, **it
fails** — not in the exotic multi-branch shape the queue asked about, but in every shape, including
the simplest one.

Half 2's predicate, as round 1 wrote it (D7, `tasks.md` 4.1), is *approved tasks whose **most recent**
`TaskIntegration` is `SKIPPED` with `reason == NOTHING_TO_MERGE`*. In the mixed case the most recent
integration is not a skip at all — approval merged the accepted target, so the newest row is
`MERGED`. The predicate does not match, no retry runs, and the awaiting commit stays outside the
product **for ever**, silently, with the task terminal at `approved`. That is F122 exactly, one
commit smaller, which is the sentence D3 itself wrote and then failed to prevent.

Traced in all three shapes:

| accepted | awaiting | approval merges | newest row | round 1's retry | outcome |
|---|---|---|---|---|---|
| A on `X` | — | nothing | `SKIPPED/NOTHING_TO_MERGE` | fires | converges |
| A on `X` | B on `X` (newer) | A | `MERGED` | **does not fire** | B never merges — and B is the task's *final* work |
| A on `X` | B on `Y` | A | `MERGED` | **does not fire** | B never merges |

Row 2 is the worst of the three and is the ordinary one: same branch, second commit, the newest
accepted footprint per branch is what `integration_targets` returns, so approval merges the *older*
commit and the newer one is stranded by a rule written to strand nothing.

**The pivotal fact is measured, not inferred.** That the newest `TaskIntegration` row after such an
approval reads `merged` is asserted by a shipped, passing test —
`hub/tests/test_task_integration.py:377-379`, `newest = rows[-1]; assert newest["outcome"] ==
"merged"`. So round 1's predicate does not merely look unlikely to match; the suite already contains
the row that proves it cannot. That file also carries every helper `C-IMPL` needs for the fixture
task 1.2 worries about — `set_main_branch`, `linked_task`, `commit_on_branch`, `accept_evidence`,
`approve`, `integrations`, `commits_on` — so the mixed-case pair (`tasks.md` 5.6) is a short test
against proven scaffolding rather than a new git harness.

**The repair is in half 2's predicate, not in D3's answer.** D3's ALLOW is correct — *after* the
repair below. Round 1 reached the right answer through an argument that did not hold, which is the
failure mode round 3 exists for, found in round 2. Recorded that way rather than smoothed over.

### Rejected: refusing per branch rather than globally

Considered, because `integration_targets`' own comment warns that "silently dropping one of them
would integrate half of what was approved" — which suggests refusing where an awaiting target sits
on a branch that has no accepted target at all, while allowing the same-branch case.

Rejected on two grounds. It refuses exactly the multi-agent shape where approval *does* merge the
task's own work, for a stricter reading of `:638` than `:638` states; and the convergence argument
above applies identically per branch, so the extra strictness buys nothing that the second half does
not already deliver. Recorded here so it is not re-proposed as a discovery.

### The advisory needs a channel, and one already exists

`transition.reported_advisories` (`task_transition_service.py:583`) is a transient attribute the
operator route reads into `TaskResponse.approval_report` (`api/v1/tasks.py:1310`, `schemas/tasks.py:298`),
and the agent plane gets it through the same shared function. It is deliberately not persisted —
"a report at the moment of approval, not an audit trail".

`GateRefusal.reported` is not the right list to reuse: its documented meaning is `contract`-rigor
requirements that are unverified, and widening it would make a consumer unable to tell a rigor
report from an evidence advisory. **A fifth list, `advisory`,** carried out alongside `reported` into
the same `reported_advisories`. Each entry names the evidence id, the requirement identifier, the
commit and branch it names, and the remedy.

**Known gap, named rather than hidden:** no UI component reads `approval_report` today — grepping
`hub/ui/src` returns nothing. The advisory therefore reaches the API and the agent, and the operator
sees the same fact on screen only through the evidence panel's `awaiting` state. Filed for the drive
to confirm; not fixed here, because inventing a card for it is scope this change did not ask for.

---

## D4 — the refusal is silent wherever integration could not have been attempted anyway

Not in the pre-authorised defaults, and it is the second wedge.

`_check_mergeable` returns silently — never refusing — when the project has no `main_branch`, when
the workspace will not resolve, when the root is not a repository, or when the named branch does not
exist. Each is *"a reason to not know, never a reason to refuse"*.

Every one of those reaches the new check identically. If the project has no main branch, accepting
the evidence merges nothing, because `integrate_task` skips at `NO_MAIN_BRANCH` before it ever asks
for targets (`task_transition_service.py:740-745`). Refusing approval there would block **every task
in an unconfigured project** on a remedy that does not work — and `task-lifecycle-governance` says in
terms that *"a project that is not a repository SHALL be no less approvable than before this
capability existed."*

So `_check_unaccepted` shares `_check_mergeable`'s preconditions exactly. Implementation note for
`C-IMPL`: resolve project, workspace and repository once and hand both checks the result, rather
than performing the same two subprocess calls twice on the approval path.

---

## D5 — one query shape, parameterised, so the refusal and the merge cannot drift

`awaiting_targets` is `integration_targets` with the review state swapped. Written as one private
`_targets(session, task, review_state)` with two named callers, not as a second query that happens
to match.

The property this buys is exact and is worth stating as the reason: **the refusal fires precisely
when acceptance would produce a target that does not exist now.** Two independently-written queries
would drift — a filter added to one and not the other would produce either a refusal nothing can
clear, or a silent non-merge of the kind this change exists to end.

---

## D6 — link-based scope, and the consequence it carries

Because both queries reach evidence through `TaskRequirementLink`, awaiting evidence recorded by
*another* task against a *shared* requirement can refuse this task's approval.

That is not an accident of the query, and narrowing it to `RequirementEvidence.task_id == task.id`
would be wrong: if that evidence were accepted, `integration_targets` **would** merge its commit as
part of *this* task's integration, because integration is link-based too. Refusing is therefore the
honest statement — approval would otherwise leave behind a commit that this very task's integration
is responsible for.

The cost is real and is named: two tasks linked to one requirement are coupled at approval. Round 2
should check how common a shared `TaskRequirementLink` actually is in practice before this is taken
as settled; round 1's position is that consistency with the merge beats a narrower refusal, because
a refusal that disagrees with the merge is the defect in a different direction.

### Round 2 measured it: sharing is ordinary, so the scope stands and the *wording* has to change

Round 1 asked for a measurement before this was settled. Three places in the code say many tasks per
requirement is a first-class shape rather than an accident:

- `requirement_links.tasks_for_requirement` (`requirement_links.py:272-279`) returns a **list**, and
  `api/v1/spec.py:767` serves it to a surface. A one-task-per-requirement product would not have
  that query.
- `spec_tasks.materialise` scopes its duplicate suppression to **hand-made** tasks
  (`spec_tasks.py:169`) and says in a comment that a later entry in a document's own decomposition
  naming a requirement an earlier *declared* task already serves **is still created**
  (`spec_tasks.py:161-168`, `test_re_approving_creates_no_duplicates`). A decomposition of "implement
  FR-3" and "document FR-3" is exactly this.
- `absorb_free_text` reached from `api/v1/tasks.py:795` lets any agent's `create_task` name any
  identifier, with no check that another task already serves it.

So the coupling is not a corner. **The scope still stands** — narrowing to
`RequirementEvidence.task_id` would make the refusal disagree with the merge, which is the defect
pointing the other way — but the consequence changes what the refusal has to *say*. An operator
refused on a row their own task never recorded, told only the requirement and the commit, is being
shown a fact with no route back to its cause.

**Round 2's change:** each named row carries **the task that recorded the evidence** as well as the
requirement identifier and commit. Where that task is not the one being approved, the sentence says
so. `RequirementEvidence.task_id` (`models.py:2348-2350`) exists and is unread by integration — this
is the one thing it is genuinely good for: not scoping the query, but explaining its result.

---

## D7 — half 2 fires on *a commit that is not in the product*, not on the previous attempt's reason

**Round 2 replaced this section.** Round 1 wrote half 2 as a copy of
`tasks_skipped_for_want_of_a_main_branch` (`task_integration.py:343-390`), inheriting both of its
restrictions — *most recent attempt*, and *one reason* (`NO_MAIN_BRANCH` there, `NOTHING_TO_MERGE`
here). D3's round-2 table shows why that inheritance is wrong: in the mixed case the most recent
attempt is a **merge**, so no reason filter can match it and the acceptance merges nothing.

**Why the sibling's proxy is exact and this one is not.** Naming a main branch changes the world in
exactly one way — it clears `NO_MAIN_BRANCH` and nothing else — so "most recent skip was
`NO_MAIN_BRANCH`" is the same proposition as "this action created something mergeable". Accepting
evidence is not like that: it adds a **target**, and a task can acquire a new target whatever its
last attempt did. The proxy was borrowed from a case where it happened to be exact.

**The predicate, stated as the proposition it actually means:**

> When evidence is accepted, attempt integration for every **approved** task linked to that
> evidence's requirement whose newly-available commit is **not already recorded as merged for that
> task**.

Two narrowings remain, and they are the two round 1 added rather than the two it inherited:

1. **Only on `accepted`.** A rejection changes nothing that could merge.
2. **Only where the accepted evidence names a git commit.** A `paths` footprint produces no target,
   so an attempt could only record a second identical skip — noise in an append-only record whose
   purpose is to distinguish a no-op from work reaching the product.

**Correctness does not rest on the predicate being exact; only noise does.** `retry_integration`
(`task_transition_service.py:686-709`) says so in terms, and it is the licence for widening:

> No refusal when the work is already merged. `task_integration.integrate` self-guards with
> `ALREADY_INTEGRATED`, which asks the repository whether the commit is reachable — a fact — rather
> than reading the attempt log. So a retry after a merge honestly records one skip and merges
> nothing.

So `integrate_task` recomputes `integration_targets` and handles each target on its own merits.
Multi-branch converges by construction: accepted `A` on `X` returns `ALREADY_INTEGRATED`, newly
accepted `B` on `Y` merges. Same-branch converges too, because `integration_targets` returns the
newest accepted footprint per branch — after the acceptance that is `B`, and merging `B` carries
`A`'s ancestry with it.

**What this costs, named rather than discovered.** A task whose last attempt skipped
`CHECKOUT_DIRTY` will now be attempted again when new evidence is accepted, and will record a second
dirty skip. Round 1 inherited the sibling's "only that cause" wording to avoid exactly that. It is
accepted here, and the difference is causal: the branch sibling fires on a **settings save** that
says nothing about the checkout, whereas this fires on an acceptance that genuinely produced a
commit nobody has merged. "You accepted this, and here is why it still did not land" is the account
the operator needs; suppressing it is how work goes missing quietly, which is the whole subject of
this change.

### Rejected: keeping the reason filter and adding `MERGED` to it

Considered — retry where the most recent row is `SKIPPED/NOTHING_TO_MERGE` *or* `MERGED`. Rejected:
it is the same proxy with a second special case bolted on, it still misses a task whose most recent
row is a workspace-unavailable skip (`task_transition_service.py:746-753`, a reason neither sibling
enumerates), and it keeps the predicate expressed in terms of the *last attempt* when the thing that
actually changed is the **target set**. Two special cases is the signal that the proposition was
never about the attempt log.

**Wrapped and after the commit**, exactly as `_integrate_what_was_waiting_for_a_branch` is: the
decision is the operator's or the granted agent's, and it must stand or fall on its own terms. A git
failure is recorded as a skip, never as a failure to accept.

**Both routes, not one.** `spec.py:864-891` and `agent_actions.py:1164-1201` are separate functions
that both call `requirement_evidence.decide`. The shared helper goes in `task_integration`; each
route calls it. Putting it inside `decide` itself was considered and rejected: `decide` neither
commits nor knows about tasks, and integration must run *after* the commit.

---

## D8 — the consequence for the flow is a deadlock, and it is the decision, not a defect

Stated plainly so no later round mistakes it for something to fix.

In a default project the flow's review leg ends with the *reviewer agent* moving the task to
`approved` through `update_task`. After this change that call is refused, because the author's
evidence is `awaiting`. The reviewer's remedy — accept it — is refused too, at
`requirement_evidence.decide`'s first check, because no agent has `can_accept_evidence`. So the flow
stops and waits for a person.

That is D-A verbatim: *"a default project's first flow will stall loudly rather than finish silently
wrong. That is the intent."* It also resolves the one genuine requirement-vs-requirement conflict the
exploration found, in favour of `requirement-traceability`'s *"Where a project has granted no agent
that capability, acceptance SHALL fall to the operator. That is a supported way to work, not a
degraded one"* — and against `loop-becomes-a-flow` design D11's *"a queue can drain without the
operator in it"*. D11 is an archived change's design note, not a shipped requirement; no capability
spec claims an unattended drain, checked by grepping `agent-flows` and `agent-loops` for it. **So no
delta is owed to either.**

What this makes load-bearing: **the refusal's wording**. Per `task-lifecycle-governance`'s *"Where a
skip names a cause the operator can put right, it SHALL point at the remedy that works… An
instruction that fails silently is worse than none"*, the sentence must name **both** ways out —
accept the evidence yourself, or grant an agent the capability — because the agent reading it can do
neither and needs to say so to the operator.

**Both remedies were checked to be reachable, which is what "the remedy that works" demands.**
Accepting is `POST /spec/evidence/{id}/decision` on the operator plane and is rendered in the
evidence panel; granting is the `can_accept_evidence` toggle at
`ui/src/components/agents/AgentSettingsControls.tsx:448`, writing through the PATCH loop at
`agents.py:2007`. The grant is *ungranted* by default, not ungrantable — `GRANT_FIELDS`'
own comment records that it was once the latter, and says why it is kept out of the checkpoint pair:
*"those two widen what an agent may read, and this one decides whether work is allowed to merge."*

---

## D9 — the edge this change does not handle, named rather than discovered later

An awaiting commit that is **already reachable from the main branch** — merged by hand, say — will
refuse approval, even though nothing is actually outside the product.

Not handled, deliberately. `EvidenceFootprint.reachable_from_main` is a *stamped* value with its own
refresh path (`requirement_evidence.refresh_reachability`), so trusting it risks refusing on a stale
fact, and asking git instead costs a subprocess per awaiting target on the approval path. The
honest statement is that the evidence has not been judged, and whether its commit is coincidentally
present does not change that. The remedy the refusal names — accept it — works, and acceptance then
records `ALREADY_INTEGRATED`, which is the correct account.

---

## D10 — rejected alternatives, recorded so they are not re-proposed

- **Seeding a granted agent per project**, and **a flow granting its resolved reviewer per task** —
  rejected by the operator 2026-08-30. `models.py:268-270` states the reason the product already
  holds: *"Producing evidence is open to anyone; accepting it is the controlled act… deliberately
  not conferred by a charter — behaviour is not authority."*
- **Leaving the machinery alone and surfacing "approved but unmerged"** — rejected by the operator,
  because it leaves *Approval integrates the approved work* breached.
- **Auto-accepting a flow's own evidence at approval** — not on the operator's list, and it makes
  the review that gates the merge decorative, which `integration_targets`' docstring names as the
  thing it exists to prevent.
- **Refusing on rejected evidence** — see D2.
- **Refusing per branch** — see D3.
- **Making `NOTHING_TO_MERGE` three strings in this change** — the awaiting world stops reaching it
  here; the rest is F124's, which is change D's, and splitting the constant twice is worse than
  splitting it once.

---

## D12 — round 2: the refusal's sentence reaches an agent as a Python dict repr (F152)

Found by following requirement 1's own load-bearing clause — *the refusal must name both remedies to
its reader* — down to the reader that most needs it, which is an agent, not the operator.

`main.py:406-415` sends `refusal.to_dict()` as the response `detail`, so an agent's `update_task`
receives a **dict**. `mcp_server._readable_detail` (`mcp_server.py:111-135`) special-cases a `list`
— the Pydantic-validation shape — and falls through to `str(detail)` for everything else. So the
agent is handed:

```
{'code': 'gate_unsatisfied', 'blocking': [], 'diagnostics': [], 'unmergeable': [], 'reported': [],
 'message': 'This task ... accept the evidence, or grant an agent ...'}
```

which is precisely the failure its own docstring says it exists to prevent, for the other shape:
*"stringifying it verbatim produced tool errors like `[{'type': 'value_error', ...}]`. An agent
trying to correct itself had to parse that."*

**Pre-existing, and in scope anyway.** Every gate refusal has arrived this way since the gate
shipped; this change did not cause it. It is in scope because this change's entire value is a
sentence an agent has to act on, and D8 makes that sentence the only thing standing between the
agent and a deadlock it must escalate. Shipping the wording without the channel would satisfy the
requirement's letter and fail its stated reason.

**The fix is three lines and stdlib-only**, which matters: `mcp_server.py` may import only stdlib
and fastmcp. Where `detail` is a dict carrying a `message`, return that; otherwise fall through to
today's behaviour. Filed as **F152**; fixed here rather than queued, because it is inside the
sentence this change is about.

---

## D13 — round 2: four facts checked in the code that the implementation would otherwise assume

Recorded so `C-IMPL` does not re-derive them and round 3 can attack them rather than the gaps.

1. **There are two unrelated `Actor` types, and half 2 crosses between them.** Both decision routes
   build `spec_lifecycle.Actor(kind="agent"|"operator", …)`. `integrate_task`/`retry_integration`
   take `task_transitions.Actor`, whose `__post_init__` admits only `run`/`operator` and *requires*
   `run_id` **and** `agent` when the kind is `run` (`task_transitions.py:59-67`). So `tasks.md` 4.6's
   "record the accepting actor" is reachable — `run_actor(actor.run_id, actor.agent)` on the agent
   route, `operator()` on the operator route — but only through an explicit conversion. Passing the
   `spec_lifecycle` actor through raises `ValueError`.
2. **`task_integration.record` constrains nothing.** `actor_kind` is a plain `String(16)` with no
   `CheckConstraint` in the model (`models.py:2548-2555`) and none in any migration. The constraint
   that actually bites is the `Actor` construction in (1). `integrate_task._record` writes
   `actor_kind=actor.kind, actor=actor.agent or ""`, so a granted agent's acceptance records
   `("run", "<agent>")` — a true account of who caused the merge, which is 4.6's whole point.
3. **`expire_on_commit=False`** (`db/engine.py:40`). So calling half 2 *after* the route's own
   `session.commit()` and letting it commit again cannot expire the ORM objects the route then
   serialises into its response. The `MissingGreenlet` hazard that shape usually carries is absent
   here. Do not add a defensive refresh.
4. **Evidence the operator records is born `accepted`** — `review_state=ACCEPTED if actor.kind ==
   "operator" else AWAITING` (`requirement_evidence.py:167`). So the refusal can only ever fire on
   **agent-produced** evidence, which is why F122 is a flow-shaped defect and why the operator can
   never trip over it by working alone. It also means D8's deadlock is exactly as narrow as D8 says.

---

## D11 — tripwires for `C-IMPL`

- **`GateRefusal.refuses`** is `bool(self.blocking or self.diagnostics or self.unmergeable)`. A new
  list that is not added there refuses nothing and every test still passes.
- **`detail()` has an early return**: `if self.unmergeable and not (self.blocking or
  self.diagnostics)`. A third category added carelessly is silently dropped from the sentence in the
  exact case that matters most — an otherwise-clean task.
- **`to_dict()`** is what `main.py:415` serialises. A field missing there never reaches any surface.
- **`ui/src/__tests__/taskIntegration.test.ts`** asserts the structured detail's `message` survives
  `readableApiError`. It should gain the new shape; the UI needs no other change.
- **`hub/tests/test_requirement_gate.py`** is the gate's own file and already reads
  `approval_report`.
- The refusal fires on an edge **the flow drives**, so `hub/tests/test_flow_chain_end_to_end.py`
  and every scheduler test that walks a task to `approved` with recorded evidence is a candidate to
  move. Grep before changing any of them, and write the reason into each — the discipline B-IMPL
  followed.
