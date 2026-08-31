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

---

## D7 — half 2 answers only `NOTHING_TO_MERGE`, on the sibling's own recorded reasoning

`tasks_skipped_for_want_of_a_main_branch` (`task_integration.py:343-390`) restricts to the *most
recent* attempt and to *one* reason, and both restrictions transfer without modification:

- **Most recent**, so "a task that skipped and was later merged by an explicit retry must not be
  picked up again".
- **One reason**, because accepting evidence says nothing about a dirty checkout or a checkout
  parked elsewhere, and a merge that failed outright wants a person. This is `D8` of the earlier
  change, shipped as *"Only that cause SHALL be answered this way."*

Two additional narrowings this sibling needs and the branch one does not:

1. **Only on `accepted`.** A rejection changes nothing that could merge.
2. **Only where the accepted evidence names a commit.** Accepting a `paths`-footprint row cannot
   produce a target, so retrying would record a second, identical `NOTHING_TO_MERGE` skip — noise in
   an append-only record whose whole purpose is to distinguish a no-op from work reaching the
   product.

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
