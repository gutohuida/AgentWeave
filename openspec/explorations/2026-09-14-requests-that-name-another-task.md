# Requests that name another task

**2026-09-14, day window, I-1 brief 4 of 11.** This is an improvement brief, not a proposal: there
is no change directory and no tasks. Source: `spec-queue/observations/2026-09-14-LoopEngine.md`,
`## Improvements` item 4, `#### dev` item 4 and `#### dev_2` items 1 and 2.

## What we saw

A run takes one task. Peer messages kept asking for work on a different one.
- **The refusal, twice.** *"This run cannot claim task task-0c07b268b9e5: it is already working task
  task-9b60162f5804. A run finishes the task it took, and takes at most one."* (`5defd7fe` 19:19,
  `05a22a80` 19:25). The rule is deliberate (`openspec/specs/run-task-binding`, *"A run carries at
  most one task binding"*; `hub/hub/task_transition_service.py:510-531`).
- **By then the work had landed on the wrong branch.** A peer turn bound to one task asked `dev` to
  fix something on another. `dev` did the work in the first task's workspace, could not move the
  second task, and `tester` rejected both evidence rows as on the wrong branch (`ev-91fc82a39196`,
  `ev-e3407121b5d8`).
- **Three more turns ended stuck** saying the work belonged to another task's session (`4a419275`
  21:22, `9935088b` 23:48, `be4ae6db` 00:01).
- **The message decides the workspace, not the recipient's role.** The Architect's
  `entry-b71caee8b603` carried `dev`'s task id and woke `dev_2` in
  `.agentweave/tasks/task-9b60162f5804`. Its next two turns ran there too. `dev_2` sensibly declined
  to touch it.
  - The mechanism: the entry takes the message's task id (`hub/hub/api/v1/messages.py:267`), and
    `resolve_bound_task` takes the delegated task first (`run_task_binding.py:356-415`).
  - The workspace follows the task (`agent_trigger.py:901-954`), and nothing consults
    `Task.assignee` (the comment at `:916` says so).
  - The only refusal is another agent's running turn on the same task, a transient 409
    (`:932-944`).
- **Two agents fixed the same thing in parallel.** `tester`'s rejection of FR-60 reached `dev_2` as
  reviewer of `task-b8e8b7f3beca`, while the Architect opened `task-9b60162f5804` for `dev`. Both
  wrote the fix. `dev_2` concluded, on its own, that it should check `list_tasks` before fixing
  anything.

## What would change

There are three parts, each small, and they are separable.
1. **A message is not a claim.** A message that names a task the recipient neither holds nor
   reviews wakes the recipient in its own workspace. The task id travels as context, not as a
   binding.
2. **A second request has somewhere to go.** A run asked for work on another task can queue that
   request for its own next turn, bound to that task. That could be `send_message` to itself with a
   task id, if the Hub admits it (unverified today), or a named "follow up on task X" action. The
   refusal sentence would then name the way out, not only the rule.
3. **Work already in hand is visible before it is duplicated.** The briefing for a fix turn names
   any open task that touches the same requirement.

## Why it matters

The one-task rule is what keeps a branch's history honest, and it should stay. What is missing is
everything around it. On LoopEngine it cost two refused claims, three more stuck turns, two
rejected evidence rows, one duplicated fix, and three of `dev_2`'s turns in a checkout that was not
its own. Every multi-agent
project with a coordinator meets this, because a coordinator's messages naturally carry "also, on
task X…".

## Rough cost — a code-read estimate

- **Part 1:** `hub/hub/run_task_binding.py` (`resolve_bound_task`) and the workspace choice in
  `hub/hub/api/v1/agent_trigger.py:901-954`. It changes an input to binding, so it must not reopen
  the one-writer-per-checkout invariant (design D8, the comment at `:914-925`). No migration.
- **Part 2:** the messages route (`hub/hub/api/v1/messages.py`), the refusal text
  (`task_transition_service.py:527-531`), and an MCP surface in `hub/hub/mcp_server.py`, **which
  F354 keeps out today**. No migration if it is a queue entry carrying a task id, which the column
  already allows.
- **Part 3:** the briefing, in `hub/hub/api/v1/agents.py` and the scheduler's flow briefings. It
  needs "which requirement does this task touch", which the evidence and requirement links already
  hold.
- **Capabilities:** `openspec/specs/run-task-binding`, `workspace-isolation`, `agent-flows`, and
  `agent-capability-plane` (`send_message`).
- **API shape:** possibly one field on the message route. No UI.

## Risks and open questions

- **Part 1 may break a use that works.** An operator or coordinator may *want* a message to hand a
  task to someone. Where handing over is intended, the fix is an explicit assignment, not a side
  effect of a message. The operator should confirm that reading.
- **Self-queued follow-ups can loop.** They spend the hop budget, which was reached 21 times on
  LoopEngine. Should a follow-up count as a hop?
- **Part 3's signal is noisy.** A requirement touched by two tasks is not always duplicated work.
  It must stay a note, never a refusal.
- **Unverified:**
  - whether `send_message` to oneself is admitted today;
  - whether the four pending `dev_2` tasks duplicate each other beyond their titles, which O-2 did
    not read.

## The decision, in one line

Approve a spec loop for part 1, *a message that names a task does not bind a recipient who does not
hold it*, which can be built without `mcp_server.py`. Hold parts 2 and 3 for a day after F354.
