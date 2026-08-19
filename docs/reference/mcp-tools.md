# Agent Tool Surface

The Hub exposes one identity-bound tool surface and injects its stdio configuration whenever it
starts a compatible Claude or Codex runner. There is nothing to install and no client configuration
to edit.

Turn-start state is already in the prompt: delivered queue entries, the roster, the charter, project
instructions, and any open specification document. **The surface carries outbound intent only** —
there is no tool for reading your inbox, because everything addressed to you is already in front of
you.

## Collaboration

| Tool | Purpose |
|------|---------|
| `send_message(to_agent, subject, content, message_type=message, task_id=None)` | Queue an attributable peer message, under the hop budget |
| `request_agent(name, template, task)` | Create an agent from a pre-approved template, under the project agent budget |

## Tasks

| Tool | Purpose |
|------|---------|
| `create_task(title, description, assignee, priority=medium, requirements, ...)` | Create a task attributed to the bound agent |
| `list_tasks(agent=None)` | Read the shared task ledger |
| `get_task(task_id)` | Read one ledger entry |
| `update_task(task_id, status)` | Move a task through its lifecycle; `status` is required |

## Asking the operator

| Tool | Purpose |
|------|---------|
| `ask_user(questions)` | Put 1–4 structured decisions to the operator and **block** until answered |
| `get_answer(question_id)` | Check a question you asked non-blocking |

## Specifications and evidence

| Tool | Purpose |
|------|---------|
| `submit_spec_document(path, title, kind, summary, problem, design, lifecycle, scope, ...)` | Write a specification document. Never author specification markup by hand — the Hub renders it and mints requirement identifiers |
| `read_spec_document(path)` | Read a document. Use before writing to one |
| `rename_spec_document(path, subject)` | Rename a document once its subject is actually known |
| `record_evidence(identifier, summary)` | Record what demonstrates a requirement is satisfied. Enters `awaiting` — what you record is a claim until somebody else decides on it |
| `list_evidence(identifier, review_state)` | The evidence this project holds, with who produced each row |
| `decide_evidence(evidence_id, decision, reason)` | Accept or reject **somebody else's** evidence, and only if the operator granted it |
| `recall(observation_id)` | Read back one observation by its identifier |
| `submit_checkpoint_notes(...)` | Hand off what the next turn needs when a conversation is checkpointed |

An agent cannot propose or approve a document, and cannot archive one. Those are the operator's
acts, enforced in `spec_lifecycle.transition()` rather than only at the API edge.

## Scheduled work

| Tool | Purpose |
|------|---------|
| `create_job(name, agent, message, cron, session_mode=new)` | Create a scheduled job |
| `toggle_job(job_id, enabled)`, `run_job(job_id)` | Manage one |
| `archive_job(job_id)` | Archive one — nothing is deleted. Refused if the job has a loop (operator-only) |

All four require the operator to have enabled the project's scheduled-work allowance. `archive_job`
additionally puts every call to the operator and waits for an explicit answer, whatever this run's
permission posture is — the allowance makes the tool reachable, it is not a standing yes. A job
carrying a purpose and an optional stop condition is a **loop**; its queue is the tasks that name it.

## Identity

Identity and the current run come from credentials the Hub mints per run and binds at spawn. **No
tool accepts a caller-supplied sender, assigner, asker or requester** — an agent cannot claim to be
another actor, and evidence carries the actor that produced it.

## Intentionally absent

There is no tool for inbox retrieval, read receipts, roster or status retrieval, agent
self-registration, configuration mutation, heartbeats, or job inspection. Those either bypass queue
and budget governance, or are supplied at turn start.

`approve_tool_call` is registered on the same server but is **not** part of this surface: it is a
runtime endpoint the harness invokes when a run is in "ask me" permission mode. Calling it
accomplishes nothing and grants nothing.
