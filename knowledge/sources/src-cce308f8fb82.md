# Request: a spec task can name the agent that builds it

Operator request, 2026-10-28. Raised while setting up the build of the change document
`spec/changes/vault-sources-can-be-edited-replaced-and-archived`. The operator named it the next
development after that build.

## The problem

- A task in a change document has no builder field. The only per-task override is `reviewer`,
  which overrides `delivery.reviewer`.
- A flow's `agent` is a default, not a mandate. Each firing hands a ready task to any free agent.
- The operator found no way, on the task screen, to assign or reassign a task to an agent.
- So there is no way to say "DeveloperOpus (Opus) builds this one subtle task, Developer (Sonnet)
  builds the rest". For the vault-editing build the operator kept every task on Sonnet, so as not
  to overcomplicate it.

## A workaround that was considered and rejected

Telling the Developer, in the task text, to delegate the task to DeveloperOpus by message does not work.

- The delegate's code lands on its own branch, not on the task's branch.
- The task's ownership, its review and its merge stay with the agent that originally held it.
- It depends on the first agent following the instruction, and it costs an extra turn.

## Scope to consider when it is specified

- A per-task builder in a change document's tasks. The flow honours it the way it honours a task's
  `reviewer`.
- Assigning or reassigning a task to an agent from the task screen.

Backlog task: task-1a1012427726 ("Spec tasks can name the agent who builds them").
