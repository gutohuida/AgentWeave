# run-task-binding

## Purpose

Which task a run is working on, who decides that, what binding does to the task's status, and what
happens when a run ends holding work nobody moved.

Established by `openspec/changes/2026-08-10-run-task-binding/`. Before it, `Run` carried project,
agent, session, conversation, pid and heartbeat and nothing about the work, so a task's status
stayed current only if an agent remembered to say so — not a discipline problem but a missing edge
in the data model.

Where `task-lifecycle-governance` governs **validity** — that a recorded transition is legal,
attributed, and made by an entitled actor — this capability governs **liveness**: that a transition
happens at all when reality changes. B1 made it impossible to record a wrong transition and could
do nothing about a missing one, because an agent that does the work and never touches the ledger
asks for nothing and so passes every check.

Both mechanisms sit at boundaries AgentWeave owns for every runner — process start and process end
— rather than inside any agent, which is what makes them enforcement rather than instruction, and
why no part of this depends on a runner hook.

It is also the prerequisite for B3: evidence is produced *by a run*, about *a task*, and that edge
did not exist.
## Requirements
### Requirement: A run carries at most one task binding

The system SHALL record, on each run, the single task that run was started for, or nothing. A run
SHALL NOT be bound to more than one task.

A run with no binding is legitimate: exploration, conversation, questions, and scheduled work are
real work with no task.

#### Scenario: A run started for a task records it

- **WHEN** a run is started from a cause that names a task
- **THEN** the run durably identifies that task
- **AND** the binding is readable for the run's whole life and after it ends

#### Scenario: A run started without a cause naming a task is unbound

- **WHEN** the operator starts a run by talking to an agent, or a scheduled job triggers one
- **THEN** the run records no task
- **AND** the run is not subject to any check that depends on a binding

#### Scenario: A second task cannot be added to a bound run

- **WHEN** anything attempts to bind a second task to a run that is already bound
- **THEN** no such path exists

### Requirement: Only the runtime binds a run to a task

The system SHALL set a run's binding itself, from the cause that started the run. No agent-facing
operation — over HTTP or MCP — SHALL create, change, or remove a run's binding.

An enforcement mechanism its subject can decline is not enforcement: an agent able to bind itself is
an agent able to never bind, and an unbound run is never divergent.

#### Scenario: The agent surface offers no binding operation

- **WHEN** an agent enumerates the operations available to it
- **THEN** no operation binds a run to a task, rebinds it, or clears a binding

#### Scenario: An agent cannot escape a binding the runtime made

- **WHEN** a run is bound and the agent attempts to remove or change that binding by any available
  means
- **THEN** the binding is unchanged

### Requirement: A run started to review a task binds to that task

The system SHALL bind a run started to review a task to the task under review, by the same binding
the runtime already performs for a run started to work a task, and SHALL NOT require a second
mechanism to do it.

A review turn is not one of the causes for which an unbound run is legitimate. Exploration,
conversation, questions and scheduled work have no task; a review has exactly one, and it is the
task whose work is being judged.

The instruction that gives a review turn its workspace SHALL remain distinct from the binding.
Selecting which commit a reviewer checks out and recording which task a run is about are different
questions, and a single value answering both would make an entry's two purposes inseparable.

Binding a review SHALL NOT move the task. The transitions available to a run from a task under
review do not include starting it, so binding records the association and changes no status.

Where a turn delivers both an item of work and a review, the binding SHALL be determined
deterministically by the same ordering already used to select among several items naming a task.

#### Scenario: A review run records the task it is reviewing

- **WHEN** a run is started to review a task
- **THEN** the run durably identifies that task
- **AND** the binding is readable for the run's whole life and after it ends

#### Scenario: Binding a review does not start the task

- **WHEN** a run binds to a task that is under review
- **THEN** the task's status is unchanged
- **AND** the task's assignee is unchanged

#### Scenario: A review turn is subject to the run boundary

- **WHEN** a run bound to a task under review ends
- **THEN** the boundary determination is performed for it, as for any other bound run

#### Scenario: The workspace instruction and the binding stay separate

- **WHEN** a review turn is prepared
- **THEN** the value selecting the commit to check out and the value recording the bound task are
  distinct
- **AND** neither is derived by reinterpreting the other

#### Scenario: A turn carrying both work and a review binds deterministically

- **WHEN** a turn delivers an item naming a task for work and an item naming a task for review
- **THEN** the run binds to exactly one of them
- **AND** the same input always produces the same binding

