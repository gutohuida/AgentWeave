---
description: The tools every agent run has for talking to the Hub — messages, tasks, questions, specifications, evidence, the vault and scheduled work.
---

# Agent tools

Every agent run can act on the Hub through one fixed set of tools. The tools are how an agent sends
a message, moves a task, asks you a question, writes a specification, or records evidence. There
is nothing to install and no client configuration to edit: the Hub hands each run what it needs.

!!! note "Profiles keep the name *agent* in the tools"
    In the app a configured agent is a [profile](../guides/agents.md), a conversation is a thread,
    and one turn is a run. The tools' descriptions use those words, but the tool names and their
    parameters do not change: `to_agent`, `assignee`, `agent` and `request_agent` all name a
    profile. Each call is made by one run of a profile, and several runs of one profile may be
    calling at once, each with its own credential.

## How a run reaches them

The tools are one HTTP contract (`/api/v1/agent-actions`) with two ways in:

- **MCP tools**, injected into CLIs that accept them. Claude Code sees them as
  `mcp__agentweave__<tool>`, and Copilot sees them as `agentweave-<tool>`.
- **`aw-tool`**, a command placed first on the run's `PATH`. It takes the arguments in a JSON file and
  prints one JSON line in reply. Every tool below can be called this way.

A run is told which way it has at the start of its turn. It is told MCP only when MCP is known to
work for that profile's runner.

Each run authenticates with its own credential, `AW_RUN_TOKEN`, valid only while that run is
running. **Identity comes from that credential, never from the arguments.** No tool takes a "from"
or "as" field, and none can act for another profile or another run.

Everything the run needs at its start is already in its prompt: queued messages, the team, its
charter, the project's instructions, and any specification document it was given. So the tools
carry **outbound intent only**. There is no tool for reading an inbox.

## Messages and tasks

| Tool | Purpose |
|---|---|
| `send_message(to_agent, subject, content, message_type?, task_id?, conversation_id?, start_new_thread?)` | Message another profile, through its queue. Replies continue the thread they answer. Messages addressed to `operator` or `user` are refused: use `ask_user`. |
| `create_task(title, description?, assignee?, priority?, requirements?, requirement_ids?, spec_document?, acceptance_criteria?, loop_id?, depends_on?)` | Create a task, attributed to the profile. |
| `list_tasks(agent?, limit?, offset?)` | Read the task ledger, optionally by assignee. |
| `get_task(task_id)` | Read one task. |
| `task_history(task_id)` | Who moved a task, when, and between which statuses. |
| `update_task(task_id, status?, notes?, requirement_ids?, spec_document?)` | Move a task, add notes, or link the requirements it serves. Nothing else about a task is the profile's to change. |
| `hand_out_task(task_id, agent, review?)` | **A build's lead only.** Hand one of the build's tasks to one of its builders, or with `review` true hand completed work to its reviewer pool, and start that profile's run on it. Anyone else is refused. |

## Asking you

| Tool | Purpose |
|---|---|
| `ask_user(questions, blocking?)` | Ask you 1–4 questions, each with 2–8 options. The turn waits for your answer, up to the profile's question timeout. |
| `get_answer(question_id)` | Check whether a question was answered. |

## Specifications and evidence

| Tool | Purpose |
|---|---|
| `create_spec_document(title?, kind?)` | Start a change or roadmap document. The Hub chooses its path. |
| `submit_spec_document(path, …)` | Write the document's structure (a requirement may carry `facts`, the vault facts it rests on, by id). The Hub validates it, mints requirement identifiers, and writes the file. At contract or gate rigor, changes become proposals for you. |
| `rename_spec_document(path, subject)` | Name the document once its subject is clear. Refused once it has been approved. |
| `set_spec_size(path, size, reason)` | Record the change's size (fix, small, large) and why. |
| `advance_spec_step(path, to?)` | Move to the next journey step. The agent calls it itself once the step's output is written and it has no question for you, and says which step it moved to. |
| `read_spec_document(path, include?, identifiers?)` | Read the document the run is implementing. Large reads are written to a file in its checkout. |
| `record_evidence(identifier, summary?, kind?, locator?, document?, task_id?, command?, output?, covers?)` | Record what shows a requirement is satisfied: the command, its output, and whether it covers the requirement fully or partly. |
| `list_evidence(identifier?, document?, review_state?)` | Read the project's evidence. |
| `decide_evidence(evidence_id, decision, reason?)` | Accept or reject someone else's evidence. Needs the *accept or reject evidence* grant, and never works on the profile's own evidence. |
| `amend_spec_document(path, op, reason, how_to_check, …)` | Tester turns only: add a task, or add or change a scenario, from what testing found. Amendments wait for your review. |
| `report_cannot_satisfy(path, criterion, reason)` | Say a criterion cannot be met as written, and why. |
| `record_reconcile(path, summary, gaps?)` | Record what comparing an approved change with its code found. Advisory. |
| `acknowledge_spec_gap(path, code, where, reason)` | Leave one gap of a document the profile wrote open on purpose, with a reason. It shows as acknowledged and counts as handled for readiness, until the gap is fixed. Not for refusals, unreviewed amendments or vault warnings. |
| `answer_pre_mortem(path, firing, note, finding?)` | Answer the pre-mortem of a document the profile wrote: one finding by number, or every unanswered one when `finding` is left out. The note, of what the profile did, is required. Only the document's author may answer, and only the newest written firing. |
| `confirm_acceptance_criteria(path, confirmations)` | Record, for each acceptance criterion, that it was checked against the current code as `new` or `guard`. Approval is refused until every criterion has a current confirmation. Allowed only while the document is exploring; all entries or none. |
| `tidy_spec_document(path, op, reason, …)` | **Needs the *Keep the specs true* switch on the profile.** Fold a built change into a capability, create or edit a capability, mark a document superseded, or fix roadmap links. Each act applies at once and is listed for you with its reason. Approving, archiving and deciding amendments or evidence stay yours. |

