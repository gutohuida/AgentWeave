# Design — the briefing names its contract

## Context

`_compose_loop_briefing` (`hub/hub/scheduler.py:1732-1833`) composes the text that sits ahead of a
loop job's own message on every firing. It is a **prefix, never a replacement**: `_do_fire_job` puts
`job.message` after it unchanged, and `format_turn_prompt` (`inbound_queue.py:98-122`) wraps the
whole thing in a per-entry block with the origin named — the content itself is carried verbatim, so
markdown structure survives to the agent.

It is one of two channels that build agent-facing text, and they are built by two modules that never
see each other:

| Channel | Built by | Delivered as | States |
|---|---|---|---|
| turn context | `api/v1/agents.py:1100-1300` | the run's system prompt | the workspace, the review boundary, the tool inventory, the review verdicts |
| firing briefing | `scheduler.py:1732-1833` | the inbound queue entry | the tier, the claimed task, the prior checkpoint, the queue counts |

F140 and F143 are both what happens when the second channel is written as description while the
first is written as instruction.

## Decisions

### D1 — the briefing states the completion contract, rather than the Hub inferring it

F140 offered three repairs. This change takes the first and records why:

| Repair | Why not |
|---|---|
| **Brief the agent** — name `update_task`, the target status, and what it causes | **Chosen.** Matches the measured evidence exactly: the tool the briefing named (`submit_checkpoint_notes`) is the tool both agents called; the tool it did not name (`update_task`) is the tool neither called. |
| **Let the Hub conclude it** — a clean turn end on a bound task moves the task to `completed` | Asserts the work is finished on the strength of the process exiting. That is precisely the inference the operator retired the question-detection backstop for making (`CLAUDE.md`, 2026-08-20), and a turn can end because the agent gave up. |
| **Surface the non-advance as a stall** rather than silently re-briefing | Right, and **not this change.** `run_divergence.py` already detects it; what is wrong is that it is graded `severity = "info"`. That is `loop-firing-accountability`'s subject. Recorded as a follow-up below. |

The objection to the chosen repair — *"it makes the flow's progress depend on an agent choosing to
make a tool call, which is what F27 and F139 both say is not reliable"* — is real and is not
dismissed. The answer is that **it already does**, unavoidably: there is no `finish_turn` tool, and
ending a turn is ending the process. The only question open today is whether the agent has been told
what the call is. It has not been. Telling it is strictly better than not telling it, and it is
independent of whether the divergence grading is also fixed.

### D2 — the contract is stated for loops as well as flows

`agent-flows:314`'s second scenario forbids a document-less loop's briefing from claiming a flow's
behaviour: *"the briefing does not state that anything will route its work onward."* Naming
`update_task` and `completed` is not a flow claim — it is the task lifecycle, and a document-less
loop's queue drains on the same band (`TERMINAL_FOR_BINDING = {approved, rejected}`,
`scheduler.py:320-338`). A loop task that never leaves `in_progress` re-claims forever for exactly
the same reason a flow task does.

What stays flow-only is the sentence about **what completing causes**: a flow offers the work for
review by somebody else; a loop's task simply moves on. That split is the same one the existing tier
statement already draws, on the same rule the function's own docstring states: *"what separates the
two wordings is what is true, not which tool created the loop."*

### D3 — the briefing names requirements by identifier, from the link table, or says nothing

`record_evidence` is what lets approved work merge — its own tool-surface line says so — and the
briefing never mentions it. But an agent told to record evidence for a task with no requirement
links gets a `404`: *"this project has no requirement FR-n"* (`agent_actions.py:1041`).

So the briefing reads the links (`requirement_links.for_task(session, task.id)`) and names the
identifiers it finds. Where there are none, it says nothing at all about evidence. This is the same
rule as D2 in a different place: **state what is true of this firing, not what is true of the
feature.**

This costs one indexed query per firing that claims a task, alongside the two the function already
runs (the checkpoint lookup and the status group-by). Not a cost worth a cache.

### D4 — the review branch keeps "stop", replaces "do the work", and re-frames the task text

Three things are true of a review firing, and the briefing gets each wrong today:

1. **It is a review.** The briefing does not say so; the turn context does, and they contradict.
2. **The task text is the standard, not the instruction.** The briefing presents it under
   `## Current task:` immediately after *"Finish the task below and stop"*, which is an instruction
   to build it.
3. **The turn ends with a verdict, not with work.** The briefing names no verdict.

The review branch therefore:

- keeps the flow/loop tier paragraph — still true, and a reviewer benefits from knowing routing is
  not its job as much as an implementer does;
- keeps a "stop" statement, reworded for what stopping means here;
- replaces `## Current task:` with a heading that names the task as the work **under review**, and
  says in one line that the text below is what the author was asked to build;
- names both verdicts and the calls that record them.

### D5 — the verdict is named on both channels, deliberately

`api/v1/agents.py:1148-1157` already names both verdicts, as the F45 fix. Saying it again in the
briefing is duplication, and duplication is normally a defect. It is right here, for a measured
reason:

