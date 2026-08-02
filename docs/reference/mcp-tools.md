# Agent Tool Surface

The Hub exposes one identity-bound tool surface and injects its stdio configuration whenever it
starts a compatible Claude or Codex runner. Operators do not run `agentweave mcp setup` or edit an
agent client's global configuration.

Turn-start state is already in the prompt: delivered queue entries, roster, charter, project
instructions, and the selected access path. The surface carries outbound intent only.

## Available tools

| Tool | Purpose |
|------|---------|
| `send_message(to_agent, subject, content, ...)` | Queue an attributable peer message under the hop budget |
| `create_task(title, ...)` | Create a task attributed to the bound agent |
| `list_tasks(agent?)` | Read the shared task ledger |
| `get_task(task_id)` | Read one task |
| `update_task(task_id, status)` | Update task lifecycle state |
| `ask_user(question, blocking?)` | Ask the operator an attributable question |
| `get_answer(question_id)` | Check the answer to that question |
| `request_agent(name, template, task)` | Create an agent from a pre-approved template under the project agent budget |
| `create_job(...)`, `toggle_job(...)`, `run_job(...)`, `delete_job(...)` | Mutate scheduled work only when the operator enabled the project allowance |

Identity and the current Run come from `AW_AGENT_IDENTITY` and `AW_RUN_ID`, which the Hub binds at
spawn. No tool accepts a caller-supplied sender, assigner, asker, or requester.

## Intentionally absent

There is no tool for inbox retrieval, read receipts, roster/status/context retrieval, agent
self-registration, configuration mutation, heartbeats, job inspection, or checkpoints. Those either
bypass queue/budget governance, are supplied at turn start, belong to the operator surface, or remain
ordinary workspace commands (`agentweave checkpoint`).

## Command-path parity

When a runner cannot use a tool-protocol server, the turn prompt selects ordinary `agentweave`
commands instead. Messaging, task work, questions, and `agentweave agent request` reach the same Hub
endpoints with the same bound identity, queue, hop budget, agent budget, and job allowance.