### Requirement: A delegation that names a task binds the run that receives it

The system SHALL carry a task named on an agent-to-agent delegation through the receiving agent's
inbound queue and onto the run that delivers it.

The task id SHALL be validated against the sending run's project when the delegation is made. A task
id that does not resolve SHALL be refused with a message naming the problem, and the delegation
SHALL still be deliverable without a binding rather than lost.

#### Scenario: A delegated task reaches the receiving run

- **WHEN** an agent delegates work naming a task in its project
- **AND** the receiving agent's next turn delivers that item
- **THEN** the receiving run is bound to that task

#### Scenario: An unresolvable task id is refused, not silently dropped

- **WHEN** a delegation names a task that does not exist or belongs to another project
- **THEN** the caller receives an error naming which task id failed and why

#### Scenario: Several delivered items naming different tasks resolve deterministically

- **WHEN** one turn delivers several queued items and more than one names a task
- **THEN** the run is bound to the task named by the earliest queued item that names one
- **AND** the same delivery always produces the same binding

### Requirement: The operator can start a bound run from a task

The system SHALL let the operator start work on a task directly from the task, producing a run bound
to it.

#### Scenario: Starting work from a task binds the run

- **WHEN** the operator starts work on a task and names the agent
- **THEN** a run for that agent is started bound to that task

#### Scenario: The binding is visible to the operator

- **WHEN** the operator views a run
- **THEN** the task it is bound to is shown, or its absence is evident

### Requirement: Binding advances the task without asking the agent

The system SHALL, when binding a run to a task from whose current status an agent run may reach
`in_progress`, move the task to `in_progress` and attribute the move to the binding run.

The move SHALL be applied through the same transition machine that governs every other status
change, so no legality rule, actor rule, or later gate is bypassed by the runtime path.

#### Scenario: A pending task starts when a run binds to it

- **WHEN** a run binds to a task in `pending` or `assigned`
- **THEN** the task moves to `in_progress`
- **AND** the transition is recorded naming the binding run and its agent
- **AND** the agent was not asked to make it

#### Scenario: A task already in progress is not moved again

- **WHEN** a run binds to a task already in `in_progress`
- **THEN** no transition is recorded

#### Scenario: Binding a task with no legal path to in_progress still binds

- **WHEN** a run binds to a task in a status from which an agent run cannot reach `in_progress`
- **THEN** the run is bound
- **AND** no transition is recorded
- **AND** the binding is not refused

#### Scenario: The runtime cannot make a move an agent run could not

- **WHEN** the runtime attempts the automatic move
- **THEN** it is subject to the same legality check as an agent-requested move

### Requirement: A run that ends without moving its task is divergent

The system SHALL determine, when a bound run ends, whether that run caused any status transition of
its bound task other than the runtime's own automatic one. A bound run that caused none SHALL be
recorded as divergent.

The determination SHALL be made at the run boundary — which the system owns for every runner —
rather than inside the agent, and SHALL NOT depend on any runner-specific mechanism.

A run's exit status SHALL NOT affect whether it is checked. A run that crashed, failed, or was
interrupted is still a run that ended holding a task nobody moved; the record SHALL name the exit
status so that a crash is distinguishable from a completed run that forgot.

A run whose queued input was returned to the queue SHALL NOT be recorded as divergent. That input
is about to be delivered to a new run bound to the same task, so nothing has been dropped —
recording a divergence would misdescribe it, and under an active policy would start a run racing
the redelivery.

#### Scenario: A run that completes its task is not divergent

- **WHEN** a bound run moves its task to `completed` and ends
- **THEN** no divergence is recorded

#### Scenario: A run that ends having moved nothing is divergent

- **WHEN** a bound run ends and the only transition it caused was the automatic one made when it was
  bound
- **THEN** a divergence is recorded naming the run, the task, the task's status at run end, and the
  run's exit status

#### Scenario: An unbound run is never divergent

- **WHEN** a run with no binding ends
- **THEN** no divergence is recorded

#### Scenario: A crashed run is checked like any other

- **WHEN** a bound run's process dies and the run is later reconciled to an ended state
- **AND** it had no queued input to return
- **THEN** the divergence check is performed
- **AND** the record names the exit status

#### Scenario: Work handed back to the queue is not a divergence

- **WHEN** a bound run ends and its delivered input is returned to the agent's queue
- **THEN** no divergence is recorded
- **AND** no run is started in response

#### Scenario: A divergence closes when the work reaches the ledger

