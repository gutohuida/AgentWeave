## Why

Two findings from the operator's first read of the run→task binding
(`openspec/changes/2026-08-10-run-task-binding/`, 2026-08-10). Both are gaps in the same mechanism,
and both are lifecycle changes rather than adjustments, which is why they are proposed rather than
patched in.

**A task has no way to say it is waiting on a human.** The operator, on the divergence policy:
*"What if an agent has a question about the implementation that was not foreseen… the task will
remain unchanged after the turn is done. Maybe we need a blocked state waiting for something from
the user."* They are right, and it is worse than cosmetic: an agent that correctly stops and asks is
currently indistinguishable from one that dropped the work. The run ends, the task has not moved, a
divergence is recorded — and under `retry` the agent is started again while still blocked on the
same unanswered question. `Question` (`hub/hub/db/models.py:714-715`) already carries `answered` and
`blocking`, so the runtime knows; the lifecycle has no status that can express it. The eight
statuses in `hub/hub/task_transitions.py:101-136` include none.

**Only the first run of a conversation is bound.** Starting work from a board card sends `task_id`;
a follow-up typed into the composer does not (`AgentOutputPanel.tsx` `postTrigger` has no `task_id`),
and nothing carries a binding across turns — not `turn_scheduler.py`, not `conversations.py`. So a
five-turn piece of work is checked once, at the end of turn one, and is invisible for the rest —
including the turn where the agent actually stops.

That is the wrong way round twice over. Turn one is when an agent is *most* legitimately unfinished,
so it is where a divergence is least informative; and the final turn, where "did it ever reach the
ledger?" is exactly the right question, is not asked at all. The mechanism is noisiest where it
matters least and silent where it matters most.

## What Changes

- **A `blocked` status**, reachable from `in_progress`, meaning the work cannot proceed until
  someone outside the run supplies something.
- **The runtime blocks the task, the answer unblocks it.** An agent does not assert `blocked` and
  then assert its way out: a run that ends with an unanswered blocking question open moves its task
  to `blocked`, and the question being answered moves it back. Same shape as the automatic
  `in_progress` on binding — derived, not remembered.
- **A blocked task is not divergent.** It has an explanation, and the explanation is a row someone
  can act on. This supersedes the narrower fix considered and set aside on 2026-08-10 (exempting a
  run that ends with a question open): an exemption records nothing, where a status says on the
  board what is true and who is holding it up.
- **The binding lives on the conversation**, so continuation turns inherit it and the boundary check
  reaches the turn where the agent actually stops. `Run.task_id` stays as the per-run record — it is
  what transitions and divergences are attributed to.
- **A conversation's binding can be released**, or the operator cannot ever talk to an agent about
  something else in the same thread.
- **The operator can block and unblock a task themselves**, because not every blocker is a question
  an agent asked.

### Non-Goals

- **A general "waiting on anything" state.** `blocked` here means blocked on a *human*. Waiting on
  another agent is delegation and already has a shape; waiting on CI or a build is B3's evidence
  model.
- **Blocking the whole conversation.** The task is blocked; the agent may still be talked to.
- **Reopening the retry/escalate bound.** A blocked task simply does not reach the policy.
- **Auto-releasing a conversation's binding by inference** — "the operator seems to be talking about
  something else now" is a guess, and a wrong guess silently stops checking a run.
- **Backfilling a binding onto conversations that already exist.**

## Capabilities

### New Capabilities

*(none — both changes land in capabilities that already exist)*

### Modified Capabilities

- `task-lifecycle-governance`: a ninth status, its edges, and who may take them; the rule that a
  blocked task is waiting on a named someone rather than on nobody.
- `run-task-binding`: the binding is inherited from the conversation; a blocked task is not
  divergent; releasing a binding.
- `agent-capability-plane`: an agent may not declare its own task blocked or unblocked — the same
  rule, and the same reason, as its not being able to bind its own run or set its own divergence
  policy.

## Impact

**Schema** — `conversations.task_id`; a link from the blocking `Question` to the task it blocked, so
answering it knows what to release. Migrations `0059`+, guarded, with both head assertions bumped.

**Backend** — `hub/hub/task_transitions.py` (the map grows a status and its edges — the first change
to it since B1); `hub/hub/run_task_binding.py`; `hub/hub/run_divergence.py`; `hub/hub/api/v1/questions.py`
(answering releases); `hub/hub/api/v1/agent_trigger.py` (inherit and record); `hub/hub/api/v1/tasks.py`.

**Frontend** — the board gains a ninth column or a blocked treatment; the card says what it is
waiting for and offers unblocking; the composer's turn inherits the binding.

**Risk, and the reason this is a proposal.** `task_transitions.TRANSITIONS` is what B3's evidence
checks and B4's completion gates will be written against. Adding a status is cheap now and expensive
after those exist, so the edges want deciding deliberately — in particular whether `blocked → completed`
is legal (it should not be) and whether a blocked task may be rejected or reassigned (it should).

Conversation-level binding has the larger blast radius: **every composer turn in a bound
conversation becomes a checked run.** That is the point, and it is also what makes the noise
question from the previous change real for the first time — so the two should ship together, or the
second will be judged on a mechanism the first has not yet corrected.
