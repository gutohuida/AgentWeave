---
description: The Hub's HTTP API — authentication, URL layout, every route group, the live event streams and request limits.
---

# Hub API

The app is a client of this API, and so is anything you build. Everything the app does, you can do
over HTTP.

!!! note "Two audiences, two credentials"
    **Operator routes** take the instance key. **Agent actions** (`/api/v1/agent-actions/…`) take a
    run's own token and are documented as [agent tools](agent-tools.md). Neither credential works
    on the other's routes.

## Authentication

Send the instance key as a bearer token:

```bash
curl -H "Authorization: Bearer $AW_KEY" http://localhost:8000/api/v1/projects
```

The key (`aw_live_…`) is in `~/.agentweave/hub/.env` as `AW_BOOTSTRAP_API_KEY`. The app on
`localhost` fetches it from `GET /api/v1/setup/token`, which answers only local requests.

The key says *who you are* (the operator), not *which project*. Project identity is always in the
URL, and choosing a project is navigation, not authentication.

## URL layout

| Prefix | What lives there |
|---|---|
| `/api/v1/projects` | The project collection: list, open, create, settings, relocate, delete. |
| `/api/v1/projects/{project_id}/…` | Everything that belongs to one project. Almost every route. |
| `/api/v1/events`, `/api/v1/model-catalog`, `/api/v1/fs`, `/api/v1/setup` | Instance-wide. |
| `/api/v1/agent-actions/…` | Agent runs only (run token). |
| `/health` | Liveness, runtime (`native` or `docker`), and whether the bundled app is stale. |

## Route groups

All paths below are relative to `/api/v1/projects/{project_id}` unless they start with `/api/v1`.

### Projects (`/api/v1/projects`)

`GET /api/v1/projects` · `POST /api/v1/projects/open` (a path; registers or reopens) ·
`POST /api/v1/projects/create` · `GET|DELETE /api/v1/projects/{id}` ·
`GET|PUT /api/v1/projects/{id}/settings` · `GET /api/v1/projects/{id}/main-branch-suggestion` ·
`POST /api/v1/projects/{id}/relocate`

### Agents, runners and charters

| Route | Purpose |
|---|---|
| `GET|POST /agents` | List agents, or create one (`name` plus `provider` and `model`, or a `runner_id`, and optionally `charter_id`). |
| `PATCH /agents/{name}` · `POST /agents/{name}/archive|unarchive` | Configure, archive, restore. |
| `GET /agents/launchability` · `GET /agents/agent-context?agent=` | Whether each agent can launch, and why not. Preview an agent's turn context. |
| `GET|POST /runners` · `GET|PATCH|DELETE /runners/{id}` · `GET /runners/launchability[-by-provider]` | Runners. |
| `GET|POST /charters` · `GET|PATCH|DELETE /charters/{id}` | Charters. |
| `GET|PUT /project/instructions` | Project instructions. |
| `GET /api/v1/model-catalog` | Models, effort levels and postures per provider. |

### Conversations and runs

| Route | Purpose |
|---|---|
| `POST /agent/trigger` | Send an agent a message. Body: `agent`, `message`, and optionally `conversation_id`, `overrides` (`model`, `effort`, posture), `task_id` (bind the run to a task), `review_task_id` (start a review turn), `spec_document`. |
| `POST /agent/{agent}/stop` | Stop the agent's running turn. |
| `GET /agent/{agent}/conversations` · `GET /conversations` | List conversations. |
| `GET /agent/{agent}/chat/{conversation_id}` | A conversation's full timeline. |
| `PATCH /agent/{agent}/conversations/{id}` · `POST …/archive|unarchive` | Rename, archive, restore. |
| `GET /queue/{agent}` · `GET /queue/{agent}/status` | An agent's inbound queue, and *why* its input is waiting. |
| `POST /queue/entries/{id}/release` · `DELETE /queue/entries/{id}` | Release held input, or discard it. |
| `POST /conversations/{id}/checkpoint` · `POST /checkpoints/{id}/cutover` | Checkpoint a conversation, and cut over to its successor. |

### Questions and permissions

`GET|POST /questions` · `GET|PATCH /questions/{id}` (answer) · `POST /questions/{id}/decline` ·
`GET /permission-requests` · `POST /permission-requests/{id}/decide|dismiss`

### Tasks