- **WHEN** an open divergence exists for a task and any actor later moves that task
- **THEN** the divergence is recorded as resolved
- **AND** the record of it having occurred is retained

### Requirement: Every divergence is recorded durably

The system SHALL persist one immutable record per divergence, naming the run, the task, the policy
applied, the outcome, and the run started in response where one was. Records MUST NOT be updated
except to mark resolution, and MUST NOT be deleted by any application path.

Broadcasting a divergence is not sufficient: the operator SHALL be able to see divergences that
occurred while they were not watching, and to ask how often an agent has diverged.

#### Scenario: A divergence survives the session it happened in

- **WHEN** a divergence occurs and the operator later opens the project
- **THEN** the divergence is visible with its task, run, policy, and outcome

#### Scenario: Ordering is exact

- **WHEN** several divergences are recorded within the same instant
- **THEN** reading them back yields the order in which they occurred

### Requirement: The response to a divergence is a policy set per task

The system SHALL let each task carry a divergence policy of `surface`, `retry`, or `escalate`, and
an escalation agent. A task with no policy set SHALL be treated as `surface`.

`surface` SHALL record and display the divergence and start nothing. `retry` SHALL start one further
run of the same agent, bound to the same task. `escalate` SHALL reassign the task to its escalation
agent and start a run of that agent, bound to the same task.

Defaulting to `surface` is required, not incidental: shipping this capability SHALL NOT cause any
existing task to start runs nobody asked for.

**The policy governs runs started to work a task, and SHALL NOT govern runs started to review one.**
A task carries one policy and, once review runs bind, can be the subject of two different failures —
work that was not done and a judgement that was not given — whose remedies are not the same. Applying
a policy chosen for the first to the second would act on the operator's behalf in a way they did not
ask for, and nothing would say it had happened.

`retry` is additionally redundant for a review: a run whose input was returned to the queue is
already re-delivered, and that is what answers a review whose process died. What remains for `retry`
to act on is a reviewer that completed its turn and gave no verdict, where running the same reviewer
against the same work is the least likely response to change the outcome.

How a review that records no verdict is answered is stated by the capability that owns flows, not
here.

#### Scenario: The default starts nothing

- **WHEN** a run bound to a task with no policy set diverges
- **THEN** the divergence is recorded and displayed
- **AND** no run is started

#### Scenario: Retry runs the same agent again

- **WHEN** a run bound to a task whose policy is `retry` diverges
- **THEN** one further run of the same agent is started bound to that task
- **AND** that run is given the task, its current status, and the transitions available to it

#### Scenario: Escalation routes the work to another agent

- **WHEN** a run bound to a task whose policy is `escalate` diverges
- **AND** the task names an escalation agent
- **THEN** the task is reassigned to that agent
- **AND** a run of that agent is started bound to the task
- **AND** the previous assignee is recorded

#### Scenario: Escalation with no agent named falls back

- **WHEN** a task whose policy is `escalate` names no escalation agent
- **THEN** the divergence is surfaced
- **AND** no run is started

#### Scenario: A review is not retried by the task's policy

- **WHEN** a run started to review a task whose policy is `retry` ends without recording a verdict
- **THEN** no further run is started by that policy

#### Scenario: A review is not escalated by the task's policy

- **WHEN** a run started to review a task whose policy is `escalate` ends without recording a verdict
- **AND** the task names an escalation agent
- **THEN** the task is not reassigned to that agent by that policy
- **AND** no run is started by that policy

### Requirement: A divergence response runs at most one hop

The system SHALL record, on a run started in response to a divergence, the run whose divergence
caused it. A run carrying that reference SHALL NOT itself trigger a retry, and SHALL NOT trigger an
escalation unless it was itself started by a retry.

A `retry` whose own run diverges SHALL fall through to `escalate` when the task names an escalation
agent, and to `surface` otherwise. No sequence of divergences SHALL be able to start an unbounded
number of runs: a chain SHALL start at most one retry and at most one escalation before surfacing.

The escalation limit is required, not incidental. An escalated run's task still carries the same
policy and the same escalation agent, so without it a divergence of that run escalates to the same
agent again, and does so forever.

The bound applies to a chain, not to a task's lifetime: a run that makes real progress ends the
chain, and a later independent run that diverges may retry again.

#### Scenario: A retry that also diverges does not retry again

- **WHEN** a run started in response to a divergence itself diverges
- **THEN** no further retry is started

