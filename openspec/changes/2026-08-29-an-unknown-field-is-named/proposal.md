# An unknown field is named

## Why

`POST /projects/{id}/agent/trigger` accepts a top-level `permission_mode`, answers `200`, and
discards it. The run then proceeds **unsupervised** while the operator's response says it started
normally:

```
POST …/agent/trigger {"agent":"asker","message":"…","permission_mode":"manual"}
  -> 200 {"success": true, "status": "running", "run_id": "run-c10e35f30d81"}
```

No permission card was ever raised. Posture is not a top-level field at all — it travels inside
`overrides`, keyed `permission_mode` (`hub/ui/src/api/modelCatalog.ts:56`,
`hub/ui/src/components/agents/AgentOutputPanel.tsx:327-328`). Sent that way it works and the card
appears in about twelve seconds.

The sibling route on the same API is strict about exactly this shape of mistake:

```
POST …/permission-requests/{id}/decide {"decision":"allow"}
  -> 422 {"detail":[{"type":"missing","loc":["body","allow"],"msg":"Field required"},
                    {"type":"extra_forbidden","loc":["body","decision"],
                     "msg":"Extra inputs are not permitted"}]}
```

This is finding **F116**, found 2026-08-29 while driving row 14 — by making the mistake and being
told nothing.

## The audit: laxness is an omission, not a policy — with one documented exception

Round 1 enumerated **every** request-body model reachable through the running app, by walking
`app.routes` for `POST`/`PUT`/`PATCH` and reading each body model's `model_config`. That measurement
is the change's foundation, and it is reproducible (see item 4 below — it becomes the test).

**36 models forbid extras. 19 do not.** Nothing in `hub/hub/` sets `extra` to `"ignore"` or
`"allow"` on a request model: the entire lax population is the pydantic default, reached by not
writing a line. The two hits for a non-default lax setting are neither of them request models —
`hub/hub/config.py:21` (`SettingsConfigDict`, environment parsing) and `hub/hub/spec_payload.py:68`
(`extra="allow"`, a parsing helper for stored payloads).

The 19:

| Model | Route |
|---|---|
| `agent_trigger.TriggerAgentRequest` | `POST …/agent/trigger` |
| `agents.OperatorAgentCreate` | `POST …/agents` |
| `agents.AgentRequest` | `POST …/agents/request` |
| `agent_chat.ConversationRenameRequest` | `PATCH …/agent/{a}/conversations/{c}` |
| `accounting.BudgetUpdate` | `PATCH …/accounting/budget` |
| `inbound_queue.QueueSettings` | `PATCH …/queue/settings` |
| `session_sync.SessionSyncRequest` | `POST …/session/sync` |
| `spec.EvidenceRecord` | `POST …/project/spec/evidence` |
| `spec.EvidenceDecision` | `POST …/project/spec/evidence/{id}/decision` |
| `spec.DriftResolution` | `POST …/project/spec/drift/{id}/resolve` |
| `spec.ReindexRequest` | `POST …/project/spec/reindex` |
| `spec.RetentionSetting` | `PUT …/project/spec/evidence-retention` |
| `schemas.agents.AgentHeartbeatCreate` | `POST …/agents/{name}/heartbeat` |
| `schemas.agents.AgentOutputCreate` | `POST …/agents/{name}/output` |
| `schemas.agents.ContextUsageCreate` | `POST …/agents/{name}/context-usage` |
| `schemas.logs.LogEventCreate` | `POST …/logs` |
| `schemas.questions.QuestionCreate` | `POST …/questions` |
| `schemas.questions.QuestionAnswer` | `PATCH …/questions/{id}` |
| `schemas.spec.SpecDocumentCreate` | `POST /agent-actions/spec/documents/create` |

### The proof that it is an omission

`EvidenceRecord` exists **twice**, with an identical field list — `identifier`, `kind`, `locator`,
`summary`, `document`, `task_id`:

- `hub/hub/api/v1/agent_actions.py:826` — **forbids** extras.
- `hub/hub/api/v1/spec.py:329` — does not.