## Checkpoints and recall

| Tool | Purpose |
|---|---|
| `list_checkpoints(agent?)` | Checkpoints the profile may open: its own, and peers' if granted. |
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
| `vault_append(entry_id, text)` | Add text to the end of a text source. It is distilled again. |
| `vault_replace_passage(entry_id, old, new)` | Replace one passage of a text source. `old` must occur exactly once. |
| `vault_replace_file(entry_id, path)` | Replace the file of a PDF or image source. |
| `vault_archive(entry_id)` | Archive a source: it and the facts citing only archived sources leave the map, and stay readable by id. |
| `vault_restore(entry_id)` | Restore an archived source. |

The write tools record the change under the profile's name and run.

## Dashboards

| Tool | Purpose |
|---|---|
| `dashboard_query_reference(tables?)` | Every table and column a dashboard query can read, with the query rules, known traps and limits. Without `tables`, columns are listed by name only. |
| `run_dashboard_query(sql)` | Run one read-only query over the current project's data. Stopped after 10 seconds, cut at 10,000 rows. |
| `save_dashboard(name, description, panels, dashboard_id?, base_version?)` | Save a new dashboard of panels, each a query and one of five chart kinds. |
| `list_dashboards()` | The project's dashboards, most recently saved first. |
| `read_dashboard(dashboard_id)` | One dashboard with its panels and version. |
| `edit_dashboard(dashboard_id, base_version, operations)` | Change a dashboard in place: add, remove, change or move panels, rename it or change its description. All operations or none. |
| `run_dashboard(dashboard_id)` | Run a saved dashboard and see each panel's rows or error. |
| `undo_dashboard(dashboard_id)` | Restore the dashboard's previous version. |

See [Dashboards](../guides/dashboards.md).

## The project's record

| Tool | Purpose |
|---|---|
| `read_model_record()` | Per model: tasks built and approved, send-backs by reason, runs, and API-equivalent cost over priced runs. A run with no price is counted as unpriced, never as zero. |
| `read_shells()` | What the shells in this thread's Terminal tab show now. Read only: it types into nothing. |

## Thread chapters

| Tool | Purpose |
|---|---|
| `read_chapters()` | The project's chapters and every version of them, with author, who asked, time and reason. |
| `save_chapters(chapters, reason)` | Save the complete chapter set as a new version under your name. Citations must resolve and every thread knot must sit in exactly one chapter. |

## Profiles and scheduled work

| Tool | Purpose |
|---|---|
| `request_agent(name, template, task)` | Create a new profile modelled on an existing one: same runner, charter and configuration, no grants. Limited by the project's agent budget. |
| `create_job(name, agent, message, cron, session_mode?, enabled?)` | Create recurring work. |
| `create_loop(name, agent, message, cron?, purpose?, stop_at?, stop_when_queue_empties?, …)` | Create a loop with a purpose and a stop condition. |
| `create_flow(name, agent, message, spec_document_id, …)` | Create a flow that works through an approved specification. |
| `toggle_job(job_id, enabled)` | Pause or resume recurring work. |
| `run_job(job_id)` | Fire recurring work now. |
| `archive_job(job_id)` | Archive recurring work. Always asks you first. |

Creating, running and archiving scheduled work needs **Agents may start jobs, flows and loops** to
be on in the project's settings. It is off by default.

### The mender

These tools are served to every run but answered only for the Hub's own `mender` profile, which is
woken by a stall. Any other caller is refused.

| Tool | Purpose |
|---|---|
| `mend_stalls()` | The project's open stalls, newest first. |
| `mend_task_branch(task_id, commit?)` | Land an approved task's work whose merge is stuck. With `commit`, a resolution made in the mend's scratch checkout: the Hub runs the project's checks on it and merges it. Without, it only retries the merge. |
| `mend_withdraw_input(entry_id)` | Withdraw input waiting in another profile's queue, so its next firing briefs it again. |
| `mend_reset_task(task_id, status, assignee?)` | Hand a stuck task back: to `assigned`, back to `pending`, or to `under_review`. |
| `mend_end_stall(stall_id, outcome, summary)` | End the mender's stall as `fixed` or `gave_up`, with a plain summary for you. |

## Intentionally absent

There is no tool for reading an inbox, read receipts, listing the roster or status, a profile
registering itself, changing configuration, heartbeats, or inspecting jobs. Those would either
bypass the queue and its budgets, or are already given at turn start.

`approve_tool_call` is served by the same MCP server but is **not** an agent tool. The CLI itself
calls it to ask the Hub for a permission decision. It is not described to agents and cannot be
called through `aw-tool`.