#### Scenario: A retry that diverges escalates when it can

- **WHEN** a run started by `retry` diverges
- **AND** the task names an escalation agent
- **THEN** the work is escalated to that agent

#### Scenario: An escalated run that diverges does not escalate again

- **WHEN** a run started by `escalate` itself diverges
- **AND** the task still names the same escalation agent
- **THEN** the divergence is surfaced
- **AND** no further run is started

#### Scenario: Progress resets the chain

- **WHEN** a run started in response to a divergence moves its task
- **AND** a later independent run bound to the same task diverges
- **THEN** that later divergence is answered by the task's policy in full, including retry

### Requirement: The operator sets and sees divergence handling where the task is

The system SHALL let the operator read and change a task's divergence policy and escalation agent
from the task itself, and SHALL show on the task that a divergence has occurred and whether it is
still open.

#### Scenario: Policy is editable from the task

- **WHEN** the operator opens a task
- **THEN** its divergence policy and escalation agent are visible and changeable there

#### Scenario: An escalation agent is chosen from the project's agents

- **WHEN** the operator sets an escalation agent
- **THEN** the choices offered are agents that exist in the project

#### Scenario: An open divergence is visible on the task

- **WHEN** a task has an unresolved divergence
- **THEN** the task shows it
- **AND** the indicator clears when the divergence resolves

### Requirement: A conversation carries the binding, and its runs inherit it

The system SHALL record a task binding on the conversation, and SHALL bind a run started in that
conversation to it when nothing more specific applies.

Work spans more turns than a run does. With the binding held only per run, a conversation's first
turn is checked at its boundary and every later turn is not — including the turn where the agent
actually stops, which is the only one at which "did this ever reach the ledger?" has a useful
answer.

An input that names its own task SHALL take precedence and SHALL rebind the conversation, so that
delegating different work into an existing thread is not silently attributed to the old task.

Each run SHALL still record the task it was bound to. Transitions and divergences are attributed to
a run, and an integrity record that had to be joined through a conversation to say what it was about
would depend on a row that may be archived.

#### Scenario: A follow-up turn is checked like the first

- **WHEN** work is started on a task in a conversation
- **AND** the operator sends a further message into that conversation
- **THEN** the run that message starts is bound to the same task
- **AND** it is subject to the run-boundary check

#### Scenario: Naming a different task rebinds the conversation

- **WHEN** an input naming a task is delivered into a conversation bound to another task
- **THEN** the run is bound to the newly named task
- **AND** the conversation's binding becomes that task

#### Scenario: An unbound conversation stays unbound

- **WHEN** a conversation has no binding and its inputs name no task
- **THEN** its runs are unbound and are not checked

#### Scenario: The run's own record is unchanged

- **WHEN** a run inherits its binding from its conversation
- **THEN** the run records the task it was bound to
- **AND** transitions it causes are attributed to it as before

### Requirement: A conversation's binding can be released

The system SHALL let the operator release a conversation's binding, and SHALL release it
automatically when the bound task reaches a status from which no further work is expected.

A binding SHALL NOT be released by inferring what the operator now seems to be discussing. A wrong
inference silently stops checking runs, and a mechanism that quietly stops enforcing is worse than
one that never started.

#### Scenario: The operator releases a binding

- **WHEN** the operator releases a conversation's binding
- **THEN** subsequent runs in that conversation are unbound

#### Scenario: Finished work releases its conversation

- **WHEN** a bound task reaches a status from which no further work is expected
- **THEN** the conversation's binding is released

#### Scenario: Changing subject does not release a binding

- **WHEN** the operator discusses something else in a bound conversation without releasing it
- **THEN** the binding is unchanged
- **AND** runs continue to be checked

### Requirement: A task recorded as waiting is not divergent

The system SHALL NOT record a divergence for a run whose bound task is waiting on a person.

Divergence means work was dropped with no account of why. A waiting task has an account, and it
names someone who can act on it. Answering a divergence with a retry would restart an agent that is
still waiting for the same thing.

#### Scenario: A run that ended waiting is not divergent

- **WHEN** a bound run ends and its task is recorded as waiting
- **THEN** no divergence is recorded
- **AND** no run is started in response

#### Scenario: The task still shows as needing attention

- **WHEN** a task is waiting on a person
- **THEN** the operator can see that it is waiting, and what for

#### Scenario: Once released, the check applies again

- **WHEN** a waiting task is released and a later bound run ends without moving it
- **THEN** that run is divergent as normal