`EvidenceDecision` is the same pair (`agent_actions.py`, forbids; `spec.py:340`, does not). And
inside `hub/hub/api/v1/spec.py` alone, `ProposalDecision`, `DocumentCreate`, `MergeRequest`,
`PhaseRequest`, `RigorRequest`, `ArrangeRequest`, `DocumentAdopt` and `DocumentContent` all forbid, while
`EvidenceRecord`, `EvidenceDecision`, `DriftResolution`, `ReindexRequest` and `RetentionSetting` in
the same file do not. Same concept, same module, opposite policy, no stated reason on either side.
That is not two policies; it is one policy and 19 places where nobody wrote the line.

### The one place where it *is* a choice — and a shipped requirement behind it

`hub/hub/schemas/spec.py:13`'s `SpecDocumentCreate` states its laxness deliberately, in its own
docstring:

> No `path`, `kind`, `actor`, `agent` or `run_id` field exists to declare — the route never reads
> the body for any of them, so a caller that sends one anyway is not rejected, it is simply not
> listened to (design D2, D3: unexpressible, not merely refused). `extra` is left at its pydantic
> default (ignore) rather than `"forbid"`, unlike this route's siblings.

And `openspec/specs/agent-document-creation/spec.md:50-58` requires that shape:

> A minted path makes the wrong destination **unexpressible rather than merely refused**.
>
> #### Scenario: No path can be supplied
> - **WHEN** an agent attempts to create a document at a chosen path
> - **THEN** the path is not honoured **and the Hub mints one**

A 422 would not mint one. **A blanket sweep would breach a requirement that shipped 2026-08-12.**
This is exactly the failure the round discipline exists to catch, arriving in round 1 rather than
round 3 only because the audit read the docstrings instead of counting the models.

So the rule cannot be "every request model forbids extras". It has to be "every request model
forbids extras **or says in the code why it does not**" — which is what makes the test below
possible at all, and what makes this change durable rather than a sweep that decays.

## One model, or a shared base?

**A shared base**, plus a test that enumerates the exceptions. The operator's standing preference is
the cleanest solution and "more work is never the objection", and here the cleanest is also the only
one that fixes the finding. F116's complaint is *"two opposite policies inside one API"*. Forbidding
extras on `TriggerAgentRequest` alone leaves 18 of the 19, so the next route written without the
line reproduces F116 exactly — as `TriggerAgentRequest` itself did, with 36 `extra: forbid` siblings
already in the tree.

Writing `model_config = {"extra": "forbid"}` 36 times has already failed as a mechanism: it is
invisible when absent. A base class is visible when absent — `class Foo(BaseModel)` standing next to
54 `class Foo(RequestModel)` — and a test can *see* it.

## What changes

1. **`hub/hub/schemas/common.py` gains `RequestModel`** — a `BaseModel` subclass whose only content
   is `model_config = ConfigDict(extra="forbid")`, with a docstring saying why a request body
   refuses what it cannot honour.
2. **Every request-body model inherits it**, replacing the 36 hand-written `model_config` lines and
   closing the 18 gaps. Models that also need `populate_by_name` or a `mode="before"` validator keep
   them; `RequestModel` sets `extra` only.
3. **`SpecDocumentCreate` is exempt, in code, by name**, with the requirement citation above beside
   it — not by silence.
4. **A test walks `app.routes`** and asserts every `POST`/`PUT`/`PATCH` body model either forbids
   extras or is on a hard-coded exemption list carrying a reason. A new route with a lax body model
   fails the suite. This is the audit above, frozen.
5. **`TriggerAgentRequest`'s 422 is driven live** against a Hub running this branch, sending F116's
   exact body, confirming the response names `permission_mode` — because a passing test is not proof
   of behaviour, and F116 is a route that answered `200` with its tests green.

## What does not change

- **The 36 models that already forbid.** Their behaviour is identical; only where the setting is
  written moves.
- **`SpecDocumentCreate`.** A stray `path` still costs the caller nothing and gains them nothing.
- **Field-level validation everywhere.** This change is about fields that do not exist, not about
  the values of ones that do.
- **`spec_payload.py:68`'s `extra="allow"`** — not a request model; it parses stored payloads.
- **`config.py:21`'s `extra="ignore"`** — environment parsing; unrelated.
- **Response models.** `from_attributes` models are serialisation, not input, and take no `extra`.
- **The posture mechanism.** `overrides["permission_mode"]` stays the way posture travels. This
  change makes the *wrong* way loud; it does not add a second right way.