**F140 established that the briefing is the channel that drives tool calls.** Both agents called the
tool the briefing named and neither called the tool only the context named — and `update_task` was
in the context's tool inventory the whole time. F45 measured the same thing from the other side:
*"measured across this Hub's history, no flow-dispatched reviewer had ever recorded a transition"*,
with the context channel already saying how.

A reviewer whose briefing is silent on how to end is a reviewer relying on the weaker channel. The
two statements must **agree**, which is a real constraint on the wording — but stating it once, on
the channel that does not work, is how F45 happened.

### D6 — `is_review` is keyword-only with no default

`_briefing_checkpoint` immediately above already takes `*, is_review: bool` with no default, and
that is the shape to copy. A default of `False` would mean a future call site that forgets the
argument silently composes an implementation briefing for a reviewer — which is F143 exactly, made
easier to reintroduce. Six existing test call sites must state it; that is the point.

## Risks

| Risk | Mitigation |
|---|---|
| The wording is *almost* right and a real agent still does not call `update_task` | Only a drive settles this. `DRIVE-1` re-runs `t_row12_flows.py`'s scenario and the pass condition is the status moving, not a string being present. |
| The briefing grows past what an agent reads | The additions are ~4 lines for implementation and ~5 for review, against a briefing whose bounded part is the checkpoint (`agent-loops:274`). The tier statement stays first, above the checkpoint, for the reason the docstring already gives. |
| The two channels drift apart again | The new requirement is written about what the briefing must state, and the review-branch test asserts against both channels' wording rather than one. Not a structural fix — that would be one module owning both — and is not attempted here. |
| Naming a status makes an illegal transition look legal | The briefing states the task's **current** status from `claimed_task.status`, so `assigned → in_progress → completed` is visible as two hops rather than implied as one. The review branch names only `approved` and `revision_needed`, both legal from `under_review`, which is where `enter_selected_task` puts a review's task before the turn begins (`scheduler.py:794-795`). |

## Follow-ups this change deliberately leaves open

- **The divergence grading.** `run_divergence.py:793-800` grades a run that did not advance its task
  `severity = "info"`, which is indistinguishable from healthy multi-turn work, and
  `POLICY_RETRY → POLICY_FLOW` (`:743-752`) makes the flow's own re-brief the remedy. If briefing
  the agent does not close F140 in the drive, this is the next change, and it belongs in
  `loop-firing-accountability`.
- **One module owning both agent-facing channels.** The structural fix. Out of scope, and larger
  than the flow.

---

# Round 2 — a fresh comparison against the code

Read independently against the code at `7da91a3`, not against round 1's reasoning. Four of round
1's claims were verified and hold; **two were wrong**, and three more constraints were found that
round 1 did not know about. Corrections are folded into `tasks.md` and the delta spec; the record of
what was checked is here.

## Verified and holding

**The claim happens before the briefing, on the same object.** `enter_selected_task` runs at
`scheduler.py:2332` and `:2690`; `_compose_loop_briefing` at `:2364` and `:2714`; and
`apply_transition` assigns `task.status = to_status` in place (`task_transition_service.py:430`) on
the same ORM row in the same session. So `claimed_task.status` at composition time is the
**post-claim** status. D3's and task 3.1's dependence on it is sound.

**No import cycle, so task 4.3's fallback is dead and is removed.** Walking every first-party
`from .x import` reachable from `requirement_links` transitively: `scheduler` is not among them. A
second hand-written `select(...).join(TaskRequirementLink)` in the scheduler would be exactly the
drift the queue group-by's own comment warns about, and there is no reason to accept it.

**The briefing survives delivery byte for byte.** `format_turn_prompt` interpolates `entry.content`
verbatim into `f"{origin} (hop {n}){retry}:\n{content}"`, joins entries with a blank line under a
one-line preamble, and truncates nothing — `inbound_queue.py` contains no length cap at all. The
only bounded region anywhere is the prior checkpoint, inside the briefing, by `agent-loops:274`.
Markdown headings reach the agent.

**Naming `update_task` in the briefing does not conflict with the tool inventory — it follows its
rule.** `UNDESCRIBED_TOOLS` excludes `submit_checkpoint_notes` with the reason *"Named in the
checkpoint prompt itself, at the moment it applies. Describing it on every turn would invite it on
turns that are not checkpoints."* That is the product's own statement that a tool belongs where it
applies, which is the argument for this change rather than an obstacle to it. `update_task` stays in
the inventory as a signature and gains a briefing mention as an instruction; nothing couples them
(`test_tool_surface_matches_server.py` compares `mcp_server` to `_tool_surface_lines` and never
reads the scheduler).

## D7 — a task returned for revision is a third arrival state, and round 1 missed it

**Round 1's task 3.2 was wrong.** It named `assigned` and `in_progress` as the states a task can
arrive in. `CLAIMABLE_LOOP_TASK_STATUSES` derives from `CLAIMABLE_STATUSES`, which is
`_statuses_in(BAND_AGENT_ACTIONABLE)` = `{pending, assigned, in_progress, revision_needed}`
(`task_transitions.py:219-222, 286`), and `enter_selected_task`'s ordinary branch moves only
`pending -> assigned` and leaves every other status alone (`scheduler.py:796-797`).