### Requirement: Starting a run does not release a waiting task

Binding a run to a task that is waiting on a person SHALL leave that task waiting. The system SHALL
NOT move it back to the in-progress status as a consequence of a run starting.

The edge out of the waiting status exists, so without this rule the act of starting a run would
release the block — and that run's end would then find the task no longer waiting and record a
divergence against work that was never dropped. A block ends when the answer arrives or the operator
ends it, never because something started.

#### Scenario: A run bound to a waiting task leaves it waiting

- **WHEN** a run is bound to a task that is waiting on a person
- **THEN** the run records the task
- **AND** the task is still waiting

#### Scenario: A later turn on a waiting task is not divergent

- **WHEN** a further run in a bound conversation ends while its task is still waiting
- **THEN** no divergence is recorded

### Requirement: An answer reaches an asker whose run has ended

Where a blocking question is answered after the run that asked it has ended, the system SHALL
deliver the answer as queued input rather than relying on the asking run to receive it as a result.

A blocking ask holds its run open only while that run lives. A question that outlived its run — it
timed out, or the run failed — has nobody waiting to receive the answer, and that is precisely the
question that caused a task to be recorded as waiting. An answer that reaches no one leaves the
operator believing they have unblocked work that is still stopped.

Where the system cannot establish that the asking run has ended, it SHALL assume the asker is still
waiting. Delivering a duplicate costs a turn; assuming wrongly in the other direction loses the
answer.

#### Scenario: The answer is queued when the asker has ended

- **WHEN** a blocking question is answered after its asking run has ended
- **THEN** the answer is queued for the agent

#### Scenario: The answer is not duplicated for an asker still waiting

- **WHEN** a blocking question is answered while its asking run is still open
- **THEN** the answer is not also queued

### Requirement: Every question that parks a task SHALL record which task it parked

A blocking question asked about a task that is already waiting SHALL record that task, so that
answering that question releases the block. Recording which task a question is about SHALL NOT depend
on that question being the one that moved the task into waiting.

Today the recording happens only as a side effect of the transition into the waiting status, and a
task already waiting has no such transition to make — the status is not a target of itself. So a
second question about the same task records nothing, and answering it releases nothing. The operator
answers the question in front of them and the task stays waiting; only answering the older question
works, and nothing tells them that.

This SHALL NOT change which transitions are legal. Recording what a question is about and moving a
task are different facts, and only one of them needs an edge in the transition map.

#### Scenario: A second question about a waiting task records it

- **GIVEN** a task already waiting on a person
- **WHEN** a run asks a further blocking question about that same task
- **THEN** that question records the task it is waiting on

#### Scenario: Answering the second question releases the task

- **GIVEN** a waiting task with more than one blocking question recorded against it
- **WHEN** the most recent of those questions is answered
- **THEN** the task is released

#### Scenario: The transition map is unchanged

- **WHEN** a question is asked about a task that is already waiting
- **THEN** the task's status is not transitioned
- **AND** no transition into the waiting status from itself is permitted

#### Scenario: A question about an unrelated task releases nothing

- **GIVEN** a waiting task and a blocking question about a different task
- **WHEN** that question is answered
- **THEN** the waiting task is not released

### Requirement: Claiming an unheld task binds the run to it

A run that moves a task it does not hold into `in_progress` SHALL become bound to that task. A run
that already holds a different task SHALL be refused, preserving the existing invariant that a run
carries at most one task binding.

This is what makes "go and find waiting work" — the behaviour the Developer charter asks for — a
claim rather than an observation. Without it, the one fact that separates *"I finished this"* from
*"I noticed this"* is never recorded.

#### Scenario: An unbound run claims a waiting task
- **WHEN** a run carrying no task binding moves a `pending` task to `in_progress`
- **THEN** the run SHALL become bound to that task
- **AND** the transition SHALL be permitted

#### Scenario: A run that already holds a task tries to claim a second
- **WHEN** a run bound to task A moves task B to `in_progress`
- **THEN** the transition SHALL be refused
- **AND** the refusal SHALL name the task the run is already bound to

#### Scenario: The operator is unaffected
- **WHEN** the operator moves a task to `in_progress`
- **THEN** no binding SHALL be required or created
- **AND** the transition SHALL be permitted

#### Scenario: The runtime binding path is unchanged
- **WHEN** the runtime binds a run to a task and starts it
- **THEN** the run SHALL already be bound when the transition is evaluated
- **AND** the transition SHALL be permitted