| Route | Purpose |
|---|---|
| `GET|POST /tasks` · `GET|PATCH|DELETE /tasks/{id}` | Tasks. A status change in `PATCH` goes through the [lifecycle](task-lifecycle.md) rules. |
| `GET /tasks/{id}/story` · `GET /tasks/{id}/transitions` | The task's whole story, and its transition history. |
| `POST /tasks/{id}/land` | Review and approve a completed task in one step. |
| `GET /tasks/{id}/integration-preview` · `GET /tasks/{id}/integrations` · `POST /tasks/{id}/integrations/retry` | What approval would merge, what it did merge, and retrying a skipped merge. |
| `GET /tasks/{id}/checks` · `POST /tasks/{id}/checks/run` | Quality checks. |
| `POST /tasks/{id}/dependencies` · `DELETE /tasks/{id}/dependencies/{depends_on}` | Dependencies. |
| `GET /worktrees` · `GET /worktrees/conflicts` | Checkouts, and conflicts between them. |

### Specifications and evidence (under `/project`)

| Route | Purpose |
|---|---|
| `GET /project/spec` · `GET /project/documents` · `POST /project/documents` | Read the corpus. Create a document. |
| `POST /project/documents/propose?path=` | Propose. Returns `blocking` and `warnings`, plus `proposed: true` when it moved. |
| `POST /project/documents/phase?path=&to=` | Approve or reopen. Body: `reason`, `approve_anyway`, `delivery_agent`, `draft_next_slice`. |
| `POST /project/documents/{path}/rigor` · `GET …/rigor-history` | Rigor. |
| `GET …/proposals` · `POST …/proposals/{id}/accept|reject|withdraw` | Agent proposals at contract or gate rigor. |
| `GET …/amendments` · `POST …/amendments/review` | Tester amendments. |
| `GET …/fold-draft` · `POST …/fold` | Fold a change into a capability. |
| `GET /project/spec/coverage` · `GET /project/spec/requirements/{identifier}` | Coverage, and one requirement's story. |
| `GET|POST /project/spec/evidence` · `POST /project/spec/evidence/{id}/decision|overturn` | Evidence. |
| `POST /project/spec/drift/detect` · `GET /project/spec/drift` · `POST /project/spec/drift/{id}/resolve` | Drift. |
| `POST /project/spec/reindex|adopt|convert` · `POST /project/spec/documents/arrange` | Corpus maintenance. |

### Jobs, loops and the vault

| Route | Purpose |
|---|---|
| `GET|POST /jobs` · `GET|PATCH /jobs/{id}` · `POST /jobs/{id}/run|archive` · `GET /jobs/{id}/history` | Jobs. A job with `purpose`, `stop_at` or `stop_when_queue_empties` is a loop. |
| `GET /loops` · `GET /loops/{id}` · `POST /loops/{id}/control|archive` | Loops. |
| `GET /vault/map` · `GET /vault/entries/{id}` | Read the vault. |
| `POST /vault/sources` (text) · `POST /vault/files` (upload) · `POST /vault/paths` (local paths) | Add sources. |
| `POST /vault/sources/{id}/distil` | Extract facts now. |
| `GET /vault/contradictions` · `POST /vault/contradictions/{id}/resolve` · `GET /vault/reports` | Review. |
| `GET /manager/jobs` · `PATCH /manager/jobs/{key}` · `GET /manager/activity` | Manager jobs. |

### Accounting, traces and logs

`GET /accounting` · `GET /accounting/conversations/{id}` · `PATCH /accounting/budget` ·
`GET /ledger` · `GET|DELETE /traces` · `GET /traces/{id}` · `GET /traces/by-run/{run_id}` ·
`GET /traces/export` · `GET|PUT /traces/settings` · `GET|POST /logs` · `GET /status`

## Live events

The app is driven by server-sent events. An `EventSource` cannot send headers, so you first trade
your key for a short-lived ticket:

```bash
# Every project, each event stamped with its project_id:
curl -H "Authorization: Bearer $AW_KEY" http://localhost:8000/api/v1/events/ticket
# → {"token": "aw_optick_…", "expires_at": "…"}
curl -N "http://localhost:8000/api/v1/events?token=aw_optick_…"

# One project:
curl -H "Authorization: Bearer $AW_KEY" http://localhost:8000/api/v1/projects/$P/events/ticket
curl -N "http://localhost:8000/api/v1/projects/$P/events?token=aw_ticket_…"
```

Tickets live for `AW_TICKET_TTL` seconds (300 by default). `GET /events/history` returns recent
events for a project.

## Limits

| Limit | Value |
|---|---|
| Request body | 1 MiB (`AW_MAX_BODY_SIZE`); vault file uploads 10 MiB |
| Agent name | `^[a-zA-Z0-9_-]{1,32}$`; `user` and `operator` are reserved |
| Message `content` | 10,000 characters |
| Agent output event | 64 KiB payload; 8 KiB per tool input or output |

## Errors

Refusals are meant to be read. A `409` or `422` carries a `detail` that says what was refused and
what to do instead. For example, an approval with gaps returns `409` with code
`approval_warnings`, the list of gaps, and how to approve anyway. A body field sent as a query
parameter is named back to you rather than silently ignored.
