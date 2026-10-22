---
description: The tools every agent run has for talking to the Hub — messages, tasks, questions, specifications, evidence, the vault and scheduled work.
---

# Agent tools

Every agent run can act on the Hub through one fixed set of tools. The tools are how an agent sends
a message, moves a task, asks you a question, writes a specification, or records evidence. There
is nothing to install and no client configuration to edit: the Hub hands each run what it needs.

## How a run reaches them

The tools are one HTTP contract (`/api/v1/agent-actions`) with two ways in:

- **MCP tools**, injected into CLIs that accept them. Claude Code sees them as
  `mcp__agentweave__<tool>`, and Copilot sees them as `agentweave-<tool>`.
- **`aw-tool`**, a command placed first on the run's `PATH`. It takes the arguments in a JSON file and
  prints one JSON line in reply. Every tool below can be called this way.

A run is told which way it has at the start of its turn. It is told MCP only when MCP is known to
work for that agent.

Each run authenticates with its own credential, `AW_RUN_TOKEN`, valid only while that run is
running. **Identity comes from that credential, never from the arguments.** No tool takes a "from"
or "as" field, and none can act for another agent.

Everything the agent needs at turn start is already in its prompt: queued messages, the team, its
charter, the project's instructions, and any specification document it was given. So the tools
carry **outbound intent only**. There is no tool for reading an inbox.

## Messages and tasks

| Tool | Purpose |
|---|---|
| `send_message(to_agent, subject, content, message_type?, task_id?, conversation_id?, start_new_thread?)` | Message another agent, through its queue. Replies continue the thread they answer. Messages addressed to `operator` or `user` are refused: use `ask_user`. |
| `create_task(title, description?, assignee?, priority?, requirements?, requirement_ids?, spec_document?, acceptance_criteria?, loop_id?, depends_on?)` | Create a task, attributed to the agent. |
| `list_tasks(agent?, limit?, offset?)` | Read the task ledger, optionally by assignee. |
| `get_task(task_id)` | Read one task. |
| `task_history(task_id)` | Who moved a task, when, and between which statuses. |
| `update_task(task_id, status?, notes?, requirement_ids?, spec_document?)` | Move a task, add notes, or link the requirements it serves. Nothing else about a task is the agent's to change. |

## Asking you

| Tool | Purpose |
|---|---|
| `ask_user(questions, blocking?)` | Ask you 1–4 questions, each with 2–8 options. The turn waits for your answer, up to the agent's question timeout. |
| `get_answer(question_id)` | Check whether a question was answered. |

## Specifications and evidence

| Tool | Purpose |
|---|---|
| `create_spec_document(title?, kind?)` | Start a change or roadmap document. The Hub chooses its path. |
| `submit_spec_document(path, …)` | Write the document's structure. The Hub validates it, mints requirement identifiers, and writes the file. At contract or gate rigor, changes become proposals for you. |
| `rename_spec_document(path, subject)` | Name the document once its subject is clear. Refused once it has been approved. |
| `set_spec_size(path, size, reason)` | Record the change's size (fix, small, large) and why. |
| `advance_spec_step(path, to?)` | Move to the next journey step, after you chose to continue. |
| `read_spec_document(path, include?, identifiers?)` | Read the document the agent is implementing. Large reads are written to a file in its checkout. |
| `record_evidence(identifier, summary?, kind?, locator?, document?, task_id?, command?, output?, covers?)` | Record what shows a requirement is satisfied: the command, its output, and whether it covers the requirement fully or partly. |
| `list_evidence(identifier?, document?, review_state?)` | Read the project's evidence. |
| `decide_evidence(evidence_id, decision, reason?)` | Accept or reject someone else's evidence. Needs the *accept or reject evidence* grant, and never works on the agent's own evidence. |
| `amend_spec_document(path, op, reason, how_to_check, …)` | Tester turns only: add a task, or add or change a scenario, from what testing found. Amendments wait for your review. |
| `report_cannot_satisfy(path, criterion, reason)` | Say a criterion cannot be met as written, and why. |
| `record_reconcile(path, summary, gaps?)` | Record what comparing an approved change with its code found. Advisory. |

## Checkpoints and recall

| Tool | Purpose |
|---|---|
| `list_checkpoints(agent?)` | Checkpoints the agent may open: its own, and peers' if granted. |
| `read_checkpoint(checkpoint_id)` | One checkpoint, in full. |
| `recall(observation_id)` | One observation a checkpoint cited, exactly as recorded. Needs the recall grant. |
| `submit_checkpoint_notes(intent, suspicions?, warnings?)` | Notes for the next checkpoint. Offered when a checkpoint is being prepared. |

## Knowledge vault

| Tool | Purpose |
|---|---|
| `vault_map()` | List the vault's entries. |
| `vault_read(entry_id, offset?)` | Read one entry, up to 50,000 characters per page. |
| `vault_report(entry_id, message)` | Report an entry that looks wrong. |
| `vault_add(paths, distil, visibility?, type?, dated?)` | Add files to the vault by path. |

## Agents and scheduled work

| Tool | Purpose |
|---|---|
| `request_agent(name, template, task)` | Create a new agent modelled on an existing one: same runner, charter and configuration, no grants. Limited by the project's agent budget. |
| `create_job(name, agent, message, cron, session_mode?, enabled?)` | Create recurring work. |
| `create_loop(name, agent, message, cron?, purpose?, stop_at?, stop_when_queue_empties?, …)` | Create a loop with a purpose and a stop condition. |
| `create_flow(name, agent, message, spec_document_id, …)` | Create a flow that works through an approved specification. |
| `toggle_job(job_id, enabled)` | Pause or resume recurring work. |
| `run_job(job_id)` | Fire recurring work now. |
| `archive_job(job_id)` | Archive recurring work. Always asks you first. |

Creating, running and archiving scheduled work needs **Agents may start jobs, flows and loops** to
be on in the project's settings. It is off by default.

## Intentionally absent

There is no tool for reading an inbox, read receipts, listing the roster or status, an agent
registering itself, changing configuration, heartbeats, or inspecting jobs. Those would either
bypass the queue and its budgets, or are already given at turn start.

`approve_tool_call` is served by the same MCP server but is **not** an agent tool. The CLI itself
calls it to ask the Hub for a permission decision. It is not described to agents and cannot be
called through `aw-tool`.