So a task returned for revision is claimed and briefed **at `revision_needed`**. And
`TRANSITIONS["revision_needed"]` offers `in_progress` and nothing else but operator rejection
(`task_transitions.py:143-146`). A briefing that named `completed` as the next call would describe a
call the machine refuses — the exact defect this change exists to remove, reintroduced by the fix.

The rule is therefore derived from the status rather than branched on two cases:

| Arrival status | What the briefing names |
|---|---|
| `assigned` | move it to `in_progress` when you start, then `completed` when the work is done |
| `revision_needed` | the same two steps — the edge back into `in_progress` is the one that exists |
| `in_progress` | `completed` |

One condition — *is the task already `in_progress`?* — covers all three, and it happens to be
exactly what `TRANSITIONS` says, so it cannot drift from the map without a test noticing.

## D8 — the loop's own message follows the briefing, and on a review turn it speaks to the wrong turn

Round 1 treated the briefing as the whole composed text. It is not:
`content = f"{briefing}\n{job.message}"` at **both** call sites (`scheduler.py:2367`, `:2719`), and
`job.message` is the operator's standing message for the loop, authored once and delivered on every
firing. In F143's own transcript it was:

> *"Work the task you have been given. Keep the edit minimal."*

— delivered **to a reviewer**, immediately after the briefing, on the same turn. A perfect review
briefing does not reach it.

Rewriting `job.message` is not available and should not be: the function's docstring already states
why — *"the operator's own message template still reads exactly as authored"* — and a conversation
that later shows the operator saying something they did not say is a worse defect than the one being
fixed.

So the review branch **pre-empts** it in one sentence: what follows this briefing is the loop's
standing message to its ordinary firings, and it does not describe this turn. Cheap, honest, and it
leaves the operator's text untouched.

## D9 — the review briefing does not name the commit, and the harness check that wants it is wrong

`scripts/drive/t_row12_review_leg.py:331-334` asserts *"the briefing names the commit under
review"*. It currently fails, and round 1's task 5.3 said not to satisfy it without saying why. The
reason:

**The briefing cannot know the commit.** It is composed at firing time by the scheduler; the commit
is resolved at spawn time by `commit_for_task_review` inside `prepare_review_turn`
(`review_turn.py:196`), one step later and in another module. The scheduler could call it, but the
two calls would then answer at two different instants — and the case where they differ is real
enough that the product already handles it: `ReviewContext.work_moved` exists precisely for evidence
that moved, and `agents.py:1165-1172` tells the reviewer about it on the channel that resolved it.

A commit named in the briefing is therefore a second copy of a fact that can disagree with the
checkout the reviewer is standing in. The harness check is corrected rather than satisfied.

## D10 — the two channels always coexist, so D5's duplication is duplication, not a fallback

Round 1 assumed, without checking, that a review briefing always arrives beside the review context.
It does, and the mechanism is worth recording because it is load-bearing for D5:

- `_review_task_from_entries` (`agent_trigger.py:379-409`) derives `review_task_id` from the queued
  entries, so a queued review briefing makes the next turn a review turn — it cannot be delivered
  onto an ordinary turn, and a turn that batches a review with ordinary work is refused by name.
- If the checkout cannot be provisioned, `ReviewTurnRefused` becomes a `409` and **the turn does not
  start at all** (`agent_trigger.py:793-795`). There is no path on which a reviewer receives the
  briefing with no review context beside it.

So D5's duplication is not insurance against a missing channel. It rests only on F45's and F140's
measurements — that the briefing is the channel that drives tool calls — and that is enough, but it
is the whole of the argument.

## D11 — an existing test constrains every word the loop branch may gain

`test_flow_width.py:600-604` asserts, over a document-less loop's **entire** briefing:

```python
assert "review" not in briefing.lower()
assert "flow" not in briefing.lower()
```

Whole-string absence, not a scoped check. It is the executable form of `agent-flows:314`'s second
scenario and must not be weakened. Every sentence the loop branch gains has to clear both words —
so no *"enters review"*, no *"review_state"*, and no *"workflow"*. Stated here because it is the
kind of constraint that is discovered by a red test at the end of an implementation rather than
designed for at the start.

It also settles a question round 1 left implicit: a document-less loop **can** staff a review
(`spec_document_id` appears exactly once in `scheduler.py`, at `:1764`, inside the briefing's own
tier branch — neither `decide_firing` nor `resolve_reviewer` consults it), so that loop's *review*
briefing necessarily contains the word "review". That is not a breach of the scenario above, which
is about a briefing claiming something will route the work onward. The test exercises a non-review
firing and keeps meaning exactly what it means today.

## D12 — the evidence sentence must survive change C

Round 1's wording for the evidence line — *"approved work merges nothing until the evidence is
accepted"* — is true today and becomes **false** when change C lands, because C refuses approval
outright while evidence sits unaccepted, rather than approving and merging nothing.

The briefing must be worded so that it is true before and after: what is recorded enters `awaiting`,
somebody else decides on it, and the work cannot land until they do. That claim holds under both
regimes and needs no second edit when C ships.