## The breaking change, said out loud

**Forbidding extras is breaking for any client that sends a field the Hub does not declare.** The
proposal's position is that this is correct and that the blast radius is small, and here is the
measurement rather than the assertion.

**In-repo clients are clean.** Every shipped caller of a lax route sends declared fields only:

| Client | Route | Verified |
|---|---|---|
| `transport/http.py:609-615` | `POST /logs` | body is exactly `event_type`/`agent`/`data`/`severity`; `LogEventCreate` declares all four |
| `transport/http.py:455-458` | `heartbeat` | `status`, optional `message` — both declared |
| `transport/http.py:537` | `session/sync` | `{"data": …}`; `data` is `Dict[str, Any]`, so its *contents* are untouched by `extra` |
| `api/tasks.ts:365`, `AgentOutputPanel.tsx:655`, `NewConversationSurface.tsx:98` | `agent/trigger` | `agent`, `message`, `conversation_id`, `overrides`, `spec_document`, `task_id` — all declared |
| `transport/http.py:161` | all writes | already strips `project_id` and seven identity fields *because* most schemas forbid extras |

**Two lax routes get better, not worse.** `post_agent_output` (`http.py:496-503`) already catches
`400`/`422` and retries with a legacy body — a fallback written for a Hub too old to know
`kind`/`payload`/`run_id`/`sequence`. Today a lax old Hub swallows those silently and records output
with its structure lost; forbidding makes the fallback fire and do its job. That is F116's own
argument, one route over.

**Two hazards a reviewer must check, not dismissed here.**

- `ContextUsageCreate` has a `mode="before"` validator (`schemas/agents.py:133`) that accepts legacy
  keys — `tokens_used`, `input_tokens`, `tokens_limit`, `context_limit`, `max_context_tokens`,
  `context_usage`, `context_usage_ratio`, `updated_at` — and rewrites them into declared ones. It
  returns the input **unchanged** when `"status"` is present. So a caller sending `status` *and* a
  legacy key is tolerated today and refused after. `post_context_usage` passes a caller-supplied
  dict straight through and has no in-repo production caller, only
  `tests/test_http_transport.py:217` — but "no in-repo caller" is not "no caller".
- `SessionSyncRequest.data` is `Dict[str, Any]`; forbidding on the wrapper is safe, and a reviewer
  should confirm no route reads a sibling key beside `data`.

**Out-of-repo clients.** `agentweave-ai` depends on `agentweave-hub`, so the CLI and Hub normally
install together — but a Docker Hub can run a different version than the local CLI, and that is the
one real skew path. A third-party script sending a stray field starts getting a `422` that names the
field: loud, immediate, one line to fix, and strictly more informative than the silence it replaces.

This is the operator's pre-authorised decision **D1** (`STATE.json`), whose `raise_it_if` was "the
audit finds a request model where extras are load-bearing, or a shipped client that relies on the
tolerance". The audit found **one** — `SpecDocumentCreate`, load-bearing on a shipped requirement —
and it is exempted by name rather than swept. No shipped client relies on the tolerance. **Proceed.**

## Open questions for review rounds

- **Does `api-request-strictness` deserve to be its own capability?** The rule spans 55 models across
  every router, so it fits no existing capability document; but a new capability for one rule may be
  the wrong granularity, and `agent-capability-plane` already states a shared HTTP/MCP contract.
  R2 must decide, because the delta directory is the hard-to-undo part.
- **R2 must verify the audit independently** by re-running the route walk, not by reading this
  table. The count is the whole argument.
- **R2/R3 must find every test that sends an extra field to a lax route.** Round 1 did not run the
  hub suite with the change applied; the ~23-minute cost is real, but the number is not a guess to
  carry into implementation.
- **R3 must check** whether any lax model's laxness is depended on by the *UI* in a path round 1 did
  not read — round 1 read the three `agent/trigger` call sites and `accounting.ts:85`, not all
  nineteen.
- **Should the exemption list live in the test or beside the model?** It is written in both here
  (docstring plus test list), which is duplication; the alternative is a marker on the model itself
  that the test reads.
