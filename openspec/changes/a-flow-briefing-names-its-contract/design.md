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
