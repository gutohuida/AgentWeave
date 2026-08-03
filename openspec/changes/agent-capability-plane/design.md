## Context

`hub/hub/mcp_server.py` is already a stdlib HTTP adapter, which is the right transport shape, but it
authenticates with the same `ApiKey` used by the operator dashboard and repeats identity in request
bodies and headers. Possession of that key grants every project route, so route-level checks inside
the adapter are not a security boundary: an agent can bypass the adapter with `urllib` or a shell
command. The command path has the same issue through `HttpTransport`.

The durable actor already exists as `Run(project_id, agent, status)`. What is missing is an
unforgeable credential that resolves to that actor and a route namespace that accepts only that
credential.

## Goals / Non-Goals

**Goals:**

- One run-scoped authentication mechanism for all agent transports.
- One application service layer and route contract for allowed agent intent.
- Identity and run derived by the server, never accepted from an agent payload.
- Durable run attribution on every effect.
- Equal operations, validation, governance, and errors through HTTP, MCP, and commands.
- No full project/operator credential in an agent process.

**Non-Goals:**

- Public remote API, federation, user accounts, OAuth, or multi-tenant authorization.
- Runner/agent/charter separation or charter scope enforcement (a separate successor).
- Replacing the operator REST API or dashboard authentication.
- Giving agents new coordination/configuration reads.
- Single-runtime deletion of watchdog/local/git transports; this change only provides its required
  replacement capability boundary.

## Decisions

### 1. A random per-run bearer secret resolves to the actor

At run creation the Hub generates an `aw_run_` secret with at least 256 bits of entropy, stores only
SHA-256 on `Run.capability_token_hash`, and injects the plaintext as `AW_RUN_TOKEN`. The agent API
hashes the bearer token and resolves a `Run` with that digest and `status="running"`; project and
agent come from the row. Constant-time digest comparison is retained where direct comparison is
needed.

The token is never written to output, event payloads, command arguments, or response bodies. A
terminal run is rejected even if its secret remains in a child process. Database compromise does
not reveal active bearer secrets.

### 2. Separate route namespaces make privilege separation structural

Operator routes remain under their current `/api/v1/*` paths and accept only project API keys.
Agent actions live under `/api/v1/agent-actions/*` and accept only run credentials. `get_project`
does not learn how to accept a run token, so a run token cannot drift into operator access. The
agent dependency does not accept project keys, so an operator key plus caller-supplied headers
cannot impersonate a run.

Payload schemas contain no `from_agent`, `assigner`, `from_agent`, `run_id`, project, or equivalent
actor fields. This makes impersonation absent from the contract instead of merely rejected by
convention.

### 3. Services own behavior; transports own serialization

Allowed operations move behind actor-aware application functions. Operator endpoints may call
those services with an explicit operator actor where behavior genuinely overlaps, while agent
routes call them with the authenticated run actor. The MCP server and CLI command adapter call the
agent HTTP API and contain no queue, budget, attribution, or lifecycle decisions.

This yields one validation/governance implementation and makes parity testable as request/response
equivalence rather than comparing duplicated business logic.

### 4. Agent permissions are an allowlist

The plane includes exactly:

- send peer message;
- create/list/get/update shared tasks;
- ask the operator and read the answer to a question created by the same agent;
- request an agent under existing template/budget governance;
- create/run/toggle/delete jobs under existing operator allowance.

It excludes roster, inbound queue, output/history, project settings, agent configuration, charter,
workspace/specification state, credentials, and arbitrary operator endpoints. New operator APIs do
not become agent capabilities by default.

### 5. Attribution is stored on effect rows

Agent-created `Message`, `Task`, `Question`, `AIJob`, and requested `Agent` outcomes retain the
creating run ID (and update-run ID where updates are mutable). Existing human/operator rows remain
nullable. Foreign keys are deliberately loose where historical data or lifecycle retention already
uses loose run references, matching `AgentOutput.run_id`; project/agent/run consistency is enforced
in the service transaction and tested.

Event logs remain observability, not the sole source of attribution.

### 6. Adapter errors retain typed meaning

The HTTP API returns its normal status and structured detail. MCP/commands may wrap transport
serialization but SHALL preserve denied/not-found/conflict/validation meaning; adapters must not
turn every failure into success-with-string or silently return an empty list. This corrects current
MCP behavior such as `list_tasks` swallowing authentication/connection errors into `[]`.

## Risks / Trade-offs

- Refactoring mature endpoints can create behavioral drift. Contract tests run the same operation
  through application HTTP and MCP/command adapters and compare persisted effects.
- A bearer secret exists in the child environment. That is unavoidable for process authentication;
  it is narrower and shorter-lived than today's full project key, and terminal status revokes it.
- SHA-256 lookup adds an indexed column and one DB query per request. Local latency is negligible;
  correctness and revocation outweigh an in-memory-only token map that would fail across restart.
- Historical effects have null run attribution. The migration does not invent provenance.

